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

    _ = await InterjectSuggestionFeedbackMutation.record(
      evaluationID: evaluation,
      suggestionID: suggestion,
      verb: .useful,
      recordedAt: Date(timeIntervalSince1970: 10),
      store: store,
      emitAnalytics: false
    )
    _ = await InterjectSuggestionFeedbackMutation.record(
      evaluationID: evaluation,
      suggestionID: suggestion,
      verb: .correction,
      recordedAt: Date(timeIntervalSince1970: 20),
      store: store,
      emitAnalytics: false
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

    _ = await InterjectSuggestionFeedbackMutation.record(
      evaluationID: aEval, suggestionID: aSug, verb: .useful, store: store, emitAnalytics: false)
    _ = await InterjectSuggestionFeedbackMutation.record(
      evaluationID: bEval, suggestionID: bSug, verb: .falsePositive, store: store, emitAnalytics: false)

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

  func testRiffIsNotATeachSignalAndDoesNotWriteTheLedger() async throws {
    XCTAssertFalse(InterjectFeedbackVerb.riff.recordsAsTeachSignal)
    XCTAssertTrue(InterjectFeedbackVerb.useful.recordsAsTeachSignal)
    XCTAssertTrue(InterjectFeedbackVerb.correction.recordsAsTeachSignal)

    let store = InterjectSuggestionFeedbackStore()
    let evaluation = try XCTUnwrap(UUID(uuidString: "00000000-0000-0000-0000-0000000000aa"))
    let suggestion = try XCTUnwrap(UUID(uuidString: "00000000-0000-0000-0000-0000000000bb"))
    _ = await InterjectSuggestionFeedbackMutation.record(
      evaluationID: evaluation,
      suggestionID: suggestion,
      verb: .riff,
      store: store,
      emitAnalytics: false
    )
    let current = await store.current(evaluationID: evaluation, suggestionID: suggestion)
    XCTAssertNil(current, "riff must not inflate teach-rate")
  }

  func testAmbientFeedbackKeepsDeliveryProvenanceInTheCanonicalLedger() async throws {
    let store = InterjectSuggestionFeedbackStore()
    let evaluation = try XCTUnwrap(UUID(uuidString: "00000000-0000-0000-0000-0000000000ca"))
    let suggestion = try XCTUnwrap(UUID(uuidString: "00000000-0000-0000-0000-0000000000cb"))
    let provenance = InterjectFeedbackProvenance(
      lane: "ambient",
      ownerID: "owner",
      deliveryID: String(repeating: "a", count: 64),
      candidateID: String(repeating: "b", count: 64),
      accountGeneration: 3
    )

    _ = await InterjectSuggestionFeedbackMutation.record(
      evaluationID: evaluation,
      suggestionID: suggestion,
      verb: .useful,
      provenance: provenance,
      store: store,
      emitAnalytics: false
    )

    let current = await store.current(evaluationID: evaluation, suggestionID: suggestion)
    XCTAssertEqual(current?.provenance, provenance)
  }

  @MainActor
  func testAmbientFeedbackEmitsOpaqueProvenanceWithAnalyticsEvent() async throws {
    let store = InterjectSuggestionFeedbackStore()
    let evaluation = try XCTUnwrap(UUID(uuidString: "00000000-0000-0000-0000-0000000000da"))
    let suggestion = try XCTUnwrap(UUID(uuidString: "00000000-0000-0000-0000-0000000000db"))
    let provenance = InterjectFeedbackProvenance(
      lane: "ambient",
      ownerID: "owner",
      deliveryID: String(repeating: "c", count: 64),
      candidateID: String(repeating: "d", count: 64),
      accountGeneration: 8
    )
    var captured: [String: Any] = [:]
    AnalyticsManager.shared.setSuggestionAssistantTelemetryCaptureForTests { event, properties in
      if event == "Suggestion Feedback Recorded" { captured = properties }
    }
    defer { AnalyticsManager.shared.setSuggestionAssistantTelemetryCaptureForTests(nil) }

    let didRecord = await InterjectSuggestionFeedbackMutation.record(
      evaluationID: evaluation,
      suggestionID: suggestion,
      verb: .useful,
      provenance: provenance,
      store: store
    )

    XCTAssertTrue(didRecord)
    XCTAssertEqual(captured["feedback_lane"] as? String, "ambient")
    XCTAssertEqual(captured["feedback_delivery_id"] as? String, provenance.deliveryID)
    XCTAssertEqual(captured["feedback_candidate_id"] as? String, provenance.candidateID)
    XCTAssertEqual(captured["feedback_account_generation"] as? Int, provenance.accountGeneration)
    XCTAssertNil(captured["owner_id"], "analytics must not emit raw owner identity")
  }
}
