#!/usr/bin/env python3
"""Tests for the Codex side: the apply_patch gate (it also protects Claude Code), the unknown-tool rule, the Codex adapter,
the client selection, the Codex-only warnings, and the generated files (tools/gen_codex.py --check).

Usage (from the repository root): python3 -I tests/test_codex.py
Exit code 0 when every check passes, 1 otherwise. Standard library only. HOME is an empty temporary folder (see test_engine.py).
"""
import io
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import test_engine as base  # noqa: E402  (Env, check, build_to_run, fake_secret; an empty HOME for the whole run)
from test_engine import Env, check, build_to_run, fake_secret  # noqa: E402

import engine  # noqa: E402
import lang  # noqa: E402
from adapters import codex as CX  # noqa: E402

PREFIX = "CreateCodeBox: "
DOTENV = "." + "env"  # written in pieces: some tools stop on a plain command text that shows this file


def patch(*blocks):
    return "*** Begin Patch\n" + "\n".join(blocks) + "\n*** End Patch"


def add(path, *lines):
    return "*** Add File: %s\n%s" % (path, "\n".join("+" + l for l in lines))


def upd(path, old="a", new="b"):
    return "*** Update File: %s\n@@\n-%s\n+%s" % (path, old, new)


def dele(path):
    return "*** Delete File: %s" % path


def move(src, dst):
    return "*** Update File: %s\n*** Move to: %s\n@@\n-a\n+b" % (src, dst)


class CodexEnv(Env):
    """The same copy of the workspace, but the hooks are started the way Codex starts them: --client codex, no CLAUDE_PROJECT_DIR."""
    def __init__(self):
        Env.__init__(self)
        self.env.pop("CLAUDE_PROJECT_DIR", None)

    def chook(self, kind, event, cwd=None):
        cmd = [sys.executable, "-I", os.path.join(self.root, ".claude", "hooks", "ws_hook.py"), kind, "--client", "codex"]
        p = subprocess.run(cmd, input=json.dumps(event).encode("utf-8"), capture_output=True, env=self.env, cwd=cwd or self.root)
        return p.returncode, p.stdout.decode("utf-8", "replace")

    def _pre(self, name, ti, cwd=None):
        rc, out = self.chook("pretool", {"hook_event_name": "PreToolUse", "tool_name": name, "tool_input": ti, "cwd": cwd or self.root,
                                         "session_id": "s", "turn_id": "t", "tool_use_id": "u"})
        assert rc == 0, (rc, out)
        return json.loads(out)["hookSpecificOutput"]["permissionDecisionReason"] if out.strip() else None

    def ap(self, text, cwd=None):
        """apply_patch through the Codex hook. Returns the deny reason, or None when allowed."""
        return self._pre("apply_patch", {"command": text}, cwd)

    def sh(self, cmd):
        return self._pre("Bash", {"command": cmd})

    def tool(self, name, **ti):
        return self._pre(name, ti)


def test_patch_parser():
    ok, err = engine.parse_patch(patch(add("a.txt", "x", "y"), upd("b.txt"), dele("c.txt"), move("d.txt", "e.txt")))
    check("codex: parse_patch reads Add / Update / Delete / Move to (every path, in order)",
          ok is not None and [(x["op"], x["path"]) for x in ok] == [("add", "a.txt"), ("update", "b.txt"), ("delete", "c.txt"), ("update", "d.txt"), ("move", "e.txt")], (ok, err))
    check("codex: parse_patch keeps the added lines of Add File and of Update File (+ lines only)",
          ok[0]["added"] == ["x", "y"] and ok[1]["added"] == ["b"], ok)
    bad = {"empty": "", "no Begin": "*** Add File: a\n+x\n*** End Patch", "no End": "*** Begin Patch\n*** Add File: a\n+x",
           "text before a header": "*** Begin Patch\nhello\n*** End Patch", "Add File line without +": patch("*** Add File: a\nx"),
           "body under Delete": patch("*** Delete File: a\n+x"), "Move to without Update": patch("*** Move to: b"),
           "unknown line in Update": patch("*** Update File: a\n@@\n!x"), "header without a path": patch("*** Add File: "),
           "no file": "*** Begin Patch\n*** End Patch", "not a string": None}
    for name, text in bad.items():
        res, err = engine.parse_patch(text)
        check("codex: parse_patch refuses a patch that is not in the format (%s)" % name, res is None, (res, err))
    check("codex: patch_in_command takes the patch out of an `apply_patch <<EOF` command",
          engine.patch_in_command("apply_patch <<'EOF'\n" + patch(add("a", "x")) + "\nEOF") == patch(add("a", "x")))


