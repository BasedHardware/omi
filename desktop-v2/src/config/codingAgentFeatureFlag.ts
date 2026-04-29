/**
 * Coding Agent feature flag.
 *
 * Mirror of `CODING_AGENT_ENABLED` in `src-tauri/src/feature_flags.rs`.
 * Both must be flipped together when toggling rollout.
 *
 * When `true`: sidebar nav entry + `/coding-agent` route are rendered.
 * When `false`: the nav entry is hidden and the route mount is skipped, so the
 * feature is dark even though the components still ship.
 */
export const CODING_AGENT_ENABLED = true;
