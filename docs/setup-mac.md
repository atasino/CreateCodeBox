# Set up on Mac

Status: an earlier version (0.2.0) was tested on macOS. Screenshots for this page are not made yet (see `docs/img/README.md`).

You need three things: Claude Code, `git`, and Python 3 (3.8 or newer; we tested 3.9).

## 1. Open Terminal

Press the Command key and the Space bar together. Type "Terminal". Press Enter. A window with a line of text opens. You type commands there and press Enter after each one.

## 2. Check git and Python

Type these two lines, one at a time:

```
git --version
python3 --version
```

- If each line shows a version number, go to step 3. For Python, the number must be 3.8 or higher.
- If your Mac shows a window that asks to install "command line developer tools", click Install. Wait until it finishes. This gives you `git` and Python 3. Then run the two lines again.

## 3. Install Claude Code

Follow Anthropic's setup guide: https://code.claude.com/docs/en/setup. The guide says how to sign in and which accounts include Claude Code. Then check that it works:

```
claude --version
```

## 4. Make a folder for your app and start

CreateCodeBox uses one folder for each app. You make an empty folder, open Claude Code in it, and paste one sentence (README, step 3). Claude sets CreateCodeBox up in that folder. We ran this on a Mac only in test runs with permission prompts turned off. We have not run it in a normal session.

First make the folder and open Claude Code in it. Type these three lines in Terminal, one at a time. Press Enter after each line.

```
mkdir ~/coffee-log
cd ~/coffee-log
claude
```

Line 1 makes an empty folder named `coffee-log` in your home folder. Use a name for your app instead: English letters, numbers, and `-`, with no spaces. Line 2 goes into that folder. Line 3 starts Claude Code. If your user name has a space or a non-English letter, see "Where to put the folder" below. To use Visual Studio Code or the Claude app, see step 2 of the [README](../README.md).

Claude Code may ask if you trust this folder. It is the empty folder you made a moment ago, so answer yes.

Then paste the one sentence from step 3 of the [README](../README.md) into Claude Code. Claude is meant to set up CreateCodeBox in this folder. Then follow step 4 of the README: Claude shows you how to open Claude Code again in the folder. If Claude Code was already open in another folder, paste the sentence there anyway. Claude is told to help you make a new folder.

