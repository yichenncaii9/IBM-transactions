# Q1 plan and work split: chat history

Thread between Jia Qing and Claude, 1 to 2 Nov 2026. The plan itself is in the doc "Q1 plan and work split" (https://claude.ai/artifact/PSa8Kwbjrxd2w8mii2SSYn). Progress-checklist updates are left out.

---

**Jia Qing (1 Nov, 14:12):** and this is what our groupmates decide to do also. Based on the prof feedback and this, help me help the entire group understand the entire plan of our project once again (maybe with a flow chart or whatever)

Moving forward, now tell us how to split the work amongst ourselves. We are meeting up in around 3 days - any potential items/tasks we should do (especially those take 3-4 hours to run) can split up and do first. Help us plan out who to do what, and by when

**Claude:** I've put the group plan in one doc: Q1 plan and work split. It has a flow chart of the whole pipeline, a task table with owners and a status column, a day-by-day timeline to 15 Nov, and a list of risks.

What to do tonight: each person picks a letter in the group chat. A is data and AWS, B is graph work in Neo4j, C is features, and D is models and scoring. Then A gets the AWS keys working, because everything else waits on that.

The three long jobs are the Glue clean-up (A), the Neo4j motif and WCC run (B) and the full feature run (C). They start Mon 2 and Tue 3 Nov so there are real numbers to look at on Wednesday.

Fix these four things before the long jobs run. Each one would make your scores look better than they really are:
- Rule C taint is seeded from the answer labels.
- Oversampling validation and test pushes the scores up.
- Account features use the whole timeline, so they include data from after the split.
- Rule A counts connections across all the data, including the future.

The doc gives a fix for each. I also flagged three more: WCC may lump most accounts into one giant scheme, the prof asked for scores per transaction, and Rule D pair counts blow up at busy accounts.

The open questions for Wednesday are at the bottom of the doc. The main one is whether the prof really meant to oversample the test set. D's pilot on Tuesday will show how big the difference is.

---

**Jia Qing (1 Nov, 16:48):** are you able to simplify the steps each person needs to take and ensure they know their tasks

**Claude:** I added a "Your steps" section near the top of the doc. Each member gets a short list of dated steps they can tick off. The risk fixes are already written into those steps, so nobody has to read the risk table. Steps marked "share" are handoffs that someone else is waiting on.

---

**Jia Qing (1 Nov, 16:51):** so we have 6 people in our group

**Jia Qing (1 Nov, 16:52):** don't need to set dates to be done by when, and also its important to note that we are all working asynchronously until wednesday when we meet in 3 days

**Claude:** I've updated the doc for six people working on their own until Wednesday:
- No task dates. I removed the day-by-day timeline and the dated tracker table.
- Six lanes, A to F. A table shows who each person waits on. Only A waits on nobody.
- Each list is in two parts. "Before Wednesday" opens with a step you can start straight away, then steps that wait for someone's "post" in the group chat. "After the meetup" comes second.
- The flow chart now has six owner colours, so it matches the lanes.

---

**Jia Qing (1 Nov, 20:22):** is this a condensed version already? can't get any shorter correct? if so, then leave it. Do i just send this docs on telegram to my groupmates? what should i tell them as a chat instruction - keep it short and concise

**Claude:** Yes, it's short enough, so I'd leave it. Each person only needs to read the flow chart and their own lane. The risk table and open questions are mainly for the meetup. The doc is private, so share it with Share at the top of the doc, or export it as a PDF and send the file.

Message for the chat:

> Q1 plan (link/PDF). Claim a letter A–F here, first come first served. Read the flow chart + your own lane under "Your steps" only. Work on your own till Wed; when you finish a step marked post, drop it here since someone's waiting on it. Long jobs (A, C, D) take 3–4h, start yours early. Meet Wed 6 PM in the lab.

---

**Jia Qing (1 Nov, 20:26):** does any of the letters require something from another letter before he can start his work

**Claude:** No. All six can start straight away, because every lane opens with a "start now" step. Only the later steps wait on someone else:
- A waits on nobody.
- B needs A's working AWS keys before running the split queries.
- C needs B's split dates for the long motif run. Loading Neo4j can start now.
- D needs A's clean data and B's dates for the long feature run. Writing the rule code can start now.
- E needs D's features for the first real training run. The scoring script can start now on fake data.
- F needs D's features for the oversampling pilot. The baseline code can start now.

So the chain is A → B → C and D → E and F. If A's AWS keys get stuck, everyone after A gets stuck too. Whoever takes A should start tonight.
