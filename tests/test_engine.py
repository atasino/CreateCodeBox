#!/usr/bin/env python3
"""Unit tests of ws/engine.py (hooks and commands). Each test copies the workspace to a temporary folder,
feeds JSON to the hooks, and checks deny / allow. Standard library only. The check names are in Japanese.

Usage (from the repository root): python3 -I tests/test_engine.py
Exit code 0 when every check passes, 1 otherwise. The last line prints the counts.
The real home folder is never used: HOME points to an empty temporary folder for the whole run.
"""
import atexit
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
TEMPLATE = os.path.abspath(os.path.join(HERE, ".."))  # the repository root is the workspace that users get
PASS, FAIL = [], []

# Keep the real ~/.createcodebox (signing key, keys) out of reach: in-process engine calls see this empty HOME.
_TEST_HOME = tempfile.mkdtemp(prefix="ccb_home_")
os.environ["HOME"] = _TEST_HOME
atexit.register(shutil.rmtree, _TEST_HOME, True)

# Not part of the workspace a user gets: the repo's own git data, these tests, and local state or secrets.
_SKIP_TOP = {".git", "tests", ".ws", "projects", ".secrets", ".env"}


def _skip_names(src, names):
    rel = os.path.relpath(src, TEMPLATE)
    skip = {n for n in names if n in ("__pycache__", ".DS_Store") or n.endswith(".pyc")}
    if rel == ".":
        skip |= {n for n in names if n in _SKIP_TOP or (n.startswith(".env.") and n != ".env.example")}
    if rel == ".claude":
        skip |= {n for n in names if n == "settings.local.json"}
    return skip


def copy_template(dst):
    shutil.copytree(TEMPLATE, dst, ignore=_skip_names)


sys.path.insert(0, os.path.join(TEMPLATE, "ws"))
import engine as _engine_template  # noqa: E402  (loaded once, from the template, for the in-process checks)

IO_OK = {"rows": [
    {"id": "IO-01", "kind": "画面", "name": "支出の入力", "dir": "in", "party": "利用者", "example": "食費 1,200 円",
     "required": True, "failure": "金額が数字でないとき、赤字で知らせる", "prd": "FR-01", "screen": "SCR-01"},
    {"id": "IO-02", "kind": "ファイル", "name": "月ごとの合計", "dir": "out", "party": "利用者", "example": "2026-10 食費 12,400 円",
     "required": True, "failure": "書けないとき、場所を知らせる", "prd": "FR-02", "screen": ""}]}


SKETCH = ("<!doctype html><html><head><meta charset=utf-8><title>sketch</title></head>"
          "<body data-ccb=\"sketch\"><p>Rough guess from one sentence — expect it to be wrong.</p>" + "<div style=\"background:#ddd\">box</div>" * 12 + "</body></html>")


class Env:
    def __init__(self):
        self.tmp = tempfile.mkdtemp(prefix="ccb_")
        self.root = os.path.join(self.tmp, "ws")
        self.home = os.path.join(self.tmp, "home")
        os.makedirs(self.home)
        copy_template(self.root)
        self.env = dict(os.environ, CLAUDE_PROJECT_DIR=self.root, HOME=self.home, CREATECODEBOX_OPEN_DRY_RUN="1")
        self.env.pop("CREATECODEBOX_LANG", None)

    def run(self, args, stdin=None):
        p = subprocess.run([sys.executable, "-I", os.path.join(self.root, "ws", "engine.py")] + args,
                           input=stdin, capture_output=True, text=True, env=self.env, cwd=self.root)
        return p.returncode, p.stdout + p.stderr

    def hook(self, kind, event):
        p = subprocess.run([sys.executable, "-I", os.path.join(self.root, ".claude", "hooks", "ws_hook.py"), kind],
                           input=json.dumps(event), capture_output=True, text=True, env=self.env, cwd=self.root)
        return p.stdout.strip()

    def pre(self, tool, **ti):
        out = self.hook("pretool", {"tool_name": tool, "tool_input": ti, "cwd": self.root})
        if not out:
            return None
        return json.loads(out)["hookSpecificOutput"]["permissionDecisionReason"]

    def prompt(self, text):
        return self.hook("prompt", {"prompt": text})

    def ctx(self, kind, event):
        """The additionalContext text of a hook answer (parsed from JSON)."""
        out = self.hook(kind, event)
        try:
            return json.loads(out)["hookSpecificOutput"].get("additionalContext", "")
        except (ValueError, KeyError):
            return out

    def pctx(self, text):
        return self.ctx("prompt", {"prompt": text})

    def stage(self):
        m = re.search(r"(?:stage|ステージ) (\w+):", self.run(["status"])[1])
        return m.group(1) if m else "?"

    def p(self, *parts):
        return os.path.join(self.root, *parts)

    def write(self, rel, text):
        path = self.p(rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)

    def set_fields(self, slug, **kw):
        path = self.p("projects", slug, "PROJECT.md")
        lines = open(path, encoding="utf-8").read().splitlines()
        out = []
        for l in lines:
            k = l.split(":")[0]
            out.append("%s: %s" % (k, kw[k]) if k in kw else l)
        open(path, "w", encoding="utf-8").write("\n".join(out) + "\n")

    def engine_call(self, code):
        """Run a few lines of Python with the engine loaded (same HOME and key as the hooks)."""
        full = "import sys; sys.path.insert(0, %r); import engine, json; root = %r\n%s" % (os.path.join(self.root, "ws"), self.root, code)
        p = subprocess.run([sys.executable, "-I", "-c", full], capture_output=True, text=True, env=self.env, cwd=self.root)
        return p.stdout + p.stderr

    def hook_raw(self, kind, event, env=None, via_sh=False):
        """Like hook() but returns (exit code, stdout bytes, stderr bytes)."""
        if via_sh:
            cmd = ["/bin/sh", os.path.join(self.root, "ws", "bin", "hook.sh"), kind]
        else:
            cmd = [sys.executable, "-I", os.path.join(self.root, ".claude", "hooks", "ws_hook.py"), kind]
        p = subprocess.run(cmd, input=json.dumps(event).encode("utf-8"), capture_output=True, env=env or self.env, cwd=self.root)
        return p.returncode, p.stdout, p.stderr

    def rec(self, name):
        """Read a .ws/ record without checking the signature."""
        return json.load(open(self.p(".ws", name), encoding="utf-8"))

    def close(self):
        shutil.rmtree(self.tmp, ignore_errors=True)


CJK_ALL = re.compile("[\u3000-\u303f\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff\uff00-\uffef]")


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(("PASS " if cond else "FAIL ") + name + ("" if cond else "  <- " + str(detail)[:200]))


def new_project(e):
    e.prompt("家計簿を作りたい")
    rc, out = e.run(["new", "kakeibo", "--name", "家計簿", "--quote", "家計簿"])
    return rc, out


IO_EN = {"rows": [
    {"id": "IO-01", "kind": "file", "name": "input file", "dir": "in", "party": "user", "example": "a.csv", "required": True,
     "failure": "a broken file shows a message", "prd": "FR-01"},
    {"id": "IO-02", "kind": "file", "name": "report", "dir": "out", "party": "user", "example": "report.txt", "required": True,
     "failure": "cannot write: say which folder", "prd": "FR-02"}]}
IO_SCHED = {"id": "IO-03", "kind": "scheduled", "name": "monthly job", "dir": "out", "party": "clock", "example": "2026-11-01 06:00",
            "required": False, "failure": "if it did not run, run it at next start", "prd": "FR-03"}


def build_to_run(e, io=None, goal="self", first_prompt="make a small tool"):
    """A project at RUN, made the way a user would (English input)."""
    e.hook("sessionstart", {"source": "startup"})
    e.prompt(first_prompt)
    e.run(["new", "app", "--name", "App", "--quote", first_prompt])
    slug = "01_app"
    e.set_fields(slug, goal_type=goal, what="a small tool", who="me", today="by hand", done_when="it works", not_doing="nothing else", has_ui="no")
    e.write("projects/%s/design/ui/sketch.html" % slug, SKETCH)
    e.write("projects/%s/design/io.json" % slug, json.dumps(io or IO_EN))
    e.prompt("approve")
    e.run(["schedule-init"])
    return slug


def fake_secret(kind):
    """Test-only strings in the SHAPE of real keys (built from parts; none of them is a real key)."""
    import base64
    b64 = lambda d: base64.urlsafe_b64encode(json.dumps(d).encode()).decode().rstrip("=")
    hdr = b64({"alg": "HS256", "typ": "JWT"})
    return {
        "sk": "sk" + "-" + "abcdefghijklmnopqrstuvwx1234",
        "ghp": "gh" + "p_" + "A1b2C3d4E5f6G7h8I9j0K1l2M3n4O5p6Q7r8",
        "ghpat": "github" + "_pat_" + "A1b2C3d4E5f6G7h8I9j0K1l2M3n4O5p6Q7r8S9t0",
        "aws": "AK" + "IA" + "ABCDEFGH12345678",
        "slack": "xox" + "b-" + "1234567890-abcdefghij",
        "google": "AI" + "za" + "SyA1b2C3d4E5f6G7h8I9j0K1l2M3n4O5p67",
        "pem": "-----BEGIN " + "RSA PRIVATE KEY-----",
        "sbsecret": "sb_" + "secret_" + "a1B2c3D4e5F6g7H8i9J0k1L2",
        "sklive": "sk_" + "live_" + "0123456789abcdefghijklmn",
        "rklive": "rk_" + "live_" + "0123456789abcdefghijklmn",
        "whsec": "whsec" + "_" + "0123456789abcdefghijklmnopqrstuv",
        "urlpw": "postgres://admin:" + "Sup3r" + "S3cretPw" + "@db.example.com:5432/app",
        "glpat": "glpat" + "-" + "a1B2c3D4e5F6g7H8i9J0",
        "npm": "npm" + "_" + "a1B2c3D4e5F6g7H8i9J0k1L2m3N4o5P6q7R8",
        "sendgrid": "SG" + "." + "a1B2c3D4e5F6g7H8i9J0k1" + "." + "a1B2c3D4e5F6g7H8i9J0k1L2m3N4o5P6q7R8s9T0u1V",
        "hf": "hf" + "_" + "a1B2c3D4e5F6g7H8i9J0k1L2m3N4o5P6q7",
        "ya29": "ya29" + "." + "a1B2c3D4e5F6g7H8i9J0k1L2m3N4o5P6q7R8",
        "jwt_service": hdr + "." + b64({"role": "service_role", "iss": "supabase"}) + "." + "a1B2c3D4e5F6g7H8i9J0",
        "jwt_anon": hdr + "." + b64({"role": "anon", "iss": "supabase"}) + "." + "a1B2c3D4e5F6g7H8i9J0",
    }[kind]


def test_scan():
    sys.path.insert(0, os.path.join(TEMPLATE, "ws"))
    import engine as en
    fs = fake_secret
    GEN = "Zx9f" + "Q2mK" + "7pL4" + "vB8n" + "T1wY" + "3hR6"  # a made-up high-entropy value, built at run time
    fp_corpus = [
        ("a.js", "const k = process.env.STRIPE_SECRET_KEY;"),
        ("a.ts", "const token = process.env.NEXT_PUBLIC_API_TOKEN ?? ''"),
        ("a.py", "API_KEY = os.environ['MY_API_KEY_VALUE_LONG']"),
        ("a.py", "secret = os.getenv('APP_SECRET_KEY_NAME_LONG')"),
        ("main.go", 'apiKey := os.Getenv("API_KEY_LONG_NAME_HERE")'),
        ("a.ts", "const apiKey = import.meta.env.VITE_API_KEY_VALUE_LONG"),
        ("a.rb", "password = ENV.fetch('DATABASE_PASSWORD_LONG_NAME')"),
        ("a.ts", 'const url = "x"; const NEXT_PUBLIC_SUPABASE_ANON_KEY = "%s"' % fs("jwt_anon")),
        (".env.example", "SUPABASE_SERVICE_ROLE_KEY=your-service-role-key-here"),
        (".env.example", "STRIPE_SECRET_KEY=sk_test_" + "x" * 24),
        (".env.example", "API_TOKEN=changeme-changeme-changeme"),
        ("config.yml", "password: ${DB_PASSWORD}"),
        ("config.yaml", "api_key: !ENV API_KEY"),
        ("a.js", "headers: { Authorization: `Bearer ${token}` }"),
        ("a.py", 'token = request.headers.get("Authorization")'),
        ("a.html", '<input type="password" name="password" placeholder="Enter your password">'),
        ("a.js", "const secret = 'this_is_a_long_lowercase_phrase_value'"),
        ("a.md", "use the risk-assessment-framework-for-everything tool"),
        ("docker-compose.yml", "      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:-postgres}"),
        ("a.py", 'password = "********************"'),
        ("db.js", "const url = `postgres://user:${PASSWORD}@localhost:5432/db`"),
        ("a.js", "const apiKey = req.headers['x-api-key']"),
        ("a.toml", "token = env.get('TOKEN_NAME_LONG_ENOUGH_HERE')"),
    ]
    bad = [(p, t) for p, t in fp_corpus if en.has_key(t, p)]
    check("鍵: 誤検出 corpus %d 例が全て allow（process.env・os.environ・anon の JWT・.env.example など）" % len(fp_corpus), not bad, bad[:3])
    real = [("a.py", "OPENAI = '%s'" % fs("sk")), ("a.js", fs("ghp")), ("a.js", fs("ghpat")), ("a.js", fs("aws")), ("a.js", fs("slack")),
            ("a.js", fs("google")), ("k.txt", fs("pem")), ("a.ts", 'const s = "%s"' % fs("sbsecret")), ("a.ts", fs("sklive")), ("a.ts", fs("rklive")),
            ("a.ts", fs("whsec")), ("a.py", 'DB = "%s"' % fs("urlpw")), ("a.yml", "t: %s" % fs("glpat")), ("a.js", fs("npm")), ("a.js", fs("sendgrid")),
            ("a.py", fs("hf")), ("a.js", fs("ya29")), ("a.ts", 'KEY = "%s"' % fs("jwt_service")),
            ("a.py", 'api_key = "%s"' % GEN), ("settings.yml", "password: " + GEN)]
    miss = [(p, t[:30]) for p, t in real if not en.has_key(t, p)]
    check("鍵: 本物の形 %d 例が全て deny（service_role の JWT・パスワード入り URL を含む）" % len(real), not miss, miss)
    check("鍵: anon の JWT は allow・復号できない eyJ 形も allow", not en.has_key(fs("jwt_anon")) and not en.has_key("eyJhbGciOi.eyJzdWIiOi.abcdefghij"))
    check("鍵: sb_publishable_ は対象外", not en.has_key("sb_publishable_a1B2c3D4e5F6g7H8i9J0k1L2"))
    check("鍵: 通常のソースでは引用符なしの汎用形は当てない・設定ファイルでは当てる",
          not en.has_key("password = " + GEN, "a.py") and en.has_key("password: " + GEN, "a.yml"))
    check("鍵: 値に . を含む物は汎用形に当てない（ドメイン名など）", not en.has_key('token = "a1B2c3D4e5F6.g7H8i9J0k1L2"', "a.py"))
    check("E4: SECRET_CMD は .env を指す物だけ（process.env は当たらない・.env.example は当たらない）",
          en.SECRET_CMD.search("cat .env") and en.SECRET_CMD.search("cat src/.env.local") and en.SECRET_CMD.search("cat x=.env")
          and not en.SECRET_CMD.search("grep -rn process.env src") and not en.SECRET_CMD.search("cat .env.example"))
    d = "diff --git a/x.py b/x.py\n+++ b/x.py\n@@ -0,0 +1,2 @@\n+a = 1\n+K = '%s'\n" % fs("sklive")
    f = en.diff_findings(os.path.join(TEMPLATE), d)
    check("E3: 履歴の検出は commit:path:行 と指紋を出す（値は出さない）", len(f) == 1 and f[0]["path"] == "x.py" and f[0]["line"] == 2 and len(f[0]["fp"]) == 12
          and fs("sklive") not in en.fmt_findings(f), f)
    check("E5: MultiEdit の edits を走査する材料（new_string）が取り出される", fs("sklive") in en.edit_body("MultiEdit", {"edits": [{"old_string": "a", "new_string": "K='%s'" % fs("sklive")}]}))


def test_gate_keys_and_protect():
    e = Env()
    try:
        slug = build_to_run(e)
        e.prompt("continue")
        e.prompt("ok")
        fs = fake_secret
        r = e.pre("MultiEdit", file_path=e.p("projects", slug, "src", "a.py"), edits=[{"old_string": "a", "new_string": "K = '%s'" % fs("sklive")}])
        check("MultiEdit: edits[].new_string の鍵も止める", r is not None and "key or a password" in r, r)
        check("本物の鍵の形の書き込みは止まる（Stripe）", e.pre("Write", file_path=e.p("projects", slug, "src", "b.py"), content="K='%s'" % fs("sklive")) is not None)
        check("process.env を読むコードの書き込みは通る", e.pre("Write", file_path=e.p("projects", slug, "src", "c.js"), content="const k = process.env.API_KEY;") is None)
        check("Supabase の anon キーの書き込みは通る", e.pre("Write", file_path=e.p("projects", slug, "src", "d.ts"), content='const a = "%s"' % fs("jwt_anon")) is None)
        check("process.env の grep は通る", e.pre("Bash", command='grep -rn "process.env" src') is None)
        check("`.w's'/`（引用符で隠した .ws）は止まる", e.pre("Bash", command="rm -rf .w's'/") is not None)
        check("`.w[s]/`（[s] で隠した .ws）は止まる", e.pre("Bash", command="rm -rf .w[s]/") is not None)
        check("`.w\"s\"` と `.w\\s`（引用符・バックスラッシュ）も止まる", e.pre("Bash", command='rm -rf .w"s"/') is not None and e.pre("Bash", command="rm -rf .w\\s/") is not None)
        check("`$x` を挟んで隠した .ws も止まる", e.pre("Bash", command="rm -rf .w$Xs/") is not None and e.pre("Bash", command="rm -rf .w${X}s/") is not None)
        r = e.pre("Bash", command="bash ws/bin/ws.sh save \"a; b\"")
        check("C2: ws.sh の引数に記号があると、利用者向けの 1 行（Don't put ...）で止まる", r is not None and "Don't put" in r, r)
        check("MultiEdit で .env を指すと止まる", e.pre("MultiEdit", file_path=e.p("projects", slug, "src", ".env"), edits=[{"old_string": "a", "new_string": "b"}]) is not None)
    finally:
        e.close()


def test_records_signature():
    e = Env()
    try:
        slug = build_to_run(e)
        check("署名: 承認の記録に _sig が付く", "_sig" in e.rec("approval_%s.json" % slug))
        check("署名: state.json に schema 3", e.rec("state.json").get("schema") == 3)
        check("署名: 鍵は ~/.createcodebox/.ws_key（32 バイト・600）", os.path.getsize(os.path.join(e.home, ".createcodebox", ".ws_key")) == 32
              and oct(os.stat(os.path.join(e.home, ".createcodebox", ".ws_key")).st_mode & 0o777) == "0o600")
        check("署名: 記録を作った後の段は RUN", e.stage() == "RUN", e.stage())
        # tamper: remove the signature
        rec = e.rec("approval_%s.json" % slug)
        rec.pop("_sig")
        json.dump(rec, open(e.p(".ws", "approval_%s.json" % slug), "w"))
        out = e.run(["status"])[1]
        check("署名: 記録を直接書き換える（署名なし）と段が進まない（R4A）・signature mismatch の警告", e.stage() == "R4A" and "signature mismatch" in out, out)
        # tamper: change the content, keep the old signature
        e.prompt("approve")
        check("署名: 承認し直すと戻る", e.stage() == "RS" or e.stage() == "RUN", e.stage())
        sc = e.rec("schedule_%s.json" % slug)
        sc["rows"][0]["status"] = "done"
        json.dump(sc, open(e.p(".ws", "schedule_%s.json" % slug), "w"))
        out = e.run(["status"])[1]
        check("署名: schedule を直接書き換える（内容を変えて署名は古いまま）と、記録は無かった扱い（RS）", e.stage() == "RS" and "signature mismatch" in out, out)
        rc, out = e.run(["resign"])
        check("resign: 利用者の入力に resign が無いと断る", rc == 1, out)
        e.prompt("I changed it myself. Please resign")
        rc, out = e.run(["resign"])
        check("resign: 利用者の言葉があれば付け直す（書き換えた内容が有効になる）", rc == 0 and e.stage() == "RUN", out + e.stage())
        # a record copied to another project / name does not verify (signature is bound to slug and path)
        shutil.copy(e.p(".ws", "approval_%s.json" % slug), e.p(".ws", "approval_02_other.json"))
        out = e.engine_call("print(engine.load_rec(root, 'approval_02_other.json', '02_other'))")
        check("署名: 別の slug・別の名前にコピーした記録は通らない", out.strip().endswith("None"), out)
    finally:
        e.close()
    # no key: progress is kept (unsigned + warning)
    e = Env()
    try:
        open(os.path.join(e.home, ".createcodebox"), "w").write("a file, so the key folder can't be made")
        slug = build_to_run(e)
        out = e.run(["status"])[1]
        check("鍵が作れない時: 未署名で進捗が残る（RUN）・警告が出る", e.stage() == "RUN" and "without a signature" in out, out)
        check("鍵が作れない時: 記録は _unsigned の印つき", e.rec("approval_%s.json" % slug).get("_unsigned") is True)
    finally:
        e.close()


def test_st_extra():
    e = Env()
    try:
        slug = build_to_run(e, io={"rows": IO_EN["rows"] + [IO_SCHED]})
        who = {r["id"]: r["who"] for r in e.rec("st_%s.json" % slug)["rows"]}
        check("F3: scheduled の行は ai のケースになる", who["T-IO-03-N1"] == "ai" and who["T-IO-03-F1"] == "ai" and who["T-IO-01-N1"] == "user", who)
        rc, out = e.run(["st", "run", "T-IO-03-N1"])
        check("F2: st run は runner が無いと断る", rc == 2 and "no test runner" in out, out)
        rc, out = e.run(["st", "run", "T-IO-01-N1"])
        check("F2: st run は user のケースには使えない", rc == 2, out)
        check("F2: st run に --cmd は無い（知らない引数は無視され、runner が無いので断る）", e.run(["st", "run", "T-IO-03-N1", "--cmd", "echo hi"])[0] == 2)
        sys.path.insert(0, os.path.join(TEMPLATE, "ws"))
        import engine as en
        td = tempfile.mkdtemp(prefix="ccb_rn_")
        try:
            check("F2: runner の検出（なし）", en.detect_runner(td) is None)
            open(os.path.join(td, "package.json"), "w").write(json.dumps({"scripts": {"test": "echo ok"}}))
            check("F2: package.json の scripts.test → npm test", en.detect_runner(td) == ["npm", "test"])
            open(os.path.join(td, "package.json"), "w").write(json.dumps({"scripts": {"test": "echo \"Error: no test specified\" && exit 1"}}))
            check("F2: 既定の「no test specified」は runner とみなさない", en.detect_runner(td) is None)
            open(os.path.join(td, "go.mod"), "w").write("module x\n")
            check("F2: go.mod → go test ./...", en.detect_runner(td) == ["go", "test", "./..."])
            os.remove(os.path.join(td, "go.mod"))
            open(os.path.join(td, "Cargo.toml"), "w").write("[package]\n")
            check("F2: Cargo.toml → cargo test", en.detect_runner(td) == ["cargo", "test"])
            os.remove(os.path.join(td, "Cargo.toml"))
            open(os.path.join(td, "pytest.ini"), "w").write("[pytest]\n")
            check("F2: pytest.ini → pytest", en.detect_runner(td)[-1] == "pytest")
        finally:
            shutil.rmtree(td, ignore_errors=True)
        # a fake npm on PATH: st run records exit code + tail
        fakebin = os.path.join(e.tmp, "fakebin")
        os.makedirs(fakebin)
        open(os.path.join(fakebin, "npm"), "w").write("#!/bin/sh\necho line1\necho \"ran $@\"\nexit ${FAKE_NPM_EXIT:-0}\n")
        os.chmod(os.path.join(fakebin, "npm"), 0o755)
        e.write("projects/%s/src/package.json" % slug, json.dumps({"scripts": {"test": "x"}}))
        e.env["PATH"] = fakebin + os.pathsep + e.env.get("PATH", "")
        rc, out = e.run(["st", "run", "T-IO-03-N1", "T-IO-03-F1"])
        rows = {r["id"]: r for r in e.rec("st_%s.json" % slug)["rows"]}
        check("F2: st run は終了コードと末尾を署名つきの記録に残す（by: run）", rc == 0 and rows["T-IO-03-N1"]["status"] == "pass" and rows["T-IO-03-N1"]["by"] == "run"
              and "exit code 0" in rows["T-IO-03-N1"]["evidence"] and "ran test" in rows["T-IO-03-N1"]["evidence"] and "_sig" in e.rec("st_%s.json" % slug), out)
        e.env["FAKE_NPM_EXIT"] = "1"
        rc, out = e.run(["st", "run", "T-IO-03-N1"])
        check("F2: 終了コードが 0 でなければ fail", rc == 1 and e.rec("st_%s.json" % slug)["rows"][4]["status"] == "fail", out)
        e.env.pop("FAKE_NPM_EXIT")
        # evidence-file and stdin
        e.write("projects/%s/knowledge/ev.txt" % slug, "the screen showed 820 yen with a $ sign; > < ; & |")
        e.prompt("T-IO-01-N1 passed")
        rc, out = e.run(["st", "mark", "T-IO-01-N1", "pass", "--by", "user", "--evidence-file", e.p("projects", slug, "knowledge", "ev.txt")])
        check("--evidence-file: 記号の入った証拠を受ける", rc == 0 and "$ sign" in e.rec("st_%s.json" % slug)["rows"][0]["evidence"], out)
        e.prompt("T-IO-01-F1 passed")
        rc, out = e.run(["st", "mark", "T-IO-01-F1", "pass", "--by", "user", "--evidence", "-"], stdin="read from stdin: a | b")
        check("--evidence - : 標準入力で証拠を受ける", rc == 0 and "read from stdin" in e.rec("st_%s.json" % slug)["rows"][1]["evidence"], out)
        # bulk
        e.run(["st", "list"])
        e.prompt("all pass")
        rc, out = e.run(["st", "mark", "T-IO-02-N1", "pass", "--by", "user"])
        r2 = e.rec("st_%s.json" % slug)["rows"][2]
        check("bulk: all + pass の語は、直近 3 入力以内に st list が出ていれば受け、記録に bulk", rc == 0 and r2.get("bulk") is True, out)
        e.prompt("a")
        e.prompt("b")
        e.prompt("c")
        e.prompt("all pass")
        rc, out = e.run(["st", "mark", "T-IO-02-F1", "pass", "--by", "user"])
        check("bulk: st list から 4 入力以上あとは受けない", rc == 1, out)
        # ai first version
        e.run(["st", "list", "--numbered"])
        shot = e.p("projects", slug, "knowledge", "s.png")
        open(shot, "wb").write(b"\x89PNG\r\n" + b"0" * 400)
        e.run(["st", "mark", "T-IO-03-N1", "pass", "--by", "ai", "--evidence", "the monthly job ran and wrote a file", "--shot", shot])
        e.prompt("4 pass")
        e.run(["st", "mark", "T-IO-02-F1", "pass", "--by", "user"])
        sm = json.loads(e.engine_call("print(json.dumps(engine.st_summary(root, %r)))" % slug).strip().splitlines()[-1])
        check("st_summary: user / ai / normal の集計", sm["user_pass"] == sm["user_total"] == 4 and sm["ai_pass"] == 2 and sm["ai_total"] == 2
              and sm["normal_pass"] == sm["normal_total"] == 3, sm)
    finally:
        e.close()


