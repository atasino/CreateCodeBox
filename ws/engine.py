#!/usr/bin/env python3
"""CreateCodeBox: stage computation and the body of the hooks and commands (standard library only).

The stage is not a saved value. It is computed every time from the files (PROJECT.md, design/, the records in .ws/).
Only the user's own words ("looks good", "approve", "publish" and their Japanese forms) are recorded by the hook. The AI cannot write to .ws/.
An input that cannot be judged or read is stopped (fail-closed).
All sentences the engine writes are in ws/lang/ (en.py is the source; ja.py is the Japanese table).
"""
import datetime
import glob
import hashlib
import hmac
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import time
import unicodedata

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lang  # noqa: E402  (ws/lang/: message tables and synonym tables)
from lang import T, synonyms as SYN  # noqa: E402
import adapters  # noqa: E402  (ws/adapters/: the host's hook protocol — root, input, answer shapes)
ADAPTER = adapters.load(os.environ.get("CREATECODEBOX_CLIENT"))

VERSION_FILE = os.path.join("ws", "VERSION")
SCHEMA = 3
GOAL_TYPES = SYN.GOAL_TYPES
R2_FIELDS = [("who", "r2.who"), ("today", "r2.today"), ("done_when", "r2.done_when"),
             ("not_doing", "r2.not_doing"), ("has_ui", "r2.has_ui")]
VIZ = SYN.VIZ
IO_KINDS = SYN.IO_KINDS
PLACEHOLDERS = {"", "（未記入）", "tbd", "TBD", "未定", "未記入", "-", "—", "?", "？",
                "n/a", "N/A", "unknown", "Unknown", "todo", "TODO", "ToDo", "(blank)", "(未記入)"}
BRIEF_SECTIONS = SYN.BRIEF_SECTIONS
STAGES = ("R0", "R1", "R2", "R3", "R4", "R4A", "RS", "RUN", "DONE")


def stage_label(code):
    return T("stage.label." + code)


STATE_ALIAS = {"通常": "normal", "空": "empty", "エラー": "error", "正常": "ok", "失敗": "failure"}  # 0.2 records
SCHEDULE_STEP = {"R0": "R0", "R1": "R1", "R2": "R2", "R3": "R3", "R4": "R4", "R4A": "R4",
                 "RS": "R4", "RUN": "RUN", "DONE": "RUN"}
PROTECTED_TOP = (".ws", ".claude", ".codex", "ws")
PROTECTED_FILES = ("CLAUDE.md", "AGENTS.md", "BOOTSTRAP.codex.md", ".mcp.json", ".gitignore", "README.md")
EDIT_TOOLS = {"Edit", "MultiEdit", "Write", "NotebookEdit"}
PATCH_TOOL = "apply_patch"  # Codex's file edit tool (the patch text is in tool_input.command)
# A tool the gate does not know by name is allowed, unless its name says it writes or changes something.
WRITE_NAME = re.compile(r"write|edit|patch|apply|create|delete|move|rename", re.I)
SAFE_TOOLS = {"TodoWrite", "update_plan", "Task", "Agent", "spawn_agent", "AskUserQuestion", "request_user_input", "ExitPlanMode",
              "WebFetch", "WebSearch", "Skill", "ToolSearch"}
GAKASO_READ = re.compile(r"(get|list|read|search|view|find|status|whoami|describe)", re.I)
READONLY_CMDS = {"ls", "cat", "pwd", "head", "tail", "wc", "grep", "rg", "date", "echo", "tree", "stat", "du", "which"}
READONLY_GIT = {"status", "log", "diff", "show"}
SHELL_META = re.compile(r"[><;&|`$\n\r]")
# find: only these options may appear (tests, operators, and actions that print to the screen). Anything else that
# starts with "-" is refused, so a write or a run (-fprintf, -fprint0, -fls, -exec, -delete …) never passes.
FIND_OK = {
    "-name", "-iname", "-path", "-ipath", "-wholename", "-iwholename", "-regex", "-iregex", "-regextype",
    "-lname", "-ilname", "-type", "-xtype", "-size", "-empty", "-perm", "-user", "-group", "-uid", "-gid",
    "-nouser", "-nogroup", "-links", "-inum", "-samefile", "-readable", "-writable", "-executable",
    "-mtime", "-mmin", "-atime", "-amin", "-ctime", "-cmin", "-newer", "-anewer", "-cnewer", "-used",
    "-maxdepth", "-mindepth", "-depth", "-xdev", "-mount", "-follow", "-noleaf", "-daystart",
    "-prune", "-quit", "-true", "-false", "-not", "-and", "-or", "-a", "-o",
    "-print", "-print0", "-printf", "-ls", "-H", "-L", "-P",
}
FIND_NEWER = re.compile(r"^-newer[aBcmt][aBcmt]$")


def shell_meta(cmd):
    """Shell symbols that can run or redirect something: SHELL_META, and a ( or ) outside quotes.
    zsh (the shell on a Mac) runs a command in =(cmd) and in glob qualifiers such as *(e:cmd:). Inside quotes they are plain text."""
    if SHELL_META.search(cmd):
        return True
    if "(" not in cmd and ")" not in cmd:
        return False
    try:
        lx = shlex.shlex(cmd, posix=True, punctuation_chars="()")
        lx.whitespace_split = True
        lx.commenters = ""  # zsh does not start a comment in the middle of a word (a#(cmd))
        return any(t and set(t) <= set("()") for t in lx)
    except ValueError:  # unbalanced quotes: refuse
        return True

# ---------- secret scanning ----------
SPECIFIC_PATTERNS = [
    ("openai-style", re.compile(r"(?<![A-Za-z0-9_])sk-[A-Za-z0-9_\-]{20,}")),
    ("github", re.compile(r"gh[pousr]_[A-Za-z0-9]{30,}")),
    ("github", re.compile(r"github_pat_[A-Za-z0-9_]{30,}")),
    ("aws", re.compile(r"AKIA[0-9A-Z]{16}")),
    ("slack", re.compile(r"xox[baprs]-[A-Za-z0-9\-]{10,}")),
    ("google", re.compile(r"AIza[0-9A-Za-z_\-]{35}")),
    ("private-key", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("supabase-secret", re.compile(r"sb_secret_[A-Za-z0-9_\-]{20,}")),
    ("stripe", re.compile(r"sk_(?:live|test)_[A-Za-z0-9]{16,}")),
    ("stripe", re.compile(r"rk_(?:live|test)_[A-Za-z0-9]{16,}")),
    ("stripe-webhook", re.compile(r"whsec_[A-Za-z0-9]{20,}")),
    ("gitlab", re.compile(r"glpat-[A-Za-z0-9_\-]{20}")),
    ("npm", re.compile(r"(?<![A-Za-z0-9_])npm_[A-Za-z0-9]{36}")),
    ("sendgrid", re.compile(r"SG\.[A-Za-z0-9_\-]{22}\.[A-Za-z0-9_\-]{43}")),
    ("huggingface", re.compile(r"(?<![A-Za-z0-9_])hf_[A-Za-z0-9]{30,}")),
    ("google-oauth", re.compile(r"ya29\.[A-Za-z0-9_\-]{30,}")),
]
URL_PW = re.compile(r"[a-z][a-z0-9+.\-]*://[^/\s:@]+:([^@\s]{6,})@")
JWT_RE = re.compile(r"eyJ[A-Za-z0-9_\-]{5,}\.(eyJ[A-Za-z0-9_\-]{5,})\.[A-Za-z0-9_\-]{5,}")
GENERIC_NAME = r"(?<![A-Za-z0-9])[A-Za-z0-9_\-]*?(?:api[_-]?key|secret|token|password|passwd)[A-Za-z0-9_]*[\"']?\s*[:=]\s*"
GENERIC_QUOTED = re.compile("(?i)" + GENERIC_NAME + r"([\"'`])([A-Za-z0-9_\-/+=]{16,})\1")
GENERIC_BARE = re.compile("(?i)" + GENERIC_NAME + r"([^\s#\"'`,;]{16,})")
BARE_SKIP = ("process.env.", "os.environ", "getenv", "import.meta.env", "$", "env.", "req.", "headers",
             "{{", "<", "!", "%", "@", "(", "[", "{")
CONFIG_EXT = (".yml", ".yaml", ".ini", ".properties", ".tfvars", ".toml")
EXAMPLE_NAMES = (".env.example", ".env.sample", ".env.template", ".env.dist")
PLACEHOLDER_WORDS = re.compile(r"(?i)(your|example|placeholder|changeme|change-me|replace|dummy|sample|insert|enter|xxxx|todo|redacted|secret-here|key-here|token-here)")
# The AI must not read or write the places that hold secret values.
SECRET_FILE = re.compile(r"(^|/)\.env(\.(?!example$)[^/]*)?$|(^|/)\.createcodebox(/|$)|(^|/)\.(ssh|aws|gnupg)(/|$)|(^|/)\.netrc$|(^|/)\.config/gh(/|$)|(^|/)\.git-credentials$|(^|/)\.npmrc$")
SECRET_CMD = re.compile(r"((^|[\s/\"'=])\.env(?!\.example)\b|\.createcodebox|\.ssh\b|\.aws\b|\.netrc|\.git-credentials|\.config/gh|\.npmrc|printenv|^env(\s|$)|\bexport\s+-p|security\s+find-|secret-tool|cmdkey|/proc/)")
SECRET_DIR = os.path.join("~", ".createcodebox")

# ---------- approval phrases (en and ja are ALWAYS both accepted, whatever the language setting) ----------
_EN_FILLER_HEAD = re.compile(r"^((ok|okay|yes|yeah|yep|yup|sure|great|perfect|thanks|thank you|alright|all right|well|so|hi|hey|please)[ ,.!:\-]+)+")
_EN_FILLER_TAIL = re.compile(r"([ ,]+(please|thanks|thank you|to me|for me|now|everyone))+$")
CONFIRM_EN = re.compile(r"^((it|that|this) )?(looks|look) good( to me)?$|^((let's|i'll|i will|we'll|lets) )?go with (this|that|it)( design)?$|^((i (like|choose|pick|want) )|(i'll take ))?this design$")
APPROVE_EN = re.compile(r"^(i )?approve(d)?( it| this| the design)?$")
PUBLISH_EN = re.compile(r"^publish( it| this)?$")
CONFIRM_RE = re.compile(r"^\s*この形で(お願いします|いいです|進めてください|進めて)?[。！!\s]*$")
APPROVE_RE = re.compile(r"^\s*(承認します|承認|これで進めてください|これで進めて|これでお願いします)[。！!\s]*$")
PUBLISH_RE = re.compile(r"^\s*公開します[。！!\s]*$")
# An input that contains any of these is never taken as an approval.
FORBID_EN = re.compile(r"(?<![A-Za-z'])(but|change|changes|however|not|no|don'?t|dont|never|wait|hold on|isn'?t|can'?t|cannot|won'?t|without|instead|cancel|stop|fix|revise|edit|unless|except)(?![A-Za-z'])")
FORBID_JA = re.compile(r"でも|直して|変えて|けど|ただし|しかし|変更|やめ|待って|まだ|ません|ない|いいえ|違う|ダメ|だめ")
AFFIRM_EN = re.compile(r"(?<![A-Za-z'])(ok|okay|yes|yeah|yep|yup|sure|good|fine|great|nice|perfect|agree|agreed|approve|approved|publish|proceed|go|lgtm|alright|correct|looks|love|done|ready|continue|do it|ship it)(?![A-Za-z'])")
AFFIRM_JA = re.compile(r"いい|良い|よい|はい|うん|オーケー|大丈夫|進めて|お願い|承認|公開|これで|それで|賛成|完璧|了解|ありがとう|最高")
# The only replies that answer the approval question with yes (two-step approval, see on_prompt). A small strict list: nothing else is a yes.
YES_EN = re.compile(r"^(yes|y|yes,? please|yes,? record it)$")
YES_JA = re.compile(r"^(はい|はい、?お願いします|お願いします)$")
CONFIRM_KIND = {"R3": "r3", "R4A": "r4a"}  # the two stages that have a two-step approval. publish and anything that sends data out never do.

GIT_RAW = re.compile(r"(^|[\s;&|(])git\s+(?:-[^\s]+\s+(?:[^\s-][^\s]*\s+)?)*(push|remote|commit|add)\b")
GH_RAW = re.compile(r"(^|[\s;&|(])gh\s")
CARD_FOR = {"init": "save", "save": "save", "link": "github", "backup": "github", "publish": "private-public", "adopt": "github"}
INLINE_CODE = re.compile(r"(^|\s)(python3?|node|ruby|perl)\s+(-c|-e)\b")
WS_CMD = re.compile(r"^(bash\s+|sh\s+)?(\./)?ws/bin/ws\.sh(\s|$)")
MCP_CMD = re.compile(r"^claude\s+mcp\s+(list|get|add)\b")
GANTT_REL = "projects/schedule.html"  # the schedule page of all projects: written only by ws.sh
PATCH_HEADER = re.compile(r"^\*\*\* (Add File|Update File|Delete File|Move to): (.*)$")
PROTECT_MENTION = re.compile(r"(\.ws\b|\.claude\b|\.codex\b|CLAUDE\.md|CLAUDE\.local\.md|AGENTS\.md|AGENTS\.override\.md|BOOTSTRAP\.codex|ws/engine|ws/bin|\.mcp\.json|projects/schedule\.html)")


# ---------- I/O parts ----------
def setup_io():
    """Make stdout and stderr UTF-8 whatever the terminal says (Windows cp932 / cp1252)."""
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError, OSError):
            pass


def nfkc(s):
    return unicodedata.normalize("NFKC", s or "")


