import Foundation

/// Durable snapshot of one monitoring session's timeline. Persisted as JSON
/// (see `MonitoringSessionStore`) so a crash or quit can be recovered at the
/// next launch instead of silently losing the whole session — see
/// `MonitoringSessionRecovery`.
struct MonitoringSessionRecord: Codable, Equatable {
  var sessionID: String
  var startedAt: Date
  /// Refreshed by the 60s heartbeat timer (and by every pause/resume) while
  /// the process is alive. On a crash recovery this is the only evidence of
  /// how long the session ran.
  var lastHeartbeatAt: Date
  /// Cumulative time spent paused (system sleep, screen lock), in seconds.
  var pausedSeconds: Double
  /// Set only by a normal `stopMonitoring()` finish or by
  /// `applicationWillTerminate`'s synchronous quit stamp. Nil means the
  /// session either is still active or the process died before it could stamp
  /// anything.
  var endedAt: Date?
  /// Raw `MonitoringStopReason` value. String (not the enum) because this
  /// crosses a Codable/UserDefaults boundary that must tolerate an unknown
  /// future case without failing to decode.
  var endReason: String?
}

/// Closed set of reasons a monitoring session ended. Emitted verbatim as
/// `stop_reason` on `Monitoring Stopped`.
///
/// `.userToggle` is the default so every ordinary UI stop (sidebar toggle,
/// settings switch, floating-bar control) keeps compiling without a call-site
/// change. `.appQuit` and `.sessionLost` are never passed to
/// `stopMonitoring(reason:)` directly — they are produced only by the
/// recovery path (`MonitoringSessionRecovery`): `.appQuit` when
/// `applicationWillTerminate` managed to stamp `endedAt` before the process
/// died, `.sessionLost` when it did not (hard crash) and the last heartbeat is
/// all that is left.
public enum MonitoringStopReason: String, CaseIterable, Sendable {
  case userToggle = "user_toggle"
  case signOut = "sign_out"
  case accountDeleted = "account_deleted"
  case paywall = "paywall"
  case permissionRevoked = "permission_revoked"
  case captureConsentDeclined = "capture_consent_declined"
  case recoveryExhausted = "recovery_exhausted"
  case settingsSync = "settings_sync"
  case appQuit = "app_quit"
  case sessionLost = "session_lost"
}

/// Closed set describing how trustworthy an emitted duration is.
///
/// `.wallClock` is the normal live-stop case. `.clockAnomaly` fires when the
/// system clock moved backwards mid-session (NTP correction, manual clock
/// change) and the raw end-minus-start would otherwise be negative — the
/// duration is clamped to 0 rather than emitting a negative number.
/// `.recoveredClean` / `.recoveredHeartbeat` are recovery-only, see
/// `MonitoringSessionRecovery`.
enum MonitoringDurationSource: String, CaseIterable, Sendable {
  case wallClock = "wall_clock"
  case clockAnomaly = "clock_anomaly"
  case recoveredClean = "recovered_clean"
  case recoveredHeartbeat = "recovered_heartbeat"
}

/// A live monitoring session's outcome at the moment `stopMonitoring()`
/// finishes it. Durations are unrounded seconds — round to whole seconds only
/// when building an analytics payload (`MonitoringTelemetry`), never here.
struct MonitoringSummary: Equatable {
  let sessionID: String
  let durationSeconds: Double
  let pausedSeconds: Double
  /// `durationSeconds - pausedSeconds`, floored at 0.
  let activeSeconds: Double
  let stopReason: MonitoringStopReason
  let durationSource: MonitoringDurationSource
}

/// Pure, deterministic tracker for one monitoring session's timeline. No
/// singletons, no timers, no PostHog — every method takes the current time as
/// an explicit `Date` so tests can drive it without depending on the wall
/// clock. `ProactiveAssistantsPlugin` owns exactly one instance across its
/// lifetime and calls `start` again for each new session.
struct MonitoringSessionTracker: Equatable {
  private(set) var record: MonitoringSessionRecord
  private var isPaused = false
  private var currentPauseStartedAt: Date?

  /// Not-yet-started placeholder — `sessionID` is empty until `start` is
  /// called. `pause`/`resume`/`heartbeat` are no-ops against it, and `finish`
  /// returns a zero-duration summary; none of that should ever be reachable
  /// in production since the plugin only calls those once `isMonitoring` is
  /// true, which is only ever set right after `start`.
  init() {
    record = MonitoringSessionRecord(
      sessionID: "",
      startedAt: .distantPast,
      lastHeartbeatAt: .distantPast,
      pausedSeconds: 0,
      endedAt: nil,
      endReason: nil
    )
  }

  /// Whether `start` has produced a session that hasn't been `finish`ed yet.
  var hasActiveSession: Bool { !record.sessionID.isEmpty }

  mutating func start(at date: Date, sessionID: String) {
    record = MonitoringSessionRecord(
      sessionID: sessionID,
      startedAt: date,
      lastHeartbeatAt: date,
      pausedSeconds: 0,
      endedAt: nil,
      endReason: nil
    )
    isPaused = false
    currentPauseStartedAt = nil
  }

