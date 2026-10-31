"""Message tables for CreateCodeBox. English (en.py) is the source; other languages fall back to it.

T(msg_id, **kw): look up in the current language, then in en, then return msg_id itself (never raises).
Placeholders are named: {name}. A missing name leaves the placeholder as it is.
"""
import importlib
import os
import re
import unicodedata

_CUR = None
_CACHE = {}
_CJK = re.compile("[぀-ヿ㐀-䶿一-鿿豈-﫿]")
_LATIN = re.compile("[A-Za-z]")


def use(code):
    """Set the language used by T() in this process (en / ja). Anything else is ignored."""
    global _CUR
    _CUR = code if isinstance(code, str) and re.match(r"^[a-z]{2,5}$", code) else None


def current():
    c = _CUR or os.environ.get("CREATECODEBOX_LANG") or "en"
    return c if re.match(r"^[a-z]{2,5}$", c) else "en"


def _table(code):
    if code in _CACHE:
        return _CACHE[code]
    try:
        mod = importlib.import_module("." + code, __name__)
        tbl = getattr(mod, "MESSAGES", {}) or {}
    except Exception:
        tbl = {}
    _CACHE[code] = tbl
    return tbl


def _fmt(s, kw):
    if not kw:
        return s
    return re.sub(r"\{([A-Za-z_][A-Za-z0-9_]*)\}", lambda m: str(kw[m.group(1)]) if m.group(1) in kw else m.group(0), s)


def T(msg_id, **kw):
    s = _table(current()).get(msg_id)
    if not isinstance(s, str) or not s:
        s = _table("en").get(msg_id)
    if not isinstance(s, str) or not s:
        s = msg_id
    return _fmt(s, kw)


def labels(*prefixes):
    """{short key: text in the current language} for every English key that starts with one of the prefixes.
    Used to pass the words of an HTML page as JSON. Placeholders ({n}) are left for the page to fill."""
    out = {}
    for k in _table("en"):
        for p in prefixes:
            if k.startswith(p):
                out[k[len(p):]] = T(k)
    return out


def nfkc(s):
    return unicodedata.normalize("NFKC", s or "")


def has_cjk(s):
    return bool(_CJK.search(s or ""))


def detect(text, default=None):
    """ja if the text has hiragana, katakana or kanji; en if it has Latin letters; else default."""
    if _CJK.search(text or ""):
        return "ja"
    if _LATIN.search(text or ""):
        return "en"
    return default or "en"
