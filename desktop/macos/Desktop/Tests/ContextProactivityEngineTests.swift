import XCTest

@testable import Omi_Computer

final class ContextProactivityEngineTests: XCTestCase {
  func testDwellAdmissionTracksVisitsInsteadOfSuppressingARevisitToTheSameBucket() {
    var admission = ContextVisitDwellAdmission()

    XCTAssertTrue(admission.begin(visitID: 41))
    XCTAssertTrue(admission.begin(visitID: 42), "a new visit needs its own dwell timer")
    XCTAssertFalse(admission.begin(visitID: 42), "the same visit must not be scheduled twice")

    admission.finish(visitID: 41)
    admission.finish(visitID: 42)
    XCTAssertTrue(admission.begin(visitID: 42))
  }

  func testDirectorDecisionClampsUntrustedOutputBeforeDatabaseQueriesAndPresentation() {
    let decision = ContextDirectorDecision(
      decision: "suggest",
      title: String(repeating: "t", count: 500),
      message: String(repeating: "m", count: 1_000),
      reasoning: String(repeating: "r", count: 2_000),
      bucketEntryRefs: (0..<50).map { "entry:\($0)" },
      factIDs: (0..<50).map { "fact:\($0)" })

    let clamped = decision.clamped()

    XCTAssertEqual(clamped.title.count, 120)
    XCTAssertEqual(clamped.message.count, 600)
    XCTAssertEqual(clamped.reasoning.count, 1_200)
    XCTAssertEqual(clamped.bucketEntryRefs.count, 20)
    XCTAssertEqual(clamped.factIDs.count, 20)
  }
}
