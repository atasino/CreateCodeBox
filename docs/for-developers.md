# For developers

You already use Git and GitHub? This page is for you. Most of the steps below need your own words in a message. Claude is blocked from running them alone.

## Use your own repo

Bring a repo you already have into an empty project:

```
bash ws/bin/ws.sh repo adopt https://github.com/your-name/your-repo.git
```

SSH addresses work for `repo adopt`, for example `git@github.com:your-name/your-repo.git`. `backup` is refused for them, because the workspace cannot tell if the repo is public. Use `publish-check` and `publish` instead. `publish` has its own gate: you type `publish`.

- The code you bring in is outside material. Claude is told not to read its `CLAUDE.md`, `AGENTS.md`, or `.claude/` folder. The workspace does not load its `CLAUDE.md` (we tested this one only).
- Claude reads the code first. Then you design the change as inputs and outputs (stage R4) and approve it. Only then does Claude change code.
- In the first turn of a session, Claude only reads. The workspace blocks edit tools on `src/`, and in RUN or DONE it blocks Bash commands that write. Writing starts from your second message.
- Save does not commit to `main` or `master`. It makes a branch named `createcodebox/<date>` (for example `createcodebox/20261102`) and commits there. You merge it yourself.
- If you have changes that are not committed, you get a warning when you bring the repo in.

If the repo is yours and you only want to keep a backup, `repo link <URL>` and `backup` send your work to a private repo. Inside the workspace, only `publish` sends to a public repo.

## Bring your own rules

To use your own `CLAUDE.md` rules, send the path in a message and then run:

```
bash ws/bin/ws.sh rules import <path>
```

- The path must appear in your latest message, exactly as typed.
- Only files under `projects/<name>/src/` and `~/.claude/CLAUDE.md` can be imported.
- The file is scanned for keys and must be 64 KB or smaller.
- The copy goes to `projects/<name>/knowledge/imported_rules.md`. The first line says who imported it, when, and from where.
- Claude follows this file as rules you approved. The safety rules are written to come first.
- Hooks from your own `settings.json` (for example a prettier hook) do not come back. Add them yourself if you need them.

## Run your app

By default, you get one HTML file. If your project needs a server, ask for it and run it yourself:

```
npm start
```

- `with-secrets [--project] [--timeout N] -- <command>` runs a command with your keys, outside the chat. It accepts only three kinds of command. First, a script declared in `package.json` (`npm run <name>`, `npm start`). Second, `python <file>` or `node <file>` for a file under `src/`. Third, a command you typed word for word in your latest message. Output streams as it runs. The default time limit is 600 seconds. Change it with `--timeout`.
- `st run <ID…>` runs your tests and records the result as evidence. It works only for cases that Claude checks. For a case that you check, it is refused, because Claude must not fill in "You checked". It has no `--cmd` option. It finds the runner by itself:
  - `package.json` with `scripts.test`: `npm test`
  - `pytest.ini` or `pyproject.toml`: `pytest`
  - `go.mod`: `go test ./...`
  - `Cargo.toml`: `cargo test`

  With none of these, it says that there is no runner. The evidence is the exit code and the last 50 lines.
- `st route <ID> user|ai --reason <text>` changes who checks a case. Use `ai` only for a case you truly cannot trigger by hand, such as a monthly job. The older `CI` and `UT` routes are gone.
- `st mark <ID> pass --by ai --shot <image>` works only for cases that Claude checks. It accepts an image only if it is under `projects/<name>/` and was made after the session started.
- You answer your own cases by number: `st mark numbered pass --by user`. The message must have the numbers from the last `st list --numbered`, for example `1, 2 pass` or `1-3 pass`.
- Who checks a new case (`case_who`): you check the normal case (`N`) of a row a person can trigger. Every empty or edge case (`B`), every failure case (`F`), and every case of a `scheduled` row is Claude's. A list that exists keeps the `who` of its cases; `st route` changes one.
- `st list --numbered` shows only your cases, numbered from 1, and one line that counts Claude's. `st list` shows all of them.
- In a numbered answer (`read_answer`), a number is recorded as passed only when a positive word belongs to it: in `1, 2 and 4 worked; 3 did not`, 1, 2 and 4 are recorded and 3 is named as not recorded. A range (`1-7`, `1 to 7`, `1 through 7`, `1から7まで`) is every number in it. A number with no such word is named too. `all worked` (sent within three messages of the list) records every case of the numbered list; `all pass but 3` records all of them except 3. Only numbers of the last numbered list count, and only the part of a sentence before a colon is read.
- Evidence: `--evidence <text>`, `--evidence -` (standard input), or `--evidence-file <path>`. If the text has any of `> < ; & | $`, the hook stops the command. Write the text in a file and use `--evidence-file`.

