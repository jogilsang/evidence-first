"""Reusable Decider 2B guardrail pattern: classify with the model, decide with code.

The model answers narrow typed questions about (incident log + proposed action). It never
picks the action. A plain-Python policy turns those numbers into allow / block, so the
thresholds stay owned by the code and are easy to tune against a golden set.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .client import Decider

CAUSES = {
    "bad_deploy": "a deployment or config change shortly before the problem began "
                  "(including a new build/image or a feature flag or rollout turned on)",
    "traffic_surge": "request volume is far above normal and resources are saturated",
    "dependency_failure": "a downstream dependency such as the database or cache is failing",
    "unknown": "the log does not show a clear cause",
}

# The model answers these narrow questions about the state; it never picks the action.
# Each question was added to catch a specific failure the golden set exposed:
#   cause          core: is the root cause the one this action fixes?
#   already_tried  repeat guard: was this same action (or an equivalent) already tried
#                  and it didn't help? -- widened from "rollback or similar" so it covers
#                  scale_out repeats too.
#   dep_saturated  misclassification guard: a saturated/failing dependency can look like a
#                  bad deploy to the cause question; this asks about it directly.
def _already_tried_q(action: str) -> dict:
    return Decider.noul(
        f"Has this same action ('{action}') or an equivalent one already been tried in "
        "this incident without fixing it?",
        {"true": f"'{action}' (or an equivalent) was already applied and the problem persists",
         "false": f"'{action}' has not been tried yet in this incident"},
    )


DEP_SATURATED_Q = Decider.noul(
    "Does the log show a downstream dependency (database, cache, or another service) "
    "saturated or failing, regardless of any recent deploy?",
    {"true": "a dependency is at its limit or failing (DB connections 100%, 'connection "
             "pool exhausted', cache unreachable, downstream 503)",
     "false": "no sign of a saturated or failing dependency"},
)

# Base questions that do not depend on the action. The action-specific repeat question is
# added per request in DeciderGate.review / build_questions.
QUESTIONS = {
    "cause": Decider.choice(
        "What is the most likely root cause of this incident, judging only from the log?", CAUSES
    ),
    "dep_saturated": DEP_SATURATED_Q,
}

# action name -> the root cause that justifies it
JUSTIFYING_CAUSE = {"rollback": "bad_deploy", "scale_out": "traffic_surge"}


def build_questions(action: str, policy: "Policy | None" = None, spec: "GateSpec | None" = None) -> dict:
    """Questions for one review: the base set plus the action-specific repeat guard, and
    the blast-radius score question when the policy is risk-aware."""
    if spec is None or spec is OPS_SPEC:
        q = dict(QUESTIONS)
        q["already_tried"] = _already_tried_q(action)
    else:
        q = {"cause": Decider.choice(spec.cause_question, spec.causes), spec.blocker_key: spec.blocker_question,
             "already_tried": spec.repeat_question(action)}
    if policy is not None and policy.high_risk_requires > 0:
        q["blast_radius"] = BLAST_RADIUS_Q
    return q


@dataclass(frozen=True)
class GateSpec:
    """Everything domain-specific about a gate, so the same pattern can guard another kind of action.

    The default OPS_SPEC reproduces the original rollback / scale_out behaviour exactly. Another
    domain supplies its own causes, the cause that justifies each action, a 'blocker' question
    (the analogue of "a dependency is saturated") and a repeat question.
    """
    name: str
    causes: dict
    justifying: dict                      # action -> the cause that justifies it
    cause_question: str
    blocker_key: str                      # answer key of the blocker noul question
    blocker_question: dict
    repeat_question: object               # callable(action) -> noul question dict
    blocker_reason: object                # callable(action) -> str
    repeat_reason: str
    unsupported_reason: object            # callable(top, needed, action) -> str


@dataclass(frozen=True)
class Policy:
    """Thresholds live here, not in the model."""
    min_cause_prob: float = 0.45   # P(justifying cause) needed to allow the action
    repeat_prob: float = 0.50      # P(this action already tried) at/above this blocks a repeat
    dep_block_prob: float = 0.50   # P(dependency saturated) at/above this blocks the action
    escalate_band: float = 0.0     # if >0, cause within [min-band, min) escalates to a human
                                   # instead of a hard block (0 keeps the old two-way behaviour)
    high_risk_requires: float = 0.0  # if >0, a high blast-radius action needs cause >= this
                                     # (stricter than min_cause_prob); 0 ignores the risk score


# A score question (the Decider's third question type, after noul and choice): rate the
# blast radius of the proposed action against an ordered rubric, lowest first. Added to a
# review only when a risk-aware policy is in use; judge() ignores it otherwise.
BLAST_RADIUS_Q = Decider.score(
    "How large is the blast radius of this action if it is wrong?",
    ["contained to one task or request",
     "affects one service",
     "affects users or data broadly"],
)


OPS_SPEC = GateSpec(
    name="ops",
    causes=CAUSES,
    justifying=JUSTIFYING_CAUSE,
    cause_question="What is the most likely root cause of this incident, judging only from the log?",
    blocker_key="dep_saturated",
    blocker_question=DEP_SATURATED_Q,
    repeat_question=_already_tried_q,
    blocker_reason=lambda action: ("a downstream dependency is saturated or failing; "
                                   f"'{action}' does not address that -- fix the dependency first"),
    repeat_reason=("this action was already tried and the problem persists; "
                   "do not repeat it, look for another cause"),
    unsupported_reason=lambda top, needed, action: (f"the log points to '{top}', not '{needed}', so '{action}' "
                                                    "is not supported by the evidence"),
)


@dataclass
class Verdict:
    reason: str
    scores: dict = field(default_factory=dict)
    decision: str = "allow"  # "allow" | "block" | "escalate"

    def __init__(self, allow=None, reason="", scores=None, decision=None):
        # Back-compat: Verdict(True/False, reason, scores) still works. New callers may pass
        # decision="escalate". allow stays a derived boolean so existing `v.allow` is intact.
        self.reason = reason
        self.scores = scores or {}
        if decision is not None:
            self.decision = decision
        elif allow is None:
            self.decision = "allow"
        else:
            self.decision = "allow" if allow else "block"

    @property
    def allow(self) -> bool:
        return self.decision == "allow"

    @property
    def escalated(self) -> bool:
        return self.decision == "escalate"


def render_state(log: str, action: str, args: dict | None = None) -> str:
    return f"--- INCIDENT LOG ---\n{log}\n\n--- PROPOSED ACTION ---\n{action} {args or ''}".rstrip()


def _repeat_score(answers: dict) -> float:
    """P(action already tried). Accepts the widened key or the legacy 'already_acted'."""
    for key in ("already_tried", "already_acted"):
        if key in answers:
            return answers[key]["noul"]
    return 0.0


def judge(answers: dict, action: str, policy: Policy = Policy(), spec: GateSpec | None = None) -> Verdict:
    """Pure policy over the model's answers (no I/O, easy to unit test).

    Guards run in order of certainty: a repeat we have evidence of, then a dependency we
    can see is saturated, then whether the cause actually matches the action. Two optional
    layers (off by default, so the two-way behaviour is unchanged):
      - escalate_band: a cause just under the bar escalates to a human instead of blocking.
      - high_risk_requires: a high blast-radius action needs a stronger cause.
    """
    probs = answers["cause"]["probabilities"]
    repeat = _repeat_score(answers)
    spec = spec or OPS_SPEC
    dep = answers.get(spec.blocker_key, {}).get("noul", 0.0)
    scores = {"cause_probs": probs, "already_tried": repeat, "dep_saturated": dep}
    # blast radius is a 0..2 score when the risk question was asked; higher = wider impact
    risk = answers.get("blast_radius", {}).get("score")
    if risk is not None:
        scores["blast_radius"] = risk
    needed = spec.justifying.get(action)
    if needed is None:
        return Verdict(True, f"'{action}' is not gated", scores)
    if repeat >= policy.repeat_prob:
        return Verdict(False, spec.repeat_reason, scores)
    if dep >= policy.dep_block_prob:
        return Verdict(False, spec.blocker_reason(action), scores)

    cause_p = probs.get(needed, 0.0)
    top = max(probs, key=probs.get)

    # risk-aware bar: a high blast-radius action needs a stronger cause than the default.
    bar = policy.min_cause_prob
    high_risk = risk is not None and risk >= 1.5
    if high_risk and policy.high_risk_requires > 0:
        bar = max(bar, policy.high_risk_requires)

    if cause_p < bar:
        # within the escalate band just under the bar? ask a human rather than hard-blocking.
        if policy.escalate_band > 0 and cause_p >= bar - policy.escalate_band:
            why = "a human should decide" if not high_risk else \
                  "high blast radius and the evidence is borderline -- a human should decide"
            return Verdict(reason=f"evidence for '{action}' is borderline ({cause_p:.2f}); {why}",
                           scores=scores, decision="escalate")
        if top == needed:   # the right cause is the leading one but not strong enough: say so plainly
            return Verdict(False, f"the evidence for '{action}' is too weak ({cause_p:.2f} below the {bar:.2f} bar)", scores)
        return Verdict(False, spec.unsupported_reason(top, needed, action), scores)
    return Verdict(True, f"evidence supports '{action}'", scores)


class DeciderGate:
    """Reviews one proposed action. Optionally also enforces a session-aware temporal
    policy (AgentCore-style) across actions.

    Additive by design: with no `history`/`temporal_policy` this behaves exactly as before
    -- same questions, same verdicts, nothing recorded. Pass both to opt into the temporal
    guard, which runs *before* the model (a thrash it catches needs no inference) and
    records an action only when the full review allows it.
    """

    def __init__(self, decider: Decider | None = None, policy: Policy = Policy(),
                 history=None, temporal_policy=None, audit=None, cache=None, spec: GateSpec | None = None):
        self.spec = spec or OPS_SPEC
        self.decider = decider or Decider()
        self.policy = policy
        self.history = history
        self.temporal_policy = temporal_policy
        self.audit = audit          # optional AuditLog: records every verdict (see audit.py)
        self.cache = cache          # optional DecisionCache: dedupes identical reviews

    def review(self, log: str, action: str, args: dict | None = None) -> Verdict:
        # 0. idempotency (opt-in): an identical (log, action) seen again within the cache
        #    window reuses the prior verdict -- no model call, no double execution.
        if self.cache is not None:
            hit = self.cache.get(log, action, args)
            if hit is not None:
                self._write_audit(log, action, args, hit, source="cache")
                return hit

        # 1. temporal guard first (opt-in): a cross-action limit the single-action judge
        #    cannot see. Cheap, and it needs no model call.
        if self.history is not None and self.temporal_policy is not None and action in self.spec.justifying:
            tv = self.history.review(action, self.temporal_policy)
            if not tv.allow:
                v = Verdict(False, tv.reason, {"temporal": tv.counts})
                self._write_audit(log, action, args, v, source="temporal")
                return v

        # 2. the single-action evidence check (unchanged default behaviour).
        answers = self.decider.ask(render_state(log, action, args),
                                   build_questions(action, self.policy, self.spec))
        verdict = judge(answers, action, self.policy, self.spec)

        # 3. remember only actions that actually get the green light, so the temporal
        #    window reflects what truly ran.
        if verdict.allow and self.history is not None and action in self.spec.justifying:
            self.history.record(action)

        if self.cache is not None:
            self.cache.put(log, action, args, verdict)
        self._write_audit(log, action, args, verdict, source="model")
        return verdict

    def _write_audit(self, log, action, args, verdict, source):
        if self.audit is not None:
            self.audit.record(log=log, action=action, args=args, verdict=verdict,
                              policy=self.policy, source=source)
