import Foundation
import Cocoa
import FlutterMacOS
import ApplicationServices

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
    // Video conferencing apps
    static let zoom = MeetingApp("Zoom", bundleIds: "us.zoom.xos", "com.zoom.us", "zoom.us")
    static let teams = MeetingApp("Microsoft Teams", bundleIds: "com.microsoft.teams", "com.microsoft.teams2")
    static let googleMeet = MeetingApp("Google Meet", bundleIds: "com.google.Chrome")
    static let webex = MeetingApp("Webex", bundleIds: "com.webex.meetingmanager", "com.cisco.webexmeetings", "com.cisco.webexmeetingsapp")
    static let gotoMeeting = MeetingApp("GoToMeeting", bundleIds: "com.goto.meeting", "com.citrixonline.GoToMeeting")
    static let blueJeans = MeetingApp("BlueJeans", bundleIds: "com.bluejeans.app")

    // Collaboration apps
    static let slack = MeetingApp("Slack", bundleIds: "com.tinyspeck.slackmacgap")
    static let discord = MeetingApp("Discord", bundleIds: "com.hnc.Discord", "com.discord")
    static let skype = MeetingApp("Skype", bundleIds: "com.skype.skype")

    // Browsers
    static let safari = MeetingApp("Safari", bundleIds: "com.apple.Safari")
    static let chrome = MeetingApp("Chrome", bundleIds: "com.google.Chrome")
    static let brave = MeetingApp("Brave", bundleIds: "com.brave.Browser")
    static let firefox = MeetingApp("Firefox", bundleIds: "org.mozilla.firefox")
    static let arc = MeetingApp("Arc", bundleIds: "company.thebrowser.Browser")
    static let edge = MeetingApp("Edge", bundleIds: "com.microsoft.edgemac")

    // Other apps
    static let facetime = MeetingApp("FaceTime", bundleIds: "com.apple.FaceTime")
    static let ringCentral = MeetingApp("RingCentral", bundleIds: "com.ringcentral.ringcentral")
    static let eightByEight = MeetingApp("8x8", bundleIds: "com.8x8.8x8-work")
    static let whereby = MeetingApp("Whereby", bundleIds: "com.whereby.desktop", "com.whereby.app")
    static let around = MeetingApp("Around", bundleIds: "com.around.Around", "com.around.app")
    static let jam = MeetingApp("Jam", bundleIds: "com.jam.desktop")
    static let tuple = MeetingApp("Tuple", bundleIds: "app.tuple.app")
    static let whatsapp = MeetingApp("WhatsApp", bundleIds: "net.whatsapp.WhatsApp")
    static let jitsi = MeetingApp("Jitsi Meet", bundleIds: "org.jitsi.jitsi-meet")

    /// All known meeting apps
    static let all: [MeetingApp] = [
        zoom, teams, googleMeet, webex, gotoMeeting, blueJeans,
        slack, discord, skype,
        safari, chrome, brave, firefox, arc, edge,
        facetime, ringCentral, eightByEight, whereby, around, jam, tuple, whatsapp, jitsi
    ]

    /// Keywords to search for in unknown bundle IDs
    static let meetingKeywords = [
        "zoom", "teams", "webex", "meet", "slack", "discord",
        "skype", "facetime", "whereby", "around", "tuple"
    ]
}

class MeetingDetector: NSObject {

    // MARK: - Properties
    private var logProcess: Process?
    private var buffer = ""
    private var activeMicApps = Set<String>()
    private var eventChannel: FlutterEventChannel?
    private var eventSink: FlutterEventSink?
    private var wasInMeeting = false  // Track previous meeting state

    // Callback for when meeting ends
    var onMeetingEnded: (() -> Void)?

    // Window title tracking for browsers
    private var currentFrontmostApp: NSRunningApplication?
    private var currentWindowTitle: String?
    private var trackedBrowserBundleIds = Set<String>()  // Browsers we're actively monitoring
    private var browserMeetingTitles: [String: String] = [:]  // Bundle ID -> Meeting window title

    // Debouncing to prevent showing nub during brief mic checks
    private var pendingMeetingTimers: [String: Timer] = [:]  // Bundle ID -> Timer for delayed confirmation
    private var latestMicActiveApps = Set<String>()  // Latest snapshot of apps using mic (from log entries)

