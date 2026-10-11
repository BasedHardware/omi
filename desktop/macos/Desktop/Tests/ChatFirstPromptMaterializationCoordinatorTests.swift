import XCTest

@testable import Omi_Computer

final class ChatFirstPromptMaterializationCoordinatorTests: XCTestCase {
  @MainActor
  func testOpeningForegroundingAndCompletingMeetingNeverFetchOrMaterialize() async {
    let driver = FakePromptMaterializationDriver(
      context: ChatFirstMaterializationContext(ownerID: "owner", controlGeneration: 7),
      pendingReceipts: .empty,
      response: ChatFirstMaterializePromptsResponse(intents: []))
    let coordinator = ChatFirstPromptMaterializationCoordinator()
    coordinator.activate(driver: driver)
    coordinator.chatTranscriptFirstPageDidLoad()
    XCTAssertFalse(coordinator.mainWindowDidBecomeForeground())
    XCTAssertFalse(coordinator.meetingConversationDidComplete(windowForeground: true))
    XCTAssertFalse(coordinator.meetingConversationDidComplete(windowForeground: false))
    coordinator.chatTranscriptDidDisappear()
    XCTAssertTrue(driver.fetchReceiptBatches.isEmpty)
    XCTAssertTrue(driver.materializedBatches.isEmpty)
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
