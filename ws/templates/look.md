# The look kit (`ws/templates/look.css`)

`look.css` is one block of CSS that gives a small app a calm, readable, finished look: a page, cards, large buttons, form fields, list rows, number tiles, notes, an empty state and a table. It has a light and a dark version, and it loads nothing from outside.

## How to use it

1. Copy the whole content of `ws/templates/look.css` into the `<style>` of the page, inline. Do not link to the file: the page must still open by double-click, with no outside loads.
2. Choose ONE accent colour that suits the purpose of the app, and change `--accent` near the top (one value). Hover and tint colours follow it. Pick a colour on which white text is clear to read, because the main button has white text on it. Write the colour and the reason in `brief.md` under `## Colors`.
3. Build the page from the classes below. Add your own CSS after the kit only when a part needs it.

## Classes

| Class | Use |
|---|---|
| `.page` | The centred container of the whole page. Put a `<header>` with the `h1` at its top |
| `.card` | One group of things that belong together |
| `.btn` | A button. Add `.primary` for the main action (one on a screen), `.quiet` for a side action, `.danger` for delete |
| `.actions` | A row of buttons that wraps on a narrow screen |
| `.field` | A `<label>` with a `<span>` (the label text), the input, and an optional `.hint` |
| `.check` | A `<label>` with a checkbox or a radio button and its text |
| `.row` | One line of a list. The first element takes the space that is left; a button goes last |
| `.pill` | One short word about a row. `.good`, `.warn`, `.bad` when the word is a status |
| `.tiles`, `.tile` | Numbers that matter: `<b>` is the number, `<span>` the label |
| `.banner` | The success message after an action ("Added.") |
| `.note` | A message. `.good`, `.warn` or `.bad`. Always say in words what happened and what to do |
| `.empty` | What to show when there is nothing yet: a `<b>` title, one sentence, and the first action |
| `table` | A few columns of plain data. `class="num"` on number cells |
| `.muted`, `.small` | Helper text |

## A minimal page

```html
<main class="page">
  <header><h1>Coffee log</h1><p class="muted">Log each coffee and see this week's total.</p></header>
  <div class="tiles"><div class="tile"><b>9</b><span>cups this week</span></div></div>
  <section class="card">
    <h2>Add a coffee</h2>
    <label class="field"><span>What did you drink?</span><input type="text" placeholder="For example: latte"></label>
    <p class="note bad" hidden>The name is missing. Type what you drank, then press Add.</p>
    <div class="actions"><button class="btn primary">Add</button></div>
  </section>
  <section class="card">
    <h2>Today</h2>
    <div class="row"><div><b>Latte</b><br><small class="muted">8:10</small></div><button class="btn danger">Delete</button></div>
  </section>
  <div class="empty"><b>No coffee logged yet</b>Your first cup will show up here.</div>
</main>
```

## Rules

- `design/ui/index.html` is the finished look. Start it from this kit, with real-looking example data from the user's own words.
- The rough first picture (`design/ui/sketch.html`) does not use the kit. It stays grey and rough on purpose: it is a question, not a design.
- The builder keeps the approved look exactly: the app's page uses the same style block and structure as `design/ui/index.html`. If something must look different, go back to the design.
- With a reference site or app: keep its layout and flow. Never copy its colours, logo, text or pictures.
- A status is never shown by colour alone: a note has a mark, a border and words.
