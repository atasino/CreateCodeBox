"""Codex hook protocol (standard library only). Source: docs/codex-notes.md.

What is here: the workspace root, how the hook input is read and put in the engine's shape, the JSON shape of each answer.
What is not here: any decision. The engine calls gate(), on_prompt(), on_stop() and on_session_start().

Hook kinds (the argument of ws_hook.py): sessionstart, prompt, pretool, stop. Selected with `--client codex`
or CREATECODEBOX_CLIENT=codex.
"""
import json
import os
import shlex
import sys

NAME = "codex"
REASON_PREFIX = "CreateCodeBox: "
EVENT_NAMES = {"sessionstart": "SessionStart", "prompt": "UserPromptSubmit", "pretool": "PreToolUse", "stop": "Stop"}
# Names Codex may give to its shell tool. The engine knows one name for it: Bash.
SHELL_TOOLS = {"bash", "shell", "local_shell", "exec_command", "shell_command", "container.exec"}


def project_root():
    """The workspace root. Codex sets no project-folder variable for hooks (its cwd can be a subfolder), so the root is
    where this engine lives: CREATECODEBOX_ROOT if set, else two folders above ws/adapters/. Always the real path."""
    env = os.environ.get("CREATECODEBOX_ROOT")
    if env:
        return os.path.realpath(env)
    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.realpath(os.path.join(here, "..", ".."))


def read_event(stream=None):
    """The hook input as parsed JSON, or None if it cannot be read or parsed. None and non-objects are 'unreadable' for the engine."""
    try:
        return normalize_event(json.load(sys.stdin if stream is None else stream))
    except (ValueError, AttributeError, OSError):
        return None


def normalize_event(ev):
    """Put a Codex hook input in the shape the engine reads: a shell tool is `Bash` with tool_input.command a string.
    apply_patch stays `apply_patch` (tool_input.command is the patch text). Anything else is left as it is."""
    if not isinstance(ev, dict):
        return ev
    name = ev.get("tool_name")
    ti = ev.get("tool_input")
    if isinstance(name, str) and name.lower() in SHELL_TOOLS and isinstance(ti, dict):
        cmd = ti.get("command", ti.get("cmd"))
        if isinstance(cmd, list):
            cmd = shlex.join(str(x) for x in cmd)
        ev = dict(ev, tool_name="Bash", tool_input=dict(ti, command=cmd if isinstance(cmd, str) else ""))
    return ev


def write(obj):
    """One JSON line on stdout, UTF-8 text kept as is (no \\u escapes)."""
    print(json.dumps(obj, ensure_ascii=False))
    sys.stdout.flush()


def deny(reason):
    """PreToolUse: do not run the tool; the reason goes to the model."""
    return {"hookSpecificOutput": {"hookEventName": EVENT_NAMES["pretool"], "permissionDecision": "deny",
                                   "permissionDecisionReason": REASON_PREFIX + reason}}


def stop_block(reason):
    """Stop: Codex starts a new turn with the reason as the prompt."""
    return {"decision": "block", "reason": reason}


def prompt_block(reason):
    """UserPromptSubmit: block the message (used when it contains a key)."""
    return {"decision": "block", "reason": reason}


def context(kind, text):
    """SessionStart / UserPromptSubmit: text added to the model's context."""
    return {"hookSpecificOutput": {"hookEventName": EVENT_NAMES[kind], "additionalContext": text}}
