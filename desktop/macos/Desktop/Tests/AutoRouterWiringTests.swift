import XCTest

@testable import Omi_Computer

/// Tests for ChatModelRouter — the v2 wiring helper that connects
/// AutoRouter to ChatProvider's model selection.
///
/// Covers all 4 cases from the v2 spec:
///   1. Empty settings → router pick if available
///   2. "Auto" settings → router pick if available
///   3. Specific model settings → use that model
///   4. Empty/"Auto" settings with NO router pick → fall back to default
@MainActor
final class AutoRouterWiringTests: XCTestCase {

  // MARK: - Case 1: Empty settings + router pick available

  func testEmptySettingsUsesRouterPick() {
    let pick = "claude-sonnet-4-6"
    let decision = ChatModelRouter.decide(
      selectedModel: "",
      routerPick: pick
    )
    XCTAssertEqual(decision.model, pick, "empty settings should use router pick")
    XCTAssertEqual(decision.reason, .routerPick)
    XCTAssertEqual(decision.routerPick, pick)
  }

  // MARK: - Case 2: "Auto" settings + router pick available

  func testAutoSettingsUsesRouterPick() {
    let pick = "haiku-4-5"
    let decision = ChatModelRouter.decide(
      selectedModel: "auto",
      routerPick: pick
    )
    XCTAssertEqual(decision.model, pick, "'auto' settings should use router pick")
    XCTAssertEqual(decision.reason, .routerPick)
  }

  func testAutoSettingsCaseInsensitive() {
    // "AUTO", "Auto", "auto" should all be treated the same.
    let pick = "gpt-4o"
    for variant in ["AUTO", "Auto", "auto", "  Auto  "] {
      let decision = ChatModelRouter.decide(
        selectedModel: variant,
        routerPick: pick
      )
      XCTAssertEqual(decision.model, pick, "variant \(variant) should use router pick")
      XCTAssertEqual(decision.reason, .routerPick)
    }
  }

  // MARK: - Case 3: Specific model settings → use that model (regression-safe)

  func testSpecificModelUsedDirectly_evenIfRouterHasPick() {
    let decision = ChatModelRouter.decide(
      selectedModel: "claude-sonnet-4-6",
      routerPick: "haiku-4-5"
    )
    XCTAssertEqual(decision.model, "claude-sonnet-4-6", "specific model should be used directly")
    XCTAssertEqual(decision.reason, .userSelected)
    XCTAssertNil(decision.routerPick)
  }

  func testSpecificModelUsedEvenIfRouterEmpty() {
    let decision = ChatModelRouter.decide(
      selectedModel: "claude-sonnet-4-6",
      routerPick: nil
    )
    XCTAssertEqual(decision.model, "claude-sonnet-4-6")
    XCTAssertEqual(decision.reason, .userSelected)
  }

  // MARK: - Case 4: Empty/"Auto" + no router pick → fallback

  func testEmptySettingsNoRouterPickFallsBack() {
    let fallback = ModelQoS.Claude.defaultSelection
    let decision = ChatModelRouter.decide(
      selectedModel: "",
      routerPick: nil,
      fallback: fallback
    )
    XCTAssertEqual(decision.model, fallback, "no router pick should fall back to default")
    XCTAssertEqual(decision.reason, .routerFallback)
    XCTAssertNil(decision.routerPick)
  }

  func testAutoSettingsNoRouterPickFallsBack() {
    let fallback = ModelQoS.Claude.defaultSelection
    let decision = ChatModelRouter.decide(
      selectedModel: "auto",
      routerPick: nil,
      fallback: fallback
    )
    XCTAssertEqual(decision.model, fallback)
    XCTAssertEqual(decision.reason, .routerFallback)
  }

  // MARK: - Edge cases

  func testEmptyRouterPickStringTreatedAsNoPick() {
    // Some UserDefaults implementations might return "" instead of nil
    // for missing keys. The router should treat "" as "no pick".
    let fallback = ModelQoS.Claude.defaultSelection
    let decision = ChatModelRouter.decide(
      selectedModel: "auto",
      routerPick: "",
      fallback: fallback
    )
    XCTAssertEqual(decision.model, fallback, "empty router pick should fall back")
    XCTAssertEqual(decision.reason, .routerFallback)
  }

  func testSpecificModelWithWhitespaceTrimmed() {
    // "  claude-sonnet-4-6  " → "claude-sonnet-4-6" (no router).
    let decision = ChatModelRouter.decide(
      selectedModel: "  claude-sonnet-4-6  ",
      routerPick: "haiku-4-5"
    )
    XCTAssertEqual(decision.model, "claude-sonnet-4-6")
    XCTAssertEqual(decision.reason, .userSelected)
  }
}
