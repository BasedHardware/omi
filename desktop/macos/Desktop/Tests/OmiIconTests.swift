import XCTest
import OmiTheme

final class OmiIconTests: XCTestCase {
  func testEveryDashboardIconHasABundledVectorPDF() {
    let missing = OmiIconName.allCases.filter { !$0.hasBundledVector }
    XCTAssertTrue(missing.isEmpty, "Missing Lucide vectors: \(missing)")
  }
}