def test_done_and_append():
    e = Env()
    try:
        slug = build_to_run(e, io={"rows": IO_EN["rows"] + [IO_SCHED]}, goal="public-free")
        shot = e.p("projects", slug, "knowledge", "s.png")
        open(shot, "wb").write(b"\x89PNG\r\n" + b"0" * 400)
        for sid in ("S-01", "S-02", "S-03", "S-04"):
            rc, out = e.run(["mark", sid, "done", "--evidence", "ran it and it worked fine"])
        check("D5: 行（io）が全て done でも、システムテストの最後の行は条件を満たすまで済にできない", e.stage() == "RUN", e.stage())
        for sid in ("S-02", "S-03", "S-04"):
            e.run(["mark", sid, "done", "--evidence", "ran it and it worked fine"])
        e.run(["st", "list", "--numbered"])
        e.prompt("all pass")
        for cid in ("T-IO-01-N1", "T-IO-01-F1", "T-IO-02-N1", "T-IO-02-F1"):
            e.run(["st", "mark", cid, "pass", "--by", "user"])
        e.run(["st", "mark", "T-IO-03-N1", "pass", "--by", "ai", "--evidence", "the monthly job ran and wrote a file", "--shot", shot])
        for sid in ("S-02", "S-03", "S-04", "S-05"):
            e.run(["mark", sid, "done", "--evidence", "ran it and it worked fine"])
        out = e.run(["status"])[1]
        check("F3/D4: user の全ケースと正常系が合格すると DONE（ai の失敗系が未了でも第 1 版）", e.stage() == "DONE", out)
        check("F3: DONE の文（You checked 4/4・Claude will check 1/2・Not yet checked: 1）", "First version done! You checked: 4/4. Claude will check: 1/2 (things you can't trigger by hand). Not yet checked: 1." in out, out)
        check("F3: 利用者向けの文に ai / user の語を出さない", " ai " not in out.split("DONE")[-1].lower() and "(user)" not in out)
        check("A6: DONE の文に開き方（double-click projects/…/src/index.html）", "double-click projects/%s/src/index.html" % slug in out, out)
        e.prompt("continue")
        e.prompt("ok")
        check("D4: DONE でも src/ に書ける・Bash も RUN と同じ", e.pre("Write", file_path=e.p("projects", slug, "src", "x.py"), content="print(1)") is None
              and e.pre("Bash", command="python3 x.py") is None)
        check("D4: DONE でも .ws に触るコマンドは止まる", e.pre("Bash", command="rm -rf .ws") is not None)
        done_ids = [r["id"] for r in e.rec("schedule_%s.json" % slug)["rows"] if r["status"] == "done"]
        # add an io row: approval is reset, and DONE does not come back by itself
        io2 = {"rows": IO_EN["rows"] + [IO_SCHED, dict(IO_EN["rows"][1], id="IO-04", name="print")]}
        e.write("projects/%s/design/io.json" % slug, json.dumps(io2))
        check("D5: io に行を足すと承認が無効になり R4A に戻る", e.stage() == "R4A", e.stage())
        e.prompt("approve")
        out = e.run(["status"])[1]
        check("D5: 行を足した後は DONE に戻らず、RS（スケジュールの追記待ち）で足りない行 IO-04 を出す", e.stage() == "RS" and "IO-04" in out, out)
        rc, out = e.run(["schedule-init"])
        sc = e.rec("schedule_%s.json" % slug)
        still = [r["id"] for r in sc["rows"] if r["status"] == "done" and r["id"] in done_ids]
        check("D5: schedule-init は追記（既存の done が保たれる・新しい行が 1 つ・最後の行は未済に戻る）", rc == 0 and set(done_ids) - {sc["rows"][-1]["id"]} <= set(still)
              and any(r.get("io") == "IO-04" for r in sc["rows"]) and sc["rows"][-1].get("gate") == "systemtest" and sc["rows"][-1]["status"] == "todo", out)
        stj = e.rec("st_%s.json" % slug)
        old = next(r for r in stj["rows"] if r["id"] == "T-IO-01-N1")
        check("D5: st init も追記（既存の合格が保たれる）", old["status"] == "pass" and any(r["id"] == "T-IO-04-N1" for r in stj["rows"]), old)
        check("D5: 追記後は RUN", e.stage() == "RUN", e.stage())
        # publish-check warns once when the ai side is unfinished and the goal is public
        e.write("projects/%s/src/README.md" % slug, "# app\n")
        e.write("projects/%s/src/LICENSE" % slug, "MIT\n")
        e.run(["save", "first"])
        e.run(["save", "first"])
        e.run(["publish-check"])
        rc, out1 = e.run(["publish-check"])
        rc, out2 = e.run(["publish-check"])
        check("F3: 目的が公開の物は、Claude 側が未了の間 publish-check が 1 回だけ注意する", "has not finished its own checks" in out1 and "has not finished its own checks" not in out2, (out1[-300:], out2[-200:]))
    finally:
        e.close()


def test_hooks_g1():
    e = Env()
    try:
        build_to_run(e)
        sh = os.path.join(e.root, "ws", "bin", "hook.sh")
        empty = os.path.join(e.tmp, "emptybin")
        os.makedirs(empty)
        p = subprocess.run(["/bin/sh", sh, "pretool"], input=b"{}", capture_output=True, env={"PATH": empty, "HOME": e.home}, cwd=e.root)
        err = p.stderr.decode("utf-8", "replace")
        check("G1: PATH に python が無いと hook.sh は exit 2 と日英の理由", p.returncode == 2 and "needs Python 3.8 or newer" in err and "Python 3.8 以上が必要です" in err, (p.returncode, err))
        fake7 = os.path.join(e.tmp, "py7")
        os.makedirs(fake7)
        open(os.path.join(fake7, "python3"), "w").write("#!/bin/sh\nexit 1\n")
        os.chmod(os.path.join(fake7, "python3"), 0o755)
        p = subprocess.run(["/bin/sh", sh, "pretool"], input=b"{}", capture_output=True, env={"PATH": fake7, "HOME": e.home}, cwd=e.root)
        check("G1: python が 3.8 未満（版の確認が失敗）でも exit 2", p.returncode == 2, p.returncode)
        rc, out, err = e.hook_raw("sessionstart", {"source": "startup"}, via_sh=True)
        check("G1: hook.sh 経由で hook が動く（SessionStart）", rc == 0 and b"CreateCodeBox" in out, (rc, out[:100], err[:100]))
        rc, out, err = e.hook_raw("pretool", {"tool_name": "Write", "tool_input": {"file_path": e.p("README.md"), "content": "x"}, "cwd": e.root}, via_sh=True)
        check("G1: hook.sh 経由で pretool が deny を返す", rc == 0 and b"deny" in out, (rc, out[:100]))
        env = dict(e.env, PYTHONIOENCODING="cp1252", CREATECODEBOX_LANG="ja")
        rc, out, err = e.hook_raw("pretool", {"tool_name": "Write", "tool_input": {"file_path": e.p("README.md"), "content": "x"}, "cwd": e.root}, env=env)
        try:
            j = json.loads(out.decode("utf-8"))
            ok = j["hookSpecificOutput"]["permissionDecision"] == "deny"
        except Exception:
            ok = False
        check("G1: PYTHONIOENCODING=cp1252 でも deny の JSON が UTF-8 で出る（日本語の理由つき）", rc == 0 and ok and "仕組み" in out.decode("utf-8", "replace"), (rc, out[:120]))
        ws = os.path.join(e.root, "ws")
        base = "import sys; sys.path.insert(0, %r); import engine\n" % ws

        def run_py(code, kind_event):
            p = subprocess.run([sys.executable, "-I", "-c", base + code], input=json.dumps(kind_event).encode(), capture_output=True, env=e.env, cwd=e.root)
            return p.returncode, p.stdout.decode("utf-8", "replace")
        rc, out = run_py("def boom(*a, **k): raise RuntimeError('x')\nengine.on_stop = boom\nsys.exit(engine.hook_main('stop'))", {})
        check("G1: Stop は例外でも exit 0", rc == 0, (rc, out))
        rc, out = run_py("def boom(*a, **k): raise RuntimeError('x')\nengine.on_prompt = boom\nsys.exit(engine.hook_main('prompt'))", {"prompt": "hi"})
        check("G1: prompt は例外でも exit 0 ＋ 警告の additionalContext", rc == 0 and "additionalContext" in out and "hook had an error" in out, (rc, out))
        rc, out = run_py("def boom(*a, **k): raise KeyboardInterrupt()\nengine._hook_dispatch = boom\nsys.exit(engine.hook_main('pretool'))", {})
        check("G1: pretool の最外周の例外（BaseException）は deny の JSON（exit 0）", rc == 0 and "deny" in out, (rc, out))
        rc, out = run_py("def boom(*a, **k): raise KeyboardInterrupt()\nengine._hook_dispatch = boom\nengine._emit = boom\nsys.exit(engine.hook_main('pretool'))", {})
        check("G1: deny も出せないときは exit 2", rc == 2, (rc, out))
        rc, out = run_py("def boom(*a, **k): raise RuntimeError('x')\nengine.gate = boom\nsys.exit(engine.hook_main('pretool'))", {"tool_name": "Bash", "tool_input": {"command": "ls"}})
        check("G1: gate の例外は deny（fail-closed）", rc == 0 and "deny" in out, (rc, out))
        broken = os.path.join(e.tmp, "brokenws")
        copy_template(broken)
        open(os.path.join(broken, "ws", "engine.py"), "w").write("this is not python (\n")
        envb = dict(e.env, CLAUDE_PROJECT_DIR=broken)
        p = subprocess.run([sys.executable, "-I", os.path.join(broken, ".claude", "hooks", "ws_hook.py"), "pretool"], input=b"{}", capture_output=True, env=envb)
        p2 = subprocess.run([sys.executable, "-I", os.path.join(broken, ".claude", "hooks", "ws_hook.py"), "stop"], input=b"{}", capture_output=True, env=envb)
        check("G1: engine が読み込めないとき、pretool は deny・stop は exit 0", p.returncode == 0 and b"deny" in p.stdout and p2.returncode == 0, (p.returncode, p.stdout[:80]))
        cfg = json.load(open(os.path.join(e.root, ".claude", "settings.json"), encoding="utf-8"))
        cmds = {k: v[0]["hooks"][0]["command"] for k, v in cfg["hooks"].items()}
        check("G1: settings.json の command の形（pretool と prompt は || exit 2・SessionStart と Stop は || exit 0）",
              cmds["PreToolUse"] == 'sh "$CLAUDE_PROJECT_DIR/ws/bin/hook.sh" pretool || exit 2'
              and cmds["UserPromptSubmit"] == 'sh "$CLAUDE_PROJECT_DIR/ws/bin/hook.sh" prompt || exit 2'
              and cmds["SessionStart"] == 'sh "$CLAUDE_PROJECT_DIR/ws/bin/hook.sh" sessionstart || exit 0'
              and cmds["Stop"] == 'sh "$CLAUDE_PROJECT_DIR/ws/bin/hook.sh" stop || exit 0', cmds)
        allow = cfg["permissions"]["allow"]
        banned = ("with-secrets", "st run", "update", "harden", "intake", "repo init", "repo link", "repo adopt", "backup", "publish", "secret", "rules", "excludes", "resign")
        check("A2: permissions.allow に with-secrets・st run・update・harden などが無い", not [a for a in allow if any(("ws.sh " + b) in a for b in banned)], allow)
        check("A2: permissions.allow に素の Read が無い", not [a for a in allow if a == "Read" or a.startswith("Read(")], allow)
        need = ["status", "list", "select", "new", "lint", "render", "open", "learn", "mark", "st list", "st mark", "st init", "schedule-init", "doctor", "version", "lang", "repo email"]
        check("A2: サブコマンド単位の許可がそろう（+ Edit/Write(projects/**)）", all(("Bash(bash ws/bin/ws.sh %s:*)" % n in allow and "Bash(bash ws/bin/ws.sh %s)" % n in allow) for n in need)
              and "Edit(projects/**)" in allow and "Write(projects/**)" in allow, allow)
        check(".gitignore に .ws/ と .env 系が入っている", ".ws/" in open(os.path.join(e.root, ".gitignore")).read().split() and ".env.*" in open(os.path.join(e.root, ".gitignore")).read())
        check("ws/VERSION は 0.4.4", open(os.path.join(e.root, "ws", "VERSION")).read().strip() == "0.4.4")
        check("ws.sh: python が無いと日英の案内で exit 1", subprocess.run(["/bin/sh", os.path.join(e.root, "ws", "bin", "ws.sh"), "version"], capture_output=True, env={"PATH": empty, "HOME": e.home}).returncode == 1)
    finally:
        e.close()


def test_lang():
    sys.path.insert(0, os.path.join(TEMPLATE, "ws"))
    import lang as lg
    from lang import en as lang_en, ja as lang_ja
    EN, JA = lang_en.MESSAGES, lang_ja.MESSAGES
    ph = lambda s: set(re.findall(r"\{([A-Za-z_]\w*)\}", s))
    check("翻訳①: en と ja の鍵の集合が一致する", set(JA) == set(EN), (sorted(set(JA) ^ set(EN)))[:5])
    check("翻訳②: 空の文が無い（en・ja）", all(isinstance(v, str) and v.strip() for v in list(EN.values()) + list(JA.values())))
    check("翻訳③: 置換名が全ての鍵で en と ja で一致する", all(ph(JA[k]) == ph(EN[k]) for k in EN if k in JA), [k for k in EN if k in JA and ph(JA[k]) != ph(EN[k])][:5])
    check("翻訳③: %s が残っていない（置換は名前つきの {name} だけ）", not [k for k, v in list(EN.items()) + list(JA.items()) if re.search(r"%[sd]", v)])
    check("翻訳④: en の表に他言語の文字が混ざらない", not [k for k, v in EN.items() if CJK_ALL.search(v)], [k for k, v in EN.items() if CJK_ALL.search(v)][:5])
    check("翻訳: 文 ID の命名（rule. todo. deny. st. warn. note. select. stage. などの接頭辞）", all(re.match(r"^[a-z0-9_]+(\.[A-Za-z0-9_]+)*$", k) for k in EN))
    lg.use("ja")
    saved = JA.pop("note.not_recorded")
    try:
        check("T: 鍵が ja に無ければ en に落ちる・どちらにも無ければ鍵をそのまま返す（KeyError で落とさない）",
              lg.T("note.not_recorded", word="x").startswith("I did not record") and lg.T("no.such.key") == "no.such.key")
    finally:
        JA["note.not_recorded"] = saved
    lg.use("en")
    check("T: 名前つきの置換・足りない名前は {name} のまま", lg.T("note.continuing", name="A") == 'Continuing A. Say "new" to start something else.' and "{word}" in lg.T("note.not_recorded"))
    lg.use(None)
    check("言語の判定: かな・漢字 → ja・他は en", lg.detect("家計簿を作りたい") == "ja" and lg.detect("I want a tool") == "en" and lg.detect("カタカナ") == "ja" and lg.detect("123", "x") == "x")
    # first message decides
    e = Env()
    try:
        e.hook("sessionstart", {"source": "startup"})
        e.prompt("12345")
        check("最初の発言が数字だけなら言語は決めない", not os.path.exists(e.p(".ws", "lang")))
        c = e.pctx("家計簿を作りたい")
        check("最初の発言の文字で ja が選ばれる（.ws/lang に保存）", open(e.p(".ws", "lang")).read().strip() == "ja" and c.startswith("Reply in: ja"), c[:60])
        c = e.pctx("Please make it simple")
        check("context に Reply in: が毎ターン・最新の発言の言語（.ws/lang は ja のまま）", c.startswith("Reply in: en") and open(e.p(".ws", "lang")).read().strip() == "ja", c[:60])
        c = e.ctx("sessionstart", {"source": "resume"})
        check("SessionStart の context の先頭にも Reply in:", c.startswith("Reply in: "), c[:40])
        rc, out = e.run(["lang"])
        check("lang: 表示", rc == 0 and "ja" in out, out)
        check("lang set: 変えられる・不正な code は断る", e.run(["lang", "set", "en"])[0] == 0 and open(e.p(".ws", "lang")).read().strip() == "en" and e.run(["lang", "set", "x y"])[0] == 2)
    finally:
        e.close()
    e = Env()
    try:
        e.hook("sessionstart", {"source": "startup"})
        e.pctx("make a todo app")
        check("最初の発言が英語なら en", open(e.p(".ws", "lang")).read().strip() == "en")
    finally:
        e.close()


def walk_stages(code):
    """Run one project from R0 to DONE with CREATECODEBOX_LANG=code. Returns [(name, text)] of everything the engine wrote on the way."""
    e = Env()
    out = []
    try:
        e.env["CREATECODEBOX_LANG"] = code
        add = lambda name, text: out.append((name, text))
        add("R0 sessionstart", e.ctx("sessionstart", {"source": "startup"}))
        add("R0 deny README", e.pre("Write", file_path=e.p("README.md"), content="a") or "")
        add("R0 deny mkdir", e.pre("Bash", command="mkdir src") or "")
        add("R0 prompt (no project)", e.pctx("make a booking page"))
        add("new", e.run(["new", "book", "--name", "Book", "--quote", "make a booking page"])[1])
        slug = "01_book"
        add("R1 status", e.run(["status"])[1])
        add("R1 prompt", e.pctx("hello"))
        add("R1 deny src", e.pre("Write", file_path=e.p("projects", slug, "src", "a.py"), content="x") or "")
        add("learn index", e.run(["learn"])[1])
        e.set_fields(slug, goal_type="share", what="booking page", who="clients", today="phone", done_when="clients can book", not_doing="payments", has_ui="yes", viz="local")
        add("R2 status", e.run(["status"])[1])
        add("R2 prompt", e.pctx("next"))
        e.write("projects/%s/design/ui/sketch.html" % slug, SKETCH)
        add("R2 status (brief missing)", e.run(["status"])[1])
        e.write("projects/%s/design/ui/brief.md" % slug, "## Purpose\nBook\n## Layout\nTop date\n## Colors\nblue\n## Text\nlarge\n## States\nempty hint\n")
        e.write("projects/%s/design/ui/index.html" % slug, "<html><body>x</body></html>")
        add("R3 prompt", e.pctx("show me"))
        add("R3 deny src", e.pre("Write", file_path=e.p("projects", slug, "src", "a.py"), content="x") or "")
        add("R3 note not recorded", e.pctx("yes"))
        add("R3 recorded", e.pctx("looks good"))
        add("R4 lint (no io.json)", e.run(["lint"])[1])
        e.write("projects/%s/design/io.json" % slug, json.dumps({"rows": [dict(IO_EN["rows"][0], example="TBD", kind="screen", screen="SC-1"), IO_EN["rows"][1]]}))
        add("R4 lint (errors)", e.run(["lint"])[1])
        e.write("projects/%s/design/io.json" % slug, json.dumps({"rows": [dict(IO_EN["rows"][0], kind="screen", screen="SC-1"), IO_EN["rows"][1]]}))
        add("R4 lint (ok)", e.run(["lint"])[1])
        add("R4A prompt", e.pctx("hmm"))
        add("R4A note not recorded", e.pctx("yes"))
        add("R4A recorded", e.pctx("approve"))
        add("RS status", e.run(["status"])[1])
        add("RS schedule-init", e.run(["schedule-init"])[1])
        add("RUN prompt", e.pctx("go on"))
        add("RUN deny raw git", e.pre("Bash", command="git push origin main") or "")
        add("RUN deny gh", e.pre("Bash", command="gh repo create x") or "")
        add("RUN deny secret", e.pre("Bash", command="cat .env") or "")
        add("RUN deny .ws", e.pre("Bash", command="rm -rf .ws") or "")
        add("RUN deny sandbox", e.pre("Bash", command="ls", dangerouslyDisableSandbox=True) or "")
        add("RUN deny key in write", e.pre("Write", file_path=e.p("projects", slug, "src", "k.py"), content="K='%s'" % fake_secret("sklive")) or "")
        add("RUN deny ws.sh meta", e.pre("Bash", command="bash ws/bin/ws.sh save \"a; b\"") or "")
        add("RUN deny write records", e.pre("Write", file_path=e.p("projects", slug, "design", "schedule.json"), content="{}") or "")
        add("RUN mark (no evidence)", e.run(["mark", "S-01", "done"])[1])
        add("RUN st list", e.run(["st", "list"])[1])
        add("RUN st list --numbered", e.run(["st", "list", "--numbered"])[1])
        add("RUN st mark (no words)", e.run(["st", "mark", "T-IO-01-N1", "pass", "--by", "user"])[1])
        rc, o = e.run(["render"])
        add("RUN render", o)
        for name in ("io", "schedule", "systemtest"):
            add("html " + name, open(e.p("projects", slug, "design", name + ".html"), encoding="utf-8").read())
        add("RUN status", e.run(["status"])[1])
        add("RUN publish-check", e.run(["publish-check"])[1])
        add("RUN save (card)", e.run(["save", "first"])[1])
        add("RUN secret check", e.run(["secret", "check"])[1])
        add("RUN secret guide", e.run(["secret", "guide", "MY_KEY"])[1])
        add("RUN doctor", e.run(["doctor"])[1])
        add("RUN harden status", e.run(["harden", "status"])[1])
        add("RUN open", e.run(["open", "projects/%s/design/ui/sketch.html" % slug])[1])
        add("RUN usage", e.run(["bogus"])[1])
        add("RUN repo link (bad)", e.run(["repo", "link", "ftp://x/y"])[1])
        add("RUN intake (bad)", e.run(["intake", e.p("nothing.txt")])[1])
        # finish: DONE
        e.run(["st", "list", "--numbered"])
        e.pctx("all pass")
        for cid in [r["id"] for r in e.rec("st_%s.json" % slug)["rows"]]:
            e.run(["st", "mark", cid, "pass", "--by", "user"])
        for sid in ("S-01", "S-02", "S-03", "S-04"):
            e.run(["mark", sid, "done", "--evidence", "ran it and it worked fine"])
        add("DONE status", e.run(["status"])[1])
        add("DONE prompt", e.pctx("thanks"))
        add("DONE render", e.run(["render"])[1])
        add("DONE html systemtest", open(e.p("projects", slug, "design", "systemtest.html"), encoding="utf-8").read())
        out.append(("(stage at the end)", e.stage()))
    finally:
        e.close()
    return out


def test_translation():
    sys.path.insert(0, os.path.join(TEMPLATE, "ws"))
    import lang as lg
    from lang import en as lang_en, ja as lang_ja
    EN, JA = lang_en.MESSAGES, lang_ja.MESSAGES
    en_out = walk_stages("en")
    ja_out = walk_stages("ja")
    en_txt, ja_txt = dict(en_out), dict(ja_out)
    check("翻訳: en と ja で同じ道筋を通せた（R0 から DONE まで）", [n for n, _ in ja_out] == [n for n, _ in en_out] and en_txt["(stage at the end)"] == "DONE" and ja_txt["(stage at the end)"] == "DONE",
          (en_txt["(stage at the end)"], ja_txt["(stage at the end)"]))
    bad = [(n, CJK_ALL.search(t).group(0)) for n, t in en_out if CJK_ALL.search(t)]
    check("翻訳④: CREATECODEBOX_LANG=en で、R0〜DONE の各段・deny・st list・render・HTML の出力に CJK が混ざらない（%d 件の出力）" % len(en_out), not bad, bad[:5])
    stage_lines = [t for n, t in en_out + ja_out if (n.endswith("status") or n.endswith("sessionstart")) and "harden" not in n]
    check("翻訳: 段の行は [CreateCodeBox で始まる行を含む（en・ja）", all(re.search(r"(^|\n)\[CreateCodeBox ", t) for t in stage_lines), [t[:40] for t in stage_lines][:3])
    check("翻訳: en の段の行は [CreateCodeBox stage <段>: <名前>] project: … missing: … の形",
          re.search(r"\[CreateCodeBox stage R1: goal\] project: Book \(01_book\) missing: ", en_txt["R1 status"]) is not None, en_txt["R1 status"][:120])
    keep_ascii = {"(stage at the end)", "RUN usage"}
    ja_fallback = [n for n, t in ja_out if n not in keep_ascii and not n.startswith("html ") and not CJK_ALL.search(t)]
    check("翻訳⑤: CREATECODEBOX_LANG=ja で、同じ出力に ja の表の文が出る（en に落ちていない）", not ja_fallback, ja_fallback[:8])
    same = [n for (n, a), (_, b) in zip(en_out, ja_out) if a == b and n not in keep_ascii]
    check("翻訳⑤: en と ja の出力が同じ物が無い", not same, same[:8])
    check("翻訳⑤: ja の規則・deny・段の行が ja の表の文そのもの",
          JA["rule.R1"] in ja_txt["R1 prompt"] and JA["rule.R0.empty"] in ja_txt["R0 prompt (no project)"] and JA["deny.raw_git"] in ja_txt["RUN deny raw git"]
          and JA["deny.secret"] in ja_txt["RUN deny secret"] and JA["rule.RUN"] in ja_txt["RUN prompt"] and JA["rule.R4A"] in ja_txt["R4A prompt"]
          and JA["rule.R3"] in ja_txt["R3 prompt"] and JA["rule.R2"] in ja_txt["R2 prompt"] and JA["rule.DONE"] in ja_txt["DONE prompt"]
          and JA["stage.label.R1"] in ja_txt["R1 status"] and JA["usage"] in ja_txt["RUN usage"], "")
    check("翻訳: en の規則・deny の文が en の表の文そのもの",
          EN["rule.R1"] in en_txt["R1 prompt"] and EN["rule.R0.empty"] in en_txt["R0 prompt (no project)"] and EN["deny.raw_git"] in en_txt["RUN deny raw git"]
          and EN["rule.RUN"] in en_txt["RUN prompt"] and EN["rule.R4A"] in en_txt["R4A prompt"] and EN["rule.DONE"] in en_txt["DONE prompt"] and EN["usage"] in en_txt["RUN usage"], "")
    check("翻訳: R4・RS の規則が表の文で出る（R4 は R3 の承認の直後・RS は承認の直後）",
          EN["rule.R4"] in en_txt["R3 recorded"] and JA["rule.R4"] in ja_txt["R3 recorded"] and EN["rule.RS"] in en_txt["R4A recorded"] and JA["rule.RS"] in ja_txt["R4A recorded"], en_txt["R3 recorded"][-200:])
    check("翻訳: 承認の note（C1）と記録の note が en・ja の表から出る",
          "send only the word: looks good" in en_txt["R3 note not recorded"] and "次の 1 語だけを送ってください: この形で" in ja_txt["R3 note not recorded"]
          and "send only the word: approve" in en_txt["R4A note not recorded"] and "次の 1 語だけを送ってください: 承認します" in ja_txt["R4A note not recorded"]
          and EN["note.recorded.r4a"] in en_txt["R4A recorded"] and JA["note.recorded.r4a"] in ja_txt["R4A recorded"], "")
    for fname, key, page in (("io", "html io", "io"), ("schedule", "html schedule", "sched"), ("systemtest", "html systemtest", "st")):
        h_en, h_ja = en_txt[key], ja_txt[key]
        labs_ja = json.dumps(lg.labels("html.common.", "html.%s." % page), ensure_ascii=False).replace("<", "\\u003c")
        use_ja = lambda: (lg.use("ja"), json.dumps(lg.labels("html.common.", "html.%s." % page), ensure_ascii=False).replace("<", "\\u003c"))[1]
        labs_ja = use_ja()
        lg.use(None)
        check("翻訳: %s.html の lang 属性・labels（言語の表から）・CJK フォントは ja のときだけ・置換の目印が残らない" % fname,
              '<html lang="en">' in h_en and '<html lang="ja">' in h_ja and "Hiragino" not in h_en and "Hiragino" in h_ja
              and "/*__WS_" not in h_en + h_ja and labs_ja in h_ja and "Turn on JavaScript" in h_en and "JavaScript をオンにしてください" in h_ja, h_ja[:60])
    for fname, page in (("io", "io"), ("schedule", "sched"), ("systemtest", "st"), ("tasks", "tasks")):
        t = open(os.path.join(TEMPLATE, "ws", "render", fname + ".template.html"), encoding="utf-8").read()
        m = re.search(r'id="ws-labels-default">(.*?)</script>', t, re.S)
        default = json.loads(m.group(1).replace("\\u003c", "<")) if m else {}
        want = {(k[len("html.common."):] if k.startswith("html.common.") else k[len("html.%s." % page):]): v
                for k, v in EN.items() if k.startswith("html.common.") or k.startswith("html.%s." % page)}
        used = set(re.findall(r"\bL\.([a-z_0-9]+)", t))
        check("翻訳: %s の雛形の既定の言葉（英語）が en.py と同じで、雛形が使う言葉は全て入っている" % fname, default == want and used <= set(default),
              (sorted(used - set(default)), [k for k in want if default.get(k) != want[k]][:3]))
        check("翻訳④: %s の雛形に CJK が無い（コメント・サンプルを含む）" % fname, not CJK_ALL.search(t))
    for f in ("sample_io.json", "sample_schedule.json", "sample_systemtest.json"):
        check("翻訳④: render/%s は英語" % f, not CJK_ALL.search(open(os.path.join(TEMPLATE, "ws", "render", f), encoding="utf-8").read()))
    readme_ja = open(os.path.join(TEMPLATE, "README.ja.md"), encoding="utf-8").read()
    miss = [k for k in ("word.r3", "word.r4a", "word.publish") if JA[k] not in readme_ja]
    check("翻訳⑥: 承認の句（word.r3 / word.r4a / word.publish の ja）が README.ja.md の本文に逐語で出る", not miss, miss)
    readme_en = open(os.path.join(TEMPLATE, "README.md"), encoding="utf-8").read()
    miss = [k for k in ("word.r3", "word.r4a", "word.publish") if EN[k] not in readme_en]
    check("翻訳⑥: 承認の句（en）が README.md の本文に出る", not miss, miss)
    base = os.path.join(TEMPLATE, "ws", "learn")
    cards = lambda c: sorted(n for n in os.listdir(os.path.join(base, c)) if n.endswith(".md"))
    check("翻訳⑦: ws/learn/en と ws/learn/ja の .md のファイル名の集合が一致する", cards("en") == cards("ja") and len(cards("en")) >= 9, (cards("en"), cards("ja")))
    first = lambda c, n: open(os.path.join(base, c, n), encoding="utf-8").readline().strip()
    body = [n for n in cards("en") if not n.startswith("_")]
    diff = [(n, first("en", n), first("ja", n)) for n in body if first("en", n) != first("ja", n) or not first("en", n).startswith("<!-- card:")]
    check("翻訳⑦: 各カードの 1 行目の版の印が en と ja で同じ", not diff, diff)
    heads = lambda c, n: [l[3:].strip() for l in open(os.path.join(base, c, n), encoding="utf-8").read().splitlines() if l.startswith("## ")]
    EN_H = ["In one line", "Think of it as", "What happens now", "Watch out", "The technical name"]
    JA_H = ["一言で", "たとえるなら", "いま起きること", "気をつけること", "裏の名前"]
    bad = [n for n in body if heads("en", n) != EN_H or heads("ja", n) != JA_H]
    check("翻訳⑦: 各カードの 5 見出しが両言語で揃う（en: In one line … / ja: 一言で …）", not bad, bad)
    e = Env()
    try:
        e.env["CREATECODEBOX_LANG"] = "ja"
        out_ja = e.run(["learn"])[1]
        e.env["CREATECODEBOX_LANG"] = "en"
        out_en = e.run(["learn"])[1]
        check("learn: 引数なしは _index.md を使う（ja は ja の一覧・en は en の一覧）", "# 学びカード" in out_ja and "# Learn cards" in out_en and "`save`" in out_ja and "`save`" in out_en, (out_ja[:40], out_en[:40]))
        check("learn: en は ws/learn/en/ のカードを読む", "## In one line" in e.run(["learn", "save"])[1])
        e.env["CREATECODEBOX_LANG"] = "ja"
        check("learn: ja は ws/learn/ja/ のカードを読む", "## 一言で" in e.run(["learn", "save"])[1])
        os.remove(os.path.join(e.root, "ws", "learn", "ja", "_index.md"))
        out = e.run(["learn"])[1]
        check("learn: ja に _index.md が無ければ en の一覧に落ちる", "# Learn cards" in out, out[:40])
        shutil.rmtree(os.path.join(e.root, "ws", "learn", "en"))
        shutil.rmtree(os.path.join(e.root, "ws", "learn", "ja"))
        check("learn: 一覧もカードも無ければ「まだありません」の文", "学びカードはまだありません" in e.run(["learn"])[1])
        e.run(["lang", "set", "en"])
        e.env["CREATECODEBOX_LANG"] = "ja"
        check("言語: CREATECODEBOX_LANG は .ws/lang を上書きする", "言語: ja" in e.run(["lang"])[1])
    finally:
        e.close()


