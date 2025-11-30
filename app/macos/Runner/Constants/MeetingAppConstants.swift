import Foundation

// MARK: - Meeting App Configuration

/// Represents a known meeting/collaboration application
struct MeetingApp {
    let bundleIds: [String]  // All possible bundle IDs for this app
    let displayName: String  // User-friendly name

    init(_ displayName: String, bundleIds: String...) {
        self.displayName = displayName
        self.bundleIds = bundleIds
    }
}

/// Centralized configuration for all known meeting apps
struct MeetingApps {
    // MARK: - Video Conferencing Apps

    static let zoom = MeetingApp("Zoom", bundleIds: "us.zoom.xos", "com.zoom.us", "zoom.us")
    static let teams = MeetingApp("Microsoft Teams", bundleIds: "com.microsoft.teams", "com.microsoft.teams2")
    static let googleMeet = MeetingApp("Google Meet", bundleIds: "com.google.Chrome")
    static let webex = MeetingApp("Webex", bundleIds: "com.webex.meetingmanager", "com.cisco.webexmeetings", "com.cisco.webexmeetingsapp")
    static let gotoMeeting = MeetingApp("GoToMeeting", bundleIds: "com.goto.meeting", "com.citrixonline.GoToMeeting")
    static let blueJeans = MeetingApp("BlueJeans", bundleIds: "com.bluejeans.app")

    // MARK: - Collaboration Apps

    static let slack = MeetingApp("Slack", bundleIds: "com.tinyspeck.slackmacgap")
    static let discord = MeetingApp("Discord", bundleIds: "com.hnc.Discord", "com.discord")
    static let skype = MeetingApp("Skype", bundleIds: "com.skype.skype")

    // MARK: - Browsers

    static let safari = MeetingApp("Safari", bundleIds: "com.apple.Safari")
    static let chrome = MeetingApp("Chrome", bundleIds: "com.google.Chrome")
    static let brave = MeetingApp("Brave", bundleIds: "com.brave.Browser")
    static let firefox = MeetingApp("Firefox", bundleIds: "org.mozilla.firefox")
    static let arc = MeetingApp("Arc", bundleIds: "company.thebrowser.Browser")
    static let edge = MeetingApp("Edge", bundleIds: "com.microsoft.edgemac")
    static let opera = MeetingApp("Opera", bundleIds: "com.operasoftware.Opera")
    static let vivaldi = MeetingApp("Vivaldi", bundleIds: "com.vivaldi.Vivaldi")

    // MARK: - Other Apps

    static let facetime = MeetingApp("FaceTime", bundleIds: "com.apple.FaceTime")
    static let ringCentral = MeetingApp("RingCentral", bundleIds: "com.ringcentral.ringcentral")
    static let eightByEight = MeetingApp("8x8", bundleIds: "com.8x8.8x8-work")
    static let whereby = MeetingApp("Whereby", bundleIds: "com.whereby.desktop", "com.whereby.app")
    static let around = MeetingApp("Around", bundleIds: "com.around.Around", "com.around.app")
    static let jam = MeetingApp("Jam", bundleIds: "com.jam.desktop")
    static let tuple = MeetingApp("Tuple", bundleIds: "app.tuple.app")
    static let whatsapp = MeetingApp("WhatsApp", bundleIds: "net.whatsapp.WhatsApp")
    static let jitsi = MeetingApp("Jitsi Meet", bundleIds: "org.jitsi.jitsi-meet")

    // MARK: - All Apps

    /// All known meeting apps
    static let all: [MeetingApp] = [
        zoom, teams, googleMeet, webex, gotoMeeting, blueJeans,
        slack, discord, skype,
        safari, chrome, brave, firefox, arc, edge, opera, vivaldi,
        facetime, ringCentral, eightByEight, whereby, around, jam, tuple, whatsapp, jitsi
    ]

    // MARK: - Browser Bundle IDs

