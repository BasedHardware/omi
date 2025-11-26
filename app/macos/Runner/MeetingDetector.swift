import Foundation
import Cocoa
import FlutterMacOS

class MeetingDetector: NSObject {

    // MARK: - Properties
    private var monitorTimer: Timer?
    private var activeMicApps = Set<String>()
    private var eventChannel: FlutterEventChannel?
    private var eventSink: FlutterEventSink?
    private var wasInMeeting = false  // Track previous meeting state

    // Callback for when meeting ends
    var onMeetingEnded: (() -> Void)?

    // Window title tracking for browsers
    private var trackedBrowserBundleIds = Set<String>()  // Browsers we're actively monitoring

    // Debouncing to prevent showing nub during brief mic checks
    private var pendingMeetingTimers: [String: Timer] = [:]  // Bundle ID -> Timer for delayed confirmation
    private var latestMeetingApps = Set<String>()  // Latest snapshot of apps with meeting windows

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


    // MARK: - Initialization
    override init() {
        super.init()
        setupAppMonitoring()
    }

    // Setup app termination monitoring
    private func setupAppMonitoring() {
        NSWorkspace.shared.notificationCenter.addObserver(
            self,
            selector: #selector(handleAppTermination(_:)),
            name: NSWorkspace.didTerminateApplicationNotification,
            object: nil
        )
    }

    @objc private func handleAppTermination(_ notification: Notification) {
        guard let app = notification.userInfo?[NSWorkspace.applicationUserInfoKey] as? NSRunningApplication,
              let bundleId = app.bundleIdentifier else {
            return
        }

        // If a meeting app terminated, immediately remove it
        if activeMicApps.contains(bundleId) {
            activeMicApps.remove(bundleId)
            trackedBrowserBundleIds.remove(bundleId)
            print("MeetingDetector: App terminated - removing \(bundleId)")
            notifyMeetingStateChanged()
        }
    }

    // MARK: - Public Methods

    func configure(eventChannel: FlutterEventChannel) {
        self.eventChannel = eventChannel
        eventChannel.setStreamHandler(self)
    }

    func start() {
        guard monitorTimer == nil else {
            print("MeetingDetector: Already running")
            return
        }


        // Perform initial check
        checkForMeetingApps()

        // Start polling every 3 seconds
        monitorTimer = Timer.scheduledTimer(
            withTimeInterval: 3.0,
            repeats: true
        ) { [weak self] _ in
            self?.checkForMeetingApps()
        }

    }

    func stop() {
        guard monitorTimer != nil else {
            return
        }

        // Stop the timer
        monitorTimer?.invalidate()
        monitorTimer = nil

        // Clear state
        activeMicApps.removeAll()
        trackedBrowserBundleIds.removeAll()
        latestMeetingApps.removeAll()
        wasInMeeting = false

        // Cancel all pending timers
        for (_, timer) in pendingMeetingTimers {
            timer.invalidate()
        }
        pendingMeetingTimers.removeAll()
    }

    func getActiveMeetingApps() -> [String] {
        return Array(activeMicApps)
    }

    // MARK: - Private Methods

    /// Check all running apps for active meetings using CGWindowList
    private func checkForMeetingApps() {
        let runningApps = NSWorkspace.shared.runningApplications
        var currentMeetingApps = Set<String>()

        // Build a map of PID -> bundleId for quick lookup
        var pidToBundleId: [Int32: String] = [:]
        
        for app in runningApps {
            guard let bundleId = app.bundleIdentifier else { continue }
            if excludedBundleIds.contains(bundleId) { continue }
            guard isKnownMeetingApp(bundleId) else { continue }
            
            pidToBundleId[app.processIdentifier] = bundleId
        }

        // Get all on-screen windows using Core Graphics
        guard let windowList = CGWindowListCopyWindowInfo(
            [.optionOnScreenOnly, .excludeDesktopElements],
            kCGNullWindowID
        ) as? [[String: Any]] else {
            // Update latest snapshot
            latestMeetingApps = currentMeetingApps
            handleMeetingAppsChanged(to: currentMeetingApps)
            return
        }

        // Check each window for meeting indicators
        for window in windowList {
            guard let ownerPID = window[kCGWindowOwnerPID as String] as? Int32,
                  let bundleId = pidToBundleId[ownerPID],
                  let title = window[kCGWindowName as String] as? String,
                  !title.isEmpty else {
                continue
            }

            // Check if window title indicates a meeting
            if isMeetingWindowTitle(title) {
                currentMeetingApps.insert(bundleId)
                
                // Track browsers separately for logging
                if MeetingApps.browserBundleIds.contains(bundleId) {
                    trackedBrowserBundleIds.insert(bundleId)
                }
            }
        }

        // Update latest snapshot
        latestMeetingApps = currentMeetingApps

        // Detect changes and update state
        handleMeetingAppsChanged(to: currentMeetingApps)
    }