def new_in_r2(e, **fields):
    """A new project at R2 (R1 filled), made the way a user would (English input)."""
    e.hook("sessionstart", {"source": "startup"})
    e.prompt("make a small tool")
    e.run(["new", "app", "--name", "App", "--quote", "make a small tool"])
    base = dict(goal_type="self", what="a small tool")
    base.update(fields)
    e.set_fields("01_app", **base)
    return "01_app"


def test_references():
    sys.path.insert(0, os.path.join(TEMPLATE, "ws"))
    import engine as en
    td = tempfile.mkdtemp(prefix="ccb_ref_")
    try:
        def parse(text):
            d = os.path.join(td, "projects", "p")
            os.makedirs(d, exist_ok=True)
            with open(os.path.join(d, "PROJECT.md"), "w", encoding="utf-8") as f:
                f.write(text)
            return en.parse_project(td, "p")
        one = parse("what: x\nreferences: Todoist | simple list | no teams\n")
        check("8-A: references の parse（1 件・name | like | differ）", one["references"] == ["Todoist | simple list | no teams"] and not one["references_none"] and en.references_ok(one), one)
        three = parse("references: A | a | x\nreferences: B | b | y\nreferences: https://example.com/c | c | z\nwhat: hi\n")
        check("8-A: references の parse（3 件・URL を含む）", len(three["references"]) == 3 and three["references"][2].startswith("https://example.com/c"), three)
        many = parse("references: A | a | x\nreferences: B | b | y\nreferences: C | c | z\nreferences: D | d | w\n")
        check("8-A: references は最大 3 件", len(many["references"]) == 3, many)
        bul = parse("references:\n- A | a | x\n- B | b | y\nwhat: hi\n")
        check("8-A: references: の次の箇条書きも 1 件ずつ読む", len(bul["references"]) == 2 and bul["references"][1].startswith("B"), bul)
        none = parse("references: none\n")
        none_ja = parse("references: なし\n")
        check("8-A: references: none（なし）は満たす・件数は 0", none["references"] == [] and none["references_none"] and en.references_ok(none) and en.references_ok(none_ja), (none, none_ja))
        absent = parse("what: hi\n")
        blank = parse("references: (blank)\n")
        blank_ja = parse("references: （未記入）\n")
        check("8-A: references が無い・空欄（雛形のまま）は満たさない", not en.references_ok(absent) and not en.references_ok(blank) and not en.references_ok(blank_ja), (absent, blank, blank_ja))
    finally:
        shutil.rmtree(td, ignore_errors=True)
    # the order of the R2 todo and the new entrance
    e = Env()
    try:
        slug = new_in_r2(e)
        out = e.run(["status"])[1]
        check("8-A: 雛形の PROJECT.md に references: の行がある（R1 を埋めた直後は R2）", e.stage() == "R2" and "references: (blank)" in open(e.p("projects", slug, "PROJECT.md"), encoding="utf-8").read(), out)
        e.set_fields(slug, goal_type="(blank)")
        check("8-A: R1 の todo に references は出ない", e.stage() == "R1" and "references" not in e.run(["status"])[1])
        e.set_fields(slug, goal_type="self")
        e.set_fields(slug, who="me", today="by hand", done_when="it works", not_doing="nothing else", has_ui="no")
        out = e.run(["status"])[1]
        want = "Ask about a reference site or app (or confirm none): add `references:` lines to PROJECT.md"
        check("8-A: 新規の入口の R2 は、todo の先頭が references の文・その次が Show the prototype",
              e.stage() == "R2" and ("missing: " + want) in out and out.index("Show the prototype") > out.index(want), out)
        e.write("projects/%s/design/ui/sketch.html" % slug, SKETCH)
        check("8-A: sketch があっても references が無ければ R2 のまま", e.stage() == "R2" and want in e.run(["status"])[1])
        e.set_fields(slug, references="Todoist | like the list | no accounts")
        check("8-A: references の行が 1 つあれば満たされ、R4 へ進む", e.stage() == "R4", e.stage())
    finally:
        e.close()
    e = Env()
    try:
        slug = new_in_r2(e, who="me", today="by hand", done_when="it works", not_doing="nothing else", has_ui="no")
        e.set_fields(slug, references="none")
        out = e.run(["status"])[1]
        check("8-A: references: none も満たす・次は sketch", e.stage() == "R2" and "Ask about a reference" not in out and "Show the prototype" in out, out)
    finally:
        e.close()
    # an old PROJECT.md (no references line) with io.json or brief.md is not pushed back
    e = Env()
    try:
        slug = new_in_r2(e, who="me", today="by hand", done_when="it works", not_doing="nothing else", has_ui="no")
        p = e.p("projects", slug, "PROJECT.md")
        txt = "\n".join(l for l in open(p, encoding="utf-8").read().splitlines() if not l.startswith("references:")) + "\n"
        open(p, "w", encoding="utf-8").write(txt)
        e.write("projects/%s/design/io.json" % slug, json.dumps(IO_EN))
        check("8-A: 旧い PROJECT.md（references 無し・io.json あり）は後退しない（R4A）", e.stage() == "R4A", e.stage())
    finally:
        e.close()
    e = Env()
    try:
        slug = new_in_r2(e, who="me", today="by hand", done_when="it works", not_doing="nothing else", has_ui="yes")
        p = e.p("projects", slug, "PROJECT.md")
        kept = "\n".join(l for l in open(p, encoding="utf-8").read().splitlines() if not l.startswith("references:")) + "\n"
        open(p, "w", encoding="utf-8").write(kept)
        e.write("projects/%s/design/ui/brief.md" % slug, "## Purpose\nA\n## Layout\nB\n## Colors\nC\n## Text\nD\n## States\nE\n")
        e.write("projects/%s/design/ui/index.html" % slug, "<html><body>x</body></html>")
        check("8-A: 旧い PROJECT.md（references 無し・brief.md あり）は後退しない（R3）", e.stage() == "R3", e.stage())
    finally:
        e.close()
    # tentative: values satisfy the R2 fields (filled())
    e = Env()
    try:
        slug = new_in_r2(e, who="tentative: only me", today="tentative: by hand", done_when="tentative: it works", not_doing="tentative: nothing else",
                         has_ui="no", references="none")
        e.write("projects/%s/design/ui/sketch.html" % slug, SKETCH)
        check("8-A 改訂: R2 の必須項目が全部 tentative: の値でも R2 を出る（R4）", e.stage() == "R4", e.stage() + e.run(["status"])[1])
    finally:
        e.close()
    sys.path.insert(0, os.path.join(TEMPLATE, "ws"))
    from lang import en as lang_en, ja as lang_ja
    check("8-A 改訂: sketch の上部の文 2 種が en・ja の表にある（参考あり・なし）と、規則文に参考なしの文",
          lang_en.MESSAGES["sketch.banner.ref"] == "Based on {reference} and your words. Tell me what is different."
          and lang_en.MESSAGES["sketch.banner.noref"] in lang_en.MESSAGES["rule.R1"] and "{reference}" in lang_ja.MESSAGES["sketch.banner.ref"]
          and "Based on <reference> and your words. Tell me what is different." in lang_en.MESSAGES["rule.R1"])


def test_place():
    sys.path.insert(0, os.path.join(TEMPLATE, "ws"))
    import engine as en
    base = os.path.realpath(tempfile.mkdtemp(prefix="ccb_pl_"))
    try:
        home = os.path.join(base, "home")

        def mk(*parts, git=False):
            d = os.path.join(home, *parts) if parts[0] != "/outside" else os.path.join(base, "outside", *parts[1:])
            os.makedirs(d, exist_ok=True)
            return d

        def chk(path):
            return en.place_check(path, home=home)
        ok_dir = mk("CreateCodeBox")
        s, why = chk(ok_dir)
        check("8-B: ~/CreateCodeBox は ok", s == "ok" and why == "", (s, why))
        for name, folder in (("Downloads", "Downloads"), ("Desktop", "Desktop"), ("Documents", "Documents")):
            s, why = chk(mk(folder, "ws"))
            check("8-B: ~/%s の下は warn" % name, s == "warn" and ("~/" + name) in why, (s, why))
        s, why = chk(mk("OneDrive - Co", "ws"))
        check("8-B: OneDrive の下は warn", s == "warn" and "OneDrive" in why, why)
        s, why = chk(mk("Library", "Mobile Documents", "com~apple~CloudDocs", "ws"))
        check("8-B: iCloud（Library/Mobile Documents）の下は warn", s == "warn" and "iCloud" in why, why)
        s, why = chk(mk("Dropbox", "ws"))
        check("8-B: Dropbox の下は warn", s == "warn" and "Dropbox" in why, why)
        s, why = chk(mk("My Folder", "ws"))
        check("8-B: パスに空白があると warn", s == "warn" and "space" in why, why)
        s, why = chk(mk("日本語", "ws"))
        check("8-B: パスに非 ASCII があると warn", s == "warn" and "non-ASCII" in why, why)
        proj = mk("proj", "ws")
        os.makedirs(os.path.join(home, "proj", ".git"))
        s, why = chk(proj)
        check("8-B: 親フォルダに .git があると warn", s == "warn" and "git repo" in why and os.path.join(home, "proj") in why, why)
        own = mk("mine")
        os.makedirs(os.path.join(own, ".git"))
        s, why = chk(own)
        check("8-B: ワークスペース自身の .git は数えない（ok）", s == "ok", (s, why))
        outside = os.path.join(base, "outside", "ws")
        os.makedirs(outside)
        s, why = chk(outside)
        check("8-B: ホームの外（$HOME 配下でない）は warn", s == "warn" and "outside your home folder" in why, why)
        odd_home = os.path.join(base, "ホーム 名")
        os.makedirs(odd_home, exist_ok=True)
        for alt in ("/Users/Shared/coffee-log", "/c/coffee-log", "/Users/Shared/CreateCodeBox"):
            s, why = en.place_check(alt, home=odd_home)
            check("8-B: ホームのパスに空白か非 ASCII があるとき、%s は「ホームの外」の警告を出さない（他の条件が無ければ ok）" % alt, s == "ok" and why == "", (s, why))
            s, why = en.place_check(alt, home=home)
            check("8-B: ホームのパスが普通のときは、%s は今までどおり「ホームの外」の警告" % alt, s == "warn" and "outside your home folder" in why, (s, why))
        check("8-B: Windows の C:/<アプリの名前> も同じ置き場（drive 文字つき）", en.safe_alt_place("C:/coffee-log", "C:/Users/山田") and en.safe_alt_place("D:/CreateCodeBox", "C:/Users/a b")
              and not en.safe_alt_place("C:/coffee-log", "C:/Users/yamada") and not en.safe_alt_place("C:/Program Files", "C:/Users/山田"))
        s, why = en.place_check("/Users/Shared/Other/coffee-log", home=odd_home)
        check("8-B: 決めた置き場以外（別の深さ）は、ホームが変でも「ホームの外」の警告のまま", s == "warn" and "outside your home folder" in why, (s, why))
        s, why = en.place_check("/Users/Shared/coffee log", home=odd_home)
        check("8-B: 置き場の名前が違う・空白つきなら、ホームが変でも警告のまま", s == "warn" and "outside your home folder" in why and "space" in why, (s, why))
        s, why = chk(mk("Downloads", "my ws"))
        check("8-B: 理由が複数あれば全て出る", s == "warn" and "Downloads" in why and "space" in why, why)
        check("8-B: place の行は warn のとき理由と移し方の 1 行（Make a new empty folder for your app …）",
              en.place_line(outside, home=home).startswith("place: warn ") and en.place_line(outside, home=home).endswith("on a Mac right under /Users/Shared/.")
              and en.place_line(ok_dir, home=home) == "place: ok")
    finally:
        shutil.rmtree(base, ignore_errors=True)
    e = Env()
    try:
        out = e.run(["doctor"])[1]
        check("8-B: doctor の出力に place: ok / place: warn <理由>（試験の置き場は $HOME の外なので warn）", "place: warn " in out and "outside your home folder" in out, out)
        c = e.ctx("sessionstart", {"source": "startup"})
        check("8-B: SessionStart の context にも place の行", "place: warn " in c, c[:300])
        e.env.pop("CREATECODEBOX_LANG", None)
        os.makedirs(e.p(".ws"), exist_ok=True)
        open(e.p(".ws", "lang"), "w").write("ja\n")
        c = e.ctx("sessionstart", {"source": "startup"})
        check("8-B（第 2 回）: .ws/lang が ja なら SessionStart の place の行は ja（理由と移し方）", "place: warn " in c and "ホームフォルダの外" in c and "outside your home folder" not in c and "Make a new empty folder" not in c, c[:400])
        out = e.run(["doctor"])[1]
        check("8-B（第 2 回）: .ws/lang が ja なら doctor の place の行も ja", "ホームフォルダの外" in out and "Make a new empty folder" not in out, out)
        sys.path.insert(0, os.path.join(TEMPLATE, "ws"))
        import engine as en_mod
        import lang as lg_mod
        lg_mod.use("en")
        line = en_mod.place_line(e.root)
        lg_mod.use(None)
        check("8-B（第 2 回）: place_line は呼び出し側の言語に関わらず .ws/lang の言語で出し、呼び出し側の設定を戻す", "ホームフォルダの外" in line and lg_mod._CUR is None, line)
        os.remove(e.p(".ws", "lang"))
        check("8-B: warn は止めない（hook は普通に動く）", "[CreateCodeBox" in c and e.pre("Bash", command="ls") is None)
        e.env["CREATECODEBOX_LANG"] = "ja"
        out = e.run(["doctor"])[1]
        check("8-B: ja の place の文（place: warn の印は同じ・理由と移し方は ja）", "place: warn " in out and "ホームフォルダの外" in out and "アプリ用の新しい空のフォルダ" in out, out)
    finally:
        e.close()


def test_read_only_options():
    """Commands that are let through as read-only before approval must not write or run anything (review of v0.4.0)."""
    e = Env()
    try:
        slug = new_in_r2(e, goal_type="(blank)")
        check("(前提) R1", e.stage() == "R1")
        src = "projects/%s/src" % slug
        deny = ["find projects -fprintf %s/a.txt %%p" % src, "find . -fprint0 %s/a" % src, "find . -fprint %s/a" % src, "find . -fls %s/a" % src,
                "find . -delete", "find . -exec touch {} +", "find . -execdir touch x", "find . -ok rm", "find . -okdir rm",
                "find -O3 . -name a", "find . -name a -fprintf x y", "find . -newerXX x",
                "tree -o %s/a.txt" % src, "tree -R -H . -L 1", "tree -aR", "tree -Lo 1 x", "tree --output=x",
                "rg --pre cat x", "rg --pre=cat x", "rg --hostname-bin=/bin/sh x", "rg --hostname-bin /bin/sh x",
                "find . \"-fprintf\" a x", "find . '-delete'", "find . \\-delete", "find . -\"exec\" touch {} +", "tree \"-o\" x", "tree '-R'",
                "rg \"--pre\" cat x", "git diff \"--output=x\"", "date \"-s\" 2020-01-01",
                "find . {-delete,}", "rg {--pre,cat} x", "tree {-o,x}", "git diff {--output=x,}", "find . *delete", "find . -name *.md", "git diff --out=x", "rg \"--pre\"* x", "find . -name x\"*\"",
                "find . =(touch x)", "echo *(e:'touch x':)", "cat =(date)", "find . .(e:'touch x':)", "cd =(touch) && ls",
                "bash ws/bin/ws.sh status =(touch x)", "echo a#(touch x)", "echo d/a#b*(e:'touch x':)", "bash ws/bin/ws.sh status d/a#*(e:'touch x':)"]
        passed = [c for c in deny if e.pre("Bash", command=c) is None]
        check("読取り扱いの find・tree・rg でも、書く・動かすオプションは承認前に止まる（%d 例）" % len(deny), not passed, passed)
        ok = ["find . -name PROJECT.md", "find projects -maxdepth 2 -type f -name \"*.md\"", "find . -newermt 2026-01-01 -print",
              "find . ! -name a -print0", "find . -size +1k -ls", "find . -printf %p", "tree -L 2", "tree -a -d", "rg -n what projects", "rg --files",
              "find . -name \"*.md\"", "rg -n \"to do\" projects", "date \"+%F\""]
        bad = [c for c in ok if e.pre("Bash", command=c) is not None]
        check("読むだけの find・tree・rg は今までどおり通る（%d 例）" % len(ok), not bad, bad)
        check("ws.sh の引数の引用符の中の ( ) は今までどおり通る（zsh でもただの文字）", e.pre("Bash", command="bash ws/bin/ws.sh task add \"Fix login (urgent)\"") is None)
    finally:
        e.close()


def test_update_check():
    """A new version is checked at most once a day, told in one line, and never installed without the user."""
    e = Env()
    try:
        cur = open(os.path.join(e.root, "ws", "VERSION")).read().strip()
        major, minor, patch = (int(x) for x in cur.split("."))
        newer = "%d.%d.0" % (major, minor + 1)
        remote = os.path.join(e.tmp, "remote.git")
        src = os.path.join(e.tmp, "remote_src")
        subprocess.run(["git", "init", "-q", "--bare", remote], check=True)
        subprocess.run(["git", "init", "-q", src], check=True)
        g = lambda *a: subprocess.run(["git", "-C", src, "-c", "user.name=t", "-c", "user.email=t@t.invalid"] + list(a), capture_output=True, text=True)
        open(os.path.join(src, "a"), "w").write("a")
        g("add", "a"); g("commit", "-q", "-m", "a")
        for tag in ("v" + cur, "v" + newer, "latest", "v99.0.0-rc1", "v98.0"):
            g("tag", tag)
        g("push", "-q", remote, "--tags")
        e.env.update(CREATECODEBOX_UPDATE_URL=remote, CREATECODEBOX_UPDATE_SYNC="1")
        start = lambda: e.ctx("sessionstart", {"source": "startup"})
        out = start()
        check("版: 新しい版があると、会話の始まりに 1 行で伝える（%s）" % newer, newer in out and "Do not update unless the user asks" in out, out)
        check("版: 版の形でないタグ（latest・-rc1・2 桁）は数えない", "99.0.0" not in out and "98.0" not in out, out)
        out = e.pctx("hello")
        check("版: 同じ日の途中の発言では、もう一度は言わない", newer not in out, out)
        subprocess.run(["git", "-C", remote, "tag", "-d", "v" + newer], capture_output=True)
        out = start()
        check("版: 24 時間たつまでは問い合わせない（前の結果のまま知らせる）", newer in out, out)
        e.env["CREATECODEBOX_UPDATE_EVERY"] = "0"
        out = start()
        check("版: 24 時間たてば問い合わせ直す（同じ版なら何も言わない）", newer not in out and "CreateCodeBox" not in out.split("\n")[-1], out)
        check("版: update-check の状態は「最新」", "newest" in e.run(["update-check"])[1] or "最新" in e.run(["update-check"])[1], e.run(["update-check"])[1])
        g("tag", "v" + newer); g("push", "-q", remote, "--tags")
        out = e.pctx("hello again")
        check("版: 使い続けていても、1 日 1 回は確かめて伝える", newer in out, out)
        rc, msg = e.run(["update-check", "off"])
        out = start()
        check("版: update-check off で、確かめも知らせもしない", rc == 0 and newer not in out, (msg, out))
        e.run(["update-check", "on"])
        check("版: update-check on で元に戻る", newer in start())
        e.env["CREATECODEBOX_UPDATE_URL"] = os.path.join(e.tmp, "nowhere.git")
        out = start()
        check("版: つながらない時は黙って飛ばし、会話は普通に始まる", newer not in out and "[CreateCodeBox" in out, out)
        rc, msg = e.run(["update-check"])
        check("版: つながらなかったことは状態で分かる", "could not get a version" in msg or "確かめられませんでした" in msg, msg)
        e.env.pop("CREATECODEBOX_UPDATE_SYNC")
        e.env["CREATECODEBOX_UPDATE_URL"] = remote
        t0 = time.time()
        start()
        quick = time.time() - t0
        rec_path = os.path.join(e.root, ".ws", "update_check.json")
        for _ in range(50):
            try:
                if json.load(open(rec_path)).get("latest") == newer:
                    break
            except (OSError, ValueError):
                pass
            time.sleep(0.2)
        check("版: 問い合わせは裏で動き、会話の始まりを待たせない（%.1f 秒）" % quick, json.load(open(rec_path)).get("latest") == newer, quick)
        import engine as eng_u
        e.env.pop("CREATECODEBOX_UPDATE_URL")
        os.environ.pop("CREATECODEBOX_UPDATE_URL", None)
        check("版: git で取っていないコピーは問い合わせない", eng_u.update_source(e.root) is None)
        subprocess.run(["git", "init", "-q", e.root], check=True)
        subprocess.run(["git", "-C", e.root, "remote", "add", "origin", "git@github.com:someone/CreateCodeBox.git"], check=True)
        check("版: SSH の住所は問い合わせない（パスワードを聞かれないように）", eng_u.update_source(e.root) is None)
        subprocess.run(["git", "-C", e.root, "remote", "set-url", "origin", "https://github.com/someone/CreateCodeBox.git"], check=True)
        check("版: フォークは自分の origin（update が取りに行く所）に問い合わせる", eng_u.update_source(e.root) == "https://github.com/someone/CreateCodeBox.git")
        check("版: 何が変わったかのページは、こちらで組み立てる", eng_u.update_page("https://github.com/someone/CreateCodeBox.git", "1.2.3") == "https://github.com/someone/CreateCodeBox/releases/tag/v1.2.3"
              and eng_u.update_page("https://example.com/x/y", "1.2.3") == "")
    finally:
        e.close()


def test_update_codex_hooks_note():
    """After `update`, a change to the Codex hooks is told, so Codex users trust them again."""
    e = Env()
    try:
        remote = os.path.join(e.tmp, "ws_remote.git")
        gr = lambda d, *a: subprocess.run(["git", "-C", d, "-c", "user.name=t", "-c", "user.email=t@t.invalid"] + list(a), capture_output=True, text=True)
        subprocess.run(["git", "init", "-q", "--bare", remote], check=True)
        subprocess.run(["git", "init", "-q", e.root], check=True)
        gr(e.root, "add", "-A"); gr(e.root, "commit", "-q", "-m", "v1"); gr(e.root, "branch", "-M", "main")
        gr(e.root, "remote", "add", "origin", remote); gr(e.root, "push", "-q", "-u", "origin", "main")
        other = os.path.join(e.tmp, "other")
        subprocess.run(["git", "clone", "-q", "-b", "main", remote, other], check=True)  # the bare repo's HEAD may name master
        hooks = os.path.join(other, ".codex", "hooks.json")
        if os.path.exists(hooks):
            open(hooks, "a").write("\n")
            gr(other, "commit", "-q", "-am", "hooks"); gr(other, "push", "-q", "origin", "HEAD:main")
            rc, out = e.run(["update"])
            check("更新: Codex のフックが変わったら、/hooks で信頼し直すよう伝える", rc == 0 and "/hooks" in out, out)
            check("更新: 開き直すよう伝える", "open it again" in out or "開き直して" in out, out)
        else:
            check("更新: (前提) .codex/hooks.json がある", False)
    finally:
        e.close()


