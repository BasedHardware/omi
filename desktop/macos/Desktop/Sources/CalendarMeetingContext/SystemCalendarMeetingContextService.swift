import EventKit
import Foundation

enum SystemCalendarAuthorizationState: Sendable {
  case notDetermined
  case allowed
  case unavailable
}

struct DesktopMeetingParticipant: Equatable, Sendable {
  let name: String?
  let email: String?
}

struct SystemCalendarEventSnapshot: Equatable, Sendable {
  let calendarEventID: String
  let title: String
  let startTime: Date
  let endTime: Date
  let isAllDay: Bool
  let isCanceled: Bool
  let participants: [DesktopMeetingParticipant]
  let urlCandidates: [String]
}

enum DesktopMeetingSource: Equatable, Sendable {
  case systemCalendar
  case derived(calendarSource: String, egress: DerivedDataEgressRequest)

  var calendarSource: String {
    switch self {
    case .systemCalendar: return "system_calendar"
    case .derived(let calendarSource, _): return calendarSource
    }
  }

  var egressRequest: DerivedDataEgressRequest? {
    guard case .derived(_, let request) = self else { return nil }
    return request
  }
}

struct DesktopMeetingPayload: Equatable, Sendable {
  let calendarEventID: String
  let source: DesktopMeetingSource
  let title: String
  let startTime: Date
  let endTime: Date
  let participants: [DesktopMeetingParticipant]
  let platform: String?
  let meetingLink: String?

  var calendarSource: String { source.calendarSource }

  var wireBody: [String: Any] {
    get throws {
      if let request = source.egressRequest {
        try DerivedDataEgressPolicy.authorize(request)
      }
      let formatter = ISO8601DateFormatter()
      formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]

      var body: [String: Any] = [
        "calendar_event_id": calendarEventID,
        "calendar_source": calendarSource,
        "title": title,
        "start_time": formatter.string(from: startTime),
        "end_time": formatter.string(from: endTime),
        "participants": participants.map { participant in
          var value: [String: Any] = [:]
          if let name = participant.name { value["name"] = name }
          if let email = participant.email { value["email"] = email }
          return value
        },
      ]
      if let platform { body["platform"] = platform }
      if let meetingLink { body["meeting_link"] = meetingLink }
      return body
    }
  }
}

protocol SystemCalendarEventProviding: Sendable {
  func authorizationState() async -> SystemCalendarAuthorizationState
  func requestAccess() async -> Bool
  func events(in interval: DateInterval) async -> [SystemCalendarEventSnapshot]
}

protocol DesktopMeetingUploading: Sendable {
  func upload(_ payload: DesktopMeetingPayload) async throws
}

