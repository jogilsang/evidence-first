# Independent evaluation (frozen policy)

The golden set and the held-out set in this repo were written by the same author and model family that built the
gate, so they cannot support an independence claim. This page reports a set that was **not** written by us and was
**not** used to tune anything.

## Protocol

- **Policy frozen** before generation: the default `Policy` and questions exactly as shipped in the initial public commit. Nothing was retuned after seeing these results. A later refactor (a `GateSpec` for other domains and a clearer weak-evidence message) was re-scored on all 115 cases and changed no verdict.
- **Generator:** Amazon Nova Pro (`us.amazon.nova-pro-v1:0`, non-Anthropic) wrote incident logs for 15 scenario families (`families.py`), 8 per family requested.
- **Labels by construction:** each family states the kind of incident to write, so the expected verdict follows from the gate's published semantics. The generator never labels.
- **Independent verifier:** Llama 3.3 70B (`us.meta.llama3-3-70b-instruct-v1:0`) labelled every log blind. Disagreements are **quarantined in `data/independent_removed.json` with a reason**, not silently dropped.
- **Counts:** 120 generated, 115 kept, 5 quarantined. Prompts and code: `generate.py`; every case records generator, verifier and date.
- **Human review:** 20 cases (15 random kept plus the 5 quarantined) were read by a human on 2026-10-18; all labels were judged correct. See the section below and `SPOT_CHECK.md`.

## Headline

| set | cases | who wrote it | gate accuracy |
|---|---|---|---|
| golden (used to tune) | 22 | the authors | 100.0% (tuned on it) |
| held-out | 20 | the authors, never tuned on | 100.0% |
| **independent (this page)** | 115 | **Nova Pro, verified by Llama** | **96.5%** |
| second domain: support refunds | 66 | Nova Pro, verified by Llama | 97.0% (no false allows) |

On data we did not write, the gate is **not** 100%: the honest headline is tuned 100% / independent 96.5%.

## Human review (2026-10-18)

A human read 15 random kept cases and all 5 quarantined cases. All 20 labels were judged correct, so on the 5 quarantined cases the **generator was right and the Llama verifier was wrong**.
Scoring the frozen gate on those 5 with the human-confirmed labels: 3/5 (ind-rb-dependency-3, ind-rb-dependency-4 were false allows, both `rb-dependency`).
Counting them in, all 120 generated cases give **114/120 = 95.0%**. The headline above stays on the 115 machine-verified cases because that was the pre-registered protocol; the quarantined cases were the hardest ones, so they are reported separately rather than folded in silently.

## Gate vs a general LLM judge on the same independent cases

| | DeciderGate (local Decider 2B) | Bedrock Haiku 4.5 |
|---|---|---|
| accuracy | 96.5% | 95.7% |
| false allow (action wrongly approved) | 4 | 0 |
| false block (justified action refused) | 0 | 5 |
| latency (median) | ~140 ms | ~1076 ms |
| API cost / 115 cases | $0 | ~$0.051 |

With n=115 the accuracy gap is within noise; the difference that matters is the **kind** of error. The gate's misses are false allows (the dangerous direction), while Haiku's misses are false blocks concentrated in a single family (`so-peak`, whose wording says autoscaling is already at its ceiling, which Haiku read as "scaling out is impossible").

## Per scenario family

| family | gate | Haiku |
|---|---|---|
| rb-already | 8/8 | 8/8 |
| rb-bug-unrelated | 8/8 | 8/8 |
| rb-dependency | 4/5 | 5/5 |
| rb-deploy | 8/8 | 8/8 |
| rb-flag | 8/8 | 8/8 |
| rb-migration | 8/8 | 8/8 |
| rb-surge | 6/8 | 8/8 |
| rb-unclear | 8/8 | 8/8 |
| so-already | 7/8 | 8/8 |
| so-dependency | 8/8 | 8/8 |
| so-deploy-bug | 8/8 | 8/8 |
| so-leak | 8/8 | 8/8 |
| so-peak | 8/8 | 3/8 |
| so-surge | 6/6 | 6/6 |
| so-unclear | 8/8 | 8/8 |

## Every gate error (nothing hidden)

- `ind-rb-surge-3` expected BLOCK, gate said ALLOW: Match-engine is reporting timeout errors and high CPU usage following a spike in traffic, possibly from increased multiplayer game activity after the last deployment two days ago.
- `ind-rb-surge-8` expected BLOCK, gate said ALLOW: ranker-api has seen a dramatic rise in CPU usage and timeout errors, with request rates tripling in the past hour. The last deployment was three days ago, prior to the start of the current traffic surge.
- `ind-rb-dependency-8` expected BLOCK, gate said ALLOW: Pricing-svc is unable to retrieve updated product prices, resulting in stale pricing data being served to customers. The external pricing API is returning 503 errors, and the last deploy occurred 48 hours ago.
- `ind-so-already-3` expected BLOCK, gate said ALLOW: 11:00 UTC: Profile-svc error rates stay constant at 18% following the increase of task counts from 20 to 40 at 10:30 UTC within the healthcare scheduling domain. CPU is now at 25%.

## Robustness to perturbations

Each perturbation keeps the facts and the label; only the surface changes (typos, shuffled sentences, five unrelated healthy log lines, Korean translation by Nova Pro).

| perturbation | gate accuracy | gate false allow / false block | Haiku 4.5 accuracy |
|---|---|---|---|
| none (original) | 96.5% | 4 / 0 | 95.7% |
| typos | 96.5% | 3 / 1 | 95.7% |
| reorder | 98.3% | 2 / 0 | 97.4% |
| noise | 90.4% | 3 / 8 | 96.5% |
| korean | 93.9% | 4 / 3 | 94.8% |

Reading it honestly:
- `noise`: gate 90.4% vs Haiku 96.5%; the Haiku judge holds up better (6.1 points).
- `korean`: gate 93.9% vs Haiku 94.8%; the Haiku judge holds up better (0.9 points).
- A small 2B classifier is more easily distracted by irrelevant log lines than a large general model, so noisy real-world logs are the main place to improve the gate (shorter evidence windows, line filtering before the question).

## Second domain: customer-support refunds

The same `DeciderGate`, with a different `GateSpec` (`rollback_gate/domains.py`), no change to `gate.py`: 66 cases, accuracy 97.0%, false allow 0, false block 2, median 159 ms. Quarantined: 0.

| family | result |
|---|---|
| gw-already | 6/6 |
| gw-defect | 6/6 |
| gw-late | 6/6 |
| gw-ontime | 6/6 |
| rf-already | 6/6 |
| rf-defect | 6/6 |
| rf-fraud | 6/6 |
| rf-late-only | 6/6 |
| rf-mind | 6/6 |
| rf-missing | 4/6 |
| rf-unclear | 6/6 |

- error `rf-rf-missing-2` expected ALLOW: Customer has not received the order ORD-78618, which tracking indicates was returned to the sender. They are now asking for a full reimbursement.

- error `rf-rf-missing-6` expected ALLOW: Order ORD-82535 is reported as undelivered by the customer. The tracking status suggests the package may have been returned to the sender. The customer is now asking for a reimbursement.

## Limits

- The cases are synthetic and machine-written; real incidents are messier. Expect to re-tune thresholds on your own data.
- One verifier model checked the labels; a human has not yet reviewed them (see `SPOT_CHECK.md`).
- Latency is from one Apple-silicon laptop (MLX). Haiku latency includes public-endpoint network time.
- Perturbations are a sample (one seed each), not an exhaustive robustness proof.
