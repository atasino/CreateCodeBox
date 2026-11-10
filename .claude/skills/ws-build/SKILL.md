---
name: ws-build
description: Use after the user approves (stages RS, RUN, and DONE) to make the schedule, build one row at a time, check the result with the test list, and decide when the first version is done. Done means every case was really run and passed, not that tests are green.
---

# ws-build: schedule, build, and check (RS, RUN, DONE)

`pm` manages. `builder` builds one row at a time. This runs only while the approval is valid. If the approval is reset, go back to R4 (`ws-design`).

Words the user sees (the screen, error sentences, the done message) follow `ws/style/plain-words.<lang>.md` (the language of the user's latest message).

## Schedule and build

1. **RS.** Run `bash ws/bin/ws.sh schedule-init`. It makes the schedule. It adds rows and never changes the status of rows that exist. The rows are: get ready, one row for each `IO-xx`, and "run it once with the user's example".
2. Run `bash ws/bin/ws.sh render`. Open `design/schedule.html` with `ws.sh open` so the user sees the progress.
3. **RUN.** `src/` can now be written. Ask `builder` for the current row (status `doing`). One row at a time.
4. The default result is **one HTML file** that opens by double-click: `projects/<name>/src/index.html`. A server (`npm start`) is only for a user who asked for it.
5. When `builder` returns, read the evidence. If it was not run, it is "not checked". When the build rows are done, ask `reviewer` to read the work **once, before you show the user their checks**, so that real defects are fixed before the user tries the app. Do not start a review after the user has passed everything.
6. Mark a row done only after it ran: `bash ws/bin/ws.sh mark <ID> done --evidence "<what ran, and the result>"`. If the evidence has any of `> < ; & | $`, the hook stops the command: write the evidence in a file and use `--evidence-file <path>`. Missing or short evidence is refused.
7. Start the next row: `bash ws/bin/ws.sh mark <ID> doing`.
8. If a row cannot meet its done condition, use `bash ws/bin/ws.sh mark <ID> hold --note "<reason>"`, and tell the user why.
9. Report each row in one or two sentences: what works now, and what is next.
10. If you want to add something that is not in the design, go back to `pm`. Change the design first. The approval resets.

While you build, the `▶` line at the end of each reply tells the user there is nothing to do yet. After `mark`, `st mark` or `schedule-init`, run `bash ws/bin/ws.sh next` before you write that line: when the build rows are done, it tells the user to try the numbered checks. The guide page (`projects/guide.html`) shows the build and check counts and follows each `ws.sh` command.

## See and test the page yourself: `ws.sh try`

To see or test a page yourself, use `bash ws/bin/ws.sh try projects/<name>/src/index.html` (it needs no extra tool). It runs the page in a browser without a window, on a new empty profile, and prints the text on the page, the console lines, and the path of a screenshot under `projects/<name>/evidence/`. `--before <file.js>` runs before the page's own scripts (set stored data, or fix the date with a small `Date` override). `--after <file.js>` runs after the page loaded (click, type, and `return` what you see). The script files are inside `projects/<name>/`.

- Use it for the evidence of each build row (`mark <ID> done --evidence` can quote what it printed) and for your own cases. The empty state: a new profile is empty by itself. A failure or a date case: put the stored data or a small `Date` override in `--before`.
- The screenshot it makes can be used for your own cases: `bash ws/bin/ws.sh st mark <ID> pass --by ai --shot <that image> --evidence "<what came out>"`.
- If it says that no browser was found, do not install anything. Those checks stay "not checked". Say once how many, and go on.
- The Playwright browser tools are optional. `try` is enough.

## What "done" means

**Done is not "tests are green".** Done is: the outputs the user wanted, in the normal case and the failure case, really come out.

- Make the test list: `bash ws/bin/ws.sh st init` (or `schedule-init`). It adds cases and never changes the result of cases that exist. Case ids look like `T-IO-01-N1`: N is normal, B is empty or edge, F is failure.
- **Who checks what.** The user checks what they asked for, once each: the normal case (N) of each thing a person can try. Every empty or edge case (B) and every failure case (F) is Claude's, and so is anything that cannot be started by hand. A list made before version 0.5.0 keeps the split it has.
- **When the build rows are done**, open the app for the user first: `bash ws/bin/ws.sh open projects/<name>/src/index.html`. Say that it opened only if the output says so.
- Show the list with numbers: `bash ws/bin/ws.sh st list --numbered`. It has only the cases the user checks, numbered from 1, and one line that counts Claude's. Show all of the user's checks in one numbered list, each as "do this → you should see this" in plain words. Ask for one answer by number, for example "1, 2 and 4 worked; 3 did not". Never ask for one check per turn. Show the card `bash ws/bin/ws.sh learn systemtest` once.
- Never ask the user to change browser settings, clear stored data, use developer tools, or find a file in Finder or Explorer. If a case needs that, it is Claude's case: `bash ws/bin/ws.sh st route <ID> ai --reason "<why>"`.
- Run every case the way a person would. Claude's cases are in `bash ws/bin/ws.sh st list` (the full list).
- **Record the result.** Each case has a "who checks it". The engine sets it from the case type. Never say `ai` or `user` to the user.
  - **The user ran it, and answers by number.** The user types numbers from the last list, for example `1, 2 pass` or `1-3 pass`. Run `bash ws/bin/ws.sh st mark numbered pass --by user`. Add `--evidence "<what the user saw>"` if they said it. One message can record many cases. A number that the message says did not work ("3 did not") is not recorded as passed: the reply names it. Record what the user saw with `st mark <ID> fail`, fix it, set it back with `bash ws/bin/ws.sh st mark <ID> todo`, and ask the user to try it again. The engine replies `recorded: T-…, T-… (p/t passed)`. Tell the user what was recorded.
  - **The user answers by case id.** Run `bash ws/bin/ws.sh st mark <ID> pass --by user`. The id may be the last part of the id (parts split by `-`, 5 characters or more, as a whole word). The latest message must also have a word like `pass`, or enough words about what they saw. With a case id, "ok" and "works" alone are not enough. (An answer by number takes everyday words: "1, 2 and 4 worked", "1 to 7 are fine", 「1から7まで全部できた」. A number with no such word, or with a word that says it failed, is not recorded, and the reply names it.) One message records one mark, and then it is used up. The engine tells you if it refuses.
  - **A bulk answer.** `all pass` counts only if you showed the list in the last three messages. Then `bash ws/bin/ws.sh st mark numbered pass --by user` records every case of the numbered list. "All pass except 2" is not a bulk answer.
  - **It failed:** `bash ws/bin/ws.sh st mark <ID> fail --by user --evidence "<what the user saw>"`.
  - **Claude's cases only.** For a case that the engine marks as checked by Claude, run `bash ws/bin/ws.sh st run <ID…>` (the project's tests), or record a screenshot: `bash ws/bin/ws.sh st mark <ID> pass --by ai --shot <image> --evidence "<what you saw>"`. The image must be inside `projects/<name>/` and made in this session. **Both are refused for a case the user checks**, because Claude must not fill in "You checked".