actor EventKitSystemCalendarProvider: SystemCalendarEventProviding {
  // EKEventStore is not Sendable, so Swift 6 rejects sending this actor-isolated reference into
  // nonisolated SDK entry points (requestFullAccessToEvents). Every actual use stays confined to
  // this actor; the unchecked annotation only covers the SDK-interop boundary.
  private nonisolated(unsafe) let eventStore = EKEventStore()

  func authorizationState() -> SystemCalendarAuthorizationState {
    switch EKEventStore.authorizationStatus(for: .event) {
    case .fullAccess, .authorized:
      return .allowed
    case .notDetermined:
      return .notDetermined
    case .denied, .restricted, .writeOnly:
      return .unavailable
    @unknown default:
      return .unavailable
    }
  }

  func requestAccess() async -> Bool {
    if #available(macOS 14.0, *) {
      return (try? await eventStore.requestFullAccessToEvents()) == true
    }
    return await requestLegacyAccess()
  }

  private func requestLegacyAccess() async -> Bool {
    await withCheckedContinuation { continuation in
      // The deployment target is macOS 14, but this dynamic call preserves the correct legacy
      // behavior if the file is reused by an older target without compiling a deprecated API call
      // under the package's warnings-as-errors policy.
      let selector = NSSelectorFromString("requestAccessToEntityType:completion:")
      typealias LegacyRequestAccess =
        @convention(c) (
          AnyObject, Selector, EKEntityType, @escaping @convention(block) (Bool, NSError?) -> Void
        ) -> Void
      let implementation = eventStore.method(for: selector)
      let requestAccess = unsafeBitCast(implementation, to: LegacyRequestAccess.self)
      requestAccess(eventStore, selector, .event) { granted, _ in
        continuation.resume(returning: granted)
      }
    }
  }

  func events(in interval: DateInterval) -> [SystemCalendarEventSnapshot] {
    let predicate = eventStore.predicateForEvents(
      withStart: interval.start,
      end: interval.end,
      calendars: nil)
    return eventStore.events(matching: predicate).map(Self.snapshot)
  }

  private static func snapshot(_ event: EKEvent) -> SystemCalendarEventSnapshot {
    var seenParticipants = Set<String>()
    var participants: [DesktopMeetingParticipant] = []
    let invitees = ([event.organizer].compactMap { $0 } + (event.attendees ?? []))
      .filter { $0.participantStatus != .declined }

    for invitee in invitees {
      let rawName = invitee.name?.trimmingCharacters(in: .whitespacesAndNewlines)
      let rawEmail =
        invitee.url.scheme?.lowercased() == "mailto"
        ? URLComponents(url: invitee.url, resolvingAgainstBaseURL: false)?.path.removingPercentEncoding
        : nil
      let email = rawEmail?.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
      let name =
        rawName?.isEmpty == false && rawName?.caseInsensitiveCompare(email ?? "") != .orderedSame
        ? rawName
        : nil
      guard let identity = email ?? name?.lowercased(), !identity.isEmpty else { continue }
      guard seenParticipants.insert(identity).inserted else { continue }
      participants.append(DesktopMeetingParticipant(name: name, email: email))
      if participants.count == 50 { break }
    }

    return SystemCalendarEventSnapshot(
      calendarEventID: event.eventIdentifier ?? "",
      title: event.title ?? "",
      startTime: event.startDate,
      endTime: event.endDate,
      isAllDay: event.isAllDay,
      isCanceled: event.status == .canceled,
      participants: participants,
      // Notes and location never leave the provider. They are used only to find a supported
      // conferencing URL; the payload contains the resulting URL/platform, not the source text.
      urlCandidates: [event.url?.absoluteString, event.location, event.notes].compactMap { $0 }
    )
  }
}

struct BackendDesktopMeetingUploader: DesktopMeetingUploading {
  func upload(_ payload: DesktopMeetingPayload) async throws {
    let apiClient = APIClient.shared
    let headers = try await apiClient.buildHeaders(requireAuth: true, includeBYOK: false)
    let baseURL = await apiClient.baseURL
    let generatedClient = OmiAPI.OmiApiClient(baseURL: baseURL, headers: headers)
    _ = try await OmiAPI.storeCalendarMeetingV1CalendarMeetingsPost(
      client: generatedClient,
      xAppPlatform: "macos",
      xAppVersion: Bundle.main.infoDictionary?["CFBundleShortVersionString"] as? String,
      body: OmiAnyCodable(try payload.wireBody)
    )
  }
}

