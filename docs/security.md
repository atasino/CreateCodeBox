# Safety details

Read this page if you plan to use real keys, or if you want to know how far the guards go. The guards reduce mistakes and shortcuts. They do not make anything safe by themselves.

## What the guards can do, and what they cannot

| Area | What the guards can do | What they cannot do |
|---|---|---|
| Order of steps | Block Claude's file tools and common commands from writing to `src/` before you approve. | Stop every way around them. Code that Claude runs may avoid some of the checks. |
| Signed records | Notice a record in `.ws/` that was edited by hand. The stage then does not move forward. | Be a strong wall. The signature only detects hand edits. In normal mode, a script that Claude runs may read the signing key. |
| Tools | Check Claude's own tools (file edits, Bash, Read, Grep, Glob) and the tools of Gakaso (our own product). In Codex, check its edit tool and its shell (the tool that runs commands). Before the build stage, stop an MCP tool whose name says it writes or changes something. (MCP is a way to add tools from an online service.) | Know what an MCP tool really does. The check uses only the tool's name. After the build stage starts, the guards stop such a tool only in the first message of a session. Beyond that, they do not limit an MCP server that you add. You decide what it can do. |
| Evidence | Refuse to mark a step done without a note of what was run and what happened. | Tell if the note is true. The note is what Claude reports. The workspace does not check it. |
| Keys | Stop keys in known formats in your messages, in files Claude writes, at save, at backup, and before publish. | See a password with no known format, a short or home-made key, or a key that was split or changed. |

The sections below give the details.

## Where keys live

- A "key" is a long secret text, such as an API key, a token, or a password.
- Keys for the workspace (for example a key for Gakaso, our own product) are in `~/.createcodebox/.env`. This is outside the workspace on purpose.
- Keys for the app you build are in `projects/<name>/src/.env`. The workspace blocks Claude's file tools and common commands from opening it. Code that Claude runs may still read it. Save does not include it.
- To see which keys are set (names only, never values): `bash ws/bin/ws.sh secret check --all`.
- If your project needs no key, you can skip this page. If it does, start with a test key that has low limits.

## Give Claude a key: one way only

When a key is needed, Claude runs `bash ws/bin/ws.sh secret guide <NAME>` and gives you one line. You do three things:

1. Open a separate Terminal window. (Not the one where Claude Code runs.)
2. Paste the line and press Enter.
3. Paste the key when asked and press Enter. Nothing shows on the screen while you type. That is normal.

Then tell Claude you are done. Claude checks the name with `secret check`. It does not see the value. If Claude tries `secret set` itself, it is refused, because it has no terminal for typing.

Never paste a key into the chat. If you did, make the key invalid at the service that gave it to you, and create a new one. A copy of your chat is saved on your computer as plain text. Treat a key you pasted as leaked.

## What the key scan stops, and what it does not

The scan looks at what you type, at files Claude writes, at every save, at backup, and before publish. It stops text in these known formats:

- OpenAI-style `sk-…`, GitHub `ghp_…` and `github_pat_…`, AWS `AKIA…`, Slack `xox…`, Google `AIza…` and `ya29.…`, GitLab `glpat-…`, npm `npm_…`, SendGrid `SG.…`, Hugging Face `hf_…`
- Stripe `sk_live_`, `sk_test_`, `rk_live_`, `rk_test_`, and `whsec_`
- Supabase `sb_secret_…`, and a JWT whose role is `service_role`
- Private key blocks, and web addresses with a password inside (`scheme://user:password@host`)
- Lines such as `api_key = "a-long-literal-value"`. In config files (`.yml`, `.yaml`, `.ini`, `.properties`, `.tfvars`, `.toml`, `docker-compose*`, `.env*`) a value without quotes is also checked.

It lets these pass, on purpose:

- Code that reads a key from the environment, such as `process.env.NAME`, `os.environ`, `getenv`, or `import.meta.env`.
- Public keys: Supabase `sb_publishable_…`, and a JWT whose role is `anon`.
- `.env.example`.

It does not see these:

- a password with no known format
- a short or home-made key
- a key split into parts
- a key that was changed in some way

If the scan stops something that is not a key, run `bash ws/bin/ws.sh secret allow <fingerprint>`. The fingerprint has 12 characters and is in the message. This needs your own words in a message. A key found in the Git history is shown as `commit:path:line` with its fingerprint. In `.env.example`-type files, a value made of the same character repeated (for example `sk_test_xxxx…`) is allowed as a placeholder.