- **If you cannot check one of Claude's cases** (no test runner, no browser tool), say once how many are not checked, and go on. They do not block the first version. `status` and the list show which are not checked yet.
- **Evidence text.** You can give `--evidence "<text>"`, `--evidence -` (text from standard input), or `--evidence-file <path>`. If the text has any of `> < ; & | $`, the hook stops the command and says: "Don't put … Use --evidence-file or rephrase." Then write the evidence in a file inside the project and use `--evidence-file <path>`.
- `bash ws/bin/ws.sh st run <ID…> [--timeout N]` finds the runner by itself (`package.json` `scripts.test`, `pytest.ini` or `pyproject.toml`, `go.mod`, `Cargo.toml`) and records the exit code and the last 50 lines. It has no `--cmd` option. If there is no runner, it says so.
- A case that the user truly cannot trigger by hand (for example a monthly job) can be moved to Claude: `bash ws/bin/ws.sh st route <ID> ai --reason "<why>"`. The reason needs 4 or more characters. `st route <ID> user --reason "<why>"` moves it back. Do not move a case just to finish sooner. `--by ci` and `--by ut` are gone.
- If a judgment is unclear, do not add words to the list. Go back and make the design (`io.json`) clear. The approval resets, and unchanged cases keep their results.
- If a message says a record is "unsigned" or "signature does not match", tell the user. Only with the user's words may you run `bash ws/bin/ws.sh resign`.

## The first version is done

The first version is done when **every case the user can run has passed, and every normal case has passed**. Then say this, with the real numbers:

`First version done! You checked: 12/12. Claude will check: 3/5 (the empty and failure cases, and things you can't trigger by hand, like the monthly job). Not yet checked: 2.`

- **When the workspace says done, you say done.** The stage in the context is the truth the user hears. First tell the user, in at most six short lines: the first version is ready, how to open it (you opened it, and the guide page has the link), the real counts, and the goal question. Do not start a review loop now, and do not say "I will not call it done yet".
- Things `reviewer` found that do not break what the user asked for go on the task board (`task add`). Offer them in one line after the goal answer: "I noted 3 small things to improve. Say `what is left?` to see them." Do not ask permission for them before the goal question. If something breaks what the user asked for, say that one thing plainly and fix it.
- **Say less.** At RUN and DONE, tell the user only what they can do now, what works, and what is not checked, in about eight short lines before the `▶` line. No row or case IDs, nothing about helpers, reviews, records or signatures. No new design question after approval unless the user's own check failed: decide it, note it as `tentative:` on the task board, and say it in one line.
- **If you cannot finish your own cases.** After a real attempt (`ws.sh try`, `st run`), say once, in two sentences, what is not checked, and tell the user the exact word that finishes as it is: `finish` (Japanese: `完成にする`). Only the user's own message records it, and only when the app exists and the user has passed all of their own checks. Never keep the user in a loop. If you stop while work is still yours, the user's next step becomes the word `continue`.
- If the goal is public (`public-free` or `public-paid`) and Claude's part is not finished, warn once before publishing.
- Say once: To open what you made: double-click `projects/<name>/src/index.html`.
- **The goal question.** The context then gives one fixed question: the user's goal in their own words, and whether the app does that. Ask it once, word for word, and nothing else in that turn. The workspace records only the user's own plain `yes` or `not yet` (`はい` or `まだ`). After `yes`, the `▶` line says the app is ready. After `not yet`, ask what is missing, put it on the task board (`ws-tasks`), and add a row to `io.json`.

## After DONE

`src/` and Bash work the same as in RUN. After a fix, your own check records can be replaced at DONE: `st mark <ID> pass --by ai --shot <a new image> --evidence "<what came out>"`, or `st run <ID>`. The user's checks stay as they are. If a new request comes, ask: add to this project, or start a new one? To add, put a row in `io.json`. The approval resets by itself and we return to R4. For a new project, go to `ws-ask`.

## Checking a screen

For a project with a screen, `builder` runs `src/index.html` with `bash ws/bin/ws.sh try` and reads what it prints. The screenshot is saved under `projects/<name>/evidence/`. The Playwright browser tools can be used too, if they are there. Follow `ws-secrets` if a key may be on the screen. If no browser is found, do not try to install one. Ask the user to open the page and tell you what they see. Say this in the user's language.
