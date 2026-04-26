/**
 * Companion cutover feature flag.
 *
 * When true:
 *   - Cmd+Ctrl+\ toggles the companion-buddy window instead of the legacy
 *     Ask Nooto floating bar.
 *   - The `floating` and `whispr` windows are immediately closed at app
 *     startup so they never appear.
 *
 * When false:
 *   - Legacy behavior is unchanged — Companion still works via Fn PTT but
 *     the old surfaces remain available.
 *
 * Flip to `false` to revert for one release without a code change beyond this
 * file (and the matching Rust const in `src-tauri/src/feature_flags.rs`).
 */
export const COMPANION_CUTOVER_ENABLED = true;