  /// Sleep and screen-lock are independent interruption sources that can
  /// overlap (the machine can lock, then sleep, then wake, then unlock), and
  /// this method takes no argument identifying which source is calling — so
  /// there is no way to tell "a second, genuinely different source paused
  /// too" apart from "the same source fired a redundant/duplicate
  /// notification". An explicit is-paused guard (rather than a depth counter)
  /// resolves that ambiguity in the safe direction: a `pause` while already
  /// paused is unconditionally a no-op, so a spurious duplicate notification
  /// can never leave the session stuck paused waiting for a `resume` that
  /// will never come. The trade-off is that in the overlap case the interval
  /// closes at the *first* `resume` (whichever source calls it first), not
  /// necessarily when every overlapping interruption has cleared — still
  /// exactly one closed interval, never two, which is the correctness
  /// property that matters for duration accounting.
  mutating func pause(at date: Date) {
    guard hasActiveSession, !isPaused else { return }
    isPaused = true
    currentPauseStartedAt = date
  }

  /// A `resume` while not paused is a no-op.
  mutating func resume(at date: Date) {
    guard hasActiveSession, isPaused else { return }
    isPaused = false
    if let pauseStart = currentPauseStartedAt {
      record.pausedSeconds += max(0, date.timeIntervalSince(pauseStart))
      currentPauseStartedAt = nil
    }
  }

  mutating func heartbeat(at date: Date) {
    guard hasActiveSession else { return }
    record.lastHeartbeatAt = date
  }

  /// Ends the session. If it finishes while still paused (no matching
  /// `resume`), the open paused interval is closed at `date` first so it is
  /// not lost.
  @discardableResult
  mutating func finish(at date: Date, reason: MonitoringStopReason) -> MonitoringSummary {
    if isPaused, let pauseStart = currentPauseStartedAt {
      record.pausedSeconds += max(0, date.timeIntervalSince(pauseStart))
    }
    isPaused = false
    currentPauseStartedAt = nil

    record.endedAt = date
    record.endReason = reason.rawValue

    let rawDuration = date.timeIntervalSince(record.startedAt)
    let durationSeconds: Double
    let durationSource: MonitoringDurationSource
    if rawDuration < 0 {
      durationSeconds = 0
      durationSource = .clockAnomaly
    } else {
      durationSeconds = rawDuration
      durationSource = .wallClock
    }
    let activeSeconds = max(0, durationSeconds - record.pausedSeconds)

    return MonitoringSummary(
      sessionID: record.sessionID,
      durationSeconds: durationSeconds,
      pausedSeconds: record.pausedSeconds,
      activeSeconds: activeSeconds,
      stopReason: reason,
      durationSource: durationSource
    )
  }
}

/// Recovers a persisted `MonitoringSessionRecord` found at next launch — the
/// session never got to emit a live `Monitoring Stopped`, either because the
/// app quit normally (`endedAt` was stamped synchronously by
/// `applicationWillTerminate`, but there is no synchronous PostHog flush at
/// terminate time) or because it crashed outright (`endedAt` is nil; the last
/// heartbeat is the only evidence it was ever alive).
///
/// Pure and deterministic like `MonitoringSessionTracker` — `now` is passed
/// in explicitly.
enum MonitoringSessionRecovery {
  struct Outcome: Equatable {
    let sessionID: String
    let durationSeconds: Double
    let activeSeconds: Double
    let pausedSeconds: Double
    let stopReason: MonitoringStopReason
    let durationSource: MonitoringDurationSource
    /// `now - lastHeartbeatAt` — how stale the recovered record was, so an
    /// analyst can see how much to trust it.
    let recoveredAfterSeconds: Double
  }

  static func recover(_ record: MonitoringSessionRecord, now: Date) -> Outcome {
    let stopReason: MonitoringStopReason
    let durationSource: MonitoringDurationSource
    let effectiveEndedAt: Date
    if let endedAt = record.endedAt {
      effectiveEndedAt = endedAt
      stopReason = record.endReason.flatMap(MonitoringStopReason.init(rawValue:)) ?? .appQuit
      durationSource = .recoveredClean
    } else {
      effectiveEndedAt = record.lastHeartbeatAt
      stopReason = .sessionLost
      durationSource = .recoveredHeartbeat
    }

    let durationSeconds = max(0, effectiveEndedAt.timeIntervalSince(record.startedAt))
    let activeSeconds = max(0, durationSeconds - record.pausedSeconds)
    let recoveredAfterSeconds = max(0, now.timeIntervalSince(record.lastHeartbeatAt))

    return Outcome(
      sessionID: record.sessionID,
      durationSeconds: durationSeconds,
      activeSeconds: activeSeconds,
      pausedSeconds: record.pausedSeconds,
      stopReason: stopReason,
      durationSource: durationSource,
      recoveredAfterSeconds: recoveredAfterSeconds
    )
  }
}
