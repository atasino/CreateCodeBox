<!-- card: private-public v4 -->
# Learn card: Private and public

## In one line
Private means you decide who can open it. Public means everyone on the internet can see it.

## Think of it as
A sealed letter and a postcard. You keep a sealed letter, and you choose who opens it. Everyone who handles a postcard can read it, and it is hard to take back.

## What happens now
- You choose private or public on the GitHub website. Start with private.
- First run `bash ws/bin/ws.sh publish-check`. It checks the whole history for keys in known formats. It checks that a README and a license exist, and that nothing is unsaved. It also checks that your saves use only hidden email addresses (ones that do not show who you are).
- It does not look inside your files for personal data, such as real names, home addresses, email addresses, or customer data. You must check that yourself.
- If the check passes, you decide whether to publish. To publish, type exactly `publish` in the chat. `pm` (the assistant you talk to) is told never to say it for you.
- Then `bash ws/bin/ws.sh publish` sends your work to the repo you registered. After it sends, you make the repo public yourself on the GitHub website. GitHub's own help shows how.

## Watch out
- When you go public, people see the files and also the whole history, including things you deleted.
- Once it is public, it is hard to take back. Others may copy it.
- If a key was ever saved, make a new key and cancel the old one. Deleting the file is not enough.
- If you edit a file on the GitHub website, or merge a pull request (a proposed change) there, GitHub may write your account's email address into the save it makes. To stop that in later changes, turn on "Keep my email addresses private" in GitHub (Settings → Emails).
- If you are not sure, keep it private. You can publish later.

## The technical name
A private repository and a public repository. The history is the commit history.
