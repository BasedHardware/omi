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

    // `latestCapturedFrame` is cleared on every app switch, so on a machine someone is
    // actively using it is nil far more often than not — probing against it lost a race
    // with the user 18 times running. Fall back to capturing the active window here so the
    // probe tests the suggestion path rather than the capture pipeline's timing.
    let frame: CapturedFrame
    if let latest = latestCapturedFrame {
      frame = CapturedFrame(
        jpegData: latest.jpegData,
        appName: appOverride ?? latest.appName,
        windowTitle: windowTitleOverride ?? latest.windowTitle,
        frameNumber: latest.frameNumber,
        captureTime: latest.captureTime,
        screenshotId: latest.screenshotId
      )
    } else if let jpeg = await ScreenCaptureService().captureActiveWindowAsync() {
      let (activeApp, activeTitle, _) = await WindowMonitor.getActiveWindowInfoAsync()
      frame = CapturedFrame(
        jpegData: jpeg,
        appName: appOverride ?? activeApp ?? "Unknown",
        windowTitle: windowTitleOverride ?? activeTitle,
        frameNumber: 0
      )
    } else {
      return ["outcome": "no_frame_captured"]
    }

    // The probe's own delivery does not need to fan out assistant events; the observable
    // result is the notification itself plus the returned outcome.
    return await assistant.probeEvaluateAndDeliver(frame: frame) { _, _ in }
  }
}
