<!-- card: github v3 -->
# Learn card: GitHub, branches, and bringing in a repo

## In one line
GitHub is a website that keeps a copy of your work online. If your computer breaks, the copy is still there.

## Think of it as
A safe at the bank. You keep a copy of your notebook there, and you decide who gets a key.

## What happens now
- A repo (a project folder that Git tracks) holds your project on GitHub. You make it on the GitHub website. Make it **private** at first. GitHub's own help shows the steps.
- Give `pm` (the assistant you talk to) the web address (URL) that starts with `https://`. It runs `bash ws/bin/ws.sh repo link <URL>`.
- When you ask, `pm` runs `backup`. It sends your saved records to that repo. A key check runs first, the same as for save. Backup stops if the repo is public, or if it cannot tell.
- When Git asks you to sign in, do it yourself. Claude is built not to need your token or password. We have not tested this with real GitHub yet.
- **Do you already have a repo?** Say so. `pm` runs `bash ws/bin/ws.sh repo adopt <URL>`. Use the web address that starts with `https://`, or an SSH address (it starts with `git@`). Claude reads the code first. It is told not to read a `CLAUDE.md` inside it.
- **Branches.** A branch is a separate line of work. The main line is called `main`. After you bring in a repo, save uses a branch named `createcodebox/<date>`, and you merge it into `main` yourself when the work is ready.

## Watch out
- Do not paste a token or a password into the chat. Claude does not need them.
- Choose **Private** when you make the repo.
- What you send stays in the repo. The key check runs first, but it knows only some key formats.
- In a repo you brought in, save uses a branch for you, so `main` stays as it was until you merge.
- Backup stops for an SSH address, because it cannot tell if the repo is public.

## The technical name
A repository (repo). Sending is a push. Copying a repo is a clone. A pull request (PR) asks to merge a branch. Merging puts a branch into `main`.
