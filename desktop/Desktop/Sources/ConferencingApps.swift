import CoreAudio
import CoreGraphics
import Foundation

/// Shared catalog of conferencing / video-call apps plus the logic for deciding whether a
/// window (or the whole screen) indicates an active call ("meeting").
///
/// Single source of truth shared by:
///  - `MeetingDetector`, which gates system-audio capture in "Only during meetings" mode, and
///  - `ProactiveAssistantsPlugin`, which throttles screen capture while a call app is frontmost.
enum ConferencingApps {

    /// Apps whose primary purpose is video/audio calls. Matched by app/owner name, which is
    /// available from `NSRunningApplication` and `CGWindowList` **without** Screen Recording
    /// permission.
    static let nativeCallApps: Set<String> = [
        "Microsoft Teams",
        "zoom.us",
        "FaceTime",
        "Webex",
        "Cisco Webex Meetings",
        "GoTo Meeting",
        "GoToMeeting",
    ]

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

    /// Bundle IDs (lowercased) of native conferencing apps, used for mic-in-use ("in a call")
    /// detection. A native call app that is *running but idle* (open, not in a call) is NOT using
    /// the microphone, so it won't be treated as a meeting.
    static let nativeCallBundleIDs: Set<String> = [
        "us.zoom.xos",  // Zoom
        "com.microsoft.teams",  // Microsoft Teams (classic)
        "com.microsoft.teams2",  // Microsoft Teams (new)
        "com.apple.facetime",  // FaceTime
        "cisco-systems.spark",  // Webex App
        "com.cisco.webexmeetingsapp",  // Webex Meetings
        "com.webex.meetingmanager",  // Webex (older)
        "com.logmein.gotomeeting",  // GoTo Meeting
        "com.logmein.goto",  // GoTo
    ]

    /// Whether a bundle ID belongs to a known native conferencing app (case-insensitive).
    static func isNativeCallApp(bundleID: String) -> Bool {
        nativeCallBundleIDs.contains(bundleID.lowercased())
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

    /// Whether a conferencing call is currently active.
    ///
    /// - **Native call apps** (Zoom, Teams, FaceTime, Webex, …): detected by **active microphone
    ///   use** — i.e. actually *in a call*, not merely open. Uses the macOS 14.4+ CoreAudio process
    ///   API and needs no Screen Recording permission. A backgrounded-but-idle call app is not
    ///   using the mic, so it does not count as a meeting.
    /// - **Browser-based calls** (Google Meet, Teams web): detected by the browser's call **window
    ///   title**, which requires Screen Recording permission (without it, browser calls aren't
    ///   detected; native calls still are).
    static func isMeetingActiveNow() -> Bool {
        if #available(macOS 14.4, *), callAppIsUsingMicrophone() {
            return true
        }
        return browserCallWindowPresent()
    }

    /// True if a known conferencing app — a native call app OR a web browser — is currently using
    /// the microphone (in a call). Native call apps usually keep the mic open even when muted; a
    /// browser drops mic input when muted, so a muted browser call may not be detected this way
    /// (the window-title fallback covers that when Screen Recording permission is granted).
    @available(macOS 14.4, *)
    static func callAppIsUsingMicrophone() -> Bool {
        for process in audioProcessObjects() where processIsRunningInput(process) {
            guard let bundleID = processBundleID(process) else { continue }
            if isNativeCallApp(bundleID: bundleID) || isBrowserBundleID(bundleID) {
                return true
            }
        }
        return false
    }

    /// True if an on-screen browser window's title indicates a call. Window titles require Screen
    /// Recording permission; without it this returns false (native-app calls are still detected).
    private static func browserCallWindowPresent() -> Bool {
        guard
            let windows = CGWindowListCopyWindowInfo(
                [.optionOnScreenOnly, .excludeDesktopElements], kCGNullWindowID) as? [[String: Any]]
        else {
            return false
        }
        for window in windows {
            let layer = window[kCGWindowLayer as String] as? Int ?? -1
            guard layer == 0 else { continue }
            guard let owner = window[kCGWindowOwnerName as String] as? String,
                browserApps.contains(owner),
                let title = window[kCGWindowName as String] as? String
            else { continue }
            let lower = title.lowercased()
            for keyword in browserCallKeywords where lower.contains(keyword.lowercased()) {
                return true
            }
        }
        return false
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
    private static func processIsRunningInput(_ process: AudioObjectID) -> Bool {
        var address = AudioObjectPropertyAddress(
            mSelector: kAudioProcessPropertyIsRunningInput,
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
