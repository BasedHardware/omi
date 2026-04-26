//! Feature flags for controlled rollout of new surfaces.
//!
//! Each flag has a matching TypeScript const in
//! `src/config/companionFeatureFlag.ts`. Both must be flipped together when
//! toggling a cutover for a release.

/// When `true`:
/// - The `Cmd+Ctrl+\` global shortcut toggles the Companion buddy instead of
///   the legacy Ask Nooto floating bar.
/// - The `floating` and `whispr` windows are closed at startup so they never
///   appear in the UI.
///
/// Set to `false` to revert for one release.
pub const COMPANION_CUTOVER_ENABLED: bool = true;
