"""Pick an action, don't just gate one: the Decider ranks remediations, the gate confirms.

Everywhere else the agent proposes an action and the gate reviews it. Here the agent
doesn't know what to do, so it asks the gate to suggest. This leans directly on the
Decider's `choice` question -- the thing the hackathon is named for -- to *rank* the
candidate actions. But the recommendation is not trusted on its own: a probe shows the
model will sometimes top-rank `scale_out` for a saturated database, which wouldn't fix it.
So the ranking is only a shortlist; each candidate, best first, is run through the ordinary
DeciderGate, and the advisor returns the first that the gate actually confirms.

That is the pattern taken to its conclusion: the model proposes a shortlist, the code
decides which (if any) survives. If none do, the advisor escalates rather than invent one.
It is additive -- a separate entry point built on top of the gate; `review()` is untouched.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .client import Decider
from .gate import DeciderGate, Verdict, render_state

# Candidate actions the advisor can suggest, with what justifies each. Only the ones the
# gate knows how to verify (rollback, scale_out) can be *confirmed*; the others can be
# recommended but will fall through to escalate unless you extend the gate to cover them.
ACTION_CRITERIA = {
    "rollback": "a change was shipped right before the problem (deploy, config, or feature flag)",
    "scale_out": "a traffic surge is saturating resources (CPU, memory, or queue depth)",
    "restart": "a transient or stuck state a restart clears -- no change and no surge",
    "wait": "cause is unclear, or a dependency is failing; investigate before acting",
}


@dataclass
class Recommendation:
    action: str | None          # the confirmed action, or None if the advisor escalates
    decision: str               # "act" | "escalate"
    reason: str
    ranking: list = field(default_factory=list)   # [(action, prob), ...] highest first
    verdicts: dict = field(default_factory=dict)   # action -> the gate's Verdict for it


def _rank_question() -> dict:
    return Decider.choice(
        "Given the incident, which remediation does the evidence most support right now?",
        ACTION_CRITERIA,
    )


class Advisor:
    """Recommends an action for an incident, confirmed by the gate."""

    # how far down the Decider's ranking we bother to confirm (keeps it to the plausible few)
    SHORTLIST = 3

    def __init__(self, gate: DeciderGate | None = None, decider: Decider | None = None):
        self.gate = gate or DeciderGate(decider)
        self.decider = self.gate.decider

    def recommend(self, log: str) -> Recommendation:
        probs = self.decider.ask(render_state(log, "(choose)"), {"best": _rank_question()})["best"]["probabilities"]
        ranking = sorted(probs.items(), key=lambda kv: kv[1], reverse=True)

        verdicts: dict[str, Verdict] = {}
        for action, _ in ranking[: self.SHORTLIST]:
            if action not in ("rollback", "scale_out"):
                continue  # the gate only confirms these two; others are advisory-only
            v = self.gate.review(log, action)
            verdicts[action] = v
            if v.allow:
                return Recommendation(
                    action=action, decision="act",
                    reason=f"evidence most supports '{action}', and the gate confirms it: {v.reason}",
                    ranking=ranking, verdicts=verdicts)

        top = ranking[0][0]
        return Recommendation(
            action=None, decision="escalate",
            reason=(f"the model leaned '{top}', but no gated action the evidence supports "
                    "survived review -- escalate rather than act on a guess"),
            ranking=ranking, verdicts=verdicts)
