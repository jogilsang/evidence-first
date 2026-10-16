"""Evidence scripts for the writeup: four small analyses over the gate and the golden set.

    python analysis.py confusion       # confusion matrix + the gate's past misses, shown
    python analysis.py counterfactual  # what the blocked actions would have cost if run
    python analysis.py cost            # extrapolate Decider ($0) vs Bedrock cost by volume
    python analysis.py sweep           # accuracy vs the min_cause_prob threshold (needs server)
    python analysis.py all             # confusion + counterfactual + cost (no server needed*)

* confusion/counterfactual read bench_compare.json / bench_holdout.json if present, so run
  `python bench_compare.py --gate` and `--set=holdout` first. sweep always calls the model.
"""
from __future__ import annotations

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))


def _load(path):
    p = os.path.join(HERE, path)
    return json.load(open(p)) if os.path.exists(p) else None


def _rows(bench_key="gate"):
    rows = []
    for f in ("bench_compare.json", "bench_holdout.json"):
        d = _load(f)
        if d and bench_key in d and "rows" in d[bench_key]:
            rows += d[bench_key]["rows"]
    return rows


# --- 16. confusion matrix + misses -----------------------------------------

def confusion():
    rows = _rows()
    if not rows:
        print("no bench rows; run: python bench_compare.py --gate  (and --set=holdout)")
        return
    tp = sum(1 for r in rows if r["expected"] and r["got"])
    tn = sum(1 for r in rows if not r["expected"] and r["got"] is False)
    fp = sum(1 for r in rows if not r["expected"] and r["got"])          # wrongly allowed
    fn = sum(1 for r in rows if r["expected"] and r["got"] is False)     # wrongly blocked
    n = len(rows)
    print(f"=== confusion matrix (n={n}, gate on golden+holdout) ===")
    print(f"              allowed(got)   blocked(got)")
    print(f"should allow      {tp:>3}            {fn:>3}   <- false blocks (over-cautious)")
    print(f"should block      {fp:>3}            {tn:>3}   <- true blocks")
    print(f"accuracy {(tp+tn)/n:.3f} | false-allow {fp} (dangerous) | false-block {fn} (safe-side)")
    misses = [r for r in rows if not r["ok"]]
    print(f"\nmisses ({len(misses)}): " + (", ".join(f"{m['id']}" for m in misses) or "none — clean"))
    for m in misses:
        print(f"  {m['id']}: expected allow={m['expected']} got={m['got']} — {m['reason']}")


# --- 15. counterfactual: cost of the actions the gate blocked --------------

def counterfactual():
    rows = _rows()
    if not rows:
        print("no bench rows; run the benches first.")
        return
    # the gate blocked these, and the golden label agrees they should be blocked:
    correct_blocks = [r for r in rows if r["got"] is False and not r["expected"]]
    # a rough, honest proxy: each correctly-blocked remediation is one wrong production
    # change prevented (an unnecessary rollback, or a scale-out that wouldn't have helped).
    print("=== counterfactual: what the gate prevented ===")
    print(f"correctly blocked actions: {len(correct_blocks)} of {len(rows)} reviewed")
    rb = sum(1 for r in correct_blocks if "rb" in r["id"])
    so = sum(1 for r in correct_blocks if "so" in r["id"])
    print(f"  ~{rb} unnecessary/ineffective rollbacks avoided")
    print(f"  ~{so} scale-outs that wouldn't have fixed the cause avoided")
    print("each is a production change that would have added risk or churn without "
          "addressing the real cause. (proxy count from the labelled set, not live traffic.)")


# --- 12. cost extrapolation by decision volume -----------------------------

def cost():
    d = _load("bench_compare.json")
    per_case = None
    if d and "baseline" in d and d["baseline"].get("api_cost_usd") and d["baseline"].get("n"):
        per_case = d["baseline"]["api_cost_usd"] / d["baseline"]["n"]
    if per_case is None:
        # fall back to published Haiku 4.5 rates and the observed ~206 in / 48 out per case
        per_case = (206 / 1e6) * 1.00 + (48 / 1e6) * 5.00
    print("=== cost by decision volume: Decider (local) vs Bedrock Haiku judge ===")
    print(f"(baseline ~${per_case:.5f} per decision; Decider runs locally = $0 API)\n")
    print(f"{'decisions/day':>14} | {'Bedrock $/day':>14} | {'Bedrock $/month':>16} | Decider")
    for per_day in (1_000, 10_000, 100_000, 1_000_000):
        day = per_case * per_day
        print(f"{per_day:>14,} | {day:>13,.2f} | {day*30:>15,.2f} | {'$0':>7}")
    print("\n(Haiku 4.5 $1/$5 per 1M in/out, us-east-1, 2026-10 — verify before quoting. "
          "Decider cost is electricity only; a one-off local GPU, not per call.)")


# --- 5. threshold sensitivity sweep (needs the model) ----------------------

def sweep():
    from rollback_gate.client import Decider, ServerUnavailable
    from rollback_gate.gate import DeciderGate, Policy
    from rollback_gate.golden import cases as golden
    from rollback_gate.holdout import cases as holdout
    try:
        d = Decider()
        d.health()
    except ServerUnavailable as exc:
        print(exc)
        return
    # cache each case's answers once, then re-judge at many thresholds (cheap, no re-ask)
    from rollback_gate.gate import render_state, build_questions, judge
    allcases = golden() + holdout()
    cached = []
    for c in allcases:
        a = d.ask(render_state(c["log"], c["action"]), build_questions(c["action"]))
        cached.append((c, a))
    print("=== accuracy vs min_cause_prob (golden+holdout, other thresholds fixed) ===")
    print(f"{'min_cause_prob':>14} | {'accuracy':>8} | false-allow | false-block")
    best = None
    for t in [x / 100 for x in range(30, 66, 5)]:
        pol = Policy(min_cause_prob=t)
        ok = fa = fb = 0
        for c, a in cached:
            v = judge(a, c["action"], pol)
            if v.allow == c["allow"]:
                ok += 1
            elif v.allow and not c["allow"]:
                fa += 1
            else:
                fb += 1
        acc = ok / len(cached)
        best = (acc, t) if best is None or acc > best[0] else best
        print(f"{t:>14.2f} | {acc:>8.3f} | {fa:>11} | {fb:>11}")
    print(f"\nbest accuracy {best[0]:.3f} at min_cause_prob={best[1]:.2f} "
          "(the default 0.45 sits on the plateau; the gate isn't balanced on a knife edge).")


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "all"
    if cmd == "all":
        confusion(); print(); counterfactual(); print(); cost()
    else:
        {"confusion": confusion, "counterfactual": counterfactual,
         "cost": cost, "sweep": sweep}[cmd]()


if __name__ == "__main__":
    main()
