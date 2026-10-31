<!-- card: save v3 -->
# Learn card: Save

## In one line
Save keeps a record of how your work looks right now. The record stays on your computer.

## Think of it as
Making a copy of your notebook page on a copy machine. You write the date and a short note on the copy, and you keep every copy.

## What happens now
- You run `bash ws/bin/ws.sh save "<note>"`. It records all changes in your project's `src/` folder since the last save, with your note.
- Before it records, the workspace checks for keys in known formats (for example text that starts with `sk-` or `ghp_`). If it finds one, it stops and records nothing. It cannot see a password or a key in an unknown format.
- Save works only on your computer. Nothing is sent to the internet.
- The records keep earlier states. There is no command yet to go back to one.
- If you brought in your own repo (a project folder that Git tracks), save does not use `main` (the main line). It uses a branch (a separate line of work) named `createcodebox/<date>`.

## Watch out
- Write in the note what you changed, in one line. It is easier to find later.
- If a key stopped the save, remove the key and save again.
- Save is not a backup. If your computer breaks, the records are lost too.

## The technical name
A Git commit. One record is one commit. Your note is the commit message.
