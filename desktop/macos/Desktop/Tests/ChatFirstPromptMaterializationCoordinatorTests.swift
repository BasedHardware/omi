import XCTest

@testable import Omi_Computer

final class ChatFirstPromptMaterializationCoordinatorTests: XCTestCase {
  func testEmptyMaterializationBatchOmitsNewOutcomeKeysForOldBackends() throws {
    let data = try ChatFirstMaterializationWire.encodedRequest(
      ownerID: "owner",
      controlGeneration: 7,
      windowForeground: true,
      receipts: .empty)
    let object = try XCTUnwrap(JSONSerialization.jsonObject(with: data) as? [String: Any])

    XCTAssertNil(object["rejections"])
    XCTAssertNil(object["deferrals"])
  }

  func testNonEmptyMaterializationBatchIncludesBothOutcomeKeys() throws {
    let batch = ChatFirstPromptReceiptBatch(
      materializationReceipts: [],
      coldStartSequenceTerminalReceipts: [],
      materializationRejections: [
        ChatFirstMaterializationRejection(intentID: "rejected", code: "invalid_intent", message: nil)
      ],
      materializationDeferrals: [
        ChatFirstMaterializationDeferral(intentID: "deferred", code: "tail_question")
      ])
    let data = try ChatFirstMaterializationWire.encodedRequest(
      ownerID: "owner",
      controlGeneration: 7,
      windowForeground: true,
      receipts: batch)
    let object = try XCTUnwrap(JSONSerialization.jsonObject(with: data) as? [String: Any])

    XCTAssertEqual((object["rejections"] as? [[String: Any]])?.count, 1)
    XCTAssertEqual((object["deferrals"] as? [[String: Any]])?.count, 1)
  }

  func testKernelMaterializationRejectionsDecodeWithTypedIdentityAndReason() {
    let decoded = AgentRuntimeProcess.chatFirstRejections(
      from: [
        ["intentId": "intent-poison", "code": "invalid_intent", "message": "Invalid block"],
        ["intentId": "", "code": "invalid_intent", "message": "Dropped malformed row"],
      ]
    )

    XCTAssertEqual(
      decoded,
      [ChatFirstMaterializationRejection(intentID: "intent-poison", code: "invalid_intent", message: "Invalid block")]
    )
  }

  func testKernelTailDeferralsDecodeSeparatelyFromPermanentRejections() {
    XCTAssertEqual(
      AgentRuntimeProcess.chatFirstDeferrals(
        from: [["intentId": "intent-deferred", "code": "tail_question"]]
      ),
      [ChatFirstMaterializationDeferral(intentID: "intent-deferred", code: "tail_question")]
    )
  }

  func testRejectionMessageIsTruncatedToTheWireLimit() {
    XCTAssertEqual(ChatFirstMaterializationWire.rejectionMessage(String(repeating: "x", count: 500)).count, 300)
  }

  func testMaterializationFallsBackOnlyWhenV2RouteIsMissing() {
    XCTAssertTrue(
      ChatFirstMaterializationEndpointPolicy.shouldFallbackToV1(
        for: APIError.httpError(statusCode: 404)))
    XCTAssertFalse(
      ChatFirstMaterializationEndpointPolicy.shouldFallbackToV1(
        for: APIError.httpError(statusCode: 401)))
    XCTAssertFalse(
      ChatFirstMaterializationEndpointPolicy.shouldFallbackToV1(
        for: APIError.httpError(statusCode: 500)))
  }

  func testPolicyRequiresTranscriptReadinessAndDebouncesForegroundFlapping() {
    let now = Date(timeIntervalSinceReferenceDate: 10_000)

    XCTAssertFalse(
      ChatFirstPromptMaterializationPolicy.shouldStart(
        hasChatFirstMainChatContext: true,
        transcriptFirstPageLoaded: false,
        isRunning: false,
        lastAttemptAt: nil,
        now: now
      )
    )
    XCTAssertTrue(
      ChatFirstPromptMaterializationPolicy.shouldStart(
        hasChatFirstMainChatContext: true,
        transcriptFirstPageLoaded: true,
        isRunning: false,
        lastAttemptAt: nil,
        now: now
      )
    )
    XCTAssertFalse(
      ChatFirstPromptMaterializationPolicy.shouldStart(
        hasChatFirstMainChatContext: true,
        transcriptFirstPageLoaded: true,
        isRunning: true,
        lastAttemptAt: now,
        now: now.addingTimeInterval(120)
      )
    )
    XCTAssertFalse(
      ChatFirstPromptMaterializationPolicy.shouldStart(
        hasChatFirstMainChatContext: true,
        transcriptFirstPageLoaded: true,
        isRunning: false,
        lastAttemptAt: now,
        now: now.addingTimeInterval(59)
      )
    )
    XCTAssertTrue(
      ChatFirstPromptMaterializationPolicy.shouldStart(
        hasChatFirstMainChatContext: true,
        transcriptFirstPageLoaded: true,
        isRunning: false,
        lastAttemptAt: now,
        now: now.addingTimeInterval(60)
      )
    )
  }

