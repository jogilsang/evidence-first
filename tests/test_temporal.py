"""Temporal policy: a session-aware guard across actions (AgentCore-style). The clock is
injected so time windows are deterministic; the Decider is mocked where a gate is built."""
import pytest
from rollback_gate.temporal import ActionHistory, TemporalPolicy
from rollback_gate.gate import DeciderGate


class Clock:
    def __init__(self, t=1000.0):
        self.t = t
    def __call__(self):
        return self.t
    def tick(self, dt):
        self.t += dt


def ans(cause="bad_deploy", p=0.8, tried=0.1, dep=0.1):
    rest = (1 - p) / 3
    probs = {k: rest for k in ("bad_deploy", "traffic_surge", "dependency_failure", "unknown")}
    probs[cause] = p
    return {"cause": {"probabilities": probs},
            "already_tried": {"noul": tried}, "dep_saturated": {"noul": dep}}


class FakeDecider:
    def __init__(self, answers):
        self.answers = answers
    def ask(self, state, questions):
        return self.answers


# --- happy path -----------------------------------------------------------

def test_first_action_is_within_limits():
    h = ActionHistory(now=Clock())
    assert h.review("rollback", TemporalPolicy()).allow


def test_same_action_after_window_is_allowed_again():
    clk = Clock()
    h = ActionHistory(now=clk)
    h.record("rollback")
    clk.tick(1000)  # past the 900s window
    v = h.review("rollback", TemporalPolicy())
    assert v.allow and v.counts["same_action_in_window"] == 0


# --- edge cases -----------------------------------------------------------

def test_repeat_same_action_within_window_is_throttled():
    h = ActionHistory(now=Clock())
    h.record("rollback")
    v = h.review("rollback", TemporalPolicy(max_per_action=1))
    assert not v.allow and "already ran" in v.reason


def test_running_total_across_different_actions_is_capped():
    h = ActionHistory(now=Clock())
    h.record("rollback")
    h.record("scale_out")
    h.record("rollback")
    # a 4th remediation of any kind trips max_total=3
    v = h.review("scale_out", TemporalPolicy(max_per_action=99, max_total=3))
    assert not v.allow and "enough" in v.reason


def test_cumulative_cost_cap_blocks_when_impact_would_exceed():
    h = ActionHistory(now=Clock())
    h.record("scale_out", cost=4)   # 4 tasks
    h.record("scale_out", cost=4)   # 8 tasks so far
    pol = TemporalPolicy(max_per_action=99, max_total=99, max_cost=10)
    # another cost-4 action would reach 12 > cap 10 -> blocked on impact
    v = h.review("scale_out", pol, cost=4)
    assert not v.allow and "cumulative impact" in v.reason and v.counts["cost_in_window"] == 8


def test_cumulative_cost_under_cap_is_allowed():
    h = ActionHistory(now=Clock())
    h.record("scale_out", cost=3)
    pol = TemporalPolicy(max_per_action=99, max_total=99, max_cost=10)
    assert h.review("scale_out", pol, cost=3).allow  # 3+3=6 <= 10


# --- error handling / integration ----------------------------------------

def test_gate_without_temporal_policy_is_unchanged_and_records_nothing():
    # the additive guarantee: no history/policy -> behaves exactly as the base gate
    gate = DeciderGate(FakeDecider(ans("bad_deploy")))
    v = gate.review("deploy then 5xx", "rollback")
    assert v.allow and "temporal" not in v.scores


def test_gate_blocks_repeat_before_calling_the_model():
    clk = Clock()
    hist = ActionHistory(now=clk)
    # a decider that would ALLOW; the temporal guard must block the repeat before it's asked
    class Boom:
        def ask(self, *a):
            raise AssertionError("model should not be consulted on a temporal block")
    gate = DeciderGate(Boom(), history=hist, temporal_policy=TemporalPolicy(max_per_action=1))
    hist.record("rollback")
    v = gate.review("x", "rollback")
    assert not v.allow and "temporal" in v.scores


def test_gate_records_only_allowed_actions():
    hist = ActionHistory(now=Clock())
    gate = DeciderGate(FakeDecider(ans("traffic_surge")),  # cause!=rollback -> blocked
                       history=hist, temporal_policy=TemporalPolicy())
    v = gate.review("x", "rollback")
    assert not v.allow
    # a blocked action must not count toward the window
    assert hist.review("rollback", TemporalPolicy()).counts["total_in_window"] == 0
