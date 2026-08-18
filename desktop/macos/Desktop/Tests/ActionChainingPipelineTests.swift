import XCTest

@testable import Omi_Computer

final class ActionChainingPipelineTests: XCTestCase {

  func testPlanFoodOrderSingleUser() {
    let now = Date()
    let memory = ["User": "Spicy Basil Fried Rice"]
    let proposal = ActionChainingPipeline.plan(
      intent: "Omi, let's order dinner",
      memoryPreferences: memory,
      now: now
    )

    XCTAssertNotNil(proposal)
    XCTAssertEqual(proposal?.actionType, "food_order")
    XCTAssertEqual(proposal?.participants, ["You"])
    XCTAssertEqual(proposal?.items, ["You: Spicy Basil Fried Rice"])
    XCTAssertEqual(proposal?.estimatedCost, "$16.00")
    XCTAssertTrue(proposal?.isReversible == true)
  }

  func testPlanFoodOrderWithMultiPartyParticipant() {
    let now = Date()
    let env = ActionContextEnvironment(
      isMultiPartyCall: true,
      participantLabels: ["Maya"]
    )
    let memory = [
      "You": "Pad Thai with Tofu",
      "Maya": "Green Curry with Jasmine Rice"
    ]

    let proposal = ActionChainingPipeline.plan(
      intent: "Omi, let's order food for Maya and me",
      environmentalContext: env,
      memoryPreferences: memory,
      now: now
    )

    XCTAssertNotNil(proposal)
    XCTAssertEqual(proposal?.title, "Food Order for You and Maya")
    XCTAssertEqual(proposal?.participants, ["You", "Maya"])
    XCTAssertEqual(proposal?.items, [
      "You: Pad Thai with Tofu",
      "Maya: Green Curry with Jasmine Rice"
    ])
    XCTAssertEqual(proposal?.estimatedCost, "$32.00")
  }

  func testExecuteProducesReversibleReceipt() {
    let now = Date()
    let proposal = ActionProposal(
      actionType: "food_order",
      title: "Food Order for You and Maya",
      summary: "Thai delivery order",
      items: ["Pad Thai", "Green Curry"],
      participants: ["You", "Maya"],
      estimatedCost: "$32.00",
      isReversible: true,
      cancellationWindowSeconds: 30.0,
      createdAt: now
    )

    let receipt = ActionChainingPipeline.execute(proposal: proposal, now: now)

    XCTAssertEqual(receipt.status, .executed)
    XCTAssertEqual(receipt.title, "✓ Food Order for You and Maya")
    XCTAssertTrue(receipt.canUndo(now: now.addingTimeInterval(10)))
    XCTAssertFalse(receipt.canUndo(now: now.addingTimeInterval(35)))
  }

  func testCancelWithinWindowSucceeds() {
    let now = Date()
    let proposal = ActionProposal(
      actionType: "food_order",
      title: "Food Order for You",
      summary: "Lunch order",
      items: ["Pad Thai"],
      participants: ["You"],
      isReversible: true,
      cancellationWindowSeconds: 30.0,
      createdAt: now
    )

    let receipt = ActionChainingPipeline.execute(proposal: proposal, now: now)
    let cancelledReceipt = ActionChainingPipeline.cancel(receipt: receipt, now: now.addingTimeInterval(15))

    XCTAssertNotNil(cancelledReceipt)
    XCTAssertEqual(cancelledReceipt?.status, .cancelled)
  }

  func testCancelAfterWindowFails() {
    let now = Date()
    let proposal = ActionProposal(
      actionType: "food_order",
      title: "Food Order for You",
      summary: "Lunch order",
      items: ["Pad Thai"],
      participants: ["You"],
      isReversible: true,
      cancellationWindowSeconds: 30.0,
      createdAt: now
    )

    let receipt = ActionChainingPipeline.execute(proposal: proposal, now: now)
    let cancelledReceipt = ActionChainingPipeline.cancel(receipt: receipt, now: now.addingTimeInterval(35))

    XCTAssertNil(cancelledReceipt, "Cancellation after window expiration must fail")
  }

  func testNonMatchingIntentReturnsNil() {
    let proposal = ActionChainingPipeline.plan(intent: "What is the weather today in Tokyo?")
    XCTAssertNil(proposal)
  }
}
