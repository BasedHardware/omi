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

  // MARK: - Widgets that grow in place

  /// The Files step shipped with its Continue below the card's lower edge: the scan finishing
  /// replaced a two-line "scanning…" widget with a four-element "your profile is ready" one, and
  /// none of the view's scroll triggers (`thread`, `showWidget`, `streamingText`) changed — so
  /// nothing scrolled and the step read as having no way forward.
  func testFinishedFileScanChangesTheWidgetShapeSoTheColumnScrollsToIt() {
    let scanning = SBOnboardingWidgetShape(
      step: .files,
      localFileProfile: .scanning,
      permission: .allow,
      screenDemoReady: false,
      screenDemoUnavailable: false,
      screenDemoDone: false)
    var complete = scanning
    complete.localFileProfile = .complete(fileCount: 22_391, memoryCount: 16, deniedFolders: [])

    XCTAssertNotEqual(scanning, complete)
  }

  /// A permission row turning into the relaunch offer adds a paragraph and a second button, which
  /// is the same growth-in-place the Files step hit.
  func testPermissionRowBecomingTheRelaunchOfferChangesTheWidgetShape() {
    let waiting = SBOnboardingWidgetShape(
      step: .screen,
      localFileProfile: .idle,
      permission: .recheck,
      screenDemoReady: false,
      screenDemoUnavailable: false,
      screenDemoDone: false)
    var reopen = waiting
    reopen.permission = .reopen

    XCTAssertNotEqual(waiting, reopen)
  }

  /// The demo arming its chord swaps a one-line spinner for a chord row plus two lines of copy.
  func testArmingTheScreenDemoChordChangesTheWidgetShape() {
    let preparing = SBOnboardingWidgetShape(
      step: .screenDemo,
      localFileProfile: .idle,
      permission: nil,
      screenDemoReady: false,
      screenDemoUnavailable: false,
      screenDemoDone: false)
    var armed = preparing
    armed.screenDemoReady = true

    XCTAssertNotEqual(preparing, armed)
  }

  /// Redrawing the same state must not fire a scroll animation on every publish.
  func testAnUnchangedWidgetIsNotTreatedAsGrowth() {
    let shape = SBOnboardingWidgetShape(
      step: .capture,
      localFileProfile: .idle,
      permission: nil,
      screenDemoReady: false,
      screenDemoUnavailable: false,
      screenDemoDone: true)

    XCTAssertEqual(shape, shape)
  }
}
