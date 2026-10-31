#!/usr/bin/env python3
"""MCP に秘密の値を渡す小さな包み。値は ~/.createcodebox/.env から読み、必要な 1 つのプロセスだけに渡す。

使い方（.mcp.json から呼ぶ）:
  stdio 型:  "command": "python3", "args": ["ws/bin/mcp_env.py", "run", "--only", "<必要な鍵の名前,…>", "--", "<MCP を起動するコマンド>", ...]（--only を付けると、その名前の鍵だけを渡す）
  HTTP 型:   "headersHelper": "python3 ws/bin/mcp_env.py header Authorization GAKASO_API_KEY 'Bearer '"
値を標準出力・標準エラー・ファイルに書かない（header は、Claude Code に渡す JSON だけを出す）。
"""
import json
import os
import re
import sys

def secret_path():
    o = os.environ.get("CREATECODEBOX_SECRETS")
    base = os.path.expanduser(o) if o else os.path.join(os.path.expanduser("~"), ".createcodebox")
    return os.path.join(base, ".env")


def load():
    env = {}
    try:
        with open(secret_path(), encoding="utf-8") as f:
            for line in f:
                m = re.match(r"^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*?)\s*$", line)
                if m and not line.lstrip().startswith("#"):
                    v = m.group(2)
                    if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
                        v = v[1:-1]
                    if v:
                        env[m.group(1)] = v
    except OSError:
        pass
    return env


def main(argv):
    only = None
    if len(argv) >= 3 and argv[0] == "run" and argv[1] == "--only":
        only = set(x for x in argv[2].split(",") if x)
        argv = ["run"] + argv[3:]
    if len(argv) >= 3 and argv[0] == "run" and argv[1] == "--":
        env = dict(os.environ)
        secrets = load()
        if only is not None:
            secrets = {k: v for k, v in secrets.items() if k in only}
        env.update(secrets)
        os.execvpe(argv[2], argv[2:], env)
    if len(argv) >= 3 and argv[0] == "header":
        name, var = argv[1], argv[2]
        prefix = argv[3] if len(argv) > 3 else ""
        v = load().get(var)
        if not v:
            sys.stderr.write("秘密の値 %s がまだ設定されていません。`bash ws/bin/ws.sh secret open` で設定してください。\n" % var)
            return 1
        print(json.dumps({name: prefix + v}))
        return 0
    sys.stderr.write("使い方: mcp_env.py run -- <コマンド> ... | header <ヘッダー名> <変数名> [前置き]\n")
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
