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


def table_frame(rows, cap, head, cols=(380, 420, 320)):
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    d.text((70, 60), head, font=F_HEAD, fill=(255, 255, 255))
    x0, y = 70, 150
    cols = list(cols)
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


def clean(line: str) -> str:
    return re.sub(r"\x1b\[\d+m", "", line)


def scene_states(lines, cap, holds):
    """Reveal one demo scene line by line; blank lines add no state. Returns [(image, seconds)]."""
    shown, out = [], []
    for i, ln in enumerate(lines):
        plain = clean(ln)
        if not plain.strip():
            continue
        for w in wrap_spans(parse_ansi(ln), 112):
            shown.append(w)
        key = "gate" if plain.strip().startswith("gate:") else "why" if plain.strip().startswith("why:") else "head" if i == 0 else "line"
        out.append((terminal_frame(shown[-24:], cap), holds[key]))
    out.append((terminal_frame(shown[-24:], cap), holds["end"]))
    return out


def agent_lines(path: Path):
    """The real Bedrock-driven agent transcript, reduced to the lines that tell the story."""
    raw = [clean(x) for x in path.read_text(encoding="utf-8").splitlines()]
    keep = []
    for ln in raw:
        if ln.startswith("INCIDENT:"):
            keep.append("\x1b[2mincident:\x1b[0m " + ln[len("INCIDENT: "):])
        elif ln.startswith("[gate]"):
            body = ln[len("[gate] "):]
            action, _, scores = body.partition("  cause~")
            keep.append("\x1b[2magent proposed:\x1b[0m " + action)
            keep.append("\x1b[2m  gate scores:\x1b[0m cause~" + scores)
        elif "guide back:" in ln:
            keep.append("gate: \x1b[31mBLOCK\x1b[0m " + ln.split("guide back: ", 1)[1])
    i = next((k for k, x in enumerate(raw) if "what the agent finally replied" in x), None)
    if i is not None:
        reply = [x.replace("**", "") for x in raw[i + 1:] if x.strip()][:4]
        keep.append("")
        keep.append("\x1b[1magent after the gate's reason:\x1b[0m")
        keep += ["  " + x for x in reply]
    return keep


VOICE = "Samantha"  # macOS built-in English voice; no cloud call, nothing leaves the machine
VOICE_RATE = 175    # words per minute


def narrate(marks, states, tmp):
    """Speak each marked group; stretch the group's last state if the speech is longer. Returns the audio file (or None)."""
    if not marks or subprocess.run(["which", "say"], capture_output=True).returncode != 0:
        return None
    bounds = [m[0] for m in marks] + [len(states)]
    parts = []
    for k, (start, text) in enumerate(marks):
        aiff = tmp / f"n{k}.aiff"
        subprocess.run(["say", "-v", VOICE, "-r", str(VOICE_RATE), "-o", str(aiff), text], check=True)
        dur = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(aiff)],
                                   capture_output=True, text=True, check=True).stdout)
        end = bounds[k + 1]
        group = sum(s for _, s in states[start:end])
        need = dur + 0.8  # leave a breath before the next group
        if need > group:
            im, sec = states[end - 1]
            states[end - 1] = (im, sec + (need - group))
            group = need
        wav = tmp / f"n{k}.wav"
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(aiff), "-ar", "44100", "-ac", "1",
                        "-af", f"apad=whole_dur={group:.3f}", "-t", f"{group:.3f}", str(wav)], check=True)
        parts.append(wav)
    lst = tmp / "narr.txt"
    lst.write_text("\n".join(f"file '{p}'" for p in parts))
    out = tmp / "narration.wav"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(lst), str(out)], check=True)
    return out


