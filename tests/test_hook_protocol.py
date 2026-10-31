#!/usr/bin/env python3
"""Characterization tests of the hook protocol: what Claude Code sends in, and the exact answer it gets back.

They fix the behaviour at the edge of ws/engine.py: where the workspace root comes from (CLAUDE_PROJECT_DIR),
how the hook input is read, and the JSON shape of every answer (deny, block, context, nothing).
The decisions themselves (gate, on_prompt, on_stop) are covered by tests/test_engine.py.

Usage (from the repository root): python3 -I tests/test_hook_protocol.py
Exit code 0 when every check passes, 1 otherwise.
"""
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import test_engine as base  # noqa: E402  (Env, check, and an empty HOME for the whole run)
from test_engine import Env, check, fake_secret  # noqa: E402

import engine  # noqa: E402  (the repository's ws/engine.py, put on sys.path by test_engine)
import lang  # noqa: E402

PREFIX = "CreateCodeBox: "


def T_en(key, **kw):
    lang.use("en")
    return engine.T(key, **kw)


def raw(e, kind, data, env=None, cwd=None, via_sh=False):
    """Run one hook with raw bytes on stdin. Returns (exit code, stdout bytes)."""
    if via_sh:
        cmd = ["/bin/sh", os.path.join(e.root, "ws", "bin", "hook.sh"), kind]
    else:
        cmd = [sys.executable, "-I", os.path.join(e.root, ".claude", "hooks", "ws_hook.py"), kind]
    p = subprocess.run(cmd, input=data, capture_output=True, env=env or e.env, cwd=cwd or e.root)
    return p.returncode, p.stdout


def ev(e, kind, event, **kw):
    return raw(e, kind, json.dumps(event).encode("utf-8"), **kw)


def one_json(out):
    """The answer must be exactly one JSON line that ends with a newline. Returns the object, or None."""
    if not out.endswith(b"\n") or out.count(b"\n") != 1:
        return None
    try:
        return json.loads(out.decode("utf-8"))
    except ValueError:
        return None


def deny_shape(o):
    return (isinstance(o, dict) and set(o) == {"hookSpecificOutput"}
            and set(o["hookSpecificOutput"]) == {"hookEventName", "permissionDecision", "permissionDecisionReason"}
            and o["hookSpecificOutput"]["hookEventName"] == "PreToolUse"
            and o["hookSpecificOutput"]["permissionDecision"] == "deny"
            and o["hookSpecificOutput"]["permissionDecisionReason"].startswith(PREFIX))


def reason_of(o):
    return o["hookSpecificOutput"]["permissionDecisionReason"]


def context_shape(o, name):
    return (isinstance(o, dict) and set(o) == {"hookSpecificOutput"}
            and set(o["hookSpecificOutput"]) == {"hookEventName", "additionalContext"}
            and o["hookSpecificOutput"]["hookEventName"] == name
            and isinstance(o["hookSpecificOutput"]["additionalContext"], str))


def run_patched(e, kind, code, data=b"{}", env=None):
    """Load the engine of the copy, apply `code` (monkeypatches), and run hook_main(kind)."""
    ws = os.path.join(e.root, "ws")
    src = "import sys; sys.path.insert(0, %r); import engine\n%s\nsys.exit(engine.hook_main(%r))" % (ws, code, kind)
    p = subprocess.run([sys.executable, "-I", "-c", src], input=data, capture_output=True, env=env or e.env, cwd=e.root)
    return p.returncode, p.stdout


