/**
 * Test environment setup.
 *
 * Only globals that are genuinely environmental belong here. Anything a test
 * needs to control per-case belongs in the test, so that a test asserting
 * "no permission prompt was requested" cannot be defeated by another test's
 * leftover state.
 */

global.__DEV__ = true;

// Without this React refuses to run inside act(), which is what keeps state
// updates flushed before an assertion. RNTL does not set it for us here, so
// every async test logs "the current testing environment is not configured to
// support act(...)" and assertions can race an un-flushed update.
global.IS_REACT_ACT_ENVIRONMENT = true;
