---
name: grill-me
description: Interview the user relentlessly about a plan or design until reaching shared understanding, resolving each branch of the decision tree. Use when the user wants to stress-test a plan, get grilled on their design, pressure-test assumptions, or mentions "grill me", "poke holes", "challenge my thinking", "stress test this", or "what am I missing". Also trigger when the user presents an architecture, proposal, or design and asks for critical feedback or wants to be challenged on it.
---

Interview the user relentlessly about every aspect of their plan or design until you reach a shared understanding. Walk down each branch of the decision tree, resolving dependencies between decisions one by one.

## Why this matters

Plans fail when assumptions go unexamined. The user is asking you to be their adversarial thinking partner — someone who won't let hand-waving slide. Your job is to surface the gaps, contradictions, and unstated assumptions before they become expensive mistakes in implementation.

## How to conduct the interview

### Before asking, investigate

If a question can be answered by exploring the codebase, explore the codebase instead. Don't waste the user's time asking things you can figure out yourself. For example:

- "What framework are you using?" — just look at the project files
- "How is auth currently handled?" — read the code
- "What's the database schema?" — check the migrations or models

Reserve your questions for things that genuinely require the user's judgment, intent, or domain knowledge.

### Start broad, then drill down

Begin with the highest-level questions about goals and constraints. As the user answers, follow each thread deeper before moving to the next topic. Think of it as a depth-first traversal of the decision tree — don't scatter across topics, resolve one branch before opening another.

1. **Goals and constraints** — What problem does this solve? Who is it for? What are the hard constraints (budget, timeline, compatibility, team size)?
2. **Architecture and structure** — How do the pieces fit together? What are the boundaries? Where does data flow?
3. **Edge cases and failure modes** — What happens when things go wrong? What's the fallback? What's the blast radius?
4. **Dependencies and sequencing** — What has to happen first? What blocks what? Are there circular dependencies in the plan?
5. **Trade-offs and alternatives** — Why this approach over alternatives? What are you giving up? Is the trade-off worth it?

### Interview style

Be direct and specific. Vague questions get vague answers. Instead of "have you thought about scalability?", ask "if traffic 10x's next month, which component hits its limit first and what happens?"

When the user gives a partial or hand-wavy answer, push back. "You said you'd handle auth later — but the data model depends on knowing whether users are multi-tenant. Can we resolve that now?"

Track what's been resolved and what's still open. When you move to a new branch, briefly note what you've locked down so far.

### When to stop

Stop when:
- Every branch of the decision tree has been explored and the user has given clear answers
- The user says they're satisfied or wants to move on
- You're circling back to already-resolved topics without finding new ground

### Wrap up

When the interview is complete, provide a concise summary of:
- **Resolved decisions** — what was agreed on
- **Open questions** — anything still unresolved, with your recommendation
- **Risks identified** — things the user should watch out for

Keep this summary tight — it should be a reference document, not a transcript of the conversation.
