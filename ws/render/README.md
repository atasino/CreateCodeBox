# ws/render templates

- `ws.sh render` fills the three templates (`io`, `schedule`, `systemtest`). The fourth, `tasks`, is the schedule page of all projects (`projects/schedule.html`): `ws.sh tasks gantt` and the hooks fill it (keys `html.tasks.*`). `sample_*.json` are test data (English).
- The engine replaces these marks, each in one place:
  - `/*__WS_DATA__*/null` with the data as JSON. Before this, every `<` in the JSON text is replaced with `<` (so `</script>` cannot cut it).
  - `/*__WS_LABELS__*/null` with the words of the page for the current language (`labels`, JSON). The words come from `ws/lang/en.py` and `ws/lang/ja.py` (keys `html.common.*` and `html.<page>.*`, where `<page>` is `io`, `sched` or `st`).
  - `<html lang="en">` with the current language code.
  - `/*__WS_FONT__*/` with the CJK font names, for Japanese only. For other languages it is removed.
  - `<!--ws-noscript-->` and the text after it, with the "turn on JavaScript" sentence.
- The templates keep the English words in `<script id="ws-labels-default">`. If a label is missing, the English word is shown. When you change `html.*` keys in `en.py`, copy the English table into that block (a unit test checks that the two are equal).
- `kind` is an English symbol (`screen`, `file`, `api`, `db`, `external`, `scheduled`). A system test row's `state` is also a symbol (`normal`, `empty`, `error`, `ok`, `failure`). The engine turns old Japanese values into symbols before it fills the page.
- If nothing is replaced, the page shows its built-in sample in English.
- It loads nothing from outside and opens with `file://`.
