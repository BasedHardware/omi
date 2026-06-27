import XCTest

@testable import Omi_Computer

/// Tests for the realtimeProvider mapping used by effectiveProvider (v3, T-306 integration).
///
/// The realtime voice path is constrained to providers that support realtime
/// voice (Gemini Live, OpenAI Realtime). The router may pick any model; we
/// filter to realtime-capable ones and fall through for non-realtime picks
/// (e.g., claude-sonnet-4-6 → fall back to geminiFlashLive).
@MainActor
final class RealtimeOmniSettingsMappingTests: XCTestCase {

  // MARK: - gpt-realtime variants

  func test_realtimeProvider_gpt_realtime_2() {
    XCTAssertEqual(RealtimeOmniSettings.realtimeProvider(for: "gpt-realtime-2"), .gptRealtime2)
  }

  func test_realtimeProvider_gpt_realtime_underscore() {
    XCTAssertEqual(RealtimeOmniSettings.realtimeProvider(for: "gpt_realtime_2"), .gptRealtime2)
  }

  func test_realtimeProvider_gpt_realtime_case_insensitive() {
    XCTAssertEqual(RealtimeOmniSettings.realtimeProvider(for: "GPT-REALTIME-2"), .gptRealtime2)
  }

  // MARK: - gemini variants

  func test_realtimeProvider_gemini_flash_live() {
    XCTAssertEqual(RealtimeOmniSettings.realtimeProvider(for: "gemini-1-5-flash-8b-exp"), .geminiFlashLive)
  }

  func test_realtimeProvider_gemini_pro() {
    XCTAssertEqual(RealtimeOmniSettings.realtimeProvider(for: "gemini-1-5-pro"), .geminiFlashLive)
  }

  func test_realtimeProvider_gemini_case_insensitive() {
    XCTAssertEqual(RealtimeOmniSettings.realtimeProvider(for: "GEMINI-Flash"), .geminiFlashLive)
  }

  // MARK: - non-realtime models (fall through to existing logic)

  func test_realtimeProvider_claude_returns_nil() {
    // Claude isn't a realtime voice model — fall through to AutoModelSelector
    XCTAssertNil(RealtimeOmniSettings.realtimeProvider(for: "claude-sonnet-4-6"))
  }

  func test_realtimeProvider_haiku_returns_nil() {
    XCTAssertNil(RealtimeOmniSettings.realtimeProvider(for: "haiku-4-5"))
  }

  func test_realtimeProvider_gpt_4_returns_nil() {
    // gpt-4o is chat-only, not realtime — fall through
    XCTAssertNil(RealtimeOmniSettings.realtimeProvider(for: "gpt-4o"))
  }

  func test_realtimeProvider_unknown_returns_nil() {
    XCTAssertNil(RealtimeOmniSettings.realtimeProvider(for: "future-model-x"))
  }

  func test_realtimeProvider_empty_returns_nil() {
    XCTAssertNil(RealtimeOmniSettings.realtimeProvider(for: ""))
  }
}
