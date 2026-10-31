"""Old Japanese values and display names -> internal English symbols. The engine reads any of them and writes symbols."""
import re
import unicodedata

GOAL_TYPES = ["self", "share", "public-free", "public-paid", "unknown"]
IO_KINDS = ["screen", "file", "api", "db", "external", "scheduled"]
VIZ = ["gakaso", "artifact", "local"]
BRIEF_SECTIONS = ["purpose", "layout", "color", "text", "state"]

_GOAL = {
    "self": ["self", "just for me", "for me", "for myself", "only me", "自分用", "自分で使うだけ", "自分で使う"],
    "share": ["share", "show to others", "show others", "friends only", "friends-only", "for friends", "見せる", "身近な人に見せる", "人に見せる"],
    "public-free": ["public-free", "public free", "public, free", "public and free", "free public", "公開無料", "公開して無料", "公開(無料)"],
    "public-paid": ["public-paid", "public paid", "public, paid", "public and paid", "paid public", "公開有料", "公開して有料", "公開(有料)"],
    "unknown": ["unknown", "not sure", "not sure yet", "undecided", "tbd", "未定", "まだ分からない", "まだわからない", "分からない"],
}
_KIND = {
    "screen": ["screen", "ui", "page", "画面"],
    "file": ["file", "files", "ファイル"],
    "api": ["api"],
    "db": ["db", "database", "data base"],
    "external": ["external", "external service", "外部"],
    "scheduled": ["scheduled", "schedule", "cron", "timer", "定期"],
}
_BRIEF = {
    "purpose": ["purpose", "目的"],
    "layout": ["layout", "配置"],
    "color": ["color", "colour", "colors", "色"],
    "text": ["text", "type", "文字"],
    "state": ["state", "states", "状態"],
}
_YES = {"yes", "y", "true", "はい", "有", "あり"}
_NO = {"no", "n", "false", "いいえ", "無", "なし"}
_BRACKETS = "()（）[]［］{}｛｝「」『』\"'`“”‘’<>＜＞"


def _clean(v):
    v = unicodedata.normalize("NFKC", v or "").strip().lower()
    v = re.sub(r"[*_]{2,}", "", v).strip("*` \t")
    v = re.sub(r"[\s。．.、,!！?？;；:：]+$", "", v)
    return re.sub(r"\s+", " ", v)


def _candidates(v):
    v = unicodedata.normalize("NFKC", v or "")
    out = [_clean(v)]
    out.append(_clean("".join(" " if ch in _BRACKETS else ch for ch in v)))
    m = re.match(r"^\s*([^(\[（［]+?)\s*[(\[（［]", v)
    if m:
        out.append(_clean(m.group(1)))
    m = re.search(r"[(\[（［]\s*([^)\]）］]+?)\s*[)\]）］]", v)
    if m:
        out.append(_clean(m.group(1)))
    out.append(_clean(v.split("/")[0].split("・")[0].split("／")[0]))
    return [x for x in out if x]


def _lookup(table, v):
    for cand in _candidates(v):
        for sym, names in table.items():
            if cand == sym or cand in [unicodedata.normalize("NFKC", n).lower() for n in names]:
                return sym
    return None


def goal_symbol(v):
    return _lookup(_GOAL, v)


def kind_symbol(v):
    return _lookup(_KIND, v)


def brief_symbol(heading):
    """'## 目的（purpose）' -> 'purpose'. Matches by the start of the heading (as the old check did)."""
    h = _clean(heading)
    cands = _candidates(heading)
    for sym, names in _BRIEF.items():
        for n in names:
            n = unicodedata.normalize("NFKC", n).lower()
            if any(c == n or c.startswith(n) for c in cands) or h.startswith(n):
                return sym
    return None


def yesno(v):
    for cand in _candidates(v):
        if cand in _YES:
            return "yes"
        if cand in _NO:
            return "no"
    return None


def viz_symbol(v):
    for cand in _candidates(v):
        if cand in VIZ:
            return cand
    return None
