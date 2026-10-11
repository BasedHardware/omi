import Foundation
import XCTest

@testable import Omi_Computer

private actor SystemCalendarProviderStub: SystemCalendarEventProviding {
  private var state: SystemCalendarAuthorizationState
  private let grantsAccess: Bool
  private let snapshots: [SystemCalendarEventSnapshot]
  private var accessRequestCount = 0
  private var eventReadCount = 0

  init(
    state: SystemCalendarAuthorizationState,
    grantsAccess: Bool = false,
    snapshots: [SystemCalendarEventSnapshot] = []
  ) {
    self.state = state
    self.grantsAccess = grantsAccess
    self.snapshots = snapshots
  }

  func authorizationState() -> SystemCalendarAuthorizationState { state }

  func requestAccess() -> Bool {
    accessRequestCount += 1
    state = grantsAccess ? .allowed : .unavailable
    return grantsAccess
  }

  func events(in interval: DateInterval) -> [SystemCalendarEventSnapshot] {
    eventReadCount += 1
    return snapshots
  }

  func counts() -> (requests: Int, reads: Int) {
    (accessRequestCount, eventReadCount)
  }
}

private actor SystemCalendarUploaderStub: DesktopMeetingUploading {
  private var payloads: [DesktopMeetingPayload] = []

  func upload(_ payload: DesktopMeetingPayload) {
    payloads.append(payload)
  }

  func uploadedPayloads() -> [DesktopMeetingPayload] { payloads }
}

final class SystemCalendarMeetingContextServiceTests: XCTestCase {
  private let referenceDate = Date(timeIntervalSince1970: 1_750_000_000)

  func testPayloadSelectionIsBoundedDeduplicatedAndPrivacyScoped() throws {
    let interval = DateInterval(
      start: referenceDate.addingTimeInterval(-1_800),
      end: referenceDate.addingTimeInterval(1_800))
    let meeting = snapshot(
      id: "event-1",
      title: " Product review ",
      start: referenceDate.addingTimeInterval(-300),
      end: referenceDate.addingTimeInterval(900),
      participants: [DesktopMeetingParticipant(name: "Alex Kim", email: "alex@example.com")],
      candidates: [
        "Room 4",
        "Agenda text that stays local https://meet.google.com/abc-defg-hij more text",
      ])
    let duplicate = snapshot(
      id: "event-1",
      title: "Duplicate",
      start: referenceDate,
      end: referenceDate.addingTimeInterval(600))
    let allDay = snapshot(
      id: "event-2",
      title: "Private all-day entry",
      start: referenceDate.addingTimeInterval(-600),
      end: referenceDate.addingTimeInterval(600),
      isAllDay: true)
    let canceled = snapshot(
      id: "event-canceled",
      title: "Canceled meeting",
      start: referenceDate.addingTimeInterval(-600),
      end: referenceDate.addingTimeInterval(600),
      isCanceled: true)
    let outside = snapshot(
      id: "event-3",
      title: "Old event",
      start: referenceDate.addingTimeInterval(-7_200),
      end: referenceDate.addingTimeInterval(-3_600))

    let payloads = SystemCalendarMeetingContextService.payloads(
      from: [outside, allDay, canceled, duplicate, meeting],
      within: interval,
      maximumCount: 20)

    let payload = try XCTUnwrap(payloads.first)
    XCTAssertEqual(payloads.count, 1)
    XCTAssertEqual(payload.calendarEventID, "event-1")
    XCTAssertEqual(payload.title, "Product review")
    XCTAssertEqual(payload.participants, [DesktopMeetingParticipant(name: "Alex Kim", email: "alex@example.com")])
    XCTAssertEqual(payload.platform, "Google Meet")
    XCTAssertEqual(payload.meetingLink, "https://meet.google.com/abc-defg-hij")

    let body = try payload.wireBody
    XCTAssertEqual(body["calendar_source"] as? String, "system_calendar")
    XCTAssertNotNil(body["start_time"] as? String)
    XCTAssertNotNil(body["end_time"] as? String)
    XCTAssertNil(body["notes"])
    XCTAssertNil(body["location"])
  }

  func testConferenceParserAcceptsOnlyRecognizedHTTPSJoinLinks() {
    XCTAssertNil(
      SystemCalendarMeetingContextService.conferencingIdentity(
        in: ["http://meet.google.com/abc-defg-hij", "https://zoom.us/pricing", "https://example.com/j/123"]))

    let zoom = SystemCalendarMeetingContextService.conferencingIdentity(
      in: ["Join (https://acme.zoom.us/j/123456789?pwd=secret)."])
    XCTAssertEqual(zoom?.platform, "Zoom")
    XCTAssertEqual(zoom?.url.absoluteString, "https://acme.zoom.us/j/123456789?pwd=secret")

    let teams = SystemCalendarMeetingContextService.conferencingIdentity(
      in: ["https://teams.microsoft.com/l/meetup-join/19%3ameeting"])
    XCTAssertEqual(teams?.platform, "Teams")
  }

  func testDeniedPermissionDoesNotPromptAgainOrReadEvents() async {
    let provider = SystemCalendarProviderStub(state: .notDetermined, grantsAccess: false)
    let uploader = SystemCalendarUploaderStub()
    let service = SystemCalendarMeetingContextService(provider: provider, uploader: uploader)

    await service.prepareAroundNow(now: referenceDate)
    await service.prepareAroundNow(now: referenceDate)
    await service.syncAuthorizedEvents(
      overlapping: DateInterval(start: referenceDate, end: referenceDate.addingTimeInterval(60)))

    let counts = await provider.counts()
    let uploaded = await uploader.uploadedPayloads()
    XCTAssertEqual(counts.requests, 1)
    XCTAssertEqual(counts.reads, 0)
    XCTAssertTrue(uploaded.isEmpty)
  }

  func testAuthorizedSyncUploadsEachEventIdentifierOnlyOnce() async {
    let event = snapshot(
      id: "event-1",
      title: "Weekly sync",
      start: referenceDate.addingTimeInterval(-300),
      end: referenceDate.addingTimeInterval(300))
    let provider = SystemCalendarProviderStub(state: .allowed, snapshots: [event, event])
    let uploader = SystemCalendarUploaderStub()
    let service = SystemCalendarMeetingContextService(provider: provider, uploader: uploader)
    let interval = DateInterval(
      start: referenceDate.addingTimeInterval(-600),
      end: referenceDate.addingTimeInterval(600))

    await service.syncAuthorizedEvents(overlapping: interval)
    await service.syncAuthorizedEvents(overlapping: interval)

    let uploaded = await uploader.uploadedPayloads()
    let counts = await provider.counts()
    XCTAssertEqual(uploaded.map(\.calendarEventID), ["event-1"])
    XCTAssertEqual(counts.reads, 2)
  }

  private func snapshot(
    id: String,
    title: String,
    start: Date,
    end: Date,
    isAllDay: Bool = false,
    isCanceled: Bool = false,
    participants: [DesktopMeetingParticipant] = [],
    candidates: [String] = []
  ) -> SystemCalendarEventSnapshot {
    SystemCalendarEventSnapshot(
      calendarEventID: id,
      title: title,
      startTime: start,
      endTime: end,
      isAllDay: isAllDay,
      isCanceled: isCanceled,
      participants: participants,
      urlCandidates: candidates)
  }
}
