# Codex notes (for developers)

What CreateCodeBox knows about Codex, with the source of each fact. We tested only part of the Codex support, and less than the Claude Code version.

Sources (fetched 2026-10-31; the pages can change, so check them again before you rely on a detail):

- Hooks: <https://learn.chatgpt.com/docs/hooks>
- AGENTS.md: <https://learn.chatgpt.com/docs/agent-configuration/agents-md>
- Real runs: codex-cli 0.154.0 on macOS, 2026-10-31 (section "Real runs" below)

## How the Codex files are made

The Claude files are the originals. `python3 tools/gen_codex.py` builds `AGENTS.md`, `.codex/hooks.json` and
`BOOTSTRAP.codex.md` from `CLAUDE.md`, `.claude/agents/pm.md`, `.claude/settings.json` and `BOOTSTRAP.md`.
The only hand-kept part is `tools/codex_overlay.json` (small replacements). `python3 tools/gen_codex.py --check`
fails if a generated file is out of date, or if an overlay replacement no longer matches its original (CI runs it).
The code that is written by hand for Codex is `ws/adapters/codex.py`. The engine (state, approvals, `write_zone`, the key scan) is shared.

## Hooks (from the hooks page)

Events: `SessionStart`, `SessionEnd`, `SubagentStart`, `UserPromptSubmit`, `PreToolUse`, `PermissionRequest`, `PostToolUse`,
`PreCompact`/`PostCompact`, `SubagentStop`, `Stop`, `Interrupt`. CreateCodeBox uses four: `SessionStart`, `UserPromptSubmit`, `PreToolUse`, `Stop`.

Input on stdin (JSON), common fields: `session_id`, `transcript_path`, `cwd`, `hook_event_name`, `model`; turn events add `turn_id`;
most events add `permission_mode`. Event fields: `SessionStart.source` (`startup`, `resume`, `clear`, `compact`, `fork`), `UserPromptSubmit.prompt`,
`PreToolUse`/`PostToolUse` `tool_name`, `tool_use_id`, `tool_input`, `Stop.stop_hook_active`, `Stop.last_assistant_message`.

Tool names: a shell command is `Bash` (`tool_input.command` is the command). **A file edit is `apply_patch`, and the patch text is in
`tool_input.command`** (even if the matcher was `Edit` or `Write`). MCP tools are `mcp__<server>__<tool>`. Hosted tools such as web search are not covered by hooks.

Output (stdout JSON, exit 0):

- `PreToolUse` deny: `{"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny", "permissionDecisionReason": "..."}}`
  (the older `{"decision": "block", "reason": "..."}` also works). `ask` is not supported: the hook is marked failed and the tool call **continues**.
- `UserPromptSubmit`: context with `hookSpecificOutput.additionalContext`, or `{"decision": "block", "reason": "..."}`.
- `SessionStart`: `hookSpecificOutput.additionalContext` (plain stdout is also added as context).
- `Stop`: `{"decision": "block", "reason": "..."}` does not reject the turn: Codex makes a new continuation prompt of the reason text.
  `stop_hook_active` tells that the turn was already continued.
- Exit code 2 blocks (reason on stderr) for `PreToolUse`, `PostToolUse`, `UserPromptSubmit`, `SubagentStop`, `Stop`. Other non-zero exit codes are not defined on the page.
  CreateCodeBox therefore ends the `PreToolUse` and `UserPromptSubmit` commands with `|| exit 2`.

`hooks.json`: event, then matcher group (`matcher` is a regex; `"*"`, `""` or none matches everything; ignored for `UserPromptSubmit` and `Stop`), then `hooks` (handlers: `type`, `command`, `timeout` in seconds, default 600).
Places: `~/.codex/hooks.json`, `<repo>/.codex/hooks.json`, `config.toml` inline `[[hooks.X]]` tables, plugins. Hooks from all places run, concurrently.

Working folder: the session `cwd` (Codex may start in a subfolder). **The page documents no project-folder variable** for hooks (no `CLAUDE_PROJECT_DIR`
equivalent). So the generated command walks up from `$PWD` to the first folder that has `ws/bin/hook.sh`, and the adapter takes the workspace root from where the engine file is
(`ws/adapters/codex.py`), not from the current folder. This also works when Codex starts inside `projects/<name>/src/`.

