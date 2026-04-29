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

/// When `true`, the Coding Agent surface (Pi sidecar + chat UI) is shown in the
/// sidebar and routable. When `false`, the route is unmounted and the nav entry
/// is hidden — the underlying code still ships, just dark.
///
/// Default: `false` until the feature has soaked in internal dogfood.
pub const CODING_AGENT_ENABLED: bool = false;
