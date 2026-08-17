// LIFECYCLE: permanent
//
// Constants shared by the write journey's driver, its outbox stage and their
// tests.
//
// THEY LIVE IN THEIR OWN MODULE FOR A REASON THAT COST A RUN. `write-journey.mjs`
// executes its CLI at import time. `write-journey-outbox.mjs` imported one
// constant from it, and `write-journey.mjs`'s CLI then dynamically imported the
// outbox module — a cycle whose two halves both awaited at top level. Node
// exited 13 with "unsettled top-level await" and no verdict at all.
//
// The retired `platform/integration/control/fence-protocol.ts` existed for the
// same shape and said so in its own header: importing a constant from a module
// that starts a server at import time silently starts a second server. Same
// lesson, different symptom: a module that DOES something at import time must
// not be anybody's source of constants.

/** Ratified: ruling B4's route shape on ruling B6's first writable domain. */
export const OPS_PATH = "/v1/tasks/ops";

/** Joins a fence and write-ops decision to the run that caused it. */
export const RUN_ID_HEADER = "x-omi-run-id";

/**
 * The dev control plane, registered on the SAME app that serves the door
 * (`apps/service/routes/qa-control.ts`). Not a harness server: the retired
 * `integration/control/fence-server.ts` stood up its own `Bun.serve` and
 * answered `/v1/tasks/ops` with `202 {"fence":"admitted"}` where the registered
 * route answers `200 {applied, idempotent}` — two doors diverged at the byte
 * level (R5, and fable's R14 quarantine of everything measured against the
 * harness while both stood).
 */
export const CONTROL_BASE = "/v1/qa/control";
