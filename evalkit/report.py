"""Write evalkit/RESULTS.md, evalkit/SPOT_CHECK.md and docs/FOOL_THE_GATE.md from the saved result JSONs.

    python -m evalkit.report

Nothing here re-runs a model; it only renders what score.py / refund.py already measured, so the
numbers in the README and article can be traced to data/*.json.
"""
from __future__ import annotations

import json
import random
from pathlib import Path

HERE = Path(__file__).resolve().parent
DATA = HERE / "data"
ROOT = HERE.parent


def load(name, default=None):
    p = DATA / name
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else default


def pct(x) -> str:
    return f"{x * 100:.1f}%"


def short(t: str, n: int = 260) -> str:
    t = " ".join(t.split())
    return t if len(t) <= n else t[: n - 1] + "…"


def perturb_table(res: dict) -> list[str]:
    gate_p, base_p = res.get("perturbed", {}), res.get("perturbed_baseline", {})
    lines = ["| perturbation | gate accuracy | gate false allow / false block | Haiku 4.5 accuracy |", "|---|---|---|---|"]
    lines.append(f"| none (original) | {pct(res['gate']['accuracy'])} | {len(res['gate']['false_allow'])} / {len(res['gate']['false_block'])} | "
                 f"{pct(res['baseline']['accuracy']) if 'baseline' in res else '-'} |")
    for name, g in gate_p.items():
        b = base_p.get(name)
        lines.append(f"| {name} | {pct(g['accuracy'])} | {len(g['false_allow'])} / {len(g['false_block'])} | {pct(b['accuracy']) if b else 'not run'} |")
    return lines


def perturb_reading(res: dict) -> list[str]:
    g, gp, bp = res["gate"], res.get("perturbed", {}), res.get("perturbed_baseline", {})
    out = ["Reading it honestly:"]
    for name in ("noise", "korean"):
        if name in gp and name in bp:
            d = gp[name]["accuracy"] - bp[name]["accuracy"]
            who = "the Haiku judge" if d < 0 else "the gate"
            out.append(f"- `{name}`: gate {pct(gp[name]['accuracy'])} vs Haiku {pct(bp[name]['accuracy'])}; {who} holds up better ({abs(d) * 100:.1f} points).")
    out.append("- A small 2B classifier is more easily distracted by irrelevant log lines than a large general model, so noisy real-world logs are the "
               "main place to improve the gate (shorter evidence windows, line filtering before the question).")
    return out


