# Recording the demo video (safe-for-Public checklist)

The submission video must be **under 3 minutes and publicly viewable**. These helpers make
the terminal safe to show (no account IDs, ARNs, username or hostname on camera) and verify
everything works before you hit record. The full shot-by-shot script is `../DEMO_SCRIPT.md`.

## One-time setup
- QuickTime (⌘⇧5) or any screen recorder, capturing a single terminal window.
- Terminal font large enough to read at 720p (16–18pt+). Dark theme reads best.
- Window ~1280×720 or larger.

## Steps

```bash
# 1. open a terminal, go to the repo, and load the recording environment
cd .../strands_decider_gate
source record/record_env.sh          # neutral prompt: "sre-demo ~/decider-gate $"
                                     # (optional) export AWS_PROFILE=... here, off-camera

# 2. in ANOTHER terminal, start the local decision model
strands-decider serve StrandsAgents/strands-decider-2B-qwen3.5-v1-2610 --port 8099

# 3. back in the recording shell, sanity-check (no AWS calls)
./record/precheck.sh                 # must say "ALL CLEAR"

# 4. start recording, then run (slowly, with narration):
python demo.py --slow                # four scenes: 1 allow, 3 blocks, each with a reason
python bench_compare.py              # the Decider-vs-Bedrock table (needs AWS_PROFILE)
#   if an AWS error ever echoes an identifier, run it through the backstop:
#   maskrun python bench_compare.py
```

## What's protected
- **Prompt** shows `sre-demo ~/decider-gate` — no real username, hostname, path, or git branch.
- **`maskrun <cmd>`** scrubs 12-digit account IDs, ARNs, and this user/host from a command's
  output — a backstop for the one risky moment (a Bedrock error on camera).
- **precheck** confirms the server is up, 34 tests pass, docs/bench JSON carry no identifiers,
  and times `demo.py` so you can budget the 3 minutes.

## On-camera don'ts
- Don't show the AWS console, `aws sts get-caller-identity`, `~/.aws/*`, or `serve.log`.
- Don't type `AWS_PROFILE=realname` on camera — set it before recording (step 1).
- Don't widen the window so other tabs/titles with the real hostname show.

## After recording
- Trim to **< 3:00**, burn in **English captions**.
- Watch it back once at full screen looking only for leaked identifiers.
- Upload **Public** (the rules say "publicly available"), put the link in the submission.
