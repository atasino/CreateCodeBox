<!-- card: mcp v4 -->
# Learn card: MCP

## In one line
MCP is a way for Claude to reach an online service and use it for you.

## Think of it as
Opening one more door for Claude. Each connection is one door. You decide which doors are open.

## What happens now
- You do these parts: sign up at the service, prove who you are, and press "allow".
- Claude does the rest through the connection.
- The service key is built not to go to Claude. It goes to the connection through a small helper that hands over the key only when it is needed. We have not tested this with a real service yet.
- When you want to connect a service, `pm` (the assistant you talk to) shows you the steps.

## Watch out
- Connect only services you chose. More connections mean more things Claude can do.
- If you add a connection other than Gakaso (our own product), the workspace checks only the names of its tools. It stops a tool whose name says it writes or changes something. It does this before the build stage starts, and in the first message of each session. Read what its tools can do before you add it.
- Do not write a key into a settings file. If you publish the file, anyone can see the key.
- When a page shows a key on the screen, you do that step yourself. Claude is told not to look at the screen then.

## The technical name
MCP means Model Context Protocol. A connection is called an MCP server. The settings are in `.mcp.json`.
