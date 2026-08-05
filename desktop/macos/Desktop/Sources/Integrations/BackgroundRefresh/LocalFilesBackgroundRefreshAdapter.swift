import Foundation

/// Background refresh adapter for the on-device local file index.
///
/// **Eligibility is computed, never declared constant.** The local-file scan
/// walks `~/Downloads`, `~/Documents`, and `~/Desktop` with `FileManager`, and
/// the *first* touch of each of those raises a macOS TCC dialog. It is only
/// prompt-free after a user-initiated scan has already answered those dialogs —
/// which the scan reports as `deniedUserFolders.isEmpty`. That fact is recorded
/// in ``ConnectorRefreshState/unattendedGrantProven`` and read here on every
/// evaluation, so a revoked grant takes the connector back out of the
/// background rotation immediately.
///
/// This connector is precisely why ``BackgroundRefreshableConnector/supportsUnattendedRefresh``
/// is a `{ get }` requirement instead of a stored constant.
///
/// **Raw import only.** A background rescan re-indexes on device and must never
/// run LLM synthesis. Synthesized memories carry no `external_id`, so the
/// backend's `external_id` + `content_hash` dedupe
/// (`backend/database/memory_imports.py`) cannot collapse them and every
/// refresh would mint fresh duplicate artifacts forever.
@MainActor
final class LocalFilesBackgroundRefreshAdapter: BackgroundRefreshableConnector {
  static let connectorIdentifier = "local-files"

  let connectorID = LocalFilesBackgroundRefreshAdapter.connectorIdentifier
  let refreshInterval: TimeInterval

  private let grantProbe: @MainActor () -> Bool
  private let performRefresh: @MainActor (ConnectorImportRunner.ProgressSink) async -> ConnectorRefreshResult

  /// Recomputed on every read: a full-disk or folder grant can be revoked in
  /// System Settings at any time, and a stale `true` here would mean a prompt.
  var supportsUnattendedRefresh: Bool { grantProbe() }

  init(
    refreshInterval: TimeInterval = 24 * 3600,
    stateStore: ConnectorRefreshStateStore? = nil,
    grantProbe: (@MainActor () -> Bool)? = nil,
    performRefresh: @escaping @MainActor (ConnectorImportRunner.ProgressSink) async -> ConnectorRefreshResult =
      LocalFilesBackgroundRefreshAdapter.liveRefresh
  ) {
    self.refreshInterval = refreshInterval
    self.performRefresh = performRefresh
    if let grantProbe {
      self.grantProbe = grantProbe
    } else if let stateStore {
      self.grantProbe = { stateStore.state(for: Self.connectorIdentifier).unattendedGrantProven }
    } else {
      // Built per read, not captured once: the store binds the signed-in user's
      // id when it is constructed, and this adapter is created during app
      // startup — before sign-in restores on a cold launch. A captured store
      // would keep reading the signed-out key forever and the grant would never
      // be seen.
      self.grantProbe = { ConnectorRefreshStateStore().state(for: Self.connectorIdentifier).unattendedGrantProven }
    }
  }

  func refresh(progress: ConnectorImportRunner.ProgressSink) async -> ConnectorRefreshResult {
    await performRefresh(progress)
  }

  /// Reuses the same scan the Apps tab runs, unchanged. There is no separate
  /// unattended entry point because the scan cannot prompt by the time this is
  /// reachable: `supportsUnattendedRefresh` is `false` until a user-initiated
  /// scan reported every user folder readable, and
  /// `ConnectorImportOperations.rescanLocalFiles` records that fact on every run
  /// — so a revoked folder takes this connector back out of the rotation on the
  /// next user scan. The scan is an on-device reindex only; it runs no LLM
  /// synthesis at all.
  static func liveRefresh(progress: ConnectorImportRunner.ProgressSink) async -> ConnectorRefreshResult {
    progress.update(
      title: "Reindexing local files",
      detail: "Checking your on-device folders for new or changed files."
    )
    let outcome = await ConnectorImportOperations.rescanLocalFiles(analyticsSurface: "background_refresh")
    return ConnectorRefreshOutcomeMapper.result(from: outcome)
  }
}