    // Bundle IDs to exclude from meeting detection
    private lazy var excludedBundleIds: Set<String> = {
        var excluded = Set<String>()

        // Exclude our own app
        if let ownBundleId = Bundle.main.bundleIdentifier {
            excluded.insert(ownBundleId)
        }

        // Exclude system apps and utilities that aren't meeting apps
        excluded.insert("com.apple.controlcenter")
        excluded.insert("com.apple.systemuiserver")
        excluded.insert("com.apple.finder")

        return excluded
    }()

    // Browser bundle IDs that require window title checking
    private let browserBundleIds: Set<String> = [
        "com.google.Chrome",
        "com.apple.Safari",
        "com.brave.Browser",
        "org.mozilla.firefox",
        "company.thebrowser.Browser",  // Arc
        "com.microsoft.edgemac"
    ]

    // Meeting keywords to look for in browser window titles
    private let meetingKeywordsInTitle: [String] = [
        "Meet", "meet.google.com",  // Google Meet
        "Zoom Meeting", "zoom.us",  // Zoom web
        "Microsoft Teams", "teams.microsoft.com",  // Teams web
        "Slack", "slack.com/huddle",  // Slack huddle
        "Discord",  // Discord voice
        "Webex", "webex.com"  // Webex meetings
    ]

    // MARK: - Bundle ID Mapping
    private let bundleIdMap: [String: String] = [
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
        "GoToMeeting": "com.citrixonline.GoToMeeting"
    ]

    // MARK: - Initialization
    override init() {
        super.init()
        setupAppMonitoring()
    }

    // Setup app activation monitoring to detect when browsers become frontmost
    private func setupAppMonitoring() {
        NSWorkspace.shared.notificationCenter.addObserver(
            self,
            selector: #selector(handleAppActivation(_:)),
            name: NSWorkspace.didActivateApplicationNotification,
            object: nil
        )
    }

    @objc private func handleAppActivation(_ notification: Notification) {
        guard let app = notification.userInfo?[NSWorkspace.applicationUserInfoKey] as? NSRunningApplication,
              let bundleId = app.bundleIdentifier else {
            return
        }

        currentFrontmostApp = app

        // If a browser we're tracking becomes active, re-check its window title
        // This handles the case where user switches tabs or windows
        if trackedBrowserBundleIds.contains(bundleId) {
            recheckBrowserMeetingStatus(for: app, bundleId: bundleId)
        }
    }

    // MARK: - Public Methods

    func configure(eventChannel: FlutterEventChannel) {
        self.eventChannel = eventChannel
        eventChannel.setStreamHandler(self)
    }

    func start() {
        guard logProcess == nil else {
            print("MeetingDetector: Already running")
            return
        }


        // Build predicate for filtering Control Center microphone events
        // Start with broader filter - just subsystem
        let predicate = "subsystem == \"com.apple.controlcenter\""

        // Create process to run log stream command
        logProcess = Process()
        logProcess?.executableURL = URL(fileURLWithPath: "/usr/bin/log")
        logProcess?.arguments = [
            "stream",
            "--type", "log",
            "--level", "default",
            "--predicate", predicate,
            "--style", "ndjson"
        ]


        // Setup output pipe
        let outputPipe = Pipe()
        logProcess?.standardOutput = outputPipe

        // Setup error pipe
        let errorPipe = Pipe()
        logProcess?.standardError = errorPipe

        // Handle output data
        outputPipe.fileHandleForReading.readabilityHandler = { [weak self] handle in
            guard let self = self else { return }

            let data = handle.availableData
            guard !data.isEmpty else { return }

            if let output = String(data: data, encoding: .utf8) {
                self.handleLogData(output)
            }
        }

        // Handle error data
        errorPipe.fileHandleForReading.readabilityHandler = { handle in
            let data = handle.availableData
            guard !data.isEmpty else { return }

            if let errorOutput = String(data: data, encoding: .utf8) {
            }
        }

        // Handle process termination
        logProcess?.terminationHandler = { [weak self] process in
            print("MeetingDetector: log stream exited with code \(process.terminationStatus)")
            self?.logProcess = nil
        }

        // Start the process
        do {
            try logProcess?.run()
        } catch {
            print("MeetingDetector: Failed to start log stream: \(error.localizedDescription)")
            logProcess = nil
        }
    }

