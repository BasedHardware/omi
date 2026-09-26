@preconcurrency import CoreAudio
import CoreGraphics
import Foundation

/// Shared catalog of conferencing / video-call apps plus the logic for deciding whether a
/// window (or the whole screen) indicates an active call ("meeting").
///
/// Single source of truth shared by:
///  - `MeetingDetector`, which gates meetings-only capture and rotates Always-mode conversations, and
///  - `ProactiveAssistantsPlugin`, which throttles screen capture while a call app is frontmost.
enum ConferencingApps {

  /// Shipping and legacy Telegram bundle IDs shared by meeting detection and proactive capture.
  /// Keep both because existing installations may still report the legacy identifier.
  static let telegramBundleIDs: Set<String> = [
    "com.tdesktop.telegram",
    "ru.keepcoder.telegram",
  ]

  /// Chat apps whose native voice/video calls are meetings. Identity extraction
  /// treats a name-shaped call-window title as roster-equivalent only for this set —
  /// not for browsers, where a capitalized tab title is usually something else.
  static let messagingCallApps: Set<String> = [
    "Telegram",
    "Discord",
    "Slack",
    "WhatsApp",
  ]

  /// Apps that host audio/video calls. Matched by app/owner name, which is
  /// available from `NSRunningApplication` and `CGWindowList` **without** Screen Recording
  /// permission.
  ///
  /// Includes chat apps whose calls hold the microphone (Discord voice, Slack huddles,
  /// WhatsApp calls, Telegram calls) — same shape as Teams. Meeting gating still requires
  /// the app to be *using the microphone* (`nativeCallBundleIDs` + `callAppIsUsingMicrophone()`),
  /// so an idle Slack/Discord/WhatsApp/Telegram window does not start capture; this
  /// owner-name list only feeds the call-window/share-indicator screen paths.
  static let nativeCallApps: Set<String> = Set([
    "Microsoft Teams",
    "zoom.us",
    "FaceTime",
    "Webex",
    "Cisco Webex Meetings",
    "GoTo Meeting",
    "GoToMeeting",
  ]).union(messagingCallApps)

  /// Whether `appName` is a native messaging-call app (Telegram / Discord / Slack / WhatsApp).
  static func isMessagingCallApp(appName: String) -> Bool {
    let lower = appName.lowercased()
    return messagingCallApps.contains { $0.lowercased() == lower }
  }

  /// Canonical platform label for a native call app name, or nil if it is not in the catalog.
  static func nativeCallPlatform(forAppName appName: String) -> String? {
    let lower = appName.lowercased()
    return nativeCallApps.first { $0.lowercased() == lower }
  }

  /// Browser app names. Browser-based calls are matched by window title.
  static let browserApps: Set<String> = [
    "Google Chrome",
    "Arc",
    "Safari",
    "Firefox",
    "Microsoft Edge",
    "Brave Browser",
    "Opera",
  ]

  /// Window-title keywords that indicate a browser-based call.
  static let browserCallKeywords: [String] = [
    "Google Meet",
    "meet.google.com",
    "Teams - Microsoft",  // Teams web app
  ]

  /// A joined Google Meet tab is titled with the bare meeting code ("Meet - amc-iajq-asx"),
  /// which contains none of `browserCallKeywords`. Kept here rather than in a caller so this
  /// stays the single conferencing catalog — the divergence #11832 consolidated.
  static let browserCallTitlePattern = "(?i)^meet\\s*[-\u{2013}]\\s*[a-z]{3}-[a-z]{4}-[a-z]{3}\\b"

  /// Whether a window title names a browser-hosted call, by keyword or by bare meeting code.
  static func isBrowserCallTitle(_ title: String) -> Bool {
    let lower = title.lowercased()
    for keyword in browserCallKeywords where lower.contains(keyword.lowercased()) {
      return true
    }
    return title.range(of: browserCallTitlePattern, options: .regularExpression) != nil
  }

  /// The meeting code a joined Google Meet tab is titled with ("Meet - amc-iajq-asx" gives
  /// "amc-iajq-asx"), or nil for any other title. Two Meets back to back differ only here.
  static func meetingCode(fromTitle title: String) -> String? {
    guard let range = title.range(of: browserCallTitlePattern, options: .regularExpression) else { return nil }
    return String(title[range].suffix(12)).lowercased()
  }

