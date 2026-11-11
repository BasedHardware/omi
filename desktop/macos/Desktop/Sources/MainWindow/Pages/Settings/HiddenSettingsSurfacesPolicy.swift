import Foundation
import SwiftUI

/// The deliberately hidden Settings surfaces (Nik, 2026-08-25) and the controls
/// that used to reach them. This is the seam production views consult, so the
/// hide is enforced by one typed decision instead of scattered comment-outs —
/// and so a test can pin the decision itself: restoring the gear or the
/// deep-link highlight requires flipping a value a regression test owns.
/// Do NOT flip these without asking Nik: 73c7f85fbc already "fixed back" a
/// previous hide that looked like dead code.
enum HiddenSettingsSurfacesPolicy {
  /// Setting ids whose panes/rows are not rendered.
  static let hiddenSettingIds: Set<String> = [
    "advanced.taskassistant",
    "advanced.insightassistant",
    "advanced.memoryassistant",
    "floatingbar.notificationpreviews",
    "floatingbar.background",
    "floatingbar.draggable",
  ]

  /// The Tasks-page header gear deep-linked to the hidden Task Assistant pane.
  static let tasksHeaderShowsSettingsGear = false

  /// What `.navigateToTaskSettings` may highlight after opening Advanced.
  /// nil while the Task Assistant pane is hidden — highlighting a card that
  /// does not render scrolls to nothing.
  static var taskSettingsHighlight: String? {
    highlightIfVisible("advanced.taskassistant")
  }

  /// A deep-link may only highlight a card that actually renders.
  static func highlightIfVisible(_ settingId: String) -> String? {
    hiddenSettingIds.contains(settingId) ? nil : settingId
  }
}

/// The Tasks-header settings gear as a component, so its visibility decision is
/// exercised by hosting the REAL view in a test rather than by reading source.
/// `visible` defaults to the policy; tests force it on to prove the probe can
/// see the gear when it exists, making the production-default absence meaningful.
struct TasksHeaderSettingsGear: View {
  var visible: Bool = HiddenSettingsSurfacesPolicy.tasksHeaderShowsSettingsGear
  let action: () -> Void

  var body: some View {
    if visible {
      Button(action: action) {
        Image(systemName: "gearshape")
      }
      .buttonStyle(.plain)
      .accessibilityIdentifier("tasks.settingsGear")
    }
  }
}

/// The `.navigateToTaskSettings` transition as data: the section to open and
/// what (if anything) to highlight. `SettingsPage.onReceive` applies exactly
/// this value, so the test drives the production transition, not a copy.
enum SettingsDeepLinkTransition {
  static func taskSettings() -> (section: String, highlight: String?) {
    ("Advanced", HiddenSettingsSurfacesPolicy.taskSettingsHighlight)
  }
}
