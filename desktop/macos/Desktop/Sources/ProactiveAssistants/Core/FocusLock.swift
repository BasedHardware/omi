import Foundation

/// A session-only identity for the source the user chose to keep in focus. A missing
/// title deliberately means app-wide focus; it must not match another app.
struct FocusLockSource: Equatable, Sendable {
  let appName: String
  let normalizedTitle: String?
  let displayTitle: String?

  init?(appName: String, windowTitle: String?) {
    let app = appName.trimmingCharacters(in: .whitespacesAndNewlines)
    guard !app.isEmpty else { return nil }
    let title = windowTitle?.trimmingCharacters(in: .whitespacesAndNewlines)
    let normalized = ContextDetection.normalizeWindowTitle(title, appName: app)
    // A title made only of progress/timer decoration is not an app-wide pin.
    guard title?.isEmpty != false || normalized != nil else { return nil }
    self.appName = app
    normalizedTitle = normalized
    displayTitle = title?.isEmpty == false ? title : nil
  }

  var displayName: String {
    guard let displayTitle else { return appName }
    return "\(appName) — \(displayTitle.prefix(48))"
  }

  func matches(appName: String, windowTitle: String?) -> Bool {
    guard self.appName == appName else { return false }
    guard let normalizedTitle else { return true }
    return normalizedTitle == ContextDetection.normalizeWindowTitle(windowTitle, appName: appName)
  }

  func matches(_ event: TaskLocalContextEvent) -> Bool {
    guard event.kind == .appWindow else { return false }
    // App-wide locks compare the separately hashed app identity, never the title.
    if normalizedTitle == nil {
      return TaskLocalContextEvent.appWindow(appName: appName, windowTitle: nil)?
        .appReferenceHash == event.appReferenceHash && event.appReferenceHash != nil
    }
    return TaskLocalContextEvent.appWindow(appName: appName, windowTitle: normalizedTitle)?
      .referenceHash == event.referenceHash
  }
}

struct FocusLockSession: Equatable, Sendable {
  let source: FocusLockSource
  let expiresAt: Date
  let durationMinutes: Int

  func isActive(at now: Date) -> Bool { now < expiresAt }
}

enum FocusLockReleaseReason: String, Sendable {
  case manual, expired, replaced
  case sourceTerminated = "source_terminated"
  case ownerChanged = "owner_changed"
  case monitoringStopped = "monitoring_stopped"
  case privacyExcluded = "privacy_excluded"
  case appQuit = "app_quit"
}

/// Fixed vocabulary only: app names and window titles never enter telemetry.
struct FocusLockTelemetryEvent: Equatable, Sendable {
  enum Kind: Equatable, Sendable { case started, ended }
  let kind: Kind
  let durationMinutes: Int
  let reason: FocusLockReleaseReason?

  var eventName: String {
    kind == .started ? "Desktop Focus Lock Started" : "Desktop Focus Lock Ended"
  }

  var properties: [String: Any] {
    var payload: [String: Any] = [
      "source_class": "app_window", "duration_minutes": durationMinutes,
    ]
    if let reason { payload["release_reason"] = reason.rawValue }
    return payload
  }
}

extension AnalyticsManager {
  func focusLockEvent(_ event: FocusLockTelemetryEvent) {
    PostHogManager.shared.track(event.eventName, properties: event.properties)
  }
}

/// Thread-safe admission shared by actor-based assistant work and synchronous
/// ScreenTaskWorkAuthority validators. Never persists titles or emits content telemetry.
final class FocusLockController: @unchecked Sendable {
  static let shared = FocusLockController()

  private let isExcluded: @Sendable (String) -> Bool
  private let lock = NSLock()
  private var session: FocusLockSession?
  private var generation: UInt64 = 0
  private var telemetryEvents: [FocusLockTelemetryEvent] = []

  init(isExcluded: @escaping @Sendable (String) -> Bool = { RewindCaptureExclusionGeneration.isExcluded($0) }) {
    self.isExcluded = isExcluded
  }

  func snapshot(now: Date = Date()) -> FocusLockSession? {
    lock.lock()
    defer { lock.unlock() }
    expireLocked(now: now)
    return session
  }

  func revision(now: Date = Date()) -> UInt64 {
    lock.lock()
    defer { lock.unlock() }
    expireLocked(now: now)
    return generation
  }

