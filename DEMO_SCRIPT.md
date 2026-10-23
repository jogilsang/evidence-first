# Demo script — DeciderGate (target < 3:00)

> **Submitted cut:** `record/make_video.py` renders a ~168 s version (English captions plus English voice-over from the macOS `say` voice; no cloud call) from real output: hook, pattern, code, scenes 1-5, the real Bedrock-driven agent run (recorded transcript), the Haiku comparison, the independent evaluation (tuned 100% vs independent 96.5%, second domain 97.0%), the threshold sweep, close. The beats below are the longer shot list.

Public video requirement: under 3 minutes, publicly viewable. English captions; narration
optional. This script runs the real `demo.py` and the real `bench_compare.py`; nothing is
staged.

Record at 1280×720+, terminal font large enough to read at 720p. Run `python demo.py --slow`
so the scenes pause for the camera.

---

## 0:00–0:18 — The hook (the problem, in one line)

**On screen:** title card → `An AI agent that can act on your infrastructure is one
confident wrong decision away from an outage.`

**Caption / VO:**
> Give an agent the power to roll back or scale your service, and the danger isn't that it
> can't decide — it's that it decides *confidently* and *wrong*. DeciderGate is the calm
> colleague that asks for evidence before the agent acts.

---

## 0:18–0:35 — What it is (the reusable pattern)

**On screen:** `rollback_gate/gate.py`, highlight the three questions and `judge()`.

**Caption / VO:**
> The pattern is one line: **the model classifies, the code decides.** A small local
> Strands Decider answers narrow questions — what's the root cause, was this already tried,
> is a dependency saturated. A plain-Python policy turns those into allow or block. The
> thresholds live in code, not in a prompt.

---

## 0:35–1:40 — The four scenes (`python demo.py --slow`)

Let the terminal play. Narrate lightly over each verdict.

- **0:35 Scene 1 — justified.** 5xx right after a deploy → **ALLOW**.
  > "Deploy, then errors. Rollback is the right call. The gate allows it."
- **0:52 Scene 2 — the wrong reflex.** Traffic 4× from a campaign → **BLOCK**.
  > "No deploy for three days — this is a traffic surge. Rolling back fixes nothing. Blocked,
  > and it tells you why: the cause is traffic, not a deploy."
- **1:10 Scene 3 — doing it again.** Already rolled back, still failing → **BLOCK**.
  > "It already rolled back and the errors persist. The gate won't let it repeat the same
  > move — look for another cause."
- **1:25 Scene 4 — the trap (hero shot).** DB at 100% connections, looks like a bad deploy
  → **BLOCK**.
  > "This one fools people. The database is saturated, but it reads like just another bad
  > deploy — the model even leans that way. A second question about the dependency catches
  > it: fix the database first. Rollback is blocked."

**On screen at 1:35:** freeze on Scene 4's reason line and the three scores
(`cause~bad_deploy 0.51 | repeat 0.31 | dep-saturated 0.76`).

## 1:40–2:00 — Scene 5: the limit across actions (temporal policy)

**On screen:** the two rollback attempts, same incident, seconds apart.

**Caption / VO:**
> One more. Every check so far judged a single action in isolation. But an agent that rolls
> back, waits, and rolls back again is thrashing — and no single-action check can see that.
> A temporal policy, the idea from AgentCore, remembers what already ran this session. The
> first rollback is allowed; the identical second one is blocked a few minutes later — not
> by the log, which is the same both times, but by a rule that spans actions. And it's
> blocked *before* the model is even asked.

**On screen:** `attempt 1 → ALLOW`, `attempt 2 → BLOCK "already ran 1 time in the last 15 min"`.

---

## 2:00–2:40 — The numbers (`python bench_compare.py`, or show bench_compare.json)

**On screen:** the comparison table.

| | DeciderGate (local) | Bedrock Haiku 4.5 |
|---|---|---|
| accuracy | 100% | 100% |
| latency median | ~141 ms | ~1091 ms |
| cost / 22 cases | $0 | ~$0.010 |

**Caption / VO:**
> Same incidents, judged two ways: our gate, and a general Bedrock LLM deciding
> directly. Same 100% accuracy — but the gate is about eight times faster and costs nothing
> per call, because the model runs locally and only answers small questions. At a million
> decisions a day that's roughly thirteen thousand dollars a month versus zero.

**Then the tuning story (the real point):**
> And it got to 100% the honest way. It missed a couple of cases — a saturated database, a
> feature flag it didn't connect to a deploy. We didn't reach for a bigger model. We named
> the missing pattern in one narrow question, added cases, and re-ran — on a *held-out* set
> it had never seen, which also scores 100%. And sweeping the threshold, every value from
> 0.35 to 0.50 scores 100%: it's a plateau, not a knife edge. That loop is the whole
> product: tune the gate in code, prove it on sets you keep separate.

**On screen:** `bench_compare_before.json` (90%) → `bench_compare.json` (100%); then
`python analysis.py sweep` showing the 0.35–0.50 plateau.

---

## 2:40–2:58 — Close (why it matters, where it goes)

**Caption / VO:**
> As agents get the keys to production, the scarce thing isn't a model that decides — it's
> a layer you can read, test, and trust that says *not yet, here's why*. DeciderGate is
> that layer: a reusable guardrail pattern, 84 unit tests, a golden set and a held-out set,
> a temporal policy, Apache-2.0.

**On screen:** repo URL + `#strands-decider-2b #guardrails`.

---

## Capture checklist
- [ ] `strands-decider serve ... --port 8099` running (health green)
- [ ] `python demo.py --slow` recorded end to end (5 scenes incl. the temporal one)
- [ ] (optional) `python agent.py` — the gate guiding a real Strands agent off a wrong rollback
- [ ] `python bench_compare.py` run live, or `bench_compare.json` shown
- [ ] before/after JSONs visible for the tuning beat (golden 90→100, held-out 93.8→100)
- [ ] no account IDs / ARNs / profile names on screen (mask terminal title & prompt)
- [ ] final cut < 3:00, English captions burned in, uploaded Public
