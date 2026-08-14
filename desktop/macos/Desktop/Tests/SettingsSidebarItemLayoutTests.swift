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
    // The fixtures the row actually spends around the label, named rather than approximated: the
    // icon column, the gap after it, and the row's own two side paddings. They are the settings-kit
    // metrics now, not generic spacing tokens, and this sum is what decides the sidebar's width —
    // see `SettingsSidebarMetrics.expandedWidth`, which is derived from it.
    let requiredWidth =
      labelWidth + 20 + SettingsGlassMetrics.rowContentSpacing
      + 2 * SettingsGlassMetrics.rowHorizontalPadding

    XCTAssertLessThanOrEqual(
      requiredWidth + SettingsSidebarMetrics.labelSlack,
      SettingsSidebarMetrics.itemAvailableWidth,
      """
      "\(SettingsContentView.SettingsSection.notifications.displayTitle)" needs \
      \(String(format: "%.1f", requiredWidth)) pt plus \(SettingsSidebarMetrics.labelSlack) pt of \
      slack, and the row has \(SettingsSidebarMetrics.itemAvailableWidth). The label does not fail \
      loudly when it runs out — it truncates to "Notifications & P…". The slack is not padding for \
      its own sake: a build whose arithmetic cleared the requirement by 4 pt still truncated, so \
      the fit is asserted with headroom rather than to the last point.
      """
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

  func testPermissionsRowWithMissingNoticeStaysOnOneLine() {
    let plain = itemHeight(section: .permissions, isSelected: false, showsMissingPermissionNotice: false)
    let noticed = itemHeight(section: .permissions, isSelected: true, showsMissingPermissionNotice: true)
    XCTAssertEqual(
      noticed, plain, accuracy: 0.5,
      "the missing-grant mark beside the label must sit in the row, not wrap it")
    XCTAssertLessThan(noticed, 60)
  }

  private func itemHeight(isSelected: Bool) -> CGFloat {
    itemHeight(section: .notifications, isSelected: isSelected, showsMissingPermissionNotice: false)
  }

  private func itemHeight(
    section: SettingsContentView.SettingsSection,
    isSelected: Bool,
    showsMissingPermissionNotice: Bool
  ) -> CGFloat {
    let host = NSHostingView(
      rootView: SettingsSidebarItem(
        section: section,
        isSelected: isSelected,
        iconWidth: 20,
        showsMissingPermissionNotice: showsMissingPermissionNotice,
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
