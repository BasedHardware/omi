import AppKit
import SwiftUI
import XCTest

@testable import Omi_Computer

@MainActor
final class DesktopUpdateStatusChipLayoutTests: XCTestCase {
  func testProgressIndicatorDoesNotReserveLinearBarWidth() {
    let constrained = NSHostingView(
      rootView: DesktopUpdateStatusProgressIndicator().fixedSize()
    ).fittingSize

    XCTAssertEqual(constrained.width, 16, accuracy: 0.5)
    XCTAssertEqual(constrained.height, 16, accuracy: 0.5)

    let defaultMacProgress = NSHostingView(
      rootView: ProgressView().controlSize(.small).fixedSize()
    ).fittingSize.width
    // On macOS the unstyled control is a linear bar. If a future SDK already
    // hugs, this still passes; the chip-width test below is the user-visible
    // contract.
    if defaultMacProgress > 40 {
      XCTAssertLessThan(constrained.width, defaultMacProgress)
    }
  }

  func testDownloadingChipHugsCaptionInsteadOfLeavingABlankGap() {
    let downloading = chipWidth(for: .downloading(version: "0.12.183"))
    let available = chipWidth(for: .updateAvailable(version: "0.12.183"))

    // "Downloading v0.12.183…" is longer than "Update v0.12.183", but a default
    // macOS ProgressView would add ~100pt of empty bar. Keep the extra under
    // one caption-sized spinner plus a little tracking.
    XCTAssertLessThan(downloading - available, 80)
    XCTAssertLessThan(downloading, 230)
  }

  private func chipWidth(for kind: DesktopUpdateStatusPresentation.Kind) -> CGFloat {
    NSHostingView(
      rootView: DesktopUpdateStatusChipLabel(kind: kind).fixedSize()
    ).fittingSize.width
  }
}
