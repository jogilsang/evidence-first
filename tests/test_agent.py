"""The Strands intervention maps gate verdicts to Guide/Proceed. The gate (and so the
Decider) is mocked: these test the before_tool_call wiring, not the live model or Bedrock."""
import pytest
from strands.interventions import Guide, Proceed

from agent import RemediationReviewer, GATED_TOOLS


class FakeVerdict:
    def __init__(self, allow, reason, cause="bad_deploy"):
        self.allow, self.reason = allow, reason
        self.scores = {"cause_probs": {cause: 0.8, "traffic_surge": 0.07,
                                       "dependency_failure": 0.07, "unknown": 0.06},
                       "already_tried": 0.1, "dep_saturated": 0.1}


class FakeGate:
    def __init__(self, verdict):
        self._verdict, self.seen = verdict, None

    def review(self, log, action, args):
        self.seen = (log, action, args)
        return self._verdict

    # the reviewer prints decider.calls via gate.decider; not needed here


class FakeEvent:
    """Mimics the Strands before_tool_call event shape."""
    def __init__(self, tool_name, args, messages):
        self.tool_use = {"name": tool_name, "input": args}
        self.agent = type("A", (), {"messages": messages})()


MSGS = [{"role": "user", "content": [{"text": "5xx after deploy v42"}]}]


# --- happy path -----------------------------------------------------------

def test_allowed_action_returns_proceed():
    r = RemediationReviewer(FakeGate(FakeVerdict(True, "evidence supports 'rollback'")))
    action = r.before_tool_call(FakeEvent("rollback", {"to": "v41"}, MSGS))
    assert isinstance(action, Proceed)
    assert r.log[-1]["allow"] is True


def test_blocked_action_returns_guide_with_reason_in_feedback():
    r = RemediationReviewer(FakeGate(FakeVerdict(False, "the log points to 'traffic_surge'")))
    action = r.before_tool_call(FakeEvent("rollback", {"to": "v41"}, MSGS))
    assert isinstance(action, Guide)
    assert "traffic_surge" in action.feedback and "rollback" in action.feedback


# --- edge cases -----------------------------------------------------------

def test_ungated_tool_is_not_reviewed():
    gate = FakeGate(FakeVerdict(False, "should not be consulted"))
    r = RemediationReviewer(gate)
    action = r.before_tool_call(FakeEvent("get_logs", {}, MSGS))
    assert isinstance(action, Proceed)
    assert gate.seen is None and r.log == []  # gate never called, nothing logged


def test_incident_text_and_action_reach_the_gate():
    gate = FakeGate(FakeVerdict(True, "ok"))
    RemediationReviewer(gate).before_tool_call(FakeEvent("scale_out", {"to_tasks": 8}, MSGS))
    log, action, args = gate.seen
    assert "5xx after deploy" in log and action == "scale_out" and args == {"to_tasks": 8}


def test_gated_tools_map_tool_name_to_gate_action():
    assert GATED_TOOLS == {"rollback": "rollback", "scale_out": "scale_out"}


# --- error handling -------------------------------------------------------

def test_gate_error_propagates_not_swallowed():
    class Boom:
        def review(self, *a):
            raise RuntimeError("decider down")
    with pytest.raises(RuntimeError):
        RemediationReviewer(Boom()).before_tool_call(FakeEvent("rollback", {}, MSGS))