  @MainActor
  func testPolicyRejectsLegacyAndNotchDriversBeforeAnyMaterializationWork() {
    let now = Date(timeIntervalSinceReferenceDate: 10_000)
    let legacyDriver = FakePromptMaterializationDriver(
      context: nil,
      pendingReceipts: .empty,
      response: ChatFirstMaterializePromptsResponse(intents: [])
    )
    let notchDriver = FakePromptMaterializationDriver(
      context: nil,
      pendingReceipts: .empty,
      response: ChatFirstMaterializePromptsResponse(intents: [])
    )
    for driver in [legacyDriver, notchDriver] {
      XCTAssertNil(driver.materializationContext())
      XCTAssertFalse(
        ChatFirstPromptMaterializationPolicy.shouldStart(
          hasChatFirstMainChatContext: false,
          transcriptFirstPageLoaded: true,
          isRunning: false,
          lastAttemptAt: nil,
          now: now
        )
      )
    }
  }

  @MainActor
  func testFailedReceiptAcknowledgementReplaysTheSameKernelReceipt() async throws {
    let receipt = ChatFirstMaterializationReceipt(intentID: "intent-1", receiptID: "receipt-1")
    let terminalReceipt = ChatFirstColdStartSequenceTerminalReceipt(
      sequenceID: "cold-start:3",
      receiptID: "terminal-receipt-1",
      terminalState: .completed
    )
    let pendingReceipts = ChatFirstPromptReceiptBatch(
      materializationReceipts: [receipt],
      coldStartSequenceTerminalReceipts: [terminalReceipt]
    )
    let driver = FakePromptMaterializationDriver(
      context: ChatFirstMaterializationContext(ownerID: "owner", controlGeneration: 3),
      pendingReceipts: pendingReceipts,
      response: ChatFirstMaterializePromptsResponse(intents: [])
    )
    driver.acknowledgementError = FixtureError.failedAcknowledgement

    do {
      try await ChatFirstPromptMaterializationRunner.run(
        driver: driver,
        context: ChatFirstMaterializationContext(ownerID: "owner", controlGeneration: 3),
        windowForeground: true,
        isCurrent: { true }
      )
      XCTFail("Expected acknowledgement failure")
    } catch FixtureError.failedAcknowledgement {
      // The driver intentionally keeps the kernel receipt until a successful local acknowledgement.
    }

    XCTAssertEqual(driver.fetchReceiptBatches, [pendingReceipts])
    XCTAssertEqual(driver.acknowledgementBatches, [pendingReceipts])
    XCTAssertTrue(driver.materializedBatches.isEmpty)

    driver.acknowledgementError = nil
    try await ChatFirstPromptMaterializationRunner.run(
      driver: driver,
      context: ChatFirstMaterializationContext(ownerID: "owner", controlGeneration: 3),
      windowForeground: true,
      isCurrent: { true }
    )
    XCTAssertEqual(driver.fetchReceiptBatches, [pendingReceipts, pendingReceipts])
    XCTAssertEqual(driver.acknowledgementBatches, [pendingReceipts, pendingReceipts])
  }

  @MainActor
  func testMeetingCompletionBypassesForegroundDebounceOnlyWhileChatIsVisible() async {
    let now = Date(timeIntervalSinceReferenceDate: 10_000)
    let driver = FakePromptMaterializationDriver(
      context: ChatFirstMaterializationContext(ownerID: "owner", controlGeneration: 3),
      pendingReceipts: .empty,
      response: ChatFirstMaterializePromptsResponse(intents: [])
    )
    let coordinator = ChatFirstPromptMaterializationCoordinator(now: { now })
    coordinator.activate(driver: driver)

    XCTAssertFalse(coordinator.meetingConversationDidComplete(windowForeground: true))
    coordinator.chatTranscriptFirstPageDidLoad()
    for _ in 0..<20 where driver.fetchReceiptBatches.count < 1 { await Task.yield() }
    XCTAssertEqual(driver.fetchReceiptBatches.count, 1)

    XCTAssertTrue(coordinator.meetingConversationDidComplete(windowForeground: true))
    for _ in 0..<20 where driver.fetchReceiptBatches.count < 2 { await Task.yield() }
    XCTAssertEqual(driver.fetchReceiptBatches.count, 2)

    coordinator.chatTranscriptDidDisappear()
    XCTAssertFalse(coordinator.meetingConversationDidComplete(windowForeground: true))
  }