    func stop() {
        guard let process = logProcess else {
            return
        }


        // Clear handlers to prevent memory leaks
        if let outputPipe = process.standardOutput as? Pipe {
            outputPipe.fileHandleForReading.readabilityHandler = nil
        }
        if let errorPipe = process.standardError as? Pipe {
            errorPipe.fileHandleForReading.readabilityHandler = nil
        }

        process.terminate()
        logProcess = nil
        activeMicApps.removeAll()
        trackedBrowserBundleIds.removeAll()
        browserMeetingTitles.removeAll()
        latestMicActiveApps.removeAll()
        buffer = ""
        wasInMeeting = false

        // Cancel all pending timers
        for (_, timer) in pendingMeetingTimers {
            timer.invalidate()
        }
        pendingMeetingTimers.removeAll()

    }

    /// Re-check if a browser still has a meeting window open (called when app becomes frontmost)
    /// This is for detecting when user switches BACK to a meeting tab they were already in
    private func recheckBrowserMeetingStatus(for app: NSRunningApplication, bundleId: String) {
        guard checkAccessibilityPermission() else { return }

        let pid = app.processIdentifier
        let axApp = AXUIElementCreateApplication(pid)

        // Get all windows
        var windowsValue: CFTypeRef?
        let result = AXUIElementCopyAttributeValue(axApp, kAXWindowsAttribute as CFString, &windowsValue)

        guard result == .success,
              let windows = windowsValue as? [AXUIElement],
              !windows.isEmpty else {
            // No windows found - browser closed entirely
            if activeMicApps.contains(bundleId) {
                activeMicApps.remove(bundleId)
                trackedBrowserBundleIds.remove(bundleId)
                browserMeetingTitles.removeValue(forKey: bundleId)
                print("MeetingDetector: Browser closed entirely - removing \(bundleId)")
                notifyMeetingStateChanged()
            }
            return
        }

        // Check if the first window (frontmost) has a meeting title
        var foundMeetingTitle = false
        var titleValue: CFTypeRef?
        let titleResult = AXUIElementCopyAttributeValue(windows[0], kAXTitleAttribute as CFString, &titleValue)

        if titleResult == .success,
           let title = titleValue as? String,
           !title.isEmpty {
            print("MeetingDetector: Browser frontmost window title: \(title)")
            foundMeetingTitle = isMeetingWindowTitle(title)
        }

        // Only ADD back if user switched back to meeting tab
        // Don't remove just because user is on a different tab - they might return
        if foundMeetingTitle && !activeMicApps.contains(bundleId) {
            // User switched back to meeting tab
            activeMicApps.insert(bundleId)
            notifyMeetingStateChanged()
        }
    }

    /// Check if meeting tab is closed when mic goes inactive
    /// Only remove meeting if BOTH mic is off AND meeting tab is not found
    private func checkIfMeetingTabClosed(for app: NSRunningApplication, bundleId: String) {
        guard checkAccessibilityPermission() else { return }

        let pid = app.processIdentifier
        let axApp = AXUIElementCreateApplication(pid)

        // Get all windows
        var windowsValue: CFTypeRef?
        let result = AXUIElementCopyAttributeValue(axApp, kAXWindowsAttribute as CFString, &windowsValue)

        guard result == .success,
              let windows = windowsValue as? [AXUIElement],
              !windows.isEmpty else {
            // Browser closed
            activeMicApps.remove(bundleId)
            trackedBrowserBundleIds.remove(bundleId)
            browserMeetingTitles.removeValue(forKey: bundleId)
            notifyMeetingStateChanged()
            return
        }

        // Check ALL windows (not just frontmost) to see if meeting tab still exists
        var meetingTabStillOpen = false
        for window in windows {
            var titleValue: CFTypeRef?
            let titleResult = AXUIElementCopyAttributeValue(window, kAXTitleAttribute as CFString, &titleValue)

            if titleResult == .success,
               let title = titleValue as? String,
               !title.isEmpty,
               isMeetingWindowTitle(title) {
                meetingTabStillOpen = true
                break
            }
        }

        if !meetingTabStillOpen {
            // Meeting tab is closed AND mic is off - remove the meeting
            activeMicApps.remove(bundleId)
            trackedBrowserBundleIds.remove(bundleId)
            browserMeetingTitles.removeValue(forKey: bundleId)
            notifyMeetingStateChanged()
        }
    }

