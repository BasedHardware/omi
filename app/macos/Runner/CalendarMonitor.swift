import Foundation
import EventKit
import FlutterMacOS

class CalendarMonitor: NSObject, FlutterStreamHandler {

    // MARK: - Configuration Constants

    static let SCAN_INTERVAL: TimeInterval = 60.0              // Check every 60 seconds (1 minute)
    static let LOOKAHEAD_WINDOW: TimeInterval = 30 * 24 * 60 * 60  // Next 30 days (for syncing to Firestore)
    static let NUB_WINDOW: TimeInterval = 60 * 60              // Show nubs for meetings in next 60 minutes
    static let NUB_TRIGGER_EARLY: TimeInterval = 5 * 60        // Start showing 5 min before
    static let NUB_TRIGGER_LATE: TimeInterval = 2 * 60         // Stop showing 2 min before
    static let MEETING_START_GRACE: TimeInterval = 5 * 60      // Show 5 min after start (late joins)
    static let SNOOZE_DURATION: TimeInterval = 5 * 60          // 5 minutes

    static let MIN_MEETING_DURATION: TimeInterval = 5 * 60         // 5 minutes
    static let MAX_MEETING_DURATION: TimeInterval = 8 * 60 * 60    // 8 hours
    static let MIN_ATTENDEE_COUNT: Int = 2                         // Including organizer

    // MARK: - Properties

    private let eventStore = EKEventStore()
    private var isAuthorized = false
    private var isMonitoring = false

    // Monitoring
    private var monitoringTimer: Timer?
    private var upcomingMeetings: [String: EKEvent] = [:]      // eventId -> event
    private var notifiedUpcoming: Set<String> = []             // Events we've shown "upcoming" nub for
    private var notifiedStarted: Set<String> = []              // Events we've shown "started" nub for
    private var snoozedMeetings: [String: Date] = [:]          // eventId -> snooze until time
    private var scheduledNubTimers: [String: Timer] = [:]      // eventId -> scheduled timer for showing nub at meeting start
    
    // Settings
    private var showEventsWithNoParticipants: Bool = false
    private var showMeetingsInMenuBar: Bool = true

    // Flutter stream
    private var eventSink: FlutterEventSink?

    // MARK: - Initialization

    override init() {
        super.init()
    }

    deinit {
        stopMonitoring()
    }

    // MARK: - Permission Management

