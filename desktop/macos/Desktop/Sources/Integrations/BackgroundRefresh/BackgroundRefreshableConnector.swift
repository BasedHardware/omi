import Foundation

/// A connector that the background refresh scheduler is allowed to drive
/// without a user standing in front of the app.
///
/// The hard rule this protocol exists to enforce: **a background refresh must
/// never raise a macOS consent dialog.** Several connector read paths take a
/// `userInitiated` flag precisely because they can prompt — decrypting another
/// application's Keychain item (browser cookies) and first-touch TCC reads of
/// `~/Downloads`, `~/Documents`, `~/Desktop`, or the Apple Notes group
/// container all surface a system dialog the first time they run. A naive timer
/// that passed `userInitiated: true` would spam the user with permission
/// prompts from a process they are not looking at.
///
/// Eligibility is therefore a **declared property of the connector**, never
/// inferred from its id, and ``ConnectorRefreshPolicy`` treats it as the
/// highest-precedence skip. `supportsUnattendedRefresh` is a `{ get }`
/// requirement rather than a stored constant because at least one connector
/// (local files) is only prompt-free *after* a prior user-initiated scan proved
/// a full grant.
@MainActor
protocol BackgroundRefreshableConnector {
  /// Matches `ImportConnector.id` on the Apps tab: `"calendar"`,
  /// `"apple-notes"`, `"local-files"`. The scheduler joins on this id to read
  /// connected state and write back sync results.
  var connectorID: String { get }

  /// True only when this connector's refresh path is proven to complete with no
  /// macOS consent dialog. Computed, not stored — a grant can be revoked and a
  /// connector can become eligible only after a user-initiated run.
  var supportsUnattendedRefresh: Bool { get }

  /// How stale the connector's data may get before a background refresh is due.
  var refreshInterval: TimeInterval { get }

  /// Performs a raw, idempotent import. Implementations must never run LLM
  /// synthesis — see the raw-import-only rule in this directory's README.
  ///
  /// The progress sink is threaded in rather than manufactured per adapter
  /// because only `ConnectorImportRunner` can build one: its stored properties
  /// are `fileprivate` so a sink can never outlive or be forged outside the run
  /// it belongs to. The scheduler dispatches every refresh through that runner,
  /// so the sink it hands back is the one the connector's import operations
  /// already require. This protocol is `@MainActor`, so the sink never crosses
  /// an isolation boundary.
  func refresh(progress: ConnectorImportRunner.ProgressSink) async -> ConnectorRefreshResult
}

/// Bounded failure classification for a background refresh. Reuses the closed
/// connector telemetry taxonomy so a refresh failure and a user-initiated
/// connect failure are described by exactly one vocabulary.
typealias ConnectorRefreshFailureReason = IntegrationConnectTelemetry.ErrorClass

/// Bounded, privacy-safe counters from one refresh. Never carries content,
/// paths, addresses, or note/event bodies.
struct ConnectorRefreshMetrics: Equatable, Sendable {
  var sourceCount: Int?
  var memoryCount: Int?
  var newItems: Int?

  init(sourceCount: Int? = nil, memoryCount: Int? = nil, newItems: Int? = nil) {
    self.sourceCount = sourceCount
    self.memoryCount = memoryCount
    self.newItems = newItems
  }
}

/// Terminal outcome of one refresh attempt.
///
/// The split between `transientFailure` and `needsUserAction` is the whole
/// retry contract: transient failures back off and retry, user-action failures
/// park the connector immediately and surface UI attention instead of looping
/// against a credential that will not heal on its own.
enum ConnectorRefreshResult: Equatable, Sendable {
  case success(ConnectorRefreshMetrics)
  case transientFailure(reason: ConnectorRefreshFailureReason)
  case needsUserAction(reason: ConnectorRefreshFailureReason)
}
