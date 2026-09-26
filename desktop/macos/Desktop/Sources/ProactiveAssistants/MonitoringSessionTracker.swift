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
  /// Cumulative time spent in *closed* paused intervals, in seconds. An
  /// interval that is still open lives in `pauseStartedAt`, not here.
  var pausedSeconds: Double
  /// Start of the currently-open paused interval, or nil when not paused.
  ///
  /// Persisted rather than kept in memory because the recovery path needs it:
  /// a crash or quit while the screen is locked must still be able to close
  /// that interval, or lock time is silently promoted to *active* monitoring
  /// time — the exact number this telemetry exists to get right.
  var pauseStartedAt: Date?
  /// Set only by a normal `stopMonitoring()` finish or by
  /// `applicationWillTerminate`'s synchronous quit stamp. Nil means the
  /// session either is still active or the process died before it could stamp
  /// anything.
  ///
  /// Also the liveness flag: `hasActiveSession` is false once this is set, so
  /// a finished session can never be re-persisted or re-stamped.
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

/// What is currently holding monitoring paused.
///
/// Screen lock and system sleep are **independent, overlapping** interruption
/// sources: the standard password-after-sleep laptop path is lock -> sleep ->
/// wake -> unlock, and capture stays down across the whole of it. Tracking
/// them as a set (rather than one boolean, or a depth counter) is what makes
/// the paused interval close when the *last* source clears instead of the
/// first: `handleSystemWake` resumes unconditionally while the screen is still
/// locked, so a first-resume-wins model bills every second between wake and
/// unlock as active monitoring.
///
/// A duplicate pause from the same source is idempotent, and a resume from a
/// source that never paused is a no-op, so a spurious notification can neither
/// double-count an interval nor strand the session paused forever.
enum MonitoringPauseSource: String, CaseIterable, Sendable {
  case screenLock
  case systemSleep
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
  private(set) var pauseSources: Set<MonitoringPauseSource> = []

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
      pauseStartedAt: nil,
      endedAt: nil,
      endReason: nil
    )
  }

  /// Whether `start` has produced a session that hasn't been finished yet.
  ///
  /// Both halves matter. Without the `endedAt` check a session that already
  /// emitted its live `Monitoring Stopped` still looks live, so the next lock,
  /// sleep, heartbeat, or quit stamp re-persists it after `stopMonitoring`
  /// cleared the store — and the next launch recovers it as a *second* stop
  /// event, with a duration running to whenever the app happened to quit.
  var hasActiveSession: Bool { !record.sessionID.isEmpty && record.endedAt == nil }

  /// Whether a paused interval is currently open.
  var isPaused: Bool { !pauseSources.isEmpty }

  /// `heldBy` seeds the interruptions already in force when the session
  /// starts. Monitoring can begin while the screen is locked — a settings
  /// sync, a permission retry, or capture intent restored at launch — and a
  /// session that starts unpaused there counts lock-screen time as active
  /// until something happens to pause it. The matching unlock would otherwise
  /// arrive with no hold to release and do nothing.
  mutating func start(at date: Date, sessionID: String, heldBy: Set<MonitoringPauseSource> = []) {
    record = MonitoringSessionRecord(
      sessionID: sessionID,
      startedAt: date,
      lastHeartbeatAt: date,
      pausedSeconds: 0,
      pauseStartedAt: heldBy.isEmpty ? nil : date,
      endedAt: nil,
      endReason: nil
    )
    pauseSources = heldBy
  }

  /// Opens a paused interval, or joins the open one. Idempotent per source.
  mutating func pause(at date: Date, source: MonitoringPauseSource) {
    guard hasActiveSession else { return }
    let wasPaused = isPaused
    pauseSources.insert(source)
    if !wasPaused {
      record.pauseStartedAt = date
    }
  }

  /// Releases one source. The open interval closes only when the last source
  /// clears — waking to a still-locked screen must not resume the clock.
  mutating func resume(at date: Date, source: MonitoringPauseSource) {
    guard hasActiveSession, pauseSources.remove(source) != nil, !isPaused else { return }
    closeOpenPause(at: date)
  }

  mutating func heartbeat(at date: Date) {
    guard hasActiveSession else { return }
    record.lastHeartbeatAt = date
  }

  /// Ends the session. If it finishes while still paused, the open interval is
  /// closed at `date` first so it is not lost.
  @discardableResult
  mutating func finish(at date: Date, reason: MonitoringStopReason) -> MonitoringSummary {
    closeOpenPause(at: date)
    pauseSources = []

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

  /// The record `applicationWillTerminate` should persist: this session, ended
  /// now, with any open paused interval closed. Returns nil when there is no
  /// live session to stamp, including one that already emitted a live stop.
  ///
  /// Deliberately non-mutating and separate from `finish` — a quit stamp emits
  /// no event (there is no synchronous PostHog flush at terminate time); the
  /// event comes from `MonitoringSessionRecovery` at the next launch.
  func quitStampedRecord(at date: Date) -> MonitoringSessionRecord? {
    guard hasActiveSession else { return nil }
    var stamped = record
    if let pauseStart = stamped.pauseStartedAt {
      stamped.pausedSeconds += max(0, date.timeIntervalSince(pauseStart))
      stamped.pauseStartedAt = nil
    }
    stamped.endedAt = date
    stamped.endReason = MonitoringStopReason.appQuit.rawValue
    return stamped
  }

  private mutating func closeOpenPause(at date: Date) {
    guard let pauseStart = record.pauseStartedAt else { return }
    record.pausedSeconds += max(0, date.timeIntervalSince(pauseStart))
    record.pauseStartedAt = nil
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
    // A session that died while paused (crash or quit with the screen locked)
    // still has an open interval. Closing it at the effective end is what
    // keeps lock time out of `activeSeconds`.
    var pausedSeconds = record.pausedSeconds
    if let pauseStart = record.pauseStartedAt {
      pausedSeconds += max(0, effectiveEndedAt.timeIntervalSince(pauseStart))
    }
    let activeSeconds = max(0, durationSeconds - pausedSeconds)
    let recoveredAfterSeconds = max(0, now.timeIntervalSince(record.lastHeartbeatAt))

    return Outcome(
      sessionID: record.sessionID,
      durationSeconds: durationSeconds,
      activeSeconds: activeSeconds,
      pausedSeconds: pausedSeconds,
      stopReason: stopReason,
      durationSource: durationSource,
      recoveredAfterSeconds: recoveredAfterSeconds
    )
  }
}
