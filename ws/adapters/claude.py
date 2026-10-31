"""Claude Code hook protocol (standard library only).

What is here: the workspace root (CLAUDE_PROJECT_DIR), how the hook input is read from stdin,
the JSON shape of each answer, and how it is written. What is not here: any decision.
The engine calls gate(), on_prompt(), on_stop() and on_session_start() and passes their plain results to these builders.

Hook kinds (the argument of ws_hook.py): sessionstart, prompt, pretool, stop.
"""
import json
import os
import sys

NAME = "claude"
REASON_PREFIX = "CreateCodeBox: "
EVENT_NAMES = {"sessionstart": "SessionStart", "prompt": "UserPromptSubmit", "pretool": "PreToolUse", "stop": "Stop"}


def project_root():
    """The workspace root: CLAUDE_PROJECT_DIR (set by Claude Code, and by ws/bin/ws.sh for commands), else the current folder.
    Always the real path, so that a symlinked folder and its target are the same place."""
    return os.path.realpath(os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd())


def read_event(stream=None):
    """The hook input as parsed JSON, or None if it cannot be read or parsed.
    The engine treats None (and anything that is not an object) as unreadable: pretool denies, the others take it as {}."""
    try:
        return json.load(sys.stdin if stream is None else stream)
    except (ValueError, AttributeError, OSError):
        return None


def normalize_event(ev):
    """Claude Code's input is already in the engine's shape."""
    return ev


def write(obj):
    """One JSON line on stdout, UTF-8 text kept as is (no \\u escapes)."""
    print(json.dumps(obj, ensure_ascii=False))
    sys.stdout.flush()


def deny(reason):
    """PreToolUse: stop the tool call and show the reason."""
    return {"hookSpecificOutput": {"hookEventName": EVENT_NAMES["pretool"], "permissionDecision": "deny",
                                   "permissionDecisionReason": REASON_PREFIX + reason}}


def stop_block(reason):
    """Stop: do not stop yet; Claude gets the reason and goes on."""
    return {"decision": "block", "reason": reason}


def prompt_block(reason):
    """UserPromptSubmit: block the message (used when it contains a key). The reason is the text for the user."""
    return {"decision": "block", "reason": reason,
            "hookSpecificOutput": {"hookEventName": EVENT_NAMES["prompt"], "suppressOriginalPrompt": True}}


def context(kind, text):
    """SessionStart / UserPromptSubmit: text added to Claude's context for this turn."""
    return {"hookSpecificOutput": {"hookEventName": EVENT_NAMES[kind], "additionalContext": text}}