actor SystemCalendarMeetingContextService {
  static let shared = SystemCalendarMeetingContextService()

  static let searchTolerance: TimeInterval = 30 * 60
  static let maximumEventsPerSync = 20

  private let provider: any SystemCalendarEventProviding
  private let uploader: any DesktopMeetingUploading
  private var requestedAccessThisLaunch = false
  private var uploadedEventIDs = Set<String>()

  init(
    provider: any SystemCalendarEventProviding = EventKitSystemCalendarProvider(),
    uploader: any DesktopMeetingUploading = BackendDesktopMeetingUploader()
  ) {
    self.provider = provider
    self.uploader = uploader
  }

  /// Called asynchronously when a meeting is detected. This is the only path that can prompt.
  /// A denied/restricted decision is terminal until macOS reports a different authorization state.
  func prepareAroundNow(now: Date = Date()) async {
    switch await provider.authorizationState() {
    case .allowed:
      await sync(interval: Self.queryInterval(overlapping: DateInterval(start: now, end: now)))
    case .notDetermined:
      guard !requestedAccessThisLaunch else { return }
      requestedAccessThisLaunch = true
      guard await provider.requestAccess() else { return }
      await sync(interval: Self.queryInterval(overlapping: DateInterval(start: now, end: now)))
    case .unavailable:
      return
    }
  }

  /// Finalization never prompts. It only consumes an existing grant, and every error is fail-open
  /// so calendar work cannot prevent the recording from becoming a conversation.
  func syncAuthorizedEvents(overlapping recordingInterval: DateInterval) async {
    guard await provider.authorizationState() == .allowed else { return }
    await sync(interval: Self.queryInterval(overlapping: recordingInterval))
  }

  private func sync(interval: DateInterval) async {
    let payloads = Self.payloads(from: await provider.events(in: interval), within: interval)
    var stored = 0
    for payload in payloads where !uploadedEventIDs.contains(payload.calendarEventID) {
      guard !Task.isCancelled else { return }
      do {
        try await uploader.upload(payload)
        uploadedEventIDs.insert(payload.calendarEventID)
        stored += 1
      } catch {
        // Calendar context is optional and sensitive. Keep logs metadata-only and let recording
        // finalization continue; a later lifecycle edge/retry may attempt this event again.
        log("SystemCalendarMeetingContext: upload failed")
      }
    }
    if stored > 0 {
      log("SystemCalendarMeetingContext: stored \(stored) nearby event(s)")
    }
  }

  static func queryInterval(overlapping interval: DateInterval) -> DateInterval {
    DateInterval(
      start: interval.start.addingTimeInterval(-searchTolerance),
      end: interval.end.addingTimeInterval(searchTolerance))
  }

  static func payloads(
    from snapshots: [SystemCalendarEventSnapshot],
    within interval: DateInterval,
    maximumCount: Int = maximumEventsPerSync
  ) -> [DesktopMeetingPayload] {
    guard maximumCount > 0 else { return [] }
    var seenIDs = Set<String>()
    return
      snapshots
      .filter { snapshot in
        !snapshot.isAllDay
          && !snapshot.isCanceled
          && !snapshot.calendarEventID.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
          && !snapshot.title.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
          && snapshot.startTime < interval.end
          && snapshot.endTime > interval.start
          && snapshot.endTime > snapshot.startTime
      }
      .sorted {
        if $0.startTime == $1.startTime { return $0.calendarEventID < $1.calendarEventID }
        return $0.startTime < $1.startTime
      }
      .compactMap { snapshot -> DesktopMeetingPayload? in
        guard seenIDs.insert(snapshot.calendarEventID).inserted else { return nil }
        let conference = conferencingIdentity(in: snapshot.urlCandidates)
        return DesktopMeetingPayload(
          calendarEventID: snapshot.calendarEventID,
          source: .systemCalendar,
          title: snapshot.title.trimmingCharacters(in: .whitespacesAndNewlines),
          startTime: snapshot.startTime,
          endTime: snapshot.endTime,
          participants: snapshot.participants,
          platform: conference?.platform,
          meetingLink: conference?.url.absoluteString)
      }
      .prefix(maximumCount)
      .map { $0 }
  }

  static func conferencingIdentity(in candidates: [String]) -> (platform: String, url: URL)? {
    for candidate in candidates {
      for token in candidate.split(whereSeparator: { $0.isWhitespace }) {
        let trimmed = token.trimmingCharacters(in: CharacterSet(charactersIn: "<>[](){}\"',.;"))
        guard let url = URL(string: trimmed), url.scheme?.lowercased() == "https",
          let host = url.host?.lowercased()
        else { continue }
        let path = url.path.lowercased()
        if (host == "zoom.us" || host.hasSuffix(".zoom.us")) && (path.contains("/j/") || path.contains("/my/")) {
          return ("Zoom", url)
        }
        if host == "meet.google.com", path.split(separator: "/").first?.isEmpty == false {
          return ("Google Meet", url)
        }
        if host == "teams.microsoft.com" && (path.contains("/l/meetup-join") || path.contains("/meet/")) {
          return ("Teams", url)
        }
        if (host == "webex.com" || host.hasSuffix(".webex.com"))
          && (path.contains("/meet/") || path.contains("/join/"))
        {
          return ("Webex", url)
        }
      }
    }
    return nil
  }
}
