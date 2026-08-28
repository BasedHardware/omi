import XCTest

@testable import Omi_Computer

/// Nik hid six settings surfaces on 2026-08-25 (the Task/Insight/Memory Assistant
/// panes and the Notification Previews / Background Style / Draggable Floating Bar
/// rows). A previous hide of the same panes was "fixed back" by 73c7f85fbc because
/// nothing recorded that the absence was deliberate. These tests are that record:
/// they pin the reachable surfaces — search index and deep-links — that would
/// otherwise quietly point at panes that no longer render.
final class HiddenSettingsSurfacesTests: XCTestCase {

  /// Settings search must not offer rows the pane no longer renders — a search hit
  /// that scrolls to nothing reads as a broken app, and is exactly the dangling
  /// door that got the last hide reverted.
  func testSearchIndexOffersNoHiddenFloatingBarRows() {
    let ids = Set(SettingsSearchItem.allSearchableItems.map(\.settingId))
    for hidden in ["floatingbar.notificationpreviews", "floatingbar.background", "floatingbar.draggable"] {
      XCTAssertFalse(ids.contains(hidden), "\(hidden) is hidden from Settings; its search entry must stay out")
    }
  }

  /// The assistant panes never had search entries; keep it that way while hidden.
  func testSearchIndexOffersNoAssistantPanes() {
    let ids = Set(SettingsSearchItem.allSearchableItems.map(\.settingId))
    for hidden in ["advanced.taskassistant", "advanced.insightassistant", "advanced.memoryassistant"] {
      XCTAssertFalse(ids.contains(hidden), "\(hidden) pane is hidden; a search entry would deep-link to nothing")
    }
  }

  /// Surfaces that are NOT hidden must keep their search entries — this suite
  /// guards the six hidden ids, not the pane wholesale.
  func testRemainingFloatingBarRowsKeepTheirSearchEntries() {
    let ids = Set(SettingsSearchItem.allSearchableItems.map(\.settingId))
    for kept in ["floatingbar.show", "floatingbar.typedvoiceanswers", "floatingbar.screenshare"] {
      XCTAssertTrue(ids.contains(kept), "\(kept) is still rendered and must stay searchable")
    }
  }
}