    func getActiveMeetingApps() -> [String] {
        return Array(activeMicApps)
    }

    // MARK: - Private Methods

    private func handleLogData(_ data: String) {

        buffer += data

        // Process complete JSON lines
        let lines = buffer.components(separatedBy: "\n")
        buffer = lines.last ?? "" // Keep incomplete line in buffer

        for line in lines.dropLast() {
            let trimmedLine = line.trimmingCharacters(in: .whitespaces)
            guard !trimmedLine.isEmpty else { continue }
            
            // Skip non-JSON lines (like the "Filtering the log data..." message)
            guard trimmedLine.hasPrefix("{") else {
                continue
            }

            do {
                if let jsonData = line.data(using: .utf8),
                   let logEntry = try JSONSerialization.jsonObject(with: jsonData) as? [String: Any] {
                    processLogEntry(logEntry)
                }
            } catch {
                print("MeetingDetector: JSON parse error for line: \(line.prefix(100))... Error: \(error)")
            }
        }
    }

    private func processLogEntry(_ logEntry: [String: Any]) {
        let message = logEntry["eventMessage"] as? String ?? ""
        var changed = false

        // ONLY process authoritative "Active activity attributions changed" messages
        // These are the definitive source of truth for what's currently using the mic
        if message.contains("Active activity attributions changed to") ||
           message.contains("Sorted active attributions") {

            let currentBundleIds = extractAllBundleIds(from: message)

            // Update latest mic state snapshot
            latestMicActiveApps = currentBundleIds

            // 1. Identify apps that stopped (in activeMicApps but not in new list)
            for app in activeMicApps {
                if !currentBundleIds.contains(app) {
                    // Only remove when BOTH mic is inactive AND user has switched away from meeting tab
                    if browserBundleIds.contains(app) {
                        // Check if user is still on the meeting tab
                        if let runningApp = NSWorkspace.shared.runningApplications.first(where: { $0.bundleIdentifier == app }) {
                            checkIfMeetingTabClosed(for: runningApp, bundleId: app)
                        }
                        continue
                    }

                    // For non-browser apps, remove immediately
                    activeMicApps.remove(app)
                    changed = true
                    print("MeetingDetector: Microphone session ended (removed from list): \(app)")
                }
            }

            // 2. Identify apps that started (in new list but not in activeMicApps)
            for app in currentBundleIds {
                // Filter excluded/unknown apps
                if excludedBundleIds.contains(app) { continue }

                // For browsers, we need to check window title before confirming it's a meeting
                if browserBundleIds.contains(app) {
                    if !activeMicApps.contains(app) {
                        // Browser started using mic - check window title
                        trackedBrowserBundleIds.insert(app)

                        // Get the running app and check its window title
                        if let runningApp = NSWorkspace.shared.runningApplications.first(where: { $0.bundleIdentifier == app }) {
                            checkBrowserWindowTitle(for: runningApp, bundleId: app)
                        }
                    }
                    continue
                }

                // For non-browser apps, use existing logic
                if !isKnownMeetingApp(app) { continue }

                if !activeMicApps.contains(app) && !pendingMeetingTimers.keys.contains(app) {
                    // Schedule a delayed confirmation - wait 3 seconds then check if mic still active
                    scheduleMeetingConfirmation(for: app, currentBundleIds: currentBundleIds)
                }
            }

            if changed {
                notifyMeetingStateChanged()
            }
        }

    }

