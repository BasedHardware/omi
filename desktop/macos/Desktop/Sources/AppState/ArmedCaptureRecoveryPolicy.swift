import Foundation

/// Decisions for an automatic microphone start whose route is temporarily silent.
/// The caller supplies time and signals; this type owns no timer, audio, or STT resource.
struct ArmedCaptureRecoveryPolicy {
  enum State: Equatable { case idle, waiting, probing }
  enum Signal: String {
    case unlock, screenWake, systemWake, sessionActive, inputChanged, displayChanged, appActive, backoff
  }
  enum Action: Equatable {
    case none
    case releaseAndWait(until: Date)
    case probe
    case retrySkipped(reason: PresenceReason, until: Date)
  }
  enum PresenceReason: String {
    case consoleInactive = "console_inactive"
    case screenLocked = "screen_locked"
    case displaysAsleep = "displays_asleep"
    case lidClosedBuiltIn = "lid_closed_built_in"
    case unknown
  }

  private(set) var state: State = .idle
  private(set) var enteredAt: Date?
  private(set) var retryCount = 0
  private(set) var nextRetryAt: Date?
  private var skippedBackoffIndex = 0
  private static let delays: [TimeInterval] = [30, 60, 120, 300, 600]

  static func canEnterWaiting(captureActive: Bool, sttActive: Bool) -> Bool {
    !captureActive && !sttActive
  }

  static func shouldDeferStart(transitionInFlight: Bool, userInitiated: Bool) -> Bool {
    transitionInFlight && !userInitiated
  }

  static func shouldWaitForUpdateRelaunch(
    isUpdateRelaunch: Bool, consoleActive: Bool?, screenLocked: Bool?, displaysAsleep: Bool?
  ) -> Bool {
    guard isUpdateRelaunch else { return false }
    // An unknown presence fact is not proof that a newly replaced binary should open the mic.
    return consoleActive != true || screenLocked != false || displaysAsleep != false
  }

  static func unavailablePresenceReason(_ presence: CapturePresence, inputIsBuiltIn: Bool?) -> PresenceReason? {
    if presence.consoleSessionActive == false { return .consoleInactive }
    if presence.screenLocked == true { return .screenLocked }
    if presence.displaysAsleep == true { return .displaysAsleep }
    if presence.lidClosed == true, inputIsBuiltIn == true { return .lidClosedBuiltIn }
    if presence.consoleSessionActive == nil || presence.screenLocked == nil || presence.displaysAsleep == nil
      || (presence.lidClosed == true && inputIsBuiltIn == nil)
    {
      return .unknown
    }
    return nil
  }

  mutating func enter(now: Date) -> Action {
    if enteredAt == nil { enteredAt = now }
    state = .waiting
    let delay = Self.delays[min(retryCount, Self.delays.count - 1)]
    retryCount += 1
    let deadline = now.addingTimeInterval(delay)
    nextRetryAt = deadline
    return .releaseAndWait(until: deadline)
  }

  mutating func signal(_ signal: Signal, now: Date, presence: CapturePresence, inputIsBuiltIn: Bool?) -> Action {
    guard state == .waiting else { return .none }
    if signal == .backoff, let nextRetryAt, now < nextRetryAt { return .none }
    if let reason = Self.unavailablePresenceReason(presence, inputIsBuiltIn: inputIsBuiltIn) {
      if signal == .backoff {
        // An absent or unknown user must not open the mic on a timer. Rechecks
        // escalate independently of probe retries, without consuming retryCount.
        // Non-timer signals may probe on unknown facts so a Mac whose presence
        // APIs never answer still has a path to recovery.
        let delay = Self.delays[min(skippedBackoffIndex, Self.delays.count - 1)]
        skippedBackoffIndex = min(skippedBackoffIndex + 1, Self.delays.count - 1)
        let deadline = now.addingTimeInterval(delay)
        nextRetryAt = deadline
        return .retrySkipped(reason: reason, until: deadline)
      }
      if reason != .unknown { return .none }
    }
    // A usable presence sample (or a non-timer recovery event with unknown
    // presence) ends the unavailable streak; future skips start at 30 seconds.
    skippedBackoffIndex = 0
    state = .probing
    nextRetryAt = nil
    return .probe
  }

  mutating func succeeded(now: Date) -> TimeInterval? {
    guard state == .probing else { return nil }
    let duration = enteredAt.map { max(0, now.timeIntervalSince($0)) }
    reset()
    return duration
  }

  mutating func reset() {
    state = .idle
    enteredAt = nil
    retryCount = 0
    nextRetryAt = nil
    skippedBackoffIndex = 0
  }
}

/// Bounds and deduplicates retry_skipped telemetry independently from the
/// entered/retry lifecycle event budget.
struct ArmedLifecycleEventPolicy {
  private(set) var lastReason: ArmedCaptureRecoveryPolicy.PresenceReason?
  private var hourStart: Date?
  private var lifecycleHourlyCount = 0
  private var skipHourlyCount = 0
  private let lifecycleHourlyLimit = 24
  private let skipHourlyLimit = 4

  mutating func shouldEmit(
    phase: String, presenceReason: ArmedCaptureRecoveryPolicy.PresenceReason? = nil, now: Date
  ) -> Bool {
    if let hourStart, now.timeIntervalSince(hourStart) >= 3_600 {
      self.hourStart = now
      lifecycleHourlyCount = 0
      skipHourlyCount = 0
    } else if hourStart == nil {
      hourStart = now
    }
    switch phase {
    case "entered", "retry":
      guard lifecycleHourlyCount < lifecycleHourlyLimit else { return false }
      lifecycleHourlyCount += 1
      return true
    case "retry_skipped":
      guard let presenceReason else { return false }
      let changed = lastReason != presenceReason
      lastReason = presenceReason
      guard changed, skipHourlyCount < skipHourlyLimit else { return false }
      skipHourlyCount += 1
      return true
    default:
      return true
    }
  }

  mutating func presenceReturned() {
    lastReason = nil
  }
}