def test_apply_patch_gate():
    e = CodexEnv()
    try:
        d = "projects/01_app/"
        r0 = e.ap(patch(add(d + "src/a.py", "x")))
        check("codex: R0 apply_patch to a project is refused (the hole in the review: Write was refused, apply_patch was not)", r0 is not None, r0)
        r0w = e.tool("Write", file_path=e.p("projects", "01_app", "src", "a.py"), content="x")
        check("codex: R0 Write is refused too (same decision)", r0w is not None)
        check("codex: R0 apply_patch to a protected file (README.md) is refused", e.ap(patch(add("README.md", "x"))) is not None)

        slug = build_to_run(e)
        e.prompt("continue")
        e.prompt("ok")
        s = "projects/%s/src/" % slug
        check("codex: RUN Add File in src/ is allowed (after approval)", e.ap(patch(add(s + "a.py", "print(1)"))) is None)
        open(e.p("projects", slug, "src", "a.py"), "w").write("a\n")
        check("codex: RUN Update File in src/ is allowed", e.ap(patch(upd(s + "a.py"))) is None)
        check("codex: RUN Delete File in src/ is allowed", e.ap(patch(dele(s + "a.py"))) is None)
        check("codex: RUN Move to inside src/ is allowed", e.ap(patch(move(s + "a.py", s + "b.py"))) is None)
        check("codex: RUN Move to a protected place (README.md) is refused", e.ap(patch(move(s + "a.py", "README.md"))) is not None)
        check("codex: RUN Move from a protected place is refused", e.ap(patch(move("ws/engine.py", s + "x.py"))) is not None)
        check("codex: RUN a patch with two files is allowed when both are allowed", e.ap(patch(add(s + "c.py", "1"), add(s + "d.py", "2"))) is None)
        r = e.ap(patch(add(s + "ok.py", "1"), add(".claude/settings.json", "{}")))
        check("codex: RUN one refused path among several stops the whole patch", r is not None and "can be changed only by the user" in r, r)
        r = e.ap(patch(add(".claude/settings.json", "{}"), add(s + "ok.py", "1")))
        check("codex: ... whatever the order", r is not None, r)
        for p in ("ws/engine.py", ".ws/state.json", ".codex/hooks.json", "AGENTS.md", "BOOTSTRAP.codex.md", "CLAUDE.md", ".mcp.json", ".gitignore",
                  "projects/%s/design/schedule.json" % slug, "projects/%s/design/systemtest.json" % slug, "other.txt"):
            check("codex: RUN Add File %s is refused" % p, e.ap(patch(add(p, "x"))) is not None, p)
        check("codex: RUN Delete File of a protected file is refused", e.ap(patch(dele("ws/engine.py"))) is not None)
        check("codex: RUN Update File of ws/engine.py is refused", e.ap(patch(upd("ws/engine.py"))) is not None)
        check("codex: a path outside the workspace is refused", e.ap(patch(add("/etc/ccb_x", "x"))) is not None)
        check("codex: a path that climbs out with .. is refused", e.ap(patch(add(s + "../../../../x.py", "x"))) is not None)
        check("codex: another project's folder is refused", e.ap(patch(add("projects/02_other/src/a.py", "x"))) is not None)
        check("codex: the secrets file (%s) is refused" % DOTENV, e.ap(patch(add(s + DOTENV, "A=1"))) is not None)
        check("codex: src/%s.example is allowed (names only)" % DOTENV, e.ap(patch(add(s + DOTENV + ".example", "API_KEY="))) is None)
        check("codex: an AGENTS.md inside imported code is refused", e.ap(patch(add(s + "AGENTS.md", "x"))) is not None)
        k = fake_secret("sklive")
        r = e.ap(patch(add(s + "k.py", "K = '%s'" % k)))
        check("codex: a key in an Add File '+' line is refused", r is not None and "key or a password" in r, r)
        check("codex: a key in an Update File '+' line is refused", e.ap(patch("*** Update File: %ss.py\n@@\n-old\n+K = '%s'" % (s, k))) is not None)
        check("codex: a key only in a removed ('-') line is not scanned", e.ap(patch("*** Update File: %sz.py\n@@\n-K = '%s'\n+K = process.env.API_KEY" % (s, k))) is None)
        check("codex: a key in the second file stops the whole patch", e.ap(patch(add(s + "o1.py", "1"), add(s + "o2.py", "K='%s'" % k))) is not None)
        check("codex: process.env code is allowed", e.ap(patch(add(s + "e.js", "const k = process.env.API_KEY;"))) is None)
        for name, text in (("no Begin", "*** Add File: x\n+x\n*** End Patch"), ("no End", "*** Begin Patch\n*** Add File: " + s + "x\n+x"),
                           ("garbage", "hello"), ("empty", ""), ("unknown line", patch("*** Update File: %sx\n!zzz" % s)),
                           ("Add File line without +", patch("*** Add File: %sx\nplain" % s))):
            r = e.ap(text)
            check("codex: an unreadable patch is refused (%s)" % name, r is not None and "could not be read exactly" in r, r)
        r = e.sh("apply_patch <<'EOF'\n" + patch(add("ws/engine.py", "x")) + "\nEOF")
        check("codex: a patch typed into the shell (apply_patch <<EOF) goes through the same checks", r is not None, r)
        check("codex: ... and one for an allowed path is allowed in RUN (the other Bash rules still apply)",
              e.sh("apply_patch <<'EOF'\n" + patch(add(s + "sh.py", "1")) + "\nEOF") is None)
        check("codex: ... but a shell patch with a key is refused", e.sh("apply_patch <<'EOF'\n" + patch(add(s + "sh.py", "K='%s'" % k)) + "\nEOF") is not None)
        # first turn of a session: read only
        e.hook("sessionstart", {"source": "clear"})
        e.prompt("continue")
        r = e.ap(patch(add(s + "ft.py", "1")))
        check("codex: the first turn is read-only for apply_patch too", r is not None and "First turn is read-only" in r, r)
    finally:
        e.close()


