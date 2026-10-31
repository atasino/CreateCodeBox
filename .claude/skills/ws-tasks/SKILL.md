---
name: ws-tasks
description: Use at the start of every session, and whenever the user adds, changes or withdraws a requirement or a wish, reports a problem, gives or changes a date, or asks what is left, how it is going, the status, the progress or the schedule (also 残り, 進み具合, 予定, スケジュール, ガント, 何が残って). Keeps one task board for all projects, so that nothing is dropped between sessions, and shows the schedule.
---

# ws-tasks: what is left, for every project

The board is the one place for what must still be done. Each item has a project, a kind (`req` wish, `todo`, `issue` problem), a state, and dates. The board also shows the missing items of the stage and the open rows of the build schedule. The context shows an open-items block at the start and at every turn.

Words for the user follow `ws/style/plain-words.<lang>.md`. Say "wish", "problem" and "to-do", not `req` or `issue`. Never show ids like `T-03` as the only name: say the title too.

## Record before you act

When the context says to sort the message, do it first. Until you do, edits and commands that write are stopped.

1. For each new or changed wish, problem, to-do or date in the message, run `bash ws/bin/ws.sh task add "<title>" --kind req|todo|issue`. One short line, in the user's words. Add `--start` and `--due` (`YYYY-MM-DD`) when there is a date.
2. To change one: `task set <id> doing|done|hold|dropped`, or `task date <id> <start|-> <due|->`. To withdraw one, `task set <id> dropped --note "<why>"`.
3. If the message adds nothing, run `bash ws/bin/ws.sh task none`.
4. Each of these commands ends with `Schedule updated: <path>`. Tell the user in one short line that the schedule is updated. Give that full path, and name the items that changed. Do not show the grid for this.

Run each `ws.sh` command on its own. Do not join commands with `&&`, `;` or `|`: the hook stops them.

Decide what you can decide. Do not ask the user about the kind, the title or the order.

## Dates

- Give each wish and to-do a start and a due date, in work order. They are guesses by default, and the board marks them with `~`.
- When the user gives or changes a date, record it with `--fixed`: `task date <id> 2026-11-05 2026-11-08 --fixed`. It is no longer tentative.

## Done

Never run `task set <id> done` for work you did not run or check. Write what you ran and what you saw in `--how` (8 characters or more). Build rows (`S-xx`) use the same commands and the rules of `ws-build`.

## Show the list or the schedule

- "What is left?" or "how is it going": run `bash ws/bin/ws.sh tasks` and show the list.
- "Show the schedule" or a question about dates: run `bash ws/bin/ws.sh tasks gantt --text`. Show the text grid in the chat (`#` fixed date, `~` guessed date, `=` done, `>` doing, `^` today). Give the page path (`projects/schedule.html`, the full path the command prints). The hooks keep it current, and it reloads by itself.
- Show the grid at the start of a session only when the user is choosing continue or new. Not after every update.

## At the start of a session

Read the task board block. With more than one project, use it to help the user choose: continue one (say what is open in it), or start a new one. With one project, say in one line what is open, then follow its stage.
