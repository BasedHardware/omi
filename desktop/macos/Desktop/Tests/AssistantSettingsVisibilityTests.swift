import XCTest

@testable import Omi_Computer

/// The screen assistants (Task, Insight, Memory, Suggestions) are frame-driven
/// only — no transcript or conversation input — so while
/// `assistantFrameProcessingEnabled` is false they can produce nothing. Their
/// settings must not be offered as controls that silently do nothing, and a
/// user who had them on must keep that choice for when frames return.
final class AssistantSettingsVisibilityTests: XCTestCase {
  private let assistantEnabledKeys = [
    "taskAssistantEnabled",
    "adviceAssistantEnabled",
    "memoryAssistantEnabled",
    "suggestionAssistantEnabled",
  ]

  private func settingsSource(_ name: String) throws -> String {
    let sourceURL = URL(fileURLWithPath: #filePath)
      .deletingLastPathComponent()
      .deletingLastPathComponent()
      .appendingPathComponent("Sources/MainWindow/Pages/Settings/Sections/\(name)")
    // omi-test-quality: source-inspection -- static contract: SwiftUI pane composition has no headless seam; this pins the frame-processing gate on the panes that render the assistant controls.
    return try String(contentsOf: sourceURL, encoding: .utf8)
  }

  /// Static checker: the behavioral contract is SwiftUI view composition, which
  /// has no headless seam here. It pins the gate to the two panes that render
  /// the controls, so removing the gate cannot pass unnoticed.
  func testAssistantSettingsPanesAreGatedOnFrameProcessing() throws {
    let advanced = try settingsSource("SettingsContentView+Advanced.swift")
    XCTAssertTrue(
      advanced.contains("if ProactiveCapturePolicy.assistantFrameProcessingEnabled {"),
      "the assistant cards must not render while their frames are discarded")
    for subsection in [
      "taskAssistantSubsection",
      "insightAssistantSubsection",
      "memoryAssistantSubsection",
      "analysisThrottleSubsection",
    ] {
      XCTAssertTrue(advanced.contains(subsection), "\(subsection) should still exist behind the gate")
    }

    let notifications = try settingsSource("SettingsContentView+NotificationsPrivacy.swift")
    XCTAssertTrue(
      notifications.contains("if ProactiveCapturePolicy.assistantFrameProcessingEnabled {"),
      "assistant notification rows must not render while no assistant can fire")
  }

  /// Hiding the controls must not rewrite anyone's stored preference: the
  /// choice has to survive so restoring frame processing restores the product
  /// exactly as the user left it.
  @MainActor
  func testHidingTheControlsLeavesPersistedPreferencesUntouched() {
    let defaults = UserDefaults.standard
    let originals = assistantEnabledKeys.map { ($0, defaults.object(forKey: $0)) }
    defer {
      for (key, value) in originals {
        if let value { defaults.set(value, forKey: key) } else { defaults.removeObject(forKey: key) }
      }
    }

    for key in assistantEnabledKeys {
      defaults.set(true, forKey: key)
    }

    // Reading the settings singletons is what the (now hidden) panes did; the
    // stored choice must be reported back unchanged.
    XCTAssertTrue(TaskAssistantSettings.shared.isEnabled)
    XCTAssertTrue(InsightAssistantSettings.shared.isEnabled)
    XCTAssertTrue(MemoryAssistantSettings.shared.isEnabled)

    for key in assistantEnabledKeys {
      XCTAssertTrue(
        defaults.bool(forKey: key),
        "\(key) must survive the controls being hidden so the user's choice is restored with frames")
    }
  }
}