def test_stage_gate():
    """Before approval, src/ stays locked for apply_patch; the design folder is open from R2."""
    e = CodexEnv()
    try:
        e.hook("sessionstart", {"source": "startup"})
        e.prompt("make a small tool")
        e.run(["new", "app", "--name", "App", "--quote", "make a small tool"])
        slug = "01_app"
        e.prompt("hello")
        s = "projects/%s/" % slug
        check("codex: R1 apply_patch to src/ is refused (locked until approval)", e.ap(patch(add(s + "src/a.py", "1"))) is not None)
        check("codex: R1 apply_patch to PROJECT.md (one line changed) is allowed", e.ap(patch("*** Update File: %sPROJECT.md\n@@\n-what: \n+what: a tool" % s)) is None)
        check("codex: R1 Add File on an existing PROJECT.md is refused (it would drop the other keys, as Write does)", e.ap(patch(add(s + "PROJECT.md", "what: x"))) is not None)
        check("codex: apply_patch to design/ is allowed", e.ap(patch(add(s + "design/ui/sketch.html", "<html></html>"))) is None)
        for name in ("mcp__fs__write_file", "mcp__tracker__create_issue", "mcp__x__createIssue"):
            r = e.tool(name, path="x")
            check("codex: before approval, an MCP tool whose name says it writes waits for the build stage (%s)" % name,
                  r is not None and "stopped until the build stage" in r, r)
        check("codex: before approval, an MCP tool with a read name is allowed", e.tool("mcp__docs__search", q="x") is None)
        check("codex: only the tool part of an MCP name counts (a server named file-editor, tool read_file)",
              e.tool("mcp__file-editor__read_file", path="x") is None)
    finally:
        e.close()


def test_unknown_tools():
    e = CodexEnv()
    try:
        build_to_run(e)
        e.prompt("continue")
        e.prompt("ok")
        for name in ("WriteFile", "edit_file", "apply_edits", "create_directory", "delete_file", "move_file", "rename_path", "FilePatch"):
            r = e.tool(name, path="x")
            check("codex: an unknown built-in tool whose name says it writes is refused, even in RUN (%s)" % name, r is not None and "does not know the tool" in r, r)
        for name in ("mcp__fs__write_file", "mcp__tracker__create_issue", "mcp__x__createIssue"):
            check("codex: in RUN, an MCP tool whose name says it writes is allowed (the user decides what an added server may do) (%s)" % name,
                  e.tool(name, path="x") is None, name)
        for name in ("update_plan", "TodoWrite", "WebSearch", "view_image", "mcp__docs__search", "mcp__docs__list_pages", "get_weather", "Task"):
            check("codex: an unknown tool with a harmless name is allowed (%s)" % name, e.tool(name, q="x") is None, name)
        check("codex: the known edit tools are decided as before (Write to README.md is refused)", e.tool("Write", file_path=e.p("README.md"), content="x") is not None)
        check("codex: the Gakaso rule still comes first (a read name is allowed)", e.tool("mcp__gakaso__list_pages") is None)
        e.hook("sessionstart", {"source": "clear"})
        e.prompt("continue")
        r = e.tool("mcp__tracker__create_issue", title="x")
        check("codex: the first turn of a session is read-only for MCP write tools too", r is not None and "First turn is read-only" in r, r)
    finally:
        e.close()


