import XCTest

@testable import Omi_Computer

final class AssistantCoordinatorTests: XCTestCase {
  func testContextTransitionQueueRetainsLatestAThenBThenCTransition() {
    let destinationA = ContextTransitionRequest(app: "A", windowTitle: "Document")
    let destinationB = ContextTransitionRequest(app: "B", windowTitle: "Document")
    let destinationC = ContextTransitionRequest(app: "C", windowTitle: "Inbox")
    var queue = ContextTransitionQueue()

    XCTAssertTrue(queue.begin(destinationA))
    XCTAssertFalse(queue.begin(destinationB))
    XCTAssertFalse(queue.begin(destinationC))
    XCTAssertEqual(queue.finish(destinationA), destinationC)

    // A fresh observation can begin before the scheduled drain task runs; the
    // retained C request must join that transition rather than be dropped.
    XCTAssertTrue(queue.begin(destinationB))
    XCTAssertFalse(queue.begin(destinationC))
    XCTAssertEqual(queue.finish(destinationB), destinationC)
    XCTAssertTrue(queue.begin(destinationC))
    XCTAssertNil(queue.finish(destinationC))
  }

  func testContextTransitionQueueCoalescesDuplicateDestination() {
    let destinationA = ContextTransitionRequest(app: "A", windowTitle: nil)
    let destinationB = ContextTransitionRequest(app: "B", windowTitle: nil)
    var queue = ContextTransitionQueue()

    XCTAssertTrue(queue.begin(destinationA))
    XCTAssertFalse(queue.begin(destinationB))
    XCTAssertFalse(queue.begin(destinationB))
    XCTAssertEqual(queue.finish(destinationA), destinationB)
    XCTAssertTrue(queue.begin(destinationB))
    XCTAssertNil(queue.finish(destinationB))
  }

  func testContextTransitionQueueRejectsStaleCompletion() {
    let destinationB = ContextTransitionRequest(app: "B", windowTitle: nil)
    let destinationC = ContextTransitionRequest(app: "C", windowTitle: nil)
    var queue = ContextTransitionQueue()

    XCTAssertTrue(queue.begin(destinationB))
    XCTAssertNil(queue.finish(destinationC))
    XCTAssertEqual(queue.inFlight, destinationB)
    XCTAssertEqual(queue.finish(destinationB), nil)
  }
}
