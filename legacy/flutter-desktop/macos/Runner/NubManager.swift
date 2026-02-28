import Cocoa
import FlutterMacOS

// MARK: - Meeting Source

enum MeetingSource {
    case calendar(eventId: String, title: String, platform: String)
    case microphone(appName: String)
    case hybrid(eventId: String, title: String, platform: String, appName: String)
}

class NubManager {

    // MARK: - Singleton
    static let shared = NubManager()

    // MARK: - Properties
    fileprivate var nubWindow: NubWindow?
    private weak var mainFlutterWindow: NSWindow?

    // Callback to check if recording is active
    var isRecordingActive: (() -> Bool)?

    // Tracking meeting sources
    private var currentCalendarEventId: String?
    private var currentCalendarTitle: String?
    private var currentCalendarPlatform: String?
    private var currentMicrophoneApp: String?
    private var meetingSource: MeetingSource?

    // MARK: - Initialization
    private init() {
        setupNotifications()
    }

    // MARK: - Setup

    private func setupNotifications() {
    }

    // MARK: - Configuration

    func setMainWindow(_ window: NSWindow) {
        self.mainFlutterWindow = window
    }

    // MARK: - Public Methods (Microphone-based - existing)

    func showNub(for appName: String = "Meeting") {
        currentMicrophoneApp = appName

        DispatchQueue.main.async { [weak self] in
            guard let self = self else {
                return
            }

            if self.nubWindow == nil {
                self.nubWindow = NubWindow(
                    contentRect: NSRect.zero,
                    styleMask: [.borderless],
                    backing: .buffered,
                    defer: false
                )
            }

            // Check if we have matching calendar context
            if let eventId = self.currentCalendarEventId,
               let title = self.currentCalendarTitle,
               let platform = self.currentCalendarPlatform {
                // Hybrid: Calendar + Microphone
                self.meetingSource = .hybrid(eventId: eventId, title: title, platform: platform, appName: appName)

                let state = NubState.recording(title: title, platform: platform)
                self.nubWindow?.updateState(state)
            } else {
                // Mic-only
                self.meetingSource = .microphone(appName: appName)

                let state = NubState.microphoneActive(platform: appName)
                self.nubWindow?.updateState(state)
            }

            self.nubWindow?.show()
        }
    }

    func hideNub() {
        DispatchQueue.main.async { [weak self] in
            guard let self = self else { return }
            self.nubWindow?.hide()

            // Clear tracking when hiding
            self.currentMicrophoneApp = nil
            self.meetingSource = nil

        }
    }

    func isNubVisible() -> Bool {
        return nubWindow?.isVisible ?? false
    }

    /// Get the current meeting source (calendar, microphone, or hybrid)
    func getCurrentMeetingSource() -> MeetingSource? {
        return meetingSource
    }

    /// Check if there's an active calendar context
    func hasCalendarContext() -> Bool {
        return currentCalendarEventId != nil
    }

    // MARK: - Calendar-based Methods (new)

    func showNubForCalendarMeeting(eventId: String, title: String, platform: String, minutesUntilStart: Int) {
        // Track calendar context
        currentCalendarEventId = eventId
        currentCalendarTitle = title
        currentCalendarPlatform = platform

        DispatchQueue.main.async { [weak self] in
            guard let self = self else { return}

            if self.nubWindow == nil {
                self.nubWindow = NubWindow(
                    contentRect: NSRect.zero,
                    styleMask: [.borderless],
                    backing: .buffered,
                    defer: false
                )
            }

            // Check if microphone is already active for this meeting
            if let micApp = self.currentMicrophoneApp {
                // Hybrid: User already joined (mic active) + calendar context
                self.meetingSource = .hybrid(eventId: eventId, title: title, platform: platform, appName: micApp)

                let state = NubState.recording(title: title, platform: platform)
                self.nubWindow?.updateState(state)
            } else {
                // Calendar-only: Upcoming meeting
                self.meetingSource = .calendar(eventId: eventId, title: title, platform: platform)

                let state = NubState.upcomingMeeting(title: title, minutesUntil: minutesUntilStart, platform: platform)
                self.nubWindow?.updateState(state)
            }

            self.nubWindow?.show()
        }
    }

    func showNubForCalendarMeetingStarted(eventId: String, title: String, platform: String) {
        // Track calendar context
        currentCalendarEventId = eventId
        currentCalendarTitle = title
        currentCalendarPlatform = platform

        DispatchQueue.main.async { [weak self] in
            guard let self = self else { return }

            if self.nubWindow == nil {
                self.nubWindow = NubWindow(
                    contentRect: NSRect.zero,
                    styleMask: [.borderless],
                    backing: .buffered,
                    defer: false
                )
            }

            // Check if microphone is already active
            if let micApp = self.currentMicrophoneApp {
                // Hybrid: Meeting started + mic active
                self.meetingSource = .hybrid(eventId: eventId, title: title, platform: platform, appName: micApp)

                let state = NubState.recording(title: title, platform: platform)
                self.nubWindow?.updateState(state)
            } else {
                // Calendar-only: Meeting started but user hasn't joined yet
                self.meetingSource = .calendar(eventId: eventId, title: title, platform: platform)

                let state = NubState.meetingStarted(title: title, platform: platform)
                self.nubWindow?.updateState(state)
            }

            self.nubWindow?.show()
        }
    }

    func hideNubIfCalendarMeeting(eventId: String) {
        // Only hide if this is the currently showing calendar meeting
        // AND microphone is not active (don't hide if user is still in meeting)
        if currentCalendarEventId == eventId {
            if currentMicrophoneApp == nil {
                hideNub()
                currentCalendarEventId = nil
                currentCalendarTitle = nil
                currentCalendarPlatform = nil
            } else {
                // Update to mic-only state
                if let micApp = currentMicrophoneApp {
                    let state = NubState.microphoneActive(platform: micApp)
                    nubWindow?.updateState(state)
                    meetingSource = .microphone(appName: micApp)
                }
                // Clear calendar context but keep nub showing
                currentCalendarEventId = nil
                currentCalendarTitle = nil
                currentCalendarPlatform = nil
            }
        }
    }

    // MARK: - Cleanup

    deinit {
        NotificationCenter.default.removeObserver(self)
    }
}
