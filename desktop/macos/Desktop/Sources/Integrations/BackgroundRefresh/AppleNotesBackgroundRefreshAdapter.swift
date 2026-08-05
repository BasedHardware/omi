import Foundation

/// Background refresh adapter for Apple Notes.
///
/// **Eligible for unattended refresh.** Notes are read through Notes.app over
/// Apple Events, so the only grant involved is the macOS Automation permission,
/// which the user answers once during the first user-initiated import. Once
/// held, re-reading raises no dialog, and there is no folder to pick.
///
/// If the grant is revoked the read fails with a permission-class error, which
/// ``ConnectorRefreshOutcomeMapper`` maps to `.needsUserAction` — the connector
/// parks and asks for a reconnect instead of retrying into a dialog.
///
/// **Raw import only.** A background refresh must never run LLM synthesis. The
/// backend dedupes raw import artifacts on `external_id` + `content_hash`
/// (`backend/database/memory_imports.py`), so re-importing the same notes is
/// idempotent. Synthesized memories carry no `external_id`, so varying model
/// output would mint fresh artifacts on every single refresh, forever — the
/// mass-duplication failure this repo already had to purge server-side.
@MainActor
final class AppleNotesBackgroundRefreshAdapter: BackgroundRefreshableConnector {
  static let connectorIdentifier = "apple-notes"

  let connectorID = AppleNotesBackgroundRefreshAdapter.connectorIdentifier
  let refreshInterval: TimeInterval

  private let unattendedRefreshSupported: Bool
  private let performRefresh: @MainActor (ConnectorImportRunner.ProgressSink) async -> ConnectorRefreshResult

  var supportsUnattendedRefresh: Bool { unattendedRefreshSupported }

  init(
    supportsUnattendedRefresh: Bool = true,
    refreshInterval: TimeInterval = 6 * 3600,
    performRefresh: @escaping @MainActor (ConnectorImportRunner.ProgressSink) async -> ConnectorRefreshResult =
      AppleNotesBackgroundRefreshAdapter.liveRefresh
  ) {
    self.unattendedRefreshSupported = supportsUnattendedRefresh
    self.refreshInterval = refreshInterval
    self.performRefresh = performRefresh
  }

  func refresh(progress: ConnectorImportRunner.ProgressSink) async -> ConnectorRefreshResult {
    await performRefresh(progress)
  }

  /// `userInitiated: false` is the whole contract of this call: it is what makes
  /// the Apple Events read passive (never prompting for the Automation grant on
  /// a run nobody asked for) and what skips `synthesizeFromNotes`, keeping the
  /// background pass to raw, `external_id`-deduped artifacts only.
  static func liveRefresh(progress: ConnectorImportRunner.ProgressSink) async -> ConnectorRefreshResult {
    let outcome = await ConnectorImportOperations.importAppleNotes(progress: progress, userInitiated: false)
    return ConnectorRefreshOutcomeMapper.result(from: outcome)
  }
}