  @discardableResult
  func activate(source: FocusLockSource, duration: TimeInterval, now: Date = Date()) -> FocusLockSession? {
    guard [15.0 * 60, 30.0 * 60, 60.0 * 60].contains(duration) else { return nil }
    let next = FocusLockSession(
      source: source, expiresAt: now.addingTimeInterval(duration), durationMinutes: Int(duration / 60))
    lock.lock()
    expireLocked(now: now)
    guard !isExcluded(source.appName) else {
      lock.unlock()
      return nil
    }
    if let session {
      telemetryEvents.append(
        FocusLockTelemetryEvent(
          kind: .ended, durationMinutes: session.durationMinutes, reason: .replaced))
    }
    session = next
    generation &+= 1
    telemetryEvents.append(
      FocusLockTelemetryEvent(
        kind: .started, durationMinutes: next.durationMinutes, reason: nil))
    lock.unlock()
    return next
  }

  @discardableResult
  func release(reason: FocusLockReleaseReason = .manual, now: Date = Date()) -> Bool {
    lock.lock()
    defer { lock.unlock() }
    expireLocked(now: now)
    guard let session else { return false }
    telemetryEvents.append(
      FocusLockTelemetryEvent(
        kind: .ended, durationMinutes: session.durationMinutes, reason: reason))
    self.session = nil
    generation &+= 1
    return true
  }

  @discardableResult
  func releaseIfAppTerminated(_ appName: String) -> Bool {
    lock.lock()
    defer { lock.unlock() }
    expireLocked(now: Date())
    guard let session, session.source.appName == appName else { return false }
    telemetryEvents.append(
      FocusLockTelemetryEvent(
        kind: .ended, durationMinutes: session.durationMinutes, reason: .sourceTerminated))
    self.session = nil
    generation &+= 1
    return true
  }

  func allows(appName: String, windowTitle: String?, now: Date = Date()) -> Bool {
    guard let session = snapshot(now: now) else { return true }
    return session.source.matches(appName: appName, windowTitle: windowTitle)
  }

  /// Durable retries keep the admission they had when the attempt began.
  func allowsQueuedDelivery(appName: String, windowTitle: String?, revision expectedRevision: UInt64) -> Bool {
    lock.lock()
    defer { lock.unlock() }
    expireLocked(now: Date())
    guard generation == expectedRevision else { return false }
    return session?.source.matches(appName: appName, windowTitle: windowTitle) ?? true
  }

  /// Memory extraction may continue for unrelated frames, but a visible event
  /// must be tied to its trusted captured source, never the model's source label.
  func allowsCapturedResult(appName: String?, windowTitle: String?, revision capturedRevision: UInt64?) -> Bool {
    lock.lock()
    defer { lock.unlock() }
    expireLocked(now: Date())
    if let capturedRevision {
      guard generation == capturedRevision else { return false }
    } else if session != nil {
      return false
    }
    return session?.source.matches(appName: appName ?? "", windowTitle: windowTitle) ?? true
  }

  func allows(_ event: TaskLocalContextEvent, now: Date = Date()) -> Bool {
    guard let session = snapshot(now: now) else { return true }
    return session.source.matches(event)
  }

  func allows(_ event: TaskLocalContextEvent, revision expectedRevision: UInt64, now: Date = Date()) -> Bool {
    lock.lock()
    defer { lock.unlock() }
    expireLocked(now: now)
    guard generation == expectedRevision else { return false }
    return session?.source.matches(event) ?? true
  }

  func takeTelemetryEvents() -> [FocusLockTelemetryEvent] {
    lock.lock()
    defer { lock.unlock() }
    let events = telemetryEvents
    telemetryEvents.removeAll(keepingCapacity: true)
    return events
  }

  private func expireLocked(now: Date) {
    if let session,
      !session.isActive(at: now) || isExcluded(session.source.appName)
    {
      let reason: FocusLockReleaseReason = session.isActive(at: now) ? .privacyExcluded : .expired
      telemetryEvents.append(
        FocusLockTelemetryEvent(
          kind: .ended, durationMinutes: session.durationMinutes, reason: reason))
      self.session = nil
      generation &+= 1
    }
  }
}
