import XCTest

@testable import Omi_Computer

#if DEBUG
  /// Two deterministic voice-lane defects: a claim made on the user's behalf about
  /// which languages they speak, and a written task that its paired read could
  /// never return.
  @MainActor
  final class RealtimeVoiceLanguageAndTaskBucketTests: XCTestCase {

    // MARK: - Reply language

    func testUnconfiguredUserGetsNoLanguageClaim() {
      // The macOS UI language describes the interface, not the person. Falling back
      // to it told the model an unconfigured bilingual user speaks ONLY their
      // menu-bar language and that anything else "was misheard".
      XCTAssertTrue(RealtimeHubTools.resolvedVoiceLanguages(explicit: []).isEmpty)
    }

    func testUnconfiguredUserInstructionOmitsTheSpeaksOnlyLine() {
      let instruction = RealtimeHubTools.systemInstruction(userLanguages: [])
      XCTAssertFalse(instruction.contains("speaks ONLY"))
    }

    func testConfiguredLanguagesAreNamedAndDeduplicated() {
      let resolved = RealtimeHubTools.resolvedVoiceLanguages(explicit: ["ru-RU", "en-US", "ru"])
      XCTAssertEqual(resolved, ["ru", "en"])

      let instruction = RealtimeHubTools.systemInstruction(userLanguages: ["ru", "en"])
      XCTAssertTrue(instruction.contains("speaks ONLY"))
      XCTAssertTrue(instruction.contains("Russian"))
      XCTAssertTrue(instruction.contains("English"))
    }
  }
#endif
