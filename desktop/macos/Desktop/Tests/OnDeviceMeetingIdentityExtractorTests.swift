import Foundation
import XCTest

@testable import Omi_Computer

final class OnDeviceMeetingIdentityExtractorTests: XCTestCase {
  private let start = Date(timeIntervalSince1970: 1_787_081_379)  // 2026-08-18 19:29:39Z
  private let end = Date(timeIntervalSince1970: 1_787_083_103)  // 2026-08-18 19:58:23Z

  private let preJoinOCR = """
    EQ
    →
    meet.google.com/amc-iajq-asx?authuser=david%40scalingforever.com
    Meet
    david@scalingforever.com
    Switch account
    Omi Monitor
    ANX
    Spud
    David Zhang
    Coinflow Portal
    Spud pay
    Om
    Manage access
    Blocked users
    Meet - amc-iaja-asx
    Ready to join?
    Ash Kalb and Boardy Boardman are in this call
    This call is open to anyone
    """

  private let inCallOCR = """
    Meet with...
    David Zhang + Ash Kalb - Al Conte:
    Ash Kalb 3:44PM
    Boardy Boardman
    Ash Kalb (Presenting, annotating)
    boardy@boardy.ai
    (boardy@boardy.ai)
    ash@fulcradynamics.com
    """

  private let junkNames: Set<String> = [
    "EQ", "Spud", "Coinflow Portal", "Manage access", "Blocked users", "Switch account", "Om",
  ]

  func testRealCapturedWindowProducesOnlyCorroboratedParticipants() throws {
    let payload = try XCTUnwrap(
      OnDeviceMeetingIdentityExtractor.payload(
        from: rows(preJoinOCR, inCallOCR),
        overlapping: DateInterval(start: start, end: end)))

    func email(for name: String) -> String? {
      payload.participants.first { $0.name == name }?.email
    }
    XCTAssertEqual(email(for: "Ash Kalb"), "ash@fulcradynamics.com")
    XCTAssertEqual(email(for: "Boardy Boardman"), "boardy@boardy.ai")
    XCTAssertEqual(email(for: "David Zhang"), "david@scalingforever.com")
    XCTAssertTrue(Set(payload.participants.compactMap(\.name)).isDisjoint(with: junkNames))
    XCTAssertEqual(payload.platform, "Google Meet")
    XCTAssertEqual(payload.calendarSource, "screen_activity")
  }

  func testWirePayloadContainsOnlyMinimalMeetingIdentity() throws {
    let payload = try XCTUnwrap(
      OnDeviceMeetingIdentityExtractor.payload(
        from: rows(preJoinOCR, inCallOCR),
        overlapping: DateInterval(start: start, end: end)))
    let body = try payload.wireBody

    XCTAssertEqual(
      Set(body.keys),
      [
        "calendar_event_id", "calendar_source", "title", "start_time", "end_time", "participants", "platform",
      ])
    XCTAssertEqual(body["calendar_source"] as? String, "screen_activity")
    XCTAssertNil(body["meeting_link"])
    XCTAssertNil(body["notes"])
    XCTAssertNil(body["ocrText"])
    XCTAssertNil(body["evidenceText"])
    XCTAssertNil(body["screenshot_id"])
    XCTAssertNil(body["appName"])
    XCTAssertNil(body["windowTitle"])

    let encoded = try JSONSerialization.data(withJSONObject: body)
    let wireText = try XCTUnwrap(String(data: encoded, encoding: .utf8))
    for forbidden in ["Coinflow Portal", "Blocked users", "Ash Kalb 3:44PM", "meet.google.com/"] {
      XCTAssertFalse(wireText.contains(forbidden), "raw captured text leaked onto the wire: \(forbidden)")
    }
  }

  func testNoParticipantsMeansNoTitleOnlyPayload() {
    XCTAssertNil(
      OnDeviceMeetingIdentityExtractor.payload(
        from: rows("Coinflow Portal\nManage access\nBlocked users"),
        overlapping: DateInterval(start: start, end: end)))
  }

