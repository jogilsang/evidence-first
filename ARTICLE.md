# evidence-first: stop your AI agent from making an outage worse (96.5% on 115 cases it had never seen)

Tags: #strands-decider-2b #guardrails

It is 2 a.m. An alert fires, and the agent that holds your production keys does what agents do: it picks an action, confidently. Roll back a deploy that was never the problem. Scale out a service whose database is the real bottleneck. Repeat the fix that already did not work. Each one is a reasonable first instinct, and each one, acted on, makes the outage worse.

I built the colleague you would want sitting next to that agent: the one who, before anything gets touched, quietly asks "what is your evidence?" I called it evidence-first. In code it is a class called DeciderGate, built on the Strands Decider 2B. It is one idea you can lift into your own agent:

**The model classifies. The code decides.**

![Figure 1: concept](docs/article/fig1-concept.png)
*Figure 1. The agent proposes, the model classifies, the code decides.*

## At a glance

- **Code (Apache-2.0):** https://github.com/jogilsang/evidence-first (the repository is evidence-first; the guardrail inside it is the DeciderGate class)
- **What it is:** a reusable guardrail for Strands agents. A small local Strands Decider 2B answers three narrow typed questions about an incident, and plain Python policy turns the answers into allow, block or escalate, with a reason a human can read.
- **Does it work on data I did not write?** 96.5% on 115 incident logs written by Amazon Nova Pro and labelled blind by Llama 3.3 70B (not by me, and never used for tuning). Amazon Bedrock Claude Haiku 4.5, asked to judge the same cases in one call, scores 95.7%.
- **Speed and cost:** about 140 ms median against about 1,076 ms for the Haiku judge, and nothing billed per call because the Decider runs locally.
- **The part I want you to notice:** the gate's 4 misses are all false allows, the dangerous direction. I list every one of them below instead of hiding them.
- **Replay every number without any model:** open `evalkit/replay.ipynb` in the repo (it renders on GitHub). It recomputes the accuracy, the misses and the perturbation results from the saved per-case data in seconds, with no model and no AWS.
- **Try to fool it yourself:** `python play.py --examples` replays known misses, and `python play.py` with your own log lets you try your own. It needs the local Decider model running (no AWS calls).
- **Tests:** 84 unit tests with the model, Bedrock, Strands and OpenTelemetry mocked. No network.

## Where to look, by judging criterion

| Criterion | What to look at |
|---|---|
| Creativity and fun | The "calm colleague" framing, and the section "Can you fool the gate?" with real tricks that worked and failed |
| Use of Decider 2B | Three typed questions per decision, an agent hook at before_tool_call, a measured comparison with a Bedrock judge, and a second domain (support refunds) reusing the same gate with only a different GateSpec |
| Communication | The 2 min 48 s video, this article, and an honest "what this is not" section |
| Originality | Model classifies and code decides; probe the model first, then add a narrow question instead of reaching for a bigger model; a cross-action temporal policy and an audit trail, all opt-in |

## The pattern

A guardrail that an agent trusts has to be two things at once: smart enough to read a messy incident log, and boring enough that you can test it, read its reasoning, and tune it without retraining anything. Those pull in opposite directions, unless you split the job.

The Strands Decider 2B is a small decision model that runs locally and answers typed questions in roughly a tenth of a second. It does the reading. It never picks the action. It answers three narrow questions about the incident and the proposed fix:

- **cause**: what is the most likely root cause, from the log alone? (a choice)
- **already_tried**: was this same action, or an equivalent, already tried without help? (yes or no)
- **dep_saturated**: is a downstream dependency saturated or failing, regardless of any deploy? (yes or no)

![Figure 2: architecture](docs/article/fig2-architecture.png)
*Figure 2. DeciderGate sits at before_tool_call: the agent proposes an action, cross-action limits run first, the local Decider 2B answers three typed questions, and policy in code returns allow, block or escalate.*

Then plain Python decides. A Policy holds the thresholds. A pure judge function runs the guards in order of certainty: a repeat we have evidence of, then a dependency we can see is saturated, then whether the cause actually matches the action. It returns allow or block with a sentence you can read. For a proposed rollback on a traffic-surge incident, the reply looks like this:

> blocked: the log points to "traffic_surge", not "bad_deploy", so "rollback" is not supported by the evidence

![Figure 3: two verdicts from one gate](docs/article/fig3-two-verdicts.png)
*Figure 3. The same gate on two incidents, from the recorded demo. A rollback right after a bad deploy is allowed. A repeat rollback after the errors persisted is blocked, with a reason.*

The thresholds live in code, not buried in a prompt. The reasoning is a value you can log and assert on. The whole gate is unit-tested with the model mocked, 84 tests, no network, because the decision logic is just a function over the model's answers.