    /// Browser bundle IDs that require window title checking
    static let browserBundleIds: Set<String> = [
        "com.google.Chrome",
        "com.apple.Safari",
        "com.brave.Browser",
        "org.mozilla.firefox",
        "company.thebrowser.Browser",  // Arc
        "com.microsoft.edgemac",
        "com.operasoftware.Opera",
        "com.vivaldi.Vivaldi"
    ]

    // MARK: - Meeting Keywords

    /// Keywords to search for in unknown bundle IDs
    static let meetingKeywords = [
        "zoom", "teams", "webex", "meet", "slack", "discord",
        "skype", "facetime", "whereby", "around", "tuple"
    ]

    /// Meeting keywords to look for in browser window titles
    static let meetingKeywordsInTitle: [String] = [
        "Meet", "meet.google.com",  // Google Meet
        "Zoom Meeting", "zoom.us",  // Zoom web
        "Microsoft Teams", "teams.microsoft.com", "teams.live.com",  // Teams web
        "Slack", "slack.com/huddle",  // Slack huddle
        "Discord",  // Discord voice
        "Webex", "webex.com"  // Webex meetings
    ]

    // MARK: - URL Pattern Matching

    /// Platform URL patterns for extracting platform from calendar events
    static let platformURLPatterns: [(pattern: String, displayName: String)] = [
        // Video conferencing platforms
        ("zoom.us", "Zoom"),
        ("teams.microsoft.com", "Teams"),
        ("teams.live.com", "Teams"),
        ("meet.google.com", "Google Meet"),
        ("webex.com", "Webex"),
        ("gotomeeting.com", "GoToMeeting"),
        ("bluejeans.com", "BlueJeans"),
        ("whereby.com", "Whereby"),
        ("around.co", "Around"),
        ("jitsi", "Jitsi"),
        ("hangouts.google.com", "Hangouts"),

        // Communication apps
        ("slack.com", "Slack"),
        ("discord.com", "Discord"),
        ("discord.gg", "Discord"),
        ("skype.com", "Skype"),
        ("whatsapp.com", "WhatsApp"),
        ("ringcentral.com", "RingCentral"),
        ("facetime", "FaceTime"),
    ]

    // MARK: - Helper Methods

    /// Extract platform name from URL or text (for calendar integration)
    static func extractPlatformFromURL(_ text: String) -> String? {
        let lowercased = text.lowercased()

        for (pattern, displayName) in platformURLPatterns {
            if lowercased.contains(pattern) {
                return displayName
            }
        }

        return nil
    }

    // MARK: - Bundle ID Mapping

    /// Map from app names (as they appear in logs) to bundle IDs
    static let bundleIdMap: [String: String] = [
        "zoom.us": "us.zoom.xos",
        "Google Chrome": "com.google.Chrome",
        "Safari": "com.apple.Safari",
        "Microsoft Teams": "com.microsoft.teams2",
        "Microsoft Teams (work or school)": "com.microsoft.teams2",
        "Slack": "com.tinyspeck.slackmacgap",
        "Discord": "com.hnc.Discord",
        "Firefox": "org.mozilla.firefox",
        "Arc": "company.thebrowser.Browser",
        "Webex": "com.cisco.webexmeetingsapp",
        "WhatsApp": "net.whatsapp.WhatsApp",
        "Tuple": "app.tuple.app",
        "Brave Browser": "com.brave.Browser",
        "Microsoft Edge": "com.microsoft.edgemac",
        "Skype": "com.skype.skype",
        "FaceTime": "com.apple.FaceTime",
        "Around": "com.around.app",
        "Whereby": "com.whereby.app",
        "Jitsi Meet": "org.jitsi.jitsi-meet",
        "BlueJeans": "com.bluejeans.app",
        "GoToMeeting": "com.citrixonline.GoToMeeting",
        "Opera": "com.operasoftware.Opera",
        "Vivaldi": "com.vivaldi.Vivaldi"
    ]
}