    private func extractAllBundleIds(from message: String) -> Set<String> {
        var foundIds = Set<String>()
        
        // Regex for "mic:bundle.id" or "[mic] ... (bundle.id)"
        // Matches: mic:us.zoom.xos
        let pattern1 = #"(?:mic:|mic\])\s*([a-zA-Z0-9._-]+)"#
        if let regex = try? NSRegularExpression(pattern: pattern1) {
            let results = regex.matches(in: message, range: NSRange(message.startIndex..., in: message))
            for result in results {
                if let range = Range(result.range(at: 1), in: message) {
                    let id = String(message[range]).trimmingCharacters(in: .whitespacesAndNewlines)
                    if id.contains(".") { foundIds.insert(id) }
                }
            }
        }
        
        // Matches: (us.zoom.xos)
        let pattern2 = #"\(([a-z0-9._-]+\.[a-z0-9._-]+)\)"#
        if let regex = try? NSRegularExpression(pattern: pattern2) {
            let results = regex.matches(in: message, range: NSRange(message.startIndex..., in: message))
            for result in results {
                if let range = Range(result.range(at: 1), in: message) {
                    let id = String(message[range])
                    if !id.isEmpty { foundIds.insert(id) }
                }
            }
        }
        
        return foundIds
    }

    private func extractBundleId(from logEntry: [String: Any], processPath: String) -> String? {
        let message = logEntry["eventMessage"] as? String ?? ""
        
        // Method 1: Extract from sensor-indicators messages like:
        // "Active activity attributions changed to ["mic:us.zoom.xos"]"
        // "Sorted active attributions from SystemStatus update: [[mic] zoom.us (us.zoom.xos)]"
        if let match = message.range(of: #"(?:mic:|mic\])\s*([a-zA-Z0-9._-]+)"#, options: .regularExpression) {
            let matched = String(message[match])
            // Extract bundle ID after "mic:" or "mic]"
            if let colonRange = matched.range(of: #"(?:mic:|mic\])\s*"#, options: .regularExpression) {
                let bundleId = String(matched[colonRange.upperBound...]).trimmingCharacters(in: .whitespacesAndNewlines)
                if !bundleId.isEmpty && bundleId.contains(".") {
                    print("MeetingDetector: Extracted bundle ID from mic attribution: \(bundleId)")
                    return bundleId
                }
            }
        }
        
        // Method 2: Extract from messages with bundle ID in parentheses: "(us.zoom.xos)"
        if let match = message.range(of: #"\(([a-z0-9._-]+\.[a-z0-9._-]+)\)"#, options: .regularExpression) {
            let matched = String(message[match])
            let bundleId = matched.trimmingCharacters(in: CharacterSet(charactersIn: "()"))
            if !bundleId.isEmpty {
                print("MeetingDetector: Extracted bundle ID from parentheses: \(bundleId)")
                return bundleId
            }
        }
        
        // Method 3: Direct bundle ID from log entry
        if let bundleId = logEntry["bundleID"] as? String {
            print("MeetingDetector: Extracted bundle ID from logEntry.bundleID: \(bundleId)")
            return bundleId
        }

        // Method 4: Extract from process path
        if !processPath.isEmpty {
            if let bundleId = extractBundleIdFromPath(processPath) {
                print("MeetingDetector: Extracted bundle ID from path: \(bundleId)")
                return bundleId
            }
        }

        // Method 5: Parse from event message with common prefixes
        if let match = message.range(of: #"(?:bundle(?:ID)?|client|attribution)[:\s]+([a-zA-Z0-9\._-]+)"#, options: [.regularExpression, .caseInsensitive]) {
            let bundleIdString = String(message[match])
            let components = bundleIdString.components(separatedBy: CharacterSet(charactersIn: ": \t"))
            if let bundleId = components.last?.trimmingCharacters(in: .whitespacesAndNewlines), !bundleId.isEmpty {
                print("MeetingDetector: Extracted bundle ID from message prefix: \(bundleId)")
                return bundleId
            }
        }

        return nil
    }

    private func extractBundleIdFromPath(_ processPath: String) -> String? {
        // Extract app name from path like:
        // /Applications/zoom.us.app/Contents/MacOS/zoom.us
        // /Applications/Google Chrome.app/Contents/MacOS/Google Chrome

        guard let appMatch = processPath.range(of: #"/([^/]+\.app)/"#, options: .regularExpression) else {
            return nil
        }

        let appPathComponent = String(processPath[appMatch])
        let appName = appPathComponent
            .replacingOccurrences(of: "/", with: "")
            .replacingOccurrences(of: ".app", with: "")

        // Look up bundle ID from mapping
        return bundleIdMap[appName]
    }