Two refinements fall out naturally once code owns the decision. The verdict is not only allow or block: a cause that lands just under the bar returns **escalate**, meaning hand it to a human rather than guess. And the bar itself can move with the stakes: the Decider also scores the blast radius of the action, and a change that could hit users or data broadly needs a stronger cause than restarting one task. Both are a few lines of policy, off by default, each covered by a test.

## Does it hold up on data I did not write?

A 100% on cases I wrote and tuned against proves little. So I froze the policy and let a different model family write the test. Amazon Nova Pro wrote 120 incident logs across 15 scenario families, with labels fixed by construction and never by the generator. Llama 3.3 70B labelled each one blind. The 5 cases where they disagreed are quarantined in the repo with a reason, not quietly removed.

Then I read 15 random kept cases and all 5 quarantined ones myself. All 20 labels were right, so in the 5 disagreements the generator was correct and the verifier was wrong. Scored separately, the frozen gate gets 3 of those 5; both misses are false allows on a dependency outage. Counting them in, the total is 114 of 120, or 95.0%. I report the 115-case number as the headline because that was the protocol I committed to before looking, and the quarantined cases were the hardest ones.

| | DeciderGate (local) | Bedrock Haiku 4.5 |
|---|---|---|
| independent set (115 cases) | **96.5%** | 95.7% |
| the errors | 4 false allows | 5 false blocks (all in one ambiguous family) |
| latency (median) | ~140 ms | ~1,076 ms |
| API cost for 115 cases | $0 | ~$0.051 |

So the real number is 96.5%, not 100%. With 115 cases the accuracy gap between the two is within noise. What matters is the kind of error. The gate's four misses are the dangerous kind, an action wrongly approved: two traffic surges with a deploy mentioned days earlier, one third-party 503 treated as a bad deploy, and one scale-out that had already been done. The Haiku judge's misses go the safe way, refusing a justified action. I did not retune the gate after seeing any of this.

The same gate also guards customer-support remedies (refund, goodwill credit) with a different GateSpec and no change to the gate itself: 66 independent cases, 97.0%, zero false allows. A blocker question about an abuse or fraud signal takes the place of "a dependency is saturated".

## Can you fool the gate?

I tried, systematically. I kept the facts and the label of every independent case and changed only the surface.

- **Typos:** 96.5%. Barely moves.
- **Shuffled sentences:** 98.3%. Does not matter.
- **Five unrelated healthy log lines added (the noise test):** the gate drops to **90.4%**, while the Haiku judge holds at 96.5%. A small classifier is easier to distract with irrelevant lines such as "cert renewal finished" or "disk usage 41%". The 11 noise errors split into 8 justified actions wrongly blocked and 3 false allows.
- **Korean translation:** 93.9% for the gate against 94.8% for Haiku.

![Figure 4: robustness](docs/article/fig4-robustness.png)
*Figure 4. Accuracy on the 115 independent cases when only the surface of each log changes. Typos and reordering barely matter; added noise is where the gate loses to the Haiku judge. The axis starts at 85%.*

That noise result is the clearest place to improve the gate, and I left it as it is on purpose, so the numbers above stay honest. Every case, including every error and every flip, is in the repo (`evalkit/RESULTS.md` and `docs/FOOL_THE_GATE.md`). The command `python play.py` lets you try your own log (it needs the local Decider).

## Getting to 100% on my own sets, the honest way

On my own small golden set, the first version of the gate scored 90%, not 100%. Two incidents slipped through:

- A database at 100% connections, with "connection pool exhausted" right there in the log, but the cause question leaned toward bad deploy, so a pointless rollback was allowed.
- A service that had already been scaled out and was still failing. The repeat check only knew about rollbacks, so a repeated scale-out walked straight past it.

The tempting move is to reach for a bigger model. I did not, and that is the point of the pattern. I probed the model first (read-only) on just those two cases and found it already knew the answers: asked directly, it scored the saturated database at 0.83 and the repeated scale-out at 0.62. The model was not the limit. The gate just had not asked.

So I added two narrow questions and two lines of policy, re-ran the golden set, and both misses were gone, with no regression on the cases that were already right. 90% to 100%, for about 30 ms and two extra questions, still far under the Bedrock judge and still nothing billed per call. The full before and after, with the probe numbers, is in the repo's `PATTERN_NOTES.md`.

That loop (probe, add a narrow question, add a line of policy, re-run the golden set) is the product, not the specific thresholds. Tuning a guardrail becomes a code change you can read and a test you can run, instead of a prompt you cross your fingers over.

The thresholds are not balanced on a knife edge either. Sweeping the main one across a range, every value from 0.35 to 0.50 scores 100% on the combined golden and held-out sets. The default sits in the middle of that plateau, with margin deliberately kept on the side that avoids a false allow.