  @MainActor
  func testMeetingCompletionDuringFetchCoalescesOneImmediateFollowUp() async {
    let driver = FakePromptMaterializationDriver(
      context: ChatFirstMaterializationContext(ownerID: "owner", controlGeneration: 3),
      pendingReceipts: .empty,
      response: ChatFirstMaterializePromptsResponse(intents: [])
    )
    driver.suspendNextFetch = true
    let coordinator = ChatFirstPromptMaterializationCoordinator()
    coordinator.activate(driver: driver)

    coordinator.chatTranscriptFirstPageDidLoad()
    for _ in 0..<20 where !driver.isFetchSuspended { await Task.yield() }
    XCTAssertEqual(driver.fetchReceiptBatches.count, 1)
    XCTAssertTrue(coordinator.meetingConversationDidComplete(windowForeground: true))

    driver.resumeFetch()
    for _ in 0..<40 where driver.fetchReceiptBatches.count < 2 { await Task.yield() }
    XCTAssertEqual(driver.fetchReceiptBatches.count, 2)
  }

  @MainActor
  func testBackgroundCompletionDuringFetchWaitsForForegroundForFollowUp() async {
    let driver = FakePromptMaterializationDriver(
      context: ChatFirstMaterializationContext(ownerID: "owner", controlGeneration: 3),
      pendingReceipts: .empty,
      response: ChatFirstMaterializePromptsResponse(intents: [])
    )
    driver.suspendNextFetch = true
    let coordinator = ChatFirstPromptMaterializationCoordinator()
    coordinator.activate(driver: driver)

    coordinator.chatTranscriptFirstPageDidLoad()
    for _ in 0..<20 where !driver.isFetchSuspended { await Task.yield() }
    XCTAssertEqual(driver.fetchReceiptBatches.count, 1)
    XCTAssertTrue(coordinator.meetingConversationDidComplete(windowForeground: false))

    driver.resumeFetch()
    for _ in 0..<40 { await Task.yield() }
    XCTAssertEqual(driver.windowForegroundValues, [true])

    XCTAssertTrue(coordinator.mainWindowDidBecomeForeground())
    for _ in 0..<40 where driver.windowForegroundValues.count < 2 { await Task.yield() }
    XCTAssertEqual(driver.windowForegroundValues, [true, true])
  }

  @MainActor
  func testBackgroundMeetingCompletionWaitsForForegroundWithoutSpendingDebounce() async {
    let driver = FakePromptMaterializationDriver(
      context: ChatFirstMaterializationContext(ownerID: "owner", controlGeneration: 3),
      pendingReceipts: .empty,
      response: ChatFirstMaterializePromptsResponse(intents: [])
    )
    let coordinator = ChatFirstPromptMaterializationCoordinator()
    coordinator.activate(driver: driver)

    coordinator.chatTranscriptFirstPageDidLoad()
    for _ in 0..<20 where driver.windowForegroundValues.count < 1 { await Task.yield() }
    XCTAssertEqual(driver.windowForegroundValues, [true])

    XCTAssertTrue(coordinator.meetingConversationDidComplete(windowForeground: false))
    // A background completion is queued locally. The backend intentionally
    // returns no intents for a background request, so it must not consume the
    // coordinator's 60-second foreground debounce window.
    for _ in 0..<20 { await Task.yield() }
    XCTAssertEqual(driver.windowForegroundValues, [true])

    XCTAssertTrue(coordinator.mainWindowDidBecomeForeground())
    for _ in 0..<20 where driver.windowForegroundValues.count < 2 { await Task.yield() }
    XCTAssertEqual(driver.windowForegroundValues, [true, true])
  }

  func testArrivalScrollPolicyFollowsFreshChatButPreservesScrollback() {
    XCTAssertEqual(
      ChatArrivalScrollPolicy.action(oldCount: 0, newCount: 2, mode: .followingBottom),
      .restoreTail
    )
    XCTAssertEqual(
      ChatArrivalScrollPolicy.action(oldCount: 3, newCount: 4, mode: .followingBottom),
      .followTail
    )
    XCTAssertEqual(
      ChatArrivalScrollPolicy.action(oldCount: 3, newCount: 4, mode: .freeScrolling),
      .preserveReadingPosition
    )
  }

