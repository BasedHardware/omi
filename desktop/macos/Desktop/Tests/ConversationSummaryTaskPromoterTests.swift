import Foundation
import XCTest

@testable import Omi_Computer

@MainActor
final class ConversationSummaryTaskPromoterTests: XCTestCase {
  private let selected = OmiAPI.SummaryTaskReference(
    actionItemIndex: 1, conversationId: "conversation-1", expectedDescription: "Send budget")

  func testUsesSeparatePrepareAndAcceptWithCapturedAuthority() async {
    let driver = SummaryPromotionDriver()
    let promoter = ConversationSummaryTaskPromoter(dependencies: driver.dependencies)
    let result = await promoter.promote(selected)
    XCTAssertEqual(result, "task-1")
    XCTAssertEqual(driver.events, ["control", "prepare", "accept"])
    XCTAssertEqual(driver.references.map(\.actionItemIndex), [1, 1])
    XCTAssertEqual(driver.generations, [7, 7])
    XCTAssertEqual(driver.owners, ["owner-a", "owner-a", "owner-a"])
    XCTAssertNotNil(UUID(uuidString: driver.keys[0]))
    XCTAssertTrue(promoter.adding.isEmpty)
    XCTAssertTrue(promoter.failed.isEmpty)
    XCTAssertNil(promoter.error)
  }

  func testDoubleClickCannotPrepareTwiceWhileAwaitingAcceptance() async {
    let driver = SummaryPromotionDriver()
    let started = expectation(description: "acceptance started")
    var resume: CheckedContinuation<Void, Never>?
    driver.beforeAccept = {
      await withCheckedContinuation { continuation in
        resume = continuation
        started.fulfill()
      }
    }
    let promoter = ConversationSummaryTaskPromoter(dependencies: driver.dependencies)
    let first = Task { await promoter.promote(selected) }
    await fulfillment(of: [started], timeout: 2)
    XCTAssertEqual(promoter.adding, [1])
    let second = await promoter.promote(selected)
    XCTAssertNil(second)
    XCTAssertEqual(driver.events, ["control", "prepare", "accept"])
    resume?.resume()
    let firstResult = await first.value
    XCTAssertEqual(firstResult, "task-1")
    XCTAssertTrue(promoter.adding.isEmpty)
  }

  func testAuthorityRevocationAtEachAwaitCannotPublishOrContinue() async {
    for phase in ["control", "prepare", "accept"] {
      let driver = SummaryPromotionDriver()
      driver.revokeAfter = phase
      let promoter = ConversationSummaryTaskPromoter(dependencies: driver.dependencies)
      let result = await promoter.promote(selected)
      XCTAssertNil(result)
      XCTAssertEqual(driver.events.last, phase)
      XCTAssertTrue(promoter.failed.isEmpty)
      XCTAssertNil(promoter.error)
      XCTAssertTrue(promoter.adding.isEmpty)
    }
  }

  func testFailedAcceptanceIsNotSuccessAndRetryUsesFreshGesture() async {
    let driver = SummaryPromotionDriver()
    driver.acceptError = APIError.httpError(statusCode: 503)
    let promoter = ConversationSummaryTaskPromoter(dependencies: driver.dependencies)
    let first = await promoter.promote(selected)
    XCTAssertNil(first)
    XCTAssertEqual(promoter.failed, [1])
    XCTAssertNotNil(promoter.error)
    driver.acceptError = nil
    let retry = await promoter.promote(selected)
    XCTAssertEqual(retry, "task-1")
    XCTAssertEqual(driver.keys.count, 2)
    XCTAssertNotEqual(driver.keys[0], driver.keys[1])
    XCTAssertTrue(promoter.failed.isEmpty)
    XCTAssertNil(promoter.error)
  }

  func testChangedRowExplainsRecoveryWithoutShowingAdded() async {
    let driver = SummaryPromotionDriver()
    driver.acceptError = APIError.httpError(statusCode: 409)
    let promoter = ConversationSummaryTaskPromoter(dependencies: driver.dependencies)
    let result = await promoter.promote(selected)
    XCTAssertNil(result)
    XCTAssertEqual(promoter.failed, [1])
    XCTAssertTrue(promoter.error?.contains("Reopen the conversation") == true)
  }

  func testUnavailableAuthorityHasVisibleRetryStateAndNoRequests() async {
    let driver = SummaryPromotionDriver()
    driver.authority.beginTransition()
    let promoter = ConversationSummaryTaskPromoter(dependencies: driver.dependencies)
    let result = await promoter.promote(selected)
    XCTAssertNil(result)
    XCTAssertTrue(driver.events.isEmpty)
    XCTAssertEqual(promoter.failed, [1])
    XCTAssertNotNil(promoter.error)
  }

