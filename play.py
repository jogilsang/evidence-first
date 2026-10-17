"""Try to fool the gate. Paste an incident log (or a support ticket), name the action, see the verdict.

    python play.py "<log text>" rollback                 # ops domain (rollback / scale_out)
    python play.py "<ticket text>" refund --domain refund   # support domain (refund / goodwill_credit)
    python play.py --examples                             # replay the curated cases from docs/FOOL_THE_GATE.md
    python play.py                                        # interactive

Needs the local Decider server (strands-decider serve <checkpoint> --port 8099). No AWS calls.
"""
from __future__ import annotations

import sys

from rollback_gate.client import Decider, ServerUnavailable
from rollback_gate.domains import REFUND_SPEC
from rollback_gate.gate import DeciderGate, OPS_SPEC

SPECS = {"ops": OPS_SPEC, "refund": REFUND_SPEC}
GREEN, RED, YELLOW, DIM, RESET = "\033[32m", "\033[31m", "\033[33m", "\033[2m", "\033[0m"

# (domain, action, log, expected, note). The two ops cases marked BLOCK are real misses of the shipped policy.
EXAMPLES = [
    ("ops", "rollback", "Service shop-api. 14:02 deploy v42 finished. 14:04 5xx rate 38%, p99 9s. No other changes.", "ALLOW", "a clean deploy-then-errors case"),
    ("ops", "rollback", "ranker-api has seen a dramatic rise in CPU usage and timeout errors, with request rates tripling in the past hour. "
                        "The last deployment was three days ago, prior to the start of the current traffic surge.",
     "BLOCK", "KNOWN MISS: a traffic surge with a deploy mentioned three days earlier"),
    ("ops", "scale_out", "11:00 UTC: Profile-svc error rates stay constant at 18% following the increase of task counts from 20 to 40 "
                         "at 10:30 UTC. CPU is now at 25%.",
     "BLOCK", "KNOWN MISS: capacity was already doubled and errors persist"),
    ("refund", "refund", "Order ORD-78618 never arrived; tracking indicates it was returned to the sender. The customer asks for a full reimbursement.",
     "ALLOW", "second domain: support refunds"),
]


def review(gate: DeciderGate, log: str, action: str) -> None:
    v = gate.review(log, action)
    colour = GREEN if v.allow else (YELLOW if v.escalated else RED)
    label = v.decision.upper()
    c = v.scores.get("cause_probs", {})
    top = max(c, key=c.get) if c else "-"
    print(f"\n  {colour}{label}{RESET}  {v.reason}")
    print(f"  {DIM}cause~{top} {c.get(top, 0):.2f} | already-tried {v.scores.get('already_tried', 0):.2f} | "
          f"blocker {v.scores.get('dep_saturated', 0):.2f} | {gate.decider.last_latency_ms} ms{RESET}\n")


def main(argv: list[str]) -> int:
    domain = "ops"
    if "--domain" in argv:
        i = argv.index("--domain")
        domain = argv[i + 1]
        argv = argv[:i] + argv[i + 2:]
    if domain not in SPECS:
        print(f"unknown domain {domain!r}; choose from {', '.join(SPECS)}")
        return 2
    try:
        d = Decider()
        print(DIM + d.banner() + RESET)
    except ServerUnavailable as exc:
        print(exc)
        return 1

    if "--examples" in argv:
        for dom, action, log, expected, note in EXAMPLES:
            print(f"[{dom}] {action}: {log}\n  expected {expected} ({note})")
            review(DeciderGate(d, spec=SPECS[dom]), log, action)
        return 0
    gate = DeciderGate(d, spec=SPECS[domain])
    if len(argv) >= 2:
        review(gate, argv[0], argv[1])
        return 0
    print(f"domain={domain}; actions: {', '.join(SPECS[domain].justifying)}; empty line to quit")
    while True:
        log = input("log> ").strip()
        if not log:
            return 0
        action = input(f"action ({'/'.join(SPECS[domain].justifying)})> ").strip()
        review(gate, log, action)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
