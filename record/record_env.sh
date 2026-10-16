#!/usr/bin/env zsh
# Clean, neutral environment for screen-recording the demo.
#
# Source this in the terminal you will record, THEN start the Decider server and run the
# demo in the same shell:
#
#   source record/record_env.sh
#   python demo.py --slow
#   AWS_PROFILE=<profile> python bench_compare.py
#
# What it does:
#   - neutral prompt: no username, no hostname, no path, no git branch -> nothing to mask.
#   - a big, legible window title.
#   - a `maskrun` helper that runs a command and scrubs 12-digit account IDs and ARNs from
#     its output, as a backstop in case an AWS error echoes an identifier on camera.
#
# It changes only THIS shell. It does not touch ~/.zshrc or any global config.

# Neutral two-line prompt. "sre-demo" is a stage name, not the real host/user.
export PROMPT=$'%F{green}sre-demo%f %F{blue}~/decider-gate%f\n$ '
export RPROMPT=""          # clear anything on the right (clock, status, etc.)

# Readable window/tab title for the recording.
print -Pn "\e]0;DeciderGate demo\a"

# Keep the AWS profile out of the visible prompt; set it once here if you like:
#   export AWS_PROFILE=your-profile   # (uncomment and edit; stays in-shell, off-camera)

# maskrun <cmd...> : run a command, hide account IDs / ARNs / this user & host from stdout.
maskrun() {
  "$@" 2>&1 | sed -E \
    -e 's/[0-9]{12}/<ACCOUNT_ID>/g' \
    -e 's#arn:aws[^ "'"'"']*#<ARN>#g' \
    -e "s/${USER}/<user>/g" \
    -e "s/$(hostname -s)/<host>/g"
}

echo "recording env ready. prompt is neutral; use 'maskrun <cmd>' to scrub IDs on camera."
echo "sanity-check first:  ./record/precheck.sh"