    func requestAccess(completion: @escaping (Bool) -> Void) {
        if #available(macOS 14.0, *) {
            eventStore.requestFullAccessToEvents { [weak self] granted, error in
                if let error = error {
                    print("CalendarMonitor: Permission error: \(error.localizedDescription)")
                    completion(false)
                    return
                }

                self?.isAuthorized = granted
                print("CalendarMonitor: Permission \(granted ? "granted" : "denied")")
                completion(granted)
            }
        } else {
            // For macOS < 14.0
            eventStore.requestAccess(to: .event) { [weak self] granted, error in
                if let error = error {
                    print("CalendarMonitor: Permission error: \(error.localizedDescription)")
                    completion(false)
                    return
                }

                self?.isAuthorized = granted
                print("CalendarMonitor: Permission \(granted ? "granted" : "denied")")
                completion(granted)
            }
        }
    }

    func checkAuthorizationStatus() -> Bool {
        if #available(macOS 14.0, *) {
            let status = EKEventStore.authorizationStatus(for: .event)
            return status == .fullAccess || status == .authorized
        } else {
            let status = EKEventStore.authorizationStatus(for: .event)
            return status == .authorized
        }
    }

    // MARK: - Monitoring Control

    func startMonitoring() {
        // Update isAuthorized property from actual status
        isAuthorized = checkAuthorizationStatus()
        guard isAuthorized else {
            return
        }

        guard !isMonitoring else {
            return
        }

        isMonitoring = true

        // Initial scan
        scanForUpcomingMeetings()

        // Set up timer for periodic scanning
        monitoringTimer = Timer.scheduledTimer(
            withTimeInterval: CalendarMonitor.SCAN_INTERVAL,
            repeats: true
        ) { [weak self] _ in
            self?.scanForUpcomingMeetings()
        }

        // Register for calendar change notifications
        NotificationCenter.default.addObserver(
            self,
            selector: #selector(calendarDatabaseChanged),
            name: .EKEventStoreChanged,
            object: eventStore
        )
    }

    func stopMonitoring() {
        monitoringTimer?.invalidate()
        monitoringTimer = nil
        isMonitoring = false
        upcomingMeetings.removeAll()
        notifiedUpcoming.removeAll()
        notifiedStarted.removeAll()

        // Invalidate all scheduled timers
        for (_, timer) in scheduledNubTimers {
            timer.invalidate()
        }
        scheduledNubTimers.removeAll()
    }
    
    func updateSettings(showEventsWithNoParticipants: Bool? = nil, showMeetingsInMenuBar: Bool? = nil) {
        if let showEventsWithNoParticipants = showEventsWithNoParticipants {
            
            self.showEventsWithNoParticipants = showEventsWithNoParticipants
        }
        if let showMeetingsInMenuBar = showMeetingsInMenuBar {
            self.showMeetingsInMenuBar = showMeetingsInMenuBar

            if !showMeetingsInMenuBar {
                for (_, timer) in scheduledNubTimers {
                    timer.invalidate()
                }
                scheduledNubTimers.removeAll()

                MenuBarManager.shared.resetToDefaultView()
            }
        }
        // Rescan immediately to apply new filter
        if isMonitoring {
            scanForUpcomingMeetings()
        }
    }

    @objc private func calendarDatabaseChanged(notification: Notification) {
        scanForUpcomingMeetings()
    }

    // MARK: - Event Scanning

    private func scanForUpcomingMeetings() {
        let now = Date()
        let lookAheadUntil = now.addingTimeInterval(CalendarMonitor.LOOKAHEAD_WINDOW)

        if !showMeetingsInMenuBar {
            MenuBarManager.shared.resetToDefaultView()
            return
        }

        // Query events
        let predicate = eventStore.predicateForEvents(
            withStart: now,
            end: lookAheadUntil,
            calendars: nil
        )

        let events = eventStore.events(matching: predicate)

        // Filter to only meetings
        let meetings = events.filter { isMeetingEvent($0) }

        // Update our tracking
        var newUpcomingMeetings: [String: EKEvent] = [:]

        for meeting in meetings {
            guard let eventId = meeting.eventIdentifier else { continue }
            newUpcomingMeetings[eventId] = meeting

            // Check if we should show nub for this meeting
            if shouldShowNub(for: meeting) {
                // Check if not snoozed and not already notified
                if !isMeetingSnoozed(eventId: eventId) && !notifiedUpcoming.contains(eventId) {
                    // Show "upcoming" nub (2-5 minutes before meeting)
                    notifyUpcomingMeeting(meeting)
                    notifiedUpcoming.insert(eventId)
                }
            }

            // Schedule timer to show nub at meeting start (if not already scheduled and meeting hasn't started)
            let timeUntilStart = meeting.startDate.timeIntervalSince(now)
            if timeUntilStart > 0 && timeUntilStart <= CalendarMonitor.NUB_WINDOW {
                // Only schedule if we don't have a timer yet
                if scheduledNubTimers[eventId] == nil {
                    scheduleNubForMeetingStart(meeting: meeting, eventId: eventId)
                }
            }
        }

        // Clean up old meetings
        let oldEventIds = Set(upcomingMeetings.keys)
        let newEventIds = Set(newUpcomingMeetings.keys)
        let removedEventIds = oldEventIds.subtracting(newEventIds)

        for eventId in removedEventIds {
            if let event = upcomingMeetings[eventId] {
                notifyMeetingEnded(event)
            }
            notifiedUpcoming.remove(eventId)
            notifiedStarted.remove(eventId)

            // Cancel scheduled timer if meeting was removed
            if let timer = scheduledNubTimers[eventId] {
                timer.invalidate()
                scheduledNubTimers.removeValue(forKey: eventId)
            }
        }

        upcomingMeetings = newUpcomingMeetings

        if showMeetingsInMenuBar {
            let futureMeetings = upcomingMeetings.values.filter { $0.startDate > now }

            if let closestMeeting = futureMeetings.min(by: { $0.startDate < $1.startDate }) {
                let minutesUntil = Int(closestMeeting.startDate.timeIntervalSinceNow / 60)
                if minutesUntil >= 0 {
                    MenuBarManager.shared.updateWithMeeting(title: closestMeeting.title, startDate: closestMeeting.startDate)
                } else {
                    MenuBarManager.shared.resetToDefaultView()
                }
            } else {
                // No upcoming meetings, reset to default
                MenuBarManager.shared.resetToDefaultView()
            }
        }

        // Notify Flutter about meetings list update
        sendEventToFlutter([
            "type": "meetingsUpdated",
            "count": upcomingMeetings.count
        ])

        // Clean up old snoozes
        cleanupExpiredSnoozes()
    }

    // MARK: - Meeting Detection Logic

    func isMeetingEvent(_ event: EKEvent) -> Bool {
        // 1. Must not be all-day
        if event.isAllDay {
            return false
        }

        // 2. Must not be in the past (already ended)
        let now = Date()
        if event.endDate < now {
            return false
        }

        // 3. Must have reasonable duration
        let duration = event.endDate.timeIntervalSince(event.startDate)
        if duration < CalendarMonitor.MIN_MEETING_DURATION || duration > CalendarMonitor.MAX_MEETING_DURATION {
            return false
        }

        // 4. Must not be declined
        if let attendees = event.attendees {
            for attendee in attendees where attendee.isCurrentUser {
                if attendee.participantStatus == .declined {
                    return false
                }
            }
        }

        // 5. Must have at least 2 attendees (including organizer) - UNLESS showEventsWithNoParticipants is enabled
        if !showEventsWithNoParticipants {
            let attendeeCount = (event.attendees?.count ?? 0) + 1 // +1 for organizer
            if attendeeCount < CalendarMonitor.MIN_ATTENDEE_COUNT {
                return false
            }
        }

        // 6. Must have video conferencing URL or meeting keywords - UNLESS showEventsWithNoParticipants is enabled
        if !showEventsWithNoParticipants {
            if extractMeetingPlatform(event) == nil {
                return false
            }
        }
        
        return true
    }

    func extractMeetingPlatform(_ event: EKEvent) -> String? {
        // Check URL first
        if let url = event.url?.absoluteString {
            if let platform = getFriendlyPlatformName(url) {
                return platform
            }
        }

        // Check notes
        if let notes = event.notes {
            if let platform = getFriendlyPlatformName(notes) {
                return platform
            }
        }

        // Check location (sometimes URLs are in location field)
        if let location = event.location {
            if let platform = getFriendlyPlatformName(location) {
                return platform
            }
        }

        return nil
    }

    func getFriendlyPlatformName(_ text: String) -> String? {
        return MeetingApps.extractPlatformFromURL(text)
    }

    private func shouldShowNub(for event: EKEvent) -> Bool {
        let now = Date()
        guard let startTime = event.startDate, let _ = event.endDate else { return false }

        let timeUntilStart = startTime.timeIntervalSince(now)

        // Show if meeting starts in 2-5 minutes (pre-meeting nub)
        if timeUntilStart >= CalendarMonitor.NUB_TRIGGER_LATE &&
           timeUntilStart <= CalendarMonitor.NUB_TRIGGER_EARLY {
            return true
        }

        return false
    }

    // MARK: - Nub Triggering

    private func scheduleNubForMeetingStart(meeting: EKEvent, eventId: String) {
        let now = Date()
        let timeUntilStart = meeting.startDate.timeIntervalSince(now)

        // Only schedule if meeting starts in the future
        guard timeUntilStart > 0 else { return }
        // Schedule timer to fire at meeting start
        DispatchQueue.main.async { [weak self] in
            let timer = Timer.scheduledTimer(withTimeInterval: timeUntilStart, repeats: false) { [weak self] _ in
                self?.handleScheduledMeetingStart(eventId: eventId)
            }
            self?.scheduledNubTimers[eventId] = timer
        }
    }

    private func handleScheduledMeetingStart(eventId: String) {

        // Remove timer from tracking
        scheduledNubTimers.removeValue(forKey: eventId)

        // Check if meeting still exists and hasn't been notified yet
        guard let meeting = upcomingMeetings[eventId],
              !notifiedStarted.contains(eventId),
              !isMeetingSnoozed(eventId: eventId) else {
            return
        }

        let title = meeting.title ?? "Meeting"
        let platform = extractMeetingPlatform(meeting) ?? "Calendar"

        // Check if recording is already active
        let isRecordingActive = NubManager.shared.isRecordingActive?() ?? false

        // Only show nub if not already recording
        if !isRecordingActive {
            // Show "started" nub directly
            DispatchQueue.main.async {
                NubManager.shared.showNubForCalendarMeetingStarted(
                    eventId: eventId,
                    title: title,
                    platform: platform
                )
            }
        }

        // Mark as notified
        notifiedStarted.insert(eventId)

        // Send event to Flutter
        if let startTime = meeting.startDate {
            sendEventToFlutter([
                "type": "started",
                "eventId": eventId,
                "title": title,
                "platform": platform,
                "startTime": ISO8601DateFormatter().string(from: startTime)
            ])
        }
    }

    private func notifyUpcomingMeeting(_ event: EKEvent) {
        guard let startTime = event.startDate,
              let eventId = event.eventIdentifier else { return }

        // Extract platform, use "Calendar" as fallback if none found
        let platform = extractMeetingPlatform(event) ?? "Calendar"

        let now = Date()
        let timeUntilStart = startTime.timeIntervalSince(now)
        let minutesUntilStart = Int(timeUntilStart / 60)

        let title = event.title ?? "Meeting"

        if minutesUntilStart > 0 {
            print("CalendarMonitor: 📅 Upcoming meeting in \(minutesUntilStart) min: \(title) • \(platform)")

            // Check if recording is already active via NubManager callback
            let isRecordingActive = NubManager.shared.isRecordingActive?() ?? false

            // Only show nub if not already recording
            if !isRecordingActive {
                // Show nub via NubManager
                DispatchQueue.main.async {
                    NubManager.shared.showNubForCalendarMeeting(
                        eventId: eventId,
                        title: title,
                        platform: platform,
                        minutesUntilStart: minutesUntilStart
                    )
                }
            }

            // Send event to Flutter
            sendEventToFlutter([
                "type": "upcomingSoon",
                "eventId": eventId,
                "title": title,
                "platform": platform,
                "minutesUntilStart": minutesUntilStart,
                "startTime": ISO8601DateFormatter().string(from: startTime)
            ])
        } else {
            // Check if recording is already active
            let isRecordingActive = NubManager.shared.isRecordingActive?() ?? false

            // Only show nub if not already recording
            if !isRecordingActive {
                // Show "started" nub
                DispatchQueue.main.async {
                    NubManager.shared.showNubForCalendarMeetingStarted(
                        eventId: eventId,
                        title: title,
                        platform: platform
                    )
                }
            }

            // Send event to Flutter
            sendEventToFlutter([
                "type": "started",
                "eventId": eventId,
                "title": title,
                "platform": platform,
                "startTime": ISO8601DateFormatter().string(from: startTime)
            ])
        }
    }

    private func notifyMeetingEnded(_ event: EKEvent) {
        guard let eventId = event.eventIdentifier else { return }
        let title = event.title ?? "Meeting"

        // Hide nub if it's still showing for this event
        DispatchQueue.main.async {
            NubManager.shared.hideNubIfCalendarMeeting(eventId: eventId)
        }

        // Send event to Flutter
        sendEventToFlutter([
            "type": "ended",
            "eventId": eventId,
            "title": title
        ])
    }

    // MARK: - Snooze Management

    func snoozeMeeting(eventId: String, duration: TimeInterval = SNOOZE_DURATION) {
        let snoozeUntil = Date().addingTimeInterval(duration)
        snoozedMeetings[eventId] = snoozeUntil

        // Hide nub
        DispatchQueue.main.async {
            NubManager.shared.hideNubIfCalendarMeeting(eventId: eventId)
        }

        // Cancel scheduled timer since meeting is snoozed
        if let timer = scheduledNubTimers[eventId] {
            timer.invalidate()
            scheduledNubTimers.removeValue(forKey: eventId)
        }

        // Reset notification flags so it can show again after snooze
        notifiedUpcoming.remove(eventId)
        notifiedStarted.remove(eventId)
    }

    func isMeetingSnoozed(eventId: String) -> Bool {
        guard let snoozeUntil = snoozedMeetings[eventId] else {
            return false
        }

        return Date() < snoozeUntil
    }

    private func cleanupExpiredSnoozes() {
        let now = Date()
        snoozedMeetings = snoozedMeetings.filter { $0.value > now }
    }

    // MARK: - Event Queries

    func getUpcomingMeetings() -> [[String: Any]] {
        var result: [[String: Any]] = []

        for (_, event) in upcomingMeetings {
            guard let eventId = event.eventIdentifier,
                  let startDate = event.startDate,
                  let endDate = event.endDate else { continue }

            // Use "Calendar" as fallback if no platform detected
            let platform = extractMeetingPlatform(event) ?? "Calendar"
            let attendeeCount = (event.attendees?.count ?? 0) + 1

            var meetingDict: [String: Any] = [
                "id": eventId,
                "title": event.title ?? "Meeting",
                "startTime": ISO8601DateFormatter().string(from: startDate),
                "endTime": ISO8601DateFormatter().string(from: endDate),
                "platform": platform,
                "attendeeCount": attendeeCount
            ]

            if let url = event.url?.absoluteString {
                meetingDict["meetingUrl"] = url
            }

            // Add participants with names and emails
            if let attendees = event.attendees {
                var participantsList: [[String: String]] = []

                for attendee in attendees {
                    var participantDict: [String: String] = [:]

                    // Add name if available
                    if let name = attendee.name, !name.isEmpty {
                        participantDict["name"] = name
                    }

                    // Add email if available (from URL property which contains mailto: URL)
                    let url = attendee.url
                    let urlString = url.absoluteString
                    if urlString.hasPrefix("mailto:") {
                        let email = urlString.replacingOccurrences(of: "mailto:", with: "")
                        if !email.isEmpty {
                            participantDict["email"] = email
                        }
                    }

                    // Only add participant if we have at least name or email
                    if !participantDict.isEmpty {
                        participantsList.append(participantDict)
                    }
                }

                if !participantsList.isEmpty {
                    meetingDict["participants"] = participantsList
                }
            }

            // Add notes/description if available
            if let notes = event.notes, !notes.isEmpty {
                meetingDict["notes"] = notes
            }

            result.append(meetingDict)
        }

        return result
    }
    
    func getAvailableCalendars() -> [[String: Any]] {
        var result: [[String: Any]] = []
        
        let calendars = eventStore.calendars(for: .event)
        
        for calendar in calendars {
            var calendarDict: [String: Any] = [
                "id": calendar.calendarIdentifier,
                "title": calendar.title,
                "type": calendar.type.rawValue,
                "isSubscribed": calendar.isSubscribed
            ]
            
            // Get RGB color components
            if let color = calendar.color {
                var red: CGFloat = 0
                var green: CGFloat = 0
                var blue: CGFloat = 0
                var alpha: CGFloat = 0
                color.getRed(&red, green: &green, blue: &blue, alpha: &alpha)
                
                calendarDict["colorRed"] = Int(red * 255)
                calendarDict["colorGreen"] = Int(green * 255)
                calendarDict["colorBlue"] = Int(blue * 255)
            }
            
            result.append(calendarDict)
        }
        
        return result
    }

    // MARK: - Flutter Communication

    private func sendEventToFlutter(_ data: [String: Any]) {
        guard let eventSink = eventSink else {
            print("CalendarMonitor: No event sink available")
            return
        }

        eventSink(data)
    }

    // MARK: - FlutterStreamHandler

    func onListen(withArguments arguments: Any?, eventSink events: @escaping FlutterEventSink) -> FlutterError? {
        print("CalendarMonitor: EventChannel stream started")
        self.eventSink = events
        return nil
    }

    func onCancel(withArguments arguments: Any?) -> FlutterError? {
        print("CalendarMonitor: EventChannel stream cancelled")
        self.eventSink = nil
        return nil
    }
}