  func testMissingGenerationAndDisabledWorkflowNeverPrepare() async {
    for control in [
      OmiAPI.TaskWorkflowControl(workflowMode: .read),
      OmiAPI.TaskWorkflowControl(accountGeneration: 7, workflowMode: .off),
    ] {
      let driver = SummaryPromotionDriver()
      driver.control = control
      let promoter = ConversationSummaryTaskPromoter(dependencies: driver.dependencies)
      let result = await promoter.promote(selected)
      XCTAssertNil(result)
      XCTAssertEqual(driver.events, ["control"])
      XCTAssertEqual(promoter.failed, [1])
    }
  }

  func testLinkSurvivesConversationEncodeDecodeAndOnlyChangesSelectedRow() throws {
    let timestamp = Date(timeIntervalSince1970: 1_700_000_000)
    let conversation = ServerConversation(
      id: "conversation-1", createdAt: timestamp, updatedAt: timestamp,
      startedAt: timestamp, finishedAt: timestamp.addingTimeInterval(60),
      structured: Structured(
        title: "Budget", overview: "A meeting", emoji: "💬", category: "other",
        actionItems: [
          ActionItem(description: "Hidden item", completed: false, deleted: true),
          ActionItem(
            description: "Send budget", completed: false, deleted: false,
            captureOwner: "user", sourceSegmentIDs: ["segment-1"]),
        ], events: [], sections: []),
      transcriptSegments: [], transcriptSegmentsIncluded: true, geolocation: nil,
      photos: [], appsResults: [], source: .desktop, language: "en", status: .completed,
      discarded: false, deleted: false, isLocked: false, starred: false, folderId: nil,
      inputDeviceName: nil)
    let linked = try XCTUnwrap(
      ConversationSummaryTaskPromoter.linkedConversation(
        conversation, selected: selected, taskID: "task-1"))
    XCTAssertEqual(linked.structured.actionItems[0], conversation.structured.actionItems[0])
    XCTAssertEqual(linked.structured.actionItems[1].captureOwner, "user")
    XCTAssertEqual(linked.structured.actionItems[1].sourceSegmentIDs, ["segment-1"])
    let encoder = JSONEncoder()
    encoder.dateEncodingStrategy = .iso8601
    let decoder = JSONDecoder()
    decoder.dateDecodingStrategy = .iso8601
    let reopened = try decoder.decode(ServerConversation.self, from: encoder.encode(linked))
    XCTAssertEqual(reopened.structured.actionItems[1].targetTaskID, "task-1")
    XCTAssertEqual(reopened.structured.overview, conversation.structured.overview)
    let changed = OmiAPI.SummaryTaskReference(
      actionItemIndex: 0, conversationId: "conversation-1", expectedDescription: "Send budget")
    XCTAssertNil(ConversationSummaryTaskPromoter.linkedConversation(conversation, selected: changed, taskID: "task-1"))
  }
}

@MainActor
private final class SummaryPromotionDriver {
  let authority = RuntimeOwnerAuthorizationAuthority()
  var events: [String] = []
  var references: [OmiAPI.SummaryTaskReference] = []
  var generations: [Int] = []
  var owners: [String] = []
  var keys: [String] = []
  var revokeAfter: String?
  var acceptError: Error?
  var beforeAccept: (() async -> Void)?
  var control = OmiAPI.TaskWorkflowControl(accountGeneration: 7, workflowMode: .read)

  init() { authority.endTransition(ownerID: "owner-a") }

  var dependencies: ConversationSummaryTaskPromoter.Dependencies {
    .init(
      capture: { self.authority.capture(ownerID: "owner-a", expectedOwnerID: "owner-a") },
      isCurrent: { self.authority.isCurrent($0, ownerID: "owner-a") },
      control: { auth in
        self.record("control", auth)
        return self.control
      },
      prepare: { selected, key, generation, auth in
        self.record("prepare", auth)
        self.references.append(selected)
        self.generations.append(generation)
        self.keys.append(key)
        return try JSONDecoder().decode(
          OmiAPI.CandidateRecord.self,
          from: Data(
            """
            {"candidate_id":"candidate-1","account_generation":7,"subject_kind":"task",
             "proposed_action":"create","status":"pending","capture_confidence":0.9,
             "ownership_confidence":1,"source_surface":"conversation","evidence_refs":[],
             "idempotency_key":"extraction","created_at":"2026-09-29T12:00:00Z",
             "task_change":{"description":"Send budget","owner":"user"}}
            """.utf8))
      },
      accept: { candidateID, selected, generation, auth in
        self.record("accept", auth)
        self.references.append(selected)
        self.generations.append(generation)
        await self.beforeAccept?()
        if let error = self.acceptError { throw error }
        return OmiAPI.CandidateResolutionReceipt(
          candidateId: candidateID, newlyResolved: true, receiptId: "receipt-1",
          resolvedAt: "2026-09-29T12:00:00Z", status: .accepted, taskId: "task-1", workstreamId: nil)
      })
  }

  private func record(_ phase: String, _ auth: RuntimeOwnerAuthorizationSnapshot) {
    events.append(phase)
    owners.append(auth.ownerID)
    if revokeAfter == phase {
      authority.beginTransition()
      authority.endTransition(ownerID: "owner-b")
    }
  }
}
