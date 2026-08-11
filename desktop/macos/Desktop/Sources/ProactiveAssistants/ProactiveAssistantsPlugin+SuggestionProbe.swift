import Foundation

/// Automation entry point for the suggestion nudge.
///
/// Lives outside `ProactiveAssistantsPlugin.swift` so debug tooling does not grow an
/// already-oversized product file, and because this is a test seam rather than runtime
/// behaviour: nothing in the app calls it, only the automation bridge does.
extension ProactiveAssistantsPlugin {
  /// Drive the suggestion assistant's grounding → evaluation → delivery path on the most
  /// recent captured frame, optionally relabelling which app/window it came from so a
  /// leisure context can be probed without stealing the user's focus for 30 seconds.
  func probeSuggestionNudge(
    appOverride: String?,
    windowTitleOverride: String?
  ) async -> [String: String] {
    let registered = AssistantCoordinator.shared.assistant(withIdentifier: "suggestion")
    guard let assistant = registered as? SuggestionAssistant else {
      return ["outcome": "assistant_unavailable"]
    }
    guard let latest = latestCapturedFrame else {
      return ["outcome": "no_frame_captured"]
    }

    let frame = CapturedFrame(
      jpegData: latest.jpegData,
      appName: appOverride ?? latest.appName,
      windowTitle: windowTitleOverride ?? latest.windowTitle,
      frameNumber: latest.frameNumber,
      captureTime: latest.captureTime,
      screenshotId: latest.screenshotId
    )

    // The probe's own delivery does not need to fan out assistant events; the observable
    // result is the notification itself plus the returned outcome.
    return await assistant.probeEvaluateAndDeliver(frame: frame) { _, _ in }
  }
}