def test_compound_and_project_write():
    e = Env()
    try:
        slug = new_in_r2(e, goal_type="(blank)")
        check("(前提) R1", e.stage() == "R1")
        ok = ["cd projects/%s && ls" % slug, "cd projects/%s && cat PROJECT.md" % slug, "cd %s && ls -la" % e.root, "cd projects/%s/design && pwd" % slug,
              "cd projects/%s && grep -n what PROJECT.md" % slug, "cd projects/%s && head PROJECT.md" % slug, "cd projects/%s && tail PROJECT.md" % slug,
              "cd projects/%s && wc -l PROJECT.md" % slug, "cd projects/%s && find . -name PROJECT.md" % slug]
        bad = [r for r in ok if e.pre("Bash", command=r) is not None]
        check("問題1: R1 で cd <ws 内> && ls|cat|head|tail|wc|grep|pwd|find は通る（%d 例）" % len(ok), not bad, bad)
        deny = ["cd projects/%s && rm PROJECT.md" % slug, "cd projects/%s && ls && pwd" % slug, "cd projects/%s; ls; pwd" % slug, "cd projects/%s && ls > out.txt" % slug,
                "cd / && ls", "cd .. && ls", "cd projects/%s && cat .env" % slug, "cd projects/%s && sed -i s/a/b/ PROJECT.md" % slug,
                "ls; rm x", "ls; ls; ls", "ls /etc; cat PROJECT.md", "cat ../../etc/passwd; ls", "cd projects/%s && ls ../../.." % slug, "ls &; ls", "cd projects/%s && ls | wc -l" % slug, "cd projects/%s && mkdir x" % slug, "cd projects/%s && ls $HOME" % slug]
        ok2 = [r for r in deny if e.pre("Bash", command=r) is None]
        check("問題1: 上の形から外れるもの（rm・区切り 2 つ以上・リダイレクト・ws の外の引数・.env・sed・パイプ・変数）は止まる（%d 例）" % len(deny), not ok2, ok2)
        semi = ["ls projects/%s; cat projects/%s/PROJECT.md" % (slug, slug), "ls; pwd", "cd projects/%s; ls" % slug, "ls projects; wc -l projects/%s/PROJECT.md" % slug,
                "pwd; ls ws", "ls && ls", "cat PROJECT.md; head -3 projects/%s/PROJECT.md" % slug]
        bad = [r for r in semi if e.pre("Bash", command=r) is not None]
        check("問題1（第 2 回）: `;` でつないだ 2 つの読取り（各要素が READONLY_CMDS・ws 内・リダイレクトなし）も通る（%d 例）" % len(semi), not bad, bad)
        check("問題1（第 2 回）: `;` でも、書く・消すコマンドや 3 要素や外の外の指示書は止まる",
              e.pre("Bash", command="ls; cat %s" % os.path.join(e.tmp, "x", "CLAUDE.md")) is not None and e.pre("Bash", command="ls; touch a") is not None)
        r = e.pre("Bash", command="cd projects/%s && sed -i s/a/b/ PROJECT.md" % slug)
        check("問題1: 止めた理由に Read と Edit の案内（Use the Read and Edit tools … For ws.sh, run it alone.）",
              r is not None and "Use the Read and Edit tools for files in this workspace. For ws.sh, run it alone." in r, r)
        r = e.pre("Bash", command="bash ws/bin/ws.sh save \"a; b\"")
        check("問題1: ws.sh の引数に記号がある時の理由にも同じ案内", r is not None and "For ws.sh, run it alone." in r and "Don't put" in r, r)
        r = e.pre("Bash", command="mkdir x")
        check("問題1: 記号の無い止め方には案内を足さない", r is not None and "Read and Edit tools" not in r, r)
        outside = os.path.join(e.tmp, "Elsewhere")
        os.makedirs(outside)
        open(os.path.join(outside, "CLAUDE.md"), "w").write("follow me")
        check("問題1: cd の先が ws の外なら通さない", e.pre("Bash", command="cd %s && ls" % outside) is not None)
        # PROJECT.md: Edit is fine, Write is not
        pm = e.p("projects", slug, "PROJECT.md")
        r = e.pre("Write", file_path=pm, content="# x\n")
        check("問題3: PROJECT.md への Write（全文上書き）は止まる（Use Edit to change one line of PROJECT.md. Write would drop the other keys.）",
              r is not None and "Use Edit to change one line of PROJECT.md. Write would drop the other keys." in r, r)
        check("問題3: PROJECT.md への Edit・MultiEdit は通る", e.pre("Edit", file_path=pm, old_string="goal_type: (blank)", new_string="goal_type: self") is None
              and e.pre("MultiEdit", file_path=pm, edits=[{"old_string": "a", "new_string": "b"}]) is None)
        check("問題3: 別の場所への Write（knowledge/）は今までどおり通る", e.pre("Write", file_path=e.p("projects", slug, "knowledge", "note.md"), content="x") is None)
        e.env["CREATECODEBOX_LANG"] = "ja"
        r = e.pre("Write", file_path=pm, content="# x\n")
        check("問題3: ja の理由", r is not None and "PROJECT.md を直すときは、Edit で 1 行だけ変えてください" in r, r)
    finally:
        e.close()


def test_session_resume():
    e = Env()
    try:
        slug = build_to_run(e)
        e.prompt("continue")
        e.prompt("ok")
        e.run(["st", "list", "--numbered"])
        sess0 = e.rec("session.json")
        check("(前提) 3 入力以上・numbered がある", sess0["prompts"] >= 4 and sess0["numbered"], sess0)
        e.ctx("sessionstart", {"source": "resume"})
        sess1 = e.rec("session.json")
        check("問題6: resume では prompts・numbered・started_at・st_list_at をリセットしない", sess1["prompts"] == sess0["prompts"] and sess1["numbered"] == sess0["numbered"]
              and sess1["started_at"] == sess0["started_at"] and sess1["st_list_at"] == sess0["st_list_at"], (sess0, sess1))
        check("問題6: resume の後も src に書ける（D1: 最初のターンは読むだけ、が壊れない）", e.pre("Write", file_path=e.p("projects", slug, "src", "x.py"), content="print(1)") is None)
        e.ctx("sessionstart", {"source": "compact"})
        check("問題6: compact でもリセットしない", e.rec("session.json")["prompts"] == sess0["prompts"])
        e.prompt("3 pass")
        rc, out = e.run(["st", "mark", "numbered", "pass", "--by", "user"])
        check("問題6: resume の後も、直前の st list --numbered の番号で答えられる（C1 の印）", rc == 0, out)
        e.ctx("sessionstart", {"source": "startup"})
        sess2 = e.rec("session.json")
        check("問題6: startup では prompts=0 にリセットされ、最初のターンは読むだけ（D1）", sess2["prompts"] == 0 and e.pre("Write", file_path=e.p("projects", slug, "src", "x.py"), content="print(1)") is not None, sess2)
        e.prompt("hello again")
        e.ctx("sessionstart", {"source": "clear"})
        check("問題6: clear でもリセットされる", e.rec("session.json")["prompts"] == 0)
    finally:
        e.close()


def to_r3(e, lang_code):
    e.hook("sessionstart", {"source": "startup"})
    e.prompt("make a booking page" if lang_code == "en" else "予約ページを作りたい")
    e.run(["new", "book", "--name", "Book", "--quote", "make a booking page" if lang_code == "en" else "予約ページ"])
    slug = "01_book"
    e.set_fields(slug, goal_type="share", what="booking page", who="clients", today="phone", done_when="clients can book", not_doing="payments", has_ui="yes", viz="local")
    e.write("projects/%s/design/ui/sketch.html" % slug, SKETCH)
    e.write("projects/%s/design/ui/brief.md" % slug, "## Purpose\nBook\n## Layout\nTop date\n## Colors\nblue\n## Text\nlarge\n## States\nempty hint\n")
    e.write("projects/%s/design/ui/index.html" % slug, "<html><body>x</body></html>")
    return slug


def test_approval_phrases():
    e = Env()
    try:
        slug = to_r3(e, "en")
        e.run(["lang", "set", "ja"])
        check("承認の句: R3 は言語設定が ja でも英語の looks good で記録される（和集合）", e.stage() == "R3")
        e.pctx("hmm, looks good but change the color")
        check("承認の句: but / change を含む入力は記録されない", e.stage() == "R3")
        e.pctx("This is not looks good")
        check("承認の句: 否定語を含む入力は記録されない", e.stage() == "R3")
        e.pctx("looks good to me and I like it very much thanks")
        check("承認の句: 6 語を超える入力は記録されない", e.stage() == "R3")
        c = e.pctx("ｌｏｏｋｓ　ｇｏｏｄ！")
        check("承認の句: 全角（NFKC）・末尾の記号・大文字小文字を無視して記録される", e.stage() == "R4" and "記録しました" in c, (e.stage(), c[-150:]))
        e.write("projects/%s/design/ui/brief.md" % slug, "## 目的\n予約\n## 配置\n上\n## 色\n青\n## 文字\n大\n## 状態\n空\n")
        check("旧い日本語の見出しの brief.md も読める", e.stage() == "R3", e.stage())
        e.run(["lang", "set", "en"])
        e.pctx("この形で")
        check("承認の句: R3 は言語設定が en でも「この形で」で記録される", e.stage() == "R4", e.stage())
        e.write("projects/%s/design/io.json" % slug, json.dumps({"rows": [dict(IO_EN["rows"][0], kind="screen", screen="SC-1"), IO_EN["rows"][1]]}))
        check("lint 通過で R4A", e.stage() == "R4A", e.stage())
        c = e.pctx("yes")
        want = "I did not record that as your approval. To approve, send only the word: approve"
        check("C1: R4A で、質問の前の短い「yes」が記録されなかった時は note（en の文）。自然な返事のほうは 2 段承認（test_two_step_approval）", want in c, c[-200:])
        c = e.pctx("yes please")
        check("C1: 別の「はい」の形でも、質問の前なら note が出る", want in c, c[-200:])
        c = e.pctx("no, change the layout")
        check("C1: 否定・修正の入力には note を出さない", "I did not record" not in c, c[-200:])
        c = e.pctx("yes please make the title bigger and the button red now")
        check("C1: 6 語を超える入力には note を出さない", "I did not record" not in c)
        e.pctx("not approved")
        check("承認の句: 否定は記録されない", e.stage() == "R4A")
        e.pctx("I approve")
        check("承認の句: R4A は I approve で記録される", e.stage() in ("RS", "RUN"), e.stage())
        # ja side and variants in a fresh project
        e2 = Env()
        slug2 = to_r3(e2, "ja")
        c = e2.pctx("はい")
        check("C1: ja の入力でも note が出る（ja の表の文）・R3 の合言葉は「この形で」", "次の 1 語だけを送ってください: この形で" in c, c[-200:])
        e2.pctx("this design")
        check("承認の句: this design", e2.stage() == "R4", e2.stage())
        e2.close()
        for phrase, idx in (("go with this", 0), ("approved.", 1)):
            e3 = Env()
            to_r3(e3, "en")
            if idx == 0:
                e3.pctx(phrase)
                check("承認の句: R3 の go with this", e3.stage() == "R4", e3.stage())
            else:
                e3.pctx("looks good")
                e3.write("projects/01_book/design/io.json", json.dumps({"rows": [dict(IO_EN["rows"][0], kind="screen", screen="SC-1"), IO_EN["rows"][1]]}))
                e3.pctx(phrase)
                check("承認の句: R4A の approved.", e3.stage() in ("RS", "RUN"), e3.stage())
            e3.close()
        e4 = Env()
        to_r3(e4, "ja")
        e4.pctx("この形で")
        e4.write("projects/01_book/design/io.json", json.dumps({"rows": [dict(IO_EN["rows"][0], kind="screen", screen="SC-1"), IO_EN["rows"][1]]}))
        e4.pctx("承認します！")
        check("承認の句: ja の「承認します！」（全角の記号）", e4.stage() in ("RS", "RUN"), e4.stage())
        e4.close()
    finally:
        e.close()


def test_publish_phrase():
    e = Env()
    try:
        slug = build_to_run(e)
        e.write("projects/%s/src/README.md" % slug, "# app\n")
        e.write("projects/%s/src/LICENSE" % slug, "MIT\n")
        e.run(["save", "first"])
        e.run(["save", "first"])
        e.run(["publish-check"])
        rc, out = e.run(["publish-check"])
        check("公開: 検査が通る", rc == 0 and "Result: passed" in out, out)
        c = e.pctx("yes")
        check("C1: 公開検査が通った後の短い肯定には、publish の note", "To approve, send only the word: publish" in c, c[-200:])
        c = e.pctx("Publish it!")
        check("承認の句: publish it（言語設定に依らず）が記録される", "Recorded the user's \"publish\"" in c, c[-200:])
        e.pctx("publish")
        e2 = Env()
        build_to_run(e2)
        c = e2.pctx("publish")
        check("公開: 検査が無い時の publish は記録されず、先に検査と伝える", "check" in c and "Recorded the user's" not in c, c[-200:])
        e2.close()
    finally:
        e.close()


Q_R3_EN = "Do you want your message recorded as 'looks good' for this prototype? Reply yes to record it."
Q_R4A_EN = "Do you want your message recorded as your approval of the design and the table? Reply yes to record it."
Q_R3_JA = "このプロトタイプについて、今の返事を「この形で」として記録しますか。記録してよければ「はい」と返してください。"
Q_R4A_JA = "今の返事を、設計と表の承認として記録しますか。記録してよければ「はい」と返してください。"
IO_SCREEN = {"rows": [dict(IO_EN["rows"][0], kind="screen", screen="SC-1"), IO_EN["rows"][1]]}


def to_r4a(e, lang_code):
    """R3 -> R4A with the exact words (so the two-step tests start at the table stage)."""
    slug = to_r3(e, lang_code)
    e.pctx("この形で" if lang_code == "ja" else "looks good")
    e.write("projects/%s/design/io.json" % slug, json.dumps(IO_SCREEN))
    return slug


def test_two_step_approval():
    sys.path.insert(0, os.path.join(TEMPLATE, "ws"))
    import engine as en
    en_yes = ["yes", "Yes", "YES!", "y", "Y.", "yes please", "Yes, please.", "yes record it", "Yes, record it", "ｙｅｓ", "  yes  "]
    ja_yes = ["はい", "はい。", "はい！", "はい、お願いします", "はい、お願いします。", "お願いします", "お願いします。"]
    no_yes = ["yeah", "ok", "okay", "sure", "yes but change the color", "yes, not yet", "no", "not yes", "yes yes", "record it", "go ahead",
              "はいはい", "はい、でも直して", "いいえ", "いいですね", "了解", "はい、お願いします。直してください", ""]
    check("2 段承認: 「はい」の表（en）は全て通る", all(en.is_confirm_yes(x) for x in en_yes), [x for x in en_yes if not en.is_confirm_yes(x)])
    check("2 段承認: 「はい」の表（ja）は全て通る（句点・感嘆符は無視）", all(en.is_confirm_yes(x) for x in ja_yes), [x for x in ja_yes if not en.is_confirm_yes(x)])
    check("2 段承認: 表に無い返事は「はい」にならない（ok・sure・否定や混ぜ物・空）", not any(en.is_confirm_yes(x) for x in no_yes), [x for x in no_yes if en.is_confirm_yes(x)])
    check("2 段承認: 2 段が使えるのは R3 と R4A だけ（publish は入っていない）", en.CONFIRM_KIND == {"R3": "r3", "R4A": "r4a"})

    # --- R3, English: natural reply -> question -> yes
    e = Env()
    try:
        slug = to_r3(e, "en")
        c = e.pctx("Looks great, go ahead")
        pend = e.rec("session.json").get("pending_confirm") or {}
        check("2 段承認(R3 en): 自然な返事は記録されず、保留が立つ（種類・project・hash・何番目の入力か・引用）",
              e.stage() == "R3" and not os.path.exists(e.p(".ws", "confirm_%s.json" % slug)) and pend.get("kind") == "r3" and pend.get("slug") == slug
              and pend.get("hash") == en.sha(en.ui_files(e.root, slug)) and pend.get("n") == e.rec("session.json")["prompts"] and pend.get("quote") == "Looks great, go ahead", pend)
        check("2 段承認(R3 en): その回の context に、決まった質問（en）を 1 回だけ言わせる指示が出る・「語だけ送って」の note は出ない",
              ('"%s"' % Q_R3_EN) in c and c.count(Q_R3_EN) == 1 and "I did not record that as your approval" not in c, c[-400:])
        c = e.pctx("yes")
        rec = e.rec("confirm_%s.json" % slug)
        check("2 段承認(R3 en): すぐ次の入力の yes で記録され、R4 に進む", e.stage() == "R4" and "Recorded the user's \"looks good\"" in c, (e.stage(), c[-300:]))
        check("2 段承認(R3 en): 記録に via=confirm と 2 つの引用（自然な返事と yes）・署名がある",
              rec.get("via") == "confirm" and rec.get("quote") == "Looks great, go ahead" and rec.get("confirm_quote") == "yes"
              and rec.get("hash") == en.sha(en.ui_files(e.root, slug)) and "_sig" in rec and rec.get("prompt") == rec.get("asked_prompt") + 1, rec)
        check("2 段承認(R3 en): 使った保留は消える・context に via の note", (e.rec("session.json").get("pending_confirm") is None) and "plain yes" in c)
        e.pctx("make the title bigger")
        e.write("projects/%s/design/ui/brief.md" % slug, "## Purpose\nBook\n## Layout\nTop date\n## Colors\nred\n## Text\nlarge\n## States\nempty hint\n")
        check("2 段承認: 記録の後でも、見た目を変えれば普通に R3 へ戻る（記録は hash に縛られている）", e.stage() == "R3", e.stage())
        c = e.pctx("yes")
        check("2 段承認: 保留なしの yes だけでは記録されない（note は従来どおり）", e.stage() == "R3" and "send only the word: looks good" in c, c[-250:])
    finally:
        e.close()

    # --- wrong next prompt clears; not the very next prompt; negative / mixed never starts
    e = Env()
    try:
        slug = to_r3(e, "en")
        e.pctx("Looks great, go ahead")
        c = e.pctx("what color is the button?")
        check("2 段承認: 次の入力が yes でなければ保留は消え、何も記録されない・消えたと伝える note",
              e.stage() == "R3" and e.rec("session.json").get("pending_confirm") is None and "Nothing is recorded" in c and Q_R3_EN not in c, c[-300:])
        c = e.pctx("yes")
        check("2 段承認: 一度消えた後の yes は記録されない", e.stage() == "R3" and not os.path.exists(e.p(".ws", "confirm_%s.json" % slug)))
        e.pctx("Looks great, go ahead")
        e.pctx("hmm, let me see")
        e.pctx("yes")
        check("2 段承認: 間に別の入力が入ったあとの yes は記録されない（次の入力でなければ無効）", e.stage() == "R3" and not os.path.exists(e.p(".ws", "confirm_%s.json" % slug)))
        for neg in ("Looks great but change the color", "Looks good, not yet", "No, it looks wrong", "いい感じですが、直してください", "いい感じです。でも変えて"):
            e.pctx(neg)
            check("2 段承認: 否定・混ぜ物の返事は保留を立てない（%s）" % neg, e.rec("session.json").get("pending_confirm") is None)
        e.pctx("Looks great, go ahead")
        e.hook("stop", {"stop_hook_active": False, "last_assistant_message": "yes"})
        e.pre("Bash", command="echo yes")
        check("2 段承認: AI の文（Stop）・道具の呼び出しは yes にならない（記録されない）", e.stage() == "R3" and not os.path.exists(e.p(".ws", "confirm_%s.json" % slug)))
        c = e.pctx("sure")
        check("2 段承認: 表に無い返事（sure）は、保留があっても記録しない", e.stage() == "R3" and not os.path.exists(e.p(".ws", "confirm_%s.json" % slug)))
        # a normal exact word still records by itself, and clears a pending question
        e.pctx("Looks great, go ahead")
        e.pctx("looks good")
        rec = e.rec("confirm_%s.json" % slug)
        check("2 段承認: 質問のあとに決まった語を送れば、これまでどおり記録される（via なし）", e.stage() == "R4" and "via" not in rec)
        # SessionStart (a new conversation) clears the pending question
    finally:
        e.close()
    e = Env()
    try:
        slug = to_r3(e, "en")
        e.pctx("Looks great, go ahead")
        e.hook("sessionstart", {"source": "startup"})
        e.pctx("yes")
        check("2 段承認: 新しい会話（startup）で保留は消える", e.stage() == "R3" and not os.path.exists(e.p(".ws", "confirm_%s.json" % slug)))
    finally:
        e.close()

    # --- design changes after the question: nothing is recorded
    e = Env()
    try:
        slug = to_r3(e, "en")
        e.pctx("Looks great, go ahead")
        e.write("projects/%s/design/ui/brief.md" % slug, "## Purpose\nBook\n## Layout\nTop date\n## Colors\nred\n## Text\nlarge\n## States\nempty hint\n")
        c = e.pctx("yes")
        check("2 段承認(R3): 質問のあとに見た目が変わったら、yes でも記録されない", e.stage() == "R3" and not os.path.exists(e.p(".ws", "confirm_%s.json" % slug)), c[-200:])
    finally:
        e.close()

    # --- R4A, English
    e = Env()
    try:
        slug = to_r4a(e, "en")
        check("2 段承認(R4A): 前提 R4A", e.stage() == "R4A", e.stage())
        c = e.pctx("Sounds good, please go ahead")
        pend = e.rec("session.json").get("pending_confirm") or {}
        check("2 段承認(R4A en): 保留が立つ・質問は『設計と表』（en）", e.stage() == "R4A" and pend.get("kind") == "r4a" and pend.get("hash") == en.design_hash(e.root, slug)
              and ('"%s"' % Q_R4A_EN) in c and Q_R3_EN not in c, (pend, c[-300:]))
        c = e.pctx("Yes, please.")
        rec = e.rec("approval_%s.json" % slug)
        check("2 段承認(R4A en): 次の入力の yes で承認が記録され、先へ進む・記録に via=confirm と 2 つの引用・署名",
              e.stage() in ("RS", "RUN") and rec.get("via") == "confirm" and rec.get("quote") == "Sounds good, please go ahead" and rec.get("confirm_quote") == "Yes, please."
              and rec.get("hash") == en.design_hash(e.root, slug) and "_sig" in rec, (e.stage(), rec))
    finally:
        e.close()
    e = Env()
    try:
        slug = to_r4a(e, "en")
        e.pctx("Sounds good, please go ahead")
        e.write("projects/%s/design/io.json" % slug, json.dumps({"rows": [dict(IO_SCREEN["rows"][0], name="changed name"), IO_EN["rows"][1]]}))
        e.pctx("yes")
        check("2 段承認(R4A): 質問のあとに表が変わったら、yes でも記録されない", e.stage() == "R4A" and not os.path.exists(e.p(".ws", "approval_%s.json" % slug)), e.stage())
    finally:
        e.close()
    e = Env()
    try:
        slug = to_r4a(e, "en")
        e.pctx("Sounds good, please go ahead")
        e.pctx("ok")
        check("2 段承認(R4A): 次の入力が yes でなければ（ok）記録されず、新しい質問が立つだけ", e.stage() == "R4A" and not os.path.exists(e.p(".ws", "approval_%s.json" % slug)))
    finally:
        e.close()

    # --- Japanese: R3 and R4A
    e = Env()
    try:
        slug = to_r3(e, "ja")
        c = e.pctx("いい感じです。進めてください")
        check("2 段承認(R3 ja): 自然な返事は記録されず、決まった質問（ja）が出る・en の質問は出ない",
              e.stage() == "R3" and ("「%s」" % Q_R3_JA) in c and Q_R3_EN not in c and "承認としては記録していません" not in c, c[-400:])
        c = e.pctx("はい。")
        rec = e.rec("confirm_%s.json" % slug)
        check("2 段承認(R3 ja): 「はい。」（句点つき）で記録される・via と 2 つの引用", e.stage() == "R4" and rec.get("via") == "confirm"
              and rec.get("quote") == "いい感じです。進めてください" and rec.get("confirm_quote") == "はい。" and "_sig" in rec, rec)
        e.write("projects/%s/design/io.json" % slug, json.dumps(IO_SCREEN))
        c = e.pctx("いい感じです。進めてください")
        check("2 段承認(R4A ja): 質問は『設計と表』（ja）", e.stage() == "R4A" and ("「%s」" % Q_R4A_JA) in c and Q_R3_JA not in c, c[-300:])
        e.pctx("はい、お願いします")
        rec = e.rec("approval_%s.json" % slug)
        check("2 段承認(R4A ja): 「はい、お願いします」で承認が記録される", e.stage() in ("RS", "RUN") and rec.get("via") == "confirm" and rec.get("confirm_quote") == "はい、お願いします", (e.stage(), rec))
    finally:
        e.close()
    e = Env()
    try:
        slug = to_r4a(e, "ja")
        e.pctx("いい感じです。進めてください")
        c = e.pctx("お願いします")
        check("2 段承認(R4A ja): 「お願いします」だけでも、質問のあとなら記録される", e.stage() in ("RS", "RUN") and e.rec("approval_%s.json" % slug).get("via") == "confirm", e.stage())
    finally:
        e.close()
    e = Env()
    try:
        slug = to_r3(e, "ja")
        e.pctx("いい感じです。進めてください")
        c = e.pctx("まだ迷っています")
        e.pctx("はい")
        check("2 段承認(ja): 別の入力が入ったあとの「はい」は記録されない", e.stage() == "R3" and not os.path.exists(e.p(".ws", "confirm_%s.json" % slug)))
    finally:
        e.close()

    # --- a bare yes (no question before it) does not start the question; publish stays strict
    e = Env()
    try:
        slug = to_r3(e, "en")
        c = e.pctx("yes")
        check("2 段承認: 質問の前の「yes」だけでは質問を立てず、従来の note", e.rec("session.json").get("pending_confirm") is None and "send only the word: looks good" in c and Q_R3_EN not in c, c[-250:])
    finally:
        e.close()
    e = Env()
    try:
        slug = build_to_run(e)
        e.write("projects/%s/src/README.md" % slug, "# app\n")
        e.write("projects/%s/src/LICENSE" % slug, "MIT\n")
        e.run(["save", "first"])
        e.run(["save", "first"])
        e.run(["publish-check"])
        e.run(["publish-check"])
        c = e.pctx("Looks great, go ahead")
        check("2 段承認: publish には 2 段が無い（自然な返事で質問は立たず、従来の note）",
              e.rec("session.json").get("pending_confirm") is None and "To approve, send only the word: publish" in c and "Do you want me to record" not in c, c[-250:])
        c = e.pctx("yes")
        check("2 段承認: publish は yes では記録されない", not os.path.exists(e.p(".ws", "publish_ok_%s.json" % slug)) and "Recorded the user's" not in c, c[-200:])
        c = e.pctx("publish")
        check("2 段承認: publish は決まった語だけで記録される", os.path.exists(e.p(".ws", "publish_ok_%s.json" % slug)) and "Recorded the user's \"publish\"" in c, c[-200:])
    finally:
        e.close()
    # the question and the yes are the user's prompt only: the text is in the engine's tables, in both languages
    check("2 段承認: 質問は en・ja の両方の表にある（R3 と R4A）",
          all(k in _engine_template.lang._table(c).keys() for c in ("en", "ja") for k in ("confirm.q.r3", "confirm.q.r4a", "note.confirm_ask", "note.confirm_cleared", "note.recorded.via_confirm")))


