"""Head-to-head on the same golden set: DeciderGate vs a Bedrock LLM judge.

Two ways to gate the same risky action:

  gate      Decider 2B answers narrow typed questions; plain-Python policy decides.
  baseline  A general Bedrock LLM (Haiku 4.5) reads the same case and decides directly.

We measure both on identical cases and report accuracy, latency (median / p95) and dollar
cost, so the trade-off is a table of numbers rather than an opinion. The Decider runs
locally (cost ~ $0 of API spend, electricity only); the baseline is billed per token.

Run:  python bench_compare.py                   # golden set, both engines
      python bench_compare.py --gate            # local Decider only (no AWS calls)
      python bench_compare.py --baseline        # Bedrock judge only
      python bench_compare.py --set=holdout      # the held-out validation set
      python bench_compare.py --gate --set=holdout
"""
from __future__ import annotations

import json
import statistics
import sys

from rollback_gate.client import Decider, ServerUnavailable
from rollback_gate.gate import DeciderGate
from rollback_gate.golden import cases as golden_cases
from rollback_gate.holdout import cases as holdout_cases

CASE_SETS = {"golden": golden_cases, "holdout": holdout_cases}


def _p95(xs: list[float]) -> float:
    s = sorted(xs)
    return round(s[max(0, int(len(s) * 0.95) - 1)], 1)


def _summary(rows: list[dict]) -> dict:
    lat = [r["latency_ms"] for r in rows if r["latency_ms"] is not None]
    return {
        "n": len(rows),
        "accuracy": round(sum(r["ok"] for r in rows) / len(rows), 3),
        "false_allow": [r["id"] for r in rows if r["got"] and not r["expected"]],
        "false_block": [r["id"] for r in rows if r["got"] is False and r["expected"]],
        "errors": [r["id"] for r in rows if r["got"] is None],
        "latency_ms_median": round(statistics.median(lat), 1) if lat else None,
        "latency_ms_p95": _p95(lat) if lat else None,
    }


def run_gate(cases) -> dict:
    d = Decider()
    gate = DeciderGate(d)
    rows = []
    for c in cases():
        v = gate.review(c["log"], c["action"])
        rows.append(dict(id=c["id"], expected=c["allow"], got=v.allow,
                         ok=v.allow == c["allow"], reason=v.reason,
                         latency_ms=d.last_latency_ms))
    s = _summary(rows)
    s.update(engine="decider-2b-local", input_tokens=d.input_tokens,
             api_cost_usd=0.0, rows=rows)
    return s


def run_baseline(cases) -> dict:
    from rollback_gate.baseline import BaselineJudge
    j = BaselineJudge()
    rows = []
    for c in cases():
        try:
            v = j.review(c["log"], c["action"])
            got, reason = v.allow, v.reason
        except Exception as exc:  # a malformed/filtered reply shouldn't abort the run
            got, reason = None, f"ERROR: {exc}"
        rows.append(dict(id=c["id"], expected=c["allow"], got=got,
                         ok=got == c["allow"], reason=reason,
                         latency_ms=j.last_latency_ms))
    s = _summary(rows)
    s.update(engine=j.model_id, input_tokens=j.input_tokens,
             output_tokens=j.output_tokens, api_cost_usd=round(j.cost_usd(), 6),
             rows=rows)
    return s


def main() -> None:
    args = sys.argv[1:]
    which = next((a for a in args if a in ("--both", "--gate", "--baseline")), "--both")
    case_set = next((a.split("=", 1)[1] for a in args if a.startswith("--set=")), "golden")
    cases = CASE_SETS[case_set]
    out: dict = {"case_set": case_set}
    if which in ("--both", "--gate"):
        try:
            out["gate"] = run_gate(cases)
        except ServerUnavailable as exc:
            out["gate"] = {"error": str(exc)}
    if which in ("--both", "--baseline"):
        out["baseline"] = run_baseline(cases)

    if "gate" in out and "baseline" in out and "error" not in out["gate"]:
        g, b = out["gate"], out["baseline"]
        out["comparison"] = {
            "accuracy": {"gate": g["accuracy"], "baseline": b["accuracy"]},
            "latency_ms_median": {"gate": g["latency_ms_median"], "baseline": b["latency_ms_median"]},
            "api_cost_usd_total": {"gate": g["api_cost_usd"], "baseline": b["api_cost_usd"]},
            "note": "Decider runs locally: $0 API cost. Baseline billed per token (Haiku 4.5 "
                    "$1/$5 per 1M in/out, us-east-1, verify before quoting).",
        }

    out_path = f"bench_{case_set}.json" if case_set != "golden" else "bench_compare.json"
    json.dump(out, open(out_path, "w"), indent=2)
    print(f"[{case_set}] -> {out_path}")
    for name in ("gate", "baseline"):
        if name in out:
            s = {k: v for k, v in out[name].items() if k != "rows"}
            print(name, s)
    if "comparison" in out:
        print("comparison", out["comparison"])


if __name__ == "__main__":
    main()
