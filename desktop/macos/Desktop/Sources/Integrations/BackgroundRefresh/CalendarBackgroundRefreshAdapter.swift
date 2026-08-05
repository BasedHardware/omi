import Foundation

/// Background refresh adapter for Google Calendar.
///
/// **Not eligible for unattended refresh today.** Calendar reaches Google by
/// decrypting another application's Safe Storage Keychain item
/// (`BrowserGoogleSession` / `BrowserKeychainCache`), which macOS guards with a
/// login-keychain consent sheet. The unattended path does not answer that sheet,
/// it suppresses it — `userInitiated: false` sets `kSecUseAuthenticationUISkip`
/// — so a background tick can never put a system password prompt in front of a
/// user who is doing something else. What it does instead is fail: any time
/// macOS will not hand the item over silently the read returns
/// `cookieDecryptionFailed`, which parks the connector and asks the user to
/// reconnect something that is not actually broken. Enabling this today would
/// trade a prompt storm for a false-alarm storm, so the default stays `false`
/// and the scheduler's very first gate skips it.
///
/// This flips to `true` once server-side Google OAuth lands
/// (https://github.com/BasedHardware/omi/pull/10969, tracking issue
/// https://github.com/BasedHardware/omi/issues/10459): with a refresh token
/// held server-side there is no Keychain item to decrypt at all. Flipping the
/// default is then a one-line change here plus deleting these two paragraphs.
///
/// **Raw import only.** A background refresh must never run LLM synthesis. The
/// backend dedupes raw import artifacts on `external_id` + `content_hash`
/// (`backend/database/memory_imports.py`), so re-importing the same calendar
/// events is idempotent. Synthesized memories carry no `external_id`, so
/// varying model output would mint fresh artifacts on every single refresh,
/// forever. This repo has already paid for that once with a server-side purge.
@MainActor
final class CalendarBackgroundRefreshAdapter: BackgroundRefreshableConnector {
  static let connectorIdentifier = "calendar"

  let connectorID = CalendarBackgroundRefreshAdapter.connectorIdentifier
  let refreshInterval: TimeInterval

  private let unattendedRefreshSupported: Bool
  private let performRefresh: @MainActor (ConnectorImportRunner.ProgressSink) async -> ConnectorRefreshResult

  var supportsUnattendedRefresh: Bool { unattendedRefreshSupported }

  init(
    supportsUnattendedRefresh: Bool = false,
    refreshInterval: TimeInterval = 6 * 3600,
    performRefresh: @escaping @MainActor (ConnectorImportRunner.ProgressSink) async -> ConnectorRefreshResult =
      CalendarBackgroundRefreshAdapter.liveRefresh
  ) {
    self.unattendedRefreshSupported = supportsUnattendedRefresh
    self.refreshInterval = refreshInterval
    self.performRefresh = performRefresh
  }

  func refresh(progress: ConnectorImportRunner.ProgressSink) async -> ConnectorRefreshResult {
    await performRefresh(progress)
  }

  /// Wired, but unreachable in production while `supportsUnattendedRefresh`
  /// defaults to `false` — the scheduler's first gate skips this connector. It
  /// runs today only when a caller opts in explicitly.
  ///
  /// `userInitiated: false` threads through to `CalendarReaderService.readEvents`,
  /// which refuses to decrypt browser cookies on a passive read, and skips
  /// `synthesizeFromEvents` so the background pass stays raw and
  /// `external_id`-deduped.
  static func liveRefresh(progress: ConnectorImportRunner.ProgressSink) async -> ConnectorRefreshResult {
    let outcome = await ConnectorImportOperations.importCalendar(progress: progress, userInitiated: false)
    return ConnectorRefreshOutcomeMapper.result(from: outcome)
  }
}
