import XCTest

@testable import Omi_Computer

/// Tests for the 4 model routers (T-306..T-309): RealtimeModelRouter,
/// ScreenshotModelRouter, TranscriptionModelRouter, EmbeddingModelRouter.
/// All four follow the same pattern (mirrors ChatModelRouter from v2), so
/// we test the pattern once with parameterization-style helpers.
@MainActor
final class ProviderModelRoutersTests: XCTestCase {

  // MARK: - All routers share the same decision logic

  func test_empty_settings_uses_router_pick() {
    let d = RealtimeModelRouter.decide(selectedModel: "", routerPick: "router-model", fallback: "fallback")
    XCTAssertEqual(d.model, "router-model")
    XCTAssertEqual(d.reason, .routerPick)
    XCTAssertEqual(d.routerPick, "router-model")
  }

  func test_auto_settings_uses_router_pick() {
    let d = RealtimeModelRouter.decide(selectedModel: "Auto", routerPick: "router-model", fallback: "fallback")
    XCTAssertEqual(d.model, "router-model")
    XCTAssertEqual(d.reason, .routerPick)
  }

  func test_auto_settings_case_insensitive() {
    for variant in ["AUTO", "Auto", "auto", "  Auto  "] {
      let d = RealtimeModelRouter.decide(selectedModel: variant, routerPick: "router-model", fallback: "fallback")
      XCTAssertEqual(d.model, "router-model", "case variant \(variant) should use router pick")
      XCTAssertEqual(d.reason, .routerPick, "case variant \(variant) reason")
    }
  }

  func test_specific_model_uses_user_choice_even_when_router_pick_available() {
    let d = RealtimeModelRouter.decide(selectedModel: "user-model", routerPick: "router-model", fallback: "fallback")
    XCTAssertEqual(d.model, "user-model")
    XCTAssertEqual(d.reason, .userSelected)
  }

  func test_specific_model_no_router_pick() {
    let d = RealtimeModelRouter.decide(selectedModel: "user-model", routerPick: nil, fallback: "fallback")
    XCTAssertEqual(d.model, "user-model")
    XCTAssertEqual(d.reason, .userSelected)
  }

  func test_empty_settings_no_router_pick_uses_fallback() {
    let d = RealtimeModelRouter.decide(selectedModel: "", routerPick: nil, fallback: "fallback-model")
    XCTAssertEqual(d.model, "fallback-model")
    XCTAssertEqual(d.reason, .routerFallback)
  }

  func test_auto_settings_no_router_pick_uses_fallback() {
    let d = RealtimeModelRouter.decide(selectedModel: "Auto", routerPick: nil, fallback: "fallback-model")
    XCTAssertEqual(d.model, "fallback-model")
    XCTAssertEqual(d.reason, .routerFallback)
  }

  func test_empty_router_pick_treated_as_no_pick() {
    let d = RealtimeModelRouter.decide(selectedModel: "", routerPick: "", fallback: "fallback-model")
    XCTAssertEqual(d.model, "fallback-model")
    XCTAssertEqual(d.reason, .routerFallback)
  }

  func test_whitespace_router_pick_treated_as_no_pick() {
    let d = RealtimeModelRouter.decide(selectedModel: "", routerPick: "   ", fallback: "fallback-model")
    XCTAssertEqual(d.model, "fallback-model")
  }

  func test_specific_model_whitespace_trimmed() {
    let d = RealtimeModelRouter.decide(selectedModel: "  user-model  ", routerPick: nil, fallback: "fallback-model")
    XCTAssertEqual(d.model, "user-model")
    XCTAssertEqual(d.reason, .userSelected)
  }

  // MARK: - Same logic across all 4 routers (parameterized sanity)

  func test_all_four_routers_share_pattern() {
    let cases: [(selected: String, routerPick: String?, fallback: String)] = [
      ("", "router-model", "fallback"),
      ("Auto", "router-model", "fallback"),
      ("user-model", "router-model", "fallback"),
      ("", nil, "fallback"),
    ]
    for (selected, routerPick, fallback) in cases {
      let r1 = RealtimeModelRouter.decide(selectedModel: selected, routerPick: routerPick, fallback: fallback)
      let r2 = ScreenshotModelRouter.decide(selectedModel: selected, routerPick: routerPick, fallback: fallback)
      let r3 = TranscriptionModelRouter.decide(selectedModel: selected, routerPick: routerPick, fallback: fallback)
      let r4 = EmbeddingModelRouter.decide(selectedModel: selected, routerPick: routerPick, fallback: fallback)
      XCTAssertEqual(r1.model, r2.model, "Realtime vs Screenshot for \(selected)/\(routerPick ?? "nil")")
      XCTAssertEqual(r2.model, r3.model, "Screenshot vs Transcription for \(selected)/\(routerPick ?? "nil")")
      XCTAssertEqual(r3.model, r4.model, "Transcription vs Embedding for \(selected)/\(routerPick ?? "nil")")
    }
  }

  // MARK: - Reason enum correctness (per-router)

  func test_realtime_router_reasons() {
    XCTAssertEqual(RealtimeModelRouter.decide(selectedModel: "x", routerPick: nil, fallback: "f").reason, .userSelected)
    XCTAssertEqual(RealtimeModelRouter.decide(selectedModel: "", routerPick: "r", fallback: "f").reason, .routerPick)
    XCTAssertEqual(RealtimeModelRouter.decide(selectedModel: "", routerPick: nil, fallback: "f").reason, .routerFallback)
  }

  func test_screenshot_router_reasons() {
    XCTAssertEqual(ScreenshotModelRouter.decide(selectedModel: "x", routerPick: nil, fallback: "f").reason, .userSelected)
    XCTAssertEqual(ScreenshotModelRouter.decide(selectedModel: "", routerPick: "r", fallback: "f").reason, .routerPick)
    XCTAssertEqual(ScreenshotModelRouter.decide(selectedModel: "", routerPick: nil, fallback: "f").reason, .routerFallback)
  }

  func test_transcription_router_reasons() {
    XCTAssertEqual(TranscriptionModelRouter.decide(selectedModel: "x", routerPick: nil, fallback: "f").reason, .userSelected)
    XCTAssertEqual(TranscriptionModelRouter.decide(selectedModel: "", routerPick: "r", fallback: "f").reason, .routerPick)
    XCTAssertEqual(TranscriptionModelRouter.decide(selectedModel: "", routerPick: nil, fallback: "f").reason, .routerFallback)
  }

  func test_embedding_router_reasons() {
    XCTAssertEqual(EmbeddingModelRouter.decide(selectedModel: "x", routerPick: nil, fallback: "f").reason, .userSelected)
    XCTAssertEqual(EmbeddingModelRouter.decide(selectedModel: "", routerPick: "r", fallback: "f").reason, .routerPick)
    XCTAssertEqual(EmbeddingModelRouter.decide(selectedModel: "", routerPick: nil, fallback: "f").reason, .routerFallback)
  }
}
