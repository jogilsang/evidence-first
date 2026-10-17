"""A second domain for the same gate: customer-support remedies (refund / goodwill credit).

Nothing in gate.py changes. A domain is just a GateSpec: the causes, which cause justifies which
action, a 'blocker' question (here: an abuse/fraud signal, the analogue of "a dependency is
saturated") and a repeat question. This shows the pattern is not about rollbacks: it is
"a small local model answers narrow typed questions about the evidence; code decides whether the
agent's action may run".

    gate = DeciderGate(Decider(), spec=REFUND_SPEC)
    gate.review(ticket_text, "refund")
"""
from __future__ import annotations

from .client import Decider
from .gate import GateSpec

REFUND_CAUSES = {
    "merchant_fault": "the item arrived defective, damaged or wrong, or never arrived, as documented in the ticket",
    "service_delay": "the order arrived late or a promised service was slow, but the item itself is fine",
    "changed_mind": "the customer simply no longer wants the item or changed their mind; nothing is wrong with the order",
    "unknown": "the ticket does not show a clear reason",
}

REFUND_JUSTIFYING = {"refund": "merchant_fault", "goodwill_credit": "service_delay"}

FRAUD_SIGNAL_Q = Decider.noul(
    "Does the ticket show an abuse or fraud signal (many refund claims in a short time, a claim that contradicts "
    "the delivery confirmation or tracking, or a chargeback already filed)?",
    {"true": "there is a clear abuse or fraud signal in the ticket",
     "false": "no sign of abuse or fraud"},
)


def _already_remedied_q(action: str) -> dict:
    what = action.replace("_", " ")
    return Decider.noul(
        f"Has this customer already received a {what} (or an equivalent remedy) for this same order?",
        {"true": f"a {what} or equivalent was already given for this order",
         "false": f"no {what} has been given yet for this order"},
    )


REFUND_SPEC = GateSpec(
    name="refund",
    causes=REFUND_CAUSES,
    justifying=REFUND_JUSTIFYING,
    cause_question="What is the customer's real situation, judging only from the support ticket?",
    blocker_key="fraud_signal",
    blocker_question=FRAUD_SIGNAL_Q,
    repeat_question=_already_remedied_q,
    blocker_reason=lambda action: (f"the ticket shows an abuse or fraud signal; '{action}' should not be issued "
                                   "automatically -- send it to a human reviewer"),
    repeat_reason="this order already received a remedy; do not issue another one",
    unsupported_reason=lambda top, needed, action: (f"the ticket points to '{top}', not '{needed}', so '{action}' "
                                                    "is not supported by the evidence"),
)
