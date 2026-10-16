#!/usr/bin/env zsh
# Pre-recording sanity check. Run from the repo root:  ./record/precheck.sh
# Fails loudly if anything that would ruin a take is wrong. No AWS calls.
set -u
zmodload zsh/datetime 2>/dev/null  # for $EPOCHREALTIME
cd "${0:A:h}/.." || exit 1
PY=.venv/bin/python
ok=1

say()  { print -P "%F{blue}--%f $1"; }
pass() { print -P "   %F{green}ok%f   $1"; }
fail() { print -P "   %F{red}FAIL%f $1"; ok=0; }

say "1. Decider server on :8099"
if curl -s --max-time 5 http://127.0.0.1:8099/health | grep -q '"status":"ok"'; then
  pass "server answering"
else
  fail "no healthy server -> run: strands-decider serve <checkpoint> --port 8099"
fi

say "2. tests green (model & Bedrock mocked, no network)"
if $PY -m pytest tests/ -q >/tmp/decider_precheck_tests.txt 2>&1; then
  pass "$(tail -1 /tmp/decider_precheck_tests.txt)"
else
  fail "tests failing -> see /tmp/decider_precheck_tests.txt"
fi

say "3. no secrets in files that may appear on camera"
HITS=$(grep -rnE '[0-9]{12}|arn:aws' README.md ARTICLE.md PATTERN_NOTES.md DEMO_SCRIPT.md \
        bench_compare.json bench_holdout.json 2>/dev/null \
        | grep -vE 'ACCOUNT_ID|<ARN>|placeholder' || true)
if [[ -z "$HITS" ]]; then
  pass "no account IDs / ARNs in docs or bench output"
else
  fail "possible identifier on camera:"; print "$HITS"
fi

say "4. neutral prompt (only visible if you ran this inside the recording shell)"
if [[ "${PROMPT:-}" == *sre-demo* ]]; then
  pass "recording prompt active (no user/host visible)"
else
  print -P "   %F{yellow}note%f record in a shell where you ran: source record/record_env.sh"
  print -P "        (this check runs in its own shell, so it can't see that prompt — not a failure)"
fi

say "5. demo runtime (keep final cut < 3:00)"
start=$EPOCHREALTIME
$PY demo.py >/dev/null 2>&1 && \
  printf "   \033[32mok\033[0m   demo.py ran in %.1fs (add narration/pauses for the real take)\n" \
    "$((EPOCHREALTIME - start))" \
  || fail "demo.py errored (server down?)"

echo
if [[ $ok -eq 1 ]]; then
  print -P "%F{green}ALL CLEAR — safe to record.%f  Suggested: python demo.py --slow ; python bench_compare.py"
else
  print -P "%F{red}NOT READY — fix the FAILs above before recording.%f"
  exit 1
fi
