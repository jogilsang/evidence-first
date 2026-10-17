"""Scenario families for the independent evaluation set.

Labels are fixed BY CONSTRUCTION: each family states which kind of incident the generator must
write, and the expected verdict follows from the gate's published semantics (an action is
allowed only when the root cause is the one it fixes, it was not already tried, and no
dependency is saturated). The generator never labels anything; a second, different model
independently verifies each label and disagreements are quarantined, not silently dropped.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Family:
    id: str
    action: str          # "rollback" | "scale_out"
    allow: bool          # expected gate verdict
    brief: str           # what the generator must write (no conclusions in the text)


FAMILIES = [
    # --- rollback that should be ALLOWED: a change right before the symptoms
    Family("rb-deploy", "rollback", True,
           "a code deploy / new container image / build rollout finished a few minutes before errors began; "
           "traffic, CPU and dependencies look normal"),
    Family("rb-flag", "rollback", True,
           "a feature flag or configuration/environment-variable change was applied a few minutes before errors began; "
           "everything else (traffic, CPU, dependencies) looks normal"),
    Family("rb-migration", "rollback", True,
           "a release containing a library upgrade or a schema migration finished minutes earlier and tasks now crash or "
           "throw errors; infrastructure metrics look normal"),
    # --- rollback that should be BLOCKED
    Family("rb-surge", "rollback", False,
           "a traffic surge (campaign, live event, crawler) saturates CPU with a much higher request rate; the last deploy "
           "was two or more days ago; errors are mostly timeouts"),
    Family("rb-dependency", "rollback", False,
           "a downstream dependency is failing (database connection pool exhausted, cache unreachable, or a payment/auth "
           "API returning 503); the last deploy was two or more days ago"),
    Family("rb-unclear", "rollback", False,
           "latency or errors are elevated but the log shows no identifiable cause: no recent deploy, traffic normal, "
           "CPU and memory normal, dependencies not mentioned as failing"),
    Family("rb-already", "rollback", False,
           "a rollback was ALREADY performed earlier in this incident (state the time and version) and the errors persist "
           "unchanged afterwards"),
    Family("rb-bug-unrelated", "rollback", False,
           "an upstream partner or third-party API the service calls is returning errors or timing out, causing failures; "
           "no change was shipped for several days"),
    # --- scale_out that should be ALLOWED
    Family("so-surge", "scale_out", True,
           "a sudden legitimate traffic surge (sale, campaign, live event) saturates CPU or queues on all tasks; the last "
           "deploy was several days ago; dependencies are healthy; errors are only timeouts"),
    Family("so-peak", "scale_out", True,
           "daily peak-hours load: request rate several times normal, CPU high on every task, autoscaling already at its "
           "current ceiling, database and cache healthy, no recent deploy"),
    # --- scale_out that should be BLOCKED
    Family("so-deploy-bug", "scale_out", False,
           "errors started right after a deploy finished; CPU and request rate are normal, so there is no capacity problem"),
    Family("so-dependency", "scale_out", False,
           "a database/cache/downstream service is failing (pool exhausted, unreachable, 503) while CPU and request rate "
           "stay low"),
    Family("so-unclear", "scale_out", False,
           "elevated latency or errors with no identifiable cause; CPU, memory and request rate are all normal"),
    Family("so-already", "scale_out", False,
           "capacity was ALREADY increased earlier in this incident (state the time and the task counts) and the errors "
           "persist unchanged, with CPU now low"),
    Family("so-leak", "scale_out", False,
           "tasks are being restarted because of an application memory leak or bug; request rate is normal and CPU is low, "
           "so adding capacity addresses nothing"),
]

FAMILY_BY_ID = {f.id: f for f in FAMILIES}
