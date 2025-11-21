import Foundation
import Cocoa
import FlutterMacOS

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

    // Bundle IDs to exclude from meeting detection
    private lazy var excludedBundleIds: Set<String> = {
        var excluded = Set<String>()

        // Exclude our own app
        if let ownBundleId = Bundle.main.bundleIdentifier {
            excluded.insert(ownBundleId)
            print("MeetingDetector: Excluding own bundle ID: \(ownBundleId)")
        }

        // Exclude system apps and utilities that aren't meeting apps
        excluded.insert("com.apple.controlcenter")
        excluded.insert("com.apple.systemuiserver")
        excluded.insert("com.apple.finder")

        return excluded
    }()

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
        print("MeetingDetector initialized")
    }

    // MARK: - Public Methods

    func configure(eventChannel: FlutterEventChannel) {
        self.eventChannel = eventChannel
        eventChannel.setStreamHandler(self)
        print("MeetingDetector: EventChannel configured")
    }

    func start() {
        guard logProcess == nil else {
            print("MeetingDetector: Already running")
            return
        }

        print("MeetingDetector: Starting log stream monitoring...")

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
        
        print("MeetingDetector: Using predicate: \(predicate)")

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
                print("MeetingDetector: log stream stderr: \(errorOutput)")
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
            print("MeetingDetector: log stream started successfully")
        } catch {
            print("MeetingDetector: Failed to start log stream: \(error.localizedDescription)")
            logProcess = nil
        }
    }

    func stop() {
        guard let process = logProcess else {
            print("MeetingDetector: Not running")
            return
        }

        print("MeetingDetector: Stopping log stream...")

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
        buffer = ""
        wasInMeeting = false

        print("MeetingDetector: Stopped")
    }

    func getActiveMeetingApps() -> [String] {
        return Array(activeMicApps)
    }

    // MARK: - Private Methods

    private func handleLogData(_ data: String) {
       // print("MeetingDetector: Raw data received: \(data.prefix(100))...") // Debug raw data
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
        let processPath = logEntry["processImagePath"] as? String ?? ""
        let category = logEntry["category"] as? String ?? ""
        var changed = false

        // Special handling for "Active activity attributions changed" messages
        // These are authoritative lists of what's currently using the mic
        if message.contains("Active activity attributions changed to") || 
           message.contains("Sorted active attributions") {
            
            let currentBundleIds = extractAllBundleIds(from: message)
            
            // 1. Identify apps that stopped (in activeMicApps but not in new list)
            for app in activeMicApps {
                if !currentBundleIds.contains(app) {
                    activeMicApps.remove(app)
                    changed = true
                    print("MeetingDetector: Microphone session ended (removed from list): \(app)")
                }
            }
            
            // 2. Identify apps that started (in new list but not in activeMicApps)
            for app in currentBundleIds {
                // Filter excluded/unknown apps
                if excludedBundleIds.contains(app) { continue }
                if !isKnownMeetingApp(app) { continue }
                
                if !activeMicApps.contains(app) {
                    activeMicApps.insert(app)
                    changed = true
                    print("MeetingDetector: Microphone session started (found in list): \(app)")
                }
            }
            
            if changed {
                notifyMeetingStateChanged()
            }
            return
        }

        // Only process microphone-related events
        let messageLower = message.lowercased()
        guard messageLower.contains("microphone") || 
              messageLower.contains("mic") ||
              category.contains("Microphone") ||
              category.contains("Attribution") else {
            return
        }
        
       // print("MeetingDetector: *** MICROPHONE EVENT DETECTED *** category: \(category) | message: \(message)")

        // Check for session start events - try to detect any positive/active language
        if messageLower.contains("session_active") ||
           messageLower.contains("new_session") ||
           messageLower.contains("microphone in use") ||
           messageLower.contains("active") ||
           messageLower.contains("client") ||
           messageLower.contains("start") ||
           messageLower.contains("begin") ||
           messageLower.contains("using") {

            if let bundleId = extractBundleId(from: logEntry, processPath: processPath) {
                // Filter out excluded apps (our own app, system apps)
                if excludedBundleIds.contains(bundleId) {
                    return
                }

                // Filter out unknown apps - only allow known meeting apps
                if !isKnownMeetingApp(bundleId) {
                    return
                }

                if !activeMicApps.contains(bundleId) {
                    activeMicApps.insert(bundleId)
                    changed = true
                    print("MeetingDetector: Microphone session started: \(bundleId)")
                }
            }
        }

        // Check for session end events
        if messageLower.contains("session_inactive") ||
           messageLower.contains("session_expired") ||
           messageLower.contains("microphone released") ||
           messageLower.contains("inactive") ||
           messageLower.contains("stop") ||
           messageLower.contains("end") ||
           messageLower.contains("released") {

            if let bundleId = extractBundleId(from: logEntry, processPath: processPath) {
                if activeMicApps.contains(bundleId) {
                    activeMicApps.remove(bundleId)
                    changed = true
                    print("MeetingDetector: Microphone session ended: \(bundleId)")
                }
            }
        }

        // Notify Flutter if apps changed
        if changed {
            notifyMeetingStateChanged()
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

    // Known meeting/collaboration app bundle IDs
    private let knownMeetingApps: Set<String> = [
        // Video conferencing
        "us.zoom.xos", "com.zoom.us", "zoom.us",
        "com.microsoft.teams", "com.microsoft.teams2",
        "com.google.Chrome",
        "com.webex.meetingmanager", "com.cisco.webexmeetings", "com.cisco.webexmeetingsapp",
        "com.goto.meeting", "com.citrixonline.GoToMeeting",
        "com.bluejeans.app",

        // Collaboration
        "com.tinyspeck.slackmacgap",
        "com.hnc.Discord", "com.discord",
        "com.skype.skype",

        // Browsers (can be used for Google Meet, etc)
        "com.apple.Safari",
        "com.brave.Browser",
        "org.mozilla.firefox",
        "company.thebrowser.Browser",
        "com.microsoft.edgemac",

        // Other
        "com.apple.FaceTime",
        "com.ringcentral.ringcentral",
        "com.8x8.8x8-work",
        "com.whereby.desktop", "com.whereby.app",
        "com.around.Around", "com.around.app",
        "com.jam.desktop",
        "app.tuple.app",
        "net.whatsapp.WhatsApp",
        "org.jitsi.jitsi-meet"
    ]

    private func isKnownMeetingApp(_ bundleId: String) -> Bool {
        // Direct match
        if knownMeetingApps.contains(bundleId) {
            return true
        }

        // Check if bundle ID contains any known meeting app identifier
        let bundleIdLower = bundleId.lowercased()
        let meetingKeywords = ["zoom", "teams", "webex", "meet", "slack", "discord",
                               "skype", "facetime", "whereby", "around", "tuple"]

        for keyword in meetingKeywords {
            if bundleIdLower.contains(keyword) {
                return true
            }
        }

        return false
    }

    private func getFriendlyAppName(from bundleId: String) -> String {
        // Map common bundle IDs to friendly names (based on Granola's app list)
        let appNameMap: [String: String] = [
            // Video conferencing
            "us.zoom.xos": "Zoom",
            "com.zoom.us": "Zoom",
            "zoom.us": "Zoom",
            "com.microsoft.teams": "Microsoft Teams",
            "com.microsoft.teams2": "Microsoft Teams",
            "com.google.Chrome": "Google Meet",
            "com.webex.meetingmanager": "Webex",
            "com.cisco.webexmeetings": "Webex",
            "com.cisco.webexmeetingsapp": "Webex",
            "com.goto.meeting": "GoToMeeting",
            "com.citrixonline.GoToMeeting": "GoToMeeting",
            "com.bluejeans.app": "BlueJeans",

            // Collaboration
            "com.tinyspeck.slackmacgap": "Slack",
            "com.hnc.Discord": "Discord",
            "com.discord": "Discord",
            "com.skype.skype": "Skype",

            // Other
            "com.apple.FaceTime": "FaceTime",
            "com.ringcentral.ringcentral": "RingCentral",
            "com.8x8.8x8-work": "8x8",
            "com.whereby.desktop": "Whereby",
            "com.whereby.app": "Whereby",
            "com.around.Around": "Around",
            "com.around.app": "Around",
            "com.jam.desktop": "Jam",
            "app.tuple.app": "Tuple",
            "net.whatsapp.WhatsApp": "WhatsApp",
            "org.jitsi.jitsi-meet": "Jitsi Meet"
        ]
        
        // Check for exact match
        if let name = appNameMap[bundleId] {
            return name
        }
        
        // Check if bundle ID contains any known app name
        for (key, value) in appNameMap {
            if bundleId.lowercased().contains(key.lowercased()) {
                return value
            }
        }
        
        // Try to extract meaningful name from bundle ID
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
    
    deinit {
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
