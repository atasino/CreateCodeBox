# Set up on Windows

Status: **not tested on a real Windows PC yet.** Treat the steps below as a guide. Screenshots for this page are not made yet (see `docs/img/README.md`).

CreateCodeBox needs Git Bash. Claude Code on Windows also needs it. You need Claude Code, Git for Windows (which includes Git Bash), and Python 3 (3.8 or newer; we tested 3.9 on a Mac).

## 1. Install Git for Windows

Get it from https://git-scm.com/download/win and install it. The default choices are fine. It adds "Git Bash" to your Start menu.

## 2. Install Python

Get Python 3 from https://www.python.org/downloads/. In the installer, tick "Add python.exe to PATH". Version 3.8 or newer is needed.

## 3. Open Git Bash

Open the Start menu, type "Git Bash", and press Enter. Use Git Bash for every command in this workspace. Do not use Command Prompt. We have not checked PowerShell, so do not use it either.

To paste text into Git Bash, press Shift + Insert, or right-click in the window.

Check your tools, one line at a time:

```
git --version
python --version
```

On some PCs the Python command is `python3` or `py`. Any of the three is fine, as long as one shows version 3.8 or higher.

## 4. Install Claude Code

Follow Anthropic's setup guide: https://code.claude.com/docs/en/setup. The guide says how to sign in and which accounts include Claude Code. Then check:

```
claude --version
```

## 5. Make a folder for your app and start

CreateCodeBox uses one folder for each app. You make an empty folder, open Claude Code in it, and paste one sentence (README, step 3). Claude sets CreateCodeBox up in that folder. We ran this only on a Mac, in test runs with permission prompts turned off. We have not run it on Windows.

First make the folder and open Claude Code in it. Type these three lines in Git Bash, one at a time. Press Enter after each line.

```
mkdir ~/coffee-log
cd ~/coffee-log
claude
```

Line 1 makes an empty folder named `coffee-log` in your home folder. In Git Bash, `~` is your Windows user folder. Use a name for your app instead: English letters, numbers, and `-`, with no spaces. Line 2 goes into that folder. Line 3 starts Claude Code. If your Windows user name has a space or a non-English letter, see "Where to put the folder" below. To use Visual Studio Code or the Claude app, see step 2 of the [README](../README.md).

Claude Code may ask if you trust this folder. It is the empty folder you made a moment ago, so answer yes.

Then paste the one sentence from step 3 of the [README](../README.md) into Claude Code. Claude is meant to set up CreateCodeBox in this folder. Then follow step 4 of the README: Claude shows you how to open Claude Code again in the folder. If Claude Code was already open in another folder, paste the sentence there anyway. Claude is told to help you make a new folder.

