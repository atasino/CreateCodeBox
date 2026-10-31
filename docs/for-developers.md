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

## Tools outside the gates

The hooks check Claude's own tools: file edits, Bash, Read, Grep, and Glob. In Codex, they check its edit tool `apply_patch` and its shell (see [codex-notes.md](codex-notes.md)). The hook looks at tool names that contain "gakaso" (Gakaso is our own product). It lets only read-type names through before a design exists. Some tool names contain write, edit, patch, apply, create, delete, move or rename. A built-in tool with such a name that the hook does not know is always refused. An MCP tool with such a name (for example `mcp__tracker__create_issue`) is refused until the build stage, after approval. After that, it is not restricted. Other unknown tools are not restricted by these gates. The hook goes by the name only. It cannot tell what an MCP tool really does. If you add an MCP server, you decide what it can do. Pass keys to it with `ws/bin/mcp_env.py`, not with `claude mcp add -e KEY=value`. See `.claude/skills/ws-secrets/SKILL.md`.

## Records and language

- Records are in `.ws/`: `st_<slug>.json` (test cases), `schedule_<slug>.json`, `tasks_<slug>.json` (the task board), `repo_<slug>.json`, `secret_allow.json`, `excludes.json`, and `lang`. The `design/` folder holds only the HTML pages. If the signing key is missing, records are unsigned and you get a warning. Your progress is kept.
- Language: `.ws/lang`, then the environment variable `CREATECODEBOX_LANG`, then English. If `CREATECODEBOX_LANG` is set, the language is not saved from your first message. Run `bash ws/bin/ws.sh lang set en` (or `ja`) to change it.
- `bash ws/bin/ws.sh open <path>` opens a file under `design/` or `src/` (html, png, svg, or pdf). The path starts from the workspace root.
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