## Task board

Each project has a list of what is left. The list is `.ws/tasks_<slug>.json`, a signed record (`resign` and `doctor` cover it). The board that you see is put together each time: the stage's missing items, the open rows of the build schedule (`schedule_<slug>.json`), and the open items of this record. The goal comes from `PROJECT.md`.

```
bash ws/bin/ws.sh task add "<title>" [--kind req|todo|issue] [--start YYYY-MM-DD] [--due YYYY-MM-DD] [--fixed] [--project <slug>]
bash ws/bin/ws.sh task set <id> todo|doing|done|hold|dropped [--note "<why>"] [--how "<what was checked>"]
bash ws/bin/ws.sh task date <id> <start|-> <due|-> [--fixed]
bash ws/bin/ws.sh task none
bash ws/bin/ws.sh tasks [<slug>]
bash ws/bin/ws.sh tasks gantt [--text]
```

- `task add` prints the new id (`T-01`). It keeps where the item came from (the prompt number and the first 60 characters). Dates are tentative until `--fixed`.
- Marking an item done needs `--how` (8 characters or more). `hold` and `dropped` need a note. For a build row (`S-xx`), `task set` runs `mark` with its rules, and `task date` stores the dates in the schedule record.
- `tasks gantt` writes `projects/schedule.html` for all projects (no outside scripts or fonts; it reloads every 30 seconds). With `--text` it also prints a week grid for the chat. The page is rewritten after `task add`, `task set`, `task date` and `mark`, and by the hooks at session start and on every prompt (so a new stage shows up too). It is written only when the content changed. If the render fails, the hook adds one warning line and goes on. The last line of `task add`, `task set` and `task date` is `Schedule updated: <path>`. Only `ws.sh` writes the page: the gate refuses an edit of it.
- Session start adds one line for each project and the open items of the active one. Every prompt adds the open items of the active project (5 lines at most), the open counts of the others, and the triage line, in about 700 characters at most.
- **Triage.** After approval (RS, RUN, DONE), a message that is not a plain yes, an approval word, check numbers, or continue / new must be sorted: `task add`, `task set` or `task date`, or `task none`. Until then the gate refuses edits (`Edit`, `Write`, `MultiEdit`, `NotebookEdit`, `apply_patch`), MCP write tools, and any Bash command that is not read-only. `ws.sh task`, `tasks`, `status`, `list`, `select`, `new` and the other read commands still run. `Stop` blocks once if the message is still not sorted. Before approval nothing is enforced: you get a one-line reminder.

## The next step, the guide page, and the goal answer

```
bash ws/bin/ws.sh next
bash ws/bin/ws.sh where
bash ws/bin/ws.sh guide
```

