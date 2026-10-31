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

Follow Anthropic's official guide: https://code.claude.com/docs/en/overview. The guide says what you need to sign in and what it costs. Then check:

```
claude --version
```

## 5. Get CreateCodeBox and start

The README shows a one-sentence start. You paste one sentence into Claude Code, and Claude copies CreateCodeBox for you. We have not tested that on a real machine yet.

**If the one sentence does not work: do it by hand.** Close Claude Code first (type `/exit`), or open a second Git Bash window. Then, in Git Bash, paste these 3 lines one at a time. Press Enter after each line.

```
git clone https://github.com/atasino/CreateCodeBox.git ~/CreateCodeBox
cd ~/CreateCodeBox
claude
```

Line 1 uses the address of this repository. If you use a copy of it, replace the address in line 1 (from `https://` to `.git`) with the address of that copy. You can copy an address from the green **Code** button on the GitHub page: click the button, then click the copy icon. Line 1 puts the copy in the folder `CreateCodeBox` in your home folder. In Git Bash, `~` is your Windows user folder. Line 2 goes into that folder. Line 3 starts Claude Code.

The first time, Claude Code asks if you trust this folder. If the folder came from the address you pasted, and you trust that address, answer yes.

After these 3 lines, Claude Code is running in your `CreateCodeBox` folder. Keep using this window. Skip step 4 of the [README](../README.md) and go to step 5: tell Claude what you want to make.

## Where to put the folder

**Best:** a folder named `CreateCodeBox` directly in your home folder: `%USERPROFILE%\CreateCodeBox` (in Git Bash: `~/CreateCodeBox`). The one-sentence start in the README uses this place.

**If your Windows user name has a space or a non-English letter** (for example `C:\Users\山田`), do not put CreateCodeBox in your home folder. Use `C:\CreateCodeBox` instead (in Git Bash: `/c/CreateCodeBox`). This path has only English letters and no spaces. The workspace warns about most folders outside your home folder. It does not warn about this one.

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
- If something does not work, go into the folder with `cd ~/CreateCodeBox` and run `bash ws/bin/ws.sh doctor` there.
- If a step does not work, it may not be your mistake. Something may be missing from the step. Please open the form [A step did not work](https://github.com/atasino/CreateCodeBox/issues/new/choose) and tell us what you saw. Ask questions in [Discussions](https://github.com/atasino/CreateCodeBox/discussions).

## Common problems

We have seen only some of these lines ourselves. The others are written from general knowledge and may differ on your computer. Find the line you see on your screen. Do what the third column says. If it does not help, use the form in the last column. Use Git Bash for every command.

| What you see | What is happening | What to do | Still stuck? |
|---|---|---|---|
| `claude: command not found` (in Git Bash: `bash: claude: command not found`) | Claude Code may not be installed, or this Git Bash window was opened before you installed it. | Close Git Bash, open a new window, and type `claude --version`. If it still fails, do step 4 again. | [A step did not work](https://github.com/atasino/CreateCodeBox/issues/new/choose) |
| `git: command not found` | Git for Windows may not be installed, or you may not be in Git Bash. | Open Git Bash from the Start menu. If there is no Git Bash, do step 1 again. | [A step did not work](https://github.com/atasino/CreateCodeBox/issues/new/choose) |
| `CreateCodeBox needs Python 3.8 or newer. Install it from python.org and open a new terminal.` (or `Python was not found`) | Python 3.8 or newer may not be installed. | Do step 2 again and tick "Add python.exe to PATH". Open a new Git Bash window, and type `python --version`. | [A step did not work](https://github.com/atasino/CreateCodeBox/issues/new/choose) |
| `bash: ws/bin/ws.sh: No such file or directory` | You are probably not in the `CreateCodeBox` folder. | Type `cd ~/CreateCodeBox`, then type the command again. | [A step did not work](https://github.com/atasino/CreateCodeBox/issues/new/choose) |
| You answered No to "Do you trust the files in this folder?" (the wording can differ by version) | Without your trust, Claude Code may not run the workspace's checks. We saw it ignore the workspace's permission list. | Type `claude` again in the `CreateCodeBox` folder, and answer yes. Answer yes only for the folder you made. | [A step did not work](https://github.com/atasino/CreateCodeBox/issues/new/choose) |
| Claude says there is no line that starts with `[CreateCodeBox`, or that the hooks are not working | The workspace's checks did not start. Possible causes: you answered No to the trust question, Python is missing, or `claude` was started in another folder. | Type `/exit`, then `cd ~/CreateCodeBox` and `claude`. If it happens again, type `bash ws/bin/ws.sh doctor` and read the lines marked `NG`. | [A step did not work](https://github.com/atasino/CreateCodeBox/issues/new/choose) |
| `place: warn` followed by a reason | The folder is in a place that may cause trouble. This is only a warning. | Move the folder to `%USERPROFILE%\CreateCodeBox` (in File Explorer, drag it into your user folder and rename it), then start `claude` there. Or go on as it is. | [A step did not work](https://github.com/atasino/CreateCodeBox/issues/new/choose) |
| Claude Code asks for permission again and again | Claude Code asks before many actions. This can happen. | Read each question. Answer yes only if you understand it. If you do not, ask Claude what it means. | [A step did not work](https://github.com/atasino/CreateCodeBox/issues/new/choose) |
| The app does not open in the browser | The file may not have opened by itself, or it opened in a text editor. | In File Explorer, open your user folder, then `CreateCodeBox\projects\<name>\src`. Right-click `index.html`, choose "Open with", and choose your browser. | [A step did not work](https://github.com/atasino/CreateCodeBox/issues/new/choose) |

`<name>` is the name of your project's folder inside `projects/`.