  @MainActor
  func testHTTP422FailureLogIncludesStatusAndBatchSizes() async {
    let batch = ChatFirstPromptReceiptBatch(
      materializationReceipts: [ChatFirstMaterializationReceipt(intentID: "receipt", receiptID: "r1")],
      coldStartSequenceTerminalReceipts: [],
      materializationRejections: [
        ChatFirstMaterializationRejection(intentID: "rejected", code: "invalid_intent", message: nil)
      ],
      materializationDeferrals: [
        ChatFirstMaterializationDeferral(intentID: "deferred", code: "tail_question")
      ])
    let driver = FakePromptMaterializationDriver(
      context: ChatFirstMaterializationContext(ownerID: "owner", controlGeneration: 3),
      pendingReceipts: batch,
      response: ChatFirstMaterializePromptsResponse(intents: []))
    let serverDetail = "raw pydantic validation body must stay private"
    driver.fetchError = APIError.httpError(statusCode: 422, detail: serverDetail)
    var messages: [String] = []
    let coordinator = ChatFirstPromptMaterializationCoordinator(logger: { messages.append($0) })
    coordinator.activate(driver: driver)

    coordinator.chatTranscriptFirstPageDidLoad()
    for _ in 0..<40 where messages.isEmpty { await Task.yield() }

    XCTAssertTrue(messages.first?.contains("status=422") == true)
    XCTAssertFalse(messages.first?.contains(serverDetail) == true)
    XCTAssertTrue(messages.first?.contains("receipts=1 rejections=1 deferrals=1") == true)
  }

  @MainActor
  func testURLErrorFailureLogIncludesTypeAndCode() async {
    let driver = FakePromptMaterializationDriver(
      context: ChatFirstMaterializationContext(ownerID: "owner", controlGeneration: 3),
      pendingReceipts: .empty,
      response: ChatFirstMaterializePromptsResponse(intents: []))
    driver.fetchError = URLError(.timedOut)
    var messages: [String] = []
    let coordinator = ChatFirstPromptMaterializationCoordinator(logger: { messages.append($0) })
    coordinator.activate(driver: driver)

    coordinator.chatTranscriptFirstPageDidLoad()
    for _ in 0..<40 where messages.isEmpty { await Task.yield() }

    XCTAssertTrue(messages.first?.contains("error_type=") == true)
    XCTAssertTrue(messages.first?.contains("url_error_code=\(URLError.Code.timedOut.rawValue)") == true)
  }
}

@MainActor
private final class FakePromptMaterializationDriver: ChatFirstPromptMaterializationDriving {
  private let contextValue: ChatFirstMaterializationContext?
  private var storedPendingReceipts: ChatFirstPromptReceiptBatch
  private let response: ChatFirstMaterializePromptsResponse
  var acknowledgementError: Error?
  var fetchError: Error?
  var suspendNextFetch = false
  private(set) var isFetchSuspended = false
  private var fetchContinuation: CheckedContinuation<Void, Never>?
  private(set) var fetchReceiptBatches: [ChatFirstPromptReceiptBatch] = []
  private(set) var windowForegroundValues: [Bool] = []
  private(set) var acknowledgementBatches: [ChatFirstPromptReceiptBatch] = []
  private(set) var materializedBatches: [[ChatFirstPromptIntent]] = []

  init(
    context: ChatFirstMaterializationContext?,
    pendingReceipts: ChatFirstPromptReceiptBatch,
    response: ChatFirstMaterializePromptsResponse
  ) {
    contextValue = context
    storedPendingReceipts = pendingReceipts
    self.response = response
  }

  func materializationContext() -> ChatFirstMaterializationContext? {
    contextValue
  }

  func pendingReceipts() async throws -> ChatFirstPromptReceiptBatch {
    storedPendingReceipts
  }

  func fetchPrompts(
    ownerID _: String,
    controlGeneration _: Int,
    windowForeground: Bool,
    receipts: ChatFirstPromptReceiptBatch
  ) async throws -> ChatFirstMaterializePromptsResponse {
    fetchReceiptBatches.append(receipts)
    windowForegroundValues.append(windowForeground)
    if suspendNextFetch {
      suspendNextFetch = false
      await withCheckedContinuation {
        isFetchSuspended = true
        fetchContinuation = $0
      }
    }
    if let fetchError { throw fetchError }
    return response
  }

  func resumeFetch() {
    isFetchSuspended = false
    fetchContinuation?.resume()
    fetchContinuation = nil
  }

  func acknowledge(_ receipts: ChatFirstPromptReceiptBatch) async throws {
    acknowledgementBatches.append(receipts)
    if let acknowledgementError { throw acknowledgementError }
    storedPendingReceipts = .empty
  }

  func materialize(_ intents: [ChatFirstPromptIntent]) async throws {
    materializedBatches.append(intents)
  }
}

private enum FixtureError: Error {
  case failedAcknowledgement
}