## Signed records

Approvals, test results, the schedule, and the allow list are saved in `.ws/` with a signature. The signing key is `~/.createcodebox/.ws_key`. Records are tied to the project, the file path, and the content. A hand edit breaks the signature, and the stage does not move forward.

- If the key file cannot be read or made, the workspace works with a warning, and your progress is kept. The records are unsigned.
- If you lose the key (new computer, another home folder), signed records go back to "todo". Type `resign` in a message. Claude runs `bash ws/bin/ws.sh resign` only then, to sign the records again.

Be clear about what this does. The signature makes shortcuts harder. In normal mode, Claude can run scripts, and a script may read the signing key. So the signature is not a wall. Hardened mode adds an operating-system limit. See its limits below.

## Hardened mode

Turn it on yourself, in a Terminal:

```
bash ws/bin/ws.sh harden on
```

Optional: `bash ws/bin/ws.sh harden on --with-denywrite`. See the list below.

Then restart Claude Code. It is built for Mac and Linux, and we tested it only on Mac. It is not available on Windows yet.

- Commands that Claude runs are set to be blocked from reading `~/.createcodebox`, `.ssh`, GitHub login files, and these `.env` files: `.env`, `.env.local`, `.env.development`, `.env.production`, `.env.test`, `.env.staging`, and `.env.*.local`. `.env.example` can be read. The operating system enforces this, not Claude. We tested `.env` files with dummy values only.
- The commands `bash ws/bin/ws.sh …` are the exception, because they are the way to use keys. A command that you start through `with-secrets` receives the keys. We cannot stop what that command does with them. A key that appears as-is in the output is hidden. A key that was split or changed is not.
- `ws.sh open` is listed as an excluded command, so that your browser can open.
- `--with-denywrite` adds a `filesystem.denyWrite` setting for `.ws`, `ws`, and `.claude`. We have not verified that this form works in Claude Code. Use it only if you want to try it.
- We tested reads of one folder and of `.env`, with dummy values, test paths, and test scripts. This is not the exact setting we ship. We have not tested `.ssh` and the GitHub login files. Network work may show more permission questions. We have not checked that either.

## Where the folder lives

- Keep each app in its own new empty folder directly in your home folder. Name it with English letters, numbers, and `-`, with no spaces, for example `~/coffee-log`. That folder is the workspace.
- If your user name has a space or a non-English letter, put the folder right under `/Users/Shared/` on a Mac, or right under `C:\` on Windows.
- Do not keep it in Downloads, Desktop, Documents, or a folder that iCloud, OneDrive, or Dropbox syncs. Sync can copy your work and your key files to the cloud.
- Do not keep it inside another Git repo, or in a path with spaces or non-English characters.
- `bash ws/bin/ws.sh doctor` prints `place: ok` or `place: warn` with the reason. It only warns.
- See "Where to put the folder" on the setup page for [Mac](setup-mac.md) or [Windows](setup-windows.md).

## Folders you bring in, and parent folders

- Claude Code loads `CLAUDE.md` files from the folder you open and from its parent folders. A bad `CLAUDE.md` in `Downloads` or in your home folder can give Claude orders.
- Inside `projects/<name>/src/`, the workspace is set to exclude `CLAUDE.md` and `CLAUDE.local.md`. We tested this for `CLAUDE.md` only.
- At the start, and in `bash ws/bin/ws.sh doctor`, the workspace looks for `CLAUDE.md` and `CLAUDE.local.md` in each parent folder, up to your home folder. If it finds one, you get a warning. Read that file yourself. If you do not trust it, move the workspace to another place.
- To stop Claude Code from loading such a file, run `bash ws/bin/ws.sh excludes add <absolute path>`. This adds the path to `claudeMdExcludes` in `settings.local.json`. It needs your own words in a message. We have not checked that Claude Code accepts an absolute path here.
- Do not keep the workspace in a synced folder (OneDrive, Dropbox, iCloud). Sync can damage the records in `.ws/`.

## Limits, in short

- Your chat history is on your computer as plain text.
- When Claude can run any code, that code may read environment variables and print them. The guards cannot read the code.
- The guards check an MCP tool that you add, other than Gakaso, only by its name. They stop a tool whose name says it writes or changes something before the build stage, and in the first message of a session.
- We have not tested these guards against a determined attacker. They are for mistakes and for common tricks.
