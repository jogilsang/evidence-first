import pytest

from rollback_gate.domains import REFUND_SPEC
from rollback_gate.gate import DeciderGate, OPS_SPEC, Policy, build_questions, judge


def ans(cause="merchant_fault", p=0.8, tried=0.1, blocker=0.1, key="fraud_signal"):
    others = [c for c in REFUND_SPEC.causes if c != cause]
    probs = {cause: p, **{o: (1 - p) / len(others) for o in others}}
    return {"cause": {"probabilities": probs}, "already_tried": {"noul": tried}, key: {"noul": blocker}}


def test_refund_allowed_for_merchant_fault():
    assert judge(ans("merchant_fault"), "refund", spec=REFUND_SPEC).allow


def test_goodwill_credit_needs_service_delay():
    assert judge(ans("service_delay"), "goodwill_credit", spec=REFUND_SPEC).allow
    v = judge(ans("service_delay"), "refund", spec=REFUND_SPEC)
    assert not v.allow and "service_delay" in v.reason


def test_fraud_signal_blocks_even_with_strong_cause_and_says_why():
    v = judge(ans("merchant_fault", blocker=0.9), "refund", spec=REFUND_SPEC)
    assert not v.allow and "fraud" in v.reason and "human reviewer" in v.reason


def test_repeat_remedy_is_blocked():
    v = judge(ans("merchant_fault", tried=0.9), "refund", spec=REFUND_SPEC)
    assert not v.allow and "already received a remedy" in v.reason


def test_unknown_action_is_not_gated():
    assert judge(ans("changed_mind"), "send_email", spec=REFUND_SPEC).allow


def test_default_spec_is_ops_and_unchanged():
    q = build_questions("rollback")
    assert set(q) == {"cause", "dep_saturated", "already_tried"}
    q2 = build_questions("refund", None, REFUND_SPEC)
    assert set(q2) == {"cause", "fraud_signal", "already_tried"}
    assert "refund" in q2["already_tried"]["instructions"]


def test_weak_but_leading_cause_reports_weakness_not_a_contradiction():
    # the right cause leads but is under the bar: the message must not say "points to X, not X"
    a = ans("merchant_fault", p=0.40)
    v = judge(a, "refund", Policy(min_cause_prob=0.45), REFUND_SPEC)
    assert not v.allow and "too weak" in v.reason and "not 'merchant_fault'" not in v.reason


class FakeDecider:
    def __init__(self, answers):
        self.answers, self.seen = answers, None

    def ask(self, state, questions):
        self.seen = questions
        return self.answers


def test_gate_with_spec_asks_the_domain_questions():
    d = FakeDecider(ans("merchant_fault"))
    v = DeciderGate(d, spec=REFUND_SPEC).review("item arrived broken", "refund")
    assert v.allow and set(d.seen) == {"cause", "fraud_signal", "already_tried"}


def test_gate_default_spec_is_ops():
    assert DeciderGate(FakeDecider({})).spec is OPS_SPEC
