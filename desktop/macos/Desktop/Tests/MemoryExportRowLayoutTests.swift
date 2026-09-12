import AppKit
import OmiTheme
import SwiftUI
import XCTest

@testable import Omi_Computer

@MainActor
final class MemoryExportRowLayoutTests: XCTestCase {
  func testClaudeExportRowStaysSingleLineAtAppsColumnWidth() {
    let status = MemoryExportStatus(
      exportedCount: 0,
      lastExportedAt: nil,
      detailText: nil,
      isConfigured: false,
      hasConnection: false)
    let row = MemoryExportRow(
      destination: .claude,
      titleOverride: "Claude / Claude Code",
      subtitleOverride: nil,
      descriptionOverride: "Claude Code (CLI) or Claude cloud — choose in setup.",
      status: status,
      action: {}
    )

    let width: CGFloat = 320
    let host = NSHostingView(rootView: row.frame(width: width))
    host.frame = NSRect(x: 0, y: 0, width: width, height: 200)
    host.layoutSubtreeIfNeeded()

    XCTAssertLessThan(
      host.fittingSize.height,
      72,
      "Claude / Claude Code export row should keep name, status, and action on one line"
    )
  }
}
