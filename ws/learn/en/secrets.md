<!-- card: secrets v3 -->
# Learn card: Keys and .env

## In one line
A key (an API key, a password, or a token) lets a program use an online service as you. Anyone who holds the key can act as you.

## Think of it as
The key to your house. You do not show it to people, and you do not leave it in a public place.

## What happens now
- A `.env` file is a list of keys, one per line, written as `NAME=value`.
- Your keys are stored outside the workspace, in `~/.createcodebox`. This way, a share or a publish is less likely to take them by mistake.
- A key for the app you build is stored in `projects/<name>/src/.env`. The workspace is set up to stop Claude's tools from opening it. Save does not include it.
- When a key is needed, `pm` (the assistant you talk to) runs `bash ws/bin/ws.sh secret guide <NAME>` and gives you one line.
- Paste that line in a **separate** Terminal window and press Enter. Then paste the key and press Enter. Nothing shows on the screen as you type. That is normal.
- To see if a key is set, run `bash ws/bin/ws.sh secret check`. It shows names only, never values.

## Watch out
- Never paste a key into the chat. If you did, revoke (cancel) the key at the service, and create a new one.
- The guards reduce mistakes. They are not a wall. They do not keep a key away from Claude in every case.
- Start with a test key that has low limits. It is safer than your real key.

## The technical name
An environment variable, an API key, a secret, or a token.