def test_adapter():
    e = CodexEnv()
    try:
        ev = {"hook_event_name": "PreToolUse", "tool_name": "Bash", "tool_input": {"command": "ls"}, "cwd": e.root}
        rc, out = e.chook("pretool", ev)
        check("codex adapter: pretool allow = exit 0 and no output", rc == 0 and out == "", (rc, out))
        rc, out = e.chook("pretool", dict(ev, tool_name="Write", tool_input={"file_path": e.p("README.md"), "content": "x"}))
        o = json.loads(out)
        h = o["hookSpecificOutput"]
        check("codex adapter: pretool deny = exit 0 and hookSpecificOutput {hookEventName, permissionDecision: deny, permissionDecisionReason}",
              rc == 0 and set(o) == {"hookSpecificOutput"} and set(h) == {"hookEventName", "permissionDecision", "permissionDecisionReason"}
              and h["hookEventName"] == "PreToolUse" and h["permissionDecision"] == "deny" and h["permissionDecisionReason"].startswith(PREFIX), (rc, out[:200]))
        for label, data in (("not JSON", b"nope"), ("empty", b""), ("a list", b"[]")):
            p = subprocess.run([sys.executable, "-I", e.p(".claude", "hooks", "ws_hook.py"), "pretool", "--client", "codex"], input=data,
                               capture_output=True, env=e.env, cwd=e.root)
            o = json.loads(p.stdout.decode()) if p.stdout.strip() else None
            check("codex adapter: pretool with %s on stdin = deny (fail-closed)" % label, p.returncode == 0 and o and o["hookSpecificOutput"]["permissionDecision"] == "deny", (p.returncode, p.stdout[:100]))
        # session start: the context starts with a [CreateCodeBox line, and the client is remembered
        rc, out = e.chook("sessionstart", {"hook_event_name": "SessionStart", "source": "startup", "cwd": e.root, "session_id": "s"})
        o = json.loads(out)
        txt = o["hookSpecificOutput"]["additionalContext"]
        check("codex adapter: SessionStart answers {hookSpecificOutput: {hookEventName: SessionStart, additionalContext}} with a [CreateCodeBox line",
              o["hookSpecificOutput"]["hookEventName"] == "SessionStart" and "[CreateCodeBox" in txt, txt[:200])
        check("codex adapter: SessionStart records that Codex is the client (for doctor)", e.rec("session.json").get("client") == "codex")
        rc, out = e.chook("prompt", {"hook_event_name": "UserPromptSubmit", "prompt": "make a small tool", "cwd": e.root})
        o = json.loads(out)
        check("codex adapter: UserPromptSubmit answers additionalContext with the stage", o["hookSpecificOutput"]["hookEventName"] == "UserPromptSubmit"
              and "[CreateCodeBox" in o["hookSpecificOutput"]["additionalContext"], out[:200])
        rc, out = e.chook("prompt", {"hook_event_name": "UserPromptSubmit", "prompt": "my key is %s" % fake_secret("sklive"), "cwd": e.root})
        o = json.loads(out)
        check("codex adapter: a key in the prompt = {decision: block, reason} and no Claude-only field", o.get("decision") == "block" and o.get("reason")
              and "hookSpecificOutput" not in o and rc == 0, out[:200])
        e.run(["new", "app", "--name", "App", "--quote", "make a small tool"])
        rc, out = e.chook("stop", {"hook_event_name": "Stop", "stop_hook_active": False, "last_assistant_message": "done", "cwd": e.root})
        check("codex adapter: Stop with nothing to say = exit 0 and no output", rc == 0 and out == "", (rc, out))
        # tool names the Codex shell may use are Bash for the engine
        check("codex adapter: exec_command with {cmd} is Bash for the engine", CX.normalize_event({"tool_name": "exec_command", "tool_input": {"cmd": "ls -l"}})["tool_name"] == "Bash"
              and CX.normalize_event({"tool_name": "shell", "tool_input": {"command": ["bash", "-lc", "ls"]}})["tool_input"]["command"] == "bash -lc ls")
        check("codex adapter: apply_patch is left as it is", CX.normalize_event({"tool_name": "apply_patch", "tool_input": {"command": "p"}}) ==
              {"tool_name": "apply_patch", "tool_input": {"command": "p"}})
        check("codex adapter: read_event parses JSON and gives None for text that is not JSON", CX.read_event(io.StringIO('{"a": 1}')) == {"a": 1} and CX.read_event(io.StringIO("x")) is None)
        # the shell: a command typed in the Codex shell tool is judged like Bash
        check("codex: Bash that prints the secrets file is refused", e.sh("cat " + DOTENV) is not None)
        check("codex: Bash `ls` is allowed", e.sh("ls") is None)
    finally:
        e.close()


