"""A four-scene demo: a hasty SRE agent proposes a fix, the DeciderGate reviews it.

The story is "the agent is about to act; a calm colleague asks for evidence first." Each
scene prints the incident, the agent's instinct, and the gate's verdict with its reason.
Scenes 2-4 are the ones worth filming: the gate turns down a plausible-looking but wrong
action, including one trap (a saturated database that looks like a bad deploy).

Run:  python demo.py          # needs the local Decider server on :8099
      python demo.py --slow   # pauses between scenes, for screen recording
"""
from __future__ import annotations

import sys
import time

from rollback_gate.client import Decider, ServerUnavailable
from rollback_gate.gate import DeciderGate

SLOW = "--slow" in sys.argv
PAUSE = 1.6 if SLOW else 0.0

# (title, what the agent "wants" to do and why, log, action)
SCENES = [
    ("Scene 1 — a fix that is justified",
     "The agent sees 5xx right after a deploy and reaches for a rollback.",
     "Service shop-api. 14:02 deploy v42 finished. 14:04 5xx rate 38%, p99 9s. "
     "v41 had 0.1% 5xx. No other changes.",
     "rollback", {"to": "v41"}),

    ("Scene 2 — the wrong reflex",
     "A marketing campaign spikes traffic. The agent still wants to roll back the last deploy.",
     "Service shop-api. Last deploy 3 days ago. 14:04 CPU 92% on all 4 tasks, p99 2.1s, "
     "request rate 4x normal (marketing campaign). 5xx 0.2%.",
     "rollback", {"to": "previous"}),

    ("Scene 3 — doing the same thing again",
     "A rollback already happened and the errors persist. The agent proposes rolling back further.",
     "Service shop-api. 14:02 rollback to v41 completed. 14:09 5xx 35% persists. "
     "Database connections at 100%.",
     "rollback", {"to": "v40"}),

    ("Scene 4 — the trap",
     "The database is at 100% connections, but to the agent it looks like just another bad deploy.",
     "Service shop-api. Last deploy 2 days ago. 14:04 5xx 40%. Database connections 100%, "
     "RDS replica lag 30s, logs show 'connection pool exhausted'.",
     "rollback", {"to": "previous"}),
]

GREEN, RED, DIM, BOLD, OFF = "\033[32m", "\033[31m", "\033[2m", "\033[1m", "\033[0m"


def main() -> None:
    try:
        gate = DeciderGate(Decider())
        gate.decider.health()
    except ServerUnavailable as exc:
        print(exc)
        sys.exit(1)

    print(f"\n{BOLD}DeciderGate — a calm second opinion before the agent acts{OFF}")
    print(f"{DIM}the agent proposes; the gate asks the model narrow questions and the code decides{OFF}\n")

    for title, instinct, log, action, args in SCENES:
        print(f"{BOLD}{title}{OFF}")
        print(f"  {DIM}incident:{OFF} {log}")
        print(f"  {DIM}agent wants:{OFF} {action} {args}  — {instinct}")
        time.sleep(PAUSE)
        v = gate.review(log, action, args)
        tag = f"{GREEN}ALLOW{OFF}" if v.allow else f"{RED}BLOCK{OFF}"
        print(f"  gate: {tag}  {v.reason}  {DIM}({gate.decider.last_latency_ms:.0f} ms){OFF}")
        c = v.scores["cause_probs"]
        top = max(c, key=c.get)
        print(f"  {DIM}why: cause~{top} {c[top]:.2f} | repeat {v.scores['already_tried']:.2f} | "
              f"dep-saturated {v.scores['dep_saturated']:.2f}{OFF}\n")
        time.sleep(PAUSE)

    print(f"{DIM}three of four actions were turned down — each for a reason you can read.{OFF}\n")

    temporal_scene(gate.decider)


def temporal_scene(decider):
    """Scene 5: a cross-action limit the single-action gate can't see.

    The same rollback is justified by the evidence every time -- but an agent that keeps
    rolling back within minutes is thrashing. A temporal policy (AgentCore-style) catches
    the repeat before the model is even asked.
    """
    from rollback_gate.temporal import ActionHistory, TemporalPolicy
    from rollback_gate.gate import DeciderGate

    hist = ActionHistory()
    gate = DeciderGate(decider, history=hist,
                       temporal_policy=TemporalPolicy(window_seconds=900, max_per_action=1))
    log = ("Service shop-api. 14:02 deploy v42 finished. 14:04 5xx rate 38%, p99 9s. "
           "v41 had 0.1% 5xx. No other changes.")

    print(f"{BOLD}Scene 5 — the limit across actions (temporal policy){OFF}")
    print(f"  {DIM}a justified rollback, then the agent tries the same move again minutes later{OFF}")
    for i in (1, 2):
        time.sleep(PAUSE)
        v = gate.review(log, "rollback", {"to": "v41"})
        tag = f"{GREEN}ALLOW{OFF}" if v.allow else f"{RED}BLOCK{OFF}"
        print(f"  attempt {i}: rollback -> {tag}  {v.reason}")
    print(f"  {DIM}same evidence both times; the second is blocked by a cross-action rule, "
          f"not by the log.{OFF}\n")


if __name__ == "__main__":
    main()