def test_pretool():
    e = Env()
    try:
        rc, out = ev(e, "pretool", {"tool_name": "Bash", "tool_input": {"command": "ls"}, "cwd": e.root})
        check("protocol: pretool allow = exit 0 and no output at all", rc == 0 and out == b"", (rc, out[:120]))

        event = {"tool_name": "Write", "tool_input": {"file_path": e.p("README.md"), "content": "x"}, "cwd": e.root}
        rc, out = ev(e, "pretool", event)
        o = one_json(out)
        check("protocol: pretool deny = exit 0, one JSON line, exactly hookEventName/permissionDecision/permissionDecisionReason",
              rc == 0 and deny_shape(o), (rc, out[:200]))
        lang.use("en")
        want = engine.gate(os.path.realpath(e.root), event)  # the hook gets the real path from project_root()
        check("protocol: deny reason = 'CreateCodeBox: ' + the reason from gate()", o is not None and want and reason_of(o) == PREFIX + want,
              (o and reason_of(o)[:120], want and want[:120]))

        bad_input = PREFIX + T_en("deny.hook_input")
        for label, data in (("not JSON", b"this is not json"), ("empty", b""), ("a JSON list", b"[]"), ("a JSON string", b"\"x\""),
                            ("bytes that are not UTF-8", b"\xff\xfe\xfd")):
            rc, out = raw(e, "pretool", data)
            o = one_json(out)
            check("protocol: pretool with %s on stdin = deny (fail-closed) with the 'hook input' reason" % label,
                  rc == 0 and deny_shape(o) and reason_of(o) == bad_input, (rc, out[:200]))

        rc, out = run_patched(e, "pretool", "def boom(*a, **k): raise RuntimeError('x')\nengine.gate = boom",
                              json.dumps({"tool_name": "Bash", "tool_input": {"command": "ls"}}).encode())
        o = one_json(out)
        check("protocol: an exception in gate() = deny with the 'hook error' reason naming the exception",
              rc == 0 and deny_shape(o) and reason_of(o) == PREFIX + T_en("deny.hook_error", err="RuntimeError"), (rc, out[:200]))

        rc, out = run_patched(e, "pretool", "def boom(*a, **k): raise ValueError('x')\nengine.get_lang = boom")
        o = one_json(out)
        check("protocol: an exception before the dispatch (pretool) = deny, exit 0",
              rc == 0 and deny_shape(o) and reason_of(o) == PREFIX + T_en("deny.hook_error", err="ValueError"), (rc, out[:200]))

        env = dict(e.env, CREATECODEBOX_LANG="ja")
        rc, out = ev(e, "pretool", event, env=env)
        o = one_json(out)
        txt = out.decode("utf-8", "replace")
        check("protocol: the JSON is written with ensure_ascii=False (Japanese stays as UTF-8, no \\u escapes)",
              rc == 0 and deny_shape(o) and "\\u" not in txt and base.CJK_ALL.search(txt) is not None, txt[:160])

        rc1, out1 = ev(e, "pretool", event, via_sh=True)
        check("protocol: hook.sh gives the same bytes as ws_hook.py (deny)", rc1 == 0 and out1 == ev(e, "pretool", event)[1], (rc1, out1[:120]))
    finally:
        e.close()


def test_session_and_prompt():
    e = Env()
    try:
        rc, out = ev(e, "sessionstart", {"source": "startup"})
        o = one_json(out)
        check("protocol: sessionstart = exit 0, one JSON line, exactly hookEventName 'SessionStart' + additionalContext",
              rc == 0 and context_shape(o, "SessionStart") and "[CreateCodeBox" in o["hookSpecificOutput"]["additionalContext"], (rc, out[:200]))

        rc, out = raw(e, "sessionstart", b"not json")
        o = one_json(out)
        check("protocol: sessionstart with unreadable stdin still answers with the context (input taken as {})",
              rc == 0 and context_shape(o, "SessionStart") and "[CreateCodeBox" in o["hookSpecificOutput"]["additionalContext"], (rc, out[:200]))

        rc, out = ev(e, "prompt", {"prompt": "make a small tool"})
        o = one_json(out)
        check("protocol: prompt = exit 0, one JSON line, exactly hookEventName 'UserPromptSubmit' + additionalContext that starts with 'Reply in: '",
              rc == 0 and context_shape(o, "UserPromptSubmit") and o["hookSpecificOutput"]["additionalContext"].startswith("Reply in: "), (rc, out[:200]))

        rc, out = raw(e, "prompt", b"[1, 2]")
        o = one_json(out)
        check("protocol: prompt with a non-object JSON is taken as {} and still gets the context", rc == 0 and context_shape(o, "UserPromptSubmit"), (rc, out[:200]))

        key = fake_secret("ghp")
        rc, out = ev(e, "prompt", {"prompt": "my key is " + key})
        o = one_json(out)
        check("protocol: a key in the prompt = exactly decision 'block' + reason + hookSpecificOutput{UserPromptSubmit, suppressOriginalPrompt: true}",
              rc == 0 and isinstance(o, dict) and set(o) == {"decision", "reason", "hookSpecificOutput"} and o["decision"] == "block"
              and o["reason"] == T_en("block.key_in_prompt")
              and o["hookSpecificOutput"] == {"hookEventName": "UserPromptSubmit", "suppressOriginalPrompt": True}, (rc, out[:240]))
        check("protocol: the blocked key is not in the answer", key.encode() not in out)

        rc, out = run_patched(e, "prompt", "def boom(*a, **k): raise RuntimeError('x')\nengine.on_prompt = boom", b'{"prompt": "hi"}')
        o = one_json(out)
        check("protocol: an exception in on_prompt = exit 0 and exactly the warning context ('Reply in: en' + the hook error line)",
              rc == 0 and context_shape(o, "UserPromptSubmit")
              and o["hookSpecificOutput"]["additionalContext"] == "Reply in: en\n" + T_en("warn.hook_error", err="RuntimeError"), (rc, out[:240]))

        rc, out = run_patched(e, "sessionstart", "def boom(*a, **k): raise RuntimeError('x')\nengine.on_session_start = boom")
        check("protocol: an exception in on_session_start = exit 0 and no output", rc == 0 and out == b"", (rc, out[:120]))

        rc, out = ev(e, "nope", {"x": 1})
        check("protocol: an unknown hook kind = exit 0 and no output", rc == 0 and out == b"", (rc, out[:120]))
        rc, out = raw(e, "", b"{}")
        check("protocol: no hook kind = exit 0 and no output", rc == 0 and out == b"", (rc, out[:120]))
    finally:
        e.close()


