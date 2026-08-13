import AppKit
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
    // A cached frame predates the current exclusion list: the user can add an app to it
    // after that app's frame was captured, and replaying it would leak what they just asked
    // to be forgotten. Re-check against the list as it stands now, not as it stood then.
    if let latest = latestCapturedFrame, SuggestionProbePrivacy.isExcluded(latest.appName) {
      return ["outcome": "skipped_excluded_app"]
    } else if let latest = latestCapturedFrame {
      frame = CapturedFrame(
        jpegData: latest.jpegData,
        appName: appOverride ?? latest.appName,
        windowTitle: windowTitleOverride ?? latest.windowTitle,
        frameNumber: latest.frameNumber,
        captureTime: latest.captureTime,
        screenshotId: latest.screenshotId
      )
    } else if let fallback = await captureActiveWindowRespectingExclusions(
      appOverride: appOverride,
      windowTitleOverride: windowTitleOverride
    ) {
      frame = fallback
    } else if activeAppIsExcluded {
      // Refuse rather than fall through to "no frame": the two are different answers and
      // conflating them would read as a capture hiccup instead of a privacy decision.
      return ["outcome": "skipped_excluded_app"]
    } else {
      return ["outcome": "no_frame_captured"]
    }

    // The probe's own delivery does not need to fan out assistant events; the observable
    // result is the notification itself plus the returned outcome.
    return await assistant.probeEvaluateAndDeliver(frame: frame) { _, _ in }
  }

  /// Whether the frontmost app is one the user has excluded from capture.
  private var activeAppIsExcluded: Bool {
    guard let app = NSWorkspace.shared.frontmostApplication?.localizedName else { return false }
    return SuggestionProbePrivacy.isExcluded(app)
  }

  /// Capture the active window for the probe, honouring the same privacy exclusions the
  /// normal capture path does.
  ///
  /// This fallback exists because `latestCapturedFrame` is nil whenever the user is moving
  /// around — but it is *also* nil precisely when the frontmost app is excluded, since the
  /// capture gate refuses those. Without this check the probe would reach for the shutter
  /// exactly in the apps the user asked Omi never to look at, and send the result to a
  /// model. The excluded case must be decided before anything is captured, not filtered
  /// afterwards.
  private func captureActiveWindowRespectingExclusions(
    appOverride: String?,
    windowTitleOverride: String?
  ) async -> CapturedFrame? {
    let (beforeApp, beforeTitle, beforeWindowID) = await WindowMonitor.getActiveWindowInfoAsync()
    if let beforeApp, SuggestionProbePrivacy.isExcluded(beforeApp) { return nil }
    if activeAppIsExcluded { return nil }

    // Capture *this* window, not "whatever is active when the shutter opens".
    // `captureActiveWindowAsync()` re-resolves the frontmost window internally, so an
    // allowed → excluded → allowed flicker around the call photographs the excluded app
    // while a before/after app comparison sees "allowed" at both ends. Binding the capture
    // to the window ID that was authorised removes the race rather than narrowing it.
    guard let windowID = beforeWindowID else { return nil }
    let service = ScreenCaptureService()
    guard case .success(let image) = await service.captureWindowCGImage(windowID: windowID),
      let jpeg = service.encodeJPEG(from: image)
    else { return nil }

    // Belt and braces: the window ID binds the pixels, and this rejects the case where the
    // app that owns it became excluded while the capture ran.
    let (afterApp, afterTitle, _) = await WindowMonitor.getActiveWindowInfoAsync()
    guard
      SuggestionProbePrivacy.allowsCapture(
        before: beforeApp,
        after: afterApp,
        isExcluded: SuggestionProbePrivacy.isExcluded
      )
    else { return nil }

    return CapturedFrame(
      jpegData: jpeg,
      appName: appOverride ?? beforeApp ?? "Unknown",
      windowTitle: windowTitleOverride ?? beforeTitle ?? afterTitle,
      frameNumber: 0
    )
  }
}

/// The exclusion predicate the probe's fallback capture must satisfy, factored out so it can
/// be exercised without a running app or a real screen.
enum SuggestionProbePrivacy {
  @MainActor
  static func isExcluded(_ appName: String) -> Bool {
    SuggestionAssistantSettings.shared.isAppExcluded(appName)
  }

  /// Whether a fallback capture may be used, given which app was frontmost before the
  /// shutter and which was frontmost after it.
  ///
  /// Checking only before the capture leaves a window: capture is async, and the user can
  /// cmd-tab into an excluded app while it runs, so the pixels that come back can belong to
  /// an app that was never allowed. Both ends must be clear, and a change of app across the
  /// capture is refused outright because the frame cannot be attributed with confidence.
  static func allowsCapture(
    before: String?,
    after: String?,
    isExcluded: (String) -> Bool
  ) -> Bool {
    if let before, isExcluded(before) { return false }
    if let after, isExcluded(after) { return false }
    if let before, let after, before != after { return false }
    return true
  }
}