def main() -> int:
    res = load("independent_results.json")
    removed = load("independent_removed.json", [])
    cases = load("independent_cases.json")
    refund = load("refund_results.json")
    refund_removed = load("refund_removed.json", [])
    golden = json.loads((ROOT / "bench_compare.json").read_text(encoding="utf-8"))["gate"]
    holdout = json.loads((ROOT / "bench_holdout.json").read_text(encoding="utf-8"))["gate"]
    g, b = res["gate"], res.get("baseline")

    out = ["# Independent evaluation (frozen policy)", "",
           "The golden set and the held-out set in this repo were written by the same author and model family that built the",
           "gate, so they cannot support an independence claim. This page reports a set that was **not** written by us and was",
           "**not** used to tune anything.", "",
           "## Protocol", "",
           "- **Policy frozen** before generation: the default `Policy` and questions exactly as shipped in the initial public commit. Nothing was retuned after seeing these results. A later refactor (a `GateSpec` for other domains and a clearer weak-evidence message) was re-scored on all 115 cases and changed no verdict.",
           "- **Generator:** Amazon Nova Pro (`us.amazon.nova-pro-v1:0`, non-Anthropic) wrote incident logs for 15 scenario families (`families.py`), 8 per family requested.",
           "- **Labels by construction:** each family states the kind of incident to write, so the expected verdict follows from the gate's published semantics. The generator never labels.",
           "- **Independent verifier:** Llama 3.3 70B (`us.meta.llama3-3-70b-instruct-v1:0`) labelled every log blind. Disagreements are **quarantined in `data/independent_removed.json` with a reason**, not silently dropped.",
           f"- **Counts:** {len(cases) + len(removed)} generated, {len(cases)} kept, {len(removed)} quarantined. Prompts and code: `generate.py`; every case records generator, verifier and date.",
           "- **Human review:** not yet done. `SPOT_CHECK.md` lists cases for a human to read. Treat the labels as machine-verified only.", "",
           "## Headline", "",
           "| set | cases | who wrote it | gate accuracy |", "|---|---|---|---|",
           f"| golden (used to tune) | {golden['n']} | the authors | {pct(golden['accuracy'])} (tuned on it) |",
           f"| held-out | {holdout['n']} | the authors, never tuned on | {pct(holdout['accuracy'])} |",
           f"| **independent (this page)** | {g['n']} | **Nova Pro, verified by Llama** | **{pct(g['accuracy'])}** |"]
    if refund:
        out.append(f"| second domain: support refunds | {refund['n']} | Nova Pro, verified by Llama | {pct(refund['accuracy'])} ({'no false allows' if not refund['false_allow'] else str(len(refund['false_allow'])) + ' false allows'}) |")
    out += ["", "On data we did not write, the gate is **not** 100%: the honest headline is tuned 100% / independent "
            f"{pct(g['accuracy'])}.", ""]
    if b:
        out += ["## Gate vs a general LLM judge on the same independent cases", "",
                "| | DeciderGate (local Decider 2B) | Bedrock Haiku 4.5 |", "|---|---|---|",
                f"| accuracy | {pct(g['accuracy'])} | {pct(b['accuracy'])} |",
                f"| false allow (action wrongly approved) | {len(g['false_allow'])} | {len(b['false_allow'])} |",
                f"| false block (justified action refused) | {len(g['false_block'])} | {len(b['false_block'])} |",
                f"| latency (median) | ~{g['latency_ms_median']:.0f} ms | ~{b['latency_ms_median']:.0f} ms |",
                f"| API cost / {b['n']} cases | $0 | ~${b.get('api_cost_usd', 0):.3f} |", "",
                "With n=115 the accuracy gap is within noise; the difference that matters is the **kind** of error. The gate's misses are "
                "false allows (the dangerous direction), while Haiku's misses are false blocks concentrated in a single family (`so-peak`, "
                "whose wording says autoscaling is already at its ceiling, which Haiku read as \"scaling out is impossible\").", ""]
    out += ["## Per scenario family", "", "| family | gate | Haiku |", "|---|---|---|"]
    for fam, v in g["per_family"].items():
        out.append(f"| {fam} | {v} | {b['per_family'].get(fam, '-') if b else '-'} |")
    out += ["", "## Every gate error (nothing hidden)", ""]
    for r in g["rows"]:
        if not r["ok"]:
            out.append(f"- `{r['id']}` expected {'ALLOW' if r['expected'] else 'BLOCK'}, gate said {'ALLOW' if r['got'] else 'BLOCK'}: {short(r['log'])}")
    out += ["", "## Robustness to perturbations", "",
            "Each perturbation keeps the facts and the label; only the surface changes (typos, shuffled sentences, five unrelated healthy log lines, "
            "Korean translation by Nova Pro).", ""] + perturb_table(res) + [""] + perturb_reading(res) + [""]
    if refund:
        out += ["## Second domain: customer-support refunds", "",
                f"The same `DeciderGate`, with a different `GateSpec` (`rollback_gate/domains.py`), no change to `gate.py`: {refund['n']} cases, "
                f"accuracy {pct(refund['accuracy'])}, false allow {len(refund['false_allow'])}, false block {len(refund['false_block'])}, "
                f"median {refund['latency_ms_median']:.0f} ms. Quarantined: {len(refund_removed)}.", "", "| family | result |", "|---|---|"]
        out += [f"| {k} | {v} |" for k, v in refund["per_family"].items()]
        for r in refund["rows"]:
            if not r["ok"]:
                out.append(f"\n- error `{r['id']}` expected {'ALLOW' if r['expected'] else 'BLOCK'}: {short(r['log'])}")
        out.append("")
    out += ["## Limits", "",
            "- The cases are synthetic and machine-written; real incidents are messier. Expect to re-tune thresholds on your own data.",
            "- One verifier model checked the labels; a human has not yet reviewed them (see `SPOT_CHECK.md`).",
            "- Latency is from one Apple-silicon laptop (MLX). Haiku latency includes public-endpoint network time.",
            "- Perturbations are a sample (one seed each), not an exhaustive robustness proof."]
    (HERE / "RESULTS.md").write_text("\n".join(out) + "\n", encoding="utf-8")

    # --- human spot-check list
    rng = random.Random(7)
    sample = rng.sample(cases, 15)
    sc = ["# Human spot-check list", "",
          "Labels here are machine-verified (Nova Pro wrote, Llama 3.3 70B checked). A human has **not** read them yet.",
          "Please read each case and tick it if the expected verdict is right for the proposed action.", "",
          "## 15 random kept cases (seeded)", ""]
    for c in sample:
        sc.append(f"- [ ] `{c['id']}` action `{c['action']}`, expected **{'ALLOW' if c['allow'] else 'BLOCK'}**: {short(c['log'], 400)}")
    sc += ["", f"## All {len(removed)} quarantined ops cases (generator and verifier disagreed)", ""]
    for c in removed:
        sc.append(f"- [ ] `{c['id']}` action `{c['action']}`, generator label **{'ALLOW' if c['allow'] else 'BLOCK'}**, verifier said "
                  f"**{'ALLOW' if c.get('verifier_allow') else 'BLOCK'}**: {short(c['log'], 400)}")
    (HERE / "SPOT_CHECK.md").write_text("\n".join(sc) + "\n", encoding="utf-8")

    # --- fool-the-gate gallery
    flips = []
    base_ok = {r["id"]: r for r in g["rows"]}
    for name, pv in res.get("perturbed", {}).items():
        for r in pv["rows"]:
            if base_ok[r["id"]]["ok"] and not r["ok"]:
                flips.append((name, r))
    gal = ["# Can you fool the gate?", "",
           "Honest gallery: the cases where the shipped policy gets it wrong, and the perturbations that flip a verdict that was right.",
           "Try your own with `python play.py \"<log>\" rollback` (needs the local Decider; no AWS calls).", "",
           "## 1. Misses on independent cases", ""]
    for r in g["rows"]:
        if not r["ok"]:
            gal += [f"**`{r['id']}`** (expected {'ALLOW' if r['expected'] else 'BLOCK'}, gate said {'ALLOW' if r['got'] else 'BLOCK'})", "",
                    f"> {r['log']}", "", f"Gate reason: _{r['reason']}_", ""]
    gal += ["## 2. Perturbations that flip a correct verdict", "",
            f"{len(flips)} flips across {len(res.get('perturbed', {}))} perturbation kinds (typos, reorder, noise, korean).", ""]
    for name, r in flips[:10]:
        gal += [f"- **{name}** on `{r['id']}` (expected {'ALLOW' if r['expected'] else 'BLOCK'}): {short(r['log'], 300)}"]
    gal += ["", "## 3. Try it", "", "```bash", "python play.py --examples          # a few cases, including known misses",
            "python play.py \"<log>\" rollback", "python play.py \"<ticket>\" refund --domain refund", "```", ""]
    (ROOT / "docs" / "FOOL_THE_GATE.md").write_text("\n".join(gal), encoding="utf-8")
    print("wrote evalkit/RESULTS.md, evalkit/SPOT_CHECK.md, docs/FOOL_THE_GATE.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