def test_stop_shape():
    e = Env()
    try:
        rc, out = ev(e, "stop", {"last_assistant_message": "Hello"})
        check("protocol: stop with nothing to say = exit 0 and no output", rc == 0 and out == b"", (rc, out[:120]))
        rc, out = raw(e, "stop", b"not json")
        check("protocol: stop with unreadable stdin = exit 0 and no output", rc == 0 and out == b"", (rc, out[:120]))
        e.hook("sessionstart", {"source": "startup"})
        e.prompt("make a thing")
        e.run(["new", "a", "--name", "A", "--quote", "make a thing"])
        e.prompt("another")
        e.run(["new", "b", "--name", "B", "--quote", "another"])
        e.hook("sessionstart", {"source": "startup"})
        e.prompt("hi")
        rc, out = ev(e, "stop", {"last_assistant_message": "Sure, I can help with many things."})
        o = one_json(out)
        check("protocol: stop block = exit 0, one JSON line, exactly {decision: 'block', reason: <the stop.ask text>}",
              rc == 0 and isinstance(o, dict) and set(o) == {"decision", "reason"} and o["decision"] == "block" and o["reason"] == T_en("stop.ask"),
              (rc, out[:200]))
        rc, out = run_patched(e, "stop", "def boom(*a, **k): raise RuntimeError('x')\nengine.on_stop = boom",
                              json.dumps({"last_assistant_message": "Sure."}).encode())
        check("protocol: an exception in on_stop = exit 0 and no output", rc == 0 and out == b"", (rc, out[:120]))
    finally:
        e.close()