  /// Bundle IDs (lowercased) of native conferencing apps, used for mic-in-use ("in a call")
  /// detection. A native call app that is *running but idle* (open, not in a call) is NOT using
  /// the microphone, so it won't be treated as a meeting.
  ///
  /// Chat apps are listed because their calls (Discord voice, Slack huddles, WhatsApp calls)
  /// open the microphone — the mic-in-use rule below is what keeps idle chat non-meetings.
  static let nativeCallBundleIDs: Set<String> = Set([
    "us.zoom.xos",  // Zoom
    "com.microsoft.teams",  // Microsoft Teams (classic)
    "com.microsoft.teams2",  // Microsoft Teams (new)
    "com.apple.facetime",  // FaceTime
    "cisco-systems.spark",  // Webex App
    "com.cisco.webexmeetingsapp",  // Webex Meetings
    "com.webex.meetingmanager",  // Webex (older)
    "com.logmein.gotomeeting",  // GoTo Meeting
    "com.logmein.goto",  // GoTo
    "com.hnc.discord",  // Discord (com.hnc.Discord)
    "com.hnc.discordptb",  // Discord PTB
    "com.hnc.discordcanary",  // Discord Canary
    "com.tinyspeck.slackmacgap",  // Slack
    "net.whatsapp.whatsapp",  // WhatsApp (net.whatsapp.WhatsApp)
  ]).union(telegramBundleIDs)

  /// Whether a bundle ID belongs to a known native conferencing app or one of its helper
  /// processes (case-insensitive).
  static func isNativeCallApp(bundleID: String) -> Bool {
    nativeCallAppID(bundleID: bundleID) != nil
  }

  /// The catalog entry a process belongs to. Electron and Chromium-based apps capture the
  /// microphone in a helper process with its own bundle ID: a Discord call holds the mic in
  /// `com.hnc.Discord.helper.Renderer` (measured 2026-09-26), so an exact match missed the call
  /// entirely. A helper is `<catalog id>.<suffix>`; the longest matching entry wins, so helpers
  /// of one app always map to the same identity.
  static func nativeCallAppID(bundleID: String) -> String? {
    let lower = bundleID.lowercased()
    if nativeCallBundleIDs.contains(lower) { return lower }
    return nativeCallBundleIDs.filter { lower.hasPrefix($0 + ".") }.max { $0.count < $1.count }
  }

  /// Bundle-ID prefixes (lowercased) of web browsers. A browser process using the **microphone**
  /// indicates a browser-based call (Google Meet, Teams web, etc.). Browsers route call audio
  /// through helper processes (e.g. `net.imput.helium.helper`, `com.google.Chrome.helper`), so we
  /// match by prefix rather than exact bundle ID.
  static let browserBundleIDPrefixes: [String] = [
    "com.google.chrome",
    "company.thebrowser",  // Arc
    "net.imput.helium",  // Helium
    "org.mozilla.firefox",
    "org.mozilla.nightly",  // Firefox Nightly
    "org.chromium.chromium",
    "com.openai.atlas",  // ChatGPT Atlas (Chromium-based)
    "com.microsoft.edgemac",
    "com.brave.browser",
    "com.operasoftware.opera",
    "com.vivaldi.vivaldi",
    "com.apple.safari",
    "com.apple.webkit.gpu",  // Safari / WebKit media process
  ]

  /// Whether a bundle ID belongs to a web browser (or one of its helpers), by prefix match.
  static func isBrowserBundleID(_ bundleID: String) -> Bool {
    let lower = bundleID.lowercased()
    return browserBundleIDPrefixes.contains { lower.hasPrefix($0) }
  }

  /// True if a single window — identified by its owner app and (optional) title — indicates a call.
  /// - Native call app: true on the owner name alone (no title / Screen Recording permission needed).
  /// - Browser app: true iff the title contains a call keyword (the title requires Screen Recording
  ///   permission; without it browser-based calls are not detected).
  static func isCallWindow(ownerName: String?, title: String?) -> Bool {
    guard let ownerName = ownerName else { return false }

    if nativeCallApps.contains(ownerName) {
      return true
    }

    if browserApps.contains(ownerName), let title = title {
      let lowercaseTitle = title.lowercased()
      for keyword in browserCallKeywords where lowercaseTitle.contains(keyword.lowercased()) {
        return true
      }
    }

    return false
  }

  /// True if a known conferencing app — a native call app OR a web browser — is currently using
  /// the microphone, i.e. *in a call* (not merely open). Uses the macOS 14.4+ CoreAudio process
  /// API; needs no Screen Recording permission. Native call apps keep the mic open even when
  /// muted; a browser drops mic input when muted, so a muted browser call is detected only via the
  /// window-title fallback (`browserCallWindowPresent()`, which needs Screen Recording permission).
  @available(macOS 14.4, *)
  static func callAppIsUsingMicrophone() -> Bool {
    bundleIDsRunningInput().contains(where: isCallSurface(bundleID:))
  }