    // Callbacks for controlling the Nub
    var onShowNub: ((String) -> Void)?
    var onHideNub: (() -> Void)?

    private func notifyMeetingStateChanged() {
        let isInMeeting = !activeMicApps.isEmpty
        let apps = Array(activeMicApps)

        let event: [String: Any] = [
            "event": isInMeeting ? "meeting_started" : "meeting_ended",
            "isInMeeting": isInMeeting,
            "apps": apps
        ]

        // Send event to Flutter
        DispatchQueue.main.async { [weak self] in
            self?.eventSink?(event)
        }

        print("MeetingDetector: Meeting state changed - isInMeeting: \(isInMeeting), apps: \(apps)")

        // Control the nub via callbacks - ONLY on state transitions
        DispatchQueue.main.async { [weak self] in
            guard let self = self else { return }
            
            // Detect transition from no meeting -> meeting
            if isInMeeting && !self.wasInMeeting {
                let appName = apps.first ?? "Meeting"
                // Convert bundle ID to friendly name
                let friendlyName = self.getFriendlyAppName(from: appName)
                print("MeetingDetector: Transition to meeting detected - showing nub for \(friendlyName)")
                self.onShowNub?(friendlyName)
            } 
            // Detect transition from meeting -> no meeting
            else if !isInMeeting && self.wasInMeeting {
                print("MeetingDetector: Transition to no meeting detected - hiding nub")
                self.onHideNub?()

                // Stop recording when meeting ends
                self.stopRecordingIfActive()
            }
            // Already in meeting state - do nothing
            else if isInMeeting && self.wasInMeeting {
                print("MeetingDetector: Still in meeting - not showing nub again")
            }
            
            // Update state tracker
            self.wasInMeeting = isInMeeting
        }
    }

    // Cached set of all known bundle IDs for fast lookup
    private lazy var knownMeetingBundleIds: Set<String> = {
        Set(MeetingApps.all.flatMap { $0.bundleIds })
    }()

    private func isKnownMeetingApp(_ bundleId: String) -> Bool {
        // Direct match against known bundle IDs
        if knownMeetingBundleIds.contains(bundleId) {
            return true
        }

        // Check if bundle ID contains any known meeting app keyword
        let bundleIdLower = bundleId.lowercased()
        for keyword in MeetingApps.meetingKeywords {
            if bundleIdLower.contains(keyword) {
                return true
            }
        }

        return false
    }

    private func getFriendlyAppName(from bundleId: String) -> String {
        // Find the app by checking if the bundle ID matches any known app
        for app in MeetingApps.all {
            if app.bundleIds.contains(bundleId) {
                return app.displayName
            }
        }

        // Try to extract meaningful name from bundle ID if not found
        let components = bundleId.components(separatedBy: ".")

        // For reversed domain names like "us.zoom.xos", check middle component
        if components.count >= 2 {
            let middleComponent = components[components.count - 2]
            if middleComponent.count > 2 {
                return middleComponent.capitalized
            }
        }

        // Fallback to last component
        if let lastComponent = components.last, lastComponent.count > 2 {
            return lastComponent.capitalized
        }

        return bundleId
    }
    
    // MARK: - Meeting Confirmation (Debouncing)

    /// Schedule a delayed confirmation for a meeting
    /// After 3 seconds, check if mic is still active before adding to activeMicApps
    private func scheduleMeetingConfirmation(for bundleId: String, currentBundleIds: Set<String>) {
        // Cancel any existing timer for this app
        pendingMeetingTimers[bundleId]?.invalidate()

        // Schedule on main thread to ensure timer fires correctly
        DispatchQueue.main.async { [weak self] in
            guard let self = self else { return }

            // Create a timer that fires after 3 seconds
            let timer = Timer.scheduledTimer(withTimeInterval: 3.0, repeats: false) { [weak self] _ in
                guard let self = self else { return }

                // Remove from pending
                self.pendingMeetingTimers.removeValue(forKey: bundleId)

                // Check if mic is STILL active by querying the latest system logs
                self.verifyAndConfirmMeeting(for: bundleId)
            }

            self.pendingMeetingTimers[bundleId] = timer
        }
    }