def test_start_check():
    sys.path.insert(0, os.path.join(TEMPLATE, "ws"))
    import engine as en
    import lang as lg
    # a clean start: nothing is added
    e = Env()
    try:
        c = e.ctx("sessionstart", {"source": "startup"})
        check("起動の点検: 問題が無いときは何も足さない（見出しも Full check も出ない）", "Problems found" not in c and "Full check" not in c and "- " not in c.split("place:")[0], c[:300])
        c_ja = Env()
        c_ja.env["CREATECODEBOX_LANG"] = "ja"
        cj = c_ja.ctx("sessionstart", {"source": "startup"})
        check("起動の点検（ja）: 問題が無いときは何も足さない", "問題が見つかりました" not in cj and "全部の点検" not in cj, cj[:300])
        c_ja.close()
        # one problem: a CLAUDE.md in a folder above
        up = os.path.join(e.tmp, "CLAUDE.md")
        open(up, "w").write("x\n")
        c = e.ctx("sessionstart", {"source": "startup"})
        lines = [l for l in c.splitlines() if l.startswith("- ")]
        check("起動の点検: 上の CLAUDE.md を 1 行（何が悪いか + 直し方）で出し、最後に Full check の行", len(lines) == 1 and up in lines[0] and "Fix:" in lines[0]
              and c.rstrip().splitlines()[-1] == "Full check: bash ws/bin/ws.sh doctor", c[-500:])
        os.remove(up)
        # a tampered approval: the stage does not move, the line says how to go on
        slug = to_r3(e, "en")
        e.pctx("looks good")
        e.write("projects/%s/design/io.json" % slug, json.dumps(IO_SCREEN))
        e.pctx("approve")
        rec = e.rec("approval_%s.json" % slug)
        rec["hash"] = "0" * 64
        json.dump(rec, open(e.p(".ws", "approval_%s.json" % slug), "w"))
        c = e.ctx("sessionstart", {"source": "resume"})
        lines = [l for l in c.splitlines() if l.startswith("- ")]
        check("起動の点検: 書き換えた承認の記録 → 段が戻ることと、承認の語を送り直す直し方が 1 行で出る・警告は二重に出ない",
              len(lines) == 1 and "approval" in lines[0] and "`approve`" in lines[0] and "signature mismatch" not in c, c[-600:])
        out = e.run(["doctor"])[1]
        check("doctor: 書き換えた記録の行と直し方が出る（起動の行と同じ文）", "WARN" in out and "`approve` again" in out, out)
        # a project with a broken record that has no safe re-do: only `resign` (the user's word), or the issue form
        e.prompt("approve")
        e.run(["schedule-init"])
        sc = e.rec("schedule_%s.json" % slug)
        sc["rows"][0]["status"] = "done"
        json.dump(sc, open(e.p(".ws", "schedule_%s.json" % slug), "w"))
        c = e.ctx("sessionstart", {"source": "resume"})
        lines = [l for l in c.splitlines() if l.startswith("- ")]
        check("起動の点検: 書き換えた schedule は、resign（利用者の言葉）と、変えていないなら resign しない・フォームの案内（署名を飛ばす直し方は出さない）",
              len(lines) == 1 and "`resign`" in lines[0] and "do not resign" in lines[0] and "issues/new/choose" in lines[0], lines)
        sc2 = e.rec("st_%s.json" % slug) if os.path.exists(e.p(".ws", "st_%s.json" % slug)) else None
        e.write(".ws/st_%s.json" % slug, "{broken")
        c = e.ctx("sessionstart", {"source": "resume"})
        lines = [l for l in c.splitlines() if l.startswith("- ")]
        check("起動の点検: 記録が 2 つ以上こわれているときは 1 行にまとめる（件数つき）", len(lines) == 1 and "2 saved records" in lines[0], lines)
    finally:
        e.close()
    # Japanese
    e = Env()
    try:
        e.env["CREATECODEBOX_LANG"] = "ja"
        up = os.path.join(e.tmp, "CLAUDE.md")
        open(up, "w").write("x\n")
        c = e.ctx("sessionstart", {"source": "startup"})
        lines = [l for l in c.splitlines() if l.startswith("- ")]
        check("起動の点検（ja）: 見出し・1 行（直し方つき）・全部の点検の行が ja", "問題が見つかりました" in c and len(lines) == 1 and up in lines[0] and "直し方:" in lines[0]
              and c.rstrip().splitlines()[-1] == "全部の点検: bash ws/bin/ws.sh doctor", c[-500:])
    finally:
        e.close()
    # at most 3 lines, and the count of the rest (in-process: the checks are replaced by a fixed list)
    e = Env()
    try:
        saved = en.ancestor_claude_files
        en.ancestor_claude_files = lambda root: ["/a/CLAUDE.md", "/b/CLAUDE.md", "/c/CLAUDE.md", "/d/CLAUDE.md", "/e/CLAUDE.md"]
        try:
            lg.use("en")
            blk = en.start_problem_block(e.root)
            lines = [l for l in blk.splitlines() if l.startswith("- ")]
            check("起動の点検: 問題が 5 つでも出すのは 3 行まで・残りの件数が Full check の行に付く", len(lines) == 3 and "/d/CLAUDE.md" not in blk
                  and blk.splitlines()[-1] == "More problems not shown: 2. Full check: bash ws/bin/ws.sh doctor", blk)
            lg.use("ja")
            blk = en.start_problem_block(e.root)
            check("起動の点検（ja）: 3 行まで・残りの件数", len([l for l in blk.splitlines() if l.startswith("- ")]) == 3 and "ほかに問題が 2 件" in blk.splitlines()[-1], blk)
            en.ancestor_claude_files = lambda root: []
            lg.use("en")
            check("起動の点検: 問題が 0 なら start_problem_block は空の文字列", en.start_problem_block(e.root) == "")
        finally:
            en.ancestor_claude_files = saved
            lg.use(None)
    finally:
        e.close()
    # every message exists in both languages, in short plain lines, without the words the style guide forbids
    from lang import en as lang_en, ja as lang_ja
    keys = [k for k in lang_en.MESSAGES if k.startswith(("problem.", "confirm.q."))]
    check("起動の点検: problem.* と confirm.q.* の文は en・ja の両方にある", keys and all(k in lang_ja.MESSAGES for k in keys), [k for k in keys if k not in lang_ja.MESSAGES])
    bad = [k for k in keys if re.search(r"(?i)\b(easy|easily|anyone|safe|safely|beginner|just|simple)\b", lang_en.MESSAGES[k])
           or re.search(r"簡単|誰でも|安全|初心者", lang_ja.MESSAGES[k])]
    check("起動の点検: 使わない言葉（easy・anyone・safe・beginner・簡単・誰でも・安全・初心者）が入っていない", not bad, bad)



def test_c3_parse():
    sys.path.insert(0, os.path.join(TEMPLATE, "ws"))
    import engine as en
    td = tempfile.mkdtemp(prefix="ccb_pp_")
    try:
        def parse(text, raw=None):
            d = os.path.join(td, "projects", "p")
            os.makedirs(d, exist_ok=True)
            with open(os.path.join(d, "PROJECT.md"), "wb") as f:
                f.write(raw if raw is not None else text.encode("utf-8"))
            return en.parse_project(td, "p")
        cases = [("goal_type: self", "self"), ("- goal_type: self", "self"), ("* goal_type: self", "self"), ("**goal_type**: self", "self"),
                 ("goal_type：self", "self"), ("- **goal_type:** self", "self"), ("goal_type: [self]", "self"), ("goal_type: just for me (self)", "self"),
                 ("  - goal_type:  `public-paid`", "public-paid"), ("goal_type: 公開有料", "public-paid"), ("goal_type: Public, free", "public-free"),
                 ("goal_type: not sure yet", "unknown"), ("goal_type: 自分用", "self")]
        bad = [(t, parse(t).get("goal_type")) for t, want in cases if parse(t).get("goal_type") != want]
        check("C3: goal_type の書式ゆれ・表示名・括弧・旧い日本語の値を記号に（%d 例）" % len(cases), not bad, bad)
        ui = [("has_ui: yes", "yes"), ("has_ui: Y", "yes"), ("has_ui: true", "yes"), ("has_ui: はい", "yes"), ("has_ui: no", "no"), ("has_ui: N", "no"),
              ("has_ui: false", "no"), ("has_ui: いいえ", "no"), ("- has_ui: **No**", "no")]
        bad = [(t, parse(t).get("has_ui")) for t, want in ui if parse(t).get("has_ui") != want]
        check("C3: has_ui は yes/no/y/n/true/false/はい/いいえ", not bad, bad)
        check("C3: # Name: と # 名前: の両方", parse("# Name: Foo\n").get("name") == "Foo" and parse("# 名前: 家計簿\n").get("name") == "家計簿")
        f = parse("", raw="what: 支出を入れて合計を見る家計簿\n".encode("cp932"))
        check("C3: read_text は cp932 の PROJECT.md も読める", f.get("what") == "支出を入れて合計を見る家計簿", f)
        f = parse("", raw=b"\xef\xbb\xbfwhat: with a BOM here\n")
        check("C3: read_text は BOM つき UTF-8 を読める", f.get("what") == "with a BOM here", f)
        f = parse("", raw=b"what: caf\xe9 au lait\n")
        check("C3: read_text は最後に latin-1 に落ちる（落ちずに読む）", "caf" in f.get("what", ""), f)
        check("C3: PLACEHOLDERS に en（tbd・n/a・unknown・todo・?）", all(not en.filled(x) for x in ("tbd", "n/a", "unknown", "todo", "?", "TBD", "ToDo")) and en.filled("a real answer"))
    finally:
        shutil.rmtree(td, ignore_errors=True)


def test_v02_fixture():
    e = Env()
    try:
        fx = os.path.join(HERE, "fixtures", "v02_project")
        shutil.copytree(os.path.join(fx, "projects", "01_kakeibo"), e.p("projects", "01_kakeibo"))
        shutil.copytree(os.path.join(fx, "dot_ws"), e.p(".ws"))
        out = e.run(["status"])[1]
        check("0.2 の fixture（日本語の値・design/schedule.json）が RUN のまま読める", e.stage() == "RUN" and "signature mismatch" not in out, out)
        check("0.2 の fixture: 旧い記録は署名され、schedule と st は .ws/ に移り、schema 3", os.path.isfile(e.p(".ws", "schedule_01_kakeibo.json"))
              and os.path.isfile(e.p(".ws", "st_01_kakeibo.json")) and not os.path.isfile(e.p("projects", "01_kakeibo", "design", "schedule.json"))
              and "_sig" in e.rec("approval_01_kakeibo.json") and e.rec("state.json").get("schema") == 3)
        check("0.2 の fixture: sketch は要求されない（io.json があるプロジェクト）", "Show the prototype" not in out)
        check("0.2 の fixture: 旧い記録の進捗（合格 1 件）が残る", e.rec("st_01_kakeibo.json")["rows"][0]["status"] == "pass")
        c = e.ctx("sessionstart", {"source": "startup"})
        check("0.2 の fixture: 起動で自動 select（既存 1 つ）・RUN の規則", "Continuing" in c and "RUN" in c, c[:200])
        out = e.run(["lint"])[1]
        check("0.2 の fixture: 旧い kind（ファイル）で lint が通る", "passed" in out, out)
        rc, out = e.run(["render"])
        check("0.2 の fixture: render できる（io.html・schedule.html・systemtest.html）", rc == 0 and "systemtest.html" in out, out)
    finally:
        e.close()


def test_stage_misc():
    # D1 first turn read-only
    e = Env()
    try:
        slug = build_to_run(e)
        e.prompt("continue")
        e.prompt("ok")
        check("(前提) RUN で src に書ける", e.pre("Write", file_path=e.p("projects", slug, "src", "x.py"), content="print(1)") is None)
        e.ctx("sessionstart", {"source": "startup"})
        check("D1: 新しい会話の 0 回目（入力前）も src は読み取り専用", e.pre("Write", file_path=e.p("projects", slug, "src", "x.py"), content="print(1)") is not None)
        c = e.pctx("add a feature please")
        r = e.pre("Write", file_path=e.p("projects", slug, "src", "x.py"), content="print(1)")
        check("D1: 既存 1 つは自動 select・最初のターンは src に書けない（理由の文）", "Continuing App" in c and r is not None and "First turn is read-only. Say what you want; I'll start writing from your next message." in r, (c[:200], r))
        check("D1: 最初のターンは書き込む Bash も止まる（読むだけは通る）", e.pre("Bash", command="python3 x.py") is not None and e.pre("Bash", command="ls") is None)
        e.run(["task", "none"])  # the message adds nothing to the task board: the design folder is open in the first turn
        check("D1: 最初のターンでも ws.sh と design/ への書き込みは通る", e.pre("Bash", command="bash ws/bin/ws.sh status") is None
              and e.pre("Write", file_path=e.p("projects", slug, "design", "x.md"), content="x") is None)
        e.pctx("go on")
        check("D1: 2 回目の入力から src に書ける", e.pre("Write", file_path=e.p("projects", slug, "src", "x.py"), content="print(1)") is None)
    finally:
        e.close()
    # open
    e = Env()
    try:
        e.env["CREATECODEBOX_OPEN_DRY_RUN"] = "1"
        e.hook("sessionstart", {"source": "startup"})
        e.prompt("make a thing")
        check("open: プロジェクトを選ぶ前は使えない", e.run(["open", "x.html"])[0] == 2)
        e.run(["new", "app", "--name", "App", "--quote", "make a thing"])
        e.write("projects/01_app/design/ui/sketch.html", SKETCH)
        e.write("projects/01_app/src/index.html", "<html></html>")
        e.write("projects/01_app/src/notes.txt", "x")
        e.write("projects/01_app/knowledge/a.html", "<html></html>")
        rc, out = e.run(["open", "projects/01_app/design/ui/sketch.html"])
        check("open: R1 から design/ の html を開ける（sketch）", rc == 0 and "Would open: projects/01_app/design/ui/sketch.html" in out, out)
        check("open: src/ の html も開ける", e.run(["open", "projects/01_app/src/index.html"])[0] == 0)
        check("open: knowledge/・README・.ws は断る（design/ と src/ の外）", e.run(["open", "projects/01_app/knowledge/a.html"])[0] == 1
              and e.run(["open", "README.md"])[0] == 1 and e.run(["open", ".ws/state.json"])[0] == 1)
        check("open: 拡張子が html/png/svg/pdf 以外は断る", e.run(["open", "projects/01_app/src/notes.txt"])[0] == 1)
        os.symlink(e.p("README.md"), e.p("projects", "01_app", "design", "link.html"))
        check("open: realpath で判定する（design/ の中の symlink で外を指しても断る）", e.run(["open", "projects/01_app/design/link.html"])[0] == 1)
        check("open: hook は ws.sh open を通す", e.pre("Bash", command="bash ws/bin/ws.sh open projects/01_app/design/ui/sketch.html") is None)
        check("write_zone: design/ui/sketch.html は R1 から書ける", e.pre("Write", file_path=e.p("projects", "01_app", "design", "ui", "sketch.html"), content="x") is None)
    finally:
        e.close()
    # select summary
    e = Env()
    try:
        build_to_run(e)
        e.hook("sessionstart", {"source": "startup"})
        e.run(["new", "two", "--name", "Two", "--quote", "x"])
        e.hook("sessionstart", {"source": "startup"})
        e.prompt("let us continue")
        e.prompt("the first one")
        e.run(["select", "01_app", "--quote", "the first one"])
        e.run(["render"])
        rc, out = e.run(["select", "01_app", "--quote", "the first one"])
        check("C4: select の戻りに Last time: up to <段>. Next: … Look at: …", rc == 0 and "Last time: up to RUN." in out and "Look at: projects/01_app/design/schedule.html" in out, out)
    finally:
        e.close()


def test_harden_lists():
    import engine as en
    e = Env()
    try:
        en.apply_harden(e.root, True)
        d = json.load(open(e.p(".claude", "settings.local.json"), encoding="utf-8"))["sandbox"]["filesystem"]
        need = ["~/**/.env", "~/**/.env.local", "~/**/.env.development", "~/**/.env.production", "~/**/.env.test", "~/**/.env.staging", "~/**/.env.*.local"]
        check("E6: denyRead は .env 系を列挙する（.env.example は読める・denyWrite は既定で入らない）",
              all(n in d["denyRead"] for n in need) and "~/**/.env.*" not in d["denyRead"] and "denyWrite" not in d, d)
        en.apply_harden(e.root, True, with_denywrite=True)
        d = json.load(open(e.p(".claude", "settings.local.json"), encoding="utf-8"))["sandbox"]["filesystem"]
        check("E6: --with-denywrite の時だけ filesystem.denyWrite（.ws・ws・.claude）が入る（任意・未確認の形）", d.get("denyWrite") == [".ws", "ws", ".claude"], d)
        en.apply_harden(e.root, False)
    finally:
        e.close()


def test_stop():
    e = Env()
    try:
        e.hook("sessionstart", {"source": "startup"})
        e.prompt("make a thing")
        e.run(["new", "a", "--name", "A", "--quote", "make a thing"])
        e.prompt("another")
        e.run(["new", "b", "--name", "B", "--quote", "another"])
        e.hook("sessionstart", {"source": "startup"})
        check("(前提) 既存が 2 つの新しい会話は R0", e.stage() == "R0")
        e.prompt("hi")
        out = e.hook("stop", {"last_assistant_message": "Sure, I can help with many things."})
        check("C5: R0 の Stop は、続きか新規かを聞いていない返事を block する（last_assistant_message）", '"block"' in out, out)
        out = e.hook("stop", {"last_assistant_message": "Do you want to continue 01_a or start a new one?"})
        check("C5: continue / new を含む返事は block しない", out == "", out)
        out = e.hook("stop", {"last_assistant_message": "続きにしますか、新規にしますか"})
        check("C5: 続き / 新規 を含む返事は block しない", out == "", out)
        tp = os.path.join(e.tmp, "t.jsonl")
        open(tp, "w").write(json.dumps({"type": "user", "message": {"role": "user", "content": "hi"}}) + "\n" +
                            json.dumps({"type": "assistant", "message": {"role": "assistant", "content": [{"type": "text", "text": "Hello there."}]}}) + "\n")
        out = e.hook("stop", {"transcript_path": tp})
        check("C5: last_assistant_message が無ければ transcript の最後の assistant を使う", '"block"' in out, out)
        out = e.hook("stop", {"transcript_path": os.path.join(e.tmp, "none.jsonl")})
        check("C5: 読めなければ許可（fail-open）", out == "", out)
        out = e.hook("stop", {"last_assistant_message": "Hello", "stop_hook_active": True})
        check("C5: stop_hook_active のときは block しない", out == "", out)
    finally:
        e.close()


def test_safety_commands():
    e = Env()
    try:
        slug = build_to_run(e)
        e.prompt("a")
        e.prompt("b")
        # excludes + doctor
        claude_md = os.path.join(e.tmp, "CLAUDE.md")
        open(claude_md, "w").write("outside rules")
        out = e.run(["doctor"])[1]
        check("H: doctor が、上のフォルダの CLAUDE.md を警告する", "WARN" in out and claude_md in out and "excludes add" in out, out)
        c = e.ctx("sessionstart", {"source": "startup"})
        check("H: SessionStart も警告する", claude_md in c, c[-300:])
        check("H: excludes add は、利用者の入力にパスが無いと断る", e.run(["excludes", "add", claude_md])[0] == 1)
        e.prompt("please exclude %s" % claude_md)
        check("H: ancestor でない CLAUDE.md は断る", e.run(["excludes", "add", os.path.join(e.root, "CLAUDE.md")])[0] == 1)
        rc, out = e.run(["excludes", "add", claude_md])
        cfg = json.load(open(e.p(".claude", "settings.local.json"), encoding="utf-8"))
        check("H: excludes add は settings.local.json の claudeMdExcludes に足し、署名つきの記録も残す", rc == 0 and claude_md in cfg["claudeMdExcludes"]
              and "_sig" in e.rec("excludes.json"), out)
        # rules import
        e.write("projects/%s/src/RULES.md" % slug, "# rules\nUse tabs.\n")
        check("D2: rules import は、パスが利用者の入力に無いと断る", e.run(["rules", "import", "projects/%s/src/RULES.md" % slug])[0] == 1)
        e.prompt("import projects/%s/src/RULES.md please" % slug)
        rc, out = e.run(["rules", "import", "projects/%s/src/RULES.md" % slug])
        t = open(e.p("projects", slug, "knowledge", "imported_rules.md"), encoding="utf-8").read() if rc == 0 else ""
        check("D2: rules import は knowledge/imported_rules.md に複製し、先頭に imported by the user on <日付> from <path>",
              rc == 0 and re.match(r"^imported by the user on \d{4}-\d\d-\d\d from projects/%s/src/RULES.md\n" % re.escape(slug), t) and "Use tabs." in t, (out, t[:100]))
        e.write("projects/%s/src/KEY.md" % slug, "k = '%s'\n" % fake_secret("sklive"))
        e.prompt("import projects/%s/src/KEY.md" % slug)
        check("D2: 鍵の走査を通らない物は取り込まない", e.run(["rules", "import", "projects/%s/src/KEY.md" % slug])[0] == 1)
        e.write("projects/%s/src/BIG.md" % slug, "x" * 70000)
        e.prompt("import projects/%s/src/BIG.md" % slug)
        check("D2: 64KB を超える物は取り込まない", e.run(["rules", "import", "projects/%s/src/BIG.md" % slug])[0] == 1)
        e.write("projects/%s/knowledge/NOTE.md" % slug, "x")
        e.prompt("import projects/%s/knowledge/NOTE.md" % slug)
        check("D2: src/ と ~/.claude/CLAUDE.md の外は取り込まない", e.run(["rules", "import", "projects/%s/knowledge/NOTE.md" % slug])[0] == 1)
        os.makedirs(os.path.join(e.home, ".claude"))
        open(os.path.join(e.home, ".claude", "CLAUDE.md"), "w").write("my global rules\n")
        hp = os.path.join(e.home, ".claude", "CLAUDE.md")
        e.prompt("import %s" % hp)
        check("D2: ~/.claude/CLAUDE.md は取り込める", e.run(["rules", "import", hp])[0] == 0)
        # secret allow
        srcd = e.p("projects", slug, "src")
        subprocess.run(["git", "-C", srcd, "init", "-q"], capture_output=True)
        leak = "K = '%s'\n" % fake_secret("sklive")
        open(os.path.join(srcd, "leak.py"), "w").write(leak)
        for a in (["add", "-A"], ["-c", "user.name=t", "-c", "user.email=t@t.invalid", "commit", "-q", "-m", "x"]):
            subprocess.run(["git", "-C", srcd] + a, capture_output=True)
        res = e.engine_call("print(engine.history_has_key(%r, root))" % srcd)
        m = re.search(r"([0-9a-f]{7,8}):leak\.py:1 \(stripe, fingerprint ([0-9a-f]{12})\)", res)
        check("E3: 履歴の検出が commit:path:行 と指紋を出す", bool(m) and fake_secret("sklive") not in res, res[:300])
        fp = m.group(2) if m else "0" * 12
        check("E3: secret allow は、指紋が利用者の入力に無いと断る", e.run(["secret", "allow", fp])[0] == 1)
        e.prompt("the fingerprint %s is a false alarm" % fp)
        rc, out = e.run(["secret", "allow", fp])
        res = e.engine_call("print(engine.history_has_key(%r, root))" % srcd)
        check("E3: secret allow の後は、その指紋の検出が消える（署名つきの secret_allow.json）", rc == 0 and res.strip().startswith("(False") and "_sig" in e.rec("secret_allow.json"), (out, res))
        # D3 save on an adopted repo is covered in the adopt test
    finally:
        e.close()


def test_new_entrance_and_render():
    e = Env()
    try:
        slug = build_to_run(e)
        rc, out = e.run(["render"])
        html = open(e.p("projects", slug, "design", "schedule.html"), encoding="utf-8").read()
        check("render: 署名（_sig）を HTML に埋め込まない", rc == 0 and "_sig" not in html and "_sig" not in open(e.p("projects", slug, "design", "io.html"), encoding="utf-8").read(), out)
        check("render: design/ に置かれるのは HTML だけ（json の記録は .ws/）", not [n for n in os.listdir(e.p("projects", slug, "design")) if n.endswith(".json") and n != "io.json"])
        check("render の雛形が英語の記号（screen・file …）の kind を受ける（KIND_ALIAS）と by: run を表示する",
              "KIND_ALIAS[str(r.kind).toLowerCase()]" in open(e.p("ws", "render", "io.template.html"), encoding="utf-8").read()
              and "run: " in open(e.p("ws", "render", "systemtest.template.html"), encoding="utf-8").read())
    finally:
        e.close()
    # R1 todo wording, R1 with symbols
    e = Env()
    try:
        e.hook("sessionstart", {"source": "startup"})
        e.prompt("make a thing")
        e.run(["new", "a", "--name", "A", "--quote", "make a thing"])
        out = e.run(["status"])[1]
        check("P1: R1 の todo は goal と what（goal: self / share / unknown (share → friends-only / public-free / public-paid)）", "goal: self / share / unknown (share → friends-only / public-free / public-paid)" in out and "what:" in out, out)
        e.set_fields("01_a", goal_type="- unclear -", what="x")
        out = e.run(["status"])[1]
        check("C3: 形が違う値のとき、todo に key: value の書き方（no bullets or brackets）", e.stage() == "R1" and "no bullets or brackets" in out, out)
        c = e.pctx("hello")
        check("R1 の規則文（英語）に 3 択・sketch・最初の質問が入る", "just for me" in c and "data-ccb=\"sketch\"" in c and "What's the most wrong thing here?" in c, c[:300])
    finally:
        e.close()


PATCH_SRC = "*** Begin Patch\n*** Add File: projects/%s/src/a.py\n+x\n*** End Patch"


def sorted_pending(e):
    t = e.rec("session.json").get("triage")
    return bool(t) and t.get("n") == e.rec("session.json").get("prompts")


def test_tasks_triage():
    en = _engine_template
    triv = ["yes", "はい", "1 2 3", "continue", "続き", "ok", "OK!", "looks good", "approve", "承認します", "publish", "この形で", "1, 2 pass", "1-3 pass",
            "all pass", "Sure, go ahead", "はい、お願いします", "いいですね", "new", "新規", "全部 OK", "yes please"]
    non = ["yes, and add a CSV export", "add an export button", "ok, now also add a dark mode", "3 fail", "CSVも出して", "いいですね、CSV出力も追加して",
           "hello", "the total is wrong", "期限は 11 月 5 日です", "ok but change the color", "2 pass 3 fail"]
    check("タスク: 承認・はい・番号・続きは「自明」と見る（%d 例）" % len(triv), all(en.trivial_prompt(t) for t in triv), [t for t in triv if not en.trivial_prompt(t)])
    check("タスク: 要望・困りごと・日付を含む入力は自明でない（yes, and add… も）", not any(en.trivial_prompt(t) for t in non), [t for t in non if en.trivial_prompt(t)])
    e = Env()
    try:
        slug = build_to_run(e)
        for w in ("continue", "ok"):
            e.prompt(w)
        miss = []
        for w in ("yes", "はい", "1 2 3", "continue", "続き"):
            e.prompt(w)
            if sorted_pending(e):
                miss.append(w)
        check("タスク: RUN で yes・はい・1 2 3・continue・続き は triage を立てない", not miss, miss)
        c = e.pctx("Please add an export to CSV by 2026-11-05")
        check("タスク: RUN の新しい要望で triage が立つ（session.json の triage = n と quote）", sorted_pending(e) and e.rec("session.json")["triage"]["quote"].startswith("Please add"), e.rec("session.json"))
        check("タスク: triage の行が文脈に出る（task add と task none）", "task add" in c and "task none" in c, c[-400:])
        r = e.pre("Edit", file_path=e.p("projects", slug, "src", "a.py"), old_string="a", new_string="b")
        check("タスク: triage 中は Edit を止める（deny.triage）", r is not None and "task none" in r, r)
        check("タスク: triage 中は Write・MultiEdit・NotebookEdit・apply_patch も止める",
              all(e.pre(t, **ti) is not None and "task none" in e.pre(t, **ti) for t, ti in (
                  ("Write", {"file_path": e.p("projects", slug, "src", "a.py"), "content": "x"}),
                  ("MultiEdit", {"file_path": e.p("projects", slug, "src", "a.py"), "edits": [{"old_string": "a", "new_string": "b"}]}),
                  ("NotebookEdit", {"notebook_path": e.p("projects", slug, "src", "a.ipynb"), "new_source": "x"}),
                  ("apply_patch", {"command": PATCH_SRC % slug}))))
        check("タスク: triage 中は書き込む Bash を止め、読むだけ・ws.sh status は通す",
              e.pre("Bash", command="python3 x.py") is not None and e.pre("Bash", command="ls") is None and e.pre("Bash", command="bash ws/bin/ws.sh status") is None)
        check("タスク: triage 中は ws.sh mark・save など task 以外で書く物も止める", e.pre("Bash", command="bash ws/bin/ws.sh mark S-02 done --evidence abcdefghij") is not None
              and e.pre("Bash", command="bash ws/bin/ws.sh save note") is not None)
        check("タスク: ws.sh task add は triage 中でも通る（他の検査も通る）", e.pre("Bash", command='bash ws/bin/ws.sh task add "Export to CSV" --due 2026-11-05') is None
              and e.pre("Bash", command="bash ws/bin/ws.sh task none") is None and e.pre("Bash", command="bash ws/bin/ws.sh tasks gantt --text") is None)
        check("タスク: mcp の書き込み名の道具も止める", e.pre("mcp__fs__write_file", path="x") is not None and e.pre("mcp__docs__search", q="x") is None)
        out = e.hook("stop", {"last_assistant_message": "done"})
        check("タスク: Stop は、未整理なら 1 回だけ block する（stop.triage）", '"block"' in out and "task none" in out, out)
        out = e.hook("stop", {"last_assistant_message": "done"})
        check("タスク: 2 回目の Stop は通す（無限ループにしない）", out == "", out)
        e.pctx("Please also add a dark mode")
        out = e.hook("stop", {"last_assistant_message": "done", "stop_hook_active": True})
        check("タスク: stop_hook_active のときは block しない", out == "", out)
        rc, out = e.run(["task", "none"])
        check("タスク: task none で triage が消え、Edit が通る", rc == 0 and not sorted_pending(e)
              and e.pre("Edit", file_path=e.p("projects", slug, "src", "a.py"), old_string="a", new_string="b") is None, out)
        e.pctx("Please add one more thing")
        out = e.hook("stop", {"last_assistant_message": "done"})
        e.run(["task", "add", "One more thing"])
        check("タスク: task add でも triage が消える（Stop は通る）", not sorted_pending(e) and e.hook("stop", {"last_assistant_message": "done"}) == "")
    finally:
        e.close()
    # before approval nothing is enforced
    e = Env()
    try:
        e.hook("sessionstart", {"source": "startup"})
        e.prompt("make a small tool")
        e.run(["new", "app", "--name", "App", "--quote", "make a small tool"])
        e.prompt("continue")
        c = e.pctx("I want it by 2026-11-30, and add a dark mode later")
        check("タスク: R1 では強制しない（triage なし・Edit は通る）・1 行の注意だけ出る",
              e.stage() == "R1" and not sorted_pending(e) and "task add" in c and "task none" not in c
              and e.pre("Edit", file_path=e.p("projects", "01_app", "PROJECT.md"), old_string="what:", new_string="what:") is None, c[-300:])
        check("タスク: R1 の Stop は止めない", e.hook("stop", {"last_assistant_message": "ok"}) == "")
        check("タスク: 承認の前の tasks は『Before the build』の見出し", "Before the build:" in e.run(["tasks"])[1])
    finally:
        e.close()


