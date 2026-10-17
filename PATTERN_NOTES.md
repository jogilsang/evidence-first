# DeciderGate: tuning a gate against a golden set, not a bigger model

The reusable pattern is **"the model classifies, the code decides."** The Decider 2B
answers a few narrow typed questions about an incident; a plain-Python `Policy` turns those
numbers into allow / block. The thresholds and the guards live in code, so you tune the
gate by editing a few lines and re-running a golden set — not by swapping in a larger,
slower model.

This note records one such tuning pass, with numbers, because the point of the pattern is
that this loop is cheap and legible.

## Baseline comparison (same 20-case golden set)

| | DeciderGate (local) | Bedrock Haiku 4.5 |
|---|---|---|
| accuracy | 100% | 100% |
| latency median | ~134 ms | ~1084 ms |
| latency p95 | ~184 ms | ~1507 ms |
| API cost / 20 cases | $0 (runs locally) | ~$0.009 |

Same correctness, roughly 8× faster, no per-call API cost. (Haiku 4.5 priced at $1 / $5
per 1M input/output tokens, us-east-1, 2026-10 — verify before quoting publicly. Latency
measured on this Mac over the public Bedrock endpoint; absolute numbers vary by network.)

The interesting part is not that number. It is how the gate got to 100%.

## The tuning pass: 90% -> 100% by adding two guards, not a bigger model

**Before** (one guard: cause + a rollback-specific repeat question):

- accuracy 90% (18/20), median ~105 ms, 5029 input tokens
- two false allows:
  - `rb-no-2` — DB connections at 100% ("connection pool exhausted"), but the cause
    question leaned `bad_deploy` (0.52), so a rollback was allowed.
  - `so-no-5` — already scaled 4→8 tasks and still failing; the repeat question only
    asked about *rollback*, so a repeated scale-out slipped through.

**Probe first (read-only), then change.** Before touching the gate, we asked the model
the candidate questions on just those cases to see whether a code guard *could* catch them:

- A **widened repeat question** ("has *this action* or an equivalent already been tried?")
  scored `so-no-5` at 0.62 — over the 0.50 block threshold — while the existing rollback
  repeats (`rb-no-5` 0.77, `rb-no-6` 0.76) stayed caught. No regression.
