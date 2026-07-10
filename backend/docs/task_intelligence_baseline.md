# Task intelligence baseline for #9352

This file records the pre-implementation boundaries that the Ticket 01 fixtures and source manifest protect.

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
- Tickets 13–14 own universal migration and physical legacy deletion after their gates.
