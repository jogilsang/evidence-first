"""The advisor ranks actions via the Decider, then confirms with the gate. Decider mocked:
these test the shortlist-then-confirm logic, especially that a wrong top pick is caught."""
from rollback_gate.advisor import Advisor, ACTION_CRITERIA
from rollback_gate.gate import DeciderGate


def cause_probs(cause, p=0.8):
    rest = (1 - p) / 3
    d = {k: rest for k in ("bad_deploy", "traffic_surge", "dependency_failure", "unknown")}
    d[cause] = p
    return d


class ScriptedDecider:
    """Returns a ranking for the 'best' question and cause answers for gate reviews.

    `ranking` is {action: prob}; `cause_for` maps a gated action -> the cause answer the
    gate should see when it reviews that action (so we can force allow/block)."""
    def __init__(self, ranking, cause_for, dep=0.1, tried=0.1):
        self.ranking, self.cause_for, self.dep, self.tried = ranking, cause_for, dep, tried
        self.calls = 0

    def ask(self, state, questions):
        self.calls += 1
        if "best" in questions:
            return {"best": {"probabilities": self.ranking}}
        # a gate review: figure out which action is being reviewed from the state text
        action = "rollback" if "rollback" in state else "scale_out"
        return {"cause": {"probabilities": cause_probs(self.cause_for[action])},
                "already_tried": {"noul": self.tried},
                "dep_saturated": {"noul": self.dep}}


# --- happy path -----------------------------------------------------------

def test_recommends_top_action_when_gate_confirms():
    dec = ScriptedDecider(ranking={"rollback": 0.6, "wait": 0.2, "scale_out": 0.1, "restart": 0.1},
                          cause_for={"rollback": "bad_deploy", "scale_out": "traffic_surge"})
    r = Advisor(DeciderGate(dec)).recommend("deploy v42 then 5xx")
    assert r.decision == "act" and r.action == "rollback"


def test_falls_through_to_second_candidate_if_first_is_blocked():
    # model ranks rollback first, but the cause for rollback is traffic -> gate blocks it;
    # scale_out is next and its cause is traffic -> gate confirms it
    dec = ScriptedDecider(ranking={"rollback": 0.5, "scale_out": 0.4, "wait": 0.1},
                          cause_for={"rollback": "traffic_surge", "scale_out": "traffic_surge"})
    r = Advisor(DeciderGate(dec)).recommend("cpu 95% traffic 5x")
    assert r.decision == "act" and r.action == "scale_out"


# --- the key case: wrong top pick is caught -------------------------------

def test_escalates_when_top_pick_would_not_fix_the_cause():
    # saturated DB: model top-ranks scale_out, but dep guard blocks it -> escalate, not act
    dec = ScriptedDecider(ranking={"scale_out": 0.65, "restart": 0.2, "wait": 0.15},
                          cause_for={"scale_out": "traffic_surge", "rollback": "bad_deploy"},
                          dep=0.9)
    r = Advisor(DeciderGate(dec)).recommend("DB connections 100% pool exhausted")
    assert r.decision == "escalate" and r.action is None


# --- edge cases -----------------------------------------------------------

def test_advisory_only_actions_do_not_get_confirmed():
    # top picks are 'wait' and 'restart' (advisory-only); rollback is in the shortlist but
    # its cause doesn't match (traffic) so the gate blocks it -> nothing confirmed, escalate
    dec = ScriptedDecider(ranking={"wait": 0.5, "restart": 0.3, "rollback": 0.15, "scale_out": 0.05},
                          cause_for={"rollback": "traffic_surge", "scale_out": "traffic_surge"},
                          dep=0.1)
    r = Advisor(DeciderGate(dec)).recommend("unclear incident")
    assert r.decision == "escalate"


def test_ranking_is_returned_highest_first():
    dec = ScriptedDecider(ranking={"rollback": 0.6, "scale_out": 0.3, "wait": 0.1},
                          cause_for={"rollback": "bad_deploy", "scale_out": "traffic_surge"})
    r = Advisor(DeciderGate(dec)).recommend("x")
    probs = [p for _, p in r.ranking]
    assert probs == sorted(probs, reverse=True)


def test_action_criteria_cover_four_actions():
    assert set(ACTION_CRITERIA) == {"rollback", "scale_out", "restart", "wait"}