def test_project_root():
    e = Env()
    saved = os.environ.get("CLAUDE_PROJECT_DIR")
    cwd0 = os.getcwd()
    try:
        link = os.path.join(e.tmp, "link_to_ws")
        os.symlink(e.root, link)
        os.environ["CLAUDE_PROJECT_DIR"] = link
        check("protocol: project_root() = the real path of CLAUDE_PROJECT_DIR (a symlink is resolved)",
              engine.project_root() == os.path.realpath(e.root), engine.project_root())
        os.environ.pop("CLAUDE_PROJECT_DIR", None)
        os.chdir(e.root)
        check("protocol: project_root() = the real path of the current folder when CLAUDE_PROJECT_DIR is not set",
              engine.project_root() == os.path.realpath(e.root), engine.project_root())
        os.environ["CLAUDE_PROJECT_DIR"] = ""
        check("protocol: an empty CLAUDE_PROJECT_DIR counts as not set", engine.project_root() == os.path.realpath(e.root), engine.project_root())
        os.chdir(cwd0)

        elsewhere = os.path.join(e.tmp, "elsewhere")
        os.makedirs(elsewhere)
        rc, out = ev(e, "sessionstart", {"source": "startup"}, cwd=elsewhere)
        o = one_json(out)
        check("protocol: the hooks use CLAUDE_PROJECT_DIR, not the current folder",
              rc == 0 and context_shape(o, "SessionStart") and "[CreateCodeBox" in o["hookSpecificOutput"]["additionalContext"], (rc, out[:160]))
        env = dict(e.env)
        env.pop("CLAUDE_PROJECT_DIR", None)
        rc, out = ev(e, "pretool", {"tool_name": "Write", "tool_input": {"file_path": e.p("README.md"), "content": "x"}, "cwd": e.root}, env=env)
        check("protocol: without CLAUDE_PROJECT_DIR the hooks use the current folder (deny still works)", rc == 0 and deny_shape(one_json(out)), (rc, out[:160]))
        env_link = dict(e.env, CLAUDE_PROJECT_DIR=link)
        rc, out = ev(e, "pretool", {"tool_name": "Write", "tool_input": {"file_path": e.p("README.md"), "content": "x"}, "cwd": e.root}, env=env_link)
        check("protocol: with CLAUDE_PROJECT_DIR as a symlink, a protected file under the real path is still denied", rc == 0 and deny_shape(one_json(out)), (rc, out[:160]))

        p = subprocess.run(["/bin/sh", os.path.join(e.root, "ws", "bin", "ws.sh"), "status"], capture_output=True, text=True, env=env, cwd=elsewhere)
        check("protocol: ws.sh sets CLAUDE_PROJECT_DIR itself, so status works from another folder", p.returncode == 0 and "R0" in p.stdout, (p.returncode, p.stdout[:120], p.stderr[:120]))
    finally:
        os.chdir(cwd0)
        if saved is None:
            os.environ.pop("CLAUDE_PROJECT_DIR", None)
        else:
            os.environ["CLAUDE_PROJECT_DIR"] = saved
        e.close()


def test_adapter():
    """ws/adapters/claude.py holds the Claude Code side; the engine's entry functions go through it."""
    import inspect
    import io
    from adapters import claude as ad
    check("adapter: engine uses ws/adapters/claude.py", engine.ADAPTER is ad and ad.NAME == "claude")
    check("adapter: deny() = the PreToolUse deny shape with the CreateCodeBox prefix",
          ad.deny("r") == {"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny", "permissionDecisionReason": PREFIX + "r"}}
          and engine.deny_json("r") == ad.deny("r"))
    check("adapter: stop_block() = {decision: block, reason}", ad.stop_block("r") == {"decision": "block", "reason": "r"})
    check("adapter: prompt_block() = block + suppressOriginalPrompt",
          ad.prompt_block("r") == {"decision": "block", "reason": "r", "hookSpecificOutput": {"hookEventName": "UserPromptSubmit", "suppressOriginalPrompt": True}})
    check("adapter: context() names the event by hook kind",
          ad.context("sessionstart", "t") == {"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": "t"}}
          and ad.context("prompt", "t") == {"hookSpecificOutput": {"hookEventName": "UserPromptSubmit", "additionalContext": "t"}})
    check("adapter: read_event() parses JSON, and gives None for text that is not JSON",
          ad.read_event(io.StringIO('{"a": 1}')) == {"a": 1} and ad.read_event(io.StringIO("nope")) is None and ad.read_event(io.StringIO("")) is None)
    entry = inspect.getsource(engine.hook_main) + inspect.getsource(engine._hook_dispatch)
    left = [w for w in ("hookSpecificOutput", "hookEventName", "CLAUDE_PROJECT_DIR", "json.load", "json.dumps", "\"decision\"") if w in entry]
    check("adapter: hook_main and _hook_dispatch no longer hold the protocol (no JSON shapes, no CLAUDE_PROJECT_DIR, no stdin parsing)", not left, left)
    check("adapter: engine.py does not read CLAUDE_PROJECT_DIR (only the adapter does)", "CLAUDE_PROJECT_DIR" not in inspect.getsource(engine),
          "engine.py still names it")


def main():
    for fn in (test_pretool, test_session_and_prompt, test_stop_shape, test_project_root, test_adapter):
        try:
            fn()
        except Exception as ex:  # a test that crashes counts as a failure, and the rest still run
            import traceback
            traceback.print_exc()
            check("%s: stopped with an exception" % fn.__name__, False, repr(ex))
    print("\n%d PASS / %d FAIL" % (len(base.PASS), len(base.FAIL)))
    sys.exit(1 if base.FAIL else 0)


if __name__ == "__main__":
    main()
