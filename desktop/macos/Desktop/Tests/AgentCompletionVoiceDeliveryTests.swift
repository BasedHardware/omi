import XCTest

@testable import Omi_Computer

/// Behavioral coverage for the voice completion-delivery dispatcher: completed
/// background-agent runs must reach a live voice session exactly once, and the
/// kernel checkpoint must advance only after the session confirmed the send.
@MainActor
final class AgentCompletionVoiceDeliveryTests: XCTestCase {

  @MainActor
  private final class Harness {
    var voiceLive = true
    var delta: AgentCompletionVoiceDelivery.Delta? = AgentCompletionVoiceDelivery.Delta(
      ids: ["run-1"], prompt: "agent finished", completedAtHighWaterMs: 42)
    var injectResult = true

    private(set) var peekCount = 0
    private(set) var injectedPrompts: [String] = []
    private(set) var acknowledged: [[String]] = []
    private(set) var scheduled: [@MainActor () async -> Void] = []

    lazy var sut = AgentCompletionVoiceDelivery(
      isVoiceSessionLive: { [unowned self] in self.voiceLive },
      peekDelta: { [unowned self] in
        self.peekCount += 1
        return self.delta
      },
      injectContext: { [unowned self] prompt in
        self.injectedPrompts.append(prompt)
        return self.injectResult
      },
      acknowledge: { [unowned self] delta in
        self.acknowledged.append(delta.ids)
      },
      scheduleWork: { [unowned self] work in
        self.scheduled.append(work)
      }
    )

    /// Runs every scheduled delivery, including trailing re-runs queued while
    /// a delivery was in flight.
    func drainScheduledWork() async {
      while !scheduled.isEmpty {
        let work = scheduled.removeFirst()
        await work()
      }
    }
  }

  private func projection(
    surface: AgentSurfaceReference,
    status: AgentRunProjectionStatus
  ) -> AgentRunProjection {
    AgentRunProjection(
      surface: surface,
      sessionId: "session-1",
      runId: "run-1",
      attemptId: nil,
      adapterSessionId: nil,
      status: status,
      statusText: nil,
      errorMessage: nil,
      failure: nil,
      updatedAt: Date(timeIntervalSince1970: 1_000),
      completedAt: nil,
      costUsd: nil,
      inputTokens: nil,
      outputTokens: nil
    )
  }

  func testBackgroundTerminalTransitionDeliversAndAcknowledges() async {
    let harness = Harness()
    let surface = AgentSurfaceReference.floatingBarRun(runId: "run-1")

    harness.sut.observe([surface.key: projection(surface: surface, status: .running)])
    harness.sut.observe([surface.key: projection(surface: surface, status: .succeeded)])
    await harness.drainScheduledWork()

    XCTAssertEqual(harness.peekCount, 1)
    XCTAssertEqual(harness.injectedPrompts, ["agent finished"])
    XCTAssertEqual(harness.acknowledged, [["run-1"]])
  }

  func testInjectFailureLeavesCheckpointUnadvanced() async {
    let harness = Harness()
    harness.injectResult = false
    let surface = AgentSurfaceReference.floatingBarRun(runId: "run-1")

    harness.sut.observe([surface.key: projection(surface: surface, status: .succeeded)])
    await harness.drainScheduledWork()

    XCTAssertEqual(harness.injectedPrompts.count, 1)
    XCTAssertTrue(harness.acknowledged.isEmpty, "checkpoint must not advance on failed delivery")
  }

  func testNoLiveVoiceSessionDoesNotPeekOrAcknowledge() async {
    let harness = Harness()
    harness.voiceLive = false
    let surface = AgentSurfaceReference.floatingBarRun(runId: "run-1")

    harness.sut.observe([surface.key: projection(surface: surface, status: .failed)])
    await harness.drainScheduledWork()

    XCTAssertEqual(harness.peekCount, 0)
    XCTAssertTrue(harness.injectedPrompts.isEmpty)
    XCTAssertTrue(harness.acknowledged.isEmpty)
  }

  func testPrimarySurfaceTerminalsDoNotTrigger() async {
    let harness = Harness()
    let mainChat = AgentSurfaceReference.mainChat(chatId: "chat-1")
    let voice = AgentSurfaceReference.realtimeVoice()

    harness.sut.observe([
      mainChat.key: projection(surface: mainChat, status: .succeeded),
      voice.key: projection(surface: voice, status: .succeeded),
    ])
    await harness.drainScheduledWork()

    XCTAssertEqual(harness.peekCount, 0, "ordinary chat/voice answers must not trigger delta reads")
  }

  func testRepeatedTerminalProjectionFiresOnce() async {
    let harness = Harness()
    let surface = AgentSurfaceReference.floatingBarRun(runId: "run-1")
    let terminal = projection(surface: surface, status: .succeeded)

    harness.sut.observe([surface.key: terminal])
    await harness.drainScheduledWork()
    harness.sut.observe([surface.key: terminal])
    await harness.drainScheduledWork()

    XCTAssertEqual(harness.peekCount, 1, "an unchanged terminal projection is not a new completion")
  }

  func testSurfaceRemovalThenRecreationIsAFreshTransition() async {
    let harness = Harness()
    let surface = AgentSurfaceReference.floatingBarRun(runId: "run-1")

    harness.sut.observe([surface.key: projection(surface: surface, status: .succeeded)])
    await harness.drainScheduledWork()
    harness.sut.observe([:])
    harness.sut.observe([surface.key: projection(surface: surface, status: .succeeded)])
    await harness.drainScheduledWork()

    XCTAssertEqual(harness.peekCount, 2, "a cleared-and-recreated surface is a fresh completion")
  }

  func testVoiceSessionConnectDrainsPendingCompletions() async {
    let harness = Harness()

    harness.sut.voiceSessionDidConnect()
    await harness.drainScheduledWork()

    XCTAssertEqual(harness.peekCount, 1)
    XCTAssertEqual(harness.acknowledged, [["run-1"]])
  }

  func testTransitionsWhileDeliveryInFlightCoalesceIntoOneTrailingRun() async {
    let harness = Harness()
    let first = AgentSurfaceReference.floatingBarRun(runId: "run-1")
    let second = AgentSurfaceReference.floatingBarRun(runId: "run-2")

    harness.sut.observe([first.key: projection(surface: first, status: .succeeded)])
    // Delivery is scheduled but has not run yet — two more transitions arrive.
    harness.sut.observe([
      first.key: projection(surface: first, status: .succeeded),
      second.key: projection(surface: second, status: .succeeded),
    ])
    await harness.drainScheduledWork()

    XCTAssertEqual(harness.peekCount, 2, "in-flight transitions coalesce into one trailing delivery")
  }

  func testEmptyDeltaAcknowledgesNothing() async {
    let harness = Harness()
    harness.delta = nil
    let surface = AgentSurfaceReference.floatingBarRun(runId: "run-1")

    harness.sut.observe([surface.key: projection(surface: surface, status: .succeeded)])
    await harness.drainScheduledWork()

    XCTAssertEqual(harness.peekCount, 1)
    XCTAssertTrue(harness.injectedPrompts.isEmpty)
    XCTAssertTrue(harness.acknowledged.isEmpty)
  }
}
