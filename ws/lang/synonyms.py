"""Old Japanese values and display names -> internal English symbols. The engine reads any of them and writes symbols."""
import re
import unicodedata

GOAL_TYPES = ["self", "share", "public-free", "public-paid", "unknown"]
IO_KINDS = ["screen", "file", "api", "db", "external", "scheduled"]
VIZ = ["gakaso", "artifact", "local"]
BRIEF_SECTIONS = ["purpose", "layout", "color", "text", "state"]

_GOAL = {
    "self": ["self", "just for me", "for me", "for myself", "only me", "only for me", "自分用", "自分で使うだけ", "自分で使う", "自分だけ", "自分用です", "自分だけで使う",
             "自分だけが使う", "自分のため", "自分だけです"],
    "share": ["share", "show to others", "show others", "friends only", "friends-only", "for friends", "friends and family", "family", "見せる", "身近な人に見せる", "人に見せる",
              "身近な人だけ", "家族に見せる", "友だちに見せる", "友達に見せる", "家族や友だちに見せる", "家族や友達に見せる", "人に見せます"],
    "public-free": ["public-free", "public free", "public, free", "public and free", "free public", "公開無料", "公開して無料", "公開(無料)"],
    "public-paid": ["public-paid", "public paid", "public, paid", "public and paid", "paid public", "公開有料", "公開して有料", "公開(有料)"],
    "unknown": ["unknown", "not sure", "not sure yet", "undecided", "tbd", "未定", "まだ分からない", "まだわからない", "分からない", "わからない", "まだ決めていない",
                "まだ決めてない", "決めていない"],
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


# ---- "I am lost" (0.5.0). A short message that is exactly one of these gets the recap of where the user is. ----
# The engine compares after lower-casing and removing apostrophes (i'm -> im), filler words around the phrase, and polite
# Japanese endings (ですか, ください, ています, ました). A longer sentence that only contains one of these is not a lost message.
LOST_EN = {
    "help", "help me", "i need help", "need help", "im lost", "i am lost", "lost", "stuck", "im stuck", "i am stuck", "what now", "now what",
    "what next", "whats next", "what is next", "what do i do", "what should i do", "what do i do now", "what do i do next", "what should i do next",
    "what should i do now", "what am i supposed to do", "where am i", "i dont know what to do", "i do not know what to do", "not sure what to do",
    "confused", "im confused", "i am confused",
}
LOST_JA = {
    "迷った", "迷いました", "迷っ", "迷って", "迷子", "ヘルプ", "助けて", "どうすれば", "どうすればいい", "どうしたらいい", "どうしよう", "次は", "次は何", "次は何をすれば",
    "次は何をすればいい", "次は何をしたらいい", "次に何をすればいい", "次どうする", "次どうすればいい", "何をすれば", "何をすればいい", "何すればいい", "今どこ", "いまどこ",
    "わからない", "分からない", "わかりません", "分かりません", "わからなくなった", "分からなくなった", "わからなくなり", "分からなくなり", "困った", "困っ", "困って", "困り",
}
# ---- the answers to the goal question at the end (short, exact lists) ----
# yes: narrow on purpose. "yes please", "y" or 「お願いします」 answer some other question, so they are not here.
GOAL_YES_EN = {"yes", "yes it does", "yes, it does", "it does"}
GOAL_YES_JA = {"はい", "できた", "できました", "届いた", "届きました", "そうです", "はい、そうです", "はいそうです", "はい、できました", "はいできました"}
GOAL_NO_EN = {"no", "not yet", "no, not yet", "no not yet", "not yet, no"}
GOAL_NO_JA = {"まだ", "まだです", "いいえ", "いいえ、まだです", "いいえまだです"}
# "not yet" alone (no bare "no"): the words that take back an earlier yes without a question before them
GOAL_NOT_YET_EN = {"not yet", "no, not yet", "no not yet", "not yet, no"}
GOAL_NOT_YET_JA = {"まだ", "まだです", "いいえ、まだです", "いいえまだです"}
