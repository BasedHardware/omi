import Foundation

/// Derives today's meeting-detection result and call identities from one snapshot.
enum MeetingCallObservation {
  /// Meeting evidence is stricter than the dictation suppression call-surface catalog.
  /// Dedicated conferencing apps keep input-only detection: output activity is not
  /// guaranteed while joining or when remote participants are silent.
  static func nativeApps(snapshot: CallAudioSnapshot) -> Set<String> {
    let inputs = Set(
      snapshot.processes.filter(\.isRunningInput).compactMap {
        ConferencingApps.nativeCallAppID(bundleID: $0.bundleID)
      })
    let outputs = Set(
      snapshot.processes.filter(\.isRunningOutput).compactMap {
        ConferencingApps.nativeCallAppID(bundleID: $0.bundleID)
      })
    return inputs.filter { app in
      !isMessagingApp(app) || outputs.contains(app)
    }
  }

  private static func isMessagingApp(_ app: String) -> Bool {
    ConferencingApps.telegramBundleIDs.contains(app) || app.hasPrefix("com.hnc.discord")
      || app == "com.tinyspeck.slackmacgap" || app == "net.whatsapp.whatsapp"
  }

  /// Canonical browser family also pairs window owners with audio helpers. Safari's
  /// WebKit GPU audio process has no Safari prefix, so it needs an explicit alias.
  static func browserFamily(_ bundle: String) -> String? {
    let lower = bundle.lowercased()
    if lower.hasPrefix("com.apple.webkit.gpu") { return "com.apple.safari" }
    return ConferencingApps.browserBundleIDPrefixes.first { lower.hasPrefix($0) }
  }

  static func liveBrowserWindows(
    snapshot: CallAudioSnapshot, processInputAPIAvailable: Bool
  ) -> [CallAudioBrowserWindow] {
    snapshot.browserWindows.filter { window in
      guard ConferencingApps.isBrowserCallTitle(window.title) else { return false }
      guard processInputAPIAvailable else { return true }
      return snapshot.processes.contains {
        ($0.isRunningInput || $0.isRunningOutput)
          && browserFamily($0.bundleID) == browserFamily(window.bundleID)
          && browserFamily(window.bundleID) != nil
      }
    }
  }

  static func isDetected(
    snapshot: CallAudioSnapshot,
    mode: AssistantSettings.AudioRecordingMode,
    processInputAPIAvailable: Bool
  ) -> Bool {
    if processInputAPIAvailable {
      if !nativeApps(snapshot: snapshot).isEmpty { return true }
      let windows = liveBrowserWindows(snapshot: snapshot, processInputAPIAvailable: true)
      let browserMic = snapshot.processes.contains { process in
        process.isRunningInput && browserFamily(process.bundleID) != nil
          && (!snapshot.browserTitlesReadable
            || windows.contains {
              browserFamily($0.bundleID) == browserFamily(process.bundleID)
            })
      }
      return browserMic || (mode == .onlyMeetings && !windows.isEmpty)
    }
    // 14.0–14.3 has no process audio activity API: retain the title-only fallback.
    return mode != .off
      && !liveBrowserWindows(snapshot: snapshot, processInputAPIAvailable: false).isEmpty
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
      for appID in nativeApps(snapshot: snapshot) {
        identities.insert(nativeIdentity(appID))
      }
    }
    for window in liveBrowserWindows(snapshot: snapshot, processInputAPIAvailable: processInputAPIAvailable) {
      if let code = ConferencingApps.meetingCode(fromTitle: window.title) {
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

/// Timing shared by meeting confirmation and the deferred note-taking card.
enum MeetingDetectionTiming {
  /// Sustained positive evidence before conversation rotation; capture remains immediate.
  static let confirmationPeriod: TimeInterval = 10
  /// Wait after confirmation before announcing. Calls ending earlier never show a card.
  static let noticeDelay: TimeInterval = 35
}