def test_tasks_codex():
    """The triage works through the Codex adapter: apply_patch and the shell are stopped until the message is sorted onto the task board."""
    e = CodexEnv()
    try:
        slug = build_to_run(e)
        e.prompt("continue")
        e.prompt("ok")
        rc, out = e.chook("sessionstart", {"hook_event_name": "SessionStart", "source": "resume", "cwd": e.root, "session_id": "s"})
        txt = json.loads(out)["hookSpecificOutput"]["additionalContext"]
        check("codex tasks: SessionStart has the task board block", "Task board" in txt and "Full board:" in txt, txt[-300:])
        s = "projects/%s/src/" % slug
        check("codex tasks: a plain `continue` starts no triage (apply_patch is allowed)",
              json.loads(e.chook("prompt", {"hook_event_name": "UserPromptSubmit", "prompt": "continue", "cwd": e.root})[1])["hookSpecificOutput"]["additionalContext"]
              and e.ap(patch(add(s + "a.py", "1"))) is None)
        rc, out = e.chook("prompt", {"hook_event_name": "UserPromptSubmit", "prompt": "Please add an export to CSV by 2026-11-05", "cwd": e.root})
        ctx = json.loads(out)["hookSpecificOutput"]["additionalContext"]
        check("codex tasks: a new requirement puts the triage line in the context", "task none" in ctx and "task add" in ctx, ctx[-300:])
        r = e.ap(patch(add(s + "a.py", "1")))
        check("codex tasks: apply_patch is refused while the message is not sorted (deny.triage)", r is not None and "task none" in r, r)
        r = e.sh("python3 x.py")
        check("codex tasks: a shell command that writes is refused; a read-only one and ws.sh task are allowed",
              r is not None and "task none" in r and e.sh("ls") is None and e.sh('bash ws/bin/ws.sh task add "Export to CSV"') is None
              and e.sh("bash ws/bin/ws.sh task none") is None, r)
        check("codex tasks: the same decision for a patch typed into the shell", e.sh("apply_patch <<'EOF'\n" + patch(add(s + "sh.py", "1")) + "\nEOF") is not None)
        rc, out = e.chook("stop", {"hook_event_name": "Stop", "stop_hook_active": False, "last_assistant_message": "done", "cwd": e.root})
        o = json.loads(out)
        check("codex tasks: Stop blocks once with {decision: block, reason} (stop.triage)", rc == 0 and o.get("decision") == "block" and "task none" in o.get("reason", ""), out)
        rc, out = e.chook("stop", {"hook_event_name": "Stop", "stop_hook_active": False, "last_assistant_message": "done", "cwd": e.root})
        check("codex tasks: the second Stop passes", rc == 0 and out == "", out)
        e.chook("prompt", {"hook_event_name": "UserPromptSubmit", "prompt": "Also add a dark mode", "cwd": e.root})
        rc, out = e.chook("stop", {"hook_event_name": "Stop", "stop_hook_active": True, "last_assistant_message": "done", "cwd": e.root})
        check("codex tasks: Stop passes when stop_hook_active", rc == 0 and out == "", out)
        rc, out = e.run(["task", "add", "Dark mode"])
        check("codex tasks: after task add the patch is allowed again", rc == 0 and "T-01" in out and e.ap(patch(add(s + "a.py", "1"))) is None, out)
        check("codex tasks: projects/schedule.html cannot be written with apply_patch", e.ap(patch(add("projects/schedule.html", "x"))) is not None)
        rc, out = e.chook("prompt", {"hook_event_name": "UserPromptSubmit", "prompt": "yes", "cwd": e.root})
        check("codex tasks: a plain yes starts no triage", e.ap(patch(add(s + "b.py", "1"))) is None)
    finally:
        e.close()


def test_root_and_cwd():
    """Codex sets no project-folder variable and can start anywhere inside the workspace."""
    e = CodexEnv()
    try:
        sub = e.p("ws", "bin")
        ev = {"hook_event_name": "PreToolUse", "tool_name": "Write", "tool_input": {"file_path": e.p("README.md"), "content": "x"}, "cwd": sub}
        rc, out = e.chook("pretool", ev, cwd=sub)
        check("codex: the root comes from where the engine is (no CLAUDE_PROJECT_DIR), even when the hook runs in a subfolder", rc == 0 and "can be changed only by the user" in out, out[:200])
        os.environ.pop("CREATECODEBOX_ROOT", None)
        check("codex adapter: project_root() is two folders above ws/adapters/", os.path.realpath(CX.project_root()) == os.path.realpath(base.TEMPLATE))
        # the command in .codex/hooks.json finds ws/bin/hook.sh by walking up
        hooks = json.load(open(e.p(".codex", "hooks.json"), encoding="utf-8"))
        cmd = hooks["hooks"]["PreToolUse"][0]["hooks"][0]["command"]
        deep = e.p("projects")
        os.makedirs(deep, exist_ok=True)
        p = subprocess.run(["/bin/sh", "-c", cmd], input=json.dumps(dict(ev, cwd=deep)).encode(), capture_output=True, env=e.env, cwd=deep)
        check("codex: the hooks.json command works from a subfolder (walks up to ws/bin/hook.sh) and denies", p.returncode == 0 and b"permissionDecision" in p.stdout, (p.returncode, p.stdout[:150], p.stderr[:150]))
        lone = os.path.join(e.tmp, "nowhere")
        os.makedirs(lone)
        p = subprocess.run(["/bin/sh", "-c", cmd], input=b"{}", capture_output=True, env=e.env, cwd=lone)
        check("codex: if ws/bin/hook.sh cannot be found, the pretool command exits 2 (blocks)", p.returncode == 2, (p.returncode, p.stderr[:100]))
        for ev_name, want in (("SessionStart", 0), ("Stop", 0), ("UserPromptSubmit", 2)):
            c = hooks["hooks"][ev_name][0]["hooks"][0]["command"]
            p = subprocess.run(["/bin/sh", "-c", c], input=b"{}", capture_output=True, env=e.env, cwd=lone)
            check("codex: hooks.json %s command without a workspace exits %d" % (ev_name, want), p.returncode == want, p.returncode)
    finally:
        e.close()