Trust: "Project-local hooks load only when the project `.codex/` layer is trusted." "Non-managed hooks must be reviewed and trusted before running", trust is stored against
the hook's hash, and a new or changed hook is skipped until it is trusted again. `/hooks` in the CLI shows the sources and trusts them. `--dangerously-bypass-hook-trust` runs enabled hooks for one invocation.
The page does not say how a project becomes trusted, which file holds the hook trust, or what `codex exec` does. (What we saw: next section.)

## AGENTS.md (from the AGENTS.md page)

Codex builds the instruction chain once at startup. First the global file in `~/.codex` (or `CODEX_HOME`): `AGENTS.override.md` if it exists, else `AGENTS.md`.
Then, from the project root (usually the Git root) down to the current folder, one file per folder (`AGENTS.override.md`, then `AGENTS.md`, then the names in
`project_doc_fallback_filenames`). Files are joined root first, so the closest one comes last. The total is limited by `project_doc_max_bytes` (32 KiB by default); empty files are skipped.
The search stops at the current folder, so a file below it is not part of the chain. The page says nothing about nested Git repositories.

What this means here: the generated `AGENTS.md` is about 17 KB, so there is room, but the user's own `~/.codex/AGENTS.md` counts against the same 32 KiB.
An `AGENTS.md` inside imported code (`projects/<name>/src/`) is not read when Codex starts in the workspace folder. It is read when Codex starts inside that folder (confirmed, see below).
`doctor` and `SessionStart` warn about both. The user's `~/.codex/AGENTS.md` is reported as INFO and its content is never read.

## What the engine does for Codex

- `apply_patch`: every path in `*** Add File`, `*** Update File`, `*** Delete File`, `*** Move to` goes through `write_zone` and the protected places; the `+` lines go through the key scan;
  one refusal stops the whole patch; a patch that cannot be parsed exactly is refused. The same check runs when a patch is typed into the shell (`apply_patch <<EOF`).
  The same gate protects Claude Code too (the review found that an unknown tool was allowed last).
- An unknown tool whose name contains `write`, `edit`, `patch`, `apply`, `create`, `delete`, `move` or `rename` is refused. Other unknown tools are allowed.
  A small list of known harmless names is exempt (`update_plan`, `TodoWrite`, `Task`, `WebSearch`, ...). For MCP tools (`mcp__<server>__<tool>`), the same names are refused only until the build stage
  (RUN, DONE), and in the first turn of a session; after that the user decides what an added server may do. For example `mcp__tracker__create_issue` is refused at R1 and allowed in RUN.
- Protected places: `.codex/`, `AGENTS.md`, `BOOTSTRAP.codex.md` (as `.claude/`, `CLAUDE.md`, `ws/`, `.ws/`).
- Client choice: `ws/bin/hook.sh <event> --client codex` or `CREATECODEBOX_CLIENT=codex`; the default is `claude`.

## Real runs (codex-cli 0.154.0, macOS, 2026-10-31)

How: a copy of the repository in a scratch folder, `codex exec` (and `codex exec resume --last` for the next messages of the same session), `-s workspace-write`, `approval_policy="never"`.
A separate `CODEX_HOME` with its own `config.toml` (it only marks the scratch folders as trusted) so that `~/.codex/config.toml` is not changed; its `auth.json` is a symlink to the real one (its content was never read).
`HOME` and `CREATECODEBOX_SECRETS` pointed to scratch folders, so no key was created in the real home. The hooks were run with `--dangerously-bypass-hook-trust`.