def test_tasks_commands():
    e = Env()
    try:
        rc, out = e.run(["task", "add", "x"])
        check("タスク: プロジェクトが無いと task add は断る（選ぶよう案内）", rc == 2 and "No project is chosen" in out, out)
        slug = build_to_run(e)
        e.prompt("continue")
        e.pctx("Please add an export to CSV by 2026-11-05")
        rc, out = e.run(["task", "add", "Export to CSV", "--due", "2026-11-05"])
        check("タスク: task add は新しい id を出す（T-01）・既定の種類は req", rc == 0 and "T-01 [req]" in out, out)
        rec = e.rec("tasks_%s.json" % slug)
        it = rec["items"][0]
        check("タスク: 記録は署名つき・from に入力の番号と文の頭・既定は仮の日付",
              "_sig" in rec and it["from"].startswith("prompt %d: Please add an export" % e.rec("session.json")["prompts"]) and it["tentative"] is True
              and it["status"] == "todo" and it["due"] == "2026-11-05" and it["start"] == "", it)
        check("タスク: task add の出力の最後は『Schedule updated: <絶対パス>』", out.strip().splitlines()[-1] == "Schedule updated: " + os.path.realpath(e.p("projects", "schedule.html")), out)
        for args, want in ((["add", "x", "--kind", "bug"], "one of req"), (["add", "x", "--due", "2026-13-40"], "YYYY-MM-DD"), (["add", "x", "--start", "2026-11-09", "--due", "2026-11-01"], "after the due"),
                           (["add", ""], "one short line"), (["add", "x", "--zzz", "1"], "usage"), (["set", "T-01", "finished"], "one of todo"),
                           (["set", "T-09", "doing"], "no item"), (["date", "T-01", "2026/11/05", "-"], "YYYY-MM-DD")):
            rc, out = e.run(["task"] + args)
            check("タスク: 誤りは断る（%s）" % " ".join(args[:3]), rc != 0 and want in out, out)
        rc, out = e.run(["task", "add", "Fix the total", "--kind", "issue", "--start", "2026-11-01", "--due", "2026-11-03", "--fixed"])
        check("タスク: --fixed は仮でなく確定（kind issue も受ける）", rc == 0 and e.rec("tasks_%s.json" % slug)["items"][1]["tentative"] is False and "T-02 [issue]" in out, out)
        rc, out = e.run(["task", "set", "T-01", "done"])
        check("タスク: done は --how が要る", rc == 1 and "--how" in out, out)
        rc, out = e.run(["task", "set", "T-01", "done", "--how", "short"])
        check("タスク: --how は 8 字以上", rc == 1, out)
        rc, out = e.run(["task", "set", "T-01", "hold"])
        check("タスク: hold には理由（--note）が要る", rc == 1 and "--note" in out, out)
        rc, out = e.run(["task", "set", "T-01", "dropped"])
        check("タスク: dropped にも理由が要る", rc == 1, out)
        rc, out = e.run(["task", "set", "T-01", "dropped", "--note", "the user withdrew it"])
        check("タスク: 理由があれば dropped にできる（取り下げ）・盤から消える", rc == 0 and "T-01 is now dropped" in out and "T-01" not in e.run(["tasks"])[1], out)
        rc, out = e.run(["task", "set", "T-02", "done", "--how", "ran it and the total showed 820"])
        check("タスク: --how があれば done にできる（how が残る）", rc == 0 and e.rec("tasks_%s.json" % slug)["items"][1]["how"].startswith("ran it"), out)
        rc, out = e.run(["task", "add", "Third", "--kind", "todo"])
        check("タスク: id は使い回さない（T-03）", "T-03 [todo]" in out, out)
        rc, out = e.run(["task", "date", "T-03", "2026-11-01", "2026-11-05", "--fixed"])
        check("タスク: task date --fixed は確定・- は消す", rc == 0 and e.rec("tasks_%s.json" % slug)["items"][2]["tentative"] is False
              and e.run(["task", "date", "T-03", "-", "-"])[0] == 0 and e.rec("tasks_%s.json" % slug)["items"][2]["due"] == "", out)
        # rows of the build schedule
        rc, out = e.run(["task", "set", "S-02", "done"])
        check("タスク: S 行は mark の規則（証拠が要る）", rc == 1 and "--evidence" in out, out)
        rc, out = e.run(["task", "set", "S-02", "dropped", "--note", "x"])
        check("タスク: S 行は dropped にできない", rc == 1, out)
        rc, out = e.run(["task", "set", "S-01", "done", "--how", "ran it once and the folder is ready"])
        check("タスク: S 行を task set で done にできる（schedule の記録に入る）", rc == 0 and [r for r in e.rec("schedule_%s.json" % slug)["rows"] if r["id"] == "S-01"][0]["status"] == "done", out)
        rc, out = e.run(["task", "date", "S-03", "2026-11-02", "2026-11-04"])
        row = [r for r in e.rec("schedule_%s.json" % slug)["rows"] if r["id"] == "S-03"][0]
        check("タスク: S 行の日付が schedule の記録に入る（仮）・schedule の署名は有効のまま", rc == 0 and row["start"] == "2026-11-02" and row["due"] == "2026-11-04" and row["tentative"] is True
              and e.stage() == "RUN" and "signature" not in e.run(["status"])[1], (out, row))
        board = e.run(["tasks"])[1]
        check("タスク: tasks は目的・作る前の不足・残りの S 行・残りの項目を出す", "Goal: a small tool" in board and "To finish the first version:" in board and "S-03 [build, todo]" in board
              and "S-01" not in board and "T-03 [todo, todo]" in board, board)
        check("タスク: RUN の tasks は『To finish the first version』の見出し（Before the build ではない）",
              "To finish the first version: System test" in board and "Before the build" not in board, board)
        # a changed record
        path = e.p(".ws", "tasks_%s.json" % slug)
        rec = json.load(open(path))
        rec["items"][0]["title"] = "changed by hand"
        json.dump(rec, open(path, "w"))
        rc, out = e.run(["task", "add", "after the change"])
        check("タスク: 書き換えられた記録は上書きしない（task add は断る）", rc == 1 and "changed outside" in out, out)
        c = e.ctx("sessionstart", {"source": "resume"})
        check("タスク: 書き換えられた記録は起動の点検で知らせる（tasks_ の名前）", "tasks_%s.json" % slug in c, c[-400:])
        check("タスク: doctor も知らせる", "tasks_%s.json" % slug in e.run(["doctor"])[1] or "signature" in e.run(["doctor"])[1].lower())
        e.prompt("I changed it myself. Please resign")
        e.run(["resign"])
        rc, out = e.run(["task", "add", "after resign"])
        check("タスク: resign（利用者の言葉）のあとは書ける（resign が tasks_ も覆う）", rc == 0, out)
    finally:
        e.close()


def test_schedule_dates():
    import datetime
    today = datetime.date.today()
    d = lambda n: (today + datetime.timedelta(days=n)).isoformat()
    e = Env()
    try:
        slug = build_to_run(e)
        rows = e.rec("schedule_%s.json" % slug)["rows"]
        check("予定表: 新しい S 行に仮の日付が付く（先頭は今日・次は翌日から・各 1 日）",
              [(r["start"], r["due"], r["tentative"]) for r in rows] == [(d(i), d(i), True) for i in range(len(rows))], [(r["id"], r.get("start"), r.get("due")) for r in rows])
        check("予定表: システムテストの行は最後", rows[-1].get("gate") == "systemtest" and rows[-1]["due"] == d(len(rows) - 1))
        check("予定表: 日付つきでも schedule の署名は有効（段は RUN のまま）", e.stage() == "RUN")
        gantt = e.run(["tasks", "gantt", "--text"])[1]
        check("予定表: ガントに S 行が出る", "S-02" in gantt and "~" in gantt.split("S-02")[1].splitlines()[0], gantt)
        # already set dates stay, and the next undated row starts the day after them
        e.prompt("continue")
        e.run(["task", "date", "S-03", "2026-12-01", "2026-12-03", "--fixed"])
        e.run(["task", "date", "S-04", "-", "-"])
        e.run(["schedule-init"])
        rows = {r["id"]: r for r in e.rec("schedule_%s.json" % slug)["rows"]}
        check("予定表: schedule-init は付いている日付を残し、日付の無い行は前の期限の翌日から",
              rows["S-03"]["start"] == "2026-12-01" and rows["S-03"]["tentative"] is False and rows["S-04"]["start"] == "2026-12-04" and rows["S-04"]["due"] == "2026-12-04", rows["S-04"])
    finally:
        e.close()
    # rows added later
    e = Env()
    try:
        slug = build_to_run(e)
        e.write("projects/%s/design/io.json" % slug, json.dumps({"rows": IO_EN["rows"] + [IO_SCHED]}))
        e.prompt("approve")
        e.run(["schedule-init"])
        rows = e.rec("schedule_%s.json" % slug)["rows"]
        check("予定表: あとから足した行にも日付が付き、ゲートの行は最後のまま",
              rows[-1].get("gate") == "systemtest" and all(r.get("start") for r in rows) and [r["start"] for r in rows] == sorted(r["start"] for r in rows), [(r["id"], r.get("start")) for r in rows])
    finally:
        e.close()
    en = _engine_template
    check("予定表: 日付が付く行は未完了だけ（done には付けない）",
          [r.get("start") for r in en.date_rows([{"id": "S-01", "status": "done"}, {"id": "S-02", "status": "todo"}], today)] == [None, today.isoformat()])


def gantt_rows(text):
    return [l for l in text.splitlines() if re.match(r"^[ >](S|T)-\d+ ", l)]


def test_open_block_on_choice():
    """When a project becomes active, Claude gets what is open in it, once: select, new, the automatic choice at session start and at the first prompt."""
    e = Env()
    try:
        slug = build_to_run(e)
        e.write("projects/02_shop/PROJECT.md", "# Name: Shop\nwhat: a shop\n")
        for i in range(14):
            e.run(["task", "add", "Item %d" % i, "--due", "2026-11-%02d" % (i + 1)])
        e.run(["task", "add", "Shop item", "--project", "shop"])
        # two projects: nothing is active at session start, only the counts reach Claude
        c = e.ctx("sessionstart", {"source": "startup"})
        check("選択: 2 つ以上あると起動では件数だけ（有効な項目の行は出ない）", "Open in App:" not in c and "Open: " in c, c[-400:])
        e.prompt("continue")
        e.prompt("ok")
        rc, out = e.run(["select", "01_app", "--quote", "ok"])
        lines = out.splitlines()
        i = [n for n, l in enumerate(lines) if l == "Open in App:"]
        body = lines[i[0] + 1:] if i else []
        check("選択: select の出力に、その項目（足りない物の 1 行・T の項目・S の行）が 12 行まで出て、残りは +N more: ws.sh tasks",
              rc == 0 and i and len(body) == 13 and body[0].startswith("To finish the first version:") and body[1].startswith("T-01 [req, todo] Item 0")
              and re.match(r"^\+\d+ more: `bash ws/bin/ws.sh tasks`$", body[-1]), out[-600:])
        rc, out = e.run(["select", "02_shop", "--quote", "ok"])
        check("選択: 別のプロジェクトを選ぶと、そのプロジェクトの項目が出る", "Open in Shop:" in out and "Shop item" in out and "Item 0" not in out, out)
        rc, out = e.run(["new", "third", "--name", "Third", "--quote", "ok"])
        check("選択: new の出力にも、足りない物の行が出る", rc == 0 and "Open in Third:" in out and "Before the build:" in out, out)
        rc, out = e.run(["select", "01_app", "--quote", "ok"])
        check("選択: 項目が 12 行以内なら +N more は付かない（別のプロジェクト）", "Open in App:" in out, out)
        # the per-prompt digest stays at 5 lines
        c = e.pctx("The totals look wrong, please fix")
        check("選択: 毎入力の項目は 5 行のまま", len([l for l in c.splitlines() if re.match(r"^[TS]-\d+ \[", l)]) <= 5, c[-500:])
    finally:
        e.close()
    # one project: the automatic choice, at session start and at the first prompt
    e = Env()
    try:
        slug = build_to_run(e)
        e.run(["task", "add", "Export to CSV", "--due", "2026-11-05"])
        c = e.ctx("sessionstart", {"source": "startup"})
        check("選択: 起動で 1 つだけのプロジェクトを自動で選ぶと、continuing の note に項目が付く（二重には出ない）",
              c.count("Open in App:") == 1 and "Continuing App." in c and c.index("Continuing App.") < c.index("Open in App:") and "T-01 [req, todo] Export to CSV" in c, c[-700:])
        e.run(["task", "none"])
        e2 = Env()
        try:
            slug = build_to_run(e2)
            e2.run(["task", "add", "Export to CSV", "--due", "2026-11-05"])
            e2.hook("sessionstart", {"source": "clear"})
            c = e2.pctx("continue")
            check("選択: 最初の入力でも、continuing の note に項目が付く", "Continuing App." in c and "T-01 [req, todo] Export to CSV" in c, c[-700:])
        finally:
            e2.close()
    finally:
        e.close()


def test_gantt_text():
    import datetime
    import unicodedata
    width = lambda t: sum(2 if unicodedata.east_asian_width(c) in "WF" else 1 for c in t)
    today = datetime.date.today()
    first = today - datetime.timedelta(days=today.weekday())
    dd = lambda n: (today + datetime.timedelta(days=n)).isoformat()
    col = lambda n: (today + datetime.timedelta(days=n) - first).days  # the cell of the day today+n in the 21 cells at the end of a row
    for code, titles in (("en", ("Export to CSV", "Fix the total", "A very long title that has to be cut somewhere")),
                         ("ja", ("CSV に書き出す", "合計が合わない", "とても長い日本語の題名がここに入っていて、どこかで切る必要があります"))):
        e = Env()
        try:
            e.env["CREATECODEBOX_LANG"] = code
            slug = build_to_run(e, first_prompt="小さな道具を作りたい" if code == "ja" else "make a small tool")
            e.prompt("continue")
            e.run(["task", "date", "S-02", dd(0), dd(0)])
            e.run(["task", "add", titles[0], "--start", dd(2), "--due", dd(6), "--fixed"])
            e.run(["task", "add", titles[1], "--kind", "issue", "--due", dd(3)])
            e.run(["task", "add", titles[2], "--due", dd(1)])
            e.run(["task", "set", "T-03", "doing"])
            e.run(["task", "add", "far away", "--due", dd(60)])
            e.run(["task", "add", "long ago", "--due", dd(-40)])
            e.run(["task", "add", "never dated", "--kind", "todo"])
            out = e.run(["tasks", "gantt", "--text"])[1]
            rows = gantt_rows(out)
            ids = {l[1:6]: l for l in rows}
            check("ガント文字（%s）: 日付つきの行は全て同じ表示幅（全角は 2 桁）で、格子の 21 日が揃う" % code,
                  len(rows) >= 6 and len({width(l) for l in rows}) == 1 and width(rows[0]) == 24 + 21, [(width(l), l) for l in rows])
            check("ガント文字（%s）: 1 日 1 文字・日の位置が合う（T-01 は確定 # が start..due の列・T-02 は仮 ~ が due の 1 列）" % code,
                  ids["T-01 "][-21:][col(2):col(6) + 1] == "#####" and ids["T-01 "][-21:][col(2) - 1] == "." and ids["T-01 "][-21:][col(6) + 1] == "."
                  and ids["T-02 "][-21:][col(3)] == "~" and ids["T-02 "][-21:].count("~") == 1, ids)
            check("ガント文字（%s）: 今日の列に ^ がある（見出しの下）・見出しは月曜ごとの MM-DD" % code,
                  out.splitlines()[2].index("^") == 24 + col(0) and out.splitlines()[1].split()[:3] == [(first + datetime.timedelta(days=7 * k)).strftime("%m-%d") for k in range(3)], out.splitlines()[:3])
            check("ガント文字（%s）: 作業中の行は > から始まる" % code, any(l.startswith(">T-03") for l in rows), rows)
            check("ガント文字（%s）: 窓より先は + ・窓より前の未完了は <" % code,
                  any(l.endswith("+") and "far away" in l for l in rows) and any(l[-21] == "<" and "long ago" in l for l in rows), rows)
            check("ガント文字（%s）: 長い題は … で切る" % code, any("…" in l[:24] for l in rows if "T-03" in l or "S-03" in l), rows)
            check("ガント文字（%s）: どの行も 60 桁ほど以内（日付の無い物の行も）" % code, all(width(l) <= 62 for l in out.splitlines() if not l.startswith("Schedule page") and "/ws/projects" not in l and "ws/projects" not in l)
                  and "never dated" in out, [(width(l), l) for l in out.splitlines()])
        finally:
            e.close()
    en = _engine_template
    check("ガント文字: fit_width は全角を 2 桁と数えて切り・足す", en.fit_width("あいうえお", 7) == "あいう…" and en.disp_width(en.fit_width("あいうえお", 7)) == 7
          and en.fit_width("abc", 5) == "abc  " and en.fit_width("abcdefgh", 5) == "abcd…")


def test_tasks_digest_and_page():
    e = Env()
    try:
        slug = build_to_run(e)
        e.prompt("continue")
        e.write("projects/02_shop/PROJECT.md", "# Name: Shop\n")
        e.run(["task", "add", "Shop item one", "--project", "shop"])
        e.run(["task", "add", "Shop item two", "--project", "shop"])
        for i in range(9):
            e.run(["task", "add", "Item number %d %s" % (i, "long title words " * 5), "--due", "2026-11-%02d" % (i + 1)])
        c = e.pctx("The totals look wrong, please fix")
        extra = c[c.index("Open in App:"):]
        lines = extra.splitlines()
        items = [l for l in lines if re.match(r"^[TS]-\d+ \[", l)]
        check("タスク: 毎入力の足し分は 700 字以内（triage の行を含む）", len(extra) <= 700, len(extra))
        check("タスク: 項目は 5 行まで・題は 60 字ほどで切る・残りは +N more", len(items) <= 5 and all(len(l) <= 110 for l in items) and any(l.startswith("+") and "more" in l for l in lines), lines)
        check("タスク: 項目の書式（T-03 [req, todo] … (due 11-05~)）", any(re.match(r"^T-\d+ \[req, todo\] Item number \d.* \(due (2026-)?11-\d\d~\)$", l) for l in items), items)
        check("タスク: 他のプロジェクトの残りは 1 行", any(l.startswith("Open in other projects: Shop 2") for l in lines), lines)
        check("タスク: 足し分に triage の行がある・コマンドは 1 つずつ（&& を使わない）の規則つき", "task none" in extra and "`&&`" in extra)
        e.run(["task", "none"])
        c = e.pctx("continue")
        check("タスク: 自明な入力では triage の行は出ず、項目だけ出る", "task none" not in c and "Open in App:" in c)
        # session start
        for n in range(3, 12):
            e.write("projects/%02d_p%d/PROJECT.md" % (n, n), "# Name: P%d\n" % n)
        s = e.ctx("sessionstart", {"source": "resume"})
        blk = s[s.index("Task board"):]
        plines = [l for l in blk.splitlines() if re.match(r"^  \S.*: .*\. Open: \d+", l)]
        check("タスク: 起動のブロックは 1 プロジェクト 1 行・8 件まで・残りは +N more", len(plines) == 8 and "+3 more" in blk, (len(plines), blk[-300:]))
        check("タスク: 起動のブロックは見る方法の行で終わる", blk.rstrip().splitlines()[-1].startswith("Full board:") or "Full check" in blk, blk[-200:])
        check("タスク: 起動のブロックに有効な項目（上位 6 行）が出る", len([l for l in blk.splitlines() if re.match(r"^  [TS]-\d+ \[", l)]) <= 6)
        # the schedule page
        page = e.p("projects", "schedule.html")
        html = open(page, encoding="utf-8").read()
        check("ガント: projects/schedule.html が書かれ、項目の題が入る", "Item number 0" in html and "Shop item one" in html and '"tent": true' in html, html[:200])
        check("ガント: 30 秒ごとの再読み込み・外部の script / font なし・明暗の切り替え",
              '<meta http-equiv="refresh" content="30">' in html and "<script src" not in html and "http://" not in html.replace("http://www.w3.org/2000/svg", "")
              and "https://" not in html and "@import" not in html and "prefers-color-scheme: dark" in html)
        check("ガント: 日付の無い物の欄・今日の線・仮の凡例の言葉が入る", "No date yet" in html and "tnow" in html and "Guessed date" in html)
        before = open(page, encoding="utf-8").read()
        e.run(["task", "add", "Brand new item for the page"])
        after = open(page, encoding="utf-8").read()
        check("ガント: task add のあとで描き直される（新しい題が入る）", "Brand new item" not in before and "Brand new item" in after)
        mt = os.stat(page).st_mtime_ns
        e.prompt("continue")
        check("ガント: 何も変わらなければ書き直さない（更新時刻が同じ）", os.stat(page).st_mtime_ns == mt)
        rc, out = e.run(["tasks", "gantt", "--text"])
        check("ガント: tasks gantt --text は週の格子（~ は仮・# は確定）と絶対パスを出す", rc == 0 and "~" in out and "^" in out and out.strip().endswith(os.path.realpath(page)), out[-300:])
        check("ガント: AI は直接書けない（Write は止まる・Bash の書き込みも止まる）",
              e.pre("Write", file_path=page, content="x") is not None and "only by ws.sh" in e.pre("Write", file_path=page, content="x")
              and e.pre("Bash", command="python3 x.py projects/schedule.html") is not None)
        rc, out = e.run(["open", "projects/schedule.html"])
        check("ガント: ws.sh open でこのページを開ける", rc == 0 and "schedule.html" in out, out)
        # the page follows the stage: a re-render by the hook
        e.run(["tasks", "gantt"])
        h0 = open(page, encoding="utf-8").read()
        os.remove(e.p("projects", slug, "design", "io.json"))
        e.prompt("continue")
        h1 = open(page, encoding="utf-8").read()
        check("ガント: on_prompt が段の変化でページを描き直す（stage_label が変わる）", h0 != h1 and '"stage_label": "build"' in h0 and '"stage_label": "build"' not in h1, (e.stage(), h1[-100:]))
        # a render that fails never breaks a hook
        tpl = e.p("ws", "render", "tasks.template.html")
        os.rename(tpl, tpl + ".off")
        out = e.hook("prompt", {"prompt": "continue"})
        s2 = e.hook("sessionstart", {"source": "resume"})
        check("ガント: 雛形が無くても on_prompt・on_session_start は壊れない（短い注意が 1 行）",
              '"additionalContext"' in out and "could not be updated" in json.loads(out)["hookSpecificOutput"]["additionalContext"]
              and "could not be updated" in json.loads(s2)["hookSpecificOutput"]["additionalContext"], (out[:200], s2[:200]))
        os.rename(tpl + ".off", tpl)
        os.remove(page)
        os.mkdir(page)  # writing the page now raises (a folder is in the way)
        out = e.hook("prompt", {"prompt": "continue"})
        s2 = e.hook("sessionstart", {"source": "resume"})
        check("ガント: 描くときに例外が出ても hook は壊れない", "could not be updated" in json.loads(out)["hookSpecificOutput"]["additionalContext"]
              and "[CreateCodeBox" in json.loads(s2)["hookSpecificOutput"]["additionalContext"])
        rc, out = e.run(["task", "add", "while the page is blocked"])
        check("ガント: 描けなくても task add は記録できる", rc == 0 and "T-" in out, out)
    finally:
        e.close()


def test_tasks_lang():
    import lang as lg
    from lang import en as lang_en, ja as lang_ja
    miss = [k for k in lang_en.MESSAGES if k not in lang_ja.MESSAGES] + [k for k in lang_ja.MESSAGES if k not in lang_en.MESSAGES]
    check("タスク: en と ja の表のキーが同じ", not miss, miss[:5])
    keys = [k for k in lang_en.MESSAGES if k.startswith(("task.", "html.tasks.")) or k in ("deny.triage", "stop.triage", "note.task_soft", "zone.board")]
    bad = [k for k in keys if re.search(r"(?i)\b(easy|easily|anyone|safe|safely|beginner|simple)\b", lang_en.MESSAGES[k]) or re.search("簡単|誰でも|安全", lang_ja.MESSAGES[k])]
    check("タスク: 新しい文に使わない語（easy・anyone・safe・beginner・簡単・誰でも・安全）が無い", not bad, bad)
    e = Env()
    try:
        e.env["CREATECODEBOX_LANG"] = "ja"
        slug = build_to_run(e, first_prompt="小さな道具を作りたい")
        e.prompt("続き")
        e.prompt("はい")
        c = e.pctx("CSV に書き出す機能を足してください")
        r = e.pre("Edit", file_path=e.p("projects", slug, "src", "a.py"), old_string="a", new_string="b")
        check("タスク（ja）: triage の行・deny・stop が日本語の表の文", lang_ja.MESSAGES["task.triage"] in c and r is not None and lang_ja.MESSAGES["deny.triage"] in r
              and lang_ja.MESSAGES["stop.triage"] == json.loads(e.hook("stop", {"last_assistant_message": "x"}))["reason"], (c[-300:], r))
        rc, out = e.run(["task", "add", "CSV 出力", "--due", "2026-11-05"])
        check("タスク（ja）: RUN の tasks の見出しは日本語（第 1 版を作り終えるために）・triage の行に単独実行の規則", "第 1 版を作り終えるためにやること:" in e.run(["tasks"])[1] and "`&&`" in lang_ja.MESSAGES["task.triage"])
        check("タスク（ja）: task add の出力は日本語（予定を更新しました）", rc == 0 and "足しました" in out and "予定を更新しました" in out, out)
        page = open(e.p("projects", "schedule.html"), encoding="utf-8").read()
        check("ガント（ja）: html lang・ラベル・CJK フォントが ja", '<html lang="ja">' in page and "日付がまだ無い物" in page and "Hiragino" in page)
    finally:
        e.close()


