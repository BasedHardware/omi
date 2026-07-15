import XCTest

@testable import Omi_Computer

final class ChatFirstPromptMaterializationCoordinatorTests: XCTestCase {
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
}

@MainActor
private final class FakePromptMaterializationDriver: ChatFirstPromptMaterializationDriving {
  private let contextValue: ChatFirstMaterializationContext?
  private var storedPendingReceipts: ChatFirstPromptReceiptBatch
  private let response: ChatFirstMaterializePromptsResponse
  var acknowledgementError: Error?
  private(set) var fetchReceiptBatches: [ChatFirstPromptReceiptBatch] = []
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
    windowForeground _: Bool,
    receipts: ChatFirstPromptReceiptBatch
  ) async throws -> ChatFirstMaterializePromptsResponse {
    fetchReceiptBatches.append(receipts)
    return response
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
