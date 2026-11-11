import VoiceTurnDomain
import XCTest

@testable import Omi_Computer

/// Push-to-talk is now reachable by clicking a mic button in the chat composer
/// and the floating ask bar, not only by holding the shortcut. A click carries
/// no "hold", so it maps onto the hands-free lane the double-tap shortcut
/// already drives. These pin that mapping against the real reducer, plus the
/// blocked path, so the button can never grow a second capture lifecycle.
@MainActor
final class PushToTalkButtonTriggerTests: XCTestCase {

  // MARK: - Core path

  func testClickStartsHandsFreeListeningAndTheNextClickCommitsTheSameTurn() {
    let coordinator = VoiceTurnCoordinator(scheduler: ManualPushToTalkButtonScheduler())

    // Idle composer: the click opens a hands-free turn rather than a held one.
    XCTAssertEqual(
      PushToTalkManager.clickAction(phase: coordinator.activeTurn?.phase),
      .beginHandsFree)
    XCTAssertEqual(
      PushToTalkManager.buttonState(
        phase: coordinator.activeTurn?.phase, isUsageLimitBlocked: false),
      .idle)

    let turnID = coordinator.begin(intent: .locked)
    XCTAssertEqual(
      coordinator.activeTurn?.phase,
      .lockedRecording,
      "A click must land in the same locked phase a double-tap does, not a hold.")
    XCTAssertTrue(coordinator.projection.isListening)
    XCTAssertTrue(coordinator.projection.isLocked)
    XCTAssertEqual(
      PushToTalkManager.buttonState(
        phase: coordinator.activeTurn?.phase, isUsageLimitBlocked: false),
      .listening)

    // Second click commits the very same turn — no second turn is opened.
    XCTAssertEqual(
      PushToTalkManager.clickAction(phase: coordinator.activeTurn?.phase),
      .finalize)
    coordinator.publish(.finalize(turnID: turnID))
    XCTAssertEqual(coordinator.activeTurn?.id, turnID)
    XCTAssertEqual(coordinator.activeTurn?.phase, .finalizing)
    XCTAssertFalse(coordinator.projection.isListening)

    // A click while the turn is committing must neither restart nor re-commit.
    XCTAssertEqual(
      PushToTalkManager.clickAction(phase: coordinator.activeTurn?.phase),
      .ignore)
    XCTAssertEqual(
      PushToTalkManager.buttonState(
        phase: coordinator.activeTurn?.phase, isUsageLimitBlocked: false),
      .committing)
    XCTAssertEqual(
      coordinator.model.invalidTransitionCount,
      0,
      "The click mapping must only publish transitions the reducer accepts.")
  }

  /// A click is far more likely than a double-tap to land while a previous
  /// answer is still in flight (the mic button sits in the composer the user is
  /// already looking at). `.lock` is not a valid transition out of a response
  /// phase, so the manager must supersede that turn instead.
  func testClickDuringAnInFlightResponseSupersedesInsteadOfLockingIt() {
    let coordinator = VoiceTurnCoordinator(scheduler: ManualPushToTalkButtonScheduler())
    let answering = coordinator.begin(intent: .hold)
    coordinator.publish(.selectRoute(turnID: answering, route: .hub(sessionID: VoiceSessionID())))
    coordinator.publish(.finalize(turnID: answering))
    coordinator.publish(.hubCommitDeferred(turnID: answering))
    XCTAssertEqual(coordinator.activeTurn?.phase, .awaitingResponse)

    XCTAssertEqual(
      PushToTalkManager.clickAction(phase: coordinator.activeTurn?.phase),
      .beginHandsFree)
    XCTAssertFalse(
      PushToTalkManager.locksExistingTurn(phase: coordinator.activeTurn?.phase),
      "A responding turn is not lockable.")

    // Prove the reducer agrees: locking it would be an invalid transition that
    // leaves the manager capturing audio for a turn that never started recording.
    coordinator.publish(.lock(turnID: answering))
    XCTAssertEqual(coordinator.model.invalidTransitionCount, 1)
    XCTAssertEqual(coordinator.activeTurn?.phase, .awaitingResponse)

    // The path the manager actually takes: a fresh locked turn that barges in.
    let bargedIn = coordinator.begin(intent: .locked)
    XCTAssertNotEqual(bargedIn, answering)
    XCTAssertEqual(coordinator.activeTurn?.id, bargedIn)
    XCTAssertEqual(coordinator.activeTurn?.phase, .lockedRecording)
    XCTAssertEqual(coordinator.model.lastTerminal?.turnID, answering)
    XCTAssertEqual(coordinator.model.lastTerminal?.reason, .interruptedByBargeIn)
  }