    /// Handle changes in detected meeting apps
    private func handleMeetingAppsChanged(to newApps: Set<String>) {
        var stateChanged = false

        // Apps that stopped (were in activeMicApps but not in newApps)
        let stoppedApps = activeMicApps.subtracting(newApps)
        for bundleId in stoppedApps {
            // Meeting window no longer visible - remove it
            activeMicApps.remove(bundleId)
            trackedBrowserBundleIds.remove(bundleId)
            stateChanged = true
        }

        // Apps that started (in newApps but not in activeMicApps)
        let startedApps = newApps.subtracting(activeMicApps)
        for bundleId in startedApps {
            // Use debouncing to avoid false positives (e.g., briefly visiting a meeting page)
            if !pendingMeetingTimers.keys.contains(bundleId) {
                scheduleMeetingConfirmation(for: bundleId)
            }
        }

        if stateChanged {
            notifyMeetingStateChanged()
        }
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
    /// After 3 seconds, check if meeting window is still visible before adding to activeMicApps
    private func scheduleMeetingConfirmation(for bundleId: String) {
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

                // Check if meeting window is STILL visible
                self.verifyAndConfirmMeeting(for: bundleId)
            }

            self.pendingMeetingTimers[bundleId] = timer
        }
    }

    /// Verify if meeting window is still visible and confirm the meeting
    private func verifyAndConfirmMeeting(for bundleId: String) {
        // Check if meeting window is STILL visible in the latest snapshot
        guard latestMeetingApps.contains(bundleId) else {
            return
        }

        // Check if app is still running
        guard NSWorkspace.shared.runningApplications.first(where: { $0.bundleIdentifier == bundleId }) != nil else {
            return
        }

        // Add to active meetings - meeting window was sustained for 3+ seconds
        if !activeMicApps.contains(bundleId) {
            activeMicApps.insert(bundleId)
            notifyMeetingStateChanged()
        }
    }

    // MARK: - Window Title Detection

    /// Check if a window title indicates a meeting is happening
    private func isMeetingWindowTitle(_ title: String) -> Bool {
        // Special handling for Google Meet to avoid landing page false positives
        // Actual meetings have format: "Meet – xxx-yyyy-zzz" or "Meet - xxx-yyyy-zzz"
        // Landing page: "Google Meet - Google Chrome"
        if title.contains("Meet") {
            // If title starts with "Meet –" or "Meet -" (with dash), it's likely an actual meeting
            if title.hasPrefix("Meet –") || title.hasPrefix("Meet -") {
                // Look for meeting code pattern (xxx-xxx-xxx)
                let pattern = "[a-z]{3}-[a-z]{4}-[a-z]{3}"
                if title.range(of: pattern, options: .regularExpression) != nil {
                    return true
                }
            }

            // Check for meet.google.com URL in title
            if title.contains("meet.google.com") {
                return true
            }

            // If it's just "Google Meet" or similar without meeting code, it's the landing page
            if title.contains("Google Meet") && !title.hasPrefix("Meet") {
                return false
            }
        }

        // Check other meeting keywords normally
        for keyword in MeetingApps.meetingKeywordsInTitle {
            // Skip "Meet" since we handled it above
            if keyword == "Meet" || keyword == "meet.google.com" {
                continue
            }

            if title.contains(keyword) {
                return true
            }
        }

        return false
    }

    deinit {
        NSWorkspace.shared.notificationCenter.removeObserver(self)
        monitorTimer?.invalidate()
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