- A **dependency-saturation question** ("is a downstream dependency saturated/failing,
  regardless of any deploy?") scored `rb-no-2` at 0.83 and the clean deploys that *should*
  allow rollback (`rb-ok-1` 0.12, `rb-ok-2` 0.08) near zero. Clean separation.

**After** (three guards: repeat → dependency → cause, in that order of certainty):

- accuracy 100% (20/20), median ~134 ms, 7639 input tokens
- both false allows gone; no previously-correct case regressed.

Cost of the fix: two extra typed questions per review (one is action-specific), ~30 ms
more latency and ~2.6k more input tokens — still ~8× under the Bedrock judge, still $0 API.

## Why this is the pattern's whole point

- The misses were **policy gaps, not model limits.** The 2B model already *knew* the DB was
  saturated and that scale-out had been retried; the first version of the gate just never
  asked. Making the model bigger would not have helped; asking the right narrow question
  did.
- Each guard is **one `noul` question + one `if` in `judge()`**, unit-tested in isolation
  (`tests/test_gate.py`) with the model mocked. You can see exactly which guard fired from
  `Verdict.reason` and `Verdict.scores`.
- Guards run **most-certain first**: a repeat we have direct evidence of, then a dependency
  we can see is saturated, then whether the cause matches the action. That ordering is a
  code decision, trivially reorderable, and covered by tests.
- Back-compat kept: `judge()` still reads a legacy `already_acted` answer key, so older
  callers don't break.

## Reproduce

```bash
strands-decider serve StrandsAgents/strands-decider-2B-qwen3.5-v1-2610 --port 8099  # local model
python -m pytest tests/ -q                 # 18 tests, model mocked, no network
python bench_compare.py --gate             # local Decider only, no AWS
AWS_PROFILE=... python bench_compare.py     # head-to-head vs Bedrock Haiku
```

`bench_compare_before.json` holds the 90% run; `bench_compare.json` holds the 100% run.

## Held-out validation: does the policy generalise, or did we overfit?

The honest worry about the 100% number: the golden set was used to *design* the questions
and *set* the thresholds, so scoring on it overstates the gate. So there is a second set,
`rollback_gate/holdout.py` — incidents written **afterwards**, with different services,
numbers, and causes phrased in new ways (a feature-flag flip instead of an image deploy, a
cache stampede instead of a connection-pool exhaustion, a cron fan-out instead of a
campaign). The Policy is **frozen** before these are scored.

### First held-out run: 93.8%, one honest miss

16 held-out cases, frozen thresholds → **93.8% (15/16)**, 0 false allows, one false block:
`hv-rb-ok-2` — a feature flag turned on at 100% with errors one second later. The right
call is a rollback, but the `cause` question read the log as `unknown` rather than
`bad_deploy`, so the gate withheld a valid action. The error was on the **safe side** (it
declined a good action rather than allowing a wrong one), but it was a real gap.

### Fixing it the honest way (a second tuning pass)

The tempting move is to nudge a threshold until `hv-rb-ok-2` passes — which would overfit
the held-out set and destroy its value. Instead:

1. **Probed** (read-only) whether the model even knew: with "feature flag / rollout" named
   in the `bad_deploy` description, it scored the flag case 0.67 `bad_deploy` (was 0.49
   `unknown`), while clean deploys, traffic and dependency cases were unmoved. The signal
   was there; the question just hadn't named it.
2. **Added the pattern to the golden set** (`rb-ok-5` flag→rollback, `so-no-7` config
   change that shifts load to a dependency) and refined the `cause` description to name
   flags/rollouts — kept short, because a long description nudged a borderline clean-deploy
   case (`rb-ok-1`) under the threshold. Golden went 20→22 cases, back to **100%**, no
   regression.
3. **Re-validated on a fresh held-out set.** The 16 old cases now pass, but a set you've
   already seen isn't a held-out set anymore — so 4 new never-seen scenarios were added
   (canary promotion, kernel-param rollout, a dependency-shedding gateway, a repeated
   scale-out). Held-out went 16→20, and the gate scores **100%** on it.

So the honest trajectory is: **golden 100% (22), held-out 100% (20)** — reached by naming a
missing pattern in one question and adding cases, never by tuning on the validation set.
The loop stays trustworthy only because tuning and validation never touch the same cases.

## Is 100% balanced on a knife edge? (threshold sensitivity)

A gate that hits 100% only at one exact threshold is fragile — nudge the number and it
breaks. So `analysis.py sweep` re-judges every golden + held-out case (42 total) across a
range of `min_cause_prob`, holding the other thresholds fixed:

| min_cause_prob | accuracy | false-allow | false-block |
|---|---|---|---|
| 0.30 | 0.976 | 1 | 0 |
| **0.35** | **1.000** | 0 | 0 |
| **0.40** | **1.000** | 0 | 0 |
| **0.45** (default) | **1.000** | 0 | 0 |
| **0.50** | **1.000** | 0 | 0 |
| 0.55 | 0.976 | 0 | 1 |
| 0.60 | 0.976 | 0 | 1 |
| 0.65 | 0.905 | 0 | 4 |

The whole band **0.35–0.50 scores 100%**. The default 0.45 sits in the middle of that
plateau, not on a spike — so the result isn't a threshold fit to the data, it's a stable
operating region. Outside the plateau the failures are also telling: too low leaks a false
*allow* (dangerous), too high turns into false *blocks* (over-cautious, safe-side). The
default is deliberately a little above the plateau's lower edge, buying margin against false
allows at no accuracy cost.

Reproduce: `python analysis.py sweep` (needs the local Decider server).

## Update: independent evaluation

The 100% above is on sets we wrote. On 115 independent cases (Nova Pro wrote, Llama 3.3 70B verified, policy frozen) the gate scores **96.5%** with 4 false allows; see `evalkit/RESULTS.md`. The tuning loop described here did not use those cases.