def test_client_selection():
    e = CodexEnv()
    try:
        ev = {"tool_name": "apply_patch", "tool_input": {"command": patch(add("README.md", "x"))}, "cwd": e.root}
        raw = lambda args, env: subprocess.run(["/bin/sh", e.p("ws", "bin", "hook.sh"), "pretool"] + args, input=json.dumps(ev).encode(), capture_output=True, env=env, cwd=e.root)
        p = raw(["--client", "codex"], e.env)
        check("client: hook.sh pretool --client codex works through the shell launcher", p.returncode == 0 and b"permissionDecision" in p.stdout, (p.returncode, p.stdout[:100], p.stderr[:100]))
        p = raw([], dict(e.env, CREATECODEBOX_CLIENT="codex"))
        check("client: CREATECODEBOX_CLIENT=codex selects the Codex adapter", p.returncode == 0 and b"permissionDecision" in p.stdout, (p.returncode, p.stdout[:100]))
        p = raw([], dict(e.env, CLAUDE_PROJECT_DIR=e.root))
        check("client: no choice = claude (apply_patch is still stopped by the gate)", p.returncode == 0 and b"permissionDecision" in p.stdout, (p.returncode, p.stdout[:100]))
        import adapters
        check("client: adapters.load picks codex / claude, and anything unknown is claude",
              adapters.load("codex").NAME == "codex" and adapters.load("claude").NAME == "claude" and adapters.load("Codex ").NAME == "codex"
              and adapters.load("emacs").NAME == "claude" and adapters.load(None).NAME == "claude" and adapters.load("").NAME == "claude")
        body = json.dumps({"prompt": "my key %s" % fake_secret("sklive")}).encode()
        p = subprocess.run([sys.executable, "-I", e.p(".claude", "hooks", "ws_hook.py"), "prompt", "--client=codex"], input=body, capture_output=True, env=e.env, cwd=e.root)
        o = json.loads(p.stdout)
        check("client: --client=codex (with =) works too", o.get("decision") == "block" and "hookSpecificOutput" not in o, p.stdout[:100])
        p = subprocess.run([sys.executable, "-I", e.p(".claude", "hooks", "ws_hook.py"), "prompt"], input=body, capture_output=True,
                           env=dict(e.env, CLAUDE_PROJECT_DIR=e.root), cwd=e.root)
        o = json.loads(p.stdout)
        check("client: the Claude answer to a key in the prompt is unchanged (suppressOriginalPrompt)", o["hookSpecificOutput"].get("suppressOriginalPrompt") is True, p.stdout[:150])
    finally:
        e.close()


