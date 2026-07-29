import AppKit
import OmiTheme
import SwiftUI
import XCTest

@testable import Omi_Computer

@MainActor
final class SettingsSidebarItemLayoutTests: XCTestCase {
  func testMergedNotificationsAndPrivacyLabelStaysOnOneLineWhenSelected() {
    let labelWidth = NSHostingView(
      rootView: Text(SettingsContentView.SettingsSection.notifications.displayTitle)
        .scaledFont(size: OmiType.body, weight: .medium)
        .fixedSize()
    ).fittingSize.width
    let requiredWidth = labelWidth + 20 + OmiSpacing.md + 2 * OmiSpacing.md

    XCTAssertLessThanOrEqual(
      requiredWidth,
      SettingsSidebarMetrics.itemAvailableWidth,
      "the merged label must fit in the fixed settings-sidebar row"
    )

    let unselectedHeight = itemHeight(isSelected: false)
    let selectedHeight = itemHeight(isSelected: true)

    XCTAssertEqual(
      selectedHeight,
      unselectedHeight,
      accuracy: 0.5,
      "selection styling must not make the merged navigation label wrap"
    )
    XCTAssertLessThan(
      selectedHeight,
      60,
      "the merged navigation label should retain the row's single-line height"
    )
  }

  func testNotificationsLabelTruncatesGracefullyAtConstrainedWidth() {
    // At a narrower-than-default width the label must not overflow the row —
    // it should truncate with an ellipsis rather than being clipped or wrapped.
    let narrowWidth: CGFloat = 120
    let host = NSHostingView(
      rootView: SettingsSidebarItem(
        section: .notifications,
        isSelected: true,
        iconWidth: 20,
        onTap: {}
      )
      .frame(width: narrowWidth)
    )
    host.frame = NSRect(x: 0, y: 0, width: narrowWidth, height: 100)
    host.layoutSubtreeIfNeeded()

    // The item should remain a single line (no wrapping) even when truncated.
    XCTAssertLessThan(
      host.fittingSize.height,
      60,
      "constrained sidebar label should stay on one line (truncate, not wrap)"
    )
  }

  private func itemHeight(isSelected: Bool) -> CGFloat {
    let host = NSHostingView(
      rootView: SettingsSidebarItem(
        section: .notifications,
        isSelected: isSelected,
        iconWidth: 20,
        onTap: {}
      )
      .frame(width: SettingsSidebarMetrics.itemAvailableWidth)
    )
    host.frame = NSRect(
      x: 0,
      y: 0,
      width: SettingsSidebarMetrics.itemAvailableWidth,
      height: 100
    )
    host.layoutSubtreeIfNeeded()
    return host.fittingSize.height
  }
}
