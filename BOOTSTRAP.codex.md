# Set up CreateCodeBox (instructions for Codex)

This file is for Codex. If you are a person, read README.md instead.

The user asked you to set up CreateCodeBox by following this file. Their message has a GitHub address. Do the steps below, in order. Do nothing else.

## Rules for the whole task

- Work from the whole text of this file, not a summary. If you only have a summary (for example from a tool that reads web pages), first read the whole file with `curl` from raw.githubusercontent.com. Reading it this way is fine. Do not use `curl` for anything else.
- Run only these four commands, and no other command (besides the `curl` read above; no `git -C`, no `ls -d`, no `ls -ld`, no `rev-parse`):
  1. `git --version`
  2. `ls <folder>` (or your file tools)
  3. `git clone <address> <folder>`
  4. `chmod 700 <folder>` (Mac and Linux only)
- You may have made a copy to read this file, because you could not read it from the web (for example, the repository is private). If that copy is in the folder from step 2, do not copy again: skip steps 3 and 4. If it is in another place, do not use it. Do steps 3 and 4 as written. At the end, tell the user where the first copy is, so they can delete it.
- Do not ask for keys, passwords, tokens, or personal information.
- Do not download and run a script (no `curl | sh`, no `wget | sh`).
- Talk to the user in the language of their message. Use plain, short sentences.
- If a step fails, show the user the error in one or two lines and stop. Do not try another way.

## Steps

1. **Check the address.** Say the address you checked, and say if it matches. It must be a web address (`https://`) that looks like `https://github.com/<owner>/CreateCodeBox`. It may end with `.git`. `<owner>` has only letters, numbers, and hyphens. If the address does not look like this, stop. Tell the user: "This address does not look right. Please copy it again from the GitHub page of CreateCodeBox." Do not continue.

2. **Choose the folder.** Use the user's home folder and nothing else.
   - Mac and Linux: `~/CreateCodeBox`
   - Windows: `%USERPROFILE%\CreateCodeBox` (this is `~/CreateCodeBox` in Git Bash)
   - **If the home folder path has a space or a non-English character** (for example `C:\Users\<a Japanese name>`), use this fixed folder instead:
     - Windows: `C:\CreateCodeBox` (`/c/CreateCodeBox` in Git Bash).
     - Mac: `/Users/Shared/CreateCodeBox`. Then run `chmod 700` on it (step 5), so other accounts cannot read it.
     - Linux: ask the user for a folder they can write to that is not under `~` and has only English letters and no spaces. Do not use `/opt`.
     - Use the same folder in the next steps, and in the `cd` line you give the user.
   - Do not use Downloads, Desktop, Documents, a folder that iCloud, OneDrive, or Dropbox syncs, a folder inside another Git repo, or a system folder. Do not use any other path with spaces or non-English characters.

3. **Do not overwrite.** To check, use your file tools, or run `ls <folder>`. If the folder already exists, do not change or delete it. Ask the user: use another name (`CreateCodeBox-2`), or stop. Use the other name only if the user says yes.

4. **Copy it.** Run `git --version` first. If git is missing, tell the user to install git (see the setup help in the README) and stop. Then run: `git clone <address> <folder>`. Use the address exactly as you checked it. Add no other options.

5. **Limit the folder to your own account.** On Mac and Linux, run `chmod 700 <folder>`. This only stops other accounts on this computer. On Windows, skip this step.

6. **Tell the user what to do next.** Say these things in plain words:
   - Close Codex first, or open a second Terminal window. Then type these two lines, one at a time, and press Enter after each: `cd <folder>` and then `codex`. Use the real folder path in the first line. In Git Bash, write `~/CreateCodeBox`, or `/c/CreateCodeBox` for the fixed folder from step 2.

     **When Codex asks you to trust the folder, answer yes only if it is the `CreateCodeBox` folder you just made. Then type `/hooks` in Codex, check the CreateCodeBox hooks, and trust them. Without this, the checks do not run.**

   - CreateCodeBox needs Python 3 (3.8 or newer). If it is missing, the workspace says so the first time. The setup help in the README shows how to install it.
   - Then tell Codex what you want to make.

Stop after step 6. Do not start the workspace yourself, and do not run any file from the new folder.
