# Images

The README and the setup pages refer to these names. The pictures of how it works are made and listed first. The screenshots are not made yet and are listed last.

## Pictures made for CreateCodeBox

"Used in" says "planned" until the README pull request puts the picture in.

| File | What it shows | Size | How it was made | Used in |
|---|---|---|---|---|
| `flow-en-light.svg`, `flow-en-dark.svg` | The stages after setup, top to bottom (English). Blue boxes are the stages. Amber marks what you do. | 800 × 968 (viewBox) | Written by `tools/make_flow_diagram.py` from one table of words. Run `python3 tools/make_flow_diagram.py` to write it again and `--check` to test it. | Planned: README.md |
| `flow-ja-light.svg`, `flow-ja-dark.svg` | The same, in Japanese. The words you type stay `looks good` and `approve`. | 800 × 988 (viewBox) | Same script. | Planned: README.ja.md |
| `top-base.png` | A picture without words: boxes going up like steps, on a dark ground. The left side is empty on purpose. | 1280 × 640 | Made with a local image model, no words in the prompt. See below. | Base of `top.png` and `top-ja.png` |
| `top.png` | `top-base.png` with the name "CreateCodeBox" and the tagline "Turn an idea into an app with Claude Code, one step at a time." added on the left (English). Also meant for the GitHub social preview. | 1280 × 640 | A text-overlay tool, in two steps: the name (white, Arial Bold 80 px) and the tagline (white, Arial 40 px, two lines). | Planned: README.md, social preview |
| `top-ja.png` | The same picture with the Japanese tagline under the name. The name stays "CreateCodeBox". | 1280 × 640 | The same tool: the name (Arial Bold 80 px) and the tagline (white, Hiragino Sans W6 40 px, two lines). | Planned: README.ja.md |
| `icon.svg` | The icon: three boxes of the same size on a blue ground, each half behind the one before, going up to the right. The low-left box is white and in front. The one at the back is amber. | 512 × 512 | Drawn by hand as SVG (shape chosen from six local-model sketches; the sketches are not kept here). | Planned: next to the title in README.md and README.ja.md |
| `icon-mono.svg` | The same, in one colour (`#1d2330`) on a transparent ground. The gaps show the three boxes. | 512 × 512 | Drawn by hand as SVG. | Planned: places that need one colour |
| `icon-32.svg`, `icon-16.svg` | Small versions of the icon for favicons. Same shape, drawn on the pixel grid so the edges stay sharp. | 32 × 32, 16 × 16 | Drawn by hand as SVG. | Planned: favicon |

Colours come from `ws/learn/overview.html`: ground `#1d2330` (dark) and `#f7f8fa` (light), blue `#2457d6` and `#8fb0ff`, amber `#ffb55e` for "your turn" only.

### How `top-base.png` was made

- Model: FLUX.2 klein 4B (Apache-2.0), run on a local computer. Nothing was sent to a web service.
- Seed: 5. Steps: 4. Size: 1280 × 640.
- The model was asked for a picture only. It did not draw any words. The name and the tagline on `top.png` and `top-ja.png` are added afterwards by a tool.
- Prompt:

  > Abstract flat-shaded illustration, wide banner. Solid dark slate navy background (#1d2330), plain and desaturated. The left 55% is calm and completely empty. On the right side, exactly three rounded-square boxes of the same corner roundness form a staircase going up: a wide low box at the bottom, a medium box sitting on the right part of it, and a smaller box on top of that, each step higher than the last. Flat solid faces in cobalt blue (#2457d6) and light periwinkle blue (#8fb0ff), no gradients, no shadows. One small golden amber block (#ffb55e, warm orange-yellow, not pink, not peach, not coral) sits on the left end of one step. One box has a tiny blank window shape on its front. Soft matte, clean geometry, generous empty space on the left, and clear margin above, below and at the right edge. no text, no letters, no people, no faces, no logos, no robots, no sparkles

- The ground came out lighter than the prompt asked (`#2c3543` instead of `#1d2330`). It was kept as it is.

## Screenshots to take

These are not made yet. The owner takes them on a real machine. Save each file in `docs/img/` with the file name below.

Rules for every screenshot:

- Take the real screen of the version you test, and write the Claude Code version and the date in the pull request.
- Crop to the window. Do not show the whole desktop.
- Do not show: an email address, a key or password, a person's name, or the user name in a home folder path (for example `/Users/<your name>/` or `C:\Users\<your name>\`). Use a test account and a test user name, or cover the part with a plain grey box before you save.
- Do not put an image line in a page until its file exists. Do not leave a line with only alt text in a page, so that no broken image shows.
- When a file is added, add one image line with alt text to the page in the "Where it goes" column, and change this table.

| Screen to take | File name | Where it goes | Must not show |
|---|---|---|---|
| Claude Code, the first sign-in screen (the first time you type `claude`) | `claude-first-signin.png` | `docs/setup-mac.md` step 3, `docs/setup-windows.md` step 4 | Email address, account name, sign-in code, a browser address bar with a code in it |
| The question "Do you trust the files in this folder?" in the `CreateCodeBox` folder | `trust-folder.png` | `docs/setup-mac.md` step 4, `docs/setup-windows.md` step 5 | The user name in the folder path (use a test user, or cover it) |
| A permission question from Claude Code (for example, asking to run a command) | `permission-prompt.png` | `docs/setup-mac.md` step 5, `docs/setup-windows.md` "Know before you start" | The user name in a path, a key or password in the command |
| The first reply after `claude` starts in the folder, with the line that starts with `[CreateCodeBox` (and `place: ok`) | `first-hook-line.png` | `docs/setup-mac.md` step 4, `docs/setup-windows.md` step 5 | The user name in the folder path |
| The prototype open in the browser (a small example project) | `prototype-in-browser.png` | `README.md` step 5 and 6 (after the file exists) | Tabs with other sites, a bookmarks bar, a profile name, real data |
| Git Bash on Windows: the window after typing `git --version` and `python --version` | `windows-git-bash.png` | `docs/setup-windows.md` step 3 | The user name in the prompt (`user@PC`), the PC name |
| Spotlight with "Terminal" typed in (Mac) | `mac-open-terminal.png` | `docs/setup-mac.md` step 1 | Other results from the user's own files, the user name |
| Start menu with "Git Bash" typed in (Windows) | `windows-open-git-bash.png` | `docs/setup-windows.md` step 3 | Other results from the user's own files, the user name |

The Windows screens need a real Windows PC. The setup pages for Windows say it is not tested yet; the screenshots do not change that.
