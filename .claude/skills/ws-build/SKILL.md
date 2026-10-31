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
5. When `builder` returns, read the evidence. If it was not run, it is "not checked". Then ask `reviewer` to read it. **Call `reviewer` before you say that anything is done.**
6. Mark a row done only after it ran: `bash ws/bin/ws.sh mark <ID> done --evidence "<what ran, and the result>"`. If the evidence has any of `> < ; & | $`, the hook stops the command: write the evidence in a file and use `--evidence-file <path>`. Missing or short evidence is refused.
7. Start the next row: `bash ws/bin/ws.sh mark <ID> doing`.
8. If a row cannot meet its done condition, use `bash ws/bin/ws.sh mark <ID> hold --note "<reason>"`, and tell the user why.
9. Report each row in one or two sentences: what works now, and what is next.
10. If you want to add something that is not in the design, go back to `pm`. Change the design first. The approval resets.

## What "done" means

**Done is not "tests are green".** Done is: the outputs the user wanted, in the normal case and the failure case, really come out.

- Make the test list: `bash ws/bin/ws.sh st init` (or `schedule-init`). It adds cases and never changes the result of cases that exist. Case ids look like `T-IO-01-N1`: N is normal, B is empty or edge, F is failure.
- Show the list with numbers: `bash ws/bin/ws.sh st list --numbered`. Show the card `bash ws/bin/ws.sh learn systemtest` once. The user may answer by number.
- Run every case the way a person would. Do not skip cases.
- **Record the result.** Each case has a "who checks it". The engine sets it from the case type. Never say `ai` or `user` to the user.
  - **The user ran it, and answers by number.** The user types numbers from the last list, for example `1, 2 pass` or `1-3 pass`. Run `bash ws/bin/ws.sh st mark numbered pass --by user`. Add `--evidence "<what the user saw>"` if they said it. One message can record many cases. The engine replies `recorded: T-…, T-… (p/t passed)`. Tell the user what was recorded.
  - **The user answers by case id.** Run `bash ws/bin/ws.sh st mark <ID> pass --by user`. The id may be the last part of the id (parts split by `-`, 5 characters or more, as a whole word). The latest message must also have a word like `pass`, or enough words about what they saw. "ok" and "works" alone are not enough. One message records one mark, and then it is used up. The engine tells you if it refuses.
  - **A bulk answer.** `all pass` counts only if you showed the list in the last three messages.
  - **It failed:** `bash ws/bin/ws.sh st mark <ID> fail --by user --evidence "<what the user saw>"`.
  - **Claude's cases only.** For a case that the engine marks as checked by Claude, run `bash ws/bin/ws.sh st run <ID…>` (the project's tests), or record a screenshot: `bash ws/bin/ws.sh st mark <ID> pass --by ai --shot <image> --evidence "<what you saw>"`. The image must be inside `projects/<name>/` and made in this session. **Both are refused for a case the user checks**, because Claude must not fill in "You checked".
- **Evidence text.** You can give `--evidence "<text>"`, `--evidence -` (text from standard input), or `--evidence-file <path>`. If the text has any of `> < ; & | $`, the hook stops the command and says: "Don't put … Use --evidence-file or rephrase." Then write the evidence in a file inside the project and use `--evidence-file <path>`.
- `bash ws/bin/ws.sh st run <ID…> [--timeout N]` finds the runner by itself (`package.json` `scripts.test`, `pytest.ini` or `pyproject.toml`, `go.mod`, `Cargo.toml`) and records the exit code and the last 50 lines. It has no `--cmd` option. If there is no runner, it says so.
- A case that the user truly cannot trigger by hand (for example a monthly job) can be moved to Claude: `bash ws/bin/ws.sh st route <ID> ai --reason "<why>"`. The reason needs 4 or more characters. `st route <ID> user --reason "<why>"` moves it back. Do not move a case just to finish sooner. `--by ci` and `--by ut` are gone.
- If a judgment is unclear, do not add words to the list. Go back and make the design (`io.json`) clear. The approval resets, and unchanged cases keep their results.
- If a message says a record is "unsigned" or "signature does not match", tell the user. Only with the user's words may you run `bash ws/bin/ws.sh resign`.

## The first version is done

The first version is done when **every case the user can run has passed, and every normal case has passed**. Then say this, with the real numbers:

`First version done! You checked: 12/12. Claude will check: 3/5 (things you can't trigger by hand, like the monthly job). Not yet checked: 2.`

- If the goal is public (`public-free` or `public-paid`) and Claude's part is not finished, warn once before publishing.
- Say once: To open what you made: double-click `projects/<name>/src/index.html`.

## After DONE

`src/` and Bash work the same as in RUN. If a new request comes, ask: add to this project, or start a new one? To add, put a row in `io.json`. The approval resets by itself and we return to R4. For a new project, go to `ws-ask`.

## Checking a screen

For a project with a screen, `builder` opens `src/index.html` with the Playwright browser tools and saves a screenshot under `projects/<name>/`. Follow `ws-secrets` if a key may be on the screen. If the browser tool (Playwright) is not available, do not try to install it. Ask the user to open the page and tell you what they see. Say this in the user's language.