  func testRosterPatternsEmailCorroborationAndDecorations() {
    let texts = [
      "Ash Kalb is in this call",
      "Meet with Boardy Boardman",
      "David Zhang has joined",
      "In call with Jordan Lee",
      "Ash Kalb 3:44PM\nAsh Kalb (Presenting, annotating)\nash@fulcradynamics.com",
      "Boardy Boardman\nboardy.boardman@boardy.ai",
    ]
    let participants = OnDeviceMeetingIdentityExtractor.participants(from: texts)
    let names = participants.compactMap(\.name)
    XCTAssertTrue(names.contains("Ash Kalb"))
    XCTAssertTrue(names.contains("Boardy Boardman"))
    XCTAssertTrue(names.contains("David Zhang"))
    XCTAssertTrue(names.contains("Jordan Lee"))
    XCTAssertEqual(names.filter { $0 == "Ash Kalb" }.count, 1)
  }

  func testBrowserJoinURLIsRecognizedWithoutNativeConferencingApp() throws {
    let snapshot = MeetingScreenActivitySnapshot(
      timestamp: start,
      appName: "Google Chrome",
      windowTitle: "Ordinary browser title",
      ocrText: "https://meet.google.com/amc-iajq-asx\nAsh Kalb is in this call")
    let payload = try XCTUnwrap(
      OnDeviceMeetingIdentityExtractor.payload(
        from: [snapshot], overlapping: DateInterval(start: start, end: end)))
    XCTAssertEqual(payload.platform, "Google Meet")
    XCTAssertEqual(payload.title, "Video meeting")
  }

  func testTelegramCallWindowTitleWithCallControlOCRYieldsParticipant() throws {
    let snapshot = MeetingScreenActivitySnapshot(
      timestamp: start,
      appName: "Telegram",
      windowTitle: "Alice Chen",
      ocrText: "Mute\nEnd Call\nVideo")
    let payload = try XCTUnwrap(
      OnDeviceMeetingIdentityExtractor.payload(
        from: [snapshot], overlapping: DateInterval(start: start, end: end)))
    XCTAssertEqual(payload.participants.compactMap(\.name), ["Alice Chen"])
    XCTAssertEqual(payload.platform, "Telegram")
    XCTAssertFalse(payload.participants.contains { $0.name == "Speaker 1" })
  }

  func testTelegramChatTitlesWithoutCallControlYieldNoParticipants() {
    let chats: [(String, String)] = [
      ("Saved Messages", "sticker"),
      ("Alice Chen", "yesterday"),
      ("Bob Martinez", "photo"),
      ("Design Review", "ok"),
      ("Nikita Petrov", "typing"),
    ]
    let snapshots = chats.enumerated().map { index, pair in
      MeetingScreenActivitySnapshot(
        timestamp: start.addingTimeInterval(TimeInterval(index)),
        appName: "Telegram",
        windowTitle: pair.0,
        ocrText: pair.1)
    }
    XCTAssertNil(
      OnDeviceMeetingIdentityExtractor.payload(
        from: snapshots, overlapping: DateInterval(start: start, end: end)))
  }

  func testChromeCalendarTileWithoutMeetRosterYieldsNoParticipants() {
    let snapshot = MeetingScreenActivitySnapshot(
      timestamp: start,
      appName: "Google Chrome",
      windowTitle: "Meet - amc-iajq-asx",
      ocrText: "Aryan Gupta and Nik\nBlocked users\nCoinflow Portal")
    XCTAssertNil(
      OnDeviceMeetingIdentityExtractor.payload(
        from: [snapshot], overlapping: DateInterval(start: start, end: end)))
  }

  func testTelegramCallControlDoesNotIngestUnrelatedChatTitles() throws {
    let call = MeetingScreenActivitySnapshot(
      timestamp: start,
      appName: "Telegram",
      windowTitle: "Alice Chen",
      ocrText: "Mute\nEnd Call")
    let chat = MeetingScreenActivitySnapshot(
      timestamp: start.addingTimeInterval(1),
      appName: "Telegram",
      windowTitle: "Bob Martinez",
      ocrText: "hey")
    let payload = try XCTUnwrap(
      OnDeviceMeetingIdentityExtractor.payload(
        from: [call, chat], overlapping: DateInterval(start: start, end: end)))
    XCTAssertEqual(payload.participants.compactMap(\.name), ["Alice Chen"])
  }

  private func rows(_ texts: String...) -> [MeetingScreenActivitySnapshot] {
    texts.enumerated().map { index, text in
      MeetingScreenActivitySnapshot(
        timestamp: start.addingTimeInterval(TimeInterval(index)),
        appName: "Google Chrome",
        windowTitle: "Meet - amc-iajq-asx",
        ocrText: text)
    }
  }
}