  /// The one place a still-capturing turn is locked in place rather than
  /// superseded: the hotkey's tap-to-lock window.
  func testOnlyACapturingTurnIsLockedInPlace() {
    XCTAssertTrue(PushToTalkManager.locksExistingTurn(phase: .recording))
    XCTAssertTrue(PushToTalkManager.locksExistingTurn(phase: .pendingLockDecision))
    let superseded: [VoiceTurnPhase?] = [
      .lockedRecording, .finalizing, .awaitingResponse, .awaitingTools, .awaitingJournal,
      .playing(.nativeRealtime), .idle, nil,
    ]
    for phase in superseded {
      XCTAssertFalse(
        PushToTalkManager.locksExistingTurn(phase: phase),
        "\(String(describing: phase)) must be superseded, not locked.")
    }
  }

  // MARK: - Error path

  /// A blocked click must take the same usage-limit popup path the hotkey does.
  /// The button therefore stays clickable while blocked — a disabled button
  /// would swallow the click and the user would get silence instead of the
  /// upgrade prompt.
  func testBlockedClickSurfacesTheUsageLimitPopupAndOpensNoTurn() throws {
    try XCTSkipIf(APIKeyService.isByokActive, "BYOK users are never usage-limited")

    let manager = PushToTalkManager.shared
    VoiceTurnCoordinator.shared.reset()
    XCTAssertNil(manager.phase, "This test requires an idle push-to-talk manager.")

    let limiter = FloatingBarUsageLimiter.shared
    defer { limiter.reset() }
    limiter.applyQuota(try exhaustedFreeQuota())

    XCTAssertTrue(manager.isPushToTalkUsageLimitBlocked)
    XCTAssertEqual(manager.pushToTalkButtonState, .blocked)

    // The popup is posted synchronously by the gate, so no waiting is involved.
    let reasons = PostedUsageLimitReasons()
    let observer = NotificationCenter.default.addObserver(
      forName: .showUsageLimitPopup, object: nil, queue: nil
    ) { note in
      reasons.append(note.userInfo?["reason"] as? String ?? "")
    }
    defer { NotificationCenter.default.removeObserver(observer) }

    manager.togglePushToTalkFromButton()

    XCTAssertEqual(
      reasons.snapshot(),
      ["ptt"],
      "A blocked click must surface the same usage-limit popup the shortcut does.")
    XCTAssertNil(manager.phase, "A blocked click must not open a capture turn.")
  }

  // MARK: - Helpers

  private func exhaustedFreeQuota() throws -> APIClient.ChatUsageQuota {
    let json: [String: Any] = [
      "plan": "Free",
      "plan_type": "basic",
      "unit": "questions",
      "used": 30.0,
      "limit": 30.0,
      "percent": 100.0,
      "allowed": false,
    ]
    let data = try JSONSerialization.data(withJSONObject: json)
    return try JSONDecoder().decode(APIClient.ChatUsageQuota.self, from: data)
  }
}

/// Lock-guarded accumulator so the `@Sendable` notification observer can record
/// what it saw without capturing mutable test state.
private final class PostedUsageLimitReasons: @unchecked Sendable {
  private let lock = NSLock()
  private var reasons: [String] = []

  func append(_ reason: String) {
    lock.lock()
    reasons.append(reason)
    lock.unlock()
  }

  func snapshot() -> [String] {
    lock.lock()
    defer { lock.unlock() }
    return reasons
  }
}

/// Deadlines are irrelevant to the click mapping; holding them inert keeps
/// these tests free of wall-clock waits.
@MainActor
private final class ManualPushToTalkButtonScheduler: VoiceTurnDeadlineScheduling {
  private final class Cancellation: VoiceTurnDeadlineCancellation {
    func cancel() {}
  }

  func schedule(
    deadline: VoiceTurnDeadline,
    after interval: TimeInterval,
    action: @escaping @MainActor () -> Void
  ) -> VoiceTurnDeadlineCancellation {
    _ = (deadline, interval, action)
    return Cancellation()
  }
}