def test_codex_warnings():
    e = CodexEnv()
    try:
        home = e.home
        lang.use("en")
        check("codex doctor: no AGENTS.md anywhere = no Codex lines", engine.codex_lines(e.root, home=home) == [])
        os.makedirs(os.path.join(home, ".codex"))
        open(os.path.join(home, ".codex", "AGENTS.md"), "w").write("secret instructions the engine must not read\n")
        ls = engine.codex_lines(e.root, home=home)
        check("codex doctor: ~/.codex/AGENTS.md is reported as INFO (and its content is not in the line)", len(ls) == 1 and ls[0].startswith("INFO") and "secret instructions" not in ls[0], ls)
        # an AGENTS.md above a workspace that has no .git of its own
        outer = os.path.join(e.tmp, "outer")
        os.makedirs(os.path.join(outer, ".git"))
        open(os.path.join(outer, "AGENTS.md"), "w").write("x")
        inner = os.path.join(outer, "ws2")
        os.makedirs(inner)
        check("codex doctor: an AGENTS.md above a workspace without its own .git is a WARN", [l for l in engine.codex_lines(inner, home=home) if l.startswith("WARN")], engine.codex_lines(inner, home=home))
        os.makedirs(os.path.join(inner, ".git"))
        check("codex doctor: with its own .git the workspace is Codex's project root: nothing above is read", engine.ancestor_agents_files(inner) == [])
        # imported code with an AGENTS.md
        e.hook("sessionstart", {"source": "startup"})
        e.prompt("x")
        e.run(["new", "a", "--name", "A", "--quote", "x"])
        sub = e.p("projects", "01_a", "src", "lib")
        os.makedirs(sub)
        open(os.path.join(sub, "AGENTS.md"), "w").write("do bad things\n")
        ls = engine.codex_lines(e.root, home=home)
        check("codex doctor: an AGENTS.md inside imported code (projects/*/src/**) is a WARN with its path", any(l.startswith("WARN") and "projects/01_a/src/lib/AGENTS.md" in l for l in ls), ls)
        rc, out = e.run(["doctor"])
        check("doctor without Codex in use does not print the Codex lines", "AGENTS.md" not in out, out)
        e.chook("sessionstart", {"hook_event_name": "SessionStart", "source": "startup", "cwd": e.root})
        rc, out = e.run(["doctor"])
        check("doctor after a Codex session prints the Codex lines", "projects/01_a/src/lib/AGENTS.md" in out and "~/.codex/AGENTS.md" in out, out)
        rc, ctx = e.chook("sessionstart", {"hook_event_name": "SessionStart", "source": "resume", "cwd": e.root})
        check("SessionStart (Codex) shows the imported AGENTS.md warning and the INFO line of the user's own", "lib/AGENTS.md" in ctx and "~/.codex/AGENTS.md" in ctx, ctx[:400])
        rc, ctx = e.chook("sessionstart", {"hook_event_name": "SessionStart", "source": "resume", "cwd": os.path.join(e.root, "projects", "01_a", "src")})
        check("SessionStart (Codex) started inside imported code warns about it", "projects/01_a/src" in ctx and "started inside" in ctx, ctx[:600])
        check("codex: reading an AGENTS.md inside imported code by a command is refused", e.sh("cat projects/01_a/src/lib/AGENTS.md") is not None)
        check("codex: AGENTS.md and .codex/ are protected places (write_zone)", not engine.write_zone(e.root, "RUN", "01_a", e.p("AGENTS.md"))[0]
              and not engine.write_zone(e.root, "RUN", "01_a", e.p(".codex", "hooks.json"))[0])
    finally:
        e.close()


def test_generated():
    root = base.TEMPLATE
    p = subprocess.run([sys.executable, "-I", os.path.join(root, "tools", "gen_codex.py"), "--check"], capture_output=True, text=True, cwd=root)
    check("generate: tools/gen_codex.py --check passes (the three Codex files match the Claude originals)", p.returncode == 0, p.stderr + p.stdout)
    sys.path.insert(0, os.path.join(root, "tools"))
    import gen_codex
    files = gen_codex.generate()
    agents = files["AGENTS.md"]
    check("generate: AGENTS.md has the rules of CLAUDE.md and the pm rules", "Only the user's own words record an approval" in agents and "plain-words" in agents and "## Codex notes" in agents)
    low = agents.lower()
    spots = [low[max(0, i - 12):i + 11] for i in range(len(low)) if low.startswith("independent", i)]
    check("generate: AGENTS.md never claims an independent review (it only says 'not an independent review')", all("not an independent" in s or "call it independent" in s for s in spots), spots)
    check("generate: AGENTS.md does not tell Codex to call helper agents (no Task / subagent call)", "Task tool" not in agents and "spawn_agent" not in agents and "There are no helper agents in Codex" in agents)
    check("generate: AGENTS.md says the hardened mode is Claude only", "harden" in agents and "for Claude Code only" in agents)
    check("generate: AGENTS.md keeps the approval words (looks good / approve / publish)", all(w in agents for w in ("`looks good`", "`approve`", "`publish`")))
    check("generate: AGENTS.md is under 32 KiB (Codex stops reading there)", len(agents.encode("utf-8")) < 32 * 1024, len(agents.encode()))
    check("generate: AGENTS.md has no Claude-only instruction left (no 'Playwright', no 'Edit tool', no `claude` command)",
          "Playwright" not in agents and "the Edit tool" not in agents and "`claude`" not in agents, [w for w in ("Playwright", "the Edit tool", "`claude`") if w in agents])
    h = json.loads(files[".codex/hooks.json"])
    ev = h["hooks"]
    check("generate: hooks.json has SessionStart, UserPromptSubmit, PreToolUse, Stop with --client codex",
          set(ev) == {"SessionStart", "UserPromptSubmit", "PreToolUse", "Stop"} and all("--client codex" in g["hooks"][0]["command"] for gs in ev.values() for g in gs))
    check("generate: PreToolUse matches every tool ('*') and exits 2 when the hook fails", ev["PreToolUse"][0]["matcher"] == "*" and ev["PreToolUse"][0]["hooks"][0]["command"].endswith("|| exit 2"))
    check("generate: hooks.json has no absolute path and no CLAUDE_PROJECT_DIR", "CLAUDE_PROJECT_DIR" not in files[".codex/hooks.json"] and "/Users/" not in files[".codex/hooks.json"])
    b = files["BOOTSTRAP.codex.md"]
    check("generate: BOOTSTRAP.codex.md starts Codex (`codex`) and asks the user to trust the hooks", "`codex`" in b and "/hooks" in b and "Claude" not in b, [w for w in ("Claude",) if w in b])
    check("generate: BOOTSTRAP.codex.md keeps the four allowed commands and the fixed folder for odd home paths",
          "`git clone <address> <folder>`" in b and "C:\\CreateCodeBox" in b and "/Users/Shared/CreateCodeBox" in b)
    # a stale overlay is a failure, not a silent skip
    try:
        gen_codex.replace_all("abc", [["zzz", "y"]], "test")
        stale = False
    except gen_codex.GenError:
        stale = True
    check("generate: an overlay replacement that no longer matches its original is an error", stale)
    check("generate: the generated files are in the repository", all(os.path.isfile(os.path.join(root, f)) for f in ("AGENTS.md", ".codex/hooks.json", "BOOTSTRAP.codex.md")))


