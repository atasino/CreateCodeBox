# How it works, and what we have checked

## How it works

You talk to one agent, called `pm`. The `pm` agent asks you questions and hands work to four helper agents:

| Agent | Job |
|---|---|
| `designer` | Makes the rough picture, the design, and the table of inputs and outputs |
| `builder` | Builds your project, one step at a time, after you approve |
| `reviewer` | Reads the work and the evidence before anything is called done. It is blocked from changing files |
| `connector` | Reads text from outside (web pages, your notes) and returns a short summary. It is told not to follow instructions in that text |

The workspace has two kinds of guards:

- **Hooks.** Small scripts that run before Claude Code reads your message, uses a tool, or stops. They are built so that the app's code (in `src/`) is not written until you approve. They also block other steps that come too early.
- **Records.** Your approvals, test results, and schedule are saved in the `.ws/` folder with a signature. The workspace is built so that a record edited by hand does not move the stage forward.

The stage is not saved as a number. The engine works it out from the files each time, so a deleted file sends you back to the right stage.

## The stages

| Stage | What happens | What stops you |
|---|---|---|
| R0 | Start. Continue a project or begin a new one | Claude is blocked from writing files until you have answered |
| R1 | Two questions: what you want to make, and the goal. Then one question about a site or app that is close. Then Claude opens a prototype (a rough first picture if there is no reference) | |
| R2 | Claude asks only what the prototype cannot show (up to five questions). It marks its own guesses as tentative. It asks where your files are, if you have any | |
| R3 | Claude shows the design | You type `looks good` |
| R4 | Claude lists every input and output, and what you see when something fails | |
| R4A | You read the table and the design | You type `approve`. Until then Claude is blocked from writing to `src/` |
| RS | Claude makes the schedule | |
| RUN | Claude builds, one row at a time | Claude must run a row and note the result before it marks the row done. The workspace does not check that the note is true |
| DONE | First version is done | New requests start at R4 again |

If you change the design or the table after you approve, the approval is reset. Claude tells you, and you look again.

## Language

Claude is told to answer in the language you write in. Fixed text from the workspace is in English or Japanese. Claude translates it when it passes it to you. Text inside backticks, such as `approve`, is never translated. Type those words exactly.

Claude writes to you in everyday words. The table of technical words and what to say instead is `ws/style/plain-words.en.md` (Japanese: `plain-words.ja.md`). The same list is in `ws/style/words.json`.
For now, a rule tells Claude to read it. A reminder on every turn and an automatic check (lint) are planned for the next version.

## Models

Default: the model you choose in Claude Code. The helper agents `connector` and `reviewer` use Haiku.

## Names and where to report problems

- The repository is private for now while we test it.
- Report a step that did not work in GitHub Issues. Ask questions in GitHub Discussions.

## What we have checked

Version 0.3.0 changed a lot compared with version 0.2.0. We have run the 0.3.0 changes in unit tests and in three `-p` runs (see below). We have not run them in a real, interactive Claude Code session. The unit tests are in `tests/`: `test_engine.py` has 460 checks, and `test_hook_protocol.py` has 41. All of them pass on a Mac with Python 3.9, and in GitHub Actions on Linux with Python 3.8 and 3.12.

### Real runs on version 0.2.0

These runs used `claude -p` (one request, one answer) on a Mac. Claude Code 2.1.312, Python 3.9.6, model Claude Haiku 5.5. Permission prompts were turned off. The workspace was a copy in another folder, with no settings from the home folder.

- Two runs from the first question to the start of building. The stages and the approval records worked.
- A message that looks like a known key was stopped before Claude saw it. The reason was shown.
- When Claude tried `secret set`, it was refused, because there is no terminal for typing the value.
- A `CLAUDE.md` inside brought-in code is loaded by Claude Code when Claude reads a file in that folder. We tried this once without and once with the exclude setting, using a dummy instruction. The setting stopped it. We tested `CLAUDE.md` only, not `CLAUDE.local.md` or `.claude/`.
- Hardened mode, with test paths and test scripts, not the exact setting we ship: reading one folder and `.env` was refused. The exception for `ws.sh` worked.

### Real runs on version 0.3.0

In three `-p` runs on 2026-10-30 (Sonnet, `bypassPermissions`, on a Mac), the prototype file was created in 3 of 3 runs. The Japanese run answered in Japanese in every turn. The browser was not opened in these runs (a dry run). These runs did not ask the reference question, and permission prompts were turned off.

### Tests of the guards and unit tests

These tests feed input straight to the guards, or run pieces of the engine. They are not real sessions. They are in `tests/`. To run them, see [For developers](for-developers.md#run-the-tests).

- Writing code before approval, opening a key file, searching for key files, and a raw `git push` were stopped.
- Save stopped when a key was in the files. Backup refused to send when the history had a key. The publish check failed without a README and a license. These were tried against a local repo, not against GitHub.
- The version 0.3.0 changes were tested only this way.

## What we have not checked yet

- How long the first picture takes. We have not measured it.
- The reference question, and the prototype built from a reference. They were not run in a real session.
- The one-sentence start (`BOOTSTRAP.md`): we have not tested it on a real machine. A plain Claude Code may not read it, or may not follow it.
- The place check (`doctor`) only warns. It does not stop you from using a bad place.
- Normal use: starting `claude` with the 3 lines in the README and working with it in a real conversation.
- Windows (Git Bash and native), Linux, and machines with no Python 3.
- The hook launcher `hook.sh` on Windows, in Git Bash and in PowerShell.
- Claude answering in the user's language. It was not run in a real session.
- Whether Claude follows the plain-words page in a real session.
- Whether `Write(projects/**)` in `permissions.allow` works on a real machine.
- Whether the form of `filesystem.denyWrite` is accepted by Claude Code.
- The VS Code extension.
- Models other than Haiku.
- Sending to a real GitHub repo, and the login approval.
- Bringing in a real GitHub repo and continuing with it.
- Telling a public repo from a private one on real GitHub.
- Typing a key in a separate Terminal window.
- Connecting to a real service that needs a key.
- Whether Claude Code loads `.claude/` or `CLAUDE.local.md` from brought-in code.
- Whether the first "Do you trust this folder?" question changes how the hooks work.
- Bringing in files, URLs, and screenshots as material.
- Watching people who are new to this workspace use it.
- Runs with the normal permission prompts turned on.
- The question "continue or start new" when a project already exists. The hook alone was tested.
- Looking at the design in Claude artifacts, or in Gakaso (our own product).
- Checking test cases by hand, one by one, from the numbered list.
- Claude using the browser to take a screenshot as evidence.
- Whether MCP tools added later are blocked when they try to write to `src/` before you approve.
- Calling the `reviewer` and `connector` agents.
- Hardened mode with network work.
- How `overview.html` and the test case page look in each browser.
- How well the apps that Claude builds work when a person uses them.
