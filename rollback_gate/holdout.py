"""Held-out validation set: NEW incidents the policy was never tuned on.

Why this file exists: golden.py was used to *design* the questions and *set* the Policy
thresholds. Measuring the gate on the same set it was tuned against overstates how good it
is. These cases were written afterwards, with different wording and situations, and the
Policy is frozen before they are scored. If accuracy holds here, the gate generalises; if
it drops, the thresholds were overfit.

Rules kept deliberately different from golden.py so this is a real test, not a paraphrase:
different service names, different numbers, and causes phrased in new ways (feature flag
vs image deploy, cache stampede vs pool exhaustion, cron-driven surge vs campaign).
"""
from __future__ import annotations

CASES = [
    # --- rollback that SHOULD be allowed (a change right before the symptoms) -----------
    ("hv-rb-ok-1", "rollback", True,
     "Service checkout-svc. 03:11 released image build 2026.287. 03:12 error rate 52%, "
     "every task throwing NullPointerException on startup. Prior build ran clean for 9 days. "
     "Traffic flat, DB healthy."),
    ("hv-rb-ok-2", "rollback", True,
     "Service search-api. 18:40 enabled feature flag ranking_v3 for 100% of users. 18:41 "
     "latency p99 8s, timeouts 44%. CPU 50%, no infra change, downstreams green."),
    ("hv-rb-ok-3", "rollback", True,
     "Service billing-worker. 12:00 deployed migration 0142. 12:01 jobs failing with "
     "'column not found'. Previous revision stable all week. Queue filling, DB otherwise fine."),

    # --- rollback that should be BLOCKED (cause is not a bad change) ---------------------
    ("hv-rb-no-1", "rollback", False,  # traffic, not a deploy
     "Service checkout-svc. No deploy in 6 days. 20:00 flash sale: requests 7x baseline, "
     "CPU 96% across all tasks, p99 5s, errors are pure timeouts, 5xx from app code 0.1%."),
    ("hv-rb-no-2", "rollback", False,  # dependency saturation masquerading as a deploy fault
     "Service search-api. Deploy was 4 days ago. 09:30 errors 36%. Elasticache evictions "
     "spiking, cache hit rate fell 95%->20% (cache stampede), DB read load tripled, "
     "'pool timeout' in logs."),
    ("hv-rb-no-3", "rollback", False,  # downstream failing
     "Service orders-api. Last release 8 days ago. 02:00 5xx 48%. Payment provider returning "
     "503s, circuit breaker open to payments. Our CPU 30%, our DB fine."),
    ("hv-rb-no-4", "rollback", False,  # unclear, no change
     "Service profile-svc. No deploy for 11 days. 16:00 p99 crept to 3.5s. No errors, "
     "CPU 45%, memory 55%, traffic normal. Cause not obvious from the log."),
    ("hv-rb-no-5", "rollback", False,  # already rolled back, still failing
     "Service billing-worker. 12:20 rolled back to revision 0141. 12:35 jobs still failing "
     "at 30%, now with 'deadlock detected'. DB locks climbing."),

    # --- scale_out that SHOULD be allowed (resource saturation from load) ---------------
    ("hv-so-ok-1", "scale_out", True,
     "Service checkout-svc. No deploy in 6 days. 20:00 flash sale, requests 7x baseline, "
     "CPU 96% on all tasks, memory fine, DB fine, errors only timeouts under load."),
    ("hv-so-ok-2", "scale_out", True,
     "Service media-api. Last deploy 5 days ago. 21:30 a cron fan-out kicked off, request "
     "rate 5x, CPU 93%, queue depth climbing steadily, downstreams healthy."),
    ("hv-so-ok-3", "scale_out", True,
     "Service feed-svc. Deploy 2 days ago. 08:00 commute peak, traffic 3.5x, CPU 90% every "
     "task, memory 60%, DB connections 40%, no app errors besides a few timeouts."),

    # --- scale_out that should be BLOCKED -----------------------------------------------
    ("hv-so-no-1", "scale_out", False,  # a bad deploy, not load
     "Service checkout-svc. 03:11 image build 2026.287 released. 03:12 50% startup crashes. "
     "CPU 25%, request rate normal."),
    ("hv-so-no-2", "scale_out", False,  # dependency saturated, adding tasks won't help
     "Service search-api. Deploy 4 days ago. 09:30 errors 36%. Cache stampede, DB read load "
     "tripled, 'pool timeout'. CPU 35%, traffic normal."),
    ("hv-so-no-3", "scale_out", False,  # downstream failing
     "Service orders-api. Release 8 days ago. 02:00 5xx 48%. Payment provider 503s, breaker "
     "open. CPU 28%, request rate flat."),
    ("hv-so-no-4", "scale_out", False,  # already scaled, still failing
     "Service media-api. 21:40 scaled 6->12 tasks. 21:55 CPU now 30% but errors still 26%, "
     "downstream transcoder returning 500s."),
    ("hv-so-no-5", "scale_out", False,  # unclear, resources not the bottleneck
     "Service profile-svc. No deploy 11 days. 16:00 p99 3.5s. CPU 45%, memory 55%, traffic "
     "normal, no errors. Cause unclear."),

    # --- second pass: added after the first held-out run, to re-validate the flag fix and
    #     keep a never-seen set. Different scenarios again (canary, kernel param, GC pause).
    ("hv2-rb-ok-1", "rollback", True,  # a canary/rollout change right before symptoms
     "Service gateway. 11:20 canary promoted config set routing_v2 to 100%. 11:21 503s at "
     "41%, upstream selection errors. Prior config stable 3 weeks. Traffic flat, deps healthy."),
    ("hv2-rb-no-1", "rollback", False,  # dependency failure, not the (old) deploy
     "Service gateway. Deploy 9 days ago. 04:00 503s 33%. Downstream auth service p99 at 12s "
     "and shedding, our CPU 30%, our DB fine, request rate normal."),
    ("hv2-so-ok-1", "scale_out", True,  # genuine load surge, no change
     "Service ingest. No deploy 7 days. 19:00 product launch, requests 9x baseline, CPU 97% "
     "on every task, queue depth climbing, memory fine, downstreams fine, errors are timeouts."),
    ("hv2-so-no-1", "scale_out", False,  # already scaled and still failing (repeat)
     "Service ingest. 19:30 scaled 8->16 tasks. 19:50 CPU 35% now but errors still 24%, "
     "downstream feature store returning 500s."),
]


def cases():
    return [dict(id=i, action=a, allow=ok, log=l) for i, a, ok, l in CASES]
