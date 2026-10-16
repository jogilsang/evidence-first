# The calm colleague: a reusable guardrail that reviews an agent's action before it runs

> Article for AWS Builder Center · Agent Experience Hackathon: Strands Decider
> Tags: `#strands-decider-2b` `#guardrails`

---

The scary thing about giving an AI agent the keys to production isn't that it can't make a
decision. It's that it makes one **confidently**, and wrong, in the second after an alert
fires. Roll back a deploy that was never the problem. Scale out a service whose database is
the real bottleneck. Repeat the fix that already didn't work. Each of those is a reasonable
first instinct — and each one, acted on, is an outage made worse.

So I built the colleague you'd want sitting next to that agent: the one who, before you
touch anything, quietly asks *"what's your evidence?"* I called it **DeciderGate**, and the
whole thing is one idea you can lift into your own agent:

> **The model classifies. The code decides.**

## The pattern

A guardrail that an agent trusts has to be two things at once: smart enough to read a messy
incident log, and boring enough that you can test it, read its reasoning, and tune it
without retraining anything. Those pull in opposite directions — unless you split the job.

The [Strands Decider 2B](https://github.com/strands-labs/strands-decider) — a small decision model that runs
locally and answers typed questions in roughly a tenth of a second — does the reading. It
never picks the action. It answers three narrow questions about the incident and the
proposed fix:

- **cause** — what's the most likely root cause, from the log alone? (a choice)
- **already_tried** — was this same action, or an equivalent, already tried and it didn't
  help? (yes/no)
- **dep_saturated** — is a downstream dependency saturated or failing, regardless of any
  deploy? (yes/no)

Then plain Python decides. A `Policy` holds the thresholds; a pure `judge()` function runs
the guards in order of certainty — a repeat we have evidence of, then a dependency we can
see is saturated, then whether the cause actually matches the action — and returns `allow`
or `block` with a sentence you can read:

```python
verdict = gate.review(incident_log, "rollback", {"to": "v41"})
# blocked: "the log points to 'traffic_surge', not 'bad_deploy',
#           so 'rollback' is not supported by the evidence"
```

The thresholds live in code, not buried in a prompt. The reasoning is a value you can log
and assert on. The whole gate is unit-tested with the model mocked — 59 tests, no network —
because the decision logic is just a function over the model's answers.

Two refinements fall out naturally once code owns the decision. The verdict isn't only
*allow* or *block*: a cause that lands just under the bar returns **escalate** — hand it to
a human rather than guess — which is the honest answer when the evidence is genuinely
borderline. And the bar itself can move with the stakes: the Decider also *scores* the
action's blast radius, and a change that could hit users or data broadly needs a stronger
cause than restarting one task. Both are a few lines of policy, off by default, each a test.

## Does it actually work? Measure it against the obvious alternative

The obvious alternative is to skip the split entirely: hand the whole incident to a capable
general LLM and let it return allow/block directly. So I measured both on the same labelled
incidents — the gate (local Decider) against Amazon Bedrock's Claude Haiku 4.5 deciding in
one call.

| | DeciderGate (local) | Bedrock Haiku 4.5 |
|---|---|---|
| accuracy | 100% | 100% |
| latency (median) | ~141 ms | ~1091 ms |
| API cost / 22 cases | $0 | ~$0.010 |

Same correctness. About eight times faster. Nothing billed per call, because the Decider
runs locally and only answers small questions. For a guardrail that sits in front of
*every* risky action an agent takes, that latency and that per-call cost are the difference
between "always on" and "too expensive to leave on." Extrapolated by volume, the gap is a
budget line, not a rounding error:

| decisions/day | Bedrock judge / month | DeciderGate / month |
|---|---|---|
| 10,000 | ~$136 | $0 |
| 100,000 | ~$1,359 | $0 |
| 1,000,000 | ~$13,589 | $0 |

(The Decider's cost is a one-off local GPU and electricity, not a per-call charge.)

## The part I'm proudest of: getting to 100% the honest way

The first version of the gate scored 90%, not 100%. Two incidents slipped through:

- A database at 100% connections — "connection pool exhausted" right there in the log — but
  the cause question leaned toward *bad deploy*, so a pointless rollback was allowed.
- A service that had **already** been scaled out and was still failing; the repeat check
  only knew about rollbacks, so a repeated scale-out walked straight past it.

Here's the tempting move: reach for a bigger model. I didn't — and that's the whole point
of the pattern. I **probed the model first** (read-only) on just those two cases and found
it already knew the answers: asked directly, it scored the saturated database at 0.83 and
the repeated scale-out at 0.62. The model wasn't the limit. The gate just hadn't asked.

So I added two narrow questions and two lines of policy, re-ran the golden set, and both
misses were gone — with no regression on the cases that were already right. 90% → 100%, for
the cost of about 30ms and two extra questions, still eight times under the Bedrock judge
and still $0 per call. The full before→after, with the probe numbers, is in the repo's
`PATTERN_NOTES.md`.

That loop — *probe, add a narrow question, add a line of policy, re-run the golden set* —
is the product. Not the specific thresholds. The fact that tuning a guardrail is a code
change you can read and a test you can run, instead of a prompt you cross your fingers over.

And the thresholds aren't balanced on a knife edge. Sweeping the main one across a range,
every value from 0.35 to 0.50 scores 100% on the combined set — the default sits in the
middle of that plateau, not on a spike. The number isn't fit to the data; it's a stable
operating region, with margin deliberately kept on the side that avoids a false *allow*.

## The decision that only exists across actions

Everything above judges one action in isolation: this incident, this proposed fix. But some
of the worst agent behaviour is only visible *across* actions. An agent rolls back, sees no
improvement, rolls back again. It scales out, waits a minute, scales out again. Each call,
looked at alone, is defensible — and that is exactly why a single-action gate waves them
all through.

So the gate has a second, opt-in layer modelled on **Amazon Bedrock AgentCore temporal
policies** — rules that span actions within a session: *limit how many times an action runs
in a window*, *keep a running total under a threshold*. A small in-memory `ActionHistory`
remembers what actually ran; a `TemporalPolicy` holds the window and the limits. The same
justified rollback is allowed once and then **blocked** if it's attempted again minutes
later — not by the incident log, which is identical both times, but by a rule about
cadence. And because it's just the agent's own recent history checked in code, it fires
*before* the model is ever asked: a thrash costs nothing to catch.

It's strictly additive. A gate built without a temporal policy behaves exactly as before —
there's a unit test that pins that down — so the cross-action guard is something you opt
into, not a tax on every call.

## Leaving a trail

A gate you trust in production has to answer "why did it decide that?" three months later.
So every decision can be written to an append-only audit log — the action, the verdict, the
scores, the reason, and a hash of the policy that produced it — with the incident text
hashed, not stored, so the trail carries no sensitive payload. Each decision can also be
emitted as an OpenTelemetry span, which is the format CloudWatch speaks natively and a CNCF
standard, so a gate verdict shows up in the same trace as the rest of the agent's work. And
because identical reviews in a tight loop are common, an idempotency cache returns the prior
verdict without re-asking the model — cheaper, and it stops the agent re-executing the same
thing. All three are opt-in; none of them change a verdict.

## What this is not

- Decider 2B is an experimental model, and this gate is a demo-scale pattern, not a production system.
- The golden set (22 cases) and held-out set (20 cases) are small, synthetic and written by me. "Held-out" here means *never tuned on*, not *independent*. On your own incidents, expect to re-tune the thresholds, and re-run the sweep to check you are still on a plateau.
- Latency was measured on one Apple-silicon laptop (MLX); the Bedrock figure includes public-endpoint network variance and will differ for you.
- The gate decides whether the evidence supports an action. It does not execute the remediation; that stays with the agent and, for escalations, a human.

## Why this matters as agents get real power

We're handing agents the ability to act, not just answer. As that happens, the scarce thing
stops being a model that can decide — models decide fine. The scarce thing becomes a layer
you can **read, test, and trust** that is willing to say *"not yet — here's why,"* and that
is cheap and fast enough to leave in front of every action.

DeciderGate is a small, honest version of that layer: a reusable guardrail pattern, a local
decision model doing the classifying, plain code doing the deciding, a golden set and a
held-out set keeping it honest, an opt-in temporal policy for the decisions that only exist
across actions, and a benchmark showing what the split buys you. It's Apache-2.0 and built
to be lifted into your own agent — swap the questions, keep the shape.

The agent proposes. The gate asks for evidence. The code decides. That's the whole idea.

---

_Repo: https://github.com/jogilsang/evidence-first · `#strands-decider-2b #guardrails`_
