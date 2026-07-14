import XCTest
import OmiTheme

final class OmiIconTests: XCTestCase {
  func testEveryDashboardIconHasABundledVector() {
    let missing = OmiIconName.allCases.filter { !$0.hasBundledVector }
    XCTAssertTrue(missing.isEmpty, "Missing Lucide vectors: \(missing)")
  }
}
