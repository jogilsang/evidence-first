"""Three-way decision (allow/block/escalate) and the risk-aware bar. Pure judge() tests
over synthetic answers; no model. The defaults must leave the old two-way behaviour intact."""
from rollback_gate.gate import judge, Policy, Verdict, build_questions


def ans(cause="bad_deploy", p=0.5, tried=0.1, dep=0.1, risk=None):
    rest = (1 - p) / 3
    probs = {k: rest for k in ("bad_deploy", "traffic_surge", "dependency_failure", "unknown")}
    probs[cause] = p
    a = {"cause": {"probabilities": probs}, "already_tried": {"noul": tried},
         "dep_saturated": {"noul": dep}}
    if risk is not None:
        a["blast_radius"] = {"score": risk}
    return a


# --- back-compat: defaults keep the two-way behaviour -----------------------

def test_default_policy_never_escalates():
    # a borderline cause with the default (escalate_band=0) must hard-block, as before
    v = judge(ans(p=0.40), "rollback")
    assert v.decision == "block" and v.allow is False and v.escalated is False


def test_verdict_allow_boolean_still_works():
    assert judge(ans(p=0.8), "rollback").allow is True
    assert judge(ans(p=0.1), "rollback").allow is False


# --- escalate band ----------------------------------------------------------

def test_cause_just_under_bar_escalates_when_band_on():
    v = judge(ans(p=0.40), "rollback", Policy(escalate_band=0.15))  # 0.30 <= 0.40 < 0.45
    assert v.decision == "escalate" and v.escalated and not v.allow


def test_cause_well_under_bar_still_blocks_even_with_band():
    v = judge(ans(p=0.20), "rollback", Policy(escalate_band=0.15))  # below 0.45-0.15
    assert v.decision == "block"


def test_cause_above_bar_allows_regardless_of_band():
    assert judge(ans(p=0.80), "rollback", Policy(escalate_band=0.15)).allow


# --- risk-aware bar (blast radius score) ------------------------------------

def test_high_blast_radius_raises_the_bar_and_escalates():
    # cause 0.55 would normally allow (bar 0.45); high risk raises bar to 0.70 -> escalate
    v = judge(ans(p=0.55, risk=2.0), "rollback",
              Policy(escalate_band=0.20, high_risk_requires=0.70))
    assert v.decision == "escalate" and "blast radius" in v.reason


def test_low_blast_radius_keeps_default_bar():
    v = judge(ans(p=0.55, risk=0.2), "rollback", Policy(high_risk_requires=0.70))
    assert v.allow  # low risk -> bar stays 0.45, 0.55 passes


def test_blast_radius_recorded_in_scores_when_asked():
    v = judge(ans(p=0.8, risk=1.0), "rollback")
    assert v.scores.get("blast_radius") == 1.0


def test_risk_question_added_only_for_risk_aware_policy():
    assert "blast_radius" not in build_questions("rollback")
    assert "blast_radius" not in build_questions("rollback", Policy())
    assert "blast_radius" in build_questions("rollback", Policy(high_risk_requires=0.7))
