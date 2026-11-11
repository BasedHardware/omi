import SwiftUI
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

  // MARK: - The production seams

  /// The Tasks-page header consults this policy for the gear. Restoring the gear
  /// requires flipping the value this test owns — that is the point.
  func testTasksHeaderDoesNotShowTheSettingsGear() {
    XCTAssertFalse(HiddenSettingsSurfacesPolicy.tasksHeaderShowsSettingsGear)
  }

  /// `.navigateToTaskSettings` highlights whatever this returns; while the Task
  /// Assistant pane is hidden it must be nil — a highlight that targets a card
  /// that does not render scrolls to nothing.
  func testTaskSettingsDeepLinkHighlightsNothingWhileThePaneIsHidden() {
    XCTAssertNil(HiddenSettingsSurfacesPolicy.taskSettingsHighlight)
  }

  /// The general rule the highlight rides on: a deep-link may never highlight a
  /// hidden card, and passes visible ones through untouched.
  func testDeepLinksNeverHighlightHiddenCards() {
    for hidden in HiddenSettingsSurfacesPolicy.hiddenSettingIds {
      XCTAssertNil(HiddenSettingsSurfacesPolicy.highlightIfVisible(hidden))
    }
    XCTAssertEqual(HiddenSettingsSurfacesPolicy.highlightIfVisible("advanced.goals"), "advanced.goals")
  }

  /// The policy's hidden set and the search index must agree: every policy-hidden
  /// id is absent from search.
  func testSearchIndexAgreesWithThePolicy() {
    let searchable = Set(SettingsSearchItem.allSearchableItems.map(\.settingId))
    XCTAssertTrue(searchable.isDisjoint(with: HiddenSettingsSurfacesPolicy.hiddenSettingIds))
  }

  // MARK: - The real view's render decision

  /// Executes TasksHeaderSettingsGear's REAL `body` builder — the production
  /// render decision — and reports whether it produced the button. A lone `if`
  /// in a ViewBuilder yields an Optional view: nil means nothing renders.
  /// (SwiftUI's accessibility tree does not materialize in this CLI test host,
  /// so the body value is the deepest reliably executable seam.)
  @MainActor
  private func gearBodyProducesButton(_ view: TasksHeaderSettingsGear) -> Bool {
    let mirror = Mirror(reflecting: view.body)
    if mirror.displayStyle == .optional { return mirror.children.first != nil }
    return true
  }

  /// Under the production policy the header component renders nothing; forced
  /// visible it renders the button — the control case that proves the probe
  /// distinguishes the two, so the production absence is meaningful.
  @MainActor
  func testGearBodyRendersNothingUnderProductionPolicyAndButtonWhenForced() {
    XCTAssertFalse(
      gearBodyProducesButton(TasksHeaderSettingsGear(action: {})),
      "production policy: the header's gear body must render nothing")
    XCTAssertTrue(
      gearBodyProducesButton(TasksHeaderSettingsGear(visible: true, action: {})),
      "control case: forced visible must render the button")
  }

  /// Drives the exact transition value SettingsPage applies on
  /// `.navigateToTaskSettings`: it opens Advanced and highlights nothing while
  /// the Task Assistant pane is hidden.
  func testTaskSettingsTransitionOpensAdvancedAndHighlightsNothing() {
    let transition = SettingsDeepLinkTransition.taskSettings()
    XCTAssertEqual(transition.section, "Advanced")
    XCTAssertNil(transition.highlight)
  }
}
