import XCTest

@testable import Omi_Computer

final class InterjectSuggestionFeedbackStoreTests: XCTestCase {
  override func tearDown() async throws {
    await InterjectSuggestionFeedbackStore.shared.removeAllForTests()
    try await super.tearDown()
  }

  func testIdentityHasOneWritePathAndLastWriteWins() async throws {
    let evaluation = try XCTUnwrap(UUID(uuidString: "00000000-0000-0000-0000-000000000001"))
    let suggestion = try XCTUnwrap(UUID(uuidString: "00000000-0000-0000-0000-000000000002"))
    let store = InterjectSuggestionFeedbackStore()

    await InterjectSuggestionFeedbackMutation.record(
      evaluationID: evaluation,
      suggestionID: suggestion,
      verb: .useful,
      recordedAt: Date(timeIntervalSince1970: 10),
      store: store
    )
    await InterjectSuggestionFeedbackMutation.record(
      evaluationID: evaluation,
      suggestionID: suggestion,
      verb: .correction,
      recordedAt: Date(timeIntervalSince1970: 20),
      store: store
    )

    let current = await store.current(evaluationID: evaluation, suggestionID: suggestion)
    XCTAssertEqual(current?.verb, .correction)
    XCTAssertEqual(current?.recordedAt, Date(timeIntervalSince1970: 20))
  }

  func testDistinctIdentitiesDoNotShareATally() async throws {
    let store = InterjectSuggestionFeedbackStore()
    let aEval = try XCTUnwrap(UUID(uuidString: "00000000-0000-0000-0000-00000000000a"))
    let aSug = try XCTUnwrap(UUID(uuidString: "00000000-0000-0000-0000-00000000000b"))
    let bEval = try XCTUnwrap(UUID(uuidString: "00000000-0000-0000-0000-00000000000c"))
    let bSug = try XCTUnwrap(UUID(uuidString: "00000000-0000-0000-0000-00000000000d"))

    await InterjectSuggestionFeedbackMutation.record(
      evaluationID: aEval, suggestionID: aSug, verb: .useful, store: store)
    await InterjectSuggestionFeedbackMutation.record(
      evaluationID: bEval, suggestionID: bSug, verb: .falsePositive, store: store)

    let a = await store.current(evaluationID: aEval, suggestionID: aSug)
    let b = await store.current(evaluationID: bEval, suggestionID: bSug)
    XCTAssertEqual(a?.verb, .useful)
    XCTAssertEqual(b?.verb, .falsePositive)
  }

  func testKeyUsesEvaluationAndSuggestionTogether() throws {
    let evaluation = try XCTUnwrap(UUID(uuidString: "00000000-0000-0000-0000-000000000001"))
    let suggestion = try XCTUnwrap(UUID(uuidString: "00000000-0000-0000-0000-000000000002"))
    XCTAssertEqual(
      InterjectSuggestionFeedbackStore.identityKey(evaluationID: evaluation, suggestionID: suggestion),
      "00000000-0000-0000-0000-000000000001|00000000-0000-0000-0000-000000000002"
    )
  }
}
