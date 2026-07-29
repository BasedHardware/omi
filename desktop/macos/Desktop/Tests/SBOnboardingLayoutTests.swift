import CoreGraphics
import XCTest

@testable import Omi_Computer

final class SBOnboardingLayoutTests: XCTestCase {
  func testPanelKeepsItsDesignedSizeWhenThereIsRoom() {
    XCTAssertEqual(
      SBOnboardingPanelLayout.size(in: CGSize(width: 1_200, height: 680)),
      SBOnboardingPanelLayout.maximumSize
    )
  }

  func testPanelStaysInsideCompactWindowContent() {
    let availableSize = CGSize(width: 480, height: 420)
    let panelSize = SBOnboardingPanelLayout.size(in: availableSize)

    XCTAssertEqual(panelSize.width, 432)
    XCTAssertEqual(panelSize.height, 380)
    XCTAssertLessThanOrEqual(panelSize.width + SBOnboardingPanelLayout.horizontalInset * 2, availableSize.width)
    XCTAssertLessThanOrEqual(panelSize.height + SBOnboardingPanelLayout.verticalInset * 2, availableSize.height)
  }
}