  /// Whether a bundle ID is a call surface: a native conferencing app or a web browser. Shared by
  /// meeting detection and `DictationMicSuppressionPolicy`, where a call surface holding the mic
  /// outranks a dictation app.
  static func isCallSurface(bundleID: String) -> Bool {
    isNativeCallApp(bundleID: bundleID) || isBrowserBundleID(bundleID)
  }

  /// Lowercased bundle IDs of every process currently running microphone input, as CoreAudio
  /// reports them (macOS 14.4+; no permission needed). Processes without a readable bundle ID
  /// are omitted; order is unspecified.
  @available(macOS 14.4, *)
  static func bundleIDsRunningInput() -> [String] {
    var ids: [String] = []
    for process in audioProcessObjects() where processIsRunningInput(process) {
      guard let bundleID = processBundleID(process) else { continue }
      ids.append(bundleID.lowercased())
    }
    return ids
  }

  /// True if an on-screen browser window's title indicates a call. Window titles require Screen
  /// Recording permission; without it this returns false (native-app calls are still detected).
  /// This is the fallback that catches a *muted* browser call (where mic input has dropped).
  static func browserCallWindowPresent() -> Bool {
    onScreenBrowserWindowTitles().contains(where: isBrowserCallTitle)
  }

  /// Titles of normal-layer on-screen browser windows (each shows its active tab's title).
  /// Empty without Screen Recording permission.
  private static func onScreenBrowserWindowTitles() -> [String] {
    guard
      let windows = CGWindowListCopyWindowInfo(
        [.optionOnScreenOnly, .excludeDesktopElements], kCGNullWindowID) as? [[String: Any]]
    else {
      return []
    }
    return windows.compactMap { window in
      guard window[kCGWindowLayer as String] as? Int ?? -1 == 0,
        let owner = window[kCGWindowOwnerName as String] as? String,
        browserApps.contains(owner)
      else { return nil }
      return window[kCGWindowName as String] as? String
    }
  }

  // MARK: - Active outgoing screen share detection

  /// True if a single window — identified by owner app and title — is a share-indicator
  /// window: the floating toolbar/status chrome a conferencing app shows **only while the
  /// user is actively sharing their screen** in a call.
  ///
  /// Known signatures (window names are internal identifiers, not localized UI strings,
  /// except the browser bubble which is English-locale best effort):
  /// - Zoom: "zoom share statusbar window" / "zoom share toolbar window" floating controls
  /// - Microsoft Teams: "Screen sharing toolbar" window while presenting
  /// - Browsers (Google Meet / Teams web): the "<site> is sharing your screen/a tab/a window"
  ///   stop-sharing bubble window
  static func isShareIndicatorWindow(ownerName: String?, title: String?) -> Bool {
    guard let ownerName = ownerName, let title = title, !title.isEmpty else { return false }
    let lowerTitle = title.lowercased()

    if ownerName == "zoom.us" {
      return lowerTitle.contains("zoom share")
    }

    if ownerName.contains("Microsoft Teams") || ownerName == "MSTeams" {
      return lowerTitle.contains("sharing toolbar")
    }

    if browserApps.contains(ownerName) {
      return lowerTitle.contains("is sharing your screen")
        || lowerTitle.contains("is sharing a tab")
        || lowerTitle.contains("is sharing a window")
    }

    return false
  }

  /// True if any on-screen window indicates an active outgoing screen share (the user is
  /// presenting in Zoom/Teams/Meet/etc.). Window titles require Screen Recording permission;
  /// without it only windows with readable names are considered.
  ///
  /// Used to pause Omi's periodic capture: a one-shot ScreenCaptureKit capture while another
  /// app streams the screen contends in WindowServer capture arbitration and has been observed
  /// to stop the other app's share (issue #10143).
  static func activeScreenSharePresent() -> Bool {
    guard
      let windows = CGWindowListCopyWindowInfo(
        [.optionOnScreenOnly, .excludeDesktopElements], kCGNullWindowID) as? [[String: Any]]
    else {
      return false
    }
    for window in windows {
      let owner = window[kCGWindowOwnerName as String] as? String
      let title = window[kCGWindowName as String] as? String
      if isShareIndicatorWindow(ownerName: owner, title: title) {
        return true
      }
    }
    return false
  }

