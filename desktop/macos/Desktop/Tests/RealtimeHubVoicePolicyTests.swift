import XCTest

@testable import Omi_Computer

final class RealtimeHubVoicePolicyTests: XCTestCase {
  /// Both lanes pin a deep male voice so a quota failover changes the engine,
  /// not who Omi sounds like. marin (female) regressing into the OpenAI lane
  /// is exactly the drift this guards against.
  func testEveryProviderPinsItsDeepMaleVoice() {
    XCTAssertEqual(RealtimeHubVoicePolicy.voiceName(for: .gemini), "Charon")
    XCTAssertEqual(RealtimeHubVoicePolicy.voiceName(for: .openai), "cedar")
  }

  /// The provider a quota failover lands on must resolve to cedar — the
  /// session payload identity the post-failover connection is configured with.
  func testFailoverAlternateResolvesToCedar() {
    XCTAssertEqual(RealtimeHubVoicePolicy.voiceName(for: RealtimeHubProvider.gemini.alternate), "cedar")
  }

  /// GPT-Live is the default lane: it pins the full-duplex `marin` voice its
  /// session.start requires, mints under `gpt_live`, and fails over to Gemini.
  func testGPTLivePinsMarinAndFailsOverToGemini() {
    XCTAssertEqual(RealtimeHubProvider.gptLive.rawValue, "gpt_live")
    XCTAssertEqual(RealtimeHubProvider.gptLive.modelID, "gpt-live-1")
    XCTAssertEqual(RealtimeHubProvider.gptLive.byokProvider, .openai)
    XCTAssertEqual(RealtimeHubProvider.gptLive.alternate, .gemini)
    XCTAssertEqual(RealtimeHubVoicePolicy.voiceName(for: .gptLive), "marin")
    XCTAssertEqual(RealtimeHubProvider.gptLive.mintProviderParam, "gpt_live")
  }
}

/// Through the production payload seams the session builders embed — not the
/// lookup table — so a per-call-site voice string drifting back in (the marin
/// regression) fails here even if the policy itself is untouched.
final class RealtimeHubSessionVoicePayloadTests: XCTestCase {
  func testOpenAISessionPayloadSpeaksCedar() {
    let output = RealtimeHubSession.openAIOutputAudioConfig()
    XCTAssertEqual(output["voice"] as? String, "cedar")
  }

  func testGeminiSetupPayloadSpeaksCharon() {
    let speech = RealtimeHubSession.geminiSpeechConfig()
    let voiceConfig = speech["voiceConfig"] as? [String: Any]
    let prebuilt = voiceConfig?["prebuiltVoiceConfig"] as? [String: Any]
    XCTAssertEqual(prebuilt?["voiceName"] as? String, "Charon")
  }
}
