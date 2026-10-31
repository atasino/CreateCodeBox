"""Hook adapters: the part that knows one host's hook protocol (Claude Code, Codex).

An adapter answers these questions for ws/engine.py: where the workspace root is, how a hook input is read (and put in the
engine's shape), and what each answer looks like on stdout. The engine decides what to answer (gate, on_prompt, on_stop, ...).

Which adapter runs: `load(name)`. The name comes from `--client <name>` on the hook command, or the environment variable
CREATECODEBOX_CLIENT. Nothing (or anything unknown) means `claude`.
"""
import importlib

CLIENTS = ("claude", "codex")


def normalize_name(name):
    n = (name or "").strip().lower()
    return n if n in CLIENTS else "claude"


def load(name=None):
    """The adapter module for the client name (claude by default)."""
    return importlib.import_module("." + normalize_name(name), __name__)
