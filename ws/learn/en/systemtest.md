<!-- card: systemtest v4 -->
# Learn card: What "done" means

## In one line
Done means you really see every result you asked for. That includes the normal case and the failure case.

## Think of it as
A parcel. It is not delivered because the label says so. It is delivered when you open the box and see what is inside.

## What happens now
- Before building, you and `pm` (the assistant you talk to) write a list: what you should see, one line at a time. These lines are the test cases.
- A case id looks like `T-IO-01-N1`. N is a normal case. B is an empty or edge case. F is a failure case.
- Many of the cases are for empty and failure situations. You decide what you see when something goes wrong, before building.
- See the list with `bash ws/bin/ws.sh st list --numbered`. You can answer by number.
- You check what you asked for, once each: the normal cases. You use the thing yourself, and tell Claude what you saw. Then the case is recorded as passed.
- Claude checks the empty and failure cases, and the cases you cannot start by hand, such as a monthly job. The list shows which of those are not checked yet.
- The first version is done when every case that you check and every normal case have passed.

## Watch out
- A test mark that says "pass" is not enough. You, or Claude, must really see the result you asked for.
- The empty and failure cases still count. Claude checks them, and tells you how many are not checked yet.
- If you cannot decide if a case passed, do not add more checks. Make the sentence about what you should see clearer.

## The technical name
This is a system test. A normal case is a normal path. An empty or failure case is an error path. CI is a machine that checks every change. Unit tests are tests of one small part. Both are extra tools that come after.
