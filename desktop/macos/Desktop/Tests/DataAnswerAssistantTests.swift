import XCTest

@testable import Omi_Computer

/// The lookup loop's pure edges: how a JSON step decodes, which steps end the search,
/// which actions may explore, and that a partial find is never thrown away.
final class DataAnswerAssistantTests: XCTestCase {
  private func step(_ json: String) -> DataAnswerAssistant.Step {
    guard let step = DataAnswerAssistant.decodeStep(json) else {
      XCTFail("undecodable step: \(json)")
      fatalError()
    }
    return step
  }

  func testPresentAnswerEndsTheSearch() {
    let outcome = DataAnswerAssistant.outcome(
      of: step(
        #"{"action":"present_answer","query":"","title":"Your links","items":[{"label":"Portfolio","text":"https://example.com"}],"missing":[]}"#
      ))
    XCTAssertEqual(
      outcome,
      .answer(
        title: "Your links",
        items: [VoicePanelItem(label: "Portfolio", text: "https://example.com")],
        missing: []))
  }

  /// The failure that shaped this contract: the model held the email and threw it away
  /// because the portfolio was missing. A partial find is an answer plus a missing list.
  func testPartialFindKeepsItemsAndNamesTheMissing() {
    let outcome = DataAnswerAssistant.outcome(
      of: step(
        #"{"action":"present_answer","query":"","title":"Your details","items":[{"label":"Email","text":"a@b.c"}],"missing":["portfolio link"]}"#
      ))
    XCTAssertEqual(
      outcome,
      .answer(
        title: "Your details",
        items: [VoicePanelItem(label: "Email", text: "a@b.c")],
        missing: ["portfolio link"]))
  }

  func testAllMissingBecomesNothingWithNames() {
    let outcome = DataAnswerAssistant.outcome(
      of: step(
        #"{"action":"present_answer","query":"","title":"Search","items":[],"missing":["portfolio link"]}"#
      ))
    XCTAssertEqual(outcome, .nothing(reason: "not found: portfolio link"))
  }

  /// An "answer" with nothing in it is a refusal wearing the wrong action name.
  func testEmptyAnswerBecomesNothingFound() {
    let outcome = DataAnswerAssistant.outcome(
      of: step(#"{"action":"present_answer","query":"","title":"Empty","items":[],"missing":[]}"#))
    XCTAssertEqual(outcome, .nothing(reason: "the answer came back empty"))
  }

  func testMissingTitleGetsAFallback() {
    let outcome = DataAnswerAssistant.outcome(
      of: step(
        #"{"action":"present_answer","query":"","title":"","items":[{"text":"42 Wallaby Way"}],"missing":[]}"#
      ))
    guard case .answer(let title, _, _)? = outcome else { return XCTFail("expected an answer") }
    XCTAssertFalse(title.isEmpty)
  }

  func testSearchStepsAreNotTerminal() {
    let outcome = DataAnswerAssistant.outcome(
      of: step(#"{"action":"search_memories","query":"email","title":"","items":[],"missing":[]}"#))
    XCTAssertNil(outcome)
  }

  func testUndecodableStepIsRefused() {
    XCTAssertNil(DataAnswerAssistant.decodeStep("Sure! Here is the JSON you asked for:"))
    XCTAssertNil(DataAnswerAssistant.decodeStep(#"{"query":"no action field"}"#))
  }

  /// The subtitle map doubles as the allowlist: an action the loop does not offer must
  /// not reach ChatToolExecutor, however confidently the model asks for it.
  func testOnlyDeclaredDataToolsMayExplore() {
    for allowed in [
      "search_memories", "get_memories", "get_work_context", "search_screen_history",
      "search_conversations",
    ] {
      XCTAssertNotNil(DataAnswerAssistant.progressSubtitle(forTool: allowed), allowed)
    }
    for refused in ["execute_sql", "create_memory", "point_click", "present_answer", ""] {
      XCTAssertNil(DataAnswerAssistant.progressSubtitle(forTool: refused), refused)
    }
  }
}

/// The panel is for values. Measured live: asking for a beginner Python syllabus routed
/// to find_and_show, found nothing in the user's data, and put "The information about an
/// 18-chapter beginner Python course syllabus was not found in your recent activity,
/// screen history, or stored memories" on screen as the thing to copy.
final class DataAnswerAbsenceGuardTests: XCTestCase {
  private func step(items: [(String, String)], missing: [String] = []) -> DataAnswerAssistant.Step {
    let json: [String: Any] = [
      "action": "present_answer", "query": "", "title": "Result",
      "items": items.map { ["label": $0.0, "text": $0.1] }, "missing": missing,
    ]
    let data = try! JSONSerialization.data(withJSONObject: json)
    return DataAnswerAssistant.decodeStep(String(data: data, encoding: .utf8)!)!
  }

  func testALoneApologyIsNotAnAnswer() {
    let outcome = DataAnswerAssistant.outcome(
      of: step(items: [("", "That was not found in your stored memories.")]))
    guard case .nothing = outcome else {
      return XCTFail("an apology must take the panel down, not fill it")
    }
  }

  func testRealValuesStillPresent() {
    let outcome = DataAnswerAssistant.outcome(
      of: step(items: [("Email", "a@b.c"), ("Site", "example.dev")]))
    guard case .answer(_, let items, _) = outcome else { return XCTFail("expected an answer") }
    XCTAssertEqual(items.count, 2)
  }

  /// Narrow on purpose: a value that merely contains a negative word is still a value.
  func testAValueThatHappensToSoundNegativeIsKept() {
    let outcome = DataAnswerAssistant.outcome(
      of: step(items: [("Diet", "No dairy, no shellfish")]))
    guard case .answer(_, let items, _) = outcome else { return XCTFail("expected an answer") }
    XCTAssertEqual(items.first?.text, "No dairy, no shellfish")
  }

  /// The guard only fires when the apology is the whole answer — a real value beside it
  /// means the panel is still worth showing.
  func testAnApologyBesideARealValueDoesNotDropThePanel() {
    let outcome = DataAnswerAssistant.outcome(
      of: step(items: [("Email", "a@b.c"), ("", "The phone number was not found.")]))
    guard case .answer(_, let items, _) = outcome else { return XCTFail("expected an answer") }
    XCTAssertEqual(items.count, 2)
  }

  func testTheSpokenReasonCarriesWhatTheModelSaid() {
    let outcome = DataAnswerAssistant.outcome(
      of: step(items: [("", "I don't have that in your memories.")]))
    guard case .nothing(let reason) = outcome else { return XCTFail("expected nothing") }
    XCTAssertTrue(reason.contains("I don't have that"))
  }
}