def read_text(path):
    try:
        with open(path, "rb") as f:
            raw = f.read()
    except OSError:
        return None
    for enc in ("utf-8-sig", "cp932"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("latin-1")


def write_text(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = "%s.tmp%d" % (path, os.getpid())
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    os.replace(tmp, path)


def load_json(path, default=None):
    t = read_text(path)
    if t is None:
        return default
    try:
        return json.loads(t)
    except ValueError:
        return default


def save_json(path, obj):
    write_text(path, json.dumps(obj, ensure_ascii=False, indent=2) + "\n")


def ws_dir(root):
    return os.path.join(root, ".ws")


def projects_dir(root):
    return os.path.join(root, "projects")


def design_dir(root, slug):
    return os.path.join(projects_dir(root), slug, "design")


def list_projects(root):
    base = projects_dir(root)
    try:
        names = sorted(os.listdir(base))
    except OSError:
        return []
    return [n for n in names if os.path.isfile(os.path.join(base, n, "PROJECT.md"))]


def clean_value(v):
    v = (v or "").strip()
    v = re.sub(r"^[\s*`]+|[\s*`]+$", "", v)
    return v.strip()


MAX_REFERENCES = 3
_NONE_WORDS = {"none", "no", "n/a", "なし", "無し", "ない", "特になし"}


def _is_none_word(v):
    return nfkc(v).strip().strip("`*.。").lower() in _NONE_WORDS


def references_ok(p):
    """True when PROJECT.md has at least one `references:` line, or `references: none`."""
    return bool(p.get("references")) or bool(p.get("references_none"))


def parse_project(root, slug):
    text = read_text(os.path.join(projects_dir(root), slug, "PROJECT.md")) or ""
    text = re.sub(r"<!--.*?-->", "", text, flags=re.DOTALL)
    fields = {}
    for line in text.splitlines():
        m = re.match(r"^[\s\-*]*\**([a-z_]+)\**\s*[:：]\s*(.+)$", line)
        if m:
            fields[m.group(1)] = clean_value(m.group(2))
        m = re.match(r"^#\s*(?:名前|Name)\s*[:：]\s*(.*?)\s*$", line, re.I)
        if m:
            fields["name"] = m.group(1)
    refs, none, after_head = [], False, False
    for line in text.splitlines():
        m = re.match(r"^[\s\-*]*\**references\**\s*[:：]\s*(.*)$", line, re.I)
        if m:
            v = clean_value(m.group(1))
            after_head = not v
            if v:
                if _is_none_word(v):
                    none = True
                elif filled(v):
                    refs.append(v)
            continue
        if after_head and re.match(r"^\s*[-*]\s+\S", line):
            v = clean_value(re.sub(r"^\s*[-*]\s+", "", line))
            if _is_none_word(v):
                none = True
            elif filled(v):
                refs.append(v)
            continue
        if line.strip():
            after_head = False
    fields["references"] = refs[:MAX_REFERENCES]
    fields["references_none"] = none and not refs
    g = SYN.goal_symbol(fields.get("goal_type", ""))
    if g:
        fields["goal_type"] = g
    ui = SYN.yesno(fields.get("has_ui", ""))
    if ui:
        fields["has_ui"] = ui
    v = SYN.viz_symbol(fields.get("viz", ""))
    if v:
        fields["viz"] = v
    return fields


_PH_LOWER = {p.lower() for p in PLACEHOLDERS}


def filled(v):
    v = (v or "").strip()
    return v.lower() not in _PH_LOWER and len(v) >= 2 and not re.match(r"^[(（]", v)


def sha(paths):
    h = hashlib.sha256()
    for p in paths:
        h.update(os.path.basename(p).encode("utf-8"))
        h.update((read_text(p) or "<none>").encode("utf-8"))
    return h.hexdigest()


# ---------- signed records (.ws/ is written by the engine only) ----------
_WARN = []


def warn_once(msg):
    if msg not in _WARN:
        _WARN.append(msg)


def key_dir():
    o = os.environ.get("CREATECODEBOX_SECRETS")
    return os.path.expanduser(o) if o else os.path.join(os.path.expanduser("~"), ".createcodebox")


def ws_key(create=True):
    """32 random bytes in ~/.createcodebox/.ws_key (created with O_EXCL). None if it can't be read or made."""
    path = os.path.join(key_dir(), ".ws_key")

    def read():
        try:
            with open(path, "rb") as f:
                k = f.read()
            return k if len(k) == 32 else None
        except OSError:
            return None
    k = read()
    if k or os.path.exists(path):
        return k
    if not create:
        return None
    try:
        os.makedirs(key_dir(), mode=0o700, exist_ok=True)
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            os.write(fd, os.urandom(32))
        finally:
            os.close(fd)
    except FileExistsError:
        pass
    except OSError:
        return None
    return read()


def canon(obj):
    o = {k: v for k, v in obj.items() if k not in ("_sig", "_unsigned")} if isinstance(obj, dict) else obj
    return json.dumps(o, sort_keys=True, ensure_ascii=True, separators=(",", ":"))


def sign_text(key, slug, relpath, obj):
    return hmac.new(key, (slug + "\n" + relpath + "\n" + canon(obj)).encode("utf-8"), hashlib.sha256).hexdigest()


def rec_rel(name):
    return ".ws/" + name


def save_rec(root, name, obj, slug=""):
    """Write .ws/<name> with an HMAC. If the key can't be used: write unsigned, warn, and keep the progress."""
    obj = {k: v for k, v in obj.items() if k not in ("_sig", "_unsigned")}
    key = ws_key(create=True)
    if key:
        obj["_sig"] = sign_text(key, slug, rec_rel(name), obj)
    else:
        obj["_unsigned"] = True
        warn_once(T("warn.unsigned"))
    save_json(os.path.join(ws_dir(root), name), obj)


def load_rec(root, name, slug="", default=None):
    """Read .ws/<name>. A record whose signature doesn't match is treated as missing (and a warning is raised)."""
    path = os.path.join(ws_dir(root), name)
    obj = load_json(path)
    if obj is None:
        if os.path.exists(path):
            warn_once(T("warn.sig_mismatch", name=name))
        return default
    if not isinstance(obj, dict):
        warn_once(T("warn.sig_mismatch", name=name))
        return default
    key = ws_key(create=True)
    if key is None:
        if obj.get("_sig") or obj.get("_unsigned"):
            warn_once(T("warn.unsigned"))
            return obj
        warn_once(T("warn.sig_mismatch", name=name))
        return default
    sig = obj.get("_sig")
    if isinstance(sig, str) and hmac.compare_digest(sig, sign_text(key, slug, rec_rel(name), obj)):
        return obj
    warn_once(T("warn.sig_mismatch", name=name))
    return default


REC_PREFIXES = ("approval_", "confirm_", "st_", "schedule_", "publish_check_", "publish_ok_", "repo_", "tasks_")


def slug_of_rec(name):
    for p in REC_PREFIXES:
        if name.startswith(p) and name.endswith(".json"):
            return name[len(p):-5]
    return ""


def resign_all(root):
    """Re-sign every .ws/*.json record with the current key (after the user said `resign`)."""
    if ws_key(create=True) is None:
        return None
    n = 0
    try:
        names = sorted(os.listdir(ws_dir(root)))
    except OSError:
        return 0
    for name in names:
        if not name.endswith(".json"):
            continue
        obj = load_json(os.path.join(ws_dir(root), name))
        if isinstance(obj, dict):
            save_rec(root, name, obj, slug_of_rec(name))
            n += 1
    return n


# ---------- state (.ws/ · the AI cannot write) ----------
def get_state(root):
    return load_rec(root, "state.json", "", {}) or {}


def set_state(root, **kw):
    s = get_state(root)
    s.update(kw)
    s["schema"] = SCHEMA
    save_rec(root, "state.json", s, "")


def get_session(root):
    return load_rec(root, "session.json", "", {}) or {}


def set_session(root, **kw):
    s = get_session(root)
    s.update(kw)
    save_rec(root, "session.json", s, "")


def lang_path(root):
    return os.path.join(ws_dir(root), "lang")


def get_lang(root):
    """The language of the engine's own sentences: CREATECODEBOX_LANG (override), else .ws/lang, else en."""
    e = (os.environ.get("CREATECODEBOX_LANG") or "").strip().lower()
    if re.match(r"^[a-z]{2,5}$", e):
        return e
    t = (read_text(lang_path(root)) or "").strip().lower()
    return t if re.match(r"^[a-z]{2,5}$", t) else "en"


def set_lang(root, code):
    write_text(lang_path(root), code + "\n")


def migrate_legacy(root):
    """0.2 -> schema 3: sign old records, move design/schedule.json and design/systemtest.json into .ws/."""
    p = os.path.join(ws_dir(root), "state.json")
    st = load_json(p)
    if not isinstance(st, dict) or st.get("schema") == SCHEMA:
        return
    names = []
    try:
        names = sorted(os.listdir(ws_dir(root)))
    except OSError:
        pass
    for name in names:
        if name.endswith(".json"):
            obj = load_json(os.path.join(ws_dir(root), name))
            if isinstance(obj, dict):
                save_rec(root, name, obj, slug_of_rec(name))
    for slug in list_projects(root):
        for old, new in (("schedule.json", "schedule_%s.json"), ("systemtest.json", "st_%s.json")):
            op = os.path.join(design_dir(root, slug), old)
            obj = load_json(op)
            if isinstance(obj, dict) and not os.path.exists(os.path.join(ws_dir(root), new % slug)):
                save_rec(root, new % slug, obj, slug)
                try:
                    os.replace(op, op + ".migrated")
                except OSError:
                    pass
    st = get_state(root)
    set_state(root, **{k: v for k, v in st.items() if k not in ("_sig", "_unsigned", "schema")})


# ---------- 設計の検査 ----------
def io_path(root, slug):
    return os.path.join(design_dir(root, slug), "io.json")


def lint_io(root, slug, has_ui):
    data = load_json(io_path(root, slug))
    if not isinstance(data, dict) or not isinstance(data.get("rows"), list):
        return [T("lint.no_io")]
    errs, ids, dirs, kinds = [], set(), set(), set()
    for i, r in enumerate(data["rows"], 1):
        if not isinstance(r, dict):
            errs.append(T("lint.row_shape", n=i))
            continue
        rid = str(r.get("id", ""))
        if not re.match(r"^IO-\d+$", rid):
            errs.append(T("lint.id_form", n=i))
        elif rid in ids:
            errs.append(T("lint.id_dup", id=rid))
        ids.add(rid)
        k = SYN.kind_symbol(str(r.get("kind", "")))
        if k is None:
            errs.append(T("lint.kind", id=rid, kinds=" / ".join(IO_KINDS)))
        else:
            kinds.add(k)
        if r.get("dir") not in ("in", "out"):
            errs.append(T("lint.dir", id=rid))
        else:
            dirs.add(r["dir"])
        for key in ("name", "party", "example", "failure", "prd"):
            if str(r.get(key, "")).strip().lower() in _PH_LOWER:
                errs.append(T("lint.blank", id=rid, label=T("lint.field." + key)))
    if not data["rows"]:
        errs.append(T("lint.no_rows"))
    elif dirs != {"in", "out"}:
        errs.append(T("lint.need_dirs"))
    if has_ui == "yes" and "screen" not in kinds:
        errs.append(T("lint.need_screen"))
    return errs


def brief_sections(root, slug):
    t = read_text(os.path.join(design_dir(root, slug), "ui", "brief.md"))
    if not t:
        return None
    sections, cur = {}, None
    for line in t.splitlines():
        m = re.match(r"^##\s+(.*?)\s*$", line)
        if m:
            cur = SYN.brief_symbol(m.group(1)) or ("?" + m.group(1))
            sections.setdefault(cur, [])
        elif cur is not None and line.strip():
            sections[cur].append(line.strip())
    return sections


def brief_ok(root, slug):
    sections = brief_sections(root, slug)
    if sections is None:
        return False, [T("brief.missing")]
    missing = [n for n in BRIEF_SECTIONS if not sections.get(n)]
    if missing:
        return False, [T("brief.empty", names=" / ".join(T("brief.h." + n) for n in missing))]
    return True, []


def sketch_path(root, slug):
    return os.path.join(design_dir(root, slug), "ui", "sketch.html")


def sketch_ok(root, slug):
    """The first picture: exists, 500 bytes or more, has <body, and the data-ccb="sketch" mark."""
    p = sketch_path(root, slug)
    try:
        if os.path.getsize(p) < 500:
            return False
    except OSError:
        return False
    t = read_text(p) or ""
    return "<body" in t.lower() and bool(re.search(r"""data-ccb\s*=\s*["']sketch["']""", t))


def new_entrance(root, slug):
    """A project that has neither io.json nor brief.md yet (0.2 projects in progress are not asked for a sketch)."""
    d = design_dir(root, slug)
    return not os.path.isfile(os.path.join(d, "io.json")) and not os.path.isfile(os.path.join(d, "ui", "brief.md"))


def ui_files(root, slug):
    d = os.path.join(design_dir(root, slug), "ui")
    return [os.path.join(d, n) for n in ("brief.md", "index.html", "gakaso.txt")
            if os.path.isfile(os.path.join(d, n))]


def ui_proposal_ok(root, slug, viz):
    d = os.path.join(design_dir(root, slug), "ui")
    ok, errs = brief_ok(root, slug)
    if not ok:
        return False, errs
    if viz == "gakaso":
        if not re.search(r"https?://", read_text(os.path.join(d, "gakaso.txt")) or ""):
            return False, [T("ui.no_gakaso_url")]
    elif not os.path.isfile(os.path.join(d, "index.html")):
        return False, [T("ui.no_index")]
    return True, []


def design_hash(root, slug):
    return sha(ui_files(root, slug) + [io_path(root, slug)])


def viz_of(p):
    """B1: blank or a template placeholder means local. A value that is not one of the three is an error (None)."""
    v = p.get("viz", "")
    if v in VIZ:
        return v
    return "local" if not filled(v) else None


# ---------- 段の計算 ----------
def load_schedule(root, slug):
    return load_rec(root, "schedule_%s.json" % slug, slug)


def save_schedule(root, slug, obj):
    save_rec(root, "schedule_%s.json" % slug, obj, slug)


def coverage_gaps(root, slug):
    """D5: every io row needs at least one test case and a schedule row. Returns the io ids that lack either."""
    io = load_json(io_path(root, slug)) or {}
    rows = [r for r in io.get("rows", []) if isinstance(r, dict)]
    sched = load_schedule(root, slug) or {}
    stj = st_load(root, slug) or {"rows": []}
    gaps = []
    for r in rows:
        rid = str(r.get("id", ""))
        has_case = any(c.get("io") == rid for c in stj["rows"])
        has_row = any(s.get("io") == rid or ("(%s)" % rid) in str(s.get("title", "")) or ("（%s）" % rid) in str(s.get("title", ""))
                      for s in sched.get("rows", []))
        if not (has_case and has_row):
            gaps.append(rid)
    return gaps


def compute(root, slug=None):
    """{"stage","slug","name","todo","warn"} を返す。todo は、この段を出るために足りない物。"""
    del _WARN[:]
    c = _compute(root, slug)
    c["warn"] = list(_WARN)
    return c


def _compute(root, slug=None):
    projects = list_projects(root)
    if slug is None:
        slug = get_state(root).get("active")
    if not slug or slug not in projects:
        return {"stage": "R0", "slug": None, "name": "", "todo": [T("todo.r0")]}
    p = parse_project(root, slug)
    base = {"slug": slug, "name": p.get("name", slug)}
    miss = []
    if p.get("goal_type", "") not in GOAL_TYPES:
        miss.append(T("todo.r1.goal"))
    if not filled(p.get("what")):
        miss.append(T("todo.r1.what"))
    if miss:
        return dict(base, stage="R1", todo=miss + [T("todo.format")])
    if new_entrance(root, slug):
        if not references_ok(p):
            miss.append(T("todo.references"))
        if not sketch_ok(root, slug):
            miss.append(T("todo.sketch", slug=slug))
    for k, label in R2_FIELDS:
        if k == "has_ui":
            if p.get(k) not in ("yes", "no"):
                miss.append(T(label))
        elif not filled(p.get(k)):
            miss.append(T(label))
    has_ui = p.get("has_ui")
    if has_ui == "yes":
        viz = viz_of(p)
        if viz is None:
            miss.append(T("todo.r2.viz"))
        else:
            ok, errs = ui_proposal_ok(root, slug, viz)
            if not ok:
                miss.extend(errs)
    if miss:
        if any(not filled(p.get(k)) for k, _ in R2_FIELDS if k != "has_ui") or p.get("has_ui") not in ("yes", "no"):
            miss.append(T("todo.format"))
        return dict(base, stage="R2", todo=miss)
    if has_ui == "yes":
        conf = load_rec(root, "confirm_%s.json" % slug, slug, {}) or {}
        if conf.get("hash") != sha(ui_files(root, slug)):
            return dict(base, stage="R3", todo=[T("todo.r3")])
    errs = lint_io(root, slug, has_ui)
    if errs:
        return dict(base, stage="R4", todo=errs)
    appr = load_rec(root, "approval_%s.json" % slug, slug, {}) or {}
    if appr.get("hash") != design_hash(root, slug):
        return dict(base, stage="R4A", todo=[T("todo.r4a")])
    sched = load_schedule(root, slug)
    gaps = coverage_gaps(root, slug)
    if not isinstance(sched, dict) or not sched.get("rows") or gaps:
        return dict(base, stage="RS", todo=[T("todo.rs")] + ([T("todo.rs.gaps", ids=", ".join(gaps))] if sched and gaps else []))
    st = st_summary(root, slug)
    if all(r.get("status") in ("done", "hold") for r in sched["rows"]) and first_version_done(st):
        return dict(base, stage="DONE", todo=[], st=st)
    return dict(base, stage="RUN", st=st, todo=([T("todo.run.st", u=st["user_pass"], ut=st["user_total"], a=st["ai_pass"], at=st["ai_total"],
                                                    n=st["normal_pass"], nt=st["normal_total"])] if st else []))


def stage_text(c):
    out = T("stage.head", stage=c["stage"], label=stage_label(c["stage"]))
    if c["slug"]:
        out += T("stage.project", name=c["name"], slug=c["slug"])
    if c["todo"]:
        out += T("stage.missing", items=T("sep.list").join(c["todo"]))
    if c["stage"] == "DONE" and c.get("st"):
        s = c["st"]
        out += " " + T("stage.done", u=s["user_pass"], ut=s["user_total"], a=s["ai_pass"], at=s["ai_total"],
                       n=s["total"] - s["pass"]) + " " + T("stage.open", slug=c["slug"])
    if c.get("warn"):
        out += "\n" + "\n".join(c["warn"])
    return out


def round_rule(root, c):
    st = c["stage"]
    if st == "R0" and not list_projects(root):
        return T("rule.R0.empty")
    return T("rule." + st)


def project_list_text(root):
    ps = list_projects(root)
    if not ps:
        return T("list.none")
    lines = []
    for sl in ps:
        c = compute(root, sl)
        miss = missing_materials(root, sl)
        lines.append(T("list.item", slug=sl, name=c["name"], label=stage_label(c["stage"]),
                       extra=T("list.extra", n=len(miss)) if miss else ""))
    return T("list.head") + "\n" + "\n".join(lines)


# ---------- 点検（doctor） ----------
def ancestor_claude_files(root):
    """CLAUDE.md / CLAUDE.local.md in the folders above the workspace (up to HOME). Claude Code reads them at startup."""
    home = os.path.realpath(os.path.expanduser("~"))
    out, d = [], os.path.dirname(root)
    while d and d != os.path.dirname(d):
        for n in ("CLAUDE.md", "CLAUDE.local.md"):
            if os.path.isfile(os.path.join(d, n)):
                out.append(os.path.join(d, n))
        if os.path.realpath(d) == home:
            break
        d = os.path.dirname(d)
    return out


def codex_in_use(root):
    return os.environ.get("CREATECODEBOX_CLIENT") == "codex" or get_session(root).get("client") == "codex"


def ancestor_agents_files(root):
    """AGENTS.md / AGENTS.override.md in the folders above the workspace that Codex reads at startup: from the folder that has
    .git (Codex's project root) down to the workspace. If the workspace has its own .git, there are none."""
    if os.path.exists(os.path.join(root, ".git")):
        return []
    out, d = [], os.path.dirname(root)
    while d and d != os.path.dirname(d):
        for n in ("AGENTS.md", "AGENTS.override.md"):
            if os.path.isfile(os.path.join(d, n)):
                out.append(os.path.join(d, n))
        if os.path.exists(os.path.join(d, ".git")):
            break
        d = os.path.dirname(d)
    return out


def imported_agents_files(root, limit=20):
    """AGENTS.md files inside imported code (projects/*/src/**). Codex loads one when it is started inside that folder."""
    out = []
    for src in sorted(glob.glob(os.path.join(root, "projects", "*", "src"))):
        for dp, dn, fn in os.walk(src):
            dn[:] = [x for x in dn if x not in (".git", "node_modules")]
            for n in fn:
                if n.lower() in ("agents.md", "agents.override.md"):
                    out.append(os.path.relpath(os.path.join(dp, n), root).replace(os.sep, "/"))
            if len(out) >= limit:
                return out
    return out


def codex_lines(root, home=None):
    """doctor lines for Codex: AGENTS.md files that Codex may read and the user's own (never opened here)."""
    lines = []
    for p in ancestor_agents_files(root):
        lines.append("WARN " + T("warn.ancestor_agents", path=p))
    for rel in imported_agents_files(root):
        lines.append("WARN " + T("warn.imported_agents", path=rel))
    h = home or os.path.expanduser("~")
    cdir = os.environ.get("CODEX_HOME") or os.path.join(h, ".codex")
    if os.path.isfile(os.path.join(cdir, "AGENTS.md")) or os.path.isfile(os.path.join(cdir, "AGENTS.override.md")):
        lines.append("INFO " + T("warn.user_agents"))
    return lines


SAFE_ALT_PLACE = re.compile(r"^(?:[A-Za-z]:|/[A-Za-z]|/Users/Shared)/[A-Za-z0-9][A-Za-z0-9._-]*$")


def safe_alt_place(p, h):
    """The place for a home folder whose path has a space or a non-ASCII character (for example C:\\Users\\<Japanese name>):
    a folder with a plain name right under C:/ (Git Bash: /c/) on Windows, or on a Mac right under /Users/Shared/ (one folder per app).
    It is outside the home folder on purpose, so that is not warned. The path must be plain ASCII with no space."""
    odd_home = bool(re.search(r"\s", h)) or any(ord(ch) > 127 for ch in h)
    return odd_home and bool(SAFE_ALT_PLACE.match(p))


def place_check(root, home=None):
    """Where the workspace lives. Returns ("ok", "") or ("warn", reasons). A warning never stops anything."""
    real = os.path.realpath(root)
    home = os.path.realpath(home or os.path.expanduser("~"))
    p = real.replace(os.sep, "/")
    h = home.replace(os.sep, "/").rstrip("/")
    reasons = []
    inside = p == h or p.startswith(h + "/")
    rel = p[len(h):].strip("/") if inside else ""
    top = rel.split("/")[0] if rel else ""
    if top in ("Downloads", "Desktop", "Documents"):
        reasons.append(T("place.why.userfolder", name="~/" + top))
    low = p.lower()
    if "onedrive" in low:
        reasons.append(T("place.why.cloud", name="OneDrive"))
    if "library/mobile documents" in low:
        reasons.append(T("place.why.cloud", name="iCloud"))
    if "dropbox" in low:
        reasons.append(T("place.why.cloud", name="Dropbox"))
    if re.search(r"\s", p) or any(ord(ch) > 127 for ch in p):
        reasons.append(T("place.why.chars"))
    d = os.path.dirname(real)
    while d and d != os.path.dirname(d):
        if os.path.exists(os.path.join(d, ".git")):
            reasons.append(T("place.why.git", path=d))
            break
        d = os.path.dirname(d)
    if not inside and not safe_alt_place(p, h):
        reasons.append(T("place.why.outside"))
    if not reasons:
        return "ok", ""
    return "warn", T("sep.list").join(reasons)


def place_line(root, home=None):
    """The place line in the language of the workspace (.ws/lang or CREATECODEBOX_LANG), whatever language the caller had set."""
    prev = lang._CUR
    lang.use(get_lang(root))
    try:
        state, why = place_check(root, home)
        return T("place.ok") if state == "ok" else T("place.warn", reason=why, fix=T("place.fix"))
    finally:
        lang._CUR = prev


def doctor(root):
    lines = []
    ok = sys.version_info >= (3, 8)
    lines.append("%s %s%s" % ("OK  " if ok else "NG  ", T("doctor.python", v=sys.version.split()[0]), "" if ok else T("doctor.python_old")))
    for p in ancestor_claude_files(root):
        lines.append("WARN " + T("warn.ancestor", path=p))
    if re.search(r"OneDrive|Dropbox|iCloud", root):
        lines.append("WARN " + T("warn.synced"))
    try:
        git_ok = subprocess.call(["git", "--version"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL) == 0
    except OSError:
        git_ok = False
    lines.append("%s %s" % ("OK  " if git_ok else "WARN", T("doctor.git")))
    lines.append(T("doctor.harden", state=T("state.on") if harden_state(root) else T("state.off")))
    lines.append(place_line(root))
    if codex_in_use(root):
        lines.extend(codex_lines(root))
    lines.extend("WARN " + t for t in record_problems(root))
    return lines


# ---------- the quick check at the start of a session ----------
SELF_HEALING_RECORDS = ("state.json", "session.json")  # the engine writes these again by itself


def bad_records(root):
    """Names of the signed records in .ws/ whose signature does not match (edited or broken). Reads only: no warning is raised, nothing is written.
    state.json and session.json are left out: the engine writes them again at the next step."""
    key = ws_key(create=False)
    if key is None:
        return []  # no usable key: that is its own problem (key_problem), not a record problem
    out = []
    try:
        names = sorted(os.listdir(ws_dir(root)))
    except OSError:
        return out
    for name in names:
        if not name.endswith(".json") or name in SELF_HEALING_RECORDS:
            continue
        path = os.path.join(ws_dir(root), name)
        obj = load_json(path)
        if not isinstance(obj, dict):
            out.append(name)
            continue
        sig = obj.get("_sig")
        if not (isinstance(sig, str) and hmac.compare_digest(sig, sign_text(key, slug_of_rec(name), rec_rel(name), obj))):
            out.append(name)
    return out


def record_problems(root):
    """One line for what is wrong with the saved records, and how to go on. A record that was changed or broken is ignored, so the stage
    does not move: an approval is sent again by the user, a check is run again. For the rest the only way the engine has is `resign`
    (the user's own word; it also covers a lost key). There is no repair that skips the signature."""
    bad = bad_records(root)
    lines = []
    if ws_key(create=True) is None:  # the key can't be read, and a new one can't be made
        lines.append(T("problem.key"))
    if not bad:
        return lines
    if len(bad) > 1:
        lines.append(T("problem.rec.many", n=len(bad)))
        return lines
    name = bad[0]
    slug = slug_of_rec(name)
    if name.startswith("confirm_"):
        lines.append(T("problem.rec.confirm", slug=slug))
    elif name.startswith("approval_"):
        lines.append(T("problem.rec.approval", slug=slug))
    elif name.startswith(("publish_check_", "publish_ok_")):
        lines.append(T("problem.rec.publish", slug=slug))
    else:
        lines.append(T("problem.rec.other", name=name))
    return lines


def start_problems(root, event=None):
    """The problems that stop work or can change what the AI reads, from checks that are quick and need no network. Worst first."""
    out = []
    if sys.version_info < (3, 8):
        out.append(T("problem.python_old", v=sys.version.split()[0]))
    out.extend(record_problems(root))
    for pth in ancestor_claude_files(root):
        out.append(T("problem.ancestor", path=pth))
    if place_check(root)[0] == "ok" and re.search(r"OneDrive|Dropbox|iCloud", root):
        out.append(T("problem.synced"))  # when place_check already warns, the place line carries it
    try:
        git_ok = subprocess.call(["git", "--version"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL) == 0
    except OSError:
        git_ok = False
    if not git_ok:
        out.append(T("problem.git"))
    if ADAPTER.NAME == "codex":
        for pth in ancestor_agents_files(root):
            out.append(T("problem.ancestor_agents", path=pth))
        cwd = os.path.realpath((event or {}).get("cwd") or root)
        rel = rel_in_root(root, cwd)
        in_src = bool(rel) and rel.split("/")[:1] == ["projects"] and len(rel.split("/")) >= 3 and rel.split("/")[2] == "src"
        imported = ([rel] if in_src else []) + [x for x in imported_agents_files(root) if not in_src or x != rel]
        for rp in imported:
            out.append(T("problem.imported_agents", path=rp))
        h = os.path.expanduser("~")
        cdir = os.environ.get("CODEX_HOME") or os.path.join(h, ".codex")
        if os.path.isfile(os.path.join(cdir, "AGENTS.md")) or os.path.isfile(os.path.join(cdir, "AGENTS.override.md")):
            out.append(T("problem.user_agents"))
    return out


def start_problem_block(root, event=None, limit=3):
    """The lines for the context at SessionStart: at most `limit` problems, then the one line for the full check. Empty when all is well."""
    probs = start_problems(root, event)
    if not probs:
        return ""
    more = len(probs) - limit
    full = T("problem.full_more", n=more) if more > 0 else T("problem.full")
    return "\n".join([T("problem.header")] + ["- " + x for x in probs[:limit]] + [full])


def version(root):
    return (read_text(os.path.join(root, VERSION_FILE)) or T("version.unknown")).strip()


# ---------- a new version (checked at most once a day) ----------
UPDATE_REC = "update_check.json"
UPDATE_TAG = re.compile(r"^refs/tags/v(\d{1,4})\.(\d{1,4})\.(\d{1,4})$")


def update_every():
    v = os.environ.get("CREATECODEBOX_UPDATE_EVERY", "")
    return int(v) if v.isdigit() else 24 * 3600


def vtuple(s):
    m = re.fullmatch(r"v?(\d{1,4})\.(\d{1,4})\.(\d{1,4})", (s or "").strip())
    return tuple(int(x) for x in m.groups()) if m else None


def update_source(root):
    """Where a new version would come from: this copy's own origin, if it is an https address (a copy of a copy checks
    its own origin, the place `update` pulls from). CREATECODEBOX_UPDATE_URL overrides it. None: no check."""
    url = os.environ.get("CREATECODEBOX_UPDATE_URL", "").strip()
    if url:
        return None if url.startswith("-") else url
    if not os.path.isdir(os.path.join(root, ".git")):
        return None
    try:
        r = git_run(root, ["remote", "get-url", "origin"], timeout=5)
    except (OSError, subprocess.SubprocessError):
        return None
    u = r.stdout.strip()
    return u if r.returncode == 0 and re.fullmatch(r"https://[A-Za-z0-9.-]+(/[\w.-]+){2}/?", u) else None


def update_page(url, latest):
    """The page that says what changed, for a GitHub address. Built here, never taken from what the server sent."""
    m = re.fullmatch(r"https://github\.com/([\w.-]+)/([\w.-]+?)(?:\.git)?/?", url or "")
    return "https://github.com/%s/%s/releases/tag/v%s" % (m.group(1), m.group(2), latest) if m else ""


def update_check_now(root):
    """Ask the source for its version tags. Only the tag names are read, and only names like v1.2.3 count.
    Nothing about the projects is sent. Any failure (offline, no answer in 8 seconds) is quiet."""
    url = update_source(root)
    latest = None
    if url:
        try:
            r = subprocess.run(["git", "ls-remote", "--tags", "--refs", url], capture_output=True, text=True, timeout=8, cwd=root,
                               env=dict(os.environ, GIT_TERMINAL_PROMPT="0", GIT_ASKPASS="", SSH_ASKPASS=""))
            if r.returncode == 0:
                found = [UPDATE_TAG.match(line.split("\t")[-1].strip()) for line in r.stdout.splitlines()]
                vs = [tuple(int(x) for x in m.groups()) for m in found if m]
                latest = "%d.%d.%d" % max(vs) if vs else None
        except (OSError, subprocess.SubprocessError):
            pass
    rec = load_rec(root, UPDATE_REC, "", {}) or {}  # read again now: the user may have turned the check off meanwhile
    rec.update(checked_at=time.time(), latest=latest, url=url or "")
    save_rec(root, UPDATE_REC, rec)
    return rec


def update_off(root):
    return os.environ.get("CREATECODEBOX_UPDATE_CHECK", "").lower() == "off" or bool((load_rec(root, UPDATE_REC, "", {}) or {}).get("off"))


def update_kick(root):
    """At most once a day, start the check without waiting for it. The next hook reads the result."""
    rec = load_rec(root, UPDATE_REC, "", {}) or {}
    if update_off(root) or time.time() - float(rec.get("checked_at") or 0) < update_every():
        return
    if os.environ.get("CREATECODEBOX_UPDATE_SYNC"):
        update_check_now(root)
        return
    rec["checked_at"] = time.time()  # mark first, so two hooks never start two checks
    save_rec(root, UPDATE_REC, rec)
    kw = {"creationflags": 0x00000008 | 0x00000200} if os.name == "nt" else {"start_new_session": True}
    try:
        subprocess.Popen([sys.executable, "-I", os.path.abspath(__file__), "update-check", "--bg"], cwd=root,
                         stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, **kw)
    except OSError:
        pass


def update_note(root, at_start):
    """One line when a newer version is out: at every session start, and at most once a day during a long session.
    Never updates by itself; the user decides."""
    try:
        update_kick(root)
        if update_off(root):
            return ""
        rec = load_rec(root, UPDATE_REC, "", {}) or {}
        latest, cur = vtuple(rec.get("latest")), vtuple(version(root))
        if not latest or not cur or latest <= cur:
            return ""
        if not at_start and time.time() - float(rec.get("announced_at") or 0) < update_every():
            return ""
        rec["announced_at"] = time.time()
        save_rec(root, UPDATE_REC, rec)
        return T("update.note", latest=rec["latest"], current=version(root), page=update_page(rec.get("url"), rec["latest"]) or "-")
    except Exception:  # the check must never stop a session
        return ""


def cmd_update_check(root, arg):
    rec = load_rec(root, UPDATE_REC, "", {}) or {}
    if arg in ("off", "on"):
        rec["off"] = arg == "off"
        save_rec(root, UPDATE_REC, rec)
        return 0, T("update.check_" + arg)
    if arg in ("now", "--bg"):
        rec = update_check_now(root)
        if arg == "--bg":
            return 0, ""
    elif arg:
        return 2, T("usage")
    latest, cur = vtuple(rec.get("latest")), vtuple(version(root))
    off = (" " + T("update.check_is_off")) if update_off(root) else ""
    if not update_source(root):
        return 0, T("update.check_nosource") + off
    if not rec.get("checked_at"):
        return 0, T("update.check_never") + off
    if latest and cur and latest > cur:
        return 0, T("update.check_newer", latest=rec["latest"], current=version(root), page=update_page(rec.get("url"), rec["latest"]) or "-") + off
    if latest:
        return 0, T("update.check_same", current=version(root)) + off
    return 0, T("update.check_unknown") + off


# ---------- 書き込み・コマンドの門 ----------
def rel_in_root(root, target):
    try:
        rel = os.path.relpath(target, root)
    except ValueError:
        return None
    if rel.startswith(".."):
        return None
    return rel.replace(os.sep, "/")


def write_zone(root, stage, slug, target):
    rel = rel_in_root(root, target)
    if rel is None:
        return False, T("zone.outside")
    parts = rel.split("/")
    if parts[0] in PROTECTED_TOP or rel in PROTECTED_FILES:
        return False, T("zone.protected", rel=rel)
    if rel == GANTT_REL:
        return False, T("zone.board", rel=rel)
    if parts[0] != "projects":
        return False, T("zone.not_projects", rel=rel)
    if stage == "R0" or not slug:
        return False, T("zone.r0")
    if len(parts) < 3 or parts[1] != slug:
        return False, T("zone.other_project", slug=slug)
    top = parts[2]
    if top == "design" and len(parts) >= 4 and (parts[3] in ("schedule.json", "systemtest.json", "evidence") or parts[3].endswith(".html") and parts[3] in ("schedule.html", "systemtest.html")):
        return False, T("zone.records", rel=rel)
    if top == "PROJECT.md" or top in ("knowledge", "design"):
        return True, ""
    if top == "src":
        if stage in ("RUN", "DONE"):
            return True, ""
        return False, T("zone.src_locked", label=stage_label(stage))
    return False, T("zone.other", rel=rel)


def readonly_command(cmd):
    cmd = cmd.strip()
    if not cmd or shell_meta(cmd):
        return False
    # The shell removes quotes and backslashes, so "-fprintf" or \-delete is the option itself. Check what the shell will see.
    raw = cmd.split()
    words = [re.sub(r"[\"'\\\\]", "", w) for w in raw]
    head = words[0]
    if head in ("find", "tree", "rg", "git"):
        # The shell also makes words: {-delete,} becomes -delete, and an unquoted *delete can match a file named -delete.
        # These commands have options that write or run, so refuse { } and unquoted * ? [ (a quoted pattern such as "*.md" is fine).
        whole = lambda w: len(w) >= 2 and w[0] in "\"'" and w[-1] == w[0] and w[0] not in w[1:-1]
        if "{" in cmd or any(re.search(r"[*?\[]", w) and not whole(w) for w in raw):
            return False
    if head == "git":
        if len(words) < 2:
            return False
        sub, rest = words[1], words[2:]
        if any(w.startswith("--ou") for w in rest):  # --output, also shortened (--out=…)
            return False
        return sub in READONLY_GIT
    if head == "find":
        return all(w in FIND_OK or FIND_NEWER.match(w) for w in words[1:] if w.startswith("-"))
    if head == "rg":
        # --pre and --hostname-bin run another program.
        return not any(w in ("--pre", "--hostname-bin") or w.startswith(("--pre=", "--hostname-bin=")) for w in words)
    if head == "tree":
        # -o writes the listing to a file, and -R writes 00Tree.html into each folder. Short options can be joined (-aR).
        return not any(w.startswith("--o") or (w.startswith("-") and not w.startswith("--") and ("o" in w[1:] or "R" in w[1:])) for w in words[1:])
    if head == "date":
        return all(w.startswith("+") for w in words[1:])
    return head in READONLY_CMDS


def readonly_compound(root, cmd, cwd):
    """Two read-only steps joined by one `&&` or one `;`, all inside the workspace, no redirects.
    Each step is `cd <inside the workspace>` or one command from READONLY_CMDS whose path arguments are inside the workspace.
    Returns [(words, folder)] for the read-only steps, else None."""
    if "&&" not in cmd and ";" not in cmd:
        return None
    parts = [x.strip() for x in re.split(r"&&|;", cmd)]
    if len(parts) != 2 or not all(parts):
        return None

    def resolve(path, cur):
        path = path.strip("\"'")
        return os.path.realpath(os.path.expanduser(path) if path.startswith("~") else (path if os.path.isabs(path) else os.path.join(cur, path)))
    cur, steps = cwd, []
    for part in parts:
        if shell_meta(part):
            return None
        m = re.match(r"^cd\s+(\S+)$", part)
        if m:
            target = resolve(m.group(1), cur)
            if rel_in_root(root, target) is None:
                return None
            cur = target
            continue
        if not readonly_command(part):
            return None
        words = part.split()
        for w in words[1:]:
            if not w.startswith("-") and rel_in_root(root, resolve(w, cur)) is None:
                return None
        steps.append((words, cur))
    return steps or None


def outside_instruction_file(root, path, cwd):
    if os.path.basename(path).lower() not in ("claude.md", "claude.local.md", "agents.md", "agents.override.md"):
        return False
    t = os.path.realpath(path if os.path.isabs(path) else os.path.join(cwd, path))
    return rel_in_root(root, t) is None


def secret_path(path, cwd):
    t = os.path.realpath(os.path.expanduser(path) if path.startswith("~") else (path if os.path.isabs(path) else os.path.join(cwd, path)))
    return bool(SECRET_FILE.search(t.replace(os.sep, "/")))


def imported_instruction(root, path, cwd):
    t = os.path.realpath(os.path.expanduser(path) if path.startswith("~") else (path if os.path.isabs(path) else os.path.join(cwd, path)))
    rel = rel_in_root(root, t)
    if rel is None:
        return False
    parts = rel.split("/")
    if len(parts) < 4 or parts[0] != "projects" or parts[2] != "src":
        return False
    return parts[-1].lower() in INSTRUCTION_NAMES or ".claude" in parts[3:] or ".codex" in parts[3:]


def glob_hits_secret(cmd, cwd):
    """コマンドの語に、ワイルドカードや ~・$HOME を使って、秘密の置き場を指す物があるか。"""
    for w in cmd.split():
        if w.startswith("-"):
            continue
        w2 = os.path.expandvars(os.path.expanduser(w.strip("\"'")))
        if any(ch in w2 for ch in "*?["):
            pattern = w2 if os.path.isabs(w2) else os.path.join(cwd, w2)
            if any(secret_path(m, cwd) for m in glob.glob(pattern)):
                return True
        elif ("/" in w2 or w2.startswith(".")) and secret_path(w2, cwd):
            return True
    return False


def is_config_path(path):
    b = os.path.basename(path or "").lower()
    return b.endswith(CONFIG_EXT) or b.startswith("docker-compose") or b.startswith(".env")


def is_example_path(path):
    return os.path.basename(path or "").lower() in EXAMPLE_NAMES


def fingerprint(value):
    return hashlib.sha256(value.encode("utf-8", "replace")).hexdigest()[:12]


def _entropy(s):
    import math
    n = len(s)
    return -sum((s.count(ch) / n) * math.log2(s.count(ch) / n) for ch in set(s)) if n else 0.0


def looks_secret(v):
    """Aux check for the generic form: 16+ chars, not a placeholder, not only letters, high enough entropy."""
    if len(v) < 16 or PLACEHOLDER_WORDS.search(v) or len(set(v.lower())) <= 3:
        return False
    if re.fullmatch(r"[A-Za-z_\-]+", v):
        return False  # a name or a phrase made of letters only
    if not re.search(r"[0-9+/=]", v):
        return False
    return _entropy(v) >= 2.8


def _placeholder_body(m):
    body = re.sub(r"^[A-Za-z]{1,10}[_\-.]", "", m.group(0))
    body = re.sub(r"^(live|test)_", "", body)
    return len(set(body.lower())) <= 2


def _jwt_role(payload):
    import base64
    try:
        pad = "=" * (-len(payload) % 4)
        data = json.loads(base64.urlsafe_b64decode((payload + pad).encode("ascii")).decode("utf-8"))
        return data.get("role") if isinstance(data, dict) else None
    except Exception:
        return None


def scan_line(line, path="", config=None):
    """Returns [(kind, matched_text)]. Real-looking secrets only; code that READS a secret is not a hit."""
    out = []
    cfg = is_config_path(path) if config is None else config
    for kind, rx in SPECIFIC_PATTERNS:
        for m in rx.finditer(line):
            if kind != "private-key" and is_example_path(path) and _placeholder_body(m):
                continue
            out.append((kind, m.group(0)))
    for m in URL_PW.finditer(line):
        pw = m.group(1)
        if pw[0] in "${<%[" or PLACEHOLDER_WORDS.search(pw) or len(set(pw.lower())) <= 2 or pw.lower() in ("password", "pass", "secret"):
            continue
        out.append(("url-password", m.group(0)))
    for m in JWT_RE.finditer(line):
        if _jwt_role(m.group(1)) == "service_role":
            out.append(("supabase-service-role", m.group(0)))
    if not is_example_path(path):
        for m in GENERIC_QUOTED.finditer(line):
            if looks_secret(m.group(2)):
                out.append(("generic", m.group(2)))
        if cfg:
            for m in GENERIC_BARE.finditer(line):
                v = m.group(1)
                if v.startswith(BARE_SKIP) or not re.fullmatch(r"[A-Za-z0-9_\-/+=]{16,}", v):
                    continue
                if looks_secret(v):
                    out.append(("generic", v))
    return out


def scan_text(text, path="", config=None):
    found = []
    for i, line in enumerate((text or "").splitlines(), 1):
        for kind, val in scan_line(line, path, config):
            found.append({"kind": kind, "fp": fingerprint(val), "line": i, "path": path})
    return found


def secret_allow(root):
    d = load_rec(root, "secret_allow.json", "", {}) or {}
    v = d.get("fingerprints")
    return set(v) if isinstance(v, list) else set()


def has_key(text, path="", config=None, root=None):
    """True if the text holds something that looks like a real secret (minus fingerprints the user allowed)."""
    found = scan_text(text, path, config)
    if root and found:
        ok = secret_allow(root)
        found = [f for f in found if f["fp"] not in ok]
    return bool(found)


def iter_added_lines(diff):
    """Yield (commit, path, lineno, text) for the added lines of `git log -p` / `git diff` output."""
    commit, path, ln = "", "", 0
    for line in diff.splitlines():
        if line.startswith("@@COMMIT "):
            commit = line[9:17]
        elif line.startswith("+++ "):
            path = line[4:].strip()
            path = path[2:] if path.startswith("b/") else path
        elif line.startswith("@@"):
            m = re.match(r"@@ -\d+(?:,\d+)? \+(\d+)", line)
            ln = int(m.group(1)) - 1 if m else 0
        elif line.startswith("+") and not line.startswith("+++"):
            ln += 1
            yield commit, path, ln, line[1:]


def diff_findings(root, diff):
    allow = secret_allow(root)
    out = []
    for commit, path, ln, text in iter_added_lines(diff):
        for kind, val in scan_line(text, path):
            fp = fingerprint(val)
            if fp not in allow:
                out.append({"commit": commit, "path": path, "line": ln, "kind": kind, "fp": fp})
    return out


def fmt_findings(found, limit=5):
    items = ["%s:%s:%d (%s, fingerprint %s)" % (f.get("commit") or "staged", f["path"], f["line"], f["kind"], f["fp"]) for f in found[:limit]]
    return "; ".join(items) + ("; ..." if len(found) > limit else "")


def staged_has_key(root):
    try:
        out = subprocess.run(["git", "diff", "--cached", "-U0"], cwd=root, capture_output=True, text=True, timeout=20).stdout
    except (OSError, subprocess.SubprocessError):
        return True  # 読めないときは止める側に倒す
    return bool(diff_findings(root, out))


def protect_hit(cmd):
    """The command mentions a workspace-machinery path, even when it is hidden by quotes, backslashes, $x, [s] or *."""
    a = re.sub(r"[\"'\\]", "", cmd)
    b = re.sub(r"\$\{?[A-Za-z_][A-Za-z0-9_]*\}?", "", a)
    c = re.sub(r"\[(.)\]", r"\1", b).replace("*", "").replace("?", "")
    d = re.sub(r"\$[A-Za-z_]", "", a)  # `.w$Xs` where $X is a one-letter (empty) variable
    return any(PROTECT_MENTION.search(f) for f in (cmd, a, b, c, d))


def edit_body(tool, ti):
    parts = [str(ti.get(k, "")) for k in ("content", "new_string", "new_source")]
    for e in ti.get("edits") or []:
        if isinstance(e, dict):
            parts.append(str(e.get("new_string", "")))
    return "\n".join(parts)


def parse_patch(text):
    """Parse an apply_patch text (the format Codex uses). Returns (entries, error).
    entries: [{"op": "add"|"update"|"delete"|"move", "path": str, "added": [str]}], in the order of the patch.
    A patch that is not exactly in the format is an error (the gate stops it): the first line must be `*** Begin Patch`,
    the last `*** End Patch`, and every line in between must be a header or a body line of the right kind."""
    if not isinstance(text, str) or not text.strip():
        return None, "empty"
    lines = [l.rstrip("\r") for l in text.strip().split("\n")]
    if lines[0].strip() != "*** Begin Patch" or lines[-1].strip() != "*** End Patch":
        return None, "no Begin/End"
    entries, cur = [], None
    for l in lines[1:-1]:
        m = PATCH_HEADER.match(l)
        if m:
            kind, path = m.group(1), m.group(2).strip()
            if not path:
                return None, "header without a path"
            if kind == "Move to":
                if cur is None or cur["op"] != "update" or cur.get("moved"):
                    return None, "Move to without Update File"
                cur["moved"] = True
                entries.append({"op": "move", "path": path, "added": []})
                continue
            cur = {"op": kind.split()[0].lower(), "path": path, "added": []}
            entries.append(cur)
            continue
        if cur is None:
            return None, "text before the first header"
        if cur["op"] == "delete":
            return None, "body under Delete File"
        if cur["op"] == "add":
            if not l.startswith("+"):
                return None, "Add File line without +"
            cur["added"].append(l[1:])
            continue
        # update: @@ (with or without text), a context line (space or empty), - removed, + added, *** End of File
        if l.startswith("@@") or l.strip() == "*** End of File" or l == "" or l[0] in " -":
            continue
        if l.startswith("+"):
            cur["added"].append(l[1:])
            continue
        return None, "unknown line in Update File"
    if not entries:
        return None, "no file"
    return entries, ""


def patch_in_command(cmd):
    """The patch text inside a shell command (`apply_patch <<'EOF' ... EOF`), else None."""
    if "*** Begin Patch" not in cmd:
        return None
    i = cmd.index("*** Begin Patch")
    j = cmd.rfind("*** End Patch")
    if j < i:
        return cmd[i:] + "\n"  # no end line: parse_patch will refuse it
    return cmd[i:j + len("*** End Patch")]


def check_edit_path(root, stage, slug, cwd, p, where, tool="Edit", exists_ok=True):
    """The write-zone checks of one file edit (shared by Edit/Write/MultiEdit and apply_patch). Reason or None."""
    target = os.path.realpath(p if os.path.isabs(p) else os.path.join(cwd, p))
    ok, why = write_zone(root, stage, slug, target)
    if not ok:
        return T("deny.with_where", why=why, where=where)
    rel = rel_in_root(root, target) or ""
    if tool == "Write" and re.match(r"^projects/[^/]+/PROJECT\.md$", rel) and os.path.isfile(target):
        return T("deny.project_write")
    if slug and rel.startswith("projects/%s/src/" % slug) and is_first_turn(root):
        return T("deny.first_turn")
    return None


def gate_patch(root, stage, slug, cwd, patch, where):
    """apply_patch: every path in the patch goes through the same checks as Edit/Write. One refusal stops the whole patch.
    A patch that cannot be parsed is stopped too."""
    entries, err = parse_patch(patch)
    if entries is None:
        return T("deny.patch_unreadable")
    by_path = {}
    for en in entries:
        p = en["path"]
        abs_p = p if os.path.isabs(p) else os.path.join(cwd, p)
        if secret_path(p, cwd):
            return T("deny.secret")
        if imported_instruction(root, p, cwd):
            return T("deny.imported_instr")
        # Add File on a file that already exists replaces all of it: the same as Write
        kind = "Write" if en["op"] == "add" and os.path.isfile(os.path.realpath(abs_p)) else "Edit"
        why = check_edit_path(root, stage, slug, cwd, p, where, tool=kind)
        if why:
            return why
        by_path.setdefault(p, []).extend(en["added"])
    for p, added in by_path.items():
        if added and has_key("\n".join(added), p, root=root):
            return T("deny.key_in_write")
    return None


def is_first_turn(root):
    return int(get_session(root).get("prompts", 0)) <= 1


def gate(root, event):
    """PreToolUse。止めるときは理由の文字列、通すときは None。"""
    tool = event.get("tool_name", "")
    ti = event.get("tool_input") or {}
    cwd = event.get("cwd") or root
    c = compute(root)
    stage, slug = c["stage"], c["slug"]
    where = stage_text(c).split("\n")[0]
    secret_msg = T("deny.secret")
    if tool in ("Read", "NotebookRead", "Grep", "Glob") or tool in EDIT_TOOLS:
        for k in ("file_path", "notebook_path", "path"):
            p = ti.get(k)
            if isinstance(p, str) and p and secret_path(p, cwd):
                return secret_msg
            if isinstance(p, str) and p and imported_instruction(root, p, cwd):
                return T("deny.imported_instr")
    if tool in EDIT_TOOLS:
        p0 = ti.get("file_path") or ti.get("notebook_path") or ""
        if has_key(edit_body(tool, ti), str(p0), root=root):
            return T("deny.key_in_write")
    triage = T("deny.triage") if triage_pending(root, c) else None  # this turn's message is not sorted onto the task board yet: nothing may write
    if tool == PATCH_TOOL:
        return gate_patch(root, stage, slug, cwd, ti.get("command") if isinstance(ti.get("command"), str) else "", where) or triage
    if tool == "Bash":
        if ti.get("dangerouslyDisableSandbox"):
            return T("deny.sandbox_off")
        cmd0 = (ti.get("command") or "").strip()
        if not WS_CMD.match(cmd0) and any(imported_instruction(root, w.strip("\"'"), cwd) for w in cmd0.split()):
            return T("deny.imported_instr_cmd")
        if not WS_CMD.match(cmd0) and (SECRET_CMD.search(cmd0) or glob_hits_secret(cmd0, cwd)):
            return secret_msg
        if "*** Begin Patch" in cmd0 and not WS_CMD.match(cmd0):
            why = gate_patch(root, stage, slug, cwd, patch_in_command(cmd0), where)  # a patch typed into the shell: the same checks
            if why:
                return why
        if GIT_RAW.search(cmd0) and not WS_CMD.match(cmd0):
            return T("deny.raw_git")
        if GH_RAW.search(cmd0) and not WS_CMD.match(cmd0):
            return T("deny.gh")
        if re.search(r"\bgit\s+add\b.*(\s-f\b|--force|\.env)", cmd0):
            return T("deny.git_force")
    if re.search("gakaso", tool, re.I) and not GAKASO_READ.search(tool):
        if not slug:
            return T("deny.gakaso_no_project", where=where)
        ok, errs = brief_ok(root, slug)
        if not ok:
            return T("deny.gakaso_no_brief", why=T("sep.list").join(errs))
        return triage
    if tool in ("Read", "NotebookRead"):
        p = ti.get("file_path") or ti.get("notebook_path") or ""
        if p and outside_instruction_file(root, p, cwd):
            return T("deny.outside_instr")
        return None
    if tool in EDIT_TOOLS:
        p = ti.get("file_path") or ti.get("notebook_path") or ""
        if not p:
            return T("deny.no_target", where=where)
        return check_edit_path(root, stage, slug, cwd, p, where, tool=tool) or triage
    if tool == "Bash":
        cmd = (ti.get("command") or "").strip()
        if WS_CMD.match(cmd) and shell_meta(cmd):
            return T("deny.meta") + " " + T("deny.meta_hint")
        if WS_CMD.match(cmd):
            if triage and not triage_ws_ok(cmd):
                return triage
            if " with-secrets" in cmd and " -- " in cmd:
                inner = cmd.split(" -- ", 1)[1]
                if (SECRET_CMD.search(inner) or glob_hits_secret(inner, cwd) or INLINE_CODE.search(inner)
                        or any(imported_instruction(root, w.strip("\"'"), cwd) for w in inner.split())):
                    return T("deny.with_secrets_inner")
            return None
        m = MCP_CMD.match(cmd)
        if m and not shell_meta(cmd):
            if m.group(1) in ("list", "get"):
                return None
            toks = cmd.split()
            scopes = [toks[i + 1] for i, t in enumerate(toks[:-1]) if t in ("-s", "--scope")]
            if stage not in ("R0", "R1") and all(s in ("project", "local") for s in scopes):
                return triage
            return T("deny.mcp_add", where=where)
        if readonly_command(cmd):
            words = cmd.split()
            if words[0] in ("cat", "head", "tail") and any(outside_instruction_file(root, w, cwd) for w in words[1:]):
                return T("deny.outside_instr_cmd")
            return None
        steps = readonly_compound(root, cmd, cwd)
        if steps is not None:
            for words, folder in steps:
                if words[0] in ("cat", "head", "tail") and any(outside_instruction_file(root, w, folder) for w in words[1:]):
                    return T("deny.outside_instr_cmd")
            return None
        if stage in ("RUN", "DONE"):
            if protect_hit(cmd):
                return T("deny.protect")
            if is_first_turn(root):
                return T("deny.first_turn")
            return triage  # a command that is not read-only waits until the message is sorted onto the board
        return T("deny.stage_cmd", where=where) + ((" " + T("deny.meta_hint")) if shell_meta(cmd) else "")
    if tool.startswith("mcp__"):
        # an MCP server the user added: a tool whose own name (not the server name) says it writes waits
        # for the build stage, as src/ does; after that the user decides what the server may do (docs/security.md)
        if WRITE_NAME.search(tool.split("__", 2)[-1]):
            if stage not in ("RUN", "DONE"):
                return T("deny.mcp_write_stage", tool=tool, where=where)
            if is_first_turn(root):
                return T("deny.first_turn")
            return triage
        return None
    if tool not in SAFE_TOOLS and WRITE_NAME.search(tool or ""):
        return T("deny.unknown_write", tool=tool)  # a built-in tool this gate does not know, and its name says it writes: stopped
    return None


# ---------- hook の本体 ----------
def norm_input(s):
    """NFKC, ’ -> ', and no trailing punctuation or spaces."""
    s = nfkc(s).replace("’", "'").strip()
    return re.sub(r"[\s。．.!！?？~〜…、,，;；:：]+$", "", s)


def within_limit(s):
    """6 words (20 characters when the input has Japanese or other CJK text)."""
    if lang.has_cjk(s):
        return len(s) <= 20
    return len(re.findall(r"[A-Za-z0-9']+", s)) <= 6


def negative_text(s):
    return bool(FORBID_EN.search(s.lower()) or FORBID_JA.search(s))


def en_core(s):
    t = re.sub(r"\s+", " ", s.lower()).strip()
    t = _EN_FILLER_HEAD.sub("", t + " ").strip()
    t = _EN_FILLER_TAIL.sub("", t).strip(" ,.!")
    return t


def is_phrase(prompt, ja_rx, en_rx):
    s = norm_input(prompt)
    if not s or not within_limit(s) or negative_text(s):
        return False
    return bool(ja_rx.match(s) or en_rx.match(en_core(s)))


def is_confirm(prompt):
    return is_phrase(prompt, CONFIRM_RE, CONFIRM_EN)


def is_approve(prompt):
    return is_phrase(prompt, APPROVE_RE, APPROVE_EN)


def is_publish(prompt):
    return is_phrase(prompt, PUBLISH_RE, PUBLISH_EN)


def short_affirm(prompt):
    """A short positive input (6 words / 20 chars, no negative word). If it was not recorded, the user is told how to approve."""
    s = norm_input(prompt)
    if not s or not within_limit(s) or negative_text(s):
        return False
    return bool(AFFIRM_EN.search(s.lower()) or AFFIRM_JA.search(s))


def is_confirm_yes(prompt):
    """A short, plain yes (NFKC, trailing punctuation ignored). Used only for the answer to the approval question."""
    s = norm_input(prompt)
    if not s or len(s) > 30:
        return False
    return bool(YES_JA.match(s) or YES_EN.match(re.sub(r"\s+", " ", s.lower())))


# ---------- triage: a new requirement must reach the task board ----------
TRIAGE_STAGES = ("RS", "RUN", "DONE")  # after the approval. Before it, the answers go into PROJECT.md and the design
SOFT_STAGES = ("R1", "R2", "R3", "R4", "R4A")
ACK_EN = re.compile(r"(?<![A-Za-z'])(please|thanks|thank|you|to|me|it|that|this|is|so|very|much|ahead|on|next|then|now|for|the|all|right|sounds?|a|i|we|let's|lets|as|planned|proceed)(?![A-Za-z'])")
ACK_JA = re.compile(r"します|ます|です|ください|ございます|続け|続き|続行|進めて|ね|よ|な|か|で|を|は|も|、|。")
NUMS_ONLY = re.compile(r"^[\d\s,、，.\-~〜～・と]+((all )?(pass|passed|ok|okay)|合格|オーケー)?[\s.。!！]*$")
ALL_PASS = re.compile(r"^(all|全部|全て|すべて)\s*(pass|passed|ok|okay|合格)?[\s.。!！]*$")
CONTINUE_RE = re.compile(r"^(continue|resume|go on|carry on|keep going|new|続き|つづき|続けて|続行|再開|新規|新しく)[\s.。!！?？]*$")


def bare_ack(prompt):
    """A short yes with nothing else in it ("ok", "looks good", "はい、お願いします"). "yes, and add a CSV export" is not one."""
    if not short_affirm(prompt):
        return False
    t = AFFIRM_EN.sub(" ", norm_input(prompt).lower())
    t = AFFIRM_JA.sub("", ACK_EN.sub(" ", t))
    return not re.search(r"[A-Za-z0-9぀-ヿ㐀-鿿]", ACK_JA.sub("", t))


def trivial_prompt(prompt):
    """A message that cannot add a requirement, a problem, a to-do or a date: an approval, a plain yes, check numbers, or continue / new."""
    s = norm_input(prompt)
    if not s:
        return True
    if is_confirm(prompt) or is_approve(prompt) or is_publish(prompt) or is_confirm_yes(prompt) or bare_ack(prompt):
        return True
    low = s.lower()
    return bool(NUMS_ONLY.match(low) or ALL_PASS.match(low) or CONTINUE_RE.match(low))


def triage_pending(root, c, sess=None):
    """The latest message of this turn still has to be sorted onto the task board (task add / set / date, or task none)."""
    sess = sess if sess is not None else get_session(root)
    t = sess.get("triage")
    return (isinstance(t, dict) and t.get("n") == sess.get("prompts") and bool(c.get("slug")) and c.get("stage") in TRIAGE_STAGES)


def ws_sub(cmd):
    """The ws.sh subcommand words of a command that matches WS_CMD (["task", "add", ...])."""
    m = WS_CMD.match(cmd)
    return cmd[m.end():].split() if m else []


TRIAGE_WS_OK = {"task", "tasks", "status", "list", "doctor", "version", "lint", "learn", "open", "lang", "select", "new"}


def triage_ws_ok(cmd):
    sub = ws_sub(cmd)
    return bool(sub) and (sub[0] in TRIAGE_WS_OK or sub[:2] == ["st", "list"])


def t_in(code, msg_id, **kw):
    """T() in another language for one call (the question to the user is asked in the language of the user's message)."""
    prev = lang._CUR
    lang.use(code)
    try:
        return T(msg_id, **kw)
    finally:
        lang._CUR = prev


def confirm_hash(root, slug, kind):
    """What the approval binds to: the look for R3 (looks good), the look and the table for R4A (approve)."""
    return sha(ui_files(root, slug)) if kind == "r3" else design_hash(root, slug)


def auto_select(root):
    """D1: exactly one project and none selected -> select it. Returns its name, else None."""
    ps = list_projects(root)
    if len(ps) == 1 and get_state(root).get("active") not in ps:
        set_state(root, active=ps[0])
        set_session(root, auto_selected=True)
        return parse_project(root, ps[0]).get("name", ps[0])
    return None


def reply_lang(root):
    return get_session(root).get("reply_lang") or get_lang(root)


def on_session_start(root, event):
    src = event.get("source", "startup")
    if src in ("startup", "clear"):  # a new conversation. resume and compact keep the counters (D1 and C1 depend on them)
        set_session(root, prompts=0, last_prompt="", started_at=time.time(), auto_selected=False, numbered={}, st_list_at=-99,
                    prompt_used_for_mark=0, pending_confirm=None)
        set_state(root, active=None)
    cont = auto_select(root) if src in ("startup", "clear", "resume") else None
    c = compute(root)
    c["warn"] = []  # a signature problem is reported once, in the problem lines below, with a way to go on
    parts = ["Reply in: " + reply_lang(root), stage_text(c), place_line(root), project_list_text(root), round_rule(root, c)]
    if cont:
        parts.append(continuing_note(root, cont))
    board = task_session_block(root, c, skip_active=bool(cont))
    if board:
        parts.append(board)
    warn = board_warn(root)
    if warn:
        parts.append(warn)
    block = start_problem_block(root, event)
    if block:
        parts.append(block)
    upd = update_note(root, at_start=True)
    if upd:
        parts.append(upd)
    return "\n".join(parts)


def not_recorded_note(word_id):
    return T("note.not_recorded", word=T(word_id))


def on_prompt(root, event):
    prompt = event.get("prompt") or ""
    if not os.path.exists(lang_path(root)) and not os.environ.get("CREATECODEBOX_LANG") and re.search(r"[A-Za-z぀-ヿ㐀-鿿]", prompt):
        set_lang(root, lang.detect(prompt, "en"))
    lang.use(get_lang(root))
    sess = get_session(root)
    n = int(sess.get("prompts", 0)) + 1
    rl = lang.detect(prompt, default=sess.get("reply_lang") or get_lang(root))
    extra = {"started_at": time.time()} if not sess.get("started_at") else {}
    pend = sess.get("pending_confirm") if isinstance(sess.get("pending_confirm"), dict) else None  # the approval question asked in the last turn
    set_session(root, prompts=n, last_prompt=prompt, reply_lang=rl, pending_confirm=None, triage=None, **extra)  # both live for one turn only
    cont = auto_select(root) if n == 1 else None
    if n == 1 and not cont and sess.get("auto_selected") and get_state(root).get("active"):
        cont = parse_project(root, get_state(root)["active"]).get("name", get_state(root)["active"])
    c = compute(root)
    notes = []
    slug = c["slug"]
    recorded = False
    if slug and c["stage"] == "R3" and is_confirm(prompt):
        save_rec(root, "confirm_%s.json" % slug, {"hash": sha(ui_files(root, slug))}, slug)
        notes.append(T("note.recorded.r3"))
        recorded = True
        c = compute(root)
    elif slug and c["stage"] == "R4A" and is_approve(prompt):
        save_rec(root, "approval_%s.json" % slug, {"hash": design_hash(root, slug)}, slug)
        notes.append(T("note.recorded.r4a"))
        recorded = True
        c = compute(root)
    # Two-step approval: a natural short yes at R3 / R4A started a question last turn. Only the very next prompt, in the same project,
    # for the same look (and table), and only a plain yes from the small list, records it. The words come from the hook's prompt, never from the AI.
    if not recorded and pend and slug and is_confirm_yes(prompt):
        kind = CONFIRM_KIND.get(c["stage"])
        h = confirm_hash(root, slug, kind) if kind else None
        if kind and pend.get("kind") == kind and pend.get("slug") == slug and pend.get("n") == n - 1 and pend.get("hash") == h:
            rec = {"hash": h, "via": "confirm", "quote": str(pend.get("quote", ""))[:120], "confirm_quote": prompt.strip()[:60],
                   "asked_prompt": n - 1, "prompt": n}
            save_rec(root, ("confirm_%s.json" if kind == "r3" else "approval_%s.json") % slug, rec, slug)
            notes.append(T("note.recorded." + kind))
            notes.append(T("note.recorded.via_confirm"))
            recorded = True
            c = compute(root)
    pub_ready = False
    if slug:
        chk = load_rec(root, "publish_check_%s.json" % slug, slug, {}) or {}
        head = repo_head(root, slug)
        okp = load_rec(root, "publish_ok_%s.json" % slug, slug, {}) or {}
        pub_ready = bool(chk.get("ok") and head and chk.get("head") == head and okp.get("head") != head)
        if is_publish(prompt):
            if chk.get("ok") and head and chk.get("head") == head:
                save_rec(root, "publish_ok_%s.json" % slug, {"head": head}, slug)
                notes.append(T("note.recorded.publish"))
                recorded = True
            else:
                notes.append(T("note.publish_needs_check"))
                recorded = True
    asked = False
    if not recorded and slug and short_affirm(prompt):
        kind = CONFIRM_KIND.get(c["stage"])
        if kind and not is_confirm_yes(prompt):
            # a natural reply (not the exact word): do not record it. Save what the approval would bind to, and have the AI ask one fixed question.
            set_session(root, pending_confirm={"kind": kind, "slug": slug, "hash": confirm_hash(root, slug, kind), "n": n, "quote": prompt.strip()[:120]})
            notes.append(T("note.confirm_ask", question=t_in(rl, "confirm.q." + kind)))
            asked = True
        elif c["stage"] == "R3":
            notes.append(not_recorded_note("word.r3"))
        elif c["stage"] == "R4A":
            notes.append(not_recorded_note("word.r4a"))
        elif pub_ready:
            notes.append(not_recorded_note("word.publish"))  # publish has no two-step: only the exact word records it
    if pend and not recorded and not asked:
        notes.append(T("note.confirm_cleared"))  # the next message was not a plain yes: nothing is recorded
    first = ""
    if n == 1 and c["stage"] == "R0" and list_projects(root):
        first = T("note.first_r0")
    if cont:
        notes.insert(0, continuing_note(root, cont))
    needs = needs_text(root, slug)
    rl2 = repo_line(root, slug)
    if rl2:
        needs = (needs + "\n" + rl2) if needs else rl2
    triage = bool(slug) and c["stage"] in TRIAGE_STAGES and not trivial_prompt(prompt)
    if triage:
        set_session(root, triage={"n": n, "quote": " ".join(prompt.split())[:60]})
    soft = bool(slug) and c["stage"] in SOFT_STAGES and not trivial_prompt(prompt)
    digest = task_prompt_digest(root, c, triage, soft)
    warn = board_warn(root)  # after the approval records above: the stage on the page may have changed
    upd = update_note(root, at_start=False)
    return "\n".join(x for x in ["Reply in: " + rl, stage_text(c), round_rule(root, c), needs, first] + notes + [digest, warn, upd] if x)


def _msg_text(m):
    if isinstance(m, str):
        return m
    if isinstance(m, dict):
        c = m.get("content", m.get("text", ""))
        if isinstance(c, str):
            return c
        if isinstance(c, list):
            return " ".join(b.get("text", "") for b in c if isinstance(b, dict) and b.get("type") == "text")
    return ""


def last_assistant_text(event):
    """C5: last_assistant_message from the hook input, else the last assistant turn in the transcript, else None."""
    m = _msg_text(event.get("last_assistant_message"))
    if m.strip():
        return m
    tp = event.get("transcript_path")
    if not isinstance(tp, str) or not tp:
        return None
    try:
        with open(os.path.expanduser(tp), "rb") as f:
            f.seek(0, 2)
            size = f.tell()
            f.seek(max(0, size - 400000))
            lines = f.read().decode("utf-8", "replace").splitlines()
    except OSError:
        return None
    for line in reversed(lines):
        try:
            o = json.loads(line)
        except ValueError:
            continue
        if not isinstance(o, dict):
            continue
        msg = o.get("message") if isinstance(o.get("message"), dict) else o
        if (o.get("type") == "assistant") or (isinstance(msg, dict) and msg.get("role") == "assistant"):
            t = _msg_text(msg)
            if t.strip():
                return t
    return None


def on_stop(root, event):
    if event.get("stop_hook_active"):
        return None
    c = compute(root)
    if c["stage"] == "R0" and len(list_projects(root)) >= 1 and int(get_session(root).get("prompts", 0)) >= 1:
        txt = last_assistant_text(event)
        if txt is None or re.search(r"\b(continu\w*|new)\b|続き|新規", txt, re.I):
            return None
        return T("stop.ask")
    sess = get_session(root)
    if triage_pending(root, c, sess) and not sess["triage"].get("blocked"):
        set_session(root, triage=dict(sess["triage"], blocked=True))  # block once: the second Stop passes even if the board was not touched
        return T("stop.triage")
    return None


# ---------- コマンド（ws.sh から） ----------
def cmd_select(root, slug, quote, new=False, name=None):
    s = get_session(root)
    existing = list_projects(root)
    need = 1 if (not existing or (new and s.get("auto_selected"))) else 2
    if int(s.get("prompts", 0)) < need:
        return 2, T("select.need_answer")
    if not quote or quote.strip() not in s.get("last_prompt", ""):
        return 2, T("select.need_quote")
    if new:
        if not re.match(r"^[a-z0-9]+(-[a-z0-9]+)*$", slug):
            return 2, T("select.bad_name")
        nums = [int(x[:2]) for x in existing if re.match(r"^\d\d_", x)]
        folder = "%02d_%s" % ((max(nums) + 1) if nums else 1, slug)
        pd = os.path.join(projects_dir(root), folder)
        for sub in ("knowledge", os.path.join("design", "ui"), "src"):
            os.makedirs(os.path.join(pd, sub), exist_ok=True)
        write_text(os.path.join(pd, "src", ".gitkeep"), "")
        write_text(os.path.join(pd, "src", ".gitignore"), ".env\n.env.*\n!.env.example\nnode_modules/\n__pycache__/\n.DS_Store\n")
        kr = read_text(os.path.join(root, "ws", "templates", "knowledge_README.md"))
        if kr:
            write_text(os.path.join(pd, "knowledge", "README.md"), kr)
        write_text(os.path.join(pd, "knowledge", "_needed.md"), T("needed.template"))
        write_text(os.path.join(pd, "PROJECT.md"), T("project.template", NAME=name or slug))
        set_state(root, active=folder)
        set_session(root, auto_selected=False, triage=None)
        return 0, T("select.created", folder=folder) + ("\n" + open_block(root, folder) if open_block(root, folder) else "")
    if slug not in existing:
        return 2, T("select.none", slug=slug)
    set_state(root, active=slug)
    set_session(root, auto_selected=False, triage=None)
    return 0, T("select.selected", slug=slug) + select_summary(root, slug) + ("\n" + open_block(root, slug) if open_block(root, slug) else "")


INTAKE_MAX = 20 * 1024 * 1024
INSTRUCTION_NAMES = ("claude.md", "claude.local.md", "agents.md", "agents.override.md")
SECRET_NAME = re.compile(r"(\.(pem|key|p12|pfx)$|^id_(rsa|ed25519|ecdsa)|^\.netrc$)", re.I)


NEEDED_HEADERS = {"材料の名前", "material", "name"}
NEEDED_STATE = {"なし": "missing", "missing": "missing", "no": "missing", "none": "missing",
                "未確認": "unchecked", "unchecked": "unchecked", "not checked": "unchecked", "unknown": "unchecked",
                "あり": "have", "have": "have", "yes": "have",
                "不要": "not needed", "not needed": "not needed", "n/a": "not needed"}


def needed_rows(root, slug):
    t = read_text(os.path.join(projects_dir(root), slug, "knowledge", "_needed.md")) or ""
    rows = []
    for line in t.splitlines():
        if not line.strip().startswith("|"):
            continue
        cells = [x.strip() for x in line.strip().strip("|").split("|")]
        if len(cells) < 4 or cells[0].lower() in NEEDED_HEADERS or cells[0] == "" or set(cells[0]) <= set("-: "):
            continue
        rows.append(cells[:4])
    return rows


def missing_materials(root, slug):
    """Names of the missing materials (status missing / not checked, or have but not brought in yet)."""
    out = []
    for name, state, where, placed in needed_rows(root, slug):
        st = NEEDED_STATE.get(nfkc(state).strip().lower())
        if st in ("missing", "unchecked"):
            out.append("%s (%s)" % (name, T("needed.state." + st)))
        elif st == "have" and not placed:
            out.append("%s (%s)" % (name, T("needed.state.before")))
    return out


def needs_text(root, slug):
    if not slug:
        return ""
    miss = missing_materials(root, slug)
    if not miss:
        return ""
    return T("note.needs", items=T("sep.item").join(miss))


def cmd_intake(root, src):
    """利用者が示した 1 ファイルを、選んだプロジェクトの knowledge/files/ にコピーする（中身は読まない）。"""
    c = compute(root)
    if not c["slug"] or c["stage"] == "R0":
        return 2, T("common.need_project")
    p = os.path.realpath(os.path.expanduser(src))
    if not os.path.isfile(p):
        return 1, T("intake.not_file", src=src)
    base = os.path.basename(p)
    if base.lower() in INSTRUCTION_NAMES:
        return 1, T("intake.instr")
    if SECRET_FILE.search(p.replace(os.sep, "/")) or SECRET_NAME.search(base):
        return 1, T("intake.secret")
    rel = rel_in_root(root, p)
    if rel is not None and rel.split("/")[0] in PROTECTED_TOP:
        return 1, T("intake.protected")
    if os.path.getsize(p) > INTAKE_MAX:
        return 1, T("intake.too_big")
    d = os.path.join(projects_dir(root), c["slug"], "knowledge", "files")
    os.makedirs(d, exist_ok=True)
    stem, ext = os.path.splitext(base)
    dest, n = os.path.join(d, base), 2
    while os.path.exists(dest):
        dest = os.path.join(d, "%s-%d%s" % (stem, n, ext))
        n += 1
    shutil.copy2(p, dest)
    return 0, T("intake.done", dest=rel_in_root(root, dest), src=p)


# ---------- 学びカードと GitHub（repo・save・backup・publish） ----------
def learn_seen(root):
    return (load_rec(root, "learn.json", "", {}) or {}).get("seen", [])


def mark_seen(root, topic):
    seen = learn_seen(root)
    if topic not in seen:
        seen.append(topic)
        save_rec(root, "learn.json", {"seen": seen}, "")


def card_text(root, topic):
    """ws/learn/<lang>/<name>.md, else ws/learn/<name>.md, else the English card."""
    if not re.match(r"^[a-z][a-z-]*$", topic or ""):
        return None
    base = os.path.join(root, "ws", "learn")
    for p in (os.path.join(base, get_lang(root), topic + ".md"), os.path.join(base, topic + ".md"), os.path.join(base, "en", topic + ".md")):
        t = read_text(p)
        if t is not None:
            return t
    return None


def card_names(root):
    base = os.path.join(root, "ws", "learn")
    names = set()
    for d in (base, os.path.join(base, get_lang(root)), os.path.join(base, "en")):
        try:
            names.update(n[:-3] for n in os.listdir(d) if n.endswith(".md") and not n.startswith("_"))
        except OSError:
            pass
    return sorted(names)


def learn_index(root):
    """ws/learn/<lang>/_index.md (else the English one). None if there is none."""
    base = os.path.join(root, "ws", "learn")
    for p in (os.path.join(base, get_lang(root), "_index.md"), os.path.join(base, "en", "_index.md")):
        t = read_text(p)
        if t is not None:
            return t.rstrip()
    return None


def cmd_learn(root, topic=None):
    if not topic:
        names = card_names(root)
        seen = learn_seen(root)
        idx = learn_index(root)
        if idx:
            out = idx
            read = [n for n in names if n in seen]
            if read:
                out += "\n\n" + T("learn.seen", names=", ".join(read))
            return 0, out
        if not names:
            return 0, T("learn.none")
        return 0, T("learn.header") + "\n" + "\n".join("  %s %s" % ("✓" if n in seen else " ", n) for n in names)
    t = card_text(root, topic)
    if t is None:
        return 2, T("learn.unknown", topic=topic)
    mark_seen(root, topic)
    return 0, t


def need_card(root, command):
    """初めて使う操作の前に、学びカードを 1 枚見せる。見せたら、もう一度実行してもらう。"""
    topic = CARD_FOR.get(command)
    if not topic or topic in learn_seen(root):
        return None
    t = card_text(root, topic)
    if t is None:
        return None
    mark_seen(root, topic)
    return 3, t + "\n\n---\n" + T("learn.again")


def src_of(root):
    c = compute(root)
    if not c["slug"] or c["stage"] == "R0":
        return None, None
    return c["slug"], os.path.join(projects_dir(root), c["slug"], "src")


def git_run(d, args, timeout=120, noprompt=True, extra_env=None):
    env = dict(os.environ)
    if noprompt:
        env["GIT_TERMINAL_PROMPT"] = "0"
    if extra_env:
        env.update(extra_env)
    return subprocess.run(["git", "-C", d] + args, capture_output=True, text=True, timeout=timeout, env=env)


def repo_head(root, slug):
    d = os.path.join(projects_dir(root), slug, "src")
    if not os.path.isdir(os.path.join(d, ".git")):
        return None
    try:
        r = git_run(d, ["rev-parse", "HEAD"], timeout=20)
    except (OSError, subprocess.SubprocessError):
        return None
    return r.stdout.strip() if r.returncode == 0 else None


def repo_line(root, slug):
    if not slug:
        return ""
    d = os.path.join(projects_dir(root), slug, "src")
    if not os.path.isdir(os.path.join(d, ".git")):
        return T("repo.none")
    try:
        n = git_run(d, ["rev-list", "--count", "HEAD"], timeout=20)
        cnt = int(n.stdout.strip()) if n.returncode == 0 and n.stdout.strip().isdigit() else 0
        rm = git_run(d, ["remote", "get-url", "origin"], timeout=20)
        dirty = git_run(d, ["status", "--porcelain"], timeout=20).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return ""
    remote = rm.stdout.strip() if rm.returncode == 0 else ""
    remote = re.sub(r"//[^/@]*@", "//", remote)
    return T("repo.line", n=cnt, dirty=T("repo.dirty") if dirty else "",
             remote=T("repo.remote", url=remote) if remote else T("repo.no_remote"))


def history_has_key(d, root=None):
    """The whole history: secret files and secret-looking text. Findings are `commit:path:line` + a fingerprint (no values)."""
    try:
        files = git_run(d, ["ls-files"], timeout=30).stdout.splitlines()
        bad = [f for f in files if SECRET_FILE.search(f)]
        log = git_run(d, ["log", "-p", "--all", "-U0", "--format=@@COMMIT %H"], timeout=120).stdout
    except (OSError, subprocess.SubprocessError):
        return True, [T("hk.unreadable")]
    why = []
    if bad:
        why.append(T("hk.secret_files", files=", ".join(bad[:3])))
    found = diff_findings(root or os.path.dirname(os.path.dirname(os.path.dirname(d))), log)
    if found:
        why.append(T("hk.keylike", found=fmt_findings(found)))
    return bool(why), why


PRIVATE_NAME = "CreateCodeBox"
PRIVATE_EMAIL = "createcodebox@users.noreply.invalid"
NOREPLY_GH = "@users.noreply.github.com"
NOREPLY_RE = re.compile(r"^(\d+\+)?[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?@users\.noreply\.github\.com$", re.I)


def mail_is_private(addr):
    """An address that does not show who the person is: GitHub's private address, GitHub's own, or a reserved .invalid one."""
    a = (addr or "").strip().lower()
    return a.endswith(NOREPLY_GH) or a == "noreply@github.com" or a.endswith(".invalid")


def git_identity(d):
    """Record saves in this project under a name and address that do not show who the person is (this repo only, never the global settings).
    Left alone when the effective address is already GitHub's private one. Returns True when something was changed."""
    n = git_run(d, ["config", "user.name"], timeout=20).stdout.strip()
    m = git_run(d, ["config", "user.email"], timeout=20).stdout.strip()
    if m.lower().endswith(NOREPLY_GH):
        return False
    changed = False
    if n != PRIVATE_NAME:
        git_run(d, ["config", "--local", "user.name", PRIVATE_NAME], timeout=20)
        changed = True
    if m != PRIVATE_EMAIL:
        git_run(d, ["config", "--local", "user.email", PRIVATE_EMAIL], timeout=20)
        changed = True
    return changed


def cmd_repo_email(root, addr):
    slug, d = src_of(root)
    if not slug:
        return 2, T("common.need_project")
    if not addr:
        return 2, T("repo.email.usage")
    if not os.path.isdir(os.path.join(d, ".git")):
        return 2, T("backup.need_save")
    if not NOREPLY_RE.match(addr.strip()):
        return 2, T("repo.email.bad")
    addr = addr.strip()
    git_run(d, ["config", "--local", "user.email", addr], timeout=20)
    if git_run(d, ["config", "--local", "user.name"], timeout=20).stdout.strip() != PRIVATE_NAME:
        git_run(d, ["config", "--local", "user.name", PRIVATE_NAME], timeout=20)
    return 0, T("repo.email.done", addr=addr)


def cmd_repo_init(root):
    slug, d = src_of(root)
    if not slug:
        return 2, T("common.need_project")
    nc = need_card(root, "init")
    if nc:
        return nc
    if os.path.isdir(os.path.join(d, ".git")):
        return 0, T("repo.init.already")
    git_run(d, ["-c", "init.defaultBranch=main", "init", "-q"], timeout=30) if False else subprocess.run(
        ["git", "-C", d, "-c", "init.defaultBranch=main", "init", "-q"], capture_output=True, text=True, timeout=30)
    changed = git_identity(d)
    return 0, T("repo.init.done") + (("\n" + T("repo.init.identity")) if changed else "")


def cmd_save(root, msg):
    slug, d = src_of(root)
    if not slug:
        return 2, T("common.need_project")
    nc = need_card(root, "save")
    if nc:
        return nc
    if not msg or len(msg.strip()) < 2:
        return 2, T("save.need_memo")
    if not os.path.isdir(os.path.join(d, ".git")):
        rc, m = cmd_repo_init(root)
        if rc != 0:
            return rc, m
    id_note = T("repo.init.identity") if git_identity(d) else ""
    git_run(d, ["add", "-A"], timeout=60)
    names = git_run(d, ["diff", "--cached", "--name-only"], timeout=30).stdout.splitlines()
    bad = [n for n in names if SECRET_FILE.search(n)]
    diff = git_run(d, ["diff", "--cached", "-U0"], timeout=60).stdout
    found = diff_findings(root, diff)
    if bad or found:
        git_run(d, ["reset", "-q"], timeout=30)
        return 1, (T("save.stopped") + (T("save.secret_files", files=", ".join(bad[:3])) if bad else "") +
                   (T("save.keylike", found=fmt_findings(found)) if found else T("save.remove_retry")))
    if not names:
        return 0, T("save.nothing")
    branch_note = ""
    if (load_rec(root, "repo_%s.json" % slug, slug, {}) or {}).get("adopted"):
        cur = git_run(d, ["rev-parse", "--abbrev-ref", "HEAD"], timeout=20).stdout.strip()
        if cur in ("main", "master"):
            nb = "createcodebox/" + datetime.datetime.now().strftime("%Y%m%d")
            r0 = git_run(d, ["checkout", "-q", nb], timeout=30)
            if r0.returncode != 0:
                r0 = git_run(d, ["checkout", "-q", "-b", nb], timeout=30)
            if r0.returncode != 0:
                return 1, T("save.branch_fail", branch=nb, err=(r0.stderr or r0.stdout).strip()[:200])
            branch_note = T("save.branch", branch=nb)
        else:
            branch_note = ""
    r = git_run(d, ["commit", "-q", "-m", msg.strip()], timeout=60)
    if r.returncode != 0:
        return 1, T("save.fail", err=(r.stderr or r.stdout).strip()[:300])
    return 0, T("save.done", n=len(names), msg=msg.strip()) + (("\n" + branch_note) if branch_note else "") + (("\n" + id_note) if id_note else "")


def valid_remote(url):
    if os.environ.get("CREATECODEBOX_ALLOW_LOCAL_REMOTE") == "1" and os.path.isabs(url):
        return True, ""
    if re.match(r"^https://[^/@\s]+@", url):
        return False, T("link.creds")
    if re.match(r"^git@[A-Za-z0-9.-]+:[^\s]+$", url):
        return True, ""
    if not re.match(r"^https://[A-Za-z0-9.-]+/[^\s]+$", url):
        return False, T("link.bad_form")
    return True, ""


def classify_remote_result(rc, stderr):
    """ls-remote の結果を 公開・非公開・不明 に分ける。認証なしで読めれば公開。認証を求められた・見つからないなら非公開（か存在しない）。つながらないなど、分からないものは不明。"""
    if rc in (0, 2):
        return "public"
    if re.search(r"(could not read Username|Authentication failed|Repository not found|terminal prompts disabled|invalid username|returned error: 40[134])", stderr or "", re.I):
        return "private"
    return "unknown"


def remote_visibility(url):
    if os.path.isabs(url):
        return "private"
    if url.startswith("git@"):
        return "unknown"  # an ssh URL can't be checked without credentials
    try:
        r = subprocess.run(["git", "-c", "credential.helper=", "ls-remote", "--exit-code", url, "HEAD"],
                           capture_output=True, text=True, timeout=45,
                           env=dict(os.environ, GIT_TERMINAL_PROMPT="0"))
    except (OSError, subprocess.SubprocessError):
        return "unknown"
    return classify_remote_result(r.returncode, r.stderr)


def is_public_remote(url):
    return remote_visibility(url) == "public"


def cmd_repo_link(root, url):
    slug, d = src_of(root)
    if not slug:
        return 2, T("common.need_project")
    nc = need_card(root, "link")
    if nc:
        return nc
    ok, why = valid_remote(url or "")
    if not ok:
        return 2, why
    if not os.path.isdir(os.path.join(d, ".git")):
        rc, m = cmd_repo_init(root)
        if rc != 0:
            return rc, m
    has = git_run(d, ["remote", "get-url", "origin"], timeout=20).returncode == 0
    git_run(d, ["remote", "set-url" if has else "add", "origin", url], timeout=20)
    vis = remote_visibility(url)
    note = T("link." + {"public": "public", "private": "private", "unknown": "unknown"}[vis])
    return 0, T("link.done", url=url, note=note)


def push_current(d):
    interactive = sys.stdin.isatty()
    r = git_run(d, ["push", "-u", "origin", "HEAD"], timeout=300, noprompt=not interactive)
    out = redact(r.stdout + r.stderr)
    if r.returncode != 0:
        return 1, T("push.fail", dir=d, out=out.strip()[-500:])
    return 0, T("push.done", out=out.strip()[-300:])


def cmd_backup(root):
    slug, d = src_of(root)
    if not slug or not os.path.isdir(os.path.join(d, ".git")):
        return 2, T("backup.need_save")
    nc = need_card(root, "backup")
    if nc:
        return nc
    rm = git_run(d, ["remote", "get-url", "origin"], timeout=20)
    if rm.returncode != 0:
        return 2, T("backup.no_repo")
    url = rm.stdout.strip()
    vis = remote_visibility(url)
    if vis == "public":
        return 1, T("backup.public")
    if vis == "unknown":
        return 1, T("backup.unknown")
    bad, why = history_has_key(d, root)
    if bad:
        return 1, T("backup.blocked", why=T("sep.list").join(why))
    return push_current(d)


def commit_mail_scan(d):
    """The author and committer addresses of the saved versions that would become public.
    Remote not public yet (or no remote, or it cannot be checked): every version in the history counts.
    Remote already public: only versions not yet on it count; older ones are already out.
    Returns None when the history cannot be read, else {"scope", "rows": [(sha, [addresses])], "old": [...]}."""
    def rows(args):
        r = git_run(d, ["log", "--format=%H%x09%ae%x09%ce"] + args, timeout=60)
        if r.returncode != 0:
            return None
        out = []
        for line in r.stdout.splitlines():
            p = line.split("\t")
            if len(p) == 3:
                out.append((p[0], [p[1].strip(), p[2].strip()]))
        return out
    try:
        if git_run(d, ["rev-parse", "--verify", "-q", "HEAD"], timeout=20).returncode != 0:
            return {"scope": "all", "rows": [], "old": []}  # nothing saved yet
        allr = rows(["HEAD"])
        if allr is None:
            return None
        rm = git_run(d, ["remote", "get-url", "origin"], timeout=20)
        vis = remote_visibility(rm.stdout.strip()) if rm.returncode == 0 else "none"
        if vis != "public":
            return {"scope": "all", "rows": allr, "old": []}
        new = rows(["HEAD", "--not", "--remotes=origin"])
        if new is None:
            return None
    except (OSError, subprocess.SubprocessError):
        return None
    ids = {sha for sha, _ in new}
    return {"scope": "new", "rows": new, "old": [r for r in allr if r[0] not in ids]}


def mail_summary(rows):
    """(distinct addresses with the number of versions using each, number of versions with a non-private address)."""
    count, bad = {}, 0
    for _, addrs in rows:
        for a in set(addrs):
            count[a] = count.get(a, 0) + 1
        if any(not mail_is_private(a) for a in addrs):
            bad += 1
    return count, bad


def mail_check_lines(scan):
    """(ok, lines) for publish-check."""
    if scan is None:
        return False, ["  " + T("pc.mail_unreadable")]
    rows = scan["rows"]
    count, bad = mail_summary(rows)
    scope = T("pc.mail_scope_all") if scan["scope"] == "all" else T("pc.mail_scope_new")
    state = T("pc.mail_state_bad", bad=bad, n=len(rows)) if bad else T("pc.mail_state_ok")
    lines = ["  " + T("pc.mail", mark="NG " if bad else "OK ", scope=scope, state=state)]
    for a in sorted(count, key=lambda x: (mail_is_private(x), x)):
        lines.append("    - " + T("pc.mail_item", mark="OK " if mail_is_private(a) else "NG ", addr=a or T("pc.mail_empty"), c=count[a], n=len(rows)))
    if scan["old"]:
        oc, ob = mail_summary(scan["old"])
        if ob:
            lines.append("  " + T("pc.mail_old", n=ob, addrs=", ".join(sorted(a for a in oc if not mail_is_private(a)))))
    if bad:
        lines.append("  " + T("pc.mail_fail"))
    return not bad, lines


def cmd_publish_check(root):
    slug, d = src_of(root)
    if not slug or not os.path.isdir(os.path.join(d, ".git")):
        return 2, T("backup.need_save")
    nc = need_card(root, "publish")
    if nc:
        return nc
    bad, why = history_has_key(d, root)
    names = [n.lower() for n in os.listdir(d)]
    has_readme = any(n.startswith("readme") for n in names)
    has_license = any(n.startswith("license") or n.startswith("licence") for n in names)
    dirty = bool(git_run(d, ["status", "--porcelain"], timeout=20).stdout.strip())
    mk = lambda good: "OK " if good else "NG "
    lines = [T("pc.head"),
             "  " + T("pc.hist", mark=mk(not bad)),
             "  " + T("pc.readme", mark=mk(has_readme)),
             "  " + T("pc.license", mark=mk(has_license)),
             "  " + T("pc.clean", mark=mk(not dirty))]
    lines += ["    - " + w for w in why]
    mail_ok, mail_lines = mail_check_lines(commit_mail_scan(d))
    lines += mail_lines
    lines.append(T("pc.personal"))
    ok = not bad and has_readme and has_license and not dirty and mail_ok
    head = repo_head(root, slug)
    save_rec(root, "publish_check_%s.json" % slug, {"ok": ok, "head": head}, slug)
    gt = parse_project(root, slug).get("goal_type", "")
    sm = st_summary(root, slug)
    warned = os.path.join(ws_dir(root), "publish_warned_%s" % slug)
    if gt in ("public-free", "public-paid") and sm and sm["ai_pass"] < sm["ai_total"] and not os.path.exists(warned):
        lines.append(T("publish.ai_unfinished", a=sm["ai_pass"], at=sm["ai_total"]))
        write_text(warned, "1\n")
    lines.append(T("pc.ok", word=T("word.publish")) if ok else T("pc.fail"))
    return (0 if ok else 1), "\n".join(lines)


def cmd_publish(root):
    slug, d = src_of(root)
    if not slug or not os.path.isdir(os.path.join(d, ".git")):
        return 2, T("backup.need_save")
    nc = need_card(root, "publish")
    if nc:
        return nc
    head = repo_head(root, slug)
    chk = load_rec(root, "publish_check_%s.json" % slug, slug, {}) or {}
    okf = load_rec(root, "publish_ok_%s.json" % slug, slug, {}) or {}
    if not (chk.get("ok") and chk.get("head") == head):
        return 1, T("publish.need_check")
    if okf.get("head") != head:
        return 1, T("publish.need_word", word=T("word.publish"))
    rm = git_run(d, ["remote", "get-url", "origin"], timeout=20)
    if rm.returncode != 0:
        return 2, T("backup.no_repo")
    bad, why = history_has_key(d, root)
    if bad:
        return 1, T("publish.blocked", why=T("sep.list").join(why))
    if not mail_check_lines(commit_mail_scan(d))[0]:
        return 1, T("publish.mail_blocked")
    return push_current(d)


def cmd_repo_adopt(root, src):
    slug, d = src_of(root)
    if not slug:
        return 2, T("common.need_project")
    nc = need_card(root, "adopt")
    if nc:
        return nc
    dirty_warn = ""
    leftovers = [n for n in os.listdir(d) if n not in (".gitkeep", ".gitignore")]
    if leftovers:
        return 1, T("adopt.in_use")
    if os.path.isabs(src or ""):
        if not os.path.isdir(os.path.join(src, ".git")):
            return 1, T("adopt.no_git")
        origin = src
        try:
            if git_run(src, ["status", "--porcelain"], timeout=30).stdout.strip():
                dirty_warn = T("adopt.uncommitted")
        except (OSError, subprocess.SubprocessError):
            pass
    else:
        ok, why = valid_remote(src or "")
        if not ok:
            return 2, why
        origin = src
    for n in (".gitkeep", ".gitignore"):
        try:
            os.remove(os.path.join(d, n))
        except OSError:
            pass
    r = subprocess.run(["git", "clone", "-q", origin, d], capture_output=True, text=True, timeout=600,
                       env=dict(os.environ, GIT_TERMINAL_PROMPT="0"))
    if r.returncode != 0:
        write_text(os.path.join(d, ".gitkeep"), "")
        return 1, T("adopt.fail", err=(r.stderr or r.stdout).strip()[:300])
    save_rec(root, "repo_%s.json" % slug, {"adopted": True}, slug)
    id_note = T("repo.init.identity") if git_identity(d) else ""
    return 0, T("adopt.done") + (("\n" + dirty_warn) if dirty_warn else "") + (("\n" + id_note) if id_note else "")


# ---------- 強化モード（OS のサンドボックス）----------
HARDEN_ENV = [".env", ".env.local", ".env.development", ".env.production", ".env.test", ".env.staging"]
HARDEN_DENY = (["~/.createcodebox", "~/.ssh", "~/.aws", "~/.gnupg", "~/.config/gh", "~/.git-credentials", "~/.netrc", "~/.npmrc"]
               + ["~/**/" + n for n in HARDEN_ENV] + ["~/**/.env.*.local"])  # .env.example stays readable
HARDEN_EXCLUDED = ["bash ws/bin/ws.sh:*", "sh ws/bin/ws.sh:*"]


def settings_local_path(root):
    return os.path.join(root, ".claude", "settings.local.json")


def harden_state(root):
    d = load_json(settings_local_path(root), {}) or {}
    return bool((d.get("sandbox") or {}).get("enabled"))


def apply_harden(root, on, with_denywrite=False):
    path = settings_local_path(root)
    d = load_json(path, {}) or {}
    if on:
        fs = {"denyRead": list(HARDEN_DENY)}
        if with_denywrite:
            # OPTIONAL and UNVERIFIED: whether `sandbox.filesystem.denyWrite` exists in this form is not confirmed.
            # Only added when the user passes --with-denywrite. If Claude Code ignores it, nothing breaks; if it rejects it, remove it.
            fs["denyWrite"] = [".ws", "ws", ".claude"]
        d["sandbox"] = {"enabled": True, "excludedCommands": list(HARDEN_EXCLUDED), "filesystem": fs}
    else:
        d.pop("sandbox", None)
    save_json(path, d)


def cmd_harden(root, action, with_denywrite=False):
    if action not in ("on", "off", "status"):
        return 2, T("harden.usage")
    if action == "status":
        return 0, T("harden.status", state=T("state.on") if harden_state(root) else T("state.off"))
    if sys.platform not in ("darwin", "linux"):
        return 1, T("harden.platform")
    if not sys.stdin.isatty():
        return 1, T("harden.need_tty")
    apply_harden(root, action == "on", with_denywrite)
    if action == "on":
        return 0, T("harden.on_done")
    return 0, T("harden.off_done")


# ---------- システムテスト（出力を、人と同じ操作で確かめる） ----------
SHOT_EXT = (".png", ".jpg", ".jpeg", ".webp", ".gif")


def st_load(root, slug):
    d = load_rec(root, "st_%s.json" % slug, slug)
    return d if isinstance(d, dict) and isinstance(d.get("rows"), list) else None


def st_save(root, slug, d):
    save_rec(root, "st_%s.json" % slug, d, slug)


def case_who(io_row, kind):
    """F3: who can check it. scheduled, a failure of external, a failure of api -> ai (can't be triggered by hand). Else the user."""
    k = SYN.kind_symbol(str(io_row.get("kind", "")))
    if k == "scheduled" or (kind == "F" and k in ("external", "api")):
        return "ai"
    return "user"


def st_basis(io_row):
    """A short hash of what the cases are made from, so progress survives a change of language."""
    keys = ("kind", "dir", "name", "example", "failure", "screen")
    raw = json.dumps([str(io_row.get(k, "")) for k in keys], ensure_ascii=True)
    return hashlib.sha1(raw.encode("ascii")).hexdigest()[:12]


def st_case(io_row, kind, n, state, what, expected):
    return {"id": "T-%s-%s%d" % (io_row["id"], kind, n), "io": io_row["id"], "kind": kind, "state": state,
            "what": what, "expected": expected, "route": "ST", "reason": "", "status": "todo",
            "who": case_who(io_row, kind), "by": "", "evidence": "", "shot": "", "at": "", "basis": st_basis(io_row)}


def st_generate(io_rows):
    cases = []
    seen_screens = set()
    for r in io_rows:
        nm, ex, fl = r.get("name", ""), r.get("example", ""), r.get("failure", "")
        if SYN.kind_symbol(str(r.get("kind", ""))) == "screen":
            cases.append(st_case(r, "N", 1, "normal", T("st.case.screen.n.what", name=nm, example=ex), T("st.case.screen.n.exp", example=ex)))
            sc = r.get("screen") or ""
            if not sc or sc not in seen_screens:  # one empty-state case for each screen
                cases.append(st_case(r, "B", 1, "empty", T("st.case.screen.b.what", name=nm, screen=sc or T("st.screen_default")), T("st.case.screen.b.exp")))
                if sc:
                    seen_screens.add(sc)
            cases.append(st_case(r, "F", 1, "error", T("st.case.screen.f.what", name=nm), fl))
        else:
            d = "in" if r.get("dir") == "in" else "out"
            cases.append(st_case(r, "N", 1, "ok", T("st.case.%s.n.what" % d, name=nm, example=ex), T("st.case.%s.n.exp" % d, example=ex)))
            cases.append(st_case(r, "F", 1, "failure", T("st.case.f.what", name=nm), fl))
    return cases


def st_summary(root, slug):
    d = st_load(root, slug)
    if not d or not d["rows"]:
        return None
    rows = d["rows"]

    def cnt(f):
        sel = [r for r in rows if f(r)]
        return sum(1 for r in sel if r.get("status") == "pass"), len(sel)
    up, ut = cnt(lambda r: r.get("who", "user") != "ai")
    ap, at = cnt(lambda r: r.get("who", "user") == "ai")
    np_, nt = cnt(lambda r: r.get("kind") == "N")
    return {"total": len(rows), "pass": sum(1 for r in rows if r.get("status") == "pass"),
            "fail": sum(1 for r in rows if r.get("status") == "fail"),
            "abnormal": sum(1 for r in rows if r.get("kind") in ("B", "F")),
            "user_pass": up, "user_total": ut, "ai_pass": ap, "ai_total": at, "normal_pass": np_, "normal_total": nt}


def first_version_done(st):
    """First version = every case the user can check is passed, and every normal-path case is passed."""
    return bool(st) and st["total"] > 0 and st["user_pass"] == st["user_total"] and st["normal_pass"] == st["normal_total"]


KEEP_KEYS = ("route", "reason", "status", "who", "by", "evidence", "shot", "at", "via", "bulk", "who_reason")


def state_label(state):
    st = STATE_ALIAS.get(state, state)
    t = T("st.state." + st)
    return state if t == "st.state." + st else t


def st_init(root, slug, name):
    io = load_json(io_path(root, slug)) or {"rows": []}
    new = st_generate([r for r in io.get("rows", []) if isinstance(r, dict) and r.get("id")])
    old = {r["id"]: r for r in (st_load(root, slug) or {"rows": []})["rows"]}
    for r in new:
        o = old.get(r["id"])
        if o and ((o.get("basis") and o.get("basis") == r.get("basis")) or (o.get("what") == r["what"] and o.get("expected") == r["expected"])):
            r.update({k: o[k] for k in KEEP_KEYS if k in o})
    st_save(root, slug, {"project": name, "rows": new})
    return new


def read_arg_text(rest, name, root=None):
    """`--name <text>` / `--name -` (stdin) / `--name-file <path>` (a file of at most 64KB). Returns text or None."""
    if name in rest:
        i = rest.index(name)
        v = rest[i + 1] if i + 1 < len(rest) else None
        if v == "-":
            try:
                return sys.stdin.read(65536)
            except (OSError, ValueError):
                return ""
        return v
    fname = name + "-file"
    if fname in rest:
        i = rest.index(fname)
        p = rest[i + 1] if i + 1 < len(rest) else ""
        try:
            if os.path.getsize(p) > 65536:
                return ""
        except OSError:
            return ""
        return read_text(p) or ""
    return None


def id_token(text, cid):
    """A suffix of the case ID (from the whole ID down to 5 characters, at a '-') that stands alone in the text."""
    parts = cid.split("-")
    for i in range(len(parts)):
        suffix = "-".join(parts[i:])
        if len(suffix) >= 5 and re.search(r"(?<![A-Za-z0-9])" + re.escape(suffix) + r"(?![A-Za-z0-9])", text, re.I):
            return suffix
    return None


def parse_numbers(text):
    """'1, 2 pass' / '1-3 pass' / '1 2' -> {1, 2, 3}. Only small numbers."""
    nums = set()
    for a, b in re.findall(r"(?<![0-9A-Za-z.\-])(\d{1,3})\s*[-~〜～]\s*(\d{1,3})(?![0-9A-Za-z])", text):
        lo, hi = int(a), int(b)
        if lo <= hi <= lo + 200:
            nums.update(range(lo, hi + 1))
    text2 = re.sub(r"(?<![0-9A-Za-z.\-])(\d{1,3})\s*[-~〜～]\s*(\d{1,3})(?![0-9A-Za-z])", " ", text)
    for a in re.findall(r"(?<![0-9A-Za-z.\-])(\d{1,3})(?![0-9A-Za-z.])", text2):
        nums.add(int(a))
    return nums


PASS_WORD = re.compile(r"(?<![a-z])(pass|passed)(?![a-z])")


def user_mark_ok(root, row, numbers_mode=False):
    """F1: the user's own latest input must name the case (ID suffix or list number) and say pass or say 10+ other characters.
    One input is good for one mark (used up), except numbered answers (each listed number) and a bulk 'all pass' after a list.
    Returns (ok, extra_fields, message)."""
    sess = get_session(root)
    last = nfkc(sess.get("last_prompt", ""))
    low = last.lower()
    n = int(sess.get("prompts", 0))
    pass_word = bool(PASS_WORD.search(low)) or "合格" in last
    bulk_word = bool(re.search(r"(?<![a-z])all(?![a-z])", low)) or any(w in last for w in ("全部", "全て", "すべて"))
    if bulk_word and pass_word and n - int(sess.get("st_list_at", -99)) <= 3:
        return True, {"bulk": True}, ""
    token = id_token(last, row["id"])
    via = None
    if token:
        rest_text = re.sub(r"(?<![A-Za-z0-9])" + re.escape(token) + r"(?![A-Za-z0-9])", " ", last, flags=re.I)
    else:
        nums = parse_numbers(last)
        mapping = sess.get("numbered") or {}
        mine = [int(k) for k, v in mapping.items() if v == row["id"] and k.isdigit()]
        if not any(k in nums for k in mine):
            return False, {}, T("st.user.need_id")
        via = "numbered"
        rest_text = re.sub(r"\d{1,3}(\s*[-~〜～]\s*\d{1,3})?", " ", last)
    if via != "numbered" and int(sess.get("prompt_used_for_mark", 0)) == n:
        return False, {}, T("st.user.used")
    if not (pass_word or len(re.sub(r"\s+", "", rest_text)) >= 10):
        return False, {}, T("st.user.need_words")
    if via != "numbered":
        set_session(root, prompt_used_for_mark=n)
    return True, ({"via": "numbered"} if via else {}), ""


def detect_runner(src):
    pj = load_json(os.path.join(src, "package.json"))
    if isinstance(pj, dict):
        t = (pj.get("scripts") or {}).get("test") if isinstance(pj.get("scripts"), dict) else None
        if isinstance(t, str) and t.strip() and "no test specified" not in t:
            return ["npm", "test"]
    if os.path.isfile(os.path.join(src, "pytest.ini")) or os.path.isfile(os.path.join(src, "pyproject.toml")):
        return ["pytest"] if shutil.which("pytest") else [sys.executable, "-m", "pytest"]
    if os.path.isfile(os.path.join(src, "go.mod")):
        return ["go", "test", "./..."]
    if os.path.isfile(os.path.join(src, "Cargo.toml")):
        return ["cargo", "test"]
    return None


def redact(text, values=()):
    for _, rx in SPECIFIC_PATTERNS:
        text = rx.sub("***", text)
    for v in sorted((v for v in values if len(v) >= 4), key=len, reverse=True):
        text = text.replace(v, "***")
    return text


def secret_values(root, project=False):
    values = dict(parse_env(secret_file(root)))
    slug = compute(root)["slug"] if project else None
    if slug:
        values.update(parse_env(secret_file(root, slug)))
    return [v for v in values.values() if v]


def st_run(root, slug, ids, timeout=600):
    d = st_load(root, slug)
    rows = {r["id"]: r for r in d["rows"]}
    for i in ids:
        if i not in rows:
            return 2, T("st.no_case", id=i)
        if rows[i].get("who", "user") != "ai":
            return 2, T("st.run.user_case", id=i)
    src = os.path.join(projects_dir(root), slug, "src")
    cmd = detect_runner(src)
    if not cmd:
        return 2, T("st.no_runner")
    try:
        r = subprocess.run(cmd, cwd=src, capture_output=True, text=True, timeout=timeout, errors="replace")
        rc, out = r.returncode, (r.stdout or "") + (r.stderr or "")
    except subprocess.TimeoutExpired:
        rc, out = 124, T("st.run.timeout", sec=timeout)
    except OSError as e:
        return 1, T("st.run.cannot", err=type(e).__name__)
    tail = redact("\n".join(out.splitlines()[-50:]), secret_values(root, True))
    ev = T("st.run.evidence", cmd=" ".join(cmd[:3]), rc=rc, tail=tail)
    for i in ids:
        rows[i].update({"status": "pass" if rc == 0 else "fail", "by": "run", "evidence": ev, "shot": "", "at": time_now()})
    st_save(root, slug, d)
    sm = st_summary(root, slug)
    return (0 if rc == 0 else 1), T("st.run.done", ids=", ".join(ids), rc=rc, p=sm["pass"], t=sm["total"]) + "\n" + tail


def cmd_st(root, rest):
    c = compute(root)
    if not c["slug"] or c["stage"] not in ("RS", "RUN", "DONE"):
        return 2, T("st.need_stage", label=stage_label(c["stage"]))
    slug = c["slug"]
    sub = rest[0] if rest else "list"

    def opt(name):
        if name in rest:
            i = rest.index(name)
            return rest[i + 1] if i + 1 < len(rest) else None
        return None
    if sub == "init":
        rows = st_init(root, slug, c["name"])
        return 0, T("st.init.done", n=len(rows), ab=sum(1 for r in rows if r["kind"] in ("B", "F")))
    d = st_load(root, slug)
    if d is None:
        return 2, T("st.no_list")
    if sub == "list":
        numbered = "--numbered" in rest
        out, mapping = [], {}
        for i, r in enumerate(d["rows"], 1):
            mapping[str(i)] = r["id"]
            stt = T("st.status." + r["status"]) if r["status"] in ("pass", "fail", "todo") else r["status"]
            parts = dict(status=stt, id=r["id"], who=r.get("who", "user"), kind=r["kind"], state=state_label(r["state"]), what=r["what"], expected=r["expected"])
            out.append(T("st.list.numbered", n=i, **parts) if numbered else T("st.list.line", **parts))
        sess = get_session(root)
        set_session(root, st_list_at=int(sess.get("prompts", 0)), **({"numbered": mapping} if numbered else {}))
        sm = st_summary(root, slug)
        out.append(T("st.list.counts", p=sm["pass"], t=sm["total"], f=sm["fail"], ab=sm["abnormal"]))
        out.append(T("st.list.summary", u=sm["user_pass"], ut=sm["user_total"], a=sm["ai_pass"], at=sm["ai_total"]))
        if sm["abnormal"] * 2 < sm["total"]:
            out.append(T("st.list.warn"))
        return 0, "\n".join(out)
    if sub == "route" and len(rest) >= 3:
        row = next((r for r in d["rows"] if r["id"] == rest[1]), None)
        if row is None:
            return 2, T("st.no_case", id=rest[1])
        who = rest[2]
        reason = (opt("--reason") or "").strip()
        if who not in ("user", "ai"):
            return 2, T("st.route.usage")
        if len(reason) < 4:
            return 2, T("st.route.need_reason")
        if who == "user" and row.get("status") == "pass" and row.get("by") != "user":
            row["status"], row["by"], row["evidence"], row["shot"], row["at"] = "todo", "", "", "", ""
        row["who"], row["who_reason"] = who, reason
        st_save(root, slug, d)
        return 0, T("st.route.done", id=row["id"], who=who)
    if sub == "run":
        if c["stage"] == "DONE":
            return 2, T("common.done_already")
        ids = []
        i = 1
        while i < len(rest) and not rest[i].startswith("--"):
            ids.append(rest[i])
            i += 1
        if not ids:
            return 2, T("st.run.usage")
        tv = opt("--timeout")
        return st_run(root, slug, ids, int(tv) if tv and tv.isdigit() else 600)
    if sub == "mark" and len(rest) >= 3:
        if c["stage"] == "DONE":
            return 2, T("common.done_already")
        status = rest[2]
        if status not in ("pass", "fail", "todo"):
            return 2, T("st.bad_status")
        by = opt("--by") or ""
        if by in ("ci", "ut"):
            return 2, T("st.by_removed")
        evidence = (read_arg_text(rest, "--evidence") or "").strip()
        if rest[1] == "numbered":
            sess = get_session(root)
            nums = parse_numbers(nfkc(sess.get("last_prompt", "")))
            mapping = sess.get("numbered") or {}
            targets = [mapping[str(k)] for k in sorted(nums) if str(k) in mapping]
            if status != "pass" or by != "user" or not targets:
                return 2, T("st.numbered.usage")
            done_ids = []
            for tid in targets:
                row = next((r for r in d["rows"] if r["id"] == tid), None)
                ok, extra, why = user_mark_ok(root, row)
                if not ok:
                    return 1, why
                row.update({"status": "pass", "by": "user", "evidence": (evidence or nfkc(sess.get("last_prompt", "")).strip())[:300],
                            "shot": "", "at": time_now(), **extra})
                done_ids.append(tid)
            st_save(root, slug, d)
            sm = st_summary(root, slug)
            return 0, T("st.recorded", ids=", ".join(done_ids), p=sm["pass"], t=sm["total"])
        row = next((r for r in d["rows"] if r["id"] == rest[1]), None)
        if row is None:
            return 2, T("st.no_case", id=rest[1])
        extra = {}
        if status == "pass":
            if by == "user":
                ok, extra, why = user_mark_ok(root, row)
                if not ok:
                    return 1, why
                evidence = (evidence or nfkc(get_session(root).get("last_prompt", "")).strip())[:300]
            elif by == "ai":
                if row.get("who", "user") != "ai":
                    return 1, T("st.ai.user_case", id=row["id"])
                if len(evidence) < 8:
                    return 1, T("st.ai.evidence")
                shot = opt("--shot")
                why = shot_problem(root, slug, shot)
                if why:
                    return 1, why
                dest = os.path.join(design_dir(root, slug), "evidence")
                os.makedirs(dest, exist_ok=True)
                ext = os.path.splitext(shot)[1].lower()
                shutil.copy2(shot, os.path.join(dest, "%s%s" % (row["id"], ext)))
                row["shot"] = "design/evidence/%s%s" % (row["id"], ext)
            else:
                return 2, T("st.by_usage")
        if status == "fail" and len(evidence) < 4:
            return 1, T("st.fail.evidence")
        for k in ("via", "bulk"):
            row.pop(k, None)
        row.update({"status": status, "by": by if status != "todo" else "", "evidence": evidence if status != "todo" else "",
                    "at": time_now() if status != "todo" else "", **extra})
        if status != "pass" and by != "ai":
            row["shot"] = ""
        st_save(root, slug, d)
        sm = st_summary(root, slug)
        return 0, T("st.recorded", ids=row["id"], p=sm["pass"], t=sm["total"])
    return 2, T("st.usage")


def shot_problem(root, slug, shot):
    """The picture must be under projects/<slug>/ and newer than the start of this session."""
    if not shot or not os.path.isfile(shot) or not shot.lower().endswith(SHOT_EXT):
        return T("st.shot.need")
    real = os.path.realpath(shot)
    base = os.path.realpath(os.path.join(projects_dir(root), slug))
    if not (real + os.sep).startswith(base + os.sep) or os.path.getsize(real) < 200:
        return T("st.shot.place")
    started = get_session(root).get("started_at")
    if not isinstance(started, (int, float)) or os.path.getmtime(real) < started:
        return T("st.shot.old")
    return None


def time_now():
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M")


def cmd_lint(root):
    c = compute(root)
    if not c["slug"]:
        return 2, T("common.no_project")
    errs = lint_io(root, c["slug"], parse_project(root, c["slug"]).get("has_ui"))
    if errs:
        return 1, T("lint.fail") + "\n- " + "\n- ".join(errs)
    return 0, T("lint.ok")


CJK_FONTS = {"ja": '"Hiragino Sans","Hiragino Kaku Gothic ProN","Yu Gothic UI","Meiryo",'}


def _embed(template_path, data, page):
    """Fill a render template: the data, the labels of the current language, <html lang>, and the CJK fonts (ja only)."""
    t = read_text(template_path)
    if t is None:
        return None
    if isinstance(data, dict):
        data = {k: v for k, v in data.items() if k not in ("_sig", "_unsigned")}
    safe = lambda obj: json.dumps(obj, ensure_ascii=False).replace("<", "\\u003c")
    code = lang.current()
    t = t.replace("/*__WS_DATA__*/null", safe(data))
    t = t.replace("/*__WS_LABELS__*/null", safe(lang.labels("html.common.", "html.%s." % page)))
    t = re.sub(r'<html lang="[^"]*">', '<html lang="%s">' % code, t, count=1)
    t = t.replace("/*__WS_FONT__*/", CJK_FONTS.get(code, ""))
    t = re.sub(r"<!--ws-noscript-->[^<]*", lambda m: T("html.common.noscript"), t)
    return t


def cmd_render(root):
    c = compute(root)
    slug = c["slug"]
    if not slug:
        return 2, T("common.no_project")
    pd = design_dir(root, slug)
    made = []
    io = load_json(io_path(root, slug))
    if isinstance(io, dict):
        io = dict(io)
        io.setdefault("project", c["name"])
        rows = []
        for r in io.get("rows", []):
            if isinstance(r, dict):
                r = dict(r)
                r["kind"] = SYN.kind_symbol(str(r.get("kind", ""))) or r.get("kind", "")
            rows.append(r)
        io["rows"] = rows
        out = _embed(os.path.join(root, "ws", "render", "io.template.html"), io, "io")
        if out is None:
            return 1, T("render.no_template", name="io.template.html")
        write_text(os.path.join(pd, "io.html"), out)
        made.append("projects/%s/design/io.html" % slug)
    sc = load_schedule(root, slug)
    if isinstance(sc, dict):
        sc = dict(sc)
        sc["stage"] = SCHEDULE_STEP[c["stage"]]
        sc.setdefault("project", c["name"])
        out = _embed(os.path.join(root, "ws", "render", "schedule.template.html"), sc, "sched")
        if out is None:
            return 1, T("render.no_template", name="schedule.template.html")
        write_text(os.path.join(pd, "schedule.html"), out)
        made.append("projects/%s/design/schedule.html" % slug)
    stj = st_load(root, slug)
    if stj is not None:
        stj = dict(stj)
        stj.setdefault("project", c["name"])
        stj["rows"] = [dict(r, state=STATE_ALIAS.get(r.get("state"), r.get("state"))) if isinstance(r, dict) else r for r in stj["rows"]]
        out = _embed(os.path.join(root, "ws", "render", "systemtest.template.html"), stj, "st")
        if out is not None:
            write_text(os.path.join(pd, "systemtest.html"), out)
            made.append("projects/%s/design/systemtest.html" % slug)
    if not made:
        return 1, T("render.nothing")
    return 0, T("render.done") + "\n- " + "\n- ".join(made)


def date_rows(rows, today=None):
    """Tentative dates for the rows that have none: the first open row starts today, each next row the day after the one before, one day each.
    Dates that are already set stay, and the next row starts after them. Rows that are done get none."""
    cur = today or datetime.date.today()
    for r in rows:
        if r.get("start") or r.get("due"):
            last = r.get("due") or r.get("start")
            cur = max(cur, to_date(last) + datetime.timedelta(days=1))
        elif r.get("status") != "done":
            r.update(start=cur.isoformat(), due=cur.isoformat(), tentative=True)
            cur += datetime.timedelta(days=1)
    return rows


def cmd_schedule_init(root):
    c = compute(root)
    if c["stage"] not in ("RS", "RUN"):
        return 2, T("sched.need_stage", label=stage_label(c["stage"]))
    slug = c["slug"]
    io = load_json(io_path(root, slug)) or {"rows": []}
    io_rows = [r for r in io.get("rows", []) if isinstance(r, dict) and r.get("id")]
    old = load_schedule(root, slug)
    cases = st_init(root, slug, c["name"])
    if isinstance(old, dict) and old.get("rows"):
        rows = old["rows"]
        gate_rows = [r for r in rows if r.get("gate") == "systemtest"]
        body = [r for r in rows if r.get("gate") != "systemtest"]
        added = 0
        for r in io_rows:
            if any(s.get("io") == r["id"] or ("(%s)" % r["id"]) in str(s.get("title", "")) or ("（%s）" % r["id"]) in str(s.get("title", "")) for s in body):
                continue
            nums = [int(m.group(1)) for s in rows for m in [re.match(r"^S-(\d+)$", str(s.get("id", "")))] if m]
            nid = "S-%02d" % (max(nums + [0]) + 1)
            body.append({"id": nid, "io": r["id"], "title": T("sched.row_title", name=r.get("name", ""), id=r["id"]), "status": "todo",
                         "done_when": T("sched.row_done", example=r.get("example", "")), "artifact": "", "note": ""})
            added += 1
        gate = gate_rows[0] if gate_rows else {"id": "S-%02d" % (len(body) + 1), "status": "todo", "artifact": "", "note": "", "gate": "systemtest",
                                               "done_when": T("sched.gate_done")}
        gate["title"] = T("sched.gate_title", n=len(cases))
        if added and gate.get("status") == "done":
            gate["status"] = "todo"
        body.append(gate)
        old["rows"] = date_rows(body)
        save_schedule(root, slug, old)
        return 0, T("sched.added", added=added, total=len(body), cases=len(cases))
    rows = [{"id": "S-01", "title": T("sched.first_title"), "status": "doing",
             "done_when": T("sched.first_done"), "artifact": "", "note": ""}]
    for n, r in enumerate(io_rows, 2):
        rows.append({"id": "S-%02d" % n, "io": r["id"], "title": T("sched.row_title", name=r.get("name", ""), id=r["id"]), "status": "todo",
                     "done_when": T("sched.row_done", example=r.get("example", "")), "artifact": "", "note": ""})
    rows.append({"id": "S-%02d" % (len(rows) + 1), "title": T("sched.gate_title", n=len(cases)), "status": "todo",
                 "done_when": T("sched.gate_done"), "artifact": "", "note": "", "gate": "systemtest"})
    save_schedule(root, slug, {"project": c["name"], "stage": "RUN", "rows": date_rows(rows)})
    return 0, T("sched.made", rows=len(rows), cases=len(cases))


def cmd_mark(root, rid, status, evidence=None, note=None):
    c = compute(root)
    if c["stage"] != "RUN":
        return 2, T("mark.need_run", label=stage_label(c["stage"]))
    if status not in ("todo", "doing", "done", "hold"):
        return 2, T("mark.bad_state")
    sc = load_schedule(root, c["slug"])
    row = next((r for r in (sc or {}).get("rows", []) if r.get("id") == rid), None)
    if row is None:
        return 2, T("mark.no_row", id=rid)
    if status == "done" and row.get("gate") == "systemtest":
        sm = st_summary(root, c["slug"])
        if not first_version_done(sm):
            return 1, T("mark.st_not_ready", up=sm["user_pass"] if sm else 0, ut=sm["user_total"] if sm else 0,
                        np=sm["normal_pass"] if sm else 0, nt=sm["normal_total"] if sm else 0)
    if status == "done" and row.get("artifact") and not os.path.exists(os.path.join(root, row["artifact"])):
        return 1, T("mark.artifact_missing", artifact=row["artifact"])
    if status == "hold":
        if note and note.strip():
            row["note"] = note.strip()
        if not (row.get("note") or "").strip():
            return 1, T("mark.hold_need_note")
    if status == "done":
        if len((evidence or "").strip()) < 8:
            return 1, T("mark.need_evidence")
        row["evidence"] = evidence.strip()
    row["status"] = status
    save_schedule(root, c["slug"], sc)
    refresh_board_page(root)  # the schedule page of all projects follows the schedule
    return 0, T("mark.done", id=rid, status=status)


# ---------- task board: what is left, for every project ----------
# One signed record for each project (.ws/tasks_<slug>.json): the items the user asked for. The board is not saved. It is put together from this
# record, the missing items of the stage (compute) and the open rows of the build schedule, so that it cannot get out of date.
TASK_KINDS = ("req", "todo", "issue")
TASK_STATES = ("todo", "doing", "done", "hold", "dropped")
OPEN_STATES = ("todo", "doing", "hold")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
DIGEST_CAP = 700  # characters the board adds to one prompt (the triage line included)
DIGEST_ITEMS = 5
TITLE_CUT = 60
GANTT_DAYS = 21  # the text Gantt shows 3 weeks
GANTT_LABEL = 24  # columns of the label (a mark, the id and the title)
GANTT_COLS = 60  # a line of the text Gantt stays about this wide


def tasks_name(slug):
    return "tasks_%s.json" % slug


def tasks_load(root, slug):
    """The items of one project (a list). A record whose signature does not match counts as missing, with a warning."""
    rec = load_rec(root, tasks_name(slug), slug, None) or {}
    return [i for i in rec.get("items", []) if isinstance(i, dict)]


def tasks_save(root, slug, items):
    save_rec(root, tasks_name(slug), {"items": items}, slug)


def tasks_broken(root, slug):
    """The record is there but its signature does not match (it was changed by hand). It is never written over."""
    return os.path.exists(os.path.join(ws_dir(root), tasks_name(slug))) and load_rec(root, tasks_name(slug), slug, None) is None


def date_arg(v):
    """'2026-11-05' -> itself, '-' or nothing -> '', anything else -> None."""
    v = nfkc(v or "").strip()
    if v in ("", "-"):
        return ""
    if DATE_RE.match(v):
        try:
            datetime.date(int(v[:4]), int(v[5:7]), int(v[8:]))
            return v
        except ValueError:
            pass
    return None


def to_date(s):
    return datetime.date(int(s[:4]), int(s[5:7]), int(s[8:]))


def resolve_project(root, name):
    """A project folder from its folder name, or from the name after the number (`01_app` or `app`)."""
    found = list_projects(root)
    if name in found:
        return name
    hit = [x for x in found if re.sub(r"^\d\d_", "", x) == name]
    return hit[0] if len(hit) == 1 else None


def board_rows(root, slug, closed=False):
    """The items of one project and the rows of its build schedule as one list: id, title, kind, status, start, due, tent.
    Only what is still open; with closed=True the done ones too. A dropped item is never shown."""
    keep = OPEN_STATES + (("done",) if closed else ())
    rows = []
    for it in tasks_load(root, slug):
        if it.get("status") in keep:
            rows.append({"id": str(it.get("id", "")), "title": " ".join(str(it.get("title", "")).split()), "kind": it.get("kind") if it.get("kind") in TASK_KINDS else "req",
                         "status": it["status"], "start": str(it.get("start") or ""), "due": str(it.get("due") or ""), "tent": it.get("tentative", True) is not False})
    for r in (load_schedule(root, slug) or {}).get("rows", []):
        if isinstance(r, dict) and r.get("status", "todo") in keep:
            rows.append({"id": str(r.get("id", "")), "title": " ".join(str(r.get("title", "")).split()), "kind": "build", "status": r.get("status", "todo"),
                         "start": str(r.get("start") or ""), "due": str(r.get("due") or ""), "tent": r.get("tentative", True) is not False})
    return rows


def row_order(r):
    """The user's items first, then the build rows; what is being done first; then the nearest date."""
    return (r["kind"] == "build", r["status"] != "doing", r["due"] or r["start"] or "9999-99-99", r["id"])


def short_date(d, today):
    return d[5:] if d[:4] == str(today.year) else d


def span_text(r, today):
    a, b, mark = r["start"], r["due"], "~" if r["tent"] else ""
    if a and b:
        return T("task.d.range", a=short_date(a, today), b=short_date(b, today)) + mark
    if b:
        return T("task.d.due", d=short_date(b, today)) + mark
    if a:
        return T("task.d.from", d=short_date(a, today)) + mark
    return ""


def item_line(r, today, cut=TITLE_CUT):
    """T-03 [req, doing] Export to CSV (due 11-05~)"""
    title = r["title"] if len(r["title"]) <= cut else r["title"][:cut - 1] + "…"
    sp = span_text(r, today)
    return "%s [%s, %s] %s%s" % (r["id"], r["kind"], r["status"], title, " (%s)" % sp if sp else "")


def kinds_text(rows):
    n = {}
    for r in rows:
        n[r["kind"]] = n.get(r["kind"], 0) + 1
    return ", ".join("%s %d" % (k, n[k]) for k in TASK_KINDS + ("build",) if n.get(k))


def next_due(rows, today):
    dues = sorted((r["due"], r["tent"]) for r in rows if r["due"])
    return short_date(dues[0][0], today) + ("~" if dues[0][1] else "") if dues else ""


def open_block(root, slug, limit=12):
    """Once, when a project becomes active (select, new, the automatic choice): what is open in it. The missing items of the stage (one line),
    then the user's items, then the open build rows. `limit` lines at most, then how to see the rest."""
    ci = compute(root, slug)
    today = datetime.date.today()
    lines = ([T("task.b.stage", label=missing_label(ci["stage"]), items=T("sep.list").join(ci["todo"]))] if ci["todo"] else [])
    lines += [item_line(r, today) for r in sorted(board_rows(root, slug), key=row_order)]
    if not lines:
        return ""
    return "\n".join([T("task.dig.head", name=ci["name"])] + lines[:limit] + ([T("task.more_tasks", n=len(lines) - limit)] if len(lines) > limit else []))


def continuing_note(root, name):
    """note.continuing, and with it what is open in the project that was just chosen."""
    block = open_block(root, get_state(root).get("active") or "")
    return T("note.continuing", name=name) + ("\n" + block if block else "")


def task_session_block(root, c, skip_active=False):
    """SessionStart: one line for each project (8 at most), then the open items of the active one (6 at most), then where to look."""
    found = list_projects(root)
    if not found:
        return ""
    today = datetime.date.today()
    lines = [T("task.sess.head")]
    for sl in found[:8]:
        ci = compute(root, sl)
        rows = board_rows(root, sl)
        kinds = kinds_text(rows)
        due = next_due(rows, today)
        lines.append(T("task.sess.line", name=ci["name"], label=stage_label(ci["stage"]), n=len(rows), kinds=" (%s)" % kinds if kinds else "",
                       due=T("task.sess.due", d=due) if due else ""))
    if len(found) > 8:
        lines.append(T("task.more", n=len(found) - 8))
    if c.get("slug") and not skip_active:  # (just chosen: the continuing note already has its open items)
        rows = sorted(board_rows(root, c["slug"]), key=row_order)
        if rows:
            lines.append(T("task.sess.open", name=c["name"]))
            lines += ["  " + item_line(r, today) for r in rows[:6]]
            if len(rows) > 6:
                lines.append("  " + T("task.more", n=len(rows) - 6))
    lines.append(T("task.sess.how"))
    return "\n".join(lines)


def task_prompt_digest(root, c, triage, soft):
    """UserPromptSubmit: the open items of the active project, the open count of the others, and the triage line.
    The whole text stays under DIGEST_CAP characters: the items give way first."""
    today = datetime.date.today()
    slug = c.get("slug")
    rows = sorted(board_rows(root, slug), key=row_order) if slug else []
    shown = [item_line(r, today) for r in rows[:DIGEST_ITEMS]]
    others = []
    for sl in list_projects(root):
        k = len(board_rows(root, sl)) if sl != slug else 0
        if k:
            others.append("%s %d" % (parse_project(root, sl).get("name", sl), k))
    tail = [T("task.dig.others", items=", ".join(others[:4]) + (", +%d" % (len(others) - 4) if len(others) > 4 else ""))] if others else []
    tail += [T("task.triage")] if triage else ([T("note.task_soft")] if soft else [])
    head = [T("task.dig.head", name=c["name"])] if rows else []

    def build(k):
        return head + shown[:k] + ([T("task.more", n=len(rows) - k)] if len(rows) > k else []) + tail
    k = len(shown)
    while k > 0 and len("\n".join(build(k))) > DIGEST_CAP:
        k -= 1
    return "\n".join(build(k))


def missing_label(stage):
    """What the missing items of the stage are for: before the build, to start it, or to finish the first version (nothing for DONE)."""
    return T("task.b.stage." + (stage if stage in ("RS", "RUN") else "pre"))


def tasks_data(root):
    """What the schedule page shows: every project with its stage, what is missing before the build, and its dated and undated items."""
    out = []
    for sl in list_projects(root):
        ci = compute(root, sl)
        out.append({"slug": sl, "name": ci["name"], "stage": ci["stage"], "stage_label": stage_label(ci["stage"]), "missing_label": missing_label(ci["stage"]), "missing": list(ci["todo"]),
                    "items": sorted(board_rows(root, sl, closed=True), key=lambda r: (r["start"] or r["due"] or "9999-99-99", r["id"]))})
    return {"generated": time_now(), "projects": out}


def render_tasks_page(root):
    """Write projects/schedule.html for all projects. Returns its path, or None when the template is missing."""
    out = _embed(os.path.join(root, "ws", "render", "tasks.template.html"), tasks_data(root), "tasks")
    if out is None:
        return None
    path = board_page_path(root)
    same = lambda t: re.sub(r'"generated": "[^"]*"', '"generated": ""', t or "")  # the time of the last change does not count as a change
    if same(read_text(path)) != same(out):
        write_text(path, out)
    return path


def board_page_path(root):
    return os.path.join(root, GANTT_REL)


def refresh_board_page(root):
    """Render the schedule page and never raise (a hook must not break because of it). Returns the path, or None when it failed."""
    try:
        return render_tasks_page(root)
    except Exception:
        return None


def board_warn(root):
    """For the hooks: render the page when a project exists. One short warning line if that failed, else nothing."""
    if list_projects(root) and refresh_board_page(root) is None:
        return T("task.render_warn")
    return ""


def with_page(root, msg):
    """The last line of task add / set / date: where the up-to-date schedule is."""
    return msg + "\n" + T("task.page_updated", path=board_page_path(root))


def disp_width(text):
    """Columns the text takes on a terminal: a wide or full-width character (Japanese, Chinese, Korean) takes 2."""
    return sum(2 if unicodedata.east_asian_width(ch) in "WF" else 1 for ch in text)


def fit_width(text, cols, pad=True):
    """Cut the text to `cols` columns (a cut ends with …) and, unless pad is False, fill it with spaces up to `cols`."""
    if disp_width(text) > cols:
        out, w = "", 0
        for ch in text:
            cw = disp_width(ch)
            if w + cw > cols - 1:
                break
            out, w = out + ch, w + cw
        text = out + "…"
    return text + " " * (cols - disp_width(text)) if pad else text


def gantt_text(root):
    """The next 3 weeks in plain text for the chat, one character for each day, from the Monday of this week.
    # fixed date, ~ tentative date, = done, > in progress (before the title), ^ today, < earlier than the window, + later than it."""
    data = tasks_data(root)
    today = datetime.date.today()
    day = datetime.timedelta(days=1)
    first = today - datetime.timedelta(days=today.weekday())
    last = first + (GANTT_DAYS - 1) * day
    shown = lambda r: bool(r["start"] or r["due"]) and not (r["status"] == "done" and to_date(r["due"] or r["start"]) < first)  # old finished work is left out
    if not any(shown(r) for p in data["projects"] for r in p["items"]):
        return T("task.gantt.none")
    pad = " " * GANTT_LABEL
    out = [fit_width(T("task.gantt.head", today=today.isoformat()), GANTT_COLS, pad=False),
           pad + "".join((first + 7 * k * day).strftime("%m-%d").ljust(7) for k in range(GANTT_DAYS // 7)),
           pad + " " * (today - first).days + "^"]
    for p in data["projects"]:
        mine = [r for r in p["items"] if shown(r)]
        undated = [r for r in p["items"] if not (r["start"] or r["due"]) and r["status"] != "done"]
        if not mine and not undated:
            continue
        out.append(fit_width(T("task.gantt.proj", name=p["name"], label=p["stage_label"]), GANTT_COLS, pad=False))
        for r in mine:
            a, b = to_date(r["start"] or r["due"]), to_date(r["due"] or r["start"])
            ch = "=" if r["status"] == "done" else ("~" if r["tent"] else "#")
            cells = [ch if a <= first + i * day <= b else "." for i in range(GANTT_DAYS)]
            if b < first:
                cells[0] = "<"
            elif a > last:
                cells[-1] = "+"
            label = fit_width((">" if r["status"] == "doing" else " ") + r["id"] + " " + r["title"], GANTT_LABEL)
            out.append(label + "".join(cells))
        if undated:
            more = " +%d" % (len(undated) - 6) if len(undated) > 6 else ""
            items = "; ".join("%s %s" % (r["id"], r["title"]) for r in undated[:6]) + more
            out.append(fit_width("  " + T("task.gantt.nodate", items=items), GANTT_COLS, pad=False))
    out.append(T("task.gantt.legend"))
    return "\n".join(out)


def board_text(root, slug=None):
    """The whole board in text: for each project the goal, what is missing before the build, the open build rows, and the open items."""
    today = datetime.date.today()
    found = [slug] if slug else list_projects(root)
    if not found:
        return T("list.none")
    out = []
    for sl in found:
        ci = compute(root, sl)
        p = parse_project(root, sl)
        out.append(T("task.b.head", name=ci["name"], slug=sl, label=stage_label(ci["stage"])))
        if filled(p.get("what")):
            out.append("  " + T("task.b.goal", what=p["what"][:120]))
        if ci["todo"]:
            out.append("  " + T("task.b.stage", label=missing_label(ci["stage"]), items=T("sep.list").join(ci["todo"])))
        rows = sorted(board_rows(root, sl), key=row_order)
        for title, part in ((T("task.b.sched"), [r for r in rows if r["kind"] == "build"]), (T("task.b.items"), [r for r in rows if r["kind"] != "build"])):
            if part:
                out.append("  " + title)
                out += ["    " + item_line(r, today, cut=100) for r in part]
        if not rows and not ci["todo"]:
            out.append("  " + T("task.b.nothing"))
        closed = [i.get("status") for i in tasks_load(root, sl) if i.get("status") in ("done", "dropped")]
        if closed:
            out.append("  " + T("task.b.closed", done=closed.count("done"), dropped=closed.count("dropped")))
        if tasks_broken(root, sl):
            out.append("  " + T("task.broken", slug=sl))
    return "\n".join(out)


def clear_triage(root):
    if get_session(root).get("triage") is not None:
        set_session(root, triage=None)


def board_changed(root):
    """After a write: this message is sorted (the triage is done), and the schedule page shows the new state."""
    clear_triage(root)
    refresh_board_page(root)


def task_args(rest):
    """Split `"title" --kind req --fixed` into (words, {option: value}, {flags}). None when an option is unknown or has no value."""
    words, opts, flags, i = [], {}, set(), 0
    while i < len(rest):
        a = rest[i]
        if a in ("--kind", "--start", "--due", "--project", "--note", "--how"):
            if i + 1 >= len(rest):
                return None
            opts[a] = rest[i + 1]
            i += 1
        elif a == "--fixed":
            flags.add(a)
        elif a.startswith("--"):
            return None
        else:
            words.append(a)
        i += 1
    return words, opts, flags


def cmd_task(root, rest):
    sub = rest[0] if rest else ""
    parsed = task_args(rest[1:])
    if sub not in ("add", "set", "date", "none") or parsed is None:
        return 2, T("task.usage")
    words, opts, flags = parsed
    if sub == "none":
        clear_triage(root)
        return 0, T("task.none")
    c = compute(root)
    slug = c["slug"]
    if "--project" in opts:
        slug = resolve_project(root, opts["--project"])
        if not slug:
            return 2, T("task.no_such_project", slug=opts["--project"])
    if not slug:
        return 2, T("task.no_project")
    name = parse_project(root, slug).get("name", slug)
    if tasks_broken(root, slug):
        return 1, T("task.broken", slug=slug)
    items = tasks_load(root, slug)
    if sub == "add":
        title = " ".join(" ".join(words).split())
        kind = opts.get("--kind", "req")
        start, due = date_arg(opts.get("--start")), date_arg(opts.get("--due"))
        if not title or len(title) > 120:
            return 1, T("task.need_title")
        if has_key(title):
            return 1, T("deny.key_in_write")
        if kind not in TASK_KINDS:
            return 2, T("task.bad_kind")
        if start is None or due is None:
            return 2, T("task.bad_date")
        if start and due and start > due:
            return 2, T("task.date_order")
        nums = [int(m.group(1)) for i in items for m in [re.match(r"^T-(\d+)$", str(i.get("id", "")))] if m]
        sess = get_session(root)
        tid = "T-%02d" % (max(nums + [0]) + 1)
        items.append({"id": tid, "title": title, "kind": kind, "status": "todo", "start": start, "due": due, "tentative": "--fixed" not in flags,
                      "from": "prompt %d: %s" % (int(sess.get("prompts", 0)), " ".join(str(sess.get("last_prompt", "")).split())[:60]), "note": "", "how": ""})
        tasks_save(root, slug, items)
        board_changed(root)
        return 0, with_page(root, T("task.added", id=tid, kind=kind, name=name))
    if len(words) < (2 if sub == "set" else 3):
        return 2, T("task.usage")
    tid = words[0]
    is_row = re.match(r"^S-\d+$", tid) is not None
    if sub == "set":
        status = words[1]
        if status not in TASK_STATES:
            return 2, T("task.bad_state")
        if is_row:  # a row of the build schedule: the same rules as `mark`
            if slug != c["slug"]:
                return 2, T("task.s_other")
            if status == "dropped":
                return 1, T("task.s_drop")
            rc, msg = cmd_mark(root, tid, status, opts.get("--how"), opts.get("--note"))
            if rc == 0:
                clear_triage(root)
                msg = with_page(root, msg)
            return rc, msg
        it = next((i for i in items if i.get("id") == tid), None)
        if it is None:
            return 1, T("task.no_item", id=tid, name=name)
        note, how = (opts.get("--note") or "").strip(), (opts.get("--how") or "").strip()
        if has_key(note + "\n" + how):
            return 1, T("deny.key_in_write")
        if status == "done" and len(how) < 8:
            return 1, T("task.need_how")
        if note:
            it["note"] = note
        if status in ("hold", "dropped") and not str(it.get("note", "")).strip():
            return 1, T("task.need_note")
        if status == "done":
            it["how"] = how
        it["status"] = status
        tasks_save(root, slug, items)
        board_changed(root)
        return 0, with_page(root, T("task.set", id=tid, status=status))
    start, due = date_arg(words[1]), date_arg(words[2])  # date
    if start is None or due is None:
        return 2, T("task.bad_date")
    if start and due and start > due:
        return 2, T("task.date_order")
    if is_row:
        sc = load_schedule(root, slug)
        row = next((r for r in (sc or {}).get("rows", []) if r.get("id") == tid), None)
        if row is None:
            return 1, T("mark.no_row", id=tid)
        row.update(start=start, due=due, tentative="--fixed" not in flags)
        save_schedule(root, slug, sc)
    else:
        it = next((i for i in items if i.get("id") == tid), None)
        if it is None:
            return 1, T("task.no_item", id=tid, name=name)
        it.update(start=start, due=due, tentative="--fixed" not in flags)
        tasks_save(root, slug, items)
    board_changed(root)
    return 0, with_page(root, T("task.dated", id=tid, start=start or "-", due=due or "-", how=T("task.fixed") if "--fixed" in flags else T("task.tentative")))


def cmd_tasks(root, rest):
    if rest and rest[0] == "gantt":
        path = render_tasks_page(root)
        if path is None:
            return 1, T("render.no_template", name="tasks.template.html")
        page = T("task.gantt.page", path=path)
        return 0, (gantt_text(root) + "\n" + page) if "--text" in rest else page
    slug = resolve_project(root, rest[0]) if rest else None
    if rest and not slug:
        return 2, T("task.no_such_project", slug=rest[0])
    return 0, board_text(root, slug)


def secret_file(root, project=None):
    if project:
        return os.path.join(projects_dir(root), project, "src", ".env")
    override = os.environ.get("CREATECODEBOX_SECRETS")
    if override:
        return os.path.join(os.path.expanduser(override), ".env")
    return os.path.join(os.path.expanduser("~"), ".createcodebox", ".env")


def parse_env(path):
    out = {}
    for line in (read_text(path) or "").splitlines():
        m = re.match(r"^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*?)\s*$", line)
        if m and not line.lstrip().startswith("#"):
            v = m.group(2)
            if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
                v = v[1:-1]
            out[m.group(1)] = v
    return out


def cmd_secret_all(root):
    """名前と設定済み／空だけを一覧にする（値は出さない）。.env.example と突き合わせて足りない名前も出す。"""
    lines = []
    g = secret_file(root)
    lines.append(T("secret.all.head", path=g))
    for k, v in sorted(parse_env(g).items()):
        lines.append("  %s: %s" % (k, T("secret.state.set") if v else T("secret.state.empty")))
    if len(lines) == 1:
        lines.append(T("secret.none_yet"))
    for slug in list_projects(root):
        env = parse_env(secret_file(root, slug))
        need = parse_env(os.path.join(projects_dir(root), slug, "src", ".env.example"))
        lines.append(T("secret.project", slug=slug))
        for k in sorted(set(env) | set(need)):
            state = T("secret.state.set") if env.get(k) else (T("secret.state.missing") if k in need else T("secret.state.empty"))
            lines.append("  %s: %s" % (k, state))
        if not env and not need:
            lines.append(T("secret.no_keys"))
    return 0, "\n".join(lines)


def with_secrets_ok(root, command):
    """F2: only (1) a script declared in package.json, (2) `python|node <file in src/>`, (3) the exact command in the user's latest input."""
    joined = " ".join(command)
    last = nfkc(get_session(root).get("last_prompt", ""))
    if joined and nfkc(joined) in last:
        return True, command
    slug = compute(root)["slug"]
    if not slug:
        return False, command
    src = os.path.join(projects_dir(root), slug, "src")
    pj = load_json(os.path.join(src, "package.json"))
    scripts = pj.get("scripts") if isinstance(pj, dict) and isinstance(pj.get("scripts"), dict) else {}
    if command[0] == "npm":
        if command[1:] in (["start"], ["test"]) and command[1] in scripts:
            return True, command
        if len(command) == 3 and command[1] == "run" and command[2] in scripts:
            return True, command
    if os.path.basename(command[0]).lower().rstrip("0123456789.") in ("python", "node", "python.exe", "node.exe") and len(command) >= 2 and not command[1].startswith("-"):
        f = command[1]
        cands = [f] if os.path.isabs(f) else [os.path.join(root, f), os.path.join(src, f)]
        for cand in cands:
            real = os.path.realpath(cand)
            if os.path.isfile(real) and (real + os.sep).startswith(os.path.realpath(src) + os.sep):
                return True, [command[0], real] + command[2:]
    return False, command


def cmd_with_secrets(root, command, project=False, timeout=600):
    """Run the command with the secret values in its environment. Output is streamed line by line; the values are replaced by ***."""
    if not command:
        return 2, T("ws.with_secrets.usage")
    ok, command = with_secrets_ok(root, command)
    if not ok:
        return 2, T("ws.with_secrets.refused")
    values = {}
    values.update(parse_env(secret_file(root)))
    slug = compute(root)["slug"]
    if project and slug:
        values.update(parse_env(secret_file(root, slug)))
    env = dict(os.environ)
    env.update({k: v for k, v in values.items() if v})
    cwd = os.path.join(projects_dir(root), slug, "src") if slug and os.path.isdir(os.path.join(projects_dir(root), slug, "src")) else root
    secrets = [v for v in values.values() if len(v) >= 4]
    import threading
    try:
        p = subprocess.Popen(command, env=env, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                             bufsize=1, errors="replace")
    except OSError as e:
        return 1, T("ws.with_secrets.cannot", err=type(e).__name__)

    def pump():
        for line in p.stdout:
            sys.stdout.write(redact(line, secrets))
            sys.stdout.flush()
    th = threading.Thread(target=pump, daemon=True)
    th.start()
    try:
        p.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        p.kill()
        th.join(5)
        return 124, T("ws.with_secrets.timeout", sec=timeout)
    th.join(10)
    return p.returncode, T("ws.with_secrets.done", rc=p.returncode)


NAME_RE = re.compile(r"^[A-Z][A-Z0-9_]*$")


def set_secret_value(path, name, value):
    """NAME=値 の行を、ファイルの中で入れ替える（無ければ足す）。権限は 600。"""
    lines = (read_text(path) or T("secret.template")).splitlines()
    out, done = [], False
    for line in lines:
        m = re.match(r"^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=", line)
        if m and m.group(1) == name and not line.lstrip().startswith("#"):
            if not done:
                out.append("%s=%s" % (name, value))
                done = True
            continue
        out.append(line)
    if not done:
        out.append("%s=%s" % (name, value))
    write_text(path, "\n".join(out) + "\n")
    try:
        os.chmod(path, 0o600)
        os.chmod(os.path.dirname(path), 0o700)
    except OSError:
        pass


def cmd_secret_set(root, name, project=False):
    if not name or not NAME_RE.match(name):
        return 2, T("secret.bad_name")
    if not sys.stdin.isatty():
        return 1, T("secret.need_tty", name=name)
    slug = None
    if project:
        slug = compute(root)["slug"]
        if not slug:
            return 2, T("common.no_project")
    import getpass
    v = getpass.getpass(T("secret.prompt", name=name)).strip()
    if not v:
        return 1, T("secret.empty")
    path = secret_file(root, slug)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    set_secret_value(path, name, v)
    return 0, T("secret.set_done", name=name)


def cmd_secret_guide(root, name, project=False):
    if not name or not NAME_RE.match(name):
        return 2, T("secret.bad_name")
    tail = " --project" if project else ""
    return 0, T("secret.guide", root=root, name=name, tail=tail)


def cmd_secret(root, action, project=False):
    slug = None
    if project:
        slug = compute(root)["slug"]
        if not slug:
            return 2, T("common.no_project")
    path = secret_file(root, slug)
    if action == "path":
        return 0, path
    if action in ("open", "check") and not os.path.exists(path):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        write_text(path, T("secret.template"))
        try:
            os.chmod(path, 0o600)
            os.chmod(os.path.dirname(path), 0o700)
        except OSError:
            pass
    if action == "open":
        opener = {"darwin": ["open", "-t"], "win32": ["notepad"]}.get(sys.platform, ["xdg-open"])
        try:
            subprocess.Popen(opener + [path])
        except OSError:
            return 1, T("secret.editor_fail", path=path)
        return 0, T("secret.opened", path=path)
    if action == "check":
        names = ["%s: %s" % (k, T("secret.state.set") if v else T("secret.state.empty")) for k, v in sorted(parse_env(path).items())]
        return 0, (T("secret.check_head") + "\n" + "\n".join(names)) if names else T("secret.check_none")
    return 2, T("secret.usage")


def last_prompt_text(root):
    return nfkc(get_session(root).get("last_prompt", ""))


def cmd_lang(root, rest):
    if rest and rest[0] == "set":
        code = (rest[1] if len(rest) > 1 else "").lower()
        if not re.match(r"^[a-z]{2,5}$", code):
            return 2, T("lang.usage")
        set_lang(root, code)
        lang.use(code)
        return 0, T("lang.set", code=code)
    return 0, T("lang.show", code=get_lang(root))


def cmd_resign(root):
    if not re.search(r"(?<![A-Za-z])resign(?![A-Za-z])", last_prompt_text(root).lower()):
        return 1, T("resign.need_word")
    n = resign_all(root)
    if n is None:
        return 1, T("resign.no_key")
    return 0, T("resign.done", n=n)


def cmd_secret_allow(root, fp):
    if not fp or not re.match(r"^[0-9a-f]{12}$", fp):
        return 2, T("secret_allow.usage")
    if fp not in last_prompt_text(root):
        return 1, T("secret_allow.need_word")
    cur = sorted(secret_allow(root) | {fp})
    save_rec(root, "secret_allow.json", {"fingerprints": cur}, "")
    return 0, T("secret_allow.done", fp=fp)


def cmd_excludes_add(root, path):
    if not path or not os.path.isabs(path):
        return 2, T("excludes.usage")
    real = os.path.realpath(path)
    if real not in [os.path.realpath(p) for p in ancestor_claude_files(root)]:
        return 1, T("excludes.not_ancestor")
    if path not in last_prompt_text(root) and nfkc(path) not in last_prompt_text(root):
        return 1, T("excludes.need_word")
    sp = settings_local_path(root)
    d = load_json(sp, {}) or {}
    lst = d.get("claudeMdExcludes") if isinstance(d.get("claudeMdExcludes"), list) else []
    if path not in lst:
        lst.append(path)
    d["claudeMdExcludes"] = lst
    save_json(sp, d)
    rec = load_rec(root, "excludes.json", "", {}) or {}
    paths = rec.get("paths") if isinstance(rec.get("paths"), list) else []
    if path not in paths:
        paths.append(path)
    save_rec(root, "excludes.json", {"paths": paths}, "")
    return 0, T("excludes.done", path=path)


def cmd_rules_import(root, path):
    slug, srcd = src_of(root)
    if not slug:
        return 2, T("common.need_project")
    if not path:
        return 2, T("rules.usage")
    last = last_prompt_text(root)
    if nfkc(path) not in last:
        return 1, T("rules.need_word")
    p = os.path.realpath(os.path.expanduser(path) if path.startswith("~") else (path if os.path.isabs(path) else os.path.join(root, path)))
    home_rules = os.path.realpath(os.path.join(os.path.expanduser("~"), ".claude", "CLAUDE.md"))
    in_src = (p + os.sep).startswith(os.path.realpath(srcd) + os.sep)
    if not (in_src or p == home_rules):
        return 1, T("rules.bad_place")
    if not os.path.isfile(p):
        return 1, T("rules.no_file")
    if os.path.getsize(p) > 65536:
        return 1, T("rules.too_big")
    text = read_text(p) or ""
    if has_key(text, p, root=root):
        return 1, T("rules.has_key")
    dest = os.path.join(projects_dir(root), slug, "knowledge", "imported_rules.md")
    block = T("rules.header", date=datetime.date.today().isoformat(), path=path) + "\n\n" + text.rstrip() + "\n"
    old = read_text(dest)
    write_text(dest, block if not old else old.rstrip() + "\n\n---\n\n" + block)
    return 0, T("rules.done", dest="projects/%s/knowledge/imported_rules.md" % slug)


def cmd_open(root, path):
    c = compute(root)
    board = bool(path) and os.path.realpath(path if os.path.isabs(path) else os.path.join(root, path)) == os.path.realpath(os.path.join(root, GANTT_REL))
    if not board and (not c["slug"] or c["stage"] == "R0"):  # the schedule page of all projects needs no project
        return 2, T("common.need_project")
    if not path:
        return 2, T("open.usage")
    p = os.path.realpath(path if os.path.isabs(path) else os.path.join(root, path))
    slug = c["slug"]
    ok_dirs = [os.path.realpath(os.path.join(projects_dir(root), slug, s)) for s in ("design", "src")] if slug else []
    if not board and not any((p + os.sep).startswith(d + os.sep) for d in ok_dirs):
        return 1, T("open.bad_place")
    if os.path.splitext(p)[1].lower() not in (".html", ".png", ".svg", ".pdf"):
        return 1, T("open.bad_type")
    if not os.path.isfile(p):
        return 1, T("open.no_file")
    if os.environ.get("CREATECODEBOX_OPEN_DRY_RUN") == "1":
        return 0, T("open.would", path=rel_in_root(root, p) or p)
    opener = {"darwin": ["open"], "win32": ["cmd", "/c", "start", ""]}.get(sys.platform, ["xdg-open"])
    try:
        subprocess.Popen(opener + [p], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except OSError:
        return 1, T("open.failed", path=p)
    return 0, T("open.done", path=rel_in_root(root, p) or p)


def select_summary(root, slug):
    """C4: where we were, what is next, and what to look at."""
    c = compute(root, slug)
    look = "-"
    for rel in ("schedule.html", "io.html", os.path.join("ui", "index.html"), os.path.join("ui", "sketch.html")):
        if os.path.isfile(os.path.join(design_dir(root, slug), rel)):
            look = "projects/%s/design/%s" % (slug, rel.replace(os.sep, "/"))
            break
    return "\n" + T("select.summary", stage=c["stage"], next=(c["todo"][0] if c["todo"] else "-"), look=look)


def cmd_update(root):
    if not os.path.isdir(os.path.join(root, ".git")):
        return 1, T("update.no_git")
    dirty = subprocess.run(["git", "status", "--porcelain", "--untracked-files=no"], cwd=root,
                           capture_output=True, text=True).stdout.strip()
    if dirty:
        return 1, T("update.dirty", dirty=dirty)
    old = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root, capture_output=True, text=True).stdout.strip()
    try:  # never wait for a password, and never hang the session
        r = subprocess.run(["git", "pull", "--ff-only"], cwd=root, capture_output=True, text=True, timeout=120,
                           env=dict(os.environ, GIT_TERMINAL_PROMPT="0", GIT_ASKPASS="", SSH_ASKPASS="", GIT_SSH_COMMAND="ssh -o BatchMode=yes"))
    except subprocess.TimeoutExpired:
        return 1, T("update.timeout")
    msg = (r.stdout + r.stderr).strip() + "\n" + T("update.version", v=version(root))
    if r.returncode == 0 and old:
        changed = subprocess.run(["git", "diff", "--name-only", old, "HEAD", "--", ".codex/hooks.json"], cwd=root,
                                 capture_output=True, text=True).stdout.split()
        if changed:
            msg += "\n" + T("update.codex_hooks")
        msg += "\n" + T("update.reopen")
    return (0 if r.returncode == 0 else 1), msg


# ---------- 入口 ----------
# The host's side of the hooks (the workspace root, how the input is read, the shape of each answer) is in the adapter
# (ws/adapters/claude.py). Here the engine only decides what to answer.
def project_root():
    return ADAPTER.project_root()


def _emit(obj):
    ADAPTER.write(obj)


def deny_json(reason):
    return ADAPTER.deny(reason)


def _hook_dispatch(kind, root, event):
    if kind == "pretool":
        if not isinstance(event, dict):
            reason = T("deny.hook_input")
        else:
            try:
                reason = gate(root, event)
            except Exception as e:  # 判断できないときは止める
                reason = T("deny.hook_error", err=type(e).__name__)
        if reason:
            _emit(deny_json(reason))
        return
    event = event if isinstance(event, dict) else {}
    if kind == "stop":
        why = on_stop(root, event)
        if why:
            _emit(ADAPTER.stop_block(why))
        return
    if kind == "prompt" and has_key(event.get("prompt") or "", config=True):
        _emit(ADAPTER.prompt_block(T("block.key_in_prompt")))
        return
    handlers = {"sessionstart": on_session_start, "prompt": on_prompt}
    if kind in handlers:
        _emit(ADAPTER.context(kind, handlers[kind](root, event)))


def select_client(name):
    """Choose the host's adapter (claude or codex). Anything else is claude."""
    global ADAPTER
    ADAPTER = adapters.load(name)
    return ADAPTER.NAME


def hook_main(kind, client=None):
    """Returns the exit code. pretool: an error becomes a deny (exit 0), and exit 2 if even that fails.
    prompt: an error becomes a warning context (exit 0). sessionstart / stop: always exit 0.
    client: "claude" or "codex" (the --client argument of the hook command); None means CREATECODEBOX_CLIENT, else claude."""
    setup_io()
    try:
        select_client(client if client else os.environ.get("CREATECODEBOX_CLIENT"))
        root = project_root()
        event = ADAPTER.read_event()
        lang.use(get_lang(root))
        if kind != "pretool":
            migrate_legacy(root)
        if ADAPTER.NAME == "codex" and kind == "sessionstart":
            set_session(root, client="codex")  # `doctor` (run from the shell) then shows the Codex lines
        _hook_dispatch(kind, root, event)
        return 0
    except BaseException as e:
        try:
            if kind == "pretool":
                _emit(deny_json(T("deny.hook_error", err=type(e).__name__)))
                return 0
            if kind == "prompt":
                _emit(ADAPTER.context("prompt", "Reply in: en\n" + T("warn.hook_error", err=type(e).__name__)))
            return 0
        except BaseException:
            return 2 if kind == "pretool" else 0



def cli_main(argv):
    setup_io()
    root = project_root()
    lang.use(get_lang(root))
    migrate_legacy(root)
    cmd = argv[0] if argv else "status"
    rest = argv[1:]

    def opt(name):
        if name in rest:
            i = rest.index(name)
            return rest[i + 1] if i + 1 < len(rest) else None
        return None
    if cmd == "status":
        c0 = compute(root)
        print(stage_text(c0))
        rl = repo_line(root, c0["slug"])
        if rl:
            print(rl)
        print(project_list_text(root))
        return 0
    if cmd == "list":
        print(project_list_text(root))
        return 0
    if cmd == "doctor":
        print("\n".join(doctor(root)))
        return 0
    if cmd == "version":
        print(version(root))
        return 0
    if cmd == "select" and rest:
        rc, msg = cmd_select(root, rest[0], opt("--quote"))
    elif cmd == "new" and rest:
        rc, msg = cmd_select(root, rest[0], opt("--quote"), new=True, name=opt("--name"))
    elif cmd == "st":
        rc, msg = cmd_st(root, rest)
    elif cmd == "harden":
        rc, msg = cmd_harden(root, rest[0] if rest else "status", "--with-denywrite" in rest)
    elif cmd == "learn":
        rc, msg = cmd_learn(root, rest[0] if rest else None)
    elif cmd == "lang":
        rc, msg = cmd_lang(root, rest)
    elif cmd == "open":
        rc, msg = cmd_open(root, rest[0] if rest else None)
    elif cmd == "resign":
        rc, msg = cmd_resign(root)
    elif cmd == "excludes" and rest and rest[0] == "add":
        rc, msg = cmd_excludes_add(root, rest[1] if len(rest) > 1 else None)
    elif cmd == "rules" and rest and rest[0] == "import":
        rc, msg = cmd_rules_import(root, rest[1] if len(rest) > 1 else None)
    elif cmd == "repo" and rest and rest[0] == "init":
        rc, msg = cmd_repo_init(root)
    elif cmd == "repo" and len(rest) >= 2 and rest[0] == "link":
        rc, msg = cmd_repo_link(root, rest[1])
    elif cmd == "repo" and rest and rest[0] == "email":
        rc, msg = cmd_repo_email(root, rest[1] if len(rest) > 1 else None)
    elif cmd == "repo" and len(rest) >= 2 and rest[0] == "adopt":
        rc, msg = cmd_repo_adopt(root, rest[1])
    elif cmd == "save":
        rc, msg = cmd_save(root, " ".join(rest))
    elif cmd == "backup":
        rc, msg = cmd_backup(root)
    elif cmd == "publish-check":
        rc, msg = cmd_publish_check(root)
    elif cmd == "publish":
        rc, msg = cmd_publish(root)
    elif cmd == "intake" and rest:
        rc, msg = cmd_intake(root, rest[0])
    elif cmd == "lint":
        rc, msg = cmd_lint(root)
    elif cmd == "render":
        rc, msg = cmd_render(root)
    elif cmd == "schedule-init":
        rc, msg = cmd_schedule_init(root)
    elif cmd == "mark" and len(rest) >= 2:
        rc, msg = cmd_mark(root, rest[0], rest[1], read_arg_text(rest, "--evidence"), opt("--note"))
    elif cmd == "task":
        rc, msg = cmd_task(root, rest)
    elif cmd == "tasks":
        rc, msg = cmd_tasks(root, rest)
    elif cmd == "secret" and rest and rest[0] == "check" and "--all" in rest:
        rc, msg = cmd_secret_all(root)
    elif cmd == "secret" and rest and rest[0] == "set":
        rc, msg = cmd_secret_set(root, rest[1] if len(rest) > 1 else None, project="--project" in rest)
    elif cmd == "secret" and rest and rest[0] == "guide":
        rc, msg = cmd_secret_guide(root, rest[1] if len(rest) > 1 else None, project="--project" in rest)
    elif cmd == "secret" and rest and rest[0] == "allow":
        rc, msg = cmd_secret_allow(root, rest[1] if len(rest) > 1 else None)
    elif cmd == "secret" and rest:
        rc, msg = cmd_secret(root, rest[0], project="--project" in rest)
    elif cmd == "with-secrets" and "--" in rest:
        i = rest.index("--")
        head = rest[:i]
        tv = head[head.index("--timeout") + 1] if "--timeout" in head and head.index("--timeout") + 1 < len(head) else ""
        rc, msg = cmd_with_secrets(root, rest[i + 1:], project="--project" in head, timeout=int(tv) if tv.isdigit() else 600)
    elif cmd == "update":
        rc, msg = cmd_update(root)
    elif cmd == "update-check":
        rc, msg = cmd_update_check(root, rest[0] if rest else "")
    else:
        print(T("usage"))
        return 2
    print(msg)
    return rc


if __name__ == "__main__":
    sys.exit(cli_main(sys.argv[1:]))