- `next` prints the one thing the user does next (`Next for the user: …`, and `Exact words: …` when a word must be typed). It is `next_step()` in `ws/engine.py`: a kind (`answer`, `say`, `look`, `check`, `wait`, `done`), a sentence from `ws/lang/` (keys `next.*`), and the exact word or nothing. The hooks put the same lines in the context at session start and with every prompt, with the rule about the `▶` line.
- `Stop` blocks once for each user message when the last reply has no line that starts with `▶` (spaces, `*`, `_`, a backtick, `>`, `#`, a list dash or a list number may come first). It does not block when the reply cannot be read, or when `stop_hook_active` is set. If the triage also applies, both texts are in the one answer.
- `Stop` also blocks once for each user message when the next step is `wait` (the missing thing is Claude's own work): the reply is held and Claude is told to go on (`stop.wait`). Not in the first prompt of a session at RUN, which is read-only. `wait` is given only while a reply runs (`turn: claude` in the session, from a prompt until a Stop passes). Outside a reply, the same state gives `say` with the word `continue`, so `ws.sh next`, `where` and the guide page never tell a user to wait for work that nobody is doing. Every SessionStart source sets `turn` back to `you`; `ws.sh` commands do not change it.
- `where` prints the recap for a user who is lost: goal, step (1 to 6), what is done, the next step. A short message from the lists in `ws/lang/synonyms.py` (`help`, `what now?`, `迷った` …) puts the same recap in the context. The session counts these messages (`lost`).
- The finish word: at RUN, when `src/index.html` exists and every case the user checks has passed, the user's own message `finish` (the exact words are in `ws/engine.py`, `FINISH_EN` and `FINISH_RE`) writes `.ws/accept_<slug>.json`, a signed record with the hash of the design. While it is valid, the stage is DONE even with open build rows or open cases of Claude's. `status`, `where` and `st list` then say how many were left. Nothing but the prompt hook writes it.
- `guide` writes `projects/guide.html` and `projects/guide.data.js`, opens the page (`CREATECODEBOX_OPEN_DRY_RUN=1` only says what it would open), and sets `guide_opened` in `.ws/state.json`. Until then, the context of each turn asks Claude to run it once. The data is `guide_data()`; its shape is `ws/render/sample_guide.json`. The template and the label rules are in `ws/render/README.md`. The same two files are written by the hooks and after each `ws.sh` command that prints a result, only when the content changed. The edit tools and the Read tool are refused for both files, and so is a shell command that names them (in any letter case). A shell command that names `schedule.html` is refused in the same way. The data file calls the page with a word made from the signing key in `~/.createcodebox` and the workspace path (`guide_token()`: the first 16 hex characters of an HMAC; it is not stored); the page ignores a call with another word.
- The goal answer is `.ws/goal_<slug>.json`, a signed record: `reached` (true or false), the hash of the design it belongs to, and the user's words. It is written only from the user's own prompt, at stage DONE. The question is open for exactly one message, and only after a Stop passed on a reply that named both answers (`goal_question_in`). Then a plain yes (`GOAL_YES_*` in `ws/lang/synonyms.py`) or a plain not yet (`GOAL_NO_*`) is recorded, and the latest answer replaces the one before. Without an open question, only two things change a record: after not yet, a short "it's finished"; after yes, a plain "not yet" or a short "it is not what I wanted". A change of the design makes it count for nothing. `status`, `st list` and `where` show it.

## Try a page without a window

```
bash ws/bin/ws.sh try <page.html> [--before <file.js>] [--after <file.js>] [--shot <out.png>] [--size WxH] [--wait <ms>]
```

- The page must be an `.html` file in the active project's `src/` (from RUN on) or `design/` (from R2 on). The script files must be inside `projects/<slug>/`. The picture must be a `.png` inside `projects/<slug>/`, but not in `design/evidence/`. The default is `projects/<slug>/evidence/try-<time>.png`. An argument with `://` is refused.
- It looks for a Chromium-family browser and installs nothing: on a Mac, Chrome, Edge, Chromium or Brave in `/Applications` or `~/Applications`; on Windows, `chrome.exe` or `msedge.exe` under `%ProgramFiles%`, `%ProgramFiles(x86)%` or `%LocalAppData%`; elsewhere, `google-chrome`, `google-chrome-stable`, `chromium`, `chromium-browser`, `microsoft-edge` or `brave-browser` on the `PATH`. `CREATECODEBOX_BROWSER` (a path) overrides the search. With none, the exit code is 3.
- It writes a copy of the page next to it (`.ccb-try-<pid>.html`, removed afterwards). In the copy, the `--before` code is the first script in `<head>`, and the `--after` code runs after `load`, inside an async function. What that function returns, an error it throws, and the `console.log` lines come back as JSON.
- The browser runs twice on that copy, each time with a new temporary profile folder: once with `--dump-dom`, once with `--screenshot`. The flags are `--headless=new` (then `--headless` if that did not work), `--no-first-run`, `--no-default-browser-check`, `--disable-gpu`, `--hide-scrollbars`, `--window-size` and `--virtual-time-budget` (`--wait`, 3000 by default). Each run is killed after 60 seconds. No shell is used.
- It prints the browser's name, the result, the console lines, the first 1,500 characters of the text on the page (scripts, styles, tags and hidden elements left out), and the path of the picture. Exit code 0 when the page loaded and the `--after` code did not throw, else 1.
- The picture can be the evidence of a case that Claude checks: `st mark <ID> pass --by ai --shot <png>`. At DONE, Claude's own cases can still be marked again this way, or with `st run`; the user's cases cannot.

## Tools outside the gates

The hooks check Claude's own tools: file edits, Bash, Read, Grep, and Glob. In Codex, they check its edit tool `apply_patch` and its shell (see [codex-notes.md](codex-notes.md)). The hook looks at tool names that contain "gakaso" (Gakaso is our own product). It lets only read-type names through before a design exists. Some tool names contain write, edit, patch, apply, create, delete, move or rename. A built-in tool with such a name that the hook does not know is always refused. An MCP tool with such a name (for example `mcp__tracker__create_issue`) is refused until the build stage, after approval. After that, it is not restricted. Other unknown tools are not restricted by these gates. The hook goes by the name only. It cannot tell what an MCP tool really does. If you add an MCP server, you decide what it can do. Pass keys to it with `ws/bin/mcp_env.py`, not with `claude mcp add -e KEY=value`. See `.claude/skills/ws-secrets/SKILL.md`.

## Records and language

- Records are in `.ws/`: `st_<slug>.json` (test cases), `schedule_<slug>.json`, `tasks_<slug>.json` (the task board), `accept_<slug>.json` (the user's word to finish), `goal_<slug>.json` (the goal answer), `repo_<slug>.json`, `secret_allow.json`, `excludes.json`, and `lang`. The `design/` folder holds only the HTML pages. If the signing key is missing, records are unsigned and you get a warning. Your progress is kept.
- Language: `.ws/lang`, then the environment variable `CREATECODEBOX_LANG`, then English. If `CREATECODEBOX_LANG` is set, the language is not saved from your first message. Run `bash ws/bin/ws.sh lang set en` (or `ja`) to change it.
- `bash ws/bin/ws.sh open <path>` opens a file under `design/` or `src/` (html, png, svg, or pdf), or one of the two pages for all projects: `projects/schedule.html` and `projects/guide.html`. The path starts from the workspace root.
- `bash ws/bin/ws.sh resign` signs the records again. Claude runs it only after you type `resign`.

## Run the tests

From the top folder of this repository:

```
python3 -I tests/test_engine.py
python3 -I tests/test_hook_protocol.py
```

- `test_engine.py` checks the guards and the commands. `test_hook_protocol.py` checks what the hooks read and the exact JSON that they answer.
- GitHub Actions runs both on Python 3.8 and 3.12 (`.github/workflows/ci.yml`).
- They need Python 3.8 or newer and `git`. They use the standard library only.
- Each test works on a copy of the workspace in a temporary folder. Your `projects/` and `.ws/` folders are not used.
- They set `HOME` to an empty temporary folder, so they do not touch `~/.createcodebox`.
- The last line prints the counts (`PASS` and `FAIL`). The exit code is 1 if any check fails.

The engine is `ws/engine.py`. It decides what each hook answers. The Claude Code side of the hooks is in `ws/adapters/claude.py`: where the workspace is (`CLAUDE_PROJECT_DIR`), how the hook input is read, and the shape of each answer.

## Update

`bash ws/bin/ws.sh update` runs `git pull --ff-only` and follows tags. It refuses if you changed files in `ws/`, `.claude/`, or `CLAUDE.md`. Your `projects/` and `.ws/` folders are not part of the update. Signed tags are not supported yet.
