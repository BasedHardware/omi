import XCTest

@testable import Omi_Computer

final class CandidateSinkDeliveryGateTests: XCTestCase {
  func testInteractiveTaskCandidateRequiresSuccessfulGraduationBeforePresent() {
    XCTAssertFalse(
      CandidateSinkDeliveryGate.mayPresentInteractively(
        decisionType: "task_candidate",
        graduation: .stale))
    XCTAssertFalse(
      CandidateSinkDeliveryGate.mayPresentInteractively(
        decisionType: "task_candidate",
        graduation: .noFactIDs))
    XCTAssertTrue(
      CandidateSinkDeliveryGate.mayPresentInteractively(
        decisionType: "task_candidate",
        graduation: .graduated))
  }

  func testNonTaskDecisionsDoNotRequireGraduationBeforePresent() {
    for decision in ["suggest", "insight", "resurface", "silence"] {
      XCTAssertTrue(
        CandidateSinkDeliveryGate.mayPresentInteractively(
          decisionType: decision,
          graduation: .stale),
        decision)
    }
  }

  func testGraduationRequiresEveryRequestedFact() {
    XCTAssertTrue(
      CandidateSinkDeliveryGate.hasCompleteValidatedFactSet(
        requestedIDs: ["fact:a", "b", "b"],
        fetchedIDs: ["a", "b"]))
    XCTAssertFalse(
      CandidateSinkDeliveryGate.hasCompleteValidatedFactSet(
        requestedIDs: ["fact:a", "fact:b"],
        fetchedIDs: ["a"]))
    XCTAssertFalse(
      CandidateSinkDeliveryGate.hasCompleteValidatedFactSet(
        requestedIDs: [],
        fetchedIDs: []))
  }

  func testGraduationCompletenessCountsCandidatePendingFacts() {
    XCTAssertTrue(
      CandidateSinkDeliveryGate.hasCompleteValidatedFactSet(
        requestedIDs: ["fact:a", "fact:b"],
        fetchedIDs: ["a", "b"]))
    XCTAssertTrue(CandidateSinkDeliveryGate.isGraduationEligibleDisposition("none"))
    XCTAssertTrue(CandidateSinkDeliveryGate.isGraduationEligibleDisposition("candidate_pending"))
    XCTAssertFalse(CandidateSinkDeliveryGate.isGraduationEligibleDisposition("task_created"))
  }

  func testCanonicalCandidateIdempotencyKeyIsFactStableAcrossDeliveries() {
    let factID = "fact-123"
    XCTAssertEqual(
      CandidateSinkDeliveryGate.canonicalCandidateIdempotencyKey(factID: factID),
      "context-bucket:\(factID)")
    XCTAssertEqual(
      CandidateSinkDeliveryGate.canonicalCandidateIdempotencyKey(factID: factID),
      CandidateSinkDeliveryGate.canonicalCandidateIdempotencyKey(factID: factID))
    XCTAssertNotEqual(
      CandidateSinkDeliveryGate.canonicalCandidateIdempotencyKey(factID: factID),
      "context-bucket:delivery-a:\(factID)")
  }
}
