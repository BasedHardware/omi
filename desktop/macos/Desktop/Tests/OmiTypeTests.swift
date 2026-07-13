import XCTest
import OmiTheme

final class OmiTypeTests: XCTestCase {
  func testGeistTypefaceIsBundledAndRegisterable() {
    XCTAssertEqual(OmiType.familyName, "Geist")
    XCTAssertTrue(OmiType.registerBundledTypeface())
  }
}
