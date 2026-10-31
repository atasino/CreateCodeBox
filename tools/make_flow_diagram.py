#!/usr/bin/env python3
"""Write the CreateCodeBox flow diagram as four SVG files (en/ja x light/dark).

Usage:
  python3 tools/make_flow_diagram.py             write docs/img/flow-{en,ja}-{light,dark}.svg
  python3 tools/make_flow_diagram.py --check     check the table and the output (exit 1 on any problem)
  python3 tools/make_flow_diagram.py --print-alt print the alt text and the README snippet (en and ja)

Standard library only (Python 3.8 or newer). The same input gives the same bytes.
All words in the diagram come from the one table (TABLE) below. A word in `backticks`
is something the user types and is drawn in a monospace font.
"""
import os
import re
import sys
import xml.etree.ElementTree as ET

# ---------------------------------------------------------------- the one table
# Each stage: name, claude (lines), turn (lines, or None when the user has no turn).
# A cell is a list of lines. English and Japanese must have the same keys.
TABLE = {
    "en": {
        "lang": "en",
        "title": ["After setup: six stages"],
        "legend_claude": "Claude",
        "legend": "Your turn",
        "note": "Claude may ask a few more short questions in between.",
        "alt": ("How CreateCodeBox goes after setup, in six stages. "
                "Ask: you say what you want to make. "
                "Reference: you name a close site or app. "
                "Prototype: you say what is most different, then type looks good. "
                "Approve: you type approve. "
                "Build: Claude builds one step at a time. "
                "Check: you tell Claude which numbered checks worked."),
        "stages": [
            {"name": "Ask",
             "claude": ["Asks short questions"],
             "turn": ["Say what you want to make"]},
            {"name": "Reference",
             "claude": ["Asks about a close site or app"],
             "turn": ["Name a close site or app"]},
            {"name": "Prototype",
             "claude": ["Shows a first version of the screen"],
             "turn": ["Say what is most different,", "then type `looks good`"]},
            {"name": "Approve",
             "claude": ["Shows the table and the design"],
             "turn": ["Type `approve`"]},
            {"name": "Build",
             "claude": ["Builds one step at a time"],
             "turn": None},
            {"name": "Check",
             "claude": ["Gives a numbered list to check"],
             "turn": ["Tell Claude which numbers worked"]},
        ],
    },
    "ja": {
        "lang": "ja",
        "title": ["準備のあと: 6 つの段階"],
        "legend_claude": "Claude",
        "legend": "あなたの番",
        "note": "ほかに、短い質問が入ることがあります。",
        "alt": ("準備のあとの CreateCodeBox の進み方（6 つの段階）。"
                "聞く: 作りたいものを伝えます。"
                "参考: 近いサイトやアプリを伝えます。"
                "プロトタイプ: いちばん違う所を伝え、looks good と打ちます。"
                "承認: approve と打ちます。"
                "作る: Claude が 1 ステップずつ作ります。"
                "確かめる: うまくいった番号を Claude に伝えます。"),
        "stages": [
            {"name": "聞く",
             "claude": ["短い質問をします"],
             "turn": ["作りたいものを伝える"]},
            {"name": "参考",
             "claude": ["近いサイトやアプリを聞きます"],
             "turn": ["近いサイトやアプリを伝える"]},
            {"name": "プロトタイプ",
             "claude": ["画面の最初の版を見せます"],
             "turn": ["いちばん違う所を伝え、", "`looks good` と打つ"]},
            {"name": "承認",
             "claude": ["表と設計を見せます"],
             "turn": ["`approve` と打つ"]},
            {"name": "作る",
             "claude": ["1 ステップずつ作ります"],
             "turn": None},
            {"name": "確かめる",
             "claude": ["番号つきの確認項目を出します"],
             "turn": ["うまくいった番号を伝える"]},
        ],
    },
}

