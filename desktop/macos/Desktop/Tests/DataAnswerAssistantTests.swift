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
