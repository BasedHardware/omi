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
  }

  private(set) var state: State = .idle
  private(set) var enteredAt: Date?
  private(set) var retryCount = 0
  private(set) var nextRetryAt: Date?
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

  mutating func enter(now: Date) -> Action {
    if enteredAt == nil { enteredAt = now }
    state = .waiting
    let delay = Self.delays[min(retryCount, Self.delays.count - 1)]
    retryCount += 1
    let deadline = now.addingTimeInterval(delay)
    nextRetryAt = deadline
    return .releaseAndWait(until: deadline)
  }

  mutating func signal(_ signal: Signal, now: Date) -> Action {
    guard state == .waiting else { return .none }
    if signal == .backoff, let nextRetryAt, now < nextRetryAt { return .none }
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
  }
}
