import XCTest
import OmiTheme

final class OmiTransparencyTests: XCTestCase {
  func testMaterialIsUsedWhenTransparencyIsAllowed() {
    XCTAssertTrue(OmiTransparency.shouldUseMaterial(reduceTransparency: false))
  }

  func testOpaqueFallbackIsUsedWhenTransparencyIsReduced() {
    XCTAssertFalse(OmiTransparency.shouldUseMaterial(reduceTransparency: true))
  }
}
