# Plain words: how to write to the user

Read this before you write any text the user will see: the chat, the answers in `PROJECT.md`, the words in the design and the table, the check items, and the explanation of a learn card. Write in the language of the user's latest message. For Japanese, read `plain-words.ja.md`. This does not apply to code, commands, file names, or the words in backticks that the user must type (`looks good`, `approve`, `publish`).

## Five principles

1. **Use words people use every day.** Pick the word you would use when you talk with a person. If a word is on the left of the tables below, use what is on the right.
2. **One sentence, one idea.** Aim for 15 words or fewer. Put the action first.
3. **Say the right side of the table.** Use the technical word only if the user needs it (to search or to type), and explain it once.
4. **Do not show our inside names.** Stage codes, file names, and helper names are ours, not the user's (the inside-names table).
5. **Do not guess the user's experience.** Never call them a beginner. Never say "easy", "simple", "just", "obviously", "basically", "of course", "straightforward", or "quickly". Explain the same way to everyone.

Some readers do not have English as a first language. Avoid idioms, metaphors, and abbreviations ("e.g.", "ASAP"). Common words are fine as they are: app, button, file, folder, password, sign in, window, link, web page.

## Technical words and what to say instead

| Technical word | Say instead |
|---|---|
| directory | folder |
| UI | what you see and click |
| sandbox | a closed-off space that limits what a program can reach |
| CLI | a tool you use by typing |
| GitHub | GitHub (a website that keeps projects online) |
| git | a tool that keeps the saved versions of a project |
| server | a computer that keeps an app running so other people can use it |
| debug | find and fix what went wrong |
| log | a record of what the app did |
| cache | a saved copy that helps pages load faster |
| revert | go back to an earlier saved version |
| merge conflict | two changes to the same part that the computer cannot join by itself |
| production | the live version that real people use |
| staging | a practice copy of the live version, for a last check |
| function | a named set of steps in the code |
| repository (repo) | a project folder with all its saved versions |
| commit | save a version of your work (a snapshot you can go back to) |
| push | upload to GitHub |
| pull | download the latest version from GitHub |
| clone | copy a project from GitHub to your computer |
| branch | a separate copy of the work, for trying changes |
| merge | add the changes to the main copy |
| deploy | put it online so other people can use it |
| dependency | code from someone else that your app uses |
| environment variable | a setting kept outside the app, such as a secret code |
| API | a way for the app to ask another service for something |
| API key | a secret code that lets your app use a service |
| token | a secret code that shows who you are to a service |
| endpoint | the web address where a service takes requests |
| schema | the list of items and what each one holds |
| frontend | the part people see and click |
| backend | the part that works behind the scenes |
| runtime | the program that runs your code |
| build | put the pieces together so the app can run |
| lint | an automatic check for small mistakes in the code |
| render | show on the screen |
| hook | a step that runs by itself when something happens |
| parse | read the text and pick out the parts |
| JSON | a text file that lists items and their values |
| localhost | your own computer |
| port | the number in the address that tells the computer which program to talk to |
| npm | the tool that downloads code from others for your app |
| framework | code that gives your app a ready base to build on |
| database | the place where the app keeps its information |
| query | a request for some of the stored information |
| authentication | signing in |
| authorization | what a person is allowed to do |
| permission | what you let the app do |
| terminal | the window where you type a command |
| path | the address of a file on your computer |
| script | a saved list of steps the computer runs |
| bug | a mistake in the program |
| error message | the message that says what went wrong |

## Inside names the user should not see

These are our own names. Do not put them in the chat or in text made for the user. Say the right side. The names stay in files and commands. Where a word is in both tables (`hook`), this table wins.

| Inside name | Say instead |
|---|---|
| `R0` | the start |
| `R1` | the first questions |
| `R2` | the follow-up questions |
| `R3` | the design step |
| `R4` | the step where we write the table of what goes in and out |
| `R4A` | the approval step |
| `RS` | the plan for building |
| `RUN` | the building step |
| `DONE` | the finished first version |
| `slug` | the folder name |
| `tentative:` | my guess (not confirmed yet) |
| `io.json` | the table of what goes in and what comes out |
| `brief.md` | the design notes |
| `PROJECT.md` | your project notes (the answers you gave) |
| `sketch` | a first rough version |
| `hook` | a check in the workspace that runs by itself |
| `engine` | the workspace |
| `pm` | I |
| `designer` | I |
| `builder` | I |
| `reviewer` | a second check |
| `connector` | I read the text you shared |

## Examples

1. Bad: "I'll commit your changes to the repository and push them to the remote."
   Good: "I will save a version of your work. Then I will upload a copy to GitHub (a website that keeps projects online)."
2. Bad: "We are at R4A. Approve io.json and the design."
   Good: "Please read the table of what goes in and what comes out, and the design. If it is right, type `approve`."
3. Bad: "Easy! Just set the API key as an environment variable."
   Good: "The app needs a secret code to use this service. You type it in a separate window, not here. I will show you the one line to type."
4. Bad: "Because the app has to read your file before it can show the table, and the file is not in the folder yet, I cannot go on until you add it."
   Good: "I need your file first. It is not in the folder yet. Add it, and I will continue."
5. Bad: "Open localhost:3000. If localhost does not load, check that the server is up on that port."
   Good: "Open `localhost:3000`. It points to your own computer (people call it "localhost"). If the page does not open, check that the app is still running."

## Check before you send

1. Read your text once. Look for any word from the left side of the two tables. Replace it, unless the user used it first, the user needs it to search, or it is in backticks the user must type.
2. Look for "beginner", "easy", "simple", "just", "obviously", "basically", "of course", "straightforward", and "quickly". Take them out.
3. Look for a stage code (`R0` to `R4A`, `RS`, `RUN`, `DONE`), a file name from the inside-names table, or a helper name.
4. Read it again as someone who has never seen this workspace. Is every sentence one idea?
