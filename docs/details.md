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
| RUN | Claude builds, one row at a time. Then you try the numbered checks, once for each thing you asked for | Claude must run a row and note the result before it marks the row done. The workspace does not check that the note is true |
| DONE | First version is done. Claude asks once whether it does what you wanted | New requests start at R4 again |

If you change the design or the table after you approve, the approval is reset. Claude tells you, and you look again.

## Where you are, and what to do next

Version 0.5.0 adds these parts. Their job is that you can tell, at any moment, where you are and what to do next. The engine works them out from the files, the same way it works out the stage. Claude is told to pass them on. Claude does not decide them.

**The next step.** For every state, the engine has one sentence for the one thing you do next: answer a question, type exact words, look at a page, try the checks, or wait. It adds that sentence to what Claude reads at the start of a session and with every message (`Next for the user: …`, and `Exact words: …` when you must type a word such as `looks good`). Claude is told to end each reply with one line that starts with `▶` and says that one thing. The Stop hook reads the last reply. If no line starts with `▶`, it holds the reply once and gives Claude the sentence again. It does this at most once for each of your messages, and not at all when it cannot read the reply. It checks that the line is there. It does not check what the line says. `bash ws/bin/ws.sh next` prints the sentence.

**When Claude stops too early.** "Wait" is shown only while Claude's reply is running. If Claude is about to stop while the missing thing is still Claude's own work (the first picture, the table, the plan, a build step, a fix, its own checks), the Stop hook holds the reply once and tells Claude to go on. It does not do this in the first reply of a session at the build stage, because that reply is read-only. If Claude stops anyway, your next step is no longer "wait". It is the word `continue` (`続けて`), in the chat and on the guide page. So the page does not say "Claude is working" after a reply has ended. One limit: if you interrupt Claude (Esc), no hook runs, and the page keeps "Claude is working" until your next message or the next start of a session.

**The guide page.** `projects/guide.html` shows your goal in your own words, the six steps with "You are here", whose turn it is, the one next step (with a Copy button when there are exact words to type), the pages you can open, how many build steps and checks are done, and what to type when you are not sure. When you have two or more projects and have not chosen one yet, it shows the next step (say `continue` or `new`) and the list of projects. The engine writes the page at the start of a session, with every message, and when a reply ends. It also writes it after a `ws.sh` command that can change the state (not after `status`, `list`, `doctor` or `version`). It writes the file only when something changed. Next to it, it writes `projects/guide.data.js` with the same data. The open page loads that file again every 2 seconds, so it is built to update without a reload. It loads nothing from the internet.