def test_commit_email_privacy():
    """Saves are recorded under a name and address that do not show who the person is, and publish-check
    refuses to publish commits that carry a real-looking address. All addresses here are made up (example.com)."""
    REAL = "jane@example.com"
    PRIV = "createcodebox@users.noreply.invalid"

    def setup(global_email=REAL, remote=False):
        e = Env()
        if global_email:
            with open(os.path.join(e.home, ".gitconfig"), "w") as f:
                f.write("[user]\n\tname = Jane Real\n\temail = %s\n" % global_email)
        new_project(e)
        for c in ("save", "github", "private-public"):
            e.run(["learn", c])
        srcd = e.p("projects", "01_kakeibo", "src")
        if remote:
            bare = os.path.join(e.tmp, "remote.git")
            subprocess.run(["git", "init", "--bare", "-q", bare], capture_output=True)
            e.env["CREATECODEBOX_ALLOW_LOCAL_REMOTE"] = "1"
            e.remote = bare
        return e, srcd

    def git(e, srcd, *a, **env):
        return subprocess.run(["git", "-C", srcd] + list(a), capture_output=True, text=True, env=dict(e.env, **env))

    def real_commit(e, srcd, name, msg, email=REAL):
        open(os.path.join(srcd, name), "w").write(msg + "\n")
        git(e, srcd, "add", "-A")
        return git(e, srcd, "commit", "-q", "-m", msg, GIT_AUTHOR_NAME="Jane Real", GIT_AUTHOR_EMAIL=email,
                   GIT_COMMITTER_NAME="Jane Real", GIT_COMMITTER_EMAIL=email)

    def pc_public(e):
        out = e.engine_call("engine.remote_visibility = lambda u: 'public'\nrc, msg = engine.cmd_publish_check(root)\nprint('RC=%d' % rc)\nprint(msg)")
        return int(re.search(r"RC=(\d+)", out).group(1)), out

    # (a) init sets a local identity and leaves the global config alone
    e, srcd = setup()
    try:
        gc = open(os.path.join(e.home, ".gitconfig")).read()
        rc, out = e.run(["repo", "init"])
        check("メール: repo init は、この repo だけに名前 CreateCodeBox を入れる", rc == 0 and git(e, srcd, "config", "--local", "user.name").stdout.strip() == "CreateCodeBox", out)
        check("メール: repo init は、この repo だけに誰か分からないアドレスを入れる", git(e, srcd, "config", "--local", "user.email").stdout.strip() == PRIV, out)
        check("メール: repo init は、利用者に一度だけ伝える", "CreateCodeBox" in out and "repo email" in out, out)
        check("メール: 利用者の全体の設定（~/.gitconfig）は変えない", open(os.path.join(e.home, ".gitconfig")).read() == gc)
        open(os.path.join(srcd, "a.txt"), "w").write("a\n")
        rc, out = e.run(["save", "first"])
        check("メール: save した記録の作者と記録者は、誰か分からないアドレス",
              rc == 0 and git(e, srcd, "log", "--format=%ae %ce").stdout.split() == [PRIV, PRIV] and REAL not in git(e, srcd, "log", "--format=%an %ae %cn %ce").stdout, out)
        check("メール: 伝えるのは一度だけ（2 回目の save には出ない）", "repo email" not in out, out)
    finally:
        e.close()

    # an older repo (started by git itself, no local identity): save sets it before the first commit
    e, srcd = setup()
    try:
        subprocess.run(["git", "-C", srcd, "init", "-q"], capture_output=True)
        open(os.path.join(srcd, "a.txt"), "w").write("a\n")
        rc, out = e.run(["save", "first"])
        check("メール: すでにある repo でも、save の前に誰か分からないアドレスにする", rc == 0 and git(e, srcd, "log", "--format=%ae").stdout.strip() == PRIV, out)
    finally:
        e.close()

    # a global GitHub private address is kept
    for gl in ("jane@users.noreply.github.com", "12345+jane@users.noreply.github.com"):
        e, srcd = setup(global_email=gl)
        try:
            rc, out = e.run(["repo", "init"])
            check("メール: 全体の設定が GitHub の非公開用アドレスなら、そのまま使う（%s）" % gl,
                  rc == 0 and git(e, srcd, "config", "--local", "user.email").returncode != 0 and git(e, srcd, "config", "user.email").stdout.strip() == gl and "repo email" not in out, out)
        finally:
            e.close()

    # (b) repo email
    e, srcd = setup()
    try:
        check("メール: repo email は、repo が無い間は断る", e.run(["repo", "email", "janedoe@users.noreply.github.com"])[0] == 2)
        e.run(["repo", "init"])
        check("メール: repo email に何も渡さないと断る", e.run(["repo", "email"])[0] == 2)
        for bad in (REAL, "janedoe@users.noreply.github.com.evil.example", "jane doe@users.noreply.github.com", "+jane@users.noreply.github.com",
                    "12345+@users.noreply.github.com", "a+b+c@users.noreply.github.com", "noreply@github.com", "x@users.noreply.invalid"):
            rc, out = e.run(["repo", "email", bad])
            check("メール: repo email は断る（%s）" % bad, rc == 2 and git(e, srcd, "config", "--local", "user.email").stdout.strip() == PRIV, (rc, out))
        for good in ("12345+janedoe@users.noreply.github.com", "janedoe@users.noreply.github.com"):
            rc, out = e.run(["repo", "email", good])
            check("メール: repo email は受ける（%s）" % good, rc == 0 and git(e, srcd, "config", "--local", "user.email").stdout.strip() == good, (rc, out))
        open(os.path.join(srcd, "a.txt"), "w").write("a\n")
        rc, out = e.run(["save", "with own private address"])
        check("メール: repo email のあとの save は、そのアドレスで残り、上書きされない",
              rc == 0 and git(e, srcd, "log", "--format=%ae|%an").stdout.strip() == "janedoe@users.noreply.github.com|CreateCodeBox", out)
    finally:
        e.close()

    # (c) publish-check: a real-looking address in a commit that would become public
    e, srcd = setup(remote=True)
    try:
        e.run(["repo", "link", e.remote])
        open(os.path.join(srcd, "README.md"), "w").write("# app\n")
        open(os.path.join(srcd, "LICENSE"), "w").write("MIT\n")
        real_commit(e, srcd, "a.txt", "one")
        rc, out = e.run(["publish-check"])
        check("メール: 本物らしいアドレスの記録があると publish-check は通らない（非公開の保管庫）", rc == 1 and REAL in out and "NG" in out, out)
        check("メール: 通らない時は、件数と、公開しないよう伝える文が出る", re.search(r"1 of 1 saves|1 件のセーブのうち 1 件", out) is not None and ("Do not publish yet" in out or "まだ公開しないで" in out), out)
        check("メール: 通らなかった記録が残り、publish は進まない", e.rec("publish_check_01_kakeibo.json")["ok"] is False and e.run(["publish"])[0] == 1)
        # a private-address commit on top does not hide the real one
        e.run(["repo", "email", "janedoe@users.noreply.github.com"])
        open(os.path.join(srcd, "b.txt"), "w").write("b\n")
        e.run(["save", "two"])
        rc, out = e.run(["publish-check"])
        check("メール: 古い記録に本物らしいアドレスが残っていれば、後の記録が非公開用でも通らない", rc == 1 and REAL in out and "janedoe@users.noreply.github.com" in out, out)
    finally:
        e.close()

    # an unreadable-looking mix: committer only
    e, srcd = setup(remote=True)
    try:
        e.run(["repo", "link", e.remote])
        open(os.path.join(srcd, "README.md"), "w").write("# app\n")
        open(os.path.join(srcd, "LICENSE"), "w").write("MIT\n")
        open(os.path.join(srcd, "a.txt"), "w").write("a\n")
        git(e, srcd, "add", "-A")
        git(e, srcd, "commit", "-q", "-m", "x", GIT_AUTHOR_EMAIL="x@foo.invalid", GIT_AUTHOR_NAME="n", GIT_COMMITTER_EMAIL=REAL, GIT_COMMITTER_NAME="n")
        rc, out = e.run(["publish-check"])
        check("メール: 記録者（committer）のアドレスだけでも見る", rc == 1 and REAL in out, out)
    finally:
        e.close()

    # all private: passes, and lists the addresses
    e, srcd = setup(remote=True)
    try:
        e.run(["repo", "link", e.remote])
        open(os.path.join(srcd, "README.md"), "w").write("# app\n")
        open(os.path.join(srcd, "LICENSE"), "w").write("MIT\n")
        e.run(["save", "one"])
        real_commit(e, srcd, "b.txt", "two", email="noreply@github.com")
        real_commit(e, srcd, "c.txt", "three", email="x@foo.invalid")
        real_commit(e, srcd, "d.txt", "four", email="12345+jane@users.noreply.github.com")
        rc, out = e.run(["publish-check"])
        check("メール: 全部が非公開用（noreply.github.com・noreply@github.com・.invalid）なら通る", rc == 0 and "NG" not in out, out)
        check("メール: 通る時も、記録のアドレスを一覧で見せる", all(a in out for a in (PRIV, "noreply@github.com", "x@foo.invalid", "12345+jane@users.noreply.github.com")), out)
        out2 = e.run(["publish"])[1]
        check("メール: 通れば、公開の語のあと publish できる", e.prompt("publish") and e.run(["publish"])[0] == 0, out2)
    finally:
        e.close()

    # already-public remote: only the saves not yet on the remote count
    e, srcd = setup(remote=True)
    try:
        e.run(["repo", "link", e.remote])
        open(os.path.join(srcd, "README.md"), "w").write("# app\n")
        open(os.path.join(srcd, "LICENSE"), "w").write("MIT\n")
        real_commit(e, srcd, "a.txt", "old one, already out")
        git(e, srcd, "push", "-q", "-u", "origin", "HEAD")
        e.run(["repo", "email", "janedoe@users.noreply.github.com"])
        open(os.path.join(srcd, "b.txt"), "w").write("b\n")
        e.run(["save", "new one"])
        rc, out = e.run(["publish-check"])
        check("メール: 保管庫が非公開なら、送り済みの記録も数えて通らない", rc == 1 and REAL in out, out)
        rc, out = pc_public(e)
        check("メール: すでに公開なら、送り済みの古い記録は数えず通る", rc == 0, out)
        check("メール: すでに公開なら、古い記録は注意として知らせる（落とさない）", REAL in out and ("already on the public repo" in out or "すでに載っている" in out), out)
        real_commit(e, srcd, "c.txt", "new real one")
        rc, out = pc_public(e)
        check("メール: すでに公開でも、まだ送っていない記録に本物らしいアドレスがあれば通らない", rc == 1 and REAL in out and "NG" in out, out)
        check("メール: 数えるのはまだ送っていない記録だけ（2 件中 1 件）", re.search(r"1 of 2 saves|2 件のセーブのうち 1 件", out) is not None, out)
    finally:
        e.close()

    # adopt sets the local identity too
    e = Env()
    try:
        with open(os.path.join(e.home, ".gitconfig"), "w") as f:
            f.write("[user]\n\tname = Jane Real\n\temail = %s\n" % REAL)
        e.prompt("既存のアプリを直したい")
        e.run(["new", "old", "--name", "既存", "--quote", "既存"])
        orig = os.path.join(e.tmp, "orig")
        os.makedirs(orig)
        subprocess.run(["git", "-C", orig, "init", "-q"], capture_output=True)
        open(os.path.join(orig, "app.py"), "w").write("print(1)\n")
        for a in (["add", "-A"], ["-c", "user.name=t", "-c", "user.email=t@t.invalid", "commit", "-q", "-m", "i"]):
            subprocess.run(["git", "-C", orig] + a, capture_output=True)
        rc, out = e.run(["repo", "adopt", orig])
        rc, out = e.run(["repo", "adopt", orig]) if rc == 3 else (rc, out)
        srcd = e.p("projects", "01_old", "src")
        check("メール: repo adopt も、この repo だけに誰か分からない名前とアドレスを入れて、一度だけ伝える",
              rc == 0 and git(e, srcd, "config", "--local", "user.email").stdout.strip() == PRIV
              and git(e, srcd, "config", "--local", "user.name").stdout.strip() == "CreateCodeBox" and "repo email" in out, out)
    finally:
        e.close()