# ---------------------------------------------------------------- colors (the brand table)
THEMES = {
    "light": {"bg": "#f7f8fa", "main": "#1d2330", "sub": "#4b5565",
              "blue": "#2457d6", "on_blue": "#ffffff", "amber": "#ffb55e", "on_amber": "#1d2330"},
    "dark": {"bg": "#1d2330", "main": "#f7f8fa", "sub": "#aab3c5",
             "blue": "#8fb0ff", "on_blue": "#1d2330", "amber": "#ffb55e", "on_amber": "#1d2330"},
}
# (foreground role, background role, minimum ratio, kind)
TEXT_PAIRS = [("main", "bg"), ("sub", "bg"), ("on_blue", "blue"), ("on_amber", "amber")]
SHAPE_PAIRS = [("blue", "bg")]

SANS = 'system-ui, -apple-system, "Segoe UI", "Hiragino Sans", "Noto Sans JP", "Yu Gothic", "Noto Sans", sans-serif'
MONO = 'ui-monospace, "SF Mono", Menlo, Consolas, "Liberation Mono", monospace'

# ---------------------------------------------------------------- sizes (viewBox px)
W = 800
M = 28                      # outer margin
SZ_TITLE = 32
SZ_NAME = 32
SZ_SUB = 22                 # small English name under the Japanese stage name
SZ_LINE = 24                # Claude line and amber chip text
SZ_NOTE = 22
LH = 30                     # line height for 24px text
CHIP_PAD_X = 8 
CHIP_PAD_Y = 3
CHIP_LH = 28                # line height inside an amber chip
ROW_PAD_Y = 12
ROW_GAP = 36                # space between rows (the arrow lives here)
STROKE = 4                  # the one line width (arrows)
RADIUS_RATIO = 0.17         # box corner radius = 17% of the shorter side (brand: 16-20%)
GROW = 1.15                 # a fallback font may be this much wider
MIN_SIZES = {"title": 32, "name": 32, "line": 24, "turn": 24, "note": 22, "sub": 22, "legend": 24}
MAX_HEIGHT = 1000
MAX_BYTES = 50 * 1024
AMBER_MAX_RATIO = 0.10

OUT_NAMES = [("en", "light"), ("en", "dark"), ("ja", "light"), ("ja", "dark")]


class Problem(Exception):
    pass


# ---------------------------------------------------------------- helpers
def _lum(hexcolor):
    h = hexcolor.lstrip("#")
    out = []
    for i in (0, 2, 4):
        c = int(h[i:i + 2], 16) / 255.0
        out.append(c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4)
    return 0.2126 * out[0] + 0.7152 * out[1] + 0.0722 * out[2]


def contrast(a, b):
    la, lb = _lum(a), _lum(b)
    if la < lb:
        la, lb = lb, la
    return (la + 0.05) / (lb + 0.05)