| # | Item | Result | What was seen |
|---|------|--------|---------------|
| 1 | Writing to `src/` before approval is refused | OK | `apply_patch` to `projects/01_app/src/index.html` at stage R1: refused with "src/ cannot be written until the approval and the schedule are done"; the file does not exist. |
| 2 | The user's word `approve` records the approval | OK | `codex exec resume` with the prompt `approve` at stage R4A: `.ws/approval_01_app.json` was written, and `ws.sh status` said stage RUN. |
| 3 | After approval, writing to `src/` works | OK | `apply_patch` created `src/index.html` (2nd message of the session), and `cat` read it back. |
| 4 | Changing the design locks `src/` again | OK | `apply_patch` changed `design/io.json` (allowed); `status` went from RUN to R4A; the next `apply_patch` to `src/` was refused. |
| 5 | A key-like string is refused | OK | `apply_patch` of a file with a `sk_live_...` string (built by the model from two pieces) in `design/`: refused with "looks like a key or a password". |
| 6 | State is kept across sessions | OK | A new `codex exec` session: `status` still said RUN, and the first message of that session was read-only ("First turn is read-only"); the next message could write. |

Other things that were seen:

- **Project hooks load only when the project is trusted in the Codex config.** `-c projects."<path>".trust_level="trusted"` on the command line did **not** make `<repo>/.codex/hooks.json` (or a project `config.toml`) load; the same line in the `config.toml` of `CODEX_HOME` did. Inline hooks given with `-c hooks.SessionStart=[...]` ran without project trust.
- **Hooks that are not trusted are skipped without any message.** In a trusted project with no hook trust, the hooks did not run and Codex showed nothing. With `--dangerously-bypass-hook-trust` they ran. Then the only signal is a missing `[CreateCodeBox` line in the context: the generated `AGENTS.md` tells the model to stop in that case, and in a real run it did ("No. I will stop ... Open `/hooks` in Codex and trust the CreateCodeBox hooks"). That is a rule the model follows, not a check by code.
- Real hook input: the shell tool is `tool_name: "Bash"` with `tool_input.command` (a string); the edit tool is `tool_name: "apply_patch"` with the patch text in `tool_input.command`; `cwd` is the session folder; `Stop` has `last_assistant_message` and `stop_hook_active`; `permission_mode` was `bypassPermissions` because of the flag. Hooks inherited the environment of `codex` (`CREATECODEBOX_SECRETS` reached them).
- `additionalContext` from `SessionStart` and `UserPromptSubmit` reached the model (it quoted the `[CreateCodeBox stage ...` line and the "outside your home folder" place line).
- The model followed the generated `AGENTS.md` without being told: after `approve` it read the skill file with `cat`, ran `ws.sh schedule-init`, `render` and `open`.
- A refusal comes back to the model as "Command blocked by PreToolUse hook: CreateCodeBox: ..." with the stage line.
- Started in a subfolder (`ws/`, and `projects/01_app/src/`), the hook command found the workspace and refused `apply_patch` to `README.md` (also with `../`).
- An `AGENTS.md` placed in `projects/01_app/src/`: Codex started in the workspace folder did not load it; Codex started in `projects/01_app/src/` did, and the `SessionStart` warning for it was in the context.

Not done, so not claimed:

- The interactive trust steps (`/hooks` in the terminal UI, and the project trust question). Only `codex exec` with the bypass flag was used.
- Windows (the generated hook command is POSIX `sh`; `commandWindows` is not generated).
- `PermissionRequest` and `PostToolUse` hooks (not used), Codex Cloud, the desktop app, and approval prompts (the runs used `approval_policy="never"`).
- Whether Codex reads an `AGENTS.md` in a nested folder while it works (the page does not say; the runs started Codex in one folder only).
- A full first-time user path from `BOOTSTRAP.codex.md` (clone, trust, build a small app). The flow from stage R1 to the first build was driven with prepared files for the design steps.

## Known differences from the Claude Code version

- No helper agents: `pm` takes the roles one at a time. The "reviewer" pass is a self-check and is not called independent.
- No hardened mode (`ws.sh harden`) and no `excludes add` (they use Claude Code settings).
- Codex reads files through the shell, so the hook sees `cat`, `sed` and `rg` commands instead of a `Read` tool. Before approval only read-only commands pass (`ls`, `cat`, `head`, `tail`, `wc`, `grep`, `rg`, `find`, `git status|log|diff|show`, ...). `sed -n` and `nl` are not in that list.
- Codex has no permission allow-list file like `.claude/settings.json`; the user's approval policy and sandbox apply.
