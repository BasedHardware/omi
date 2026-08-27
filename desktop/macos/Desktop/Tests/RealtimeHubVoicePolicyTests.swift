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
}
