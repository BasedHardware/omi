import XCTest

@testable import Omi_Computer

/// The developer-keys section hints which BYOK keys are still missing while
/// only some of the four are entered, so someone who pastes a single key
/// learns the free plan needs all four at the same time.
final class BYOKIncompleteHintTests: XCTestCase {
  func testHintOnlyForPartiallyFilledKeySet() {
    let hint = byokMissingKeysHint(["sk-test", "", "", ""])
    XCTAssertEqual(
      hint,
      "Still missing: Anthropic, Gemini, Deepgram. All 4 keys must be entered at the same time to activate the free plan."
    )
    XCTAssertNil(byokMissingKeysHint(["", "", "", ""]), "blank form shows no hint")
    XCTAssertNil(byokMissingKeysHint(["a", "b", "c", "d"]), "complete form shows no hint")
  }
}
