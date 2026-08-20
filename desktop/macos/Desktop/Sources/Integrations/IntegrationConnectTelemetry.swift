import Foundation

/// Closed, privacy-safe telemetry contract for the macOS integration connect
/// lifecycle (Calendar, Gmail, Apple Notes, Local Files, X, and the memory-log
/// connectors surfaced on the Apps tab and during onboarding).
///
/// This closes the macOS half of a gap the Flutter app already covers: Flutter
/// emits `Integration Connect Attempted/Succeeded/Failed`
/// (`app/lib/utils/analytics/analytics_manager.dart`), but the macOS Swift app
/// emitted nothing for any connector connect/import outcome. The event-name
/// strings are mirrored **byte-for-byte** so PostHog can aggregate the connect
/// funnel across iOS/Android/macOS by `integration_name` + build cohort, and
/// the bounded dimensions mirror the proven macOS `Auth Flow *` contract
/// (`AuthService.trackAuthFlowEvent`) — stage, classified failure, duration.
///
/// Payloads are pure value builders carrying **only** bounded dimensions. They
/// never include tokens, cookies, OAuth credentials, email/calendar/note
/// content, account IDs, URL query strings, raw exception text, local file
/// paths, or browser profile names. `error_class` is always a closed-enum value
/// derived from the connector-native failure enum
/// (`GmailFailureClass`/`CalendarFailureClass`/`AppleNotesReaderError.reasonCode`)
/// or `PostHogManager.diagnosticErrorClass` — never a raw `message`/
/// `errorDescription`/`localizedDescription`.
///
/// `platform`, `app_version`, `app_build`, and `update_channel` are attached
/// automatically to every captured event by PostHog super-properties registered
/// once at `PostHogManager.initialize()` (`PostHogManager.swift`). They MUST NOT
/// be re-added to payloads here — doing so would duplicate the Auth Flow helper's
/// now-redundant per-event re-addition.
///
/// Channel discipline: these are product-funnel events routed through
/// `AnalyticsManager` → `PostHogManager.track`. They are DISTINCT from
/// `DesktopDiagnosticsManager.recordFallback` (`desktop_health_event` /
/// `fallback_triggered`), which is reserved for fail-open resilience. A connect
/// MODE change (e.g. OAuth↔cookie) additionally calls `recordFallback`; the two
/// are complementary, not duplicative.
enum IntegrationConnectTelemetry {
  /// PostHog event names. Stable identifiers — do not rename. Cross-platform
  /// PostHog aggregation depends on byte-identical strings with Flutter.
  static let attemptedEventName = "Integration Connect Attempted"
  static let succeededEventName = "Integration Connect Succeeded"
  static let failedEventName = "Integration Connect Failed"

  /// macOS surface that initiated the connect action. Closed set.
  enum Surface: String, CaseIterable {
    /// Apps tab → connector sheet → `ConnectorImportRunner` import run.
    case apps = "apps"
    /// Conversational Second-Brain onboarding "connect what I can see" step.
    case onboarding = "onboarding"
    /// Proactive integration nudge — the user opened an app Omi integrates with
    /// and accepted the offer from the floating-bar card. Keeping this separate
    /// from `apps` is the whole point of the nudge experiment: it is the only
    /// way to tell whether the interruption converts better than the tab.
    case nudge = "nudge"
  }

  /// Bounded failure classification. Closed set: the union of the
  /// connector-native failure enums (`GmailFailureClass` /
  /// `CalendarFailureClass` raw values, `AppleNotesReaderError.reasonCode`) and
  /// `PostHogManager.diagnosticErrorClass` outputs, so one `error_class`
  /// dimension serves every connector. Do not add cases that cannot occur.
  enum ErrorClass: String, CaseIterable {
    case notSignedIn = "not_signed_in"
    case sessionExpired = "session_expired"
    case noBrowser = "no_browser"
    case decryptFailed = "decrypt_failed"
    case configuration = "configuration"
    case storeNotFound = "store_not_found"
    case authorizationDenied = "authorization_denied"
    case network = "network"
    case timeout = "timeout"
    case cancelled = "cancelled"
    /// Memory-log connector parsed successfully but produced no durable output
    /// (e.g. user pasted a partial ChatGPT/Claude response). NOT a connect
    /// failure — a no-op result the UI still surfaces guidance for. Carries a
    /// distinct class so analysts can exclude it from the connect-failure rate.
    case noContent = "no_content"
    case rateLimit = "rate_limit"
    case permission = "permission"
    case authentication = "authentication"
    case conflict = "conflict"
    case invalidResponse = "invalid_response"
    case resourceExhausted = "resource_exhausted"
    case unknown = "unknown"

    /// Fallback for connectors without a native taxonomy: normalize a free-text
    /// error through the shared sanitizer. Never pass a raw message as a
    /// dimension — only this closed value.
    static func fromMessage(_ message: String) -> ErrorClass {
      ErrorClass(rawValue: PostHogManager.diagnosticErrorClass(message)) ?? .unknown
    }

    init(_ gmail: GmailFailureClass) {
      self = ErrorClass(rawValue: gmail.rawValue) ?? .unknown
    }

    init(_ calendar: CalendarFailureClass) {
      self = ErrorClass(rawValue: calendar.rawValue) ?? .unknown
    }
  }

