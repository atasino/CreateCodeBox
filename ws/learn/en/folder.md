<!-- card: folder v3 -->
# Learn card: Folders and paths

## In one line
A folder is a box that holds files. A path tells you which boxes to open to find a file.

## Think of it as
Boxes inside boxes. The path lists the boxes from the outer one to the inner one, with `/` between them.

## What happens now
- Your home folder is the outer box that holds all your own things. It is written `~`.
- This workspace is one folder inside it. Each thing you make has its own folder in `projects/`.
- Claude works inside the workspace. It reads and writes files there.
- Some things are outside on purpose, such as your keys (the folder `~/.createcodebox`). The workspace is set up to stop Claude from reading those.
- In the Terminal, `pwd` shows where you are. `cd <path>` moves you to another folder.

## Watch out
- Do not keep personal files, such as documents and photos, inside the workspace.
- If you share or copy a folder, everything inside goes with it. Check what is inside before you send it.
- Keep the workspace in your home folder, for example `~/CreateCodeBox`. Do not keep it in Downloads, Desktop, Documents, or a folder that syncs to the cloud. `bash ws/bin/ws.sh doctor` warns if it is in such a place.

## The technical name
A path, a directory, and the home directory.
