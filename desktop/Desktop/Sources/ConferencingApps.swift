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

    /// Scan all on-screen windows and report whether any indicates an active call.
    ///
    /// Owner names are available without Screen Recording permission; window titles (needed to
    /// distinguish browser-based calls) require it. We only consider normal-layer, reasonably
    /// sized windows so menu-bar / status-item helper windows of a backgrounded call app don't
    /// count as a meeting.
    static func isMeetingActiveNow() -> Bool {
        guard
            let windows = CGWindowListCopyWindowInfo(
                [.optionOnScreenOnly, .excludeDesktopElements], kCGNullWindowID) as? [[String: Any]]
        else {
            return false
        }

        for window in windows {
            // Skip non-normal layers (menu bar items, status items, overlays live above layer 0).
            let layer = window[kCGWindowLayer as String] as? Int ?? -1
            guard layer == 0 else { continue }

            // Skip tiny helper windows (a backgrounded call app may keep a small status window).
            if let bounds = window[kCGWindowBounds as String] as? [String: CGFloat],
                let width = bounds["Width"], let height = bounds["Height"],
                width < 120 || height < 120
            {
                continue
            }

            let owner = window[kCGWindowOwnerName as String] as? String
            let title = window[kCGWindowName as String] as? String
            if isCallWindow(ownerName: owner, title: title) {
                return true
            }
        }

        return false
    }
}
