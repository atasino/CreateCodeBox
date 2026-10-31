#!/bin/sh
# CreateCodeBox commands (Mac, Linux, Git Bash on Windows). The work is in ws/engine.py.
# usage: bash ws/bin/ws.sh status | list | select | new | lint | render | open | lang | schedule-init | mark | st ... | task add|set|date|none | tasks [gantt] | doctor | version | update
HERE="$(cd "$(dirname "$0")" && pwd)"
export CLAUDE_PROJECT_DIR="${CLAUDE_PROJECT_DIR:-$(cd "$HERE/../.." && pwd)}"
PYTHONUTF8=1
export PYTHONUTF8
if command -v python3 >/dev/null 2>&1; then
  exec python3 "$HERE/../engine.py" "$@"
elif command -v python >/dev/null 2>&1; then
  exec python "$HERE/../engine.py" "$@"
elif command -v py >/dev/null 2>&1; then
  exec py -3 "$HERE/../engine.py" "$@"
fi
echo "Python 3 was not found. Install Python 3.8 or newer from python.org, open a new terminal, and run this again." >&2
echo "Python 3 が見つかりません。python.org から Python 3.8 以上を入れて、ターミナルを開き直してください。" >&2
exit 1