**If the one sentence does not work: do it by hand.** Close Claude Code first (type `/exit`), or open a second Terminal window. Go into your new empty folder with `cd ~/coffee-log` (use your folder's name). Then paste these 2 lines into Terminal, one at a time. Press Enter after each line.

```
git clone https://github.com/atasino/CreateCodeBox.git .
claude
```

Line 1 uses the address of this repository. If you use a copy of it, replace the address in line 1 (from `https://` to `.git`) with the address of that copy. You can copy an address from the green **Code** button on the GitHub page: click the button, then click the copy icon. Line 1 copies CreateCodeBox into the folder you are in. The `.` at the end means "this folder", so the folder must be empty. Line 2 starts Claude Code.

If `git clone` says the folder is not empty, make another new empty folder and type the same lines there.

When Claude Code asks if you trust this folder, read the question. If the folder came from the address you used, and you trust that address, answer yes.

After these 2 lines, Claude Code is running in your app's folder. Keep using this window. Skip step 4 of the [README](../README.md) and go to step 5: tell Claude what you want to make.

## Where to put the folder

**Best:** one new empty folder for each app, directly in your home folder. Name it with English letters, numbers, and `-`, with no spaces. For example: `~/coffee-log`. "Your app's folder" on this page means this folder.

**If your Mac user name has a space or a non-English letter:** do not put the folder in your home folder. Put it right under `/Users/Shared/` instead, for example `/Users/Shared/coffee-log`. This path has only English letters and no spaces. The workspace warns about most folders outside your home folder. It does not warn about this one.

**Avoid these places:**

- **Downloads, Desktop, and Documents.** Sync apps often copy these folders to the cloud. Your work and your key files could leave your computer. Files you download also land here, and a `CLAUDE.md` file from outside could get mixed in.
- **A folder that iCloud Drive, OneDrive, or Dropbox syncs.** Your work could be copied to the cloud, and sync can damage the records in `.ws/`.
- **Inside another Git repo.** Git can mix the two projects, and the `CLAUDE.md` of the outer repo can be loaded.
- **A path with spaces or non-English characters.** Some tools and scripts can fail on such paths.
- **A system folder**, for example `/tmp` or `/usr`. It may be deleted, or it may need administrator rights.

The workspace checks this. Run `bash ws/bin/ws.sh doctor`. It prints `place: ok` or `place: warn` with the reason. It only warns. It does not stop you.

## 5. If something does not work

- Go into your app's folder (for example `cd ~/coffee-log`), and run `bash ws/bin/ws.sh doctor` there. It prints one line for each check.
- If Claude Code asks permission for each step, that is normal. You can read each question and answer. Do not answer yes to a question you do not understand. Ask Claude what it means.
- Do not paste keys or passwords into the chat.
- If a step does not work, it may not be your mistake. Something may be missing from the step. Please open the form [A step did not work](https://github.com/atasino/CreateCodeBox/issues/new/choose) and tell us what you saw. Ask questions in [Discussions](https://github.com/atasino/CreateCodeBox/discussions).

## Common problems

We have seen only some of these lines ourselves. The others are written from general knowledge and may differ on your computer. Find the line you see on your screen. Do what the third column says. If it does not help, use the form in the last column.

| What you see | What is happening | What to do | Still stuck? |
|---|---|---|---|
| `claude: command not found` (in Terminal: `zsh: command not found: claude`) | Claude Code may not be installed, or this Terminal window was opened before you installed it. | Close Terminal, open a new window, and type `claude --version`. If it still fails, do step 3 again. | [A step did not work](https://github.com/atasino/CreateCodeBox/issues/new/choose) |
| `git: command not found`, or `xcode-select: note: No developer tools were found`, or a window about "command line developer tools" | `git` may not be installed yet. | Type `xcode-select --install`, click Install, wait until it finishes, then type `git --version`. | [A step did not work](https://github.com/atasino/CreateCodeBox/issues/new/choose) |
| `CreateCodeBox needs Python 3.8 or newer. Install it from python.org and open a new terminal.` | Python 3.8 or newer may not be installed. | Install Python 3 from https://www.python.org/downloads/, open a new Terminal window, and type `python3 --version`. | [A step did not work](https://github.com/atasino/CreateCodeBox/issues/new/choose) |
| `bash: ws/bin/ws.sh: No such file or directory` | You are probably not in your app's folder. | Type `cd ~/coffee-log` (use your folder's name), then type the command again. | [A step did not work](https://github.com/atasino/CreateCodeBox/issues/new/choose) |
| You answered No to "Do you trust the files in this folder?" (the wording can differ by version) | Without your trust, Claude Code may not run the workspace's checks. We saw it ignore the workspace's permission list. | Type `claude` again in your app's folder, and answer yes. Answer yes only for the folder you made. | [A step did not work](https://github.com/atasino/CreateCodeBox/issues/new/choose) |
| Claude says there is no line that starts with `[CreateCodeBox`, or that the hooks are not working | The workspace's checks did not start. Possible causes: you answered No to the trust question, Python is missing, or `claude` was started in another folder. | Type `/exit`, then `cd ~/coffee-log` (use your folder's name) and `claude`. If it happens again, type `bash ws/bin/ws.sh doctor` and read the lines marked `NG`. | [A step did not work](https://github.com/atasino/CreateCodeBox/issues/new/choose) |
| `place: warn` followed by a reason | The folder is in a place that may cause trouble. This is only a warning. | Make a new empty folder for your app in your home folder (see step 4), and set CreateCodeBox up there. Your earlier work stays in the old folder. Or go on as it is. | [A step did not work](https://github.com/atasino/CreateCodeBox/issues/new/choose) |
| Claude Code asks for permission again and again | Claude Code asks before many actions. This can happen. | Read each question. Answer yes only if you understand it. If you do not, ask Claude what it means. | [A step did not work](https://github.com/atasino/CreateCodeBox/issues/new/choose) |
| The app does not open in the browser | The file may not have opened by itself. | In Finder, press Shift + Command + H to go to your home folder, open your app's folder, then `projects/<name>/src`, and double-click `index.html`. | [A step did not work](https://github.com/atasino/CreateCodeBox/issues/new/choose) |

`<name>` is the name of your project's folder inside `projects/`.
