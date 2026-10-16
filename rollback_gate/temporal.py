"""A session-aware temporal guard, modelled on Amazon Bedrock AgentCore temporal policies.

The DeciderGate elsewhere judges one action in isolation: it looks at this incident and
this proposed fix. But some wrong decisions are only visible *across* actions -- an agent
that rolls back, sees no improvement, and rolls back again; or one that thrashes a service
with repeated scale-outs in a few minutes. No single-action check can see that, because
each call looks locally reasonable.

AgentCore temporal policies solve exactly this: rules that span multiple actions within a
session -- "limit how many times an action runs within a time window" and "keep a running
total under a threshold". This is a small local stand-in for that idea, so the gate can
enforce the same kind of rule without a round trip: the agent's own recent history, in
memory, checked by code before the model is ever asked.

Design note: this is strictly *additive*. A DeciderGate with no TemporalPolicy behaves
exactly as before -- same questions, same verdicts. The temporal check only exists when you
opt in by passing one, and even then it runs before the model, so a rule it does not fire
on changes nothing.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field


@dataclass
class ActionRecord:
    action: str
    at: float   # epoch seconds
    cost: float = 1.0  # impact weight of this action (e.g. tasks restarted); 1.0 = one action


@dataclass
class TemporalPolicy:
    """Session-aware limits over recent actions. Thresholds owned by code, like Policy.

    window_seconds   the look-back window the limits apply over.
    max_per_action   most times one action may run within the window (rate limit).
    max_total        most gated actions of any kind within the window (running total count).
    max_cost         most cumulative impact (sum of action costs) within the window
                     (AgentCore's "keep a running total under a threshold"). 0/None = off.
    0 or None disables a limit.
    """
    window_seconds: float = 900.0   # 15 minutes
    max_per_action: int = 1         # the same action at most once per window
    max_total: int = 3             # at most 3 remediations of any kind per window
    max_cost: float = 0.0          # cumulative impact cap per window (0 = disabled)


@dataclass
class TemporalVerdict:
    allow: bool
    reason: str
    counts: dict = field(default_factory=dict)


class ActionHistory:
    """Remembers recently *executed* actions for one session. In-memory on purpose: a demo
    stand-in for what AgentCore keeps per session. Swap for a durable store in production."""

    def __init__(self, now=time.time):
        self._now = now
        self._records: list[ActionRecord] = []

    def record(self, action: str, cost: float = 1.0) -> None:
        """Call this only when an action actually ran (allowed by the gate). `cost` is the
        action's impact weight; defaults to 1.0 so count-only policies are unaffected."""
        self._records.append(ActionRecord(action, self._now(), cost))

    def _within(self, window_seconds: float) -> list[ActionRecord]:
        if not window_seconds:
            return list(self._records)
        cutoff = self._now() - window_seconds
        return [r for r in self._records if r.at >= cutoff]

    def review(self, action: str, policy: TemporalPolicy, cost: float = 1.0) -> TemporalVerdict:
        """Would running `action` (with impact `cost`) now break a temporal limit? Pure
        read; records nothing."""
        recent = self._within(policy.window_seconds)
        same = sum(1 for r in recent if r.action == action)
        total = len(recent)
        spent = sum(r.cost for r in recent)
        counts = {"same_action_in_window": same, "total_in_window": total,
                  "cost_in_window": round(spent, 3), "window_seconds": policy.window_seconds}
        mins = int(policy.window_seconds // 60)
        if policy.max_per_action and same >= policy.max_per_action:
            return TemporalVerdict(False,
                f"'{action}' already ran {same} time(s) in the last {mins} min; "
                "repeating it so soon is throttled -- let the first one take effect or "
                "escalate instead of acting again", counts)
        if policy.max_total and total >= policy.max_total:
            return TemporalVerdict(False,
                f"{total} remediations already ran in the last {mins} min; that is enough "
                "churn -- stop and escalate rather than keep changing things", counts)
        if policy.max_cost and spent + cost > policy.max_cost:
            return TemporalVerdict(False,
                f"cumulative impact in the last {mins} min would reach {spent + cost:g} "
                f"(cap {policy.max_cost:g}); hold off and escalate rather than add more", counts)
        return TemporalVerdict(True, "within temporal limits", counts)
