# ws/render templates

- `ws.sh render` fills the three templates (`io`, `schedule`, `systemtest`). The fourth, `tasks`, is the schedule page of all projects (`projects/schedule.html`): `ws.sh tasks gantt` and the hooks fill it (keys `html.tasks.*`). `sample_*.json` are test data (English).
- The fifth, `guide`, is the guide page (`projects/guide.html`, keys `html.guide.*`): where the user is, whose turn it is, and the one next step. The hooks (session start, every prompt, every Stop that passes) and every `ws.sh` command that prints a result fill it when a project exists; `ws.sh guide` fills it and opens it. Its data has the shape of `sample_guide.json` (`engine.guide_data`).
  - When no project is chosen (`project` is `null`), the data has one more key at the top: `next` (`kind`, `text`, `say`), the one next step for that state. `others` is always sent. `sample_guide.json` shows the shape with a project.
  - Next to the page the engine writes `projects/guide.data.js`: one statement, `window.__CCB_GUIDE__ && window.__CCB_GUIDE__("<word>", <the same data as JSON>);`. The open page adds this file as a script every 2 seconds and draws again when the data changed, so it updates without a reload (`fetch` does not work on `file://`).
  - `<word>` is a word for the workspace, made from the signing key (outside the workspace) and the workspace path. It is not stored. The engine fills the mark `/*__WS_TOKEN__*/""` in the template with it, and the page ignores a call that carries another word.
  - In the next step, in the "not sure" text and in the text for no project, a word in backticks is drawn as a small `<code>` chip. The page builds it from text nodes, never from markup in the text.
  - Both files are written only when their content changed. The `generated` time alone does not count as a change.
  - A label key may have a dot in it (`step.1`, `goal_for.self`, `link.app`): read it as `L["step.1"]`.
- The engine replaces these marks, each in one place:
  - `/*__WS_DATA__*/null` with the data as JSON. Before this, every `<` in the JSON text is replaced with `\u003c` (so `</script>` cannot cut it), and a mark that is inside the data is escaped. All marks are filled in one pass, so text that was filled in is never read as a mark.
  - `/*__WS_LABELS__*/null` with the words of the page for the current language (`labels`, JSON). The words come from `ws/lang/en.py` and `ws/lang/ja.py` (keys `html.common.*` and `html.<page>.*`, where `<page>` is `io`, `sched` or `st`).
  - `<html lang="en">` with the current language code.
  - `/*__WS_FONT__*/` with the CJK font names, for Japanese only. For other languages it is removed.
  - `<!--ws-noscript-->` and the text after it, with the "turn on JavaScript" sentence.
- The templates keep the English words in `<script id="ws-labels-default">`. If a label is missing, the English word is shown. When you change `html.*` keys in `en.py`, copy the English table into that block (a unit test checks that the two are equal).
- `kind` is an English symbol (`screen`, `file`, `api`, `db`, `external`, `scheduled`). A system test row's `state` is also a symbol (`normal`, `empty`, `error`, `ok`, `failure`). The engine turns old Japanese values into symbols before it fills the page.
- If nothing is replaced, the page shows its built-in sample in English.
- It loads nothing from outside and opens with `file://`.