What keeps the page honest, exactly: Claude's edit tools are refused for both files, at every stage. Claude's Read tool is refused for them too. A shell command that names `guide.html`, `guide.data.js` or `schedule.html` (in any letter case, also when the name is split by quotes) is refused at every stage, so the schedule pages are covered the same way. The page takes new data only from a call that carries a word for this workspace. The engine makes that word from the signing key, which is outside the workspace (`~/.createcodebox`, a place Claude's tools are refused), and from the workspace path. It puts the word into the page and into the data file, and stores it nowhere else. If the key cannot be used, the word is made from the path alone and is no secret. This does not make the page impossible to forge. A search over the whole folder or a wildcard can still read the page, and after you approve, Claude can run programs: a program that builds the file name in pieces is not seen by these checks.

`bash ws/bin/ws.sh guide` opens the page. Claude is told to run it once, right after your first project is made.

**When you are not sure what to do.** Send a short message such as `help`, `help me`, `what now?`, `what's next?`, `I'm lost`, `迷った`, or `助けてください` (the full list is in `ws/lang/synonyms.py`). The engine then gives Claude a recap: your goal, the step you are at, what is done, and the one next step. Claude is told to do no other work in that turn. Such a message is never taken as an approval, and it is not sorted onto the task board. A longer sentence that only contains one of the words ("help me add a login page") does not count. `bash ws/bin/ws.sh where` prints the same recap.

**Who checks what.** You check what you asked for, once each: the normal case of each thing a person can try. The empty and failure cases, and anything that cannot be started by hand (such as a job on a timer), are Claude's to check. The workspace shows which of those are not checked yet. The first version is done when every case that you check has passed and every normal case has passed, so Claude's empty and failure cases do not hold it back. When the build steps are done, Claude is told to open the app for you, to show all of your checks in one numbered list, and to ask for one answer by number. Claude is told not to ask you to change browser settings, clear stored data, use developer tools, or look for a file. A test list made before version 0.5.0 keeps the split it has.

**How your answer is read.** You answer by number in everyday words: "1, 2 and 4 worked; 3 did not", "1 to 7 are fine", "all worked", 「1から7まで全部できました」. A range counts for every number in it. A number is recorded as passed only when a positive word belongs to it. A number with a word that says it failed, or with no such word, is not recorded, and Claude is told which ones. "All pass but 3" records every listed number except 3. Only the part of a sentence before a colon is read, so a number in an explanation ("1 passed: I added 3 coffees") is not taken as a check. When the engine is in doubt, it records nothing.

**Finishing with your own word.** Claude may be unable to run its own cases, or may stop with build steps not marked. You are not kept at the build stage for that. When the app (`src/index.html`) exists and you have passed every one of your own checks, you can type `finish` (also `finish as it is`, `use it as it is`, `完成にする`, `このまま使う`, `これで完成`). Only your own message records it, as a signed record bound to the design, like an approval. No command and no reply of Claude can write it. The stage is then DONE, and the status line, the recap and the test list say how many of Claude's checks and build steps were left. If the design changes, the record no longer counts.

**How Claude tries the page.** `bash ws/bin/ws.sh try <page.html>` runs a page of the project in a browser without a window, on a new empty profile, and prints the text on the page, the console lines, and the path of a screenshot. It can run a script before the page's own scripts (`--before`, for stored data or a fixed date) and one after the page has loaded (`--after`, to click, type, and return what it sees). It uses Chrome, Edge, Chromium or Brave if one is already on the computer. It installs nothing. If there is none, it says so, and those checks stay "not checked". It runs a file inside the project only, never a web address. The page itself can still load from the internet if its own code does so.

**The goal question.** When the first version is done, the engine gives Claude one fixed question: "You wanted: (your own words). Open the app and try it. Does it do that? Reply yes or not yet." Your answer is recorded only when the reply before your message put the question to you. The Stop hook checks this: the reply must name both answers (yes and not yet, or 「はい」 and 「まだ」). Then your very next message is recorded if it is a plain yes (`yes`, `yes it does`, `it does`, `はい`, `できた`, `届いた`, `そうです`) or a plain not yet (`not yet`, `no`, `まだ`, `まだです`, `いいえ`). A `yes` to any other reply is not recorded. `yes please`, `y` and `お願いします` are not on the list. The latest answer wins: each time the question is put again, a new answer replaces the old one. Two more cases change a record without a new question. After `not yet`, a short message that says the app is finished ("it's finished now", 「完成した」) records yes. After `yes`, a plain `not yet` (`まだ`), or a short message that says it is not what you wanted, records not yet. The record is signed, like an approval, and it counts only for the design as it is: if you add a feature later, the question comes back when that is built. Claude is told to ask the question word for word at most once in a session, not on top of a new request, and again when you say the app is finished. Until the question has been put in the session, your next step at this stage is to say what to add or change. The stage stays DONE either way. The check for the question looks for English or Japanese words, so in another language the answer is not recorded.

**The finished look.** The first picture is rough and grey on purpose: it is a question. The design that you agree to is the finished look, in colour. The workspace ships a small style kit (`ws/templates/look.css`, explained in `ws/templates/look.md`). Claude is told to start the design from it, to choose one accent colour and say why, and to build the app with the same styles. If the design page has no colour when you are asked to agree to it, the engine adds one line for Claude that says so. It is a note. It does not stop anything.

**When the workspace says done.** Claude is told to say that the first version is ready as soon as the stage is DONE, in a few short lines, and to ask the goal question. Smaller things a review found go on the task board and are offered after your answer. After DONE, Claude can still replace the records of its own checks (for example with a new screenshot after a fix). Your own checks stay as they are.

## Language

Claude is told to answer in the language you write in. Fixed text from the workspace is in English or Japanese. Claude translates it when it passes it to you. Text inside backticks, such as `approve`, is never translated. Type those words exactly.

Claude writes to you in everyday words. The table of technical words and what to say instead is `ws/style/plain-words.en.md` (Japanese: `plain-words.ja.md`). The same list is in `ws/style/words.json`.
For now, a rule tells Claude to read it. A reminder on every turn and an automatic check (lint) are planned for the next version.

## Models

Default: the model you choose in Claude Code. The helper agents `connector` and `reviewer` use Haiku.

## Names and where to report problems

- Report a step that did not work in GitHub Issues. Ask questions in GitHub Discussions.
- Report a weakness in private, as [SECURITY.md](../SECURITY.md) explains.

## What we have checked

The unit tests are in `tests/`. In version 0.5.0, `test_engine.py` has 1020 checks, `test_hook_protocol.py` has 46, and `test_codex.py` has 164. All of them pass on a Mac with Python 3.9. GitHub Actions runs them on Linux with Python 3.8 and 3.12. We have not run the workspace in a real, interactive Claude Code session with a person. The real runs below are `-p` runs.

### Real runs on version 0.5.0

These runs were made on 2026-11-10 on a Mac, with Claude Code 2.1.322 and Python 3.9.6. They are test runs, not sessions with a person:

- Each run starts from a fresh copy of the workspace in its own folder inside the home folder, with only the workspace's own settings.
- Each message is one `claude -p` call that goes on with the same session (`--resume`). The hooks run on every message, as they do in a conversation, but nobody sits at the screen.
- Permission prompts were turned off (`bypassPermissions`).
- The person was played by a second AI (Claude Sonnet 5.5, with no tools). It was told to act as someone who has never built software. It saw only what Claude wrote and the text of the pages (drawn in a browser without a window), and it had to say so when it could not tell what to do next. When Claude asked it to try the numbered checks, it answered from the text of the app's page; it did not click in the app.
- The system's `open` command was replaced by a stand-in that writes down the path and reports success. No browser window was opened.
- A run ended when the person said they were finished, or after 45 messages.

| Version | Model | What the person asked for | Messages | First version done | "I can't tell what to do" |
|---|---|---|---|---|---|
| 0.4.8 | Sonnet 5.5 | A counter for drinks sold at a cafe (English) | 45 (the limit) | no | 3 |
| 0.4.8 | Sonnet 5.5 | A list of who has paid a yearly fee (Japanese) | 45 (the limit) | no | 2 |
| 0.5.0, first build | Sonnet 5.5 | A packing checklist (Japanese) | 13 | yes | 0 |
| 0.5.0, first build | Sonnet 5.5 | The fee list (Japanese) | 16 | yes | 0 |
| 0.5.0, first build | Sonnet 5.5 | The drink counter (English) | 11 | not reached: our account's usage limit cut the run after the person's checks had passed | 0 |
| 0.5.0, first build | Sonnet 5.5 | A habit tracker with a month grid (English) | 42 | no | 1 |
| 0.5.0, one change before this version | Fable 5.2 | The packing checklist (Japanese) | 10 | yes | 0 |
| 0.5.0, one change before this version | Fable 5.2 | The drink counter (English) | 10 | yes | 0 |
| 0.5.0, this version | Sonnet 5.5 | The habit tracker (English) | 11 | yes | 0 |
| 0.5.0, this version | Fable 5.2 | The packing checklist (Japanese) | 9 | yes | 0 |
| 0.5.0, this version | Fable 5.2 | The drink counter (English) | 11 | yes | 0 |

What we saw:

- In the two runs on 0.4.8 the check stage never ended. All 17 and 25 checks were given to the person, some of them needed the browser's stored data to be cleared, and after the person said "thank you" the replies had no next step.
- In the habit-tracker run on the first build of 0.5.0, three checks could only be done by Claude (they need marks on earlier days and a change of month), Claude had no way to run the page, and the stage did not end. This is why this version has `ws.sh try`, the word `continue` when Claude has stopped, and the word `finish`.
- In the last five runs in the table, Claude used `ws.sh try` (with Chrome) for its own checks, each run reached "first version done", and Claude asked the goal question at the end.
- In the three runs on this version, the person's answer to the goal question (yes) was sent too, and the workspace recorded it. Their message counts include that answer.
- In the two Fable 5.2 runs on this version, one message each was cut by our account's usage limit. The run went on with the word `continue` (`続けて` in the Japanese run).
- "One change before this version" means the build before the last three small changes (where the word of the guide page comes from, the small boxes around words to type on the guide page, and the guard for `schedule.html`).

What these runs do not show: how a person does. The AI that played the person reads every reply in full and does not get tired. "I can't tell what to do" is that AI's own report. The runs also do not show an interactive session, a real browser window, permission prompts, Windows, or how well the finished apps work when a person uses them.

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
- The version 0.5.0 parts are covered by these tests: every state of the next step in English and Japanese, the Stop answers, the data the page gets, the reading of answers by number, the records of `finish` and of the goal answer, and `ws.sh try` with a stand-in browser. One test runs `ws.sh try` with a real browser when the computer has one.

## What we have not checked yet

The runs on version 0.5.0 above were `-p` runs in which an AI played the person. Everything below is still not checked in an interactive session with a person.

- How long the first picture takes. We have not measured it.
- Whether Claude ends each reply with the `▶` line in a real session, and how often the Stop hook has to hold a reply for it.
- The Stop check when Claude Code gives the hook no last reply and the transcript file is behind: the hook may then read an older reply.
- The guide page in each browser: whether it updates by itself from a `file://` address, and how it looks.
- Whether a person who types `help` gets the recap in plain words.
- The goal question in a real session.
- Whether Claude shows all of your checks in one list and asks for one answer, and whether it checks its own empty and failure cases, in a real session.
- `ws.sh try` with Edge, Chromium or Brave, on Windows and on Linux. We ran it with Chrome on a Mac only.
- Whether Claude uses the style kit and gives the design a finished look. The kit itself was looked at in Chrome only.
- The guide page after an interrupt (Esc): it keeps "Claude is working" until your next message.
- The reference question, and the prototype built from a reference. They were not run in a real session.
- The one-sentence start (README step 3, `BOOTSTRAP.md`): we ran it on a Mac only, in test runs with permission prompts turned off. We have not run it in a normal session, or on Windows. A plain Claude Code may not read it, or may not follow it.
- The place check (`doctor`) only warns. It does not stop you from using a bad place.
- Normal use: starting `claude` in your app's folder, as the README shows, and working with it in a real conversation.
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
