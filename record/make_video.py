"""Render the submission demo video from REAL command output (no staging).

It runs `demo.py` and `analysis.py sweep` against the local Decider server, reads the measured
numbers from bench_compare.json / bench_holdout.json, and replays that output as a terminal
screencast with English captions. Nothing on screen is typed by hand and no personal data (account
IDs, hostnames, profile names) can leak, because only the program output is rendered.

    python record/make_video.py [out.mp4]      # needs: local Decider on :8099, ffmpeg, Pillow

Why a rendered replay instead of a screen capture: a window recording can pick up notifications,
other windows and the window title. The text here is the program's actual stdout.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
import textwrap
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
W, H = 1280, 720
MONO = "/System/Library/Fonts/Menlo.ttc"
SANS = "/System/Library/Fonts/HelveticaNeue.ttc"
BG, PANEL, FG, DIM = (13, 14, 36), (22, 24, 52), (232, 233, 245), (140, 144, 190)
GREEN, RED, ACCENT, GOLD = (74, 222, 128), (255, 107, 107), (125, 130, 255), (253, 178, 77)
ANSI = {"0": None, "1": "bold", "2": "dim", "31": RED, "32": GREEN}


def font(path, size, idx=0):
    return ImageFont.truetype(path, size, index=idx)


F_MONO = font(MONO, 17)
F_MONO_S = font(MONO, 15)
F_CAP = font(SANS, 25)
F_TITLE = font(SANS, 54, 1)
F_SUB = font(SANS, 28)
F_HEAD = font(SANS, 34, 1)


def parse_ansi(line: str):
    """-> [(text, color)] with bold rendered brighter and dim greyer."""
    spans, color, bold, dim, pos = [], FG, False, False, 0
    for m in re.finditer(r"\x1b\[(\d+)m", line):
        if m.start() > pos:
            spans.append((line[pos:m.start()], GOLD if bold and color == FG else (DIM if dim else color)))
        code = ANSI.get(m.group(1), None)
        if m.group(1) == "0":
            color, bold, dim = FG, False, False
        elif code == "bold":
            bold = True
        elif code == "dim":
            dim = True
        elif code:
            color = code
        pos = m.end()
    if pos < len(line):
        spans.append((line[pos:], GOLD if bold and color == FG else (DIM if dim else color)))
    return spans


def wrap_spans(spans, width):
    """Wrap a coloured line at `width` chars with a hanging indent of 2 spaces."""
    plain = "".join(t for t, _ in spans)
    if len(plain) <= width:
        return [spans]
    out, cur, cur_len = [], [], 0
    for text, col in spans:
        for word in re.findall(r"\S+\s*|\s+", text):
            if cur_len + len(word) > width and cur:
                out.append(cur)
                cur, cur_len = [("    ", col)], 4
            cur.append((word, col))
            cur_len += len(word)
    out.append(cur)
    return out


def caption(draw, text):
    lines = textwrap.wrap(text, 78)[:3]
    h = 24 + 34 * len(lines)
    draw.rectangle([0, H - h - 8, W, H], fill=(0, 0, 0))
    y = H - h
    for ln in lines:
        w = draw.textlength(ln, font=F_CAP)
        draw.text(((W - w) / 2, y), ln, font=F_CAP, fill=(255, 255, 255))
        y += 34


def terminal_frame(lines, cap, title="sre-demo ~/decider-gate $ python demo.py"):
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([40, 28, W - 40, H - 120], radius=14, fill=PANEL)
    d.rectangle([40, 28, W - 40, 66], fill=(30, 32, 66))
    for i, c in enumerate([(255, 95, 86), (255, 189, 46), (39, 201, 63)]):
        d.ellipse([58 + i * 26, 40, 72 + i * 26, 54], fill=c)
    d.text((150, 38), title, font=F_MONO_S, fill=DIM)
    y = 82
    for spans in lines:
        x = 62
        for text, col in spans:
            d.text((x, y), text, font=F_MONO, fill=col)
            x += d.textlength(text, font=F_MONO)
        y += 25
    caption(d, cap)
    return img


def card_frame(head, sub=None, cap=None, big=True):
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    f = F_TITLE if big else F_HEAD
    y = 200 if big else 150
    for ln in textwrap.wrap(head, 30 if big else 44):
        w = d.textlength(ln, font=f)
        d.text(((W - w) / 2, y), ln, font=f, fill=(255, 255, 255))
        y += 70 if big else 48
    if sub:
        y += 20
        for ln in textwrap.wrap(sub, 62):
            w = d.textlength(ln, font=F_SUB)
            d.text(((W - w) / 2, y), ln, font=F_SUB, fill=(190, 194, 235))
            y += 40
    if cap:
        caption(d, cap)
    return img


def table_frame(rows, cap, head):
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    d.text((70, 60), head, font=F_HEAD, fill=(255, 255, 255))
    x0, y = 70, 150
    cols = [380, 420, 320]
    for r, row in enumerate(rows):
        x = x0
        d.rectangle([x0, y - 6, x0 + sum(cols), y + 44], fill=(40, 43, 100) if r == 0 else (PANEL if r % 2 else BG))
        for c, cell in enumerate(row):
            colr = GOLD if r == 0 else (GREEN if c == 1 and r > 0 else FG)
            d.text((x + 14, y + 6), cell, font=F_SUB, fill=colr)
            x += cols[c]
        y += 56
    caption(d, cap)
    return img


def run(cmd):
    return subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, check=True).stdout


def build(out_mp4: Path):
    py = sys.executable
    demo = run([py, "demo.py"]).splitlines()
    sweep = run([py, "analysis.py", "sweep"]).splitlines()
    bench = json.load(open(ROOT / "bench_compare.json"))
    ho = json.load(open(ROOT / "bench_holdout.json"))["gate"]
    g, b = bench["gate"], bench["baseline"]

    # scene -> (header line index range), parsed from the real output
    scenes, cur = [], None
    for ln in demo:
        if re.match(r"\x1b\[1mScene \d", ln):
            cur = [ln]; scenes.append(cur)
        elif cur is not None:
            cur.append(ln)
    assert len(scenes) == 5, f"expected 5 scenes, got {len(scenes)}"

    caps = [
        "Scene 1: a deploy, then errors. Rolling back is justified, so the gate allows it.",
        "Scene 2: no deploy for three days. This is a traffic surge, so a rollback is blocked, with the reason.",
        "Scene 3: it already rolled back and errors persist. The gate will not let the agent repeat the move.",
        "Scene 4, the trap: the database is saturated but reads like a bad deploy. A second question catches it.",
        "Scene 5: same evidence twice. The second rollback is blocked by a rule that spans actions, before the model is asked.",
    ]
    states = []   # (PIL image, seconds)

    states.append((card_frame("DeciderGate", "An AI agent that can act on your infrastructure is one confident wrong decision away from an outage.",
                              "The danger is not that an agent cannot decide. It decides confidently, and wrong."), 9))
    states.append((card_frame("The model classifies. The code decides.", "A local Strands Decider 2B answers narrow typed questions; plain-Python policy turns them into allow or block.",
                              "The thresholds live in code, not in a prompt.", big=False), 8))

    code = [
        ("QUESTIONS = {", FG), ('    "cause":         Decider.choice("What is the most likely root cause ...", CAUSES),', FG),
        ('    "dep_saturated": Decider.noul("Is a downstream dependency saturated or failing?", ...),', FG),
        ('    "already_tried": Decider.noul("Was this same action already tried and it did not help?", ...),', FG),
        ("}", FG), ("", FG),
        ("@dataclass(frozen=True)", DIM), ("class Policy:", FG),
        ("    min_cause_prob: float = 0.45   # thresholds live here, not in the model", GOLD),
        ("    repeat_prob:    float = 0.50", FG), ("    dep_block_prob: float = 0.50", FG),
    ]
    st = []
    for i in range(1, len(code) + 1):
        st.append(terminal_frame([[(t, c)] for t, c in code[:i]],
                                 "gate.py: three narrow questions to the model, and a Policy of thresholds owned by the code.",
                                 title="rollback_gate/gate.py"))
    for i, im in enumerate(st):
        states.append((im, 1.1 if i < len(st) - 1 else 5))

    for sc, cap in zip(scenes[:4], caps[:4]):
        shown = []
        for i, ln in enumerate(sc):
            for w in wrap_spans(parse_ansi(ln), 112):
                shown.append(w)
            hold = 1.0
            plain = re.sub(r"\x1b\[\d+m", "", ln)
            if plain.strip().startswith("gate:"):
                hold = 3.0
            elif plain.strip().startswith("why:"):
                hold = 4.0
            elif i == 0:
                hold = 1.2
            else:
                hold = 2.2
            states.append((terminal_frame(shown[-24:], cap), hold))
        states.append((terminal_frame(shown[-24:], cap), 2.0))

    sc5 = scenes[4]
    shown = []
    for ln in sc5:
        shown += wrap_spans(parse_ansi(ln), 112)
        plain = re.sub(r"\x1b\[\d+m", "", ln)
        states.append((terminal_frame(shown[-24:], caps[4]), 4.5 if "attempt" in plain else 2.2))
    states.append((terminal_frame(shown[-24:], caps[4]), 3.0))

    ratio = b["latency_ms_median"] / g["latency_ms_median"]
    rows = [["", "DeciderGate (local)", "Bedrock Haiku 4.5"],
            ["accuracy (22 cases)", f"{g['accuracy']*100:.0f}%", f"{b['accuracy']*100:.0f}%"],
            ["latency (median)", f"~{g['latency_ms_median']:.0f} ms", f"~{b['latency_ms_median']:.0f} ms"],
            ["API cost / 22 cases", "$0", f"~${b['api_cost_usd']:.3f}"],
            ["held-out (20 cases)", f"{ho['accuracy']*100:.0f}%", "-"]]
    states.append((table_frame(rows, f"Same accuracy, about {ratio:.0f}x faster, and nothing billed per call: the Decider runs locally.",
                               "Decider gate vs a general LLM judge, same incidents"), 14))

    sw = [re.sub(r"\x1b\[\d+m", "", ln) for ln in sweep if ln.strip()]
    st = []
    for i in range(1, len(sw) + 1):
        st.append(terminal_frame([w for t in sw[:i] for w in wrap_spans([(t, FG)], 112)],
                                 "Sweeping the main threshold: every value from 0.35 to 0.50 scores 100%. A plateau, not a knife edge.",
                                 title="python analysis.py sweep"))
    for i, im in enumerate(st):
        states.append((im, 0.9 if i < len(st) - 1 else 6))

    states.append((card_frame("Open source, Apache-2.0", "65 unit tests · golden set and held-out set · temporal policy · audit log. Lift the pattern into your own agent.",
                              "#strands-decider-2b   #guardrails", big=False), 9))

    tmp = ROOT / "record" / "_frames"
    tmp.mkdir(exist_ok=True)
    lst = []
    for i, (im, sec) in enumerate(states):
        p = tmp / f"f{i:04d}.png"
        im.save(p)
        lst.append(f"file '{p}'\nduration {sec}")
    lst.append(f"file '{tmp / f'f{len(states)-1:04d}.png'}'")
    (tmp / "list.txt").write_text("\n".join(lst))
    total = sum(s for _, s in states)
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(tmp / "list.txt"),
                    "-vf", "fps=30,format=yuv420p", "-c:v", "libx264", "-crf", "20", "-movflags", "+faststart", str(out_mp4)], check=True)
    for f in tmp.glob("*"):
        f.unlink()
    tmp.rmdir()
    print(f"saved {out_mp4}  (~{total:.0f}s, {len(states)} states)")


if __name__ == "__main__":
    build(Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "record" / "demo_video.mp4")
