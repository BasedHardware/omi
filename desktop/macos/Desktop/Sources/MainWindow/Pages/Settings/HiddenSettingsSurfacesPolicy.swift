import Foundation

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
