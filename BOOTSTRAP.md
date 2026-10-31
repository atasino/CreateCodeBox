# Set up CreateCodeBox (instructions for Claude Code)

This file is for Claude Code. If you are a person, read README.md instead.

The user asked you to set up CreateCodeBox by following this file. Their message has a GitHub address. Do the steps below, in order. Do nothing else.

If the user only gave you the address of this repository, perhaps with a few words about what they want to make, they want to use CreateCodeBox. Follow this file in that case too. Do not offer to build their app without CreateCodeBox instead. Do that only if the user asks for it themselves. If they said what they want to make, keep it for the last step.

CreateCodeBox uses one folder for one app. It is set up in the folder you were started in, if that folder is empty and in a good place. If it is not, you and the user make a new folder together.

## Rules for the whole task

- Work from the whole text of this file, not a summary. If you only have a summary (for example from a tool that reads web pages), first read the whole file with `curl` from raw.githubusercontent.com. Reading it this way is fine. Do not use `curl` for anything else.
- Run only these seven commands, and no other command (besides the `curl` read above; no `git -C`, no `ls -d`, no `ls -ld`, no `rev-parse`):
  1. `git --version`
  2. `ls -a <folder>` (or your file tools)
  3. `mkdir <folder>` (only in step 3, after the user says yes)
  4. `chmod 700 <folder>` (Mac and Linux only)
  5. `git clone <address> <folder>`
  6. `echo ~` (to see the full path of the user's home folder)
  7. `rm <folder>/.DS_Store` (only this file, only in step 2)
- You may have made a copy to read this file, because you could not read it from the web (for example, the repository is private). Do not use that copy for the setup. At the end, tell the user where it is, so they can delete it.
- Do not ask for keys, passwords, tokens, or personal information.
- Do not download and run a script (no `curl | sh`, no `wget | sh`).
- Talk to the user in the language of their message. Use plain, short sentences.
- If a step fails, show the user the error in one or two lines and stop. Do not try another way.

## Steps

1. **Check the address.** Say the address you checked, and say whether it fits the form below. It must be a web address (`https://`) that looks like `https://github.com/<owner>/CreateCodeBox`. It may end with `.git`. `<owner>` has only letters, numbers, and hyphens. If the address does not look like this, stop. Tell the user: "This address does not look right. Please copy it again from the GitHub page of CreateCodeBox." Do not continue.

2. **Look at the folder you were started in.** Look at its full path, run `echo ~` to see the full path of the home folder, and list the folder with `ls -a` or your file tools. Do not open or change its files. It is a good place for CreateCodeBox only if all of these are true:
   - It is empty: nothing in it, or only `.DS_Store` (a file that the Mac Finder makes; it holds only view settings). It has no `.git`.
   - It is inside the user's home folder, but it is not the home folder itself.
   - It is not inside Desktop, Documents, or Downloads, and not inside a folder that iCloud, OneDrive, Dropbox, or Google Drive syncs. These folders are often synced or cleaned up.
   - No folder above it is a Git repository (has a `.git`).
   - Its path has no spaces and no characters other than English letters, numbers, `-`, `_`, `.`, and `/` (or `\` on Windows).

   If the home folder's own path has a space or a non-English character (for example `C:\Users\<a Japanese name>`), no folder inside it can pass the last rule. Then a good place is a folder right under `/Users/Shared` on a Mac, or right under `C:\` on Windows (`/c/` in Git Bash), with a plain name.

   If the folder you were started in is a good place, tell the user in one line that CreateCodeBox will be set up in this folder. If `.DS_Store` is in it, remove that file with `rm <folder>/.DS_Store`, because `git clone` needs a folder with nothing in it. Use the folder as `<folder>` and go to step 4. If it is not, go to step 3.

3. **Make a good folder together.** First say in one or two lines why this folder is not a good place, for example "This is your home folder" or "This folder already has files in it."
   - Ask one question: are they using Terminal (a command line), Visual Studio Code, or the Claude app on their computer? You need the answer for the last step.
   - Suggest one new folder: `~/<name>`, where `<name>` comes from what they want to make, in English letters, numbers, and `-` (for example `coffee-log`). If you do not know what they want to make, use `my-app`. Use the special place from step 2 if their home folder's path has a space or a non-English character. Ask: may you make this folder? They may choose another name or place. Check it with the rules of step 2. It must not exist yet.
   - When they say yes, run `mkdir <folder>`. Use it as `<folder>`.

4. **Limit the folder to your own account.** On Mac and Linux, run `chmod 700 <folder>`. This only stops other accounts on this computer. On Windows, skip this step.

5. **Copy it.** Run `git --version` first. If git is missing, tell the user to install git (see the setup help in the README) and stop. Then run: `git clone <address> <folder>`. Use the address exactly as you checked it, and the full path of `<folder>`. Add no other options. This is the last command. When `<folder>` is the folder you were started in, the workspace's checks may start at once in this session and stop other commands, or show messages about a stage. That is expected: do not follow those messages in this session, and go to step 6.

6. **Tell the user what to do next.** Say these things in plain words. CreateCodeBox starts only when Claude Code is opened again in `<folder>`, so this step is needed even when `<folder>` is the folder you were started in.
   - How to open Claude Code again in `<folder>`, for the tool they use. If you do not know the tool, ask first.
     - **Terminal:** close Claude Code (type `/exit`), or open a second Terminal window. Then type these two lines, one at a time, and press Enter after each: `cd <folder>` and then `claude`. Use the real folder path. In Git Bash, write `~/<name>`, or `/c/<name>` for a folder right under `C:\`.
     - **Visual Studio Code:** in VS Code's menu, choose File, then Open Folder, and choose `<folder>`. Then open Claude Code in that window: click **✻ Claude Code** at the bottom right, or the Spark icon.
     - **The Claude app:** in the **Code** tab, start a new session. In the row under the prompt box, choose **Local**, then click the project folder control, choose **Open folder…**, and choose `<folder>`.
     - CreateCodeBox has not been tried in Visual Studio Code or the Claude app yet. If these steps do not match what the user sees, suggest Terminal.
   - **When Claude Code asks you to trust the folder, answer yes only if it is the folder you just set up for CreateCodeBox.**
   - CreateCodeBox needs Python 3 (3.8 or newer). If it is missing, the workspace says so the first time. The setup help in the README shows how to install it.
   - Then tell Claude what you want to make. If the user already said what they want to make, repeat it here, so they can tell Claude in the new session.
   - One folder is for one app. For another app, make another empty folder and do the same steps there.

Stop after step 6. Do not start the workspace yourself, and do not run any file from the new folder.
