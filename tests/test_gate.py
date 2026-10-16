import pytest
from rollback_gate.client import ServerUnavailable
from rollback_gate.gate import DeciderGate, judge, Policy, build_questions
from rollback_gate.golden import cases


def ans(cause="bad_deploy", p=0.8, tried=0.1, dep=0.1):
    rest = (1 - p) / 3
    probs = {k: rest for k in ("bad_deploy", "traffic_surge", "dependency_failure", "unknown")}
    probs[cause] = p
    return {"cause": {"probabilities": probs},
            "already_tried": {"noul": tried},
            "dep_saturated": {"noul": dep}}


def test_rollback_allowed_when_deploy_is_cause():
    assert judge(ans("bad_deploy"), "rollback").allow


def test_scale_out_allowed_when_traffic_is_cause():
    assert judge(ans("traffic_surge"), "scale_out").allow


def test_rollback_blocked_when_cause_is_traffic():
    v = judge(ans("traffic_surge"), "rollback")
    assert not v.allow and "traffic_surge" in v.reason


def test_repeat_blocked_even_if_cause_matches():
    v = judge(ans("bad_deploy", tried=0.9), "rollback")
    assert not v.allow and "already tried" in v.reason


def test_scale_out_repeat_blocked_too():
    # the widened repeat guard must also catch a repeated scale_out, not just rollback
    v = judge(ans("traffic_surge", tried=0.8), "scale_out")
    assert not v.allow and "already tried" in v.reason


def test_dependency_saturation_blocks_even_if_cause_looks_like_deploy():
    # the misclassification guard: cause says bad_deploy but a dependency is clearly saturated
    v = judge(ans("bad_deploy", p=0.8, dep=0.85), "rollback")
    assert not v.allow and "dependency" in v.reason


def test_ungated_action_passes():
    assert judge(ans("unknown"), "restart_task").allow


def test_threshold_is_owned_by_policy():
    a = ans("bad_deploy", p=0.5)
    assert judge(a, "rollback", Policy(min_cause_prob=0.45)).allow
    assert not judge(a, "rollback", Policy(min_cause_prob=0.6)).allow


def test_judge_still_reads_legacy_already_acted_key():
    # back-compat: older answer dicts used 'already_acted'
    legacy = ans("bad_deploy")
    legacy["already_acted"] = legacy.pop("already_tried")
    assert judge(legacy, "rollback").allow
    legacy["already_acted"] = {"noul": 0.9}
    assert not judge(legacy, "rollback").allow


class FakeDecider:
    def __init__(self, answers=None, exc=None):
        self.answers, self.exc, self.seen = answers, exc, None

    def ask(self, state, questions):
        if self.exc:
            raise self.exc
        self.seen = (state, questions)
        return self.answers


def test_gate_sends_log_and_action_and_returns_verdict():
    d = FakeDecider(ans("bad_deploy"))
    v = DeciderGate(d).review("deploy then 5xx", "rollback", {"to": "v41"})
    assert v.allow
    assert "deploy then 5xx" in d.seen[0] and "rollback" in d.seen[0]
    assert set(d.seen[1]) == {"cause", "dep_saturated", "already_tried"}


def test_build_questions_includes_action_specific_repeat_guard():
    q = build_questions("scale_out")
    assert set(q) == {"cause", "dep_saturated", "already_tried"}
    assert "scale_out" in q["already_tried"]["instructions"]


def test_gate_propagates_server_down():
    with pytest.raises(ServerUnavailable):
        DeciderGate(FakeDecider(exc=ServerUnavailable("down"))).review("x", "rollback")


def test_golden_set_has_both_labels_per_action_and_unique_ids():
    cs = cases()
    assert len({c["id"] for c in cs}) == len(cs)
    for action in ("rollback", "scale_out"):
        labels = {c["allow"] for c in cs if c["action"] == action}
        assert labels == {True, False}