  /// One CoreAudio pass plus, only when `browserTitles` asks for them, one
  /// window-title pass. The meeting detector uses this as its only probe per tick.
  static func captureCallAudioSnapshot(browserTitles: CallAudioBrowserTitles) -> CallAudioSnapshot {
    let processes: [CallAudioProcessSnapshot]
    if #available(macOS 14.4, *) {
      processes = callAudioProcesses()
    } else {
      processes = []
    }
    let includeTitles: Bool
    switch browserTitles {
    case .always:
      includeTitles = true
    case .whenCallSurfaceHoldsInput:
      includeTitles = processes.contains {
        $0.isRunningInput && isCallSurface(bundleID: $0.bundleID)
      }
    }
    return CallAudioSnapshot(
      processes: processes,
      defaultInputDeviceID: defaultInputDeviceID(),
      browserWindowTitles: includeTitles ? onScreenBrowserWindowTitles() : [])
  }

  // MARK: - CoreAudio process API (macOS 14.4+) — microphone-in-use detection

  @available(macOS 14.4, *)
  private static func audioProcessObjects() -> [AudioObjectID] {
    let system = AudioObjectID(kAudioObjectSystemObject)
    var address = AudioObjectPropertyAddress(
      mSelector: kAudioHardwarePropertyProcessObjectList,
      mScope: kAudioObjectPropertyScopeGlobal,
      mElement: kAudioObjectPropertyElementMain)
    var dataSize: UInt32 = 0
    guard AudioObjectGetPropertyDataSize(system, &address, 0, nil, &dataSize) == noErr else {
      return []
    }
    let count = Int(dataSize) / MemoryLayout<AudioObjectID>.size
    guard count > 0 else { return [] }
    var objects = [AudioObjectID](repeating: 0, count: count)
    guard AudioObjectGetPropertyData(system, &address, 0, nil, &dataSize, &objects) == noErr
    else { return [] }
    return objects
  }

  @available(macOS 14.4, *)
  private static func callAudioProcesses() -> [CallAudioProcessSnapshot] {
    var processes: [CallAudioProcessSnapshot] = []
    for process in audioProcessObjects() {
      guard let bundleID = processBundleID(process) else { continue }
      processes.append(
        CallAudioProcessSnapshot(
          bundleID: bundleID.lowercased(),
          pid: processPID(process),
          isRunningInput: processBoolProperty(process, kAudioProcessPropertyIsRunningInput),
          isRunningOutput: processBoolProperty(process, kAudioProcessPropertyIsRunningOutput)))
    }
    return processes
  }

  @available(macOS 14.4, *)
  private static func processPID(_ process: AudioObjectID) -> Int32 {
    var address = AudioObjectPropertyAddress(
      mSelector: kAudioProcessPropertyPID,
      mScope: kAudioObjectPropertyScopeGlobal,
      mElement: kAudioObjectPropertyElementMain)
    var value: pid_t = -1
    var size = UInt32(MemoryLayout<pid_t>.size)
    guard AudioObjectGetPropertyData(process, &address, 0, nil, &size, &value) == noErr else {
      return -1
    }
    return value
  }

  private static func defaultInputDeviceID() -> UInt32 {
    var deviceID: AudioDeviceID = 0
    var size = UInt32(MemoryLayout<AudioDeviceID>.size)
    var address = AudioObjectPropertyAddress(
      mSelector: kAudioHardwarePropertyDefaultInputDevice,
      mScope: kAudioObjectPropertyScopeGlobal,
      mElement: kAudioObjectPropertyElementMain)
    let status = AudioObjectGetPropertyData(
      AudioObjectID(kAudioObjectSystemObject), &address, 0, nil, &size, &deviceID)
    guard status == noErr else { return 0 }
    return deviceID
  }

  @available(macOS 14.4, *)
  private static func processIsRunningInput(_ process: AudioObjectID) -> Bool {
    processBoolProperty(process, kAudioProcessPropertyIsRunningInput)
  }

  @available(macOS 14.4, *)
  private static func processBoolProperty(
    _ process: AudioObjectID, _ selector: AudioObjectPropertySelector
  ) -> Bool {
    var address = AudioObjectPropertyAddress(
      mSelector: selector,
      mScope: kAudioObjectPropertyScopeGlobal,
      mElement: kAudioObjectPropertyElementMain)
    var value: UInt32 = 0
    var size = UInt32(MemoryLayout<UInt32>.size)
    guard AudioObjectGetPropertyData(process, &address, 0, nil, &size, &value) == noErr else {
      return false
    }
    return value != 0
  }

  @available(macOS 14.4, *)
  private static func processBundleID(_ process: AudioObjectID) -> String? {
    var address = AudioObjectPropertyAddress(
      mSelector: kAudioProcessPropertyBundleID,
      mScope: kAudioObjectPropertyScopeGlobal,
      mElement: kAudioObjectPropertyElementMain)
    var unmanaged: Unmanaged<CFString>?
    var size = UInt32(MemoryLayout<Unmanaged<CFString>?>.size)
    let status = withUnsafeMutablePointer(to: &unmanaged) {
      AudioObjectGetPropertyData(process, &address, 0, nil, &size, $0)
    }
    guard status == noErr, let bundleID = unmanaged?.takeRetainedValue() as String?,
      !bundleID.isEmpty
    else { return nil }
    return bundleID
  }
}