def build(out_mp4: Path):
    py = sys.executable
    demo = run([py, "demo.py"]).splitlines()
    sweep = run([py, "analysis.py", "sweep"]).splitlines()
    bench = json.load(open(ROOT / "bench_compare.json"))
    ho = json.load(open(ROOT / "bench_holdout.json"))["gate"]
    ind = json.load(open(ROOT / "evalkit" / "data" / "independent_results.json"))
    refund = json.load(open(ROOT / "evalkit" / "data" / "refund_results.json"))
    g, b = bench["gate"], bench["baseline"]
    runs = sorted((ROOT / "record" / "agent_runs").glob("run_*.txt"))
    blocked = sum(1 for p in runs if "blocked 1 of 1" in p.read_text(encoding="utf-8"))
    n_tests = int(re.search(r"(\d+) passed", subprocess.run([py, "-m", "pytest", "-q", "tests"], cwd=ROOT, capture_output=True, text=True).stdout).group(1))

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
    states = []
    marks = []  # (index of first state of a narrated group, spoken text)

    def mark(text):
        marks.append((len(states), text))

    mark("An AI agent that can act on your infrastructure is one confident wrong decision away from an outage. "
         "The danger is not that it cannot decide. It decides confidently, and wrong.")
    states.append((card_frame("DeciderGate", "An AI agent that can act on your infrastructure is one confident wrong decision away from an outage.",
                              "The danger is not that an agent cannot decide. It decides confidently, and wrong."), 7))
    mark("DeciderGate puts a calm second opinion in front of the agent. A small local Strands Decider two B model answers narrow, typed questions. "
         "Plain Python policy turns the answers into allow or block. The thresholds live in code, not in a prompt.")
    states.append((card_frame("The model classifies. The code decides.", "A local Strands Decider 2B answers narrow typed questions; plain-Python policy turns them into allow or block.",
                              "The thresholds live in code, not in a prompt.", big=False), 6))
    code_a = [('QUESTIONS = {', FG), ('    "cause":         Decider.choice("What is the most likely root cause ...", CAUSES),', FG),
              ('    "dep_saturated": Decider.noul("Is a downstream dependency saturated or failing?", ...),', FG),
              ('    "already_tried": Decider.noul("Was this same action already tried and it did not help?", ...),', FG), ("}", FG)]
    code_b = code_a + [("", FG), ("@dataclass(frozen=True)", DIM), ("class Policy:", FG),
                       ("    min_cause_prob: float = 0.45   # thresholds live here, not in the model", GOLD),
                       ("    repeat_prob:    float = 0.50", FG), ("    dep_block_prob: float = 0.50", FG)]
    capc = "gate.py: three narrow questions to the model, and a Policy of thresholds owned by the code."
    mark("Here is the whole idea. Three questions: what is the likely cause, is a dependency failing, was this already tried. "
         "And a Policy dataclass that holds every threshold.")
    states.append((terminal_frame([[(t, c)] for t, c in code_a], capc, title="rollback_gate/gate.py"), 4))
    states.append((terminal_frame([[(t, c)] for t, c in code_b], capc, title="rollback_gate/gate.py"), 5))

    holds = {"head": 1.0, "line": 1.5, "gate": 2.4, "why": 2.8, "end": 1.0}
    scene_say = [
        "Scene one. A deploy, then errors. A rollback is justified, so the gate allows it.",
        "Scene two. No deploy for three days; this is a marketing traffic surge. The agent still wants to roll back, and the gate blocks it, with a reason you can read.",
        "Scene three. It already rolled back and the errors persist. The gate will not let the agent repeat the same move.",
        "Scene four, the trap. The database is saturated, but the log reads like a bad deploy. A second question about dependencies catches it.",
    ]
    for sc, cap, say_ in zip(scenes[:4], caps[:4], scene_say):
        mark(say_)
        states += scene_states(sc, cap, holds)
    mark("Scene five. The same evidence twice. The first rollback is allowed. The second is blocked by a rule that spans actions, "
         "before the model is even asked.")
    shown = []
    for ln in scenes[4]:
        if not clean(ln).strip():
            continue
        shown += wrap_spans(parse_ansi(ln), 112)
        states.append((terminal_frame(shown[-24:], caps[4]), 4.0 if "attempt" in clean(ln) else 1.6))
    states.append((terminal_frame(shown[-24:], caps[4]), 1.5))

    # the real Bedrock-driven agent (non-deterministic LLM -> rendered from a saved, dated transcript)
    if runs:
        capa = (f"Amazon Bedrock (Claude Haiku 4.5) drives the Strands agent; the local Decider gates its tool calls. "
                f"In {blocked} of {len(runs)} recorded runs the agent reached for a remediation first and the gate sent it back.")
        title_a = "sre-demo ~/decider-gate $ python agent.py"
        mark(f"Now the real thing. Amazon Bedrock, Claude Haiku four point five, drives a Strands agent, and the local Decider gates its tool calls. "
             f"In {blocked} of {len(runs)} recorded runs the agent reached for scale out first, and the gate sent it back.")
        shown = []
        for i, ln in enumerate(agent_lines(runs[0])):
            shown += wrap_spans(parse_ansi(ln), 112)
            states.append((terminal_frame(shown[-24:], capa, title=title_a), 3.2 if i in (0, 2) else 2.0))
        states.append((terminal_frame(shown[-24:], capa, title=title_a), 5.0))

    ratio = b["latency_ms_median"] / g["latency_ms_median"]
    rows = [["", "DeciderGate (local)", "Bedrock Haiku 4.5"],
            ["accuracy (22 cases)", f"{g['accuracy']*100:.0f}%", f"{b['accuracy']*100:.0f}%"],
            ["latency (median)", f"~{g['latency_ms_median']:.0f} ms", f"~{b['latency_ms_median']:.0f} ms"],
            ["API cost / 22 cases", "$0", f"~${b['api_cost_usd']:.3f}"]]
    mark(f"Against a general LLM judge on Bedrock, the same accuracy on our golden set, about {ratio:.0f} times faster, and nothing billed per call, because the Decider runs locally.")
    states.append((table_frame(rows, f"Same accuracy on our golden set, about {ratio:.0f}x faster, nothing billed per call: the Decider runs locally.",
                               "Decider gate vs a general LLM judge, same incidents"), 9))

    gi, bi = ind["gate"], ind["baseline"]
    rows2 = [["set", "cases", "gate accuracy"],
             ["golden (we tuned on it)", f"{g['n']}", f"{g['accuracy']*100:.1f}%"],
             ["held-out (written by us)", f"{ho['n']}", f"{ho['accuracy']*100:.1f}%"],
             ["independent (Nova Pro, Llama-verified)", f"{gi['n']}", f"{gi['accuracy']*100:.1f}%"],
             ["second domain: support refunds", f"{refund['n']}", f"{refund['accuracy']*100:.1f}%"]]
    mark(f"But we tuned on that set, so we also tested on cases we did not write. Amazon Nova Pro wrote them, and Llama verified the labels. "
         f"The gate scores {gi['accuracy']*100:.1f} percent there, not 100. A human then checked twenty of the cases. "
         "The same gate also guards a second domain: support refunds.")
    states.append((table_frame(rows2, f"On cases we did not write the gate is not 100%: {gi['accuracy']*100:.1f}% (Haiku {bi['accuracy']*100:.1f}%), about "
                               f"{bi['latency_ms_median']/gi['latency_ms_median']:.0f}x faster. The same gate also guards a second domain.",
                               "Honest evaluation on independent data", cols=(620, 200, 330)), 13))

    mark("And the main threshold sits on a plateau: every value from point three five to point five zero scores 100 percent on the tuned sets.")
    sw = [clean(ln) for ln in sweep if ln.strip()]
    states.append((terminal_frame([w for t in sw for w in wrap_spans([(t, FG)], 112)],
                                  "Sweeping the main threshold: every value from 0.35 to 0.50 scores 100% on the tuned sets. A plateau, not a knife edge.",
                                  title="python analysis.py sweep"), 6))
    mark("DeciderGate is open source under Apache two point zero. Lift the pattern into your own agent. Evidence first, then action.")
    states.append((card_frame("Open source, Apache-2.0", f"{n_tests} unit tests · two domains · independent evaluation · temporal policy · audit log. Lift the pattern into your own agent.",
                              "#strands-decider-2b   #guardrails", big=False), 7))

    tmp = ROOT / "record" / "_frames"
    tmp.mkdir(exist_ok=True)
    narr = narrate(marks, states, tmp)
    lst = []
    for i, (im, sec) in enumerate(states):
        p = tmp / f"f{i:04d}.png"
        im.save(p)
        lst.append(f"file '{p}'\nduration {sec}")
    lst.append(f"file '{tmp / f'f{len(states)-1:04d}.png'}'")
    (tmp / "list.txt").write_text("\n".join(lst))
    total = sum(s for _, s in states)
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(tmp / "list.txt")]
    if narr:
        cmd += ["-i", str(narr), "-c:a", "aac", "-b:a", "128k", "-shortest"]
    subprocess.run(cmd + ["-vf", "fps=30,format=yuv420p", "-c:v", "libx264", "-crf", "20", "-movflags", "+faststart", str(out_mp4)], check=True)
    for f in tmp.glob("*"):
        f.unlink()
    tmp.rmdir()
    print(f"saved {out_mp4}  (~{total:.0f}s, {len(states)} states)")


if __name__ == "__main__":
    build(Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "record" / "demo_video.mp4")
