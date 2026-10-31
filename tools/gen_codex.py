#!/usr/bin/env python3
"""Build the Codex files from the Claude originals (standard library only).

  AGENTS.md            <- CLAUDE.md + .claude/agents/pm.md, with tools/codex_overlay.json applied
  .codex/hooks.json    <- the hooks of .claude/settings.json
  BOOTSTRAP.codex.md   <- BOOTSTRAP.md, with the overlay applied

The Claude files are the originals. The only hand-kept part is tools/codex_overlay.json (small replacements).
usage (from the repository root):
  python3 tools/gen_codex.py           write the three files
  python3 tools/gen_codex.py --check   write nothing; exit 1 if a file differs from what would be generated
                                       (or if an overlay replacement no longer matches its original)
"""
import json
import os
import re
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
HOOK_CMD = re.compile(r'^sh "\$CLAUDE_PROJECT_DIR/ws/bin/hook\.sh" (\w+) \|\| exit (\d+)$')
# Codex sets no project-folder variable and may start in a subfolder (or inside imported code with its own .git),
# so the command walks up from the current folder until it finds ws/bin/hook.sh. If it finds none: pretool fails closed.
FIND_ROOT = 'd="$PWD"; while [ ! -f "$d/ws/bin/hook.sh" ] && [ "$d" != "/" ]; do d=$(dirname "$d"); done; '


class GenError(Exception):
    pass


def read(rel):
    with open(os.path.join(ROOT, rel), encoding="utf-8") as f:
        return f.read()


def replace_all(text, pairs, where):
    for old, new in pairs:
        if text.count(old) != 1:
            raise GenError("overlay text not found exactly once in %s: %r" % (where, old[:70]))
        text = text.replace(old, new)
    return text


def split_front_matter(text):
    m = re.match(r"^---\n.*?\n---\n", text, re.S)
    return text[m.end():] if m else text


def replace_sections(text, sections, where):
    """Replace a whole `## heading` section (up to the next `## `) by new text."""
    for head, new in sections.items():
        m = re.search(r"^" + re.escape(head) + r"\n.*?(?=^## |\Z)", text, re.S | re.M)
        if not m:
            raise GenError("overlay section not found in %s: %r" % (where, head))
        text = text[:m.start()] + new.rstrip("\n") + "\n\n" + text[m.end():]
    return text


def demote(text):
    """pm.md headings go one level down (## -> ###), so that they sit under the pm title."""
    return re.sub(r"^(#{2,5}) ", lambda m: "#" + m.group(1) + " ", text, flags=re.M)


def gen_agents(ov):
    a = ov["agents_md"]
    rules = replace_all(read("CLAUDE.md"), a["claude_md"], "CLAUDE.md").strip()
    pm = split_front_matter(read(".claude/agents/pm.md"))
    pm = replace_sections(pm, a["pm_sections"], "pm.md")
    pm = replace_all(pm, a["pm_md"], "pm.md").strip()
    pm = demote(pm)
    parts = [a["header"], "", a["intro"], "", rules, "", "## The front desk (`pm`)", "", pm, "", a["extra_section"].strip(), ""]
    return "\n".join(parts)


def gen_hooks(ov):
    settings = json.loads(read(".claude/settings.json"))
    h = ov["hooks"]
    out = {}
    for event, groups in settings.get("hooks", {}).items():
        new_groups = []
        for g in groups:
            hs = []
            for item in g.get("hooks", []):
                m = HOOK_CMD.match(item.get("command", ""))
                if not m:
                    raise GenError("hook command in settings.json is not in the known form: %r" % item.get("command"))
                kind, code = m.group(1), m.group(2)
                cmd = FIND_ROOT + 'sh "$d/ws/bin/hook.sh" %s --client codex || exit %s' % (kind, code)
                hs.append({"type": "command", "command": cmd, "timeout": h["timeout"]})
            ng = {}
            if event == "PreToolUse":
                ng["matcher"] = h["pretool_matcher"]
            ng["hooks"] = hs
            new_groups.append(ng)
        out[event] = new_groups
    return json.dumps({"description": h["description"], "hooks": out}, indent=2, ensure_ascii=False) + "\n"


def gen_bootstrap(ov):
    return replace_all(read("BOOTSTRAP.md"), ov["bootstrap"], "BOOTSTRAP.md")


def generate():
    ov = json.loads(read("tools/codex_overlay.json"))
    return {"AGENTS.md": gen_agents(ov), ".codex/hooks.json": gen_hooks(ov), "BOOTSTRAP.codex.md": gen_bootstrap(ov)}


def main(argv):
    check = "--check" in argv
    try:
        files = generate()
    except GenError as e:
        print("gen_codex: %s" % e, file=sys.stderr)
        return 1
    bad = []
    for rel, text in files.items():
        path = os.path.join(ROOT, rel)
        try:
            cur = open(path, encoding="utf-8").read()
        except OSError:
            cur = None
        if check:
            if cur != text:
                bad.append(rel)
            continue
        os.makedirs(os.path.dirname(path), exist_ok=True)
        if cur != text:
            with open(path, "w", encoding="utf-8", newline="\n") as f:
                f.write(text)
            print("wrote " + rel)
    if check:
        if bad:
            print("gen_codex --check: out of date: %s. Run `python3 tools/gen_codex.py` and commit." % ", ".join(bad), file=sys.stderr)
            return 1
        print("gen_codex --check: AGENTS.md, .codex/hooks.json and BOOTSTRAP.codex.md match the originals")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
