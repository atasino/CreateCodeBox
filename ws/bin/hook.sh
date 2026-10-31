#!/bin/sh
# CreateCodeBox hook launcher (POSIX sh). Finds Python 3.8 or newer and runs .claude/hooks/ws_hook.py with it.
# usage: sh ws/bin/hook.sh <sessionstart|prompt|pretool|stop> [--client claude|codex]
case "$0" in
  */*) here=${0%/*} ;;
  *) here=. ;;
esac
dir=$(cd "$here" && pwd)
ok='import sys; sys.exit(0 if sys.version_info>=(3,8) else 1)'
PY=
if command -v python3 >/dev/null 2>&1 && python3 -c "$ok" >/dev/null 2>&1; then
  PY=python3
elif command -v python >/dev/null 2>&1 && python -c "$ok" >/dev/null 2>&1; then
  PY=python
elif command -v py >/dev/null 2>&1 && py -3 -c "$ok" >/dev/null 2>&1; then
  PY="py -3"
fi
if [ -z "$PY" ]; then
  echo "CreateCodeBox needs Python 3.8 or newer. Install it from python.org and open a new terminal." >&2
  echo "CreateCodeBox は Python 3.8 以上が必要です。python.org から入れて、ターミナルを開き直してください。" >&2
  exit 2
fi
PYTHONUTF8=1
export PYTHONUTF8
# shellcheck disable=SC2086
exec $PY "$dir/../../.claude/hooks/ws_hook.py" "$@"