## Why bother: speed and cost at agent scale

On the 22-case golden set both approaches were correct (100% each), but the gate took about 141 ms against about 1,091 ms for the Haiku judge, and cost nothing per call. A guardrail that sits in front of every risky action an agent takes needs to be both fast and cheap, or it gets turned off. Extrapolated by volume, the gap becomes a budget line:

| decisions per day | Bedrock judge per month | DeciderGate per month |
|---|---|---|
| 10,000 | ~$136 | $0 |
| 100,000 | ~$1,359 | $0 |
| 1,000,000 | ~$13,589 | $0 |

The Decider's cost is a one-off local GPU and electricity, not a per-call charge. These figures extrapolate the small measured set linearly and are an estimate, not a bill.

## Running it with a real agent

The gate sits in a Strands agent at before_tool_call. Amazon Bedrock (Claude Haiku 4.5) drives the agent, and the local Decider gates its tool calls. On the saturated-database incident, the agent reached for scale_out first in 5 of 5 recorded runs. The gate sent it back every time with a readable reason, and the agent then concluded the database was the real bottleneck. The transcripts are in `record/agent_runs/`. An LLM is not deterministic, so the video replays a saved run.

![Figure 5: agent run](docs/article/fig5-agent-run.png)
*Figure 5. Recorded run: the agent proposes scale_out, the gate blocks it because the database is saturated, and the agent concludes the database is the real bottleneck.*

## The decision that only exists across actions

Everything above judges one action in isolation: this incident, this proposed fix. But some of the worst agent behaviour is only visible across actions. An agent rolls back, sees no improvement, rolls back again. It scales out, waits a minute, scales out again. Each call looked at alone is defensible, and that is exactly why a single-action gate waves them all through.

So the gate has a second, opt-in layer modelled on Amazon Bedrock AgentCore temporal policies: rules that span actions within a session, such as limiting how many times an action runs in a window or keeping a running total under a threshold. A small in-memory ActionHistory remembers what actually ran, and a TemporalPolicy holds the window and the limits. The same justified rollback is allowed once and then blocked if it is attempted again minutes later. The incident log is identical both times; a rule about cadence is what stops it. Because it is just the agent's own recent history checked in code, it fires before the model is ever asked, so catching a thrash costs nothing.

![Figure 6: temporal policy](docs/article/fig6-temporal-policy.png)
*Figure 6. Same evidence twice. The first rollback is allowed; the second is blocked by a rule about cadence, not by the log.*

It is strictly additive. A gate built without a temporal policy behaves exactly as before, and a unit test pins that down.

## Leaving a trail

A gate you trust in production has to answer "why did it decide that?" three months later. So every decision can be written to an append-only audit log: the action, the verdict, the scores, the reason, and a hash of the policy that produced it, with the incident text hashed rather than stored so the trail carries no sensitive payload. Each decision can also be emitted as an OpenTelemetry span, which CloudWatch speaks natively, so a gate verdict shows up in the same trace as the rest of the agent's work. An idempotency cache returns the prior verdict for identical reviews in a tight loop without re-asking the model. All three are opt-in, and none of them change a verdict.

## What this is not

- Decider 2B is an experimental model, and this gate is a demo-scale pattern, not a production system.
- The golden set (22 cases) and the held-out set (20 cases) are small, synthetic and written by me. The 115-case independent set is machine-written and machine-verified; I read 20 of its cases (15 random kept plus the 5 quarantined) and found the labels right, but I did not review the other 100.
- Latency was measured on one Apple-silicon laptop (MLX). The Bedrock figure includes public-endpoint network variance and will differ for you.
- The gate is weaker than a general LLM judge on noisy logs (90.4% against 96.5%) and its misses are false allows. For high-stakes actions, keep the escalate path and a human in the loop.
- The gate decides whether the evidence supports an action. It does not execute the remediation; that stays with the agent and, for escalations, a human.

## Why this matters as agents get real power

We are handing agents the ability to act, not just answer. As that happens, the scarce thing stops being a model that can decide, because models decide fine. The scarce thing becomes a layer you can read, test and trust, that is willing to say "not yet, here is why", and that is cheap and fast enough to leave in front of every action.

evidence-first is a small, honest version of that layer: a reusable guardrail pattern, a local decision model doing the classifying, plain code doing the deciding, independent data keeping it honest, an opt-in temporal policy for the decisions that only exist across actions, and a benchmark showing what the split buys you. It is Apache-2.0 and built to be lifted into your own agent. Swap the questions, keep the shape.

The agent proposes. The gate asks for evidence. The code decides. That is the whole idea.

Repo: https://github.com/jogilsang/evidence-first
