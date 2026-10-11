import Foundation

/// Derives today's meeting-detection result and call identities from one snapshot.
enum MeetingCallObservation {
  /// Same answer `ensureMeetingDetector` used to compute from two probes.
  ///
  /// macOS 14.4+: a native call app or browser running input, plus the browser
  /// window-title fallback in Only Meetings (a muted browser drops the mic).
  /// macOS 14.0–14.3 has no per-process input API, so a browser call window is
  /// the signal for every mode other than Off.
  static func isDetected(
    snapshot: CallAudioSnapshot,
    mode: AssistantSettings.AudioRecordingMode,
    processInputAPIAvailable: Bool
  ) -> Bool {
    if processInputAPIAvailable {
      if snapshot.processes.contains(where: {
        $0.isRunningInput && ConferencingApps.isCallSurface(bundleID: $0.bundleID)
      }) {
        return true
      }
      return mode == .onlyMeetings
        && snapshot.browserWindowTitles.contains(where: ConferencingApps.isBrowserCallTitle)
    }
    return mode != .off
      && snapshot.browserWindowTitles.contains(where: ConferencingApps.isBrowserCallTitle)
  }

  /// `meet:<code>` from on-screen Meet titles, and `nativeIdentity(bundle)` for
  /// each native call app running input. Browsers get no app identity.
  static func identities(
    snapshot: CallAudioSnapshot,
    processInputAPIAvailable: Bool,
    nativeIdentity: (String) -> String
  ) -> Set<String> {
    var identities = Set<String>()
    if processInputAPIAvailable {
      // Helpers resolve to their app (`com.hnc.discord.helper.renderer` → `com.hnc.discord`), so
      // an app and its helper never look like two calls.
      for process in snapshot.processes where process.isRunningInput {
        if let appID = ConferencingApps.nativeCallAppID(bundleID: process.bundleID) {
          identities.insert(nativeIdentity(appID))
        }
      }
    }
    for title in snapshot.browserWindowTitles {
      if let code = ConferencingApps.meetingCode(fromTitle: title) {
        identities.insert("meet:\(code)")
      }
    }
    return identities
  }

  /// 1s while a native call app or browser holds the mic, otherwise the idle interval.
  static func pollInterval(
    snapshot: CallAudioSnapshot,
    idle: TimeInterval,
    active: TimeInterval
  ) -> TimeInterval {
    let micHeld = snapshot.processes.contains {
      $0.isRunningInput && ConferencingApps.isCallSurface(bundleID: $0.bundleID)
    }
    return micHeld ? active : idle
  }
}
