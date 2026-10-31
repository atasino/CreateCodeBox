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

Follow Anthropic's official guide: https://code.claude.com/docs/en/overview. The guide says what you need to sign in and what it costs. Then check that it works:

```
claude --version
```

## 4. Get CreateCodeBox and start

The README shows a one-sentence start. You paste one sentence into Claude Code, and Claude copies CreateCodeBox for you. We have not tested that on a real machine yet.

**If the one sentence does not work: do it by hand.** Close Claude Code first (type `/exit`), or open a second Terminal window. Then paste these 3 lines into Terminal, one at a time. Press Enter after each line.

```
git clone https://github.com/atasino/CreateCodeBox.git ~/CreateCodeBox
cd ~/CreateCodeBox
claude
```

Line 1 uses the address of this repository. If you use a copy of it, replace the address in line 1 (from `https://` to `.git`) with the address of that copy. You can copy an address from the green **Code** button on the GitHub page: click the button, then click the copy icon. Line 1 puts the copy in the folder `CreateCodeBox` in your home folder. Line 2 goes into that folder. Line 3 starts Claude Code.

The first time, Claude Code asks if you trust this folder. Read the question. If the folder came from the address you pasted, and you trust that address, answer yes.

After these 3 lines, Claude Code is running in your `CreateCodeBox` folder. Keep using this window. Skip step 4 of the [README](../README.md) and go to step 5: tell Claude what you want to make.

## Where to put the folder

**Best:** a folder named `CreateCodeBox` directly in your home folder: `~/CreateCodeBox`. The one-sentence start in the README uses this place.

**Avoid these places:**

- **Downloads, Desktop, and Documents.** Sync apps often copy these folders to the cloud. Your work and your key files could leave your computer. Files you download also land here, and a `CLAUDE.md` file from outside could get mixed in.
- **A folder that iCloud Drive, OneDrive, or Dropbox syncs.** Your work could be copied to the cloud, and sync can damage the records in `.ws/`.
- **Inside another Git repo.** Git can mix the two projects, and the `CLAUDE.md` of the outer repo can be loaded.
- **A path with spaces or non-English characters.** Some tools and scripts can fail on such paths.
- **A system folder**, for example `/tmp` or `/usr`. It may be deleted, or it may need administrator rights.

The workspace checks this. Run `bash ws/bin/ws.sh doctor`. It prints `place: ok` or `place: warn` with the reason. It only warns. It does not stop you.

## 5. If something does not work

- Go into the folder with `cd ~/CreateCodeBox`, and run `bash ws/bin/ws.sh doctor` there. It prints one line for each check.
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
| `bash: ws/bin/ws.sh: No such file or directory` | You are probably not in the `CreateCodeBox` folder. | Type `cd ~/CreateCodeBox`, then type the command again. | [A step did not work](https://github.com/atasino/CreateCodeBox/issues/new/choose) |
| You answered No to "Do you trust the files in this folder?" (the wording can differ by version) | Without your trust, Claude Code may not run the workspace's checks. We saw it ignore the workspace's permission list. | Type `claude` again in the `CreateCodeBox` folder, and answer yes. Answer yes only for the folder you made. | [A step did not work](https://github.com/atasino/CreateCodeBox/issues/new/choose) |
| Claude says there is no line that starts with `[CreateCodeBox`, or that the hooks are not working | The workspace's checks did not start. Possible causes: you answered No to the trust question, Python is missing, or `claude` was started in another folder. | Type `/exit`, then `cd ~/CreateCodeBox` and `claude`. If it happens again, type `bash ws/bin/ws.sh doctor` and read the lines marked `NG`. | [A step did not work](https://github.com/atasino/CreateCodeBox/issues/new/choose) |
| `place: warn` followed by a reason | The folder is in a place that may cause trouble. This is only a warning. | Move the folder to `~/CreateCodeBox` (in Finder, drag it into your home folder and rename it), then start `claude` there. Or go on as it is. | [A step did not work](https://github.com/atasino/CreateCodeBox/issues/new/choose) |
| Claude Code asks for permission again and again | Claude Code asks before many actions. This can happen. | Read each question. Answer yes only if you understand it. If you do not, ask Claude what it means. | [A step did not work](https://github.com/atasino/CreateCodeBox/issues/new/choose) |
| The app does not open in the browser | The file may not have opened by itself. | In Finder, press Shift + Command + H to go to your home folder, open `CreateCodeBox/projects/<name>/src`, and double-click `index.html`. | [A step did not work](https://github.com/atasino/CreateCodeBox/issues/new/choose) |

`<name>` is the name of your project's folder inside `projects/`.