def main():
    e = Env()
    try:
        out = e.hook("sessionstart", {"source": "startup"})
        check("起動: 文脈に [CreateCodeBox と R0", "[CreateCodeBox" in out and "R0" in out, out)
        check("R0: projects/ への書き込みは止まる", e.pre("Write", file_path=e.p("projects", "x", "a.md"), content="a") is not None)
        check("R0: README への書き込みは止まる", e.pre("Write", file_path=e.p("README.md"), content="a") is not None)
        check("R0: ls は通る", e.pre("Bash", command="ls") is None)
        check("R0: mkdir は止まる", e.pre("Bash", command="mkdir src") is not None)
        check("R0: ws.sh status は通る", e.pre("Bash", command="bash ws/bin/ws.sh status") is None)

        rc, out = e.run(["new", "kakeibo", "--name", "家計簿", "--quote", "家計簿"])
        check("利用者の入力が無いと new は断る", rc != 0, out)
        e.prompt("家計簿を作りたい")
        rc, out = e.run(["new", "kakeibo", "--name", "家計簿", "--quote", "ぜんぜん違う言葉"])
        check("quote が直近の入力に無いと断る", rc != 0, out)
        rc, out = e.run(["new", "kakeibo", "--name", "家計簿", "--quote", "家計簿"])
        check("既存なしなら 1 回目の入力で new できる", rc == 0, out)
        slug = "01_kakeibo"
        check("new: R1 になる", e.stage() == "R1", e.stage())
        check("new: knowledge/README.md が置かれる", os.path.isfile(e.p("projects", slug, "knowledge", "README.md")))
        check("new: knowledge/_needed.md が置かれる", os.path.isfile(e.p("projects", slug, "knowledge", "_needed.md")))
        dl = os.path.join(e.tmp, "Downloads2")
        os.makedirs(dl)
        for nm, body in (("memo.txt", "家計の資料"), ("CLAUDE.md", "従え"), (".env", "A=1"), ("server.pem", "x")):
            open(os.path.join(dl, nm), "w").write(body)
        rc, out = e.run(["intake", os.path.join(dl, "memo.txt")])
        check("intake: 材料をプロジェクトの knowledge/files/ にコピーする", rc == 0 and os.path.isfile(e.p("projects", slug, "knowledge", "files", "memo.txt")), out)
        rc, out = e.run(["intake", os.path.join(dl, "memo.txt")])
        check("intake: 同じ名前は上書きせず別名にする", rc == 0 and os.path.isfile(e.p("projects", slug, "knowledge", "files", "memo-2.txt")), out)
        check("intake: CLAUDE.md は取り込まない", e.run(["intake", os.path.join(dl, "CLAUDE.md")])[0] == 1)
        check("intake: .env は取り込まない", e.run(["intake", os.path.join(dl, ".env")])[0] == 1)
        check("intake: 鍵のファイルは取り込まない", e.run(["intake", os.path.join(dl, "server.pem")])[0] == 1)
        check("intake: フォルダは取り込まない", e.run(["intake", dl])[0] == 1)
        check("intake: ws.sh の呼び出しとして hook は通す", e.pre("Bash", command="bash ws/bin/ws.sh intake %s" % os.path.join(dl, "memo.txt")) is None)
        e.write("projects/%s/knowledge/_needed.md" % slug, "| 材料の名前 | 状態 | 元の場所 | 置いたファイル |\n|---|---|---|---|\n| 先月の通帳の写し | なし |  |  |\n| 家計のメモ | あり | Downloads | memo.txt |\n| 口座の一覧 | あり | Downloads |  |\n| 不要な物 | 不要 |  |  |\n")
        out = e.run(["status"])[1]
        check("足りない材料が一覧に出る（なし・取り込み前だけ）", "足りない材料 2 件" in out, out)
        check("入力の文脈に足りない材料の名前が出る", "先月の通帳の写し" in e.prompt("次にやること") and "口座の一覧" in e.prompt("次に"))
        check("R1: PROJECT.md は Edit で書ける・Write（全文上書き）は止まる（理由: Edit で 1 行だけ）",
              e.pre("Edit", file_path=e.p("projects", slug, "PROJECT.md"), old_string="a", new_string="b") is None
              and "PROJECT.md を直すときは" in (e.pre("Write", file_path=e.p("projects", slug, "PROJECT.md"), content="x") or ""))
        check("R1: src/ は止まる", e.pre("Write", file_path=e.p("projects", slug, "src", "a.py"), content="x") is not None)
        check("R1: 別プロジェクトの場所は止まる", e.pre("Write", file_path=e.p("projects", "02_other", "PROJECT.md"), content="x") is not None)

        e.set_fields(slug, goal_type="自分用", what="家計簿の Web アプリ")
        check("R1 を埋めると R2", e.stage() == "R2", e.stage())
        e.set_fields(slug, who="自分", today="Excel で手入力", done_when="月ごとの合計が見える", not_doing="銀行との連携", has_ui="no")
        st_txt = e.run(["status"])[1]
        check("8-A: 新規の入口の R2 は、todo の先頭が references・その次が sketch（プロトタイプ）", e.stage() == "R2" and 0 < st_txt.index("近いサイトやアプリを聞く") < st_txt.index("プロトタイプを見せる"), st_txt)
        e.set_fields(slug, references="none")
        check("新規の入口: references: none で満たされ、sketch が無いと R2 のまま・todo の先頭は sketch", e.stage() == "R2" and "プロトタイプを見せる" in e.run(["status"])[1] and "近いサイトやアプリ" not in e.run(["status"])[1], e.run(["status"])[1])
        e.write("projects/%s/design/ui/sketch.html" % slug, "<body data-ccb=\"sketch\">short</body>")
        check("sketch: 500 バイト未満は不可", e.stage() == "R2")
        e.write("projects/%s/design/ui/sketch.html" % slug, "<html><body>" + "x" * 600 + "</body></html>")
        check("sketch: data-ccb の印が無いと不可", e.stage() == "R2")
        e.write("projects/%s/design/ui/sketch.html" % slug, "<html><div data-ccb=\"sketch\">" + "x" * 600 + "</div></html>")
        check("sketch: <body が無いと不可", e.stage() == "R2")
        e.write("projects/%s/design/ui/sketch.html" % slug, SKETCH)
        check("R2 を埋める（画面なし）と R4（sketch あり）", e.stage() == "R4", e.stage())

        # R4: I/O
        e.write("projects/%s/design/io.json" % slug, json.dumps({"rows": [dict(IO_OK["rows"][0], example="TBD")]}))
        rc, out = e.run(["lint"])
        check("lint: TBD と out 無しを検出", rc == 1 and "具体的な例" in out and "出力(out)" in out, out)
        e.write("projects/%s/design/io.json" % slug, json.dumps({"rows": [dict(IO_OK["rows"][0], kind="ファイル"), IO_OK["rows"][1]]}))
        check("lint 通過で R4A（承認待ち）", e.stage() == "R4A", e.stage())
        e.prompt("たぶんこれでいいと思います")
        check("承認の言葉でない入力では承認されない", e.stage() == "R4A")
        check("承認前: src/ は止まる", e.pre("Write", file_path=e.p("projects", slug, "src", "a.py"), content="x") is not None)
        e.prompt("承認します")
        check("承認後は RS（スケジュール待ち）", e.stage() == "RS", e.stage())
        check("RS: src/ はまだ止まる", e.pre("Write", file_path=e.p("projects", slug, "src", "a.py"), content="x") is not None)
        rc, out = e.run(["schedule-init"])
        check("schedule-init で RUN", rc == 0 and e.stage() == "RUN", out)
        check("RUN: src/ に書ける", e.pre("Write", file_path=e.p("projects", slug, "src", "app.py"), content="print(1)") is None)
        check("RUN: 普通のコマンドは通る", e.pre("Bash", command="python3 app.py") is None)
        check("RUN: python3 -m venv env は止まらない", e.pre("Bash", command="python3 -m venv env") is None)
        check("RUN: .ws に触るコマンドは止まる", e.pre("Bash", command="rm -rf .ws") is not None)
        check("RUN: .ws への書き込みは止まる", e.pre("Write", file_path=e.p(".ws", "approval_%s.json" % slug), content="{}") is not None)
        check("RUN: .claude への書き込みは止まる", e.pre("Edit", file_path=e.p(".claude", "settings.json"), old_string="a", new_string="b") is not None)
        check("RUN: CLAUDE.md への書き込みは止まる", e.pre("Write", file_path=e.p("CLAUDE.md"), content="x") is not None)

        rc, out = e.run(["render"])
        check("schedule は .ws/ に署名つきで置かれ、design/ には無い", os.path.isfile(e.p(".ws", "schedule_%s.json" % slug)) and "_sig" in e.rec("schedule_%s.json" % slug)
              and not os.path.isfile(e.p("projects", slug, "design", "schedule.json")))
        check("render: io.html と schedule.html を作る", rc == 0 and os.path.isfile(e.p("projects", slug, "design", "io.html"))
              and os.path.isfile(e.p("projects", slug, "design", "schedule.html")), out)
        html = open(e.p("projects", slug, "design", "io.html"), encoding="utf-8").read()
        check("render: データが埋め込まれ、置換の目印が消える", "支出の入力" in html and "/*__WS_DATA__*/null" not in html)

        rc, out = e.run(["mark", "S-01", "done"])
        check("mark done は確かめた結果（--evidence）が無いと断る", rc == 1 and "evidence" in out, out)
        rc, out = e.run(["mark", "S-01", "done", "--evidence", "python3 app.py を動かして、画面が開いた"])
        check("mark done は --evidence があれば通る（記録される）", rc == 0, out)
        e.engine_call("sc = engine.load_schedule(root, %r); sc['rows'][1]['artifact'] = 'projects/%s/src/nothing.py'; engine.save_schedule(root, %r, sc)" % (slug, slug, slug))
        rc, out = e.run(["mark", "S-02", "done", "--evidence", "820 円を入れて、合計に 820 円と出た"])
        check("mark done は成果物が無いと断る", rc == 1 and "成果物" in out, out)
        rc, out = e.run(["mark", "S-02", "hold"])
        check("hold は理由が無いと断る", rc == 1, out)

        # ---- システムテスト（出力を、人と同じ操作で確かめる）
        stp = e.p(".ws", "st_%s.json" % slug)
        check("schedule-init で、システムテストの一覧も .ws/ に作られる（署名つき）", os.path.isfile(stp) and "_sig" in e.rec("st_%s.json" % slug))
        rows0 = e.rec("st_%s.json" % slug)["rows"]
        check("一覧: 入出力 1 行につき正常 1・失敗 1 のケース（異常系が半分）", [r["id"] for r in rows0] == ["T-IO-01-N1", "T-IO-01-F1", "T-IO-02-N1", "T-IO-02-F1"], [r["id"] for r in rows0])
        rc, out = e.run(["st", "list"])
        check("st list: 合格 0 / 全 4", rc == 0 and "合格 0 / 全 4" in out, out)
        sys.path.insert(0, os.path.join(e.root, "ws"))
        import engine as eng3
        gen = eng3.st_generate([{"id": "IO-01", "kind": "画面", "name": "a", "dir": "in", "example": "x", "failure": "f", "screen": "SC-1"},
                                {"id": "IO-02", "kind": "画面", "name": "b", "dir": "out", "example": "y", "failure": "g", "screen": "SC-1"},
                                {"id": "IO-03", "kind": "画面", "name": "c", "dir": "in", "example": "z", "failure": "h", "screen": "SC-2"}])
        check("一覧: 空の状態（B）は画面ごとに 1 つ（同じ画面の行ごとには作らない）", [r["id"] for r in gen if r["kind"] == "B"] == ["T-IO-01-B1", "T-IO-03-B1"], [r["id"] for r in gen])
        gen2 = eng3.st_generate([{"id": "IO-01", "kind": "scheduled", "name": "a", "dir": "in", "example": "x", "failure": "f"},
                                 {"id": "IO-02", "kind": "external", "name": "b", "dir": "out", "example": "y", "failure": "g"},
                                 {"id": "IO-03", "kind": "api", "name": "c", "dir": "in", "example": "z", "failure": "h"},
                                 {"id": "IO-04", "kind": "file", "name": "d", "dir": "in", "example": "w", "failure": "i"}])
        who = {r["id"]: r["who"] for r in gen2}
        check("F3: who の初期値（scheduled は全て・external と api の失敗は ai・他は user）",
              who == {"T-IO-01-N1": "ai", "T-IO-01-F1": "ai", "T-IO-02-N1": "user", "T-IO-02-F1": "ai", "T-IO-03-N1": "user", "T-IO-03-F1": "ai",
                      "T-IO-04-N1": "user", "T-IO-04-F1": "user"}, who)
        check("st mark: 入力に ID が無いと合格にできない（--quote だけでは足りない）", e.run(["st", "mark", "T-IO-01-N1", "pass", "--by", "user"])[0] == 1)
        e.prompt("動かしてみました。820 円と出ました。")
        check("st mark: ID を言わない入力では合格にできない", e.run(["st", "mark", "T-IO-01-N1", "pass", "--by", "user", "--quote", "820 円と出ました"])[0] == 1)
        e.prompt("T-IO-01-N1 と T-IO-02-N1 を動かして、820 円と出ました")
        rc, out = e.run(["st", "mark", "T-IO-01-N1", "pass", "--by", "user"])
        check("st mark: ID と 10 文字以上の説明があれば合格にできる（recorded: の文が出る）", rc == 0 and "記録しました: T-IO-01-N1" in out and "4 件中 1 件" in out, out)
        check("st mark: 記録に via/bulk は無い（ID で答えた）", "via" not in e.rec("st_%s.json" % slug)["rows"][0])
        check("st mark: 1 入力は 1 回だけ（使い切り）", e.run(["st", "mark", "T-IO-02-N1", "pass", "--by", "user"])[0] == 1)
        e.prompt("IO-02-N1 ok")
        check("st mark: ID だけで ok のような短い返事は不可", e.run(["st", "mark", "T-IO-02-N1", "pass", "--by", "user"])[0] == 1)
        e.prompt("01-N1 works")
        check("st mark: works も不可（pass / 合格 でも 10 文字でもない）", e.run(["st", "mark", "T-IO-01-N1", "pass", "--by", "user"])[0] == 1)
        e.prompt("N1 passed")
        check("st mark: ID の一部が短すぎる（N1）と不可", e.run(["st", "mark", "T-IO-02-N1", "pass", "--by", "user"])[0] == 1)
        check("st mark: AI は user のケースを --by ai で合格にできない", e.run(["st", "mark", "T-IO-01-F1", "pass", "--by", "ai", "--evidence", "画面に赤字が出た", "--shot", "x.png"])[0] == 1)
        check("st route: 理由が無いと変えられない", e.run(["st", "route", "T-IO-01-F1", "ai"])[0] == 2)
        check("st route: user|ai 以外は不可（旧 CI など）", e.run(["st", "route", "T-IO-01-F1", "CI", "--reason", "not by hand"])[0] == 2)
        rc, out = e.run(["st", "route", "T-IO-01-F1", "ai", "--reason", "cannot be triggered by hand"])
        check("st route: 理由つきなら ai にできる", rc == 0 and e.rec("st_%s.json" % slug)["rows"][1]["who"] == "ai", out)
        check("st mark: ci / ut は廃止", e.run(["st", "mark", "T-IO-01-F1", "pass", "--by", "ci", "--evidence", "CI の失敗系ケースが緑になった（ログ）"])[0] == 2)
        check("st mark: AI が写真なしで合格にはできない", e.run(["st", "mark", "T-IO-01-F1", "pass", "--by", "ai", "--evidence", "画面に赤字が出た"])[0] == 1)
        shot_out = os.path.join(e.tmp, "shot.png")
        open(shot_out, "wb").write(b"\x89PNG\r\n" + b"0" * 400)
        check("st mark: 写真が projects/ の外だと不可", e.run(["st", "mark", "T-IO-01-F1", "pass", "--by", "ai", "--evidence", "金額が数字でないとき、赤字で知らせた", "--shot", shot_out])[0] == 1)
        shot = e.p("projects", slug, "knowledge", "shot.png")
        os.makedirs(os.path.dirname(shot), exist_ok=True)
        open(shot, "wb").write(b"\x89PNG\r\n" + b"0" * 400)
        os.utime(shot, (1000000, 1000000))
        check("st mark: セッション開始より古い写真は不可", e.run(["st", "mark", "T-IO-01-F1", "pass", "--by", "ai", "--evidence", "金額が数字でないとき、赤字で知らせた", "--shot", shot])[0] == 1)
        os.utime(shot, None)
        rc, out = e.run(["st", "mark", "T-IO-01-F1", "pass", "--by", "ai", "--evidence", "金額が数字でないとき、赤字で知らせた", "--shot", shot])
        check("st mark: ai のケースは、projects/ の中の新しい写真と出た物があれば合格にできる", rc == 0 and os.path.isfile(e.p("projects", slug, "design", "evidence", "T-IO-01-F1.png")), out)
        check("st mark: 不合格は理由が要る", e.run(["st", "mark", "T-IO-02-N1", "fail", "--by", "user"])[0] == 1)
        rc, out = e.run(["mark", "S-04", "done"])
        check("mark: 利用者が確かめるケースが残る間は、最後の行を済にできない", rc == 1 and "システムテスト" in out, out)
        rc, out = e.run(["st", "list", "--numbered"])
        check("st list --numbered: 番号つきで出る（1. T-IO-01-N1 …）", rc == 0 and out.startswith("1. T-IO-01-N1") and "4. T-IO-02-F1" in out, out)
        e.prompt("3, 4 pass")
        rc, out = e.run(["st", "mark", "numbered", "pass", "--by", "user"])
        rows_now = e.rec("st_%s.json" % slug)["rows"]
        check("番号で答えると、複数まとめて記録される（recorded: に両方・via: numbered）", rc == 0 and "記録しました: T-IO-02-N1, T-IO-02-F1" in out
              and rows_now[2].get("via") == "numbered" and rows_now[3].get("via") == "numbered", out)
        rc, out = e.run(["mark", "S-04", "done", "--evidence", "一覧の全ケースが実際に出た"])
        check("mark: 利用者のケースと正常系が合格すれば、最後の行を済にできる", rc == 0, out)
        check("予定表・システムテストの記録は、AI が直接書き換えられない（.ws/ と、旧い design/ の場所）", e.pre("Write", file_path=stp, content="{}") is not None
              and e.pre("Edit", file_path=e.p("projects", slug, "design", "schedule.json"), old_string="a", new_string="b") is not None
              and e.pre("Write", file_path=e.p("projects", slug, "design", "systemtest.json"), content="{}") is not None)
        check("証跡の置き場も、AI が直接書けない", e.pre("Write", file_path=e.p("projects", slug, "design", "evidence", "x.png"), content="x") is not None)
        check("入出力の設計（io.json）は、これまでどおり書ける", e.pre("Write", file_path=e.p("projects", slug, "design", "io.json"), content="{}") is None)
        rc, out = e.run(["render"])
        check("render: systemtest.html も作る（雛形があれば）", rc == 0 and ("systemtest.html" in out or not os.path.isfile(e.p("ws", "render", "systemtest.template.html"))), out)

        # 設計を直すと承認は無効
        e.write("projects/%s/design/io.json" % slug, json.dumps({"rows": [IO_OK["rows"][0], IO_OK["rows"][1], dict(IO_OK["rows"][1], id="IO-03", name="印刷")]}))
        check("設計を直すと承認が無効（R4A に戻る）", e.stage() == "R4A", e.stage())

        # 秘密
        check("Read .env は止まる", e.pre("Read", file_path=e.p("projects", slug, "src", ".env")) is not None)
        check("Read .env.example は通る", e.pre("Read", file_path=e.p("projects", slug, "src", ".env.example")) is None)
        check("Read ~/.createcodebox は止まる", e.pre("Read", file_path=os.path.join(e.home, ".createcodebox", ".env")) is not None)
        check("Bash cat .env は止まる", e.pre("Bash", command="cat .env") is not None)
        check("Bash printenv は止まる", e.pre("Bash", command="printenv") is not None)
        check("Bash echo $VAR は止まる", e.pre("Bash", command="echo $GAKASO_API_KEY") is not None)
        check("承認が無効の間は、普通のコマンドも止まる", e.pre("Bash", command="python3 app.py") is not None)
        e.run(["secret", "check"])  # ~/.createcodebox を作っておく（ワイルドカードの試験のため）
        e.run(["secret", "check"])  # ~/.createcodebox を作っておく（ワイルドカードの試験のため）
        check("Grep で秘密のファイルを指すと止まる", e.pre("Grep", pattern="KEY", path=e.p("projects", slug, "src", ".env")) is not None)
        check("Glob で秘密の置き場を指すと止まる", e.pre("Glob", pattern="*", path=os.path.join(e.home, ".createcodebox")) is not None)
        check("Bash のワイルドカードで秘密の置き場を指すと止まる", e.pre("Bash", command="cat ~/.create*/.en*") is not None)
        check("Bash の $HOME で秘密の置き場を指すと止まる", e.pre("Bash", command="cat $HOME/.createc*/.env") is not None)
        check("サンドボックスを外す指定の Bash は止まる", e.pre("Bash", command="ls", dangerouslyDisableSandbox=True) is not None)
        check("with-secrets の中で 1 行のコードを直接実行するのは止まる", e.pre("Bash", command="bash ws/bin/ws.sh with-secrets -- python3 -c print(1)") is not None)
        check("with-secrets の中で環境変数の表示は止まる", e.pre("Bash", command="bash ws/bin/ws.sh with-secrets -- printenv") is not None)
        check("with-secrets の中で鍵の置き場を指すと止まる", e.pre("Bash", command="bash ws/bin/ws.sh with-secrets -- cat ~/.createcodebox/.env") is not None)
        check("with-secrets でファイルのスクリプトを動かすのは通る", e.pre("Bash", command="bash ws/bin/ws.sh with-secrets -- python3 app.py") is None)
        import engine as eng4
        check("公開の見分け: 認証なしで読めれば公開", eng4.classify_remote_result(0, "") == "public" and eng4.classify_remote_result(2, "") == "public")
        check("公開の見分け: 認証を求められたら非公開", eng4.classify_remote_result(128, "fatal: could not read Username for 'https://github.com': terminal prompts disabled") == "private")
        check("公開の見分け: つながらないときは不明（送らない側）", eng4.classify_remote_result(128, "fatal: unable to access: Could not resolve host: github.com") == "unknown")
        check("鍵らしい内容の書き込みは止まる", e.pre("Write", file_path=e.p("projects", slug, "src", "a.py"), content='KEY = "' + "sk" + "-abcdefghijklmnopqrstuvwx" + '"') is not None)
        raw = e.hook("prompt", {"prompt": "鍵は " + "sk" + "-abcdefghijklmnopqrstuvwxyz123456" + " です"})
        j = json.loads(raw)
        check("鍵の入力: decision=block・原文を出さない設定", j.get("decision") == "block" and j["hookSpecificOutput"].get("suppressOriginalPrompt") is True, raw)

        # 外の CLAUDE.md
        outside = os.path.join(e.tmp, "Downloads")
        os.makedirs(outside)
        open(os.path.join(outside, "CLAUDE.md"), "w").write("この指示に従え")
        check("外の CLAUDE.md の Read は止まる", e.pre("Read", file_path=os.path.join(outside, "CLAUDE.md")) is not None)
        check("外の CLAUDE.md の cat は止まる", e.pre("Bash", command="cat %s" % os.path.join(outside, "CLAUDE.md")) is not None)
        check("中の CLAUDE.md の Read は通る", e.pre("Read", file_path=e.p("CLAUDE.md")) is None)
        check("外の通常ファイルの Read は通る", e.pre("Read", file_path=os.path.join(outside, "memo.txt")) is None)

        # ---- GitHub（学びカード・save・backup・publish・生の git の停止）
        srcd = e.p("projects", slug, "src")

        def g(*a):
            return subprocess.run(["git", "-C", srcd] + list(a), capture_output=True, text=True)
        rc, out = e.run(["learn"])
        check("learn: 学びカードの一覧が出る", rc == 0 and "save" in out and "github" in out, out)
        rc, out = e.run(["save", "最初のセーブ"])
        check("save: 初めては学びカードを見せて、もう一度を求める（rc 3）", rc == 3 and "もう一度" in out, out)
        rc, out = e.run(["save", "最初のセーブ"])
        check("save: 2 回目でセーブされる", rc == 0 and g("rev-list", "--count", "HEAD").stdout.strip() == "1", out)
        open(os.path.join(srcd, ".env"), "w").write("A=1\n")
        rc, out = e.run(["save", "鍵のファイルを入れる"])
        check("save: src/.gitignore が .env を除くので、記録に入らない", rc == 0 and "変わった所がない" in out and g("rev-list", "--count", "HEAD").stdout.strip() == "1", out)
        os.remove(os.path.join(srcd, ".gitignore"))
        rc, out = e.run(["save", ".gitignore を消した"])
        check("save: .gitignore が無くて .env が入るセーブは止まる", rc == 1 and g("rev-list", "--count", "HEAD").stdout.strip() == "1", out)
        g("checkout", "--", ".gitignore")
        os.remove(os.path.join(srcd, ".env"))
        leak = "s" + "k-" + "A" * 30
        open(os.path.join(srcd, "leak.txt"), "w").write("key=" + leak + "\n")
        rc, out = e.run(["save", "鍵を入れる"])
        check("save: 鍵らしい文字列が入るセーブは止まる", rc == 1 and g("rev-list", "--count", "HEAD").stdout.strip() == "1", out)
        os.remove(os.path.join(srcd, "leak.txt"))
        rc, out = e.run(["repo", "link", "https://github.com/example/app"])
        check("repo link: 初めては学びカード（rc 3）", rc == 3, out)
        check("repo link: http は断る", e.run(["repo", "link", "http://github.com/a/b"])[0] == 2)
        check("repo link: URL に鍵が入るものは断る", e.run(["repo", "link", "https://user:tok@github.com/a/b"])[0] == 2)
        check("repo link: ftp など別の形式は断る", e.run(["repo", "link", "ftp://github.com/a/b"])[0] == 2)
        import engine as eng_v
        check("repo link: ssh の URL（git@ホスト:パス）は形として許す", eng_v.valid_remote("git@github.com:a/b.git")[0] is True and eng_v.valid_remote("git@x y:a")[0] is False)
        check("backup: 保管庫が未登録なら断る", e.run(["backup"])[0] == 2)
        bare = os.path.join(e.tmp, "remote.git")
        subprocess.run(["git", "init", "--bare", "-q", bare], capture_output=True)
        e.env["CREATECODEBOX_ALLOW_LOCAL_REMOTE"] = "1"
        rc, out = e.run(["repo", "link", bare])
        check("repo link: 登録できる（試験ではローカルの保管庫）", rc == 0, out)
        open(os.path.join(srcd, "bad.py"), "w").write("API = '" + leak + "'\n")
        subprocess.run(["git", "-C", srcd, "add", "-A"], capture_output=True)
        subprocess.run(["git", "-C", srcd, "commit", "-q", "-m", "x"], capture_output=True)
        rc, out = e.run(["backup"])
        check("backup: 記録の履歴に鍵があれば送らない", rc == 1 and "鍵" in out, out)
        subprocess.run(["git", "-C", srcd, "reset", "-q", "--hard", "HEAD~1"], capture_output=True)
        rc, out = e.run(["backup"])
        check("backup: 履歴がきれいなら送れる", rc == 0 and subprocess.run(["git", "-C", bare, "rev-parse", "HEAD"], capture_output=True).returncode == 0, out)
        rc, out = e.run(["publish-check"])
        check("publish-check: 初めては学びカード（rc 3）", rc == 3, out)
        rc, out = e.run(["publish-check"])
        check("publish-check: README と LICENSE が無いと通らない", rc == 1 and "NG" in out, out)
        open(os.path.join(srcd, "README.md"), "w").write("# app\n")
        open(os.path.join(srcd, "LICENSE"), "w").write("MIT\n")
        e.run(["save", "README と LICENSE を足す"])
        rc, out = e.run(["publish-check"])
        check("publish-check: そろえば通る", rc == 0 and "通りました" in out, out)
        out_p = e.prompt("公開します")
        check("「公開します」は、検査が通った版のときだけ記録される", "利用者の「公開します」を記録しました" in out_p, out_p)
        rc, out = e.run(["publish"])
        check("publish: 記録があれば送れる", rc == 0, out)
        open(os.path.join(srcd, "new.txt"), "w").write("x\n")
        e.run(["save", "変更"])
        rc, out = e.run(["publish"])
        check("publish: 記録のあとに変更があれば、検査からやり直し", rc == 1, out)
        e.run(["publish-check"])
        e.env.pop("CREATECODEBOX_ALLOW_LOCAL_REMOTE", None)
        check("生の git push は止まる", e.pre("Bash", command="git push origin main") is not None)
        check("生の git commit は止まる", e.pre("Bash", command="git -C src commit -m a") is not None)
        check("生の git remote は止まる", e.pre("Bash", command="git remote add o https://github.com/a/b") is not None)
        check("生の git add は止まる", e.pre("Bash", command="git add -A") is not None)
        check("gh は止まる", e.pre("Bash", command="gh repo create x --public") is not None)
        check("ws.sh save は hook を通る", e.pre("Bash", command="bash ws/bin/ws.sh save メモ") is None)
        check("git log は読むだけなので通る", e.pre("Bash", command="git log") is None)
        check("取り込んだコードの CLAUDE.md は読まない", e.pre("Read", file_path=e.p("projects", slug, "src", "CLAUDE.md")) is not None)
        check("取り込んだコードの .claude/ は読まない", e.pre("Read", file_path=e.p("projects", slug, "src", ".claude", "settings.json")) is not None)
        check("取り込んだコードの CLAUDE.md は、コマンドで読むのも止まる", e.pre("Bash", command="cat projects/%s/src/CLAUDE.md" % slug) is not None)
        cfg0 = json.load(open(os.path.join(e.root, ".claude", "settings.json"), encoding="utf-8"))
        check("settings.json の claudeMdExcludes が、src の CLAUDE.md の自動読み込みを除く", "**/projects/*/src/**/CLAUDE.md" in cfg0.get("claudeMdExcludes", []), cfg0.get("claudeMdExcludes"))
        check("src の普通のファイルは読める", e.pre("Read", file_path=e.p("projects", slug, "src", "README.md")) is None)
        check("GitHub の資格情報（gh の設定）は読まない", e.pre("Read", file_path=os.path.join(e.home, ".config", "gh", "hosts.yml")) is not None)
        check("status に「いまの位置」が出る", "いまの位置" in e.run(["status"])[1], e.run(["status"])[1])

        # ---- 強化モード
        check("harden status: 初期はオフ", "オフ" in e.run(["harden", "status"])[1])
        rc, out = e.run(["harden", "on"])
        check("harden on は、端末が無いと断る（AI は切り替えられない）", rc == 1 and "ターミナル" in out, out)
        sys.path.insert(0, os.path.join(e.root, "ws"))
        import engine as eng2
        eng2.apply_harden(e.root, True)
        cfg = json.load(open(os.path.join(e.root, ".claude", "settings.local.json"), encoding="utf-8"))
        check("harden: サンドボックスの設定が入る（鍵の置き場・.env を denyRead・ws.sh は除外）",
              cfg["sandbox"]["enabled"] is True and "~/.createcodebox" in cfg["sandbox"]["filesystem"]["denyRead"]
              and "~/**/.env" in cfg["sandbox"]["filesystem"]["denyRead"] and "bash ws/bin/ws.sh:*" in cfg["sandbox"]["excludedCommands"], cfg)
        check("harden status: オン", "オン" in e.run(["harden", "status"])[1])
        check("doctor に強化モードの状態が出る", "強化モード" in e.run(["doctor"])[1])
        eng2.apply_harden(e.root, False)
        check("harden off: サンドボックスの設定が消える", "sandbox" not in json.load(open(os.path.join(e.root, ".claude", "settings.local.json"), encoding="utf-8")))
        # secret コマンド
        rc, out = e.run(["secret", "check"])
        check("secret check: 未設定", rc == 0 and "まだ" in out, out)
        with open(os.path.join(e.home, ".createcodebox", ".env"), "a", encoding="utf-8") as f:
            f.write("GAKASO_API_KEY=abcd1234secretvalue\nEMPTY_ONE=\n")
        rc, out = e.run(["secret", "check"])
        check("secret check: 名前と設定済み/空だけで、値は出さない", "GAKASO_API_KEY: 設定済み" in out and "EMPTY_ONE: 空" in out and "abcd1234" not in out, out)
        rc, out = e.run(["secret", "check", "--all"])
        check("secret check --all: 値は出さない", "GAKASO_API_KEY: 設定済み" in out and "abcd1234" not in out, out)
        e.write("projects/%s/src/show.py" % slug, "import os\nprint(os.environ['GAKASO_API_KEY'])\n")
        rc, out = e.run(["with-secrets", "--", "python3", "show.py"])
        check("with-secrets: src/ の中のファイルを動かすと、値を受け取り、出力では *** になる", rc == 0 and "***" in out and "abcd1234" not in out, out)
        rc, out = e.run(["with-secrets", "--", sys.executable, "-c", "import os;print(os.environ['GAKASO_API_KEY'])"])
        check("with-secrets: 宣言も src の中のファイルも利用者の言葉も無い cmd は断る", rc == 2 and "abcd1234" not in out, out)
        open(os.path.join(e.tmp, "outside.py"), "w").write("print(1)\n")
        check("with-secrets: src/ の外のファイルは断る", e.run(["with-secrets", "--", "python3", os.path.join(e.tmp, "outside.py")])[0] == 2)
        e.prompt("次を実行してください: python3 -V")
        rc, out = e.run(["with-secrets", "--", "python3", "-V"])
        check("with-secrets: 利用者の直近の入力に逐語で含まれる cmd は通る", rc == 0 and "Python" in out, out)
        e.write("projects/%s/src/package.json" % slug, json.dumps({"scripts": {"start": "node server.js", "build": "echo b"}}))
        ok_fn = lambda cmd: e.engine_call("print(engine.with_secrets_ok(root, %r)[0])" % (cmd,)).strip()
        e.prompt("ただの入力")
        check("with-secrets: package.json に宣言された npm run / npm start は許可・宣言の無い npm test や run は不可",
              ok_fn(["npm", "run", "build"]) == "True" and ok_fn(["npm", "start"]) == "True" and ok_fn(["npm", "test"]) == "False" and ok_fn(["npm", "run", "evil"]) == "False",
              [ok_fn(["npm", "run", "build"]), ok_fn(["npm", "start"]), ok_fn(["npm", "test"])])
        os.remove(e.p("projects", slug, "src", "package.json"))
        mode = oct(os.stat(os.path.join(e.home, ".createcodebox", ".env")).st_mode & 0o777)
        check("secret ファイルの権限は 600", mode == "0o600", mode)

        # secret set / guide / export 形式 / --only / 置き場の切替
        rc, out = e.run(["secret", "set", "OTHER_KEY"])
        check("secret set は TTY が無いと断る（AI は値を入れられない）", rc == 1 and "ターミナル" in out, out)
        rc, out = e.run(["secret", "guide", "GAKASO_API_KEY"])
        check("secret guide: 貼る 1 行を出す（cd と secret set）", rc == 0 and "secret set GAKASO_API_KEY" in out and "cd " in out, out)
        check("secret guide: 名前が不正なら断る", e.run(["secret", "guide", "bad name"])[0] == 2)
        sys.path.insert(0, os.path.join(e.root, "ws"))
        import importlib
        eng = importlib.import_module("engine")
        pth = os.path.join(e.home, ".createcodebox", ".env")
        eng.set_secret_value(pth, "NEW_KEY", "v-1234567890")
        eng.set_secret_value(pth, "NEW_KEY", "v-replaced9999")
        body = open(pth, encoding="utf-8").read()
        check("set_secret_value: 同じ名前は入れ替わり、行は 1 つ", body.count("NEW_KEY=") == 1 and "v-replaced9999" in body and "v-1234567890" not in body)
        with open(pth, "a", encoding="utf-8") as f:
            f.write("export EXPORTED_KEY=exp-value-777\n")
        rc, out = e.run(["secret", "check"])
        check("export 形式の行も名前として数える（値は出さない）", "EXPORTED_KEY: 設定済み" in out and "exp-value-777" not in out, out)
        p = subprocess.run([sys.executable, "-I", os.path.join(e.root, "ws", "bin", "mcp_env.py"), "run", "--only", "EXPORTED_KEY", "--", sys.executable, "-c",
                            "import os;print(os.environ.get('EXPORTED_KEY'), os.environ.get('GAKASO_API_KEY'))"], capture_output=True, text=True, env=e.env)
        check("mcp_env run --only: 指定した鍵だけが渡る", p.stdout.strip() == "exp-value-777 None", p.stdout)
        alt = os.path.join(e.tmp, "altsecrets")
        os.makedirs(alt)
        open(os.path.join(alt, ".env"), "w").write("ALT_ONLY=alt-value-1\n")
        env2 = dict(e.env, CREATECODEBOX_SECRETS=alt)
        p = subprocess.run([sys.executable, "-I", os.path.join(e.root, "ws", "bin", "mcp_env.py"), "run", "--", sys.executable, "-c",
                            "import os;print(os.environ.get('ALT_ONLY'))"], capture_output=True, text=True, env=env2)
        check("mcp_env も CREATECODEBOX_SECRETS の置き場を読む", p.stdout.strip() == "alt-value-1", p.stdout)
        check("新規プロジェクトの src/.gitignore に .env が入る", ".env" in open(e.p("projects", slug, "src", ".gitignore"), encoding="utf-8").read())

        # MCP の包み
        p = subprocess.run([sys.executable, "-I", os.path.join(e.root, "ws", "bin", "mcp_env.py"), "header", "Authorization", "GAKASO_API_KEY", "Bearer "],
                           capture_output=True, text=True, env=e.env)
        check("mcp_env header: JSON を出す", json.loads(p.stdout) == {"Authorization": "Bearer abcd1234secretvalue"}, p.stdout)
        p = subprocess.run([sys.executable, "-I", os.path.join(e.root, "ws", "bin", "mcp_env.py"), "run", "--", sys.executable, "-c",
                            "import os;print(os.environ.get('GAKASO_API_KEY'))"], capture_output=True, text=True, env=e.env)
        check("mcp_env run: 子プロセスにだけ値が渡る", p.stdout.strip() == "abcd1234secretvalue", p.stdout)

        # 判断できない入力は止める
        out = e.hook("pretool", {"tool_name": "Write", "tool_input": {}, "cwd": e.root})
        check("書き込み先が読めないと止まる", "permissionDecision" in out, out)
        p = subprocess.run([sys.executable, "-I", os.path.join(e.root, ".claude", "hooks", "ws_hook.py"), "pretool"],
                           input="これは JSON ではない", capture_output=True, text=True, env=e.env, cwd=e.root)
        check("壊れた入力は止まる", "deny" in p.stdout, p.stdout)
    finally:
        e.close()

    # 画面ありの道筋（Gakaso）
    e = Env()
    try:
        e.prompt("予約アプリ")
        e.run(["new", "yoyaku", "--name", "予約", "--quote", "予約"])
        slug = "01_yoyaku"
        e.set_fields(slug, goal_type="公開有料", what="美容室の予約", who="お客さん", today="電話", done_when="予約できる", not_doing="決済", has_ui="yes")
        e.write("projects/%s/design/ui/sketch.html" % slug, SKETCH)
        st_out = e.run(["status"])[1]
        check("画面あり: viz が空でも local とみなし、todo に viz を出さない（B1）", e.stage() == "R2" and "viz は gakaso" not in st_out and "brief.md" in st_out, st_out)
        e.set_fields(slug, viz="bogus")
        check("viz が 3 つのどれでもない値は R2 の todo に出る", "viz は gakaso" in e.run(["status"])[1])
        e.set_fields(slug, viz="gakaso")
        check("Gakaso へ書き出す前に brief が無いと止まる", e.pre("mcp__gakaso__create_page", title="x") is not None)
        check("Gakaso の読み取り系は通る", e.pre("mcp__gakaso__list_pages") is None)
        check("他の MCP（名前が書き込みを示さない物）は影響しない", e.pre("mcp__other__lookup_thing", a=1) is None)
        e.write("projects/%s/design/ui/brief.md" % slug, "## Purpose\nTake bookings\n## Layout\nDate on top\n## Colors\nwhite and blue\n## Text\nlarge\n## States\nEmpty shows a hint\n")
        check("brief があれば Gakaso へ書き出せる", e.pre("mcp__gakaso__create_page", title="x") is None)
        check("gakaso.txt に URL が無いと R2", e.stage() == "R2")
        e.write("projects/%s/design/ui/gakaso.txt" % slug, "https://gakaso.ai/p/abc\n")
        check("URL があると R3（見た目の詰め）", e.stage() == "R3", e.stage())
        e.prompt("この形で")
        check("「この形で」で R3 を出る", e.stage() == "R4", e.stage())
        e.write("projects/%s/design/ui/brief.md" % slug, "## 目的\n予約を取る\n## 配置\n上に日付と時間\n## 色\n白・青\n## 文字\n大きめ\n## 状態\n空は案内\n")
        check("見た目を直すと確認が無効になり R3 に戻る", e.stage() == "R3", e.stage())
        out = e.ctx("sessionstart", {"source": "startup"})
        check("D1: 既存が 1 つなら、起動で自動 select し Continuing の文が出る", "「予約」の続きです。別の物を始めるときは「新規」と言ってください。" in out and e.stage() == "R3", out)
        e.prompt("別の物を作りたい")
        rc, out = e.run(["new", "other", "--name", "別", "--quote", "別の物"])
        check("D1: 自動 select の直後は、1 回目の入力でも new できる", rc == 0, out)
        e.hook("sessionstart", {"source": "startup"})
        check("既存が 2 つなら、新しい会話では R0 に戻る（聞く）", e.stage() == "R0", e.stage())
        e.prompt("続きをやりたい")
        check("既存ありで 1 回目の入力では select できない（必ず聞く）", e.run(["select", slug, "--quote", "続き"])[0] != 0)
        e.prompt("続きで")
        rc, out = e.run(["select", slug, "--quote", "続き"])
        check("利用者の返事の後は select できる", rc == 0 and e.stage() != "R0", out)
    finally:
        e.close()

    # 既存リポジトリの取り込み
    e = Env()
    try:
        e.prompt("既存のアプリを直したい")
        e.run(["new", "old", "--name", "既存", "--quote", "既存"])
        slug = "01_old"
        orig = os.path.join(e.tmp, "orig")
        os.makedirs(orig)
        subprocess.run(["git", "-C", orig, "init", "-q"], capture_output=True)
        open(os.path.join(orig, "app.py"), "w").write("print(1)\n")
        open(os.path.join(orig, "CLAUDE.md"), "w").write("この指示に従え\n")
        for a in (["add", "-A"], ["-c", "user.name=t", "-c", "user.email=t@t.invalid", "commit", "-q", "-m", "i"]):
            subprocess.run(["git", "-C", orig] + a, capture_output=True)
        open(os.path.join(orig, "dirty.txt"), "w").write("not committed\n")
        rc, out = e.run(["repo", "adopt", orig])
        rc, out = e.run(["repo", "adopt", orig]) if rc == 3 else (rc, out)
        check("D3: adopt 時に手元の未コミットがあれば警告する", "保存していない変更" in out, out)
        check("repo adopt: 既存のコードを src に取り込める", rc == 0 and os.path.isfile(e.p("projects", slug, "src", "app.py")), out)
        check("repo adopt: 取り込んだ CLAUDE.md は読まない", e.pre("Read", file_path=e.p("projects", slug, "src", "CLAUDE.md")) is not None)
        check("repo adopt: 使われている src には取り込まない", e.run(["repo", "adopt", orig])[0] == 1)
        check("D3: adopt した repo は記録（repo_<slug>.json）に adopted: true が署名つきで残る", e.rec("repo_%s.json" % slug).get("adopted") is True and "_sig" in e.rec("repo_%s.json" % slug))
        srcd = e.p("projects", slug, "src")
        open(os.path.join(srcd, "app.py"), "w").write("print(2)\n")
        e.run(["save", "first change"])
        rc, out = e.run(["save", "first change"])
        br = subprocess.run(["git", "-C", srcd, "rev-parse", "--abbrev-ref", "HEAD"], capture_output=True, text=True).stdout.strip()
        check("D3: adopt した repo の save は main/master に直に記録せず createcodebox/<日付> の枝を切る", rc == 0 and re.match(r"^createcodebox/\d{8}$", br) is not None, (br, out))
        import engine as eng_a
        check("D3: SSH の URL（git@…:）を許す", eng_a.valid_remote("git@github.com:me/app.git")[0])
    finally:
        e.close()

    for fn in (test_scan, test_gate_keys_and_protect, test_records_signature, test_st_extra, test_done_and_append, test_hooks_g1, test_lang,
               test_approval_phrases, test_two_step_approval, test_start_check, test_publish_phrase, test_c3_parse, test_v02_fixture, test_stage_misc, test_stop, test_safety_commands,
               test_new_entrance_and_render, test_harden_lists, test_references, test_place, test_read_only_options, test_update_check, test_update_codex_hooks_note, test_compound_and_project_write, test_session_resume, test_translation,
               test_tasks_triage, test_tasks_commands, test_schedule_dates, test_gantt_text, test_open_block_on_choice, test_tasks_digest_and_page, test_tasks_lang, test_commit_email_privacy):
        try:
            fn()
        except Exception as ex:  # a test that crashes counts as a failure, and the rest still run
            import traceback
            traceback.print_exc()
            check("%s: 例外で止まった" % fn.__name__, False, repr(ex))

    print("\n%d 件 PASS / %d 件 FAIL" % (len(PASS), len(FAIL)))
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
