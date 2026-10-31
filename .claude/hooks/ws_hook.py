#!/usr/bin/env python3
"""Entry point of the hooks (Claude Code and Codex). usage: ws_hook.py <sessionstart|prompt|pretool|stop> [--client claude|codex]
(the work is in ws/engine.py). Without --client, the environment variable CREATECODEBOX_CLIENT decides; nothing means claude.

If the engine can't even be loaded: pretool denies (exit 0), everything else exits 0 (a bug must not stop the user from typing).
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "ws"))


def client_arg(argv):
    """The value after --client (or --client=...), else None."""
    for i, a in enumerate(argv):
        if a == "--client" and i + 1 < len(argv):
            return argv[i + 1]
        if a.startswith("--client="):
            return a.split("=", 1)[1]
    return None


def main():
    kind = sys.argv[1] if len(sys.argv) > 1 else ""
    try:
        import engine
        return engine.hook_main(kind, client_arg(sys.argv[2:]))
    except BaseException as e:  # the engine itself could not be loaded or crashed
        if kind == "pretool":
            try:
                print(json.dumps({"hookSpecificOutput": {
                    "hookEventName": "PreToolUse", "permissionDecision": "deny",
                    "permissionDecisionReason": "CreateCodeBox: the workspace engine failed to load (%s). Stopped for safety." % type(e).__name__}}))
                sys.stdout.flush()
                return 0
            except BaseException:
                return 2
        return 0


if __name__ == "__main__":
    sys.exit(main())