**If the one sentence does not work: do it by hand.** Close Claude Code first (type `/exit`), or open a second Git Bash window. Go into your new empty folder with `cd ~/coffee-log` (use your folder's name). Then paste these 2 lines into Git Bash, one at a time. Press Enter after each line.

```
git clone https://github.com/atasino/CreateCodeBox.git .
claude
```

Line 1 uses the address of this repository. If you use a copy of it, replace the address in line 1 (from `https://` to `.git`) with the address of that copy. You can copy an address from the green **Code** button on the GitHub page: click the button, then click the copy icon. Line 1 copies CreateCodeBox into the folder you are in. The `.` at the end means "this folder", so the folder must be empty. Line 2 starts Claude Code.

If `git clone` says the folder is not empty, make another new empty folder and type the same lines there.

When Claude Code asks if you trust this folder, read the question. If the folder came from the address you used, and you trust that address, answer yes.

After these 2 lines, Claude Code is running in your app's folder. Keep using this window. Skip step 4 of the [README](../README.md) and go to step 5: tell Claude what you want to make.

## Where to put the folder

**Best:** one new empty folder for each app, directly in your home folder. Name it with English letters, numbers, and `-`, with no spaces. For example: `%USERPROFILE%\coffee-log` (in Git Bash: `~/coffee-log`). "Your app's folder" on this page means this folder.

**If your Windows user name has a space or a non-English letter** (for example `C:\Users\山田`), do not put the folder in your home folder. Put it right under `C:\` instead, for example `C:\coffee-log` (in Git Bash: `/c/coffee-log`). This path has only English letters and no spaces. The workspace warns about most folders outside your home folder. It does not warn about this one.

**Avoid these places:**

- **Downloads, Desktop, and Documents.** Sync apps often copy these folders to the cloud. Your work and your key files could leave your computer. Files you download also land here, and a `CLAUDE.md` file from outside could get mixed in.
- **A folder that iCloud Drive, OneDrive, or Dropbox syncs.** Your work could be copied to the cloud, and sync can damage the records in `.ws/`.
- **Inside another Git repo.** Git can mix the two projects, and the `CLAUDE.md` of the outer repo can be loaded.
- **A path with spaces or non-English characters.** Some tools can fail on such paths. Git Bash and Python scripts are the usual ones.
- **A system folder**, for example `C:\Windows`. It may be deleted, or it may need administrator rights.

The workspace checks this. Run `bash ws/bin/ws.sh doctor`. It prints `place: ok` or `place: warn` with the reason. It only warns. It does not stop you.

## Know before you start

- When Claude asks you to "open a separate Terminal", open a second Git Bash window.
- Hardened mode is not available on Windows yet. It is an optional setting that stops commands Claude runs from reading your key files.
- If the workspace says that it needs Python 3.8, check step 2 and the `python` line in step 3.
- If something does not work, go into your app's folder (for example `cd ~/coffee-log`) and run `bash ws/bin/ws.sh doctor` there.
- If a step does not work, it may not be your mistake. Something may be missing from the step. Please open the form [A step did not work](https://github.com/atasino/CreateCodeBox/issues/new/choose) and tell us what you saw. Ask questions in [Discussions](https://github.com/atasino/CreateCodeBox/discussions).

## Common problems

We have seen only some of these lines ourselves. The others are written from general knowledge and may differ on your computer. Find the line you see on your screen. Do what the third column says. If it does not help, use the form in the last column. Use Git Bash for every command.

| What you see | What is happening | What to do | Still stuck? |
|---|---|---|---|
| `claude: command not found` (in Git Bash: `bash: claude: command not found`) | Claude Code may not be installed, or this Git Bash window was opened before you installed it. | Close Git Bash, open a new window, and type `claude --version`. If it still fails, do step 4 again. | [A step did not work](https://github.com/atasino/CreateCodeBox/issues/new/choose) |
| `git: command not found` | Git for Windows may not be installed, or you may not be in Git Bash. | Open Git Bash from the Start menu. If there is no Git Bash, do step 1 again. | [A step did not work](https://github.com/atasino/CreateCodeBox/issues/new/choose) |
| `CreateCodeBox needs Python 3.8 or newer. Install it from python.org and open a new terminal.` (or `Python was not found`) | Python 3.8 or newer may not be installed. | Do step 2 again and tick "Add python.exe to PATH". Open a new Git Bash window, and type `python --version`. | [A step did not work](https://github.com/atasino/CreateCodeBox/issues/new/choose) |
| `bash: ws/bin/ws.sh: No such file or directory` | You are probably not in your app's folder. | Type `cd ~/coffee-log` (use your folder's name), then type the command again. | [A step did not work](https://github.com/atasino/CreateCodeBox/issues/new/choose) |
| You answered No to "Do you trust the files in this folder?" (the wording can differ by version) | Without your trust, Claude Code may not run the workspace's checks. We saw it ignore the workspace's permission list. | Type `claude` again in your app's folder, and answer yes. Answer yes only for the folder you made. | [A step did not work](https://github.com/atasino/CreateCodeBox/issues/new/choose) |
| Claude says there is no line that starts with `[CreateCodeBox`, or that the hooks are not working | The workspace's checks did not start. Possible causes: you answered No to the trust question, Python is missing, or `claude` was started in another folder. | Type `/exit`, then `cd ~/coffee-log` (use your folder's name) and `claude`. If it happens again, type `bash ws/bin/ws.sh doctor` and read the lines marked `NG`. | [A step did not work](https://github.com/atasino/CreateCodeBox/issues/new/choose) |
| `place: warn` followed by a reason | The folder is in a place that may cause trouble. This is only a warning. | Make a new empty folder for your app in your user folder (see step 5), and set CreateCodeBox up there. Your earlier work stays in the old folder. Or go on as it is. | [A step did not work](https://github.com/atasino/CreateCodeBox/issues/new/choose) |
| Claude Code asks for permission again and again | Claude Code asks before many actions. This can happen. | Read each question. Answer yes only if you understand it. If you do not, ask Claude what it means. | [A step did not work](https://github.com/atasino/CreateCodeBox/issues/new/choose) |
| The app does not open in the browser | The file may not have opened by itself, or it opened in a text editor. | In File Explorer, open your app's folder, then `projects\<name>\src`. Right-click `index.html`, choose "Open with", and choose your browser. | [A step did not work](https://github.com/atasino/CreateCodeBox/issues/new/choose) |

`<name>` is the name of your project's folder inside `projects/`.
