---
description: Interview the user and scaffold this freshly-cloned starter into a real project
---

This repo was cloned from the agentic starter template and is not yet set up.

**The procedure is [docs/scaffold.md](../../docs/scaffold.md).** Read it, work its sections in
order, and tick each box as you complete it so the state survives an interrupted session. Do not
restate its steps here — this file holds only how to conduct the interview.

How to run it:

- **Ask, don't infer.** Do not scan the filesystem and guess the stack. An empty repo has no signal,
  and generated guesses are exactly the noise this template exists to avoid.
- Ask in **small batches** — two or three related questions at a time, not a wall of twenty.
- Offer a concrete recommendation with each question so the user can say "yes" and move on.
- If the user says something that contradicts an earlier answer, follow the new answer and adjust
  what you already wrote.
- **Stop at the gate.** Do not proceed past the "The gate" section until `./scripts/check` actually
  exits 0 on the empty project. Everything after it depends on that being real.
- Prefer editing the files that exist over adding new ones. This starter is deliberately small; a
  scaffolded project should gain a lockfile, tool configs, and a source tree — not a docs sprawl.