def esc(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def segments(line):
    """Split a line on `backticks` into (text, is_code) pieces."""
    parts = line.split("`")
    out = []
    for i, p in enumerate(parts):
        if p:
            out.append((p, i % 2 == 1))
    return out


def est_width(line, size, bold=False):
    """Rough width of a line in px. CJK = 1 em, code = 0.62 em, Latin = 0.50 em (0.57 bold)."""
    total = 0.0
    for text, code in segments(line):
        for ch in text:
            o = ord(ch)
            if o >= 0x2E80:
                total += 1.0 * size
            elif code:
                total += 0.62 * size
            else:
                total += (0.57 if bold else 0.50) * size
    return total


def plain(line):
    return line.replace("`", "")


def radius(w, h):
    return round(RADIUS_RATIO * min(w, h), 1)


def num(v):
    s = ("%.1f" % v).rstrip("0").rstrip(".")
    return s


def spans(line):
    """tspans for a line (code pieces in the monospace font)."""
    out = []
    for text, code in segments(line):
        if code:
            out.append('<tspan font-family=\'%s\'>%s</tspan>' % (MONO, esc(text)))
        else:
            out.append(esc(text))
    return "".join(out)


# ---------------------------------------------------------------- the drawing
def render(lang, theme):
    """Return (svg text, stats). stats holds what --check needs."""
    t = TABLE[lang]
    c = THEMES[theme]
    ja = lang == "ja"
    stats = {"fonts": [], "fit": [], "amber_area": 0.0, "height": 0}

    box_w = 262 if ja else 212
    text_x = M + box_w + 18
    text_w = W - M - text_x
    min_row_h = 84 if ja else 64
    en_names = [s["name"] for s in TABLE["en"]["stages"]]

    def fit(label, line, size, avail, bold=False):
        stats["fit"].append((label, plain(line), est_width(line, size, bold) * GROW, avail))

    body = []
    y = 30
    # title
    for i, line in enumerate(t["title"]):
        base = y + 32 + i * 42
        body.append('<text x="%d" y="%d" font-size="%d" font-weight="700" fill="%s">%s</text>'
                    % (M, base, SZ_TITLE, c["main"], spans(line)))
        stats["fonts"].append(("title", SZ_TITLE))
        fit("title", line, SZ_TITLE, W - 2 * M, True)
    y += 32 + (len(t["title"]) - 1) * 42 + 14 + 14      # below the last title line, then a gap

    # legend right under the title: grey "Claude" (the colour of the Claude lines) and the amber "Your turn" chip
    leg_h = CHIP_LH + 2 * CHIP_PAD_Y
    cl_w = est_width(t["legend_claude"], SZ_LINE) * GROW
    body.append('<text x="%d" y="%s" font-size="%d" fill="%s">%s</text>'
                % (M, num(y + CHIP_PAD_Y + 0.5 * CHIP_LH + 0.35 * SZ_LINE), SZ_LINE, c["sub"], esc(t["legend_claude"])))
    stats["fonts"].append(("legend", SZ_LINE))
    leg_x = M + int(round(cl_w)) + 20
    fit("legend", t["legend_claude"], SZ_LINE, leg_x - M - 8)
    leg_w = round(est_width(t["legend"], SZ_LINE) * GROW + 2 * CHIP_PAD_X)
    body.append('<rect x="%d" y="%s" width="%d" height="%d" rx="%s" fill="%s"/>'
                % (leg_x, num(y), leg_w, leg_h, num(radius(leg_w, leg_h)), c["amber"]))
    body.append('<text x="%d" y="%s" font-size="%d" fill="%s">%s</text>'
                % (leg_x + CHIP_PAD_X, num(y + CHIP_PAD_Y + 0.5 * CHIP_LH + 0.35 * SZ_LINE), SZ_LINE, c["on_amber"], esc(t["legend"])))
    stats["amber_area"] += leg_w * leg_h
    stats["fonts"].append(("legend", SZ_LINE))
    fit("legend", t["legend"], SZ_LINE, leg_w - 2 * CHIP_PAD_X)
    y += leg_h + 24

    stages = t["stages"]
    for idx, s in enumerate(stages):
        n_c = len(s["claude"])
        chip_lines = s["turn"] or []
        chip_h = len(chip_lines) * CHIP_LH + 2 * CHIP_PAD_Y if chip_lines else 0
        content_h = n_c * LH + ((6 + chip_h) if chip_lines else 0)
        row_h = max(content_h + 2 * ROW_PAD_Y, min_row_h)
        # stage box
        rx = radius(box_w, row_h)
        body.append('<rect x="%d" y="%s" width="%d" height="%s" rx="%s" fill="%s"/>'
                    % (M, num(y), box_w, num(row_h), num(rx), c["blue"]))
        cx = M + box_w / 2.0
        if ja:
            main_base = y + row_h / 2.0 - 4
            sub_base = main_base + 28
            body.append('<text x="%s" y="%s" font-size="%d" font-weight="700" text-anchor="middle" fill="%s">%s</text>'
                        % (num(cx), num(main_base), SZ_NAME, c["on_blue"], esc(s["name"])))
            body.append('<text x="%s" y="%s" font-size="%d" text-anchor="middle" fill="%s">%s</text>'
                        % (num(cx), num(sub_base), SZ_SUB, c["on_blue"], esc(en_names[idx])))
            stats["fonts"] += [("name", SZ_NAME), ("sub", SZ_SUB)]
            fit("name", s["name"], SZ_NAME, box_w - 20, True)
            fit("sub", en_names[idx], SZ_SUB, box_w - 20)
        else:
            base = y + row_h / 2.0 + 0.35 * SZ_NAME
            body.append('<text x="%s" y="%s" font-size="%d" font-weight="700" text-anchor="middle" fill="%s">%s</text>'
                        % (num(cx), num(base), SZ_NAME, c["on_blue"], esc(s["name"])))
            stats["fonts"].append(("name", SZ_NAME))
            fit("name", s["name"], SZ_NAME, box_w - 20, True)
        # content block (Claude lines, then the amber chip)
        top = y + (row_h - content_h) / 2.0
        for i, line in enumerate(s["claude"]):
            base = top + LH * i + 0.5 * LH + 0.35 * SZ_LINE
            body.append('<text x="%d" y="%s" font-size="%d" fill="%s">%s</text>'
                        % (text_x, num(base), SZ_LINE, c["sub"], spans(line)))
            stats["fonts"].append(("line", SZ_LINE))
            fit("line", line, SZ_LINE, text_w)
        if chip_lines:
            chip_top = top + n_c * LH + 6
            widest = max(est_width(l, SZ_LINE) for l in chip_lines)
            chip_w = round(widest * GROW + 2 * CHIP_PAD_X)
            chip_w = min(chip_w, text_w)
            body.append('<rect x="%d" y="%s" width="%d" height="%s" rx="%s" fill="%s"/>'
                        % (text_x, num(chip_top), chip_w, num(chip_h), num(radius(chip_w, chip_h)), c["amber"]))
            stats["amber_area"] += chip_w * chip_h
            for i, line in enumerate(chip_lines):
                base = chip_top + CHIP_PAD_Y + CHIP_LH * i + 0.5 * CHIP_LH + 0.35 * SZ_LINE
                body.append('<text x="%d" y="%s" font-size="%d" fill="%s">%s</text>'
                            % (text_x + CHIP_PAD_X, num(base), SZ_LINE, c["on_amber"], spans(line)))
                stats["fonts"].append(("turn", SZ_LINE))
                fit("turn", line, SZ_LINE, chip_w - 2 * CHIP_PAD_X)
        y += row_h
        if idx < len(stages) - 1:
            # arrow in the gap, centered under the stage box
            a0, a1 = y + 4, y + ROW_GAP - 4
            body.append('<path d="M%s %s V%s M%s %s L%s %s L%s %s" fill="none" stroke="%s" '
                        'stroke-width="%d" stroke-linecap="round" stroke-linejoin="round"/>'
                        % (num(cx), num(a0), num(a1), num(cx - 8), num(a1 - 9), num(cx), num(a1),
                           num(cx + 8), num(a1 - 9), c["blue"], STROKE))
            y += ROW_GAP

    # the one-line note
    y += 24
    body.append('<text x="%d" y="%s" font-size="%d" fill="%s">%s</text>'
                % (M, num(y + 0.5 * LH + 0.35 * SZ_NOTE), SZ_NOTE, c["sub"], esc(t["note"])))
    stats["fonts"].append(("note", SZ_NOTE))
    fit("note", t["note"], SZ_NOTE, W - 2 * M)
    y += LH + 24

    height = int(round(y))
    stats["height"] = height
    stats["amber_ratio"] = stats["amber_area"] / float(W * height)

    head = ('<svg xmlns="http://www.w3.org/2000/svg" xml:lang="%s" lang="%s" viewBox="0 0 %d %d" '
            'width="%d" height="%d" role="img" aria-labelledby="t d" '
            'font-family=\'%s\'>\n' % (t["lang"], t["lang"], W, height, W, height, SANS))
    title_plain = " ".join(plain(l) for l in t["title"])
    head += '<title id="t">%s</title>\n<desc id="d">%s</desc>\n' % (esc(title_plain), esc(t["alt"]))
    head += '<rect width="%d" height="%d" rx="24" fill="%s"/>\n' % (W, height, c["bg"])
    svg = head + "\n".join(body) + "\n</svg>\n"
    return svg, stats


# ---------------------------------------------------------------- snippets
def snippet(lang):
    t = TABLE[lang]
    return ('<picture>\n'
            '  <source media="(prefers-color-scheme: dark)" srcset="docs/img/flow-%s-dark.svg">\n'
            '  <img alt="%s" src="docs/img/flow-%s-light.svg">\n'
            '</picture>' % (lang, esc(t["alt"]), lang))


# ---------------------------------------------------------------- checks
FORBIDDEN_STRINGS = ["/Users/", "/home/", "C:\\", "op://", ".env", "<script", "foreignObject", "href=", "<image",
                     "@import", "url(", "http://", "https://", "<!--", "python", "claude code"]
FORBIDDEN_WORDS = ["簡単", "易しい", "誰でも", "初心者", "Codex", "公式", "世界初", "9 言語", "同時編集",
                   "30 分でプロ品質", "1 バイトも外に出さない", "ずっと無料", "CCB"]
FORBIDDEN_EN = [r"\beasy\b", r"\beasily\b", r"\bsimple\b", r"\bbeginners?\b", r"\banyone\b", r"\beveryone\b",
                r"\bofficial\b", r"\bCodex\b", r"\bCCB\b", r"\bworld.first\b", r"\bfree forever\b"]


def out_dir():
    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(os.path.dirname(here), "docs", "img")


def check():
    problems = []

    def bad(msg):
        problems.append(msg)

    en, ja = TABLE["en"], TABLE["ja"]
    # 1. keys and empty strings
    if set(en.keys()) != set(ja.keys()):
        bad("top-level keys differ: %s vs %s" % (sorted(en.keys()), sorted(ja.keys())))
    if len(en["stages"]) != len(ja["stages"]):
        bad("stage count differs")
    for i, (a, b) in enumerate(zip(en["stages"], ja["stages"])):
        if set(a.keys()) != set(b.keys()):
            bad("stage %d keys differ" % (i + 1))
        if (a["turn"] is None) != (b["turn"] is None):
            bad("stage %d: your-turn mark differs between en and ja" % (i + 1))
        if len(a["claude"]) < 1 or len(b["claude"]) < 1:
            bad("stage %d: a claude line is missing" % (i + 1))

    def cells(t):
        yield "lang", t["lang"]
        for k in ("title", "legend_claude", "legend", "note", "alt"):
            v = t[k]
            for x in (v if isinstance(v, list) else [v]):
                yield k, x
        for i, s in enumerate(t["stages"]):
            yield "stage%d.name" % (i + 1), s["name"]
            for x in s["claude"]:
                yield "stage%d.claude" % (i + 1), x
            for x in (s["turn"] or []):
                yield "stage%d.turn" % (i + 1), x

    for lang in ("en", "ja"):
        for k, x in cells(TABLE[lang]):
            if not isinstance(x, str) or not x.strip():
                bad("%s: empty string at %s" % (lang, k))
            if x.count("`") % 2:
                bad("%s: unbalanced backtick at %s" % (lang, k))
            for w in FORBIDDEN_WORDS:
                if w in x:
                    bad("%s: forbidden word %r at %s" % (lang, w, k))
            for pat in FORBIDDEN_EN:
                if re.search(pat, x, re.I):
                    bad("%s: forbidden word /%s/ at %s" % (lang, pat, k))
    # typed words stay the same in both languages
    for lang in ("en", "ja"):
        joined = " ".join(x for _, x in cells(TABLE[lang]))
        for w in ("`looks good`", "`approve`"):
            if w not in joined:
                bad("%s: typed word %s missing" % (lang, w))

    # 2. contrast of every text color on its background, and shapes
    for name, c in THEMES.items():
        for fg, bgk in TEXT_PAIRS:
            r = contrast(c[fg], c[bgk])
            if r < 4.5:
                bad("%s: %s on %s = %.2f (< 4.5)" % (name, fg, bgk, r))
        for fg, bgk in SHAPE_PAIRS:
            r = contrast(c[fg], c[bgk])
            if r < 3.0:
                bad("%s: shape %s on %s = %.2f (< 3.0)" % (name, fg, bgk, r))

    # 3. render, then look at the output
    outputs = {}
    for lang, theme in OUT_NAMES:
        svg, stats = render(lang, theme)
        svg2, _ = render(lang, theme)
        label = "flow-%s-%s.svg" % (lang, theme)
        outputs[label] = svg
        if svg != svg2:
            bad("%s: two renders differ" % label)
        data = svg.encode("utf-8")
        if len(data) > MAX_BYTES:
            bad("%s: %d bytes (> %d)" % (label, len(data), MAX_BYTES))
        if stats["height"] > MAX_HEIGHT:
            bad("%s: height %d (> %d)" % (label, stats["height"], MAX_HEIGHT))
        if stats["amber_ratio"] > AMBER_MAX_RATIO:
            bad("%s: amber area %.1f%% (> 10%%)" % (label, stats["amber_ratio"] * 100))
        for role, size in stats["fonts"]:
            if size < MIN_SIZES[role]:
                bad("%s: %s text is %dpx (< %d)" % (label, role, size, MIN_SIZES[role]))
        for role, text, w, avail in stats["fit"]:
            if w > avail + 1:
                bad("%s: %s %r needs %.0fpx with a wider font, room is %.0fpx" % (label, role, text, w, avail))
        sizes = [int(m) for m in re.findall(r'font-size="(\d+)"', svg)]
        if sizes and min(sizes) < 22:
            bad("%s: font-size %d in the file (< 22)" % (label, min(sizes)))
        # forbidden strings (the namespace is the one allowed address)
        probe = svg.replace('xmlns="http://www.w3.org/2000/svg"', "").lower()
        for s in FORBIDDEN_STRINGS:
            if s.lower() in probe:
                bad("%s: forbidden string %r" % (label, s))
        if "\r" in svg:
            bad("%s: carriage return" % label)
        if '<title id="t">' not in svg or '<desc id="d">' not in svg:
            bad("%s: title or desc missing" % label)
        if 'xml:lang="%s"' % lang not in svg:
            bad("%s: xml:lang missing" % label)
        if 'opacity' in svg:
            bad("%s: uses opacity (the ground must be opaque)" % label)
        try:
            root = ET.fromstring(data)
            if not root.tag.endswith("svg"):
                bad("%s: root is not svg" % label)
        except ET.ParseError as e:
            bad("%s: not well-formed XML (%s)" % (label, e))
        # opaque ground is the first rect
        if '<rect width="%d" height="%d" rx="24" fill="%s"/>' % (W, stats["height"], THEMES[theme]["bg"]) not in svg:
            bad("%s: opaque ground missing" % label)

    # 4. files on disk, if present, must equal the output
    d = out_dir()
    for label, svg in outputs.items():
        p = os.path.join(d, label)
        if os.path.exists(p):
            with open(p, "rb") as f:
                if f.read() != svg.encode("utf-8"):
                    bad("%s on disk differs from the script output (run the script again)" % label)
    return problems, outputs


def write_all():
    d = out_dir()
    os.makedirs(d, exist_ok=True)
    for lang, theme in OUT_NAMES:
        svg, _ = render(lang, theme)
        with open(os.path.join(d, "flow-%s-%s.svg" % (lang, theme)), "wb") as f:
            f.write(svg.encode("utf-8"))


def main(argv):
    if "--check" in argv:
        problems, outputs = check()
        if problems:
            for p in problems:
                print("FAIL: " + p)
            return 1
        for lang, theme in OUT_NAMES:
            svg, stats = render(lang, theme)
            print("ok flow-%s-%s.svg: %d bytes, height %d, amber %.1f%%"
                  % (lang, theme, len(svg.encode("utf-8")), stats["height"], stats["amber_ratio"] * 100))
        print("check passed")
        return 0
    if "--print-alt" in argv:
        for lang in ("en", "ja"):
            print("[%s] alt:\n%s\n" % (lang, TABLE[lang]["alt"]))
            print("[%s] snippet:\n%s\n" % (lang, snippet(lang)))
        return 0
    write_all()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