  /// Keys permitted in any emitted payload. Anything else is dropped by the
  /// allow-list filter, so a caller cannot accidentally thread content through
  /// an extra property. Mirrors the content-key denylist discipline in
  /// `DesktopDiagnosticsManager`.
  static let allowedKeys: Set<String> = [
    "integration_name",
    "connector_id",
    "surface",
    "stage",
    "error_class",
    "reconnect_required",
    "duration_bucket",
    "source_count_bucket",
    "memory_count_bucket",
    "was_first_sync",
  ]

  /// Display name matching the Flutter `integration_name` values so PostHog
  /// aggregates the connect funnel across platforms. Falls back to the raw
  /// connector id for any id not yet mapped.
  static func integrationName(forConnectorID connectorID: String) -> String {
    switch connectorID {
    case "calendar": return "Google Calendar"
    case "email", "gmail": return "Gmail"
    case "apple-notes", "applenotes": return "Apple Notes"
    case "local-files", "files": return "Local Files"
    case "x": return "X"
    case "chatgpt": return "ChatGPT"
    case "claude": return "Claude"
    default: return connectorID
    }
  }

  /// True when the failure class means a re-sign-in / re-auth will plausibly
  /// resolve it (vs. a terminal/config problem). Drives the reconnect-required
  /// denominator from a single event stream — no separate event needed.
  static func failureRequiresReconnect(_ errorClass: ErrorClass) -> Bool {
    switch errorClass {
    case .notSignedIn, .sessionExpired, .noBrowser, .decryptFailed, .authentication:
      return true
    case .configuration, .storeNotFound, .authorizationDenied, .network, .timeout,
      .cancelled, .noContent, .rateLimit, .permission, .conflict, .invalidResponse,
      .resourceExhausted, .unknown:
      return false
    }
  }

  /// Buckets a raw millisecond duration into closed ranges so the raw value
  /// never reaches PostHog. Negative values clamp to the fastest bucket.
  static func durationBucket(_ ms: Int) -> String {
    let clamped = max(ms, 0)
    switch clamped {
    case 0..<1_000: return "0_1s"
    case 1_000..<3_000: return "1_3s"
    case 3_000..<10_000: return "3_10s"
    case 10_000..<30_000: return "10_30s"
    case 30_000..<60_000: return "30_60s"
    default: return "60s_plus"
    }
  }

  /// Buckets a raw item count into closed ranges so a per-import volume signal
  /// is available without emitting exact counts (which could be a faint
  /// content proxy at the edges).
  static func countBucket(_ count: Int) -> String {
    switch max(count, 0) {
    case 0: return "0"
    case 1..<11: return "1_10"
    case 11..<51: return "11_50"
    case 51..<201: return "51_200"
    case 201..<501: return "201_500"
    default: return "500_plus"
    }
  }

  // MARK: - Payload builders (closed schema + allow-list filter)

  /// `Integration Connect Attempted` payload. Emitted once per user-initiated
  /// connect action, at the authoritative start boundary.
  static func attemptedPayload(
    integrationName: String,
    connectorID: String,
    surface: Surface,
    stage: String
  ) -> [String: Any] {
    allowListOnly([
      "integration_name": integrationName,
      "connector_id": connectorID,
      "surface": surface.rawValue,
      "stage": stage,
    ])
  }

  /// `Integration Connect Succeeded` payload. Emitted once at the terminal
  /// success boundary. `durationMs`/counts are optional; omitted keys are not
  /// emitted (closed schema stays exact per event).
  static func succeededPayload(
    integrationName: String,
    connectorID: String,
    surface: Surface,
    stage: String,
    durationMs: Int? = nil,
    sourceCount: Int? = nil,
    memoryCount: Int? = nil,
    wasFirstSync: Bool = false
  ) -> [String: Any] {
    var payload: [String: Any] = [
      "integration_name": integrationName,
      "connector_id": connectorID,
      "surface": surface.rawValue,
      "stage": stage,
      "was_first_sync": wasFirstSync,
    ]
    if let durationMs { payload["duration_bucket"] = durationBucket(durationMs) }
    if let sourceCount { payload["source_count_bucket"] = countBucket(sourceCount) }
    if let memoryCount { payload["memory_count_bucket"] = countBucket(memoryCount) }
    return allowListOnly(payload)
  }

  /// `Integration Connect Failed` payload. Emitted once at the terminal failure
  /// boundary. `error_class` is always a closed value; `reconnect_required` is
  /// derived from it so analysts can separate reauth-needed users from
  /// terminal/config failures without a second event.
  static func failedPayload(
    integrationName: String,
    connectorID: String,
    surface: Surface,
    stage: String,
    errorClass: ErrorClass,
    durationMs: Int? = nil,
    wasFirstSync: Bool = false
  ) -> [String: Any] {
    var payload: [String: Any] = [
      "integration_name": integrationName,
      "connector_id": connectorID,
      "surface": surface.rawValue,
      "stage": stage,
      "error_class": errorClass.rawValue,
      "reconnect_required": failureRequiresReconnect(errorClass),
      "was_first_sync": wasFirstSync,
    ]
    if let durationMs { payload["duration_bucket"] = durationBucket(durationMs) }
    return allowListOnly(payload)
  }

  /// Drops any key not in `allowedKeys`. Defense-in-depth so a future caller
  /// threading an extra property cannot leak it to PostHog.
  private static func allowListOnly(_ properties: [String: Any]) -> [String: Any] {
    properties.filter { allowedKeys.contains($0.key) }
  }
}
