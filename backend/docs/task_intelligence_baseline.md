# Task intelligence baseline for #9352

This file records the pre-implementation boundaries that the Ticket 01 fixtures and source manifest protect.

Current authority boundary: all authenticated users share the Candidate, task,
goal, workstream, recommendation, and Chat-first logic. Persisted workflow/UI
fields remain account-generation and proactive-choice fences; memory storage
origin and deployment environment variables are never product gates.

- Backend conversation extraction can write directly to `action_items`; desktop screen extraction stages and ranks locally.
- Desktop task discovery is coupled to proactive-task notification enablement.
- The backend action-item contract drops desktop-only provenance, confidence, goal, recurrence, and agent fields.
- Mobile goal links and desktop task-agent continuity are not canonical backend relationships.
- `staged_tasks` and local staged SQLite can both influence promotion and deduplication.
- Feedback cannot yet join an intervention to a Candidate, canonical task/workstream, and later outcome.

Ticket ownership:

- Ticket 02 removes backend contract and Candidate-lifecycle gaps.
- Ticket 03 proves Swift/Dart round-trip parity.
- Tickets 04–06 establish workstream product and execution boundaries.
- Tickets 07–12 replace capture, UX, evaluation, and attention behavior.
- Universal convergence retains staged-task reads only as a compatibility
  adapter. Physical legacy deletion requires separate evidence and approval.

Remaining compatibility burn-down (not an entitlement boundary):

- Delete `TaskPromotionService` timer and local `staged_tasks` GRDB authority once released-client parity is proven.
- Grep ratchet proving legacy staged writers are gone.
- Collapse Swift `task_chat_messages` into kernel SQLite (INV-CHAT-1 dual-store debt).
- Remove tmux / legacy `task_chat` surface paths marked for Ticket 14.
