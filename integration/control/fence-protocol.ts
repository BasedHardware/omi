/**
 * Constants shared by the fence harness server and its test.
 *
 * They live in their own module because `fence-server.ts` calls `Bun.serve` at
 * import time: importing a constant from it would silently start a second
 * listener inside the test process, and the test would then be measuring a server
 * it did not spawn. That is the "measured artifact is not the artifact under
 * test" shape, in miniature.
 */

/** Ratified: ruling B4 (route shape) on ruling B6's first writable domain. */
export const OPS_PATH = "/v1/tasks/ops";

/** Joins a fence decision to the run that caused it. */
export const RUN_ID_HEADER = "x-omi-run-id";

/** The harness's single accepted credential. Its only job is to make the
 * `authentication` outcome reachable so a test can prove it is a different
 * outcome from `stale_epoch`. */
export const QA_BEARER = "omi-fence-integration-qa-token-v1";

/** The account the harness's single principal resolves to, server-side. */
export const ACCOUNT_OF_PRINCIPAL = "acct-fence-integration-fixture";
