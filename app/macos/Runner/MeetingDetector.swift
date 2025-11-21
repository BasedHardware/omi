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
        
        // Debug: Print ALL events to see what Control Center is logging
        // print("MeetingDetector: category: \(category) | message: \(message) | path: \(processPath)")

        // Only process microphone-related events
        let messageLower = message.lowercased()
        guard messageLower.contains("microphone") || 
              messageLower.contains("mic") ||
              category.contains("Microphone") ||
              category.contains("Attribution") else {
            return
        }
        
       // print("MeetingDetector: *** MICROPHONE EVENT DETECTED *** category: \(category) | message: \(message)")

        var changed = false

        // Check for session start events - try to detect any positive/active language
        if messageLower.contains("session_active") ||
           messageLower.contains("new_session") ||
           messageLower.contains("microphone in use") ||
           messageLower.contains("attribution") ||
           messageLower.contains("active") ||
           messageLower.contains("client") ||
           messageLower.contains("start") ||
           messageLower.contains("begin") ||
           messageLower.contains("using") {

            if let bundleId = extractBundleId(from: logEntry, processPath: processPath) {
                if !activeMicApps.contains(bundleId) {
                    activeMicApps.insert(bundleId)
                    changed = true
                    print("MeetingDetector: ✅ Microphone session started: \(bundleId)")
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
                    print("MeetingDetector: ❌ Microphone session ended: \(bundleId)")
                }
            }
        }

        // Notify Flutter if apps changed
        if changed {
            notifyMeetingStateChanged()
        }
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
        
        // Directly control the nub from native side
        DispatchQueue.main.async {
            if isInMeeting {
                let appName = apps.first ?? "Meeting"
                // Convert bundle ID to friendly name
                let friendlyName = self.getFriendlyAppName(from: appName)
                print("MeetingDetector: Showing nub for \(friendlyName)")
                NubManager.shared.showNub(for: friendlyName)
            } else {
                print("MeetingDetector: Hiding nub - meeting ended")
                NubManager.shared.hideNub()
            }
        }
    }

    private func getFriendlyAppName(from bundleId: String) -> String {
        // Map common bundle IDs to friendly names (based on Granola's app list)
        let appNameMap: [String: String] = [
            // Video conferencing
            "us.zoom.xos": "Zoom",
            "com.zoom.us": "Zoom",
            "com.microsoft.teams": "Microsoft Teams",
            "com.microsoft.teams2": "Microsoft Teams",
            "com.google.Chrome": "Google Meet",
            "com.webex.meetingmanager": "Webex",
            "com.cisco.webexmeetings": "Webex",
            "com.goto.meeting": "GoToMeeting",
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
            "com.around.Around": "Around",
            "com.jam.desktop": "Jam"
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
}
