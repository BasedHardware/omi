import XCTest

@testable import Omi_Computer

final class InterjectFeatureTests: XCTestCase {
  override func tearDown() {
    InterjectFeature.testOverride = nil
    super.tearDown()
  }

  func testReplyHintUsesTheUsersPTTTokens() {
    XCTAssertEqual(InterjectReplyHint.text(tokens: ["⌥"]), "hold ⌥ to reply")
    XCTAssertEqual(InterjectReplyHint.text(tokens: ["Right ⌘"]), "hold Right ⌘ to reply")
    XCTAssertEqual(InterjectReplyHint.text(tokens: []), "hold Option to reply")
  }

  func testListeningChipNamesTheCard() {
    XCTAssertEqual(
      InterjectReplyHint.listeningChip(title: "Thursday standup"),
      "replying to: Thursday standup"
    )
    XCTAssertEqual(InterjectReplyHint.listeningChip(title: "  "), "replying to the last card")
  }

  func testTimeoutAttentionSplitsNeverSeenFromReadAndIgnored() {
    XCTAssertEqual(InterjectAttention.timeoutAttention(didHover: false), .neverSeen)
    XCTAssertEqual(InterjectAttention.timeoutAttention(didHover: true), .readAndIgnored)
  }

  func testFeatureUsesTheSharedBetaDogfoodDecision() {
    XCTAssertEqual(InterjectFeature.killSwitchFlagName, "\(InterjectFeature.flagName)_kill")
    XCTAssertFalse(
      BetaDogfoodRollout.isEnabled(
        isNonProduction: true,
        isBetaProductionBundle: false,
        localOverrideValue: nil,
        isFlagEnabled: true,
        isKillSwitchEnabled: false
      ),
      "non-production stays off unless OMI_FORCE_INTERJECT=1"
    )
    XCTAssertTrue(
      BetaDogfoodRollout.isEnabled(
        isNonProduction: false,
        isBetaProductionBundle: true,
        localOverrideValue: nil,
        isFlagEnabled: false,
        isKillSwitchEnabled: false
      )
    )
    XCTAssertFalse(
      BetaDogfoodRollout.isEnabled(
        isNonProduction: false,
        isBetaProductionBundle: false,
        localOverrideValue: nil,
        isFlagEnabled: false,
        isKillSwitchEnabled: false
      ),
      "stable stays dark — flag off is today's behavior"
    )
  }

  @MainActor
  func testOverridePinsTheRuntimeFlagForTests() {
    InterjectFeature.testOverride = true
    XCTAssertTrue(InterjectFeature.isEnabled)
    InterjectFeature.testOverride = false
    XCTAssertFalse(InterjectFeature.isEnabled)
  }
}