    /// Verify if mic is still active and confirm the meeting
    private func verifyAndConfirmMeeting(for bundleId: String) {
        // Check if mic is STILL active in the latest snapshot
        guard latestMicActiveApps.contains(bundleId) else {
            return
        }

        // Check if app is still running
        guard NSWorkspace.shared.runningApplications.first(where: { $0.bundleIdentifier == bundleId }) != nil else {
            return
        }

        // Add to active meetings - mic was sustained for 3+ seconds
        if !activeMicApps.contains(bundleId) {
            activeMicApps.insert(bundleId)
            notifyMeetingStateChanged()
        }
    }

    // MARK: - Browser Window Title Detection

    /// Check if Accessibility permission is granted
    private func checkAccessibilityPermission() -> Bool {
        let options = [kAXTrustedCheckOptionPrompt.takeUnretainedValue() as String: false]
        return AXIsProcessTrustedWithOptions(options as CFDictionary)
    }

    /// Request Accessibility permission with prompt
    private func requestAccessibilityPermission() {
        let options = [kAXTrustedCheckOptionPrompt.takeUnretainedValue() as String: true]
        _ = AXIsProcessTrustedWithOptions(options as CFDictionary)
    }

    /// Check browser window title using Accessibility API
    private func checkBrowserWindowTitle(for app: NSRunningApplication, bundleId: String) {
        // Check if we have Accessibility permission
        guard checkAccessibilityPermission() else {
            requestAccessibilityPermission()
            return
        }

        let pid = app.processIdentifier
        let axApp = AXUIElementCreateApplication(pid)

        // Get all windows for this app
        var windowsValue: CFTypeRef?
        let result = AXUIElementCopyAttributeValue(axApp, kAXWindowsAttribute as CFString, &windowsValue)

        guard result == .success,
              let windows = windowsValue as? [AXUIElement],
              !windows.isEmpty else {
            return
        }

        // Try to get the title from the first window (usually the frontmost)
        var windowTitle: String?
        for window in windows {
            var titleValue: CFTypeRef?
            let titleResult = AXUIElementCopyAttributeValue(window, kAXTitleAttribute as CFString, &titleValue)

            if titleResult == .success, let title = titleValue as? String, !title.isEmpty {
                windowTitle = title
                break
            }
        }

        guard let title = windowTitle else {
            return
        }

        currentWindowTitle = title

        // Check if the title contains meeting keywords
        if isMeetingWindowTitle(title) {
            if !activeMicApps.contains(bundleId) {
                activeMicApps.insert(bundleId)
                browserMeetingTitles[bundleId] = title  // Store initial meeting title
                notifyMeetingStateChanged()
            }
        } else {
            // Remove from tracked browsers since it's not a meeting
            trackedBrowserBundleIds.remove(bundleId)
        }
    }

    /// Check if a window title indicates a meeting is happening
    private func isMeetingWindowTitle(_ title: String) -> Bool {
        // Check if title contains any meeting keywords
        for keyword in meetingKeywordsInTitle {
            if title.contains(keyword) {
                return true
            }
        }
        return false
    }

    deinit {
        NSWorkspace.shared.notificationCenter.removeObserver(self)
        stop()
    }
}

// MARK: - FlutterStreamHandler
extension MeetingDetector: FlutterStreamHandler {
    func onListen(withArguments arguments: Any?, eventSink events: @escaping FlutterEventSink) -> FlutterError? {
        print("MeetingDetector: EventSink connected")
        self.eventSink = events

        // Send current state immediately
        let isInMeeting = !activeMicApps.isEmpty
        let apps = Array(activeMicApps)

        let event: [String: Any] = [
            "event": isInMeeting ? "meeting_started" : "meeting_ended",
            "isInMeeting": isInMeeting,
            "apps": apps
        ]

        events(event)

        return nil
    }

    func onCancel(withArguments arguments: Any?) -> FlutterError? {
        print("MeetingDetector: EventSink disconnected")
        self.eventSink = nil
        return nil
    }

    private func stopRecordingIfActive() {
        print("MeetingDetector: Triggering auto-stop recording because meeting ended")
        onMeetingEnded?()
    }
}