def test_two_step_approval_codex():
    """The Codex adapter shares the engine: a natural reply starts the approval question, and the next prompt's plain yes records it."""
    e = CodexEnv()
    try:
        def prompt(text):
            rc, out = e.chook("prompt", {"hook_event_name": "UserPromptSubmit", "prompt": text, "cwd": e.root})
            assert rc == 0, (rc, out)
            return json.loads(out)["hookSpecificOutput"]["additionalContext"]
        slug = base.to_r3(e, "en")
        c = prompt("Looks great, go ahead")
        pend = e.rec("session.json").get("pending_confirm") or {}
        check("codex two-step: a natural reply at R3 is not recorded; the context has the fixed question; a pending approval is saved (kind, project, prompt number)",
              base.Q_R3_EN in c and pend.get("kind") == "r3" and pend.get("slug") == slug and e.stage() == "R3"
              and not os.path.exists(e.p(".ws", "confirm_%s.json" % slug)), (c[-200:], pend))
        c = prompt("yes")
        rec = e.rec("confirm_%s.json" % slug)
        check("codex two-step: the next prompt's plain yes records the approval; the record has via=confirm, both quotes, and a signature",
              e.stage() == "R4" and rec.get("via") == "confirm" and rec.get("quote") == "Looks great, go ahead" and rec.get("confirm_quote") == "yes" and "_sig" in rec, (e.stage(), rec))
        # not the very next prompt: nothing is recorded
        e2 = CodexEnv()
        try:
            slug2 = base.to_r3(e2, "ja")
            rc, out = e2.chook("prompt", {"hook_event_name": "UserPromptSubmit", "prompt": "いい感じです。進めてください", "cwd": e2.root})
            check("codex two-step (ja): the question is asked in Japanese", base.Q_R3_JA in json.loads(out)["hookSpecificOutput"]["additionalContext"], out[-200:])
            e2.chook("prompt", {"hook_event_name": "UserPromptSubmit", "prompt": "少し待ってください", "cwd": e2.root})
            e2.chook("prompt", {"hook_event_name": "UserPromptSubmit", "prompt": "はい", "cwd": e2.root})
            check("codex two-step: a yes that is not the very next prompt records nothing", e2.stage() == "R3" and not os.path.exists(e2.p(".ws", "confirm_%s.json" % slug2)), e2.stage())
        finally:
            e2.close()
    finally:
        e.close()


def test_start_check_codex():
    """The start check shows the Codex-only problems in the same short form (a line for each, at most 3, then the full-check line)."""
    e = CodexEnv()
    try:
        home = e.home
        os.makedirs(os.path.join(home, ".codex"))
        open(os.path.join(home, ".codex", "AGENTS.md"), "w").write("my own rules\n")
        rc, out = e.chook("sessionstart", {"hook_event_name": "SessionStart", "source": "startup", "cwd": e.root, "session_id": "s"})
        txt = json.loads(out)["hookSpecificOutput"]["additionalContext"]
        lines = [l for l in txt.splitlines() if l.startswith("- ")]
        check("codex start check: ~/.codex/AGENTS.md is one short line with a fix, then the full-check line; its content is not printed",
              len(lines) == 1 and "~/.codex/AGENTS.md" in lines[0] and "Fix:" in lines[0] and "my own rules" not in txt
              and txt.rstrip().splitlines()[-1] == "Full check: bash ws/bin/ws.sh doctor", txt[-400:])
    finally:
        e.close()


def main():
    for fn in (test_patch_parser, test_apply_patch_gate, test_stage_gate, test_unknown_tools, test_adapter, test_root_and_cwd,
               test_client_selection, test_codex_warnings, test_two_step_approval_codex, test_start_check_codex, test_tasks_codex, test_generated):
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
