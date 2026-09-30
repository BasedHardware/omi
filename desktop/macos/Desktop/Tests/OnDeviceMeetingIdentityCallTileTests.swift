import Foundation
import XCTest

@testable import Omi_Computer

/// The call-tile name rule, kept in parity with the backend's `call_tile_names`
/// (`backend/utils/conversations/meeting_context.py`). Both sides run the same shared vectors.
final class OnDeviceMeetingIdentityCallTileTests: XCTestCase {
  private struct VectorFile: Decodable {
    let vectors: [Vector]
  }

  private struct Vector: Decodable {
    struct Row: Decodable {
      let appName: String
      let windowTitle: String?
      let ocrText: String?
    }

    let id: String
    let rows: [Row]
    let ownerNames: [String]
    let ownerEmails: [String]
    let expectedTileNames: [String]
    let expectedParticipantNames: [String]
    let expectedAgentNames: [String]
    let mustExclude: [String]

    enum CodingKeys: String, CodingKey {
      case id, rows
      case ownerNames = "owner_names"
      case ownerEmails = "owner_emails"
      case expectedTileNames = "expected_tile_names"
      case expectedParticipantNames = "expected_participant_names"
      case expectedAgentNames = "expected_agent_names"
      case mustExclude = "must_exclude"
    }
  }

  /// The one fixture both extractors are pinned to. It lives with the backend tests; this resolves
  /// it from the monorepo checkout this test file belongs to.
  private static var sharedVectorsURL: URL {
    if let override = ProcessInfo.processInfo.environment["OMI_CALL_TILE_VECTORS_PATH"], !override.isEmpty {
      return URL(fileURLWithPath: override)
    }
    return URL(fileURLWithPath: #filePath)
      .deletingLastPathComponent()  // Tests
      .deletingLastPathComponent()  // Desktop
      .deletingLastPathComponent()  // macos
      .deletingLastPathComponent()  // desktop
      .deletingLastPathComponent()  // repository root
      .appendingPathComponent("backend/tests/fixtures/meeting_identity/call_tile_vectors.json")
  }

  func testSharedCallTileVectorsMatchTheBackendRule() throws {
    guard FileManager.default.fileExists(atPath: Self.sharedVectorsURL.path) else {
      throw XCTSkip("shared call-tile vectors are not in this checkout yet (backend lane lands them)")
    }
    let file = try JSONDecoder().decode(VectorFile.self, from: Data(contentsOf: Self.sharedVectorsURL))
    XCTAssertFalse(file.vectors.isEmpty)
    for vector in file.vectors {
      let snapshots = vector.rows.enumerated().map { index, row in
        MeetingScreenActivitySnapshot(
          timestamp: Date(timeIntervalSince1970: 1_790_769_600 + Double(index) * 60),
          appName: row.appName,
          windowTitle: row.windowTitle,
          ocrText: row.ocrText)
      }
      XCTAssertEqual(
        OnDeviceMeetingIdentityExtractor.callTileNames(
          in: snapshots, ownerNames: vector.ownerNames, ownerEmails: vector.ownerEmails),
        vector.expectedTileNames, vector.id)
      XCTAssertEqual(
        OnDeviceMeetingIdentityExtractor.callTileAgentNames(
          in: snapshots, ownerNames: vector.ownerNames, ownerEmails: vector.ownerEmails),
        vector.expectedAgentNames, vector.id)
      // Agent tiles join the upload as agents (the roster classifies them by name), never as people.
      let everyone = participantNames(snapshots, ownerNames: vector.ownerNames, ownerEmails: vector.ownerEmails)
      let names = everyone.filter { !OnDeviceMeetingIdentityExtractor.looksLikeAIAgentName($0) }
      XCTAssertEqual(names, vector.expectedParticipantNames, vector.id)
      XCTAssertEqual(
        everyone.filter(OnDeviceMeetingIdentityExtractor.looksLikeAIAgentName), vector.expectedAgentNames, vector.id)
      XCTAssertTrue(Set(names).isDisjoint(with: vector.mustExclude), vector.id)
    }
  }

  // The incident, owner, and agent cases also run inline so this rule is covered in any checkout.

  func testBareRepeatedTileNameBecomesAParticipant() {
    // Conversation 449565eb: a 1:1 Meet whose only identity is the other person's tile label.
    let tab = "meet.google.com/abc-defg-hij\nOmi Monitor\nDashboards - Grafana\nSpud pay"
    let rows =
      (0..<5).map { meetRow("\(tab)\nJordan Rivera\nYou\n10:3\($0) AM | abc-defg-hij", minute: $0) }
      + [meetRow("\(tab)\nCoinflow Portal\n10:38 AM | abc-defg-hij", minute: 8)]

    XCTAssertEqual(OnDeviceMeetingIdentityExtractor.callTileNames(in: rows), ["Jordan Rivera"])
    XCTAssertEqual(participantNames(rows), ["Jordan Rivera"])
  }

  func testOwnerTileAndSuppliedOwnerIdentityAreExcluded() {
    let marked = (0..<4).map { meetRow("David Zhang (You)\nJordan Rivera\nDavid Zhang", minute: $0) }
    XCTAssertEqual(OnDeviceMeetingIdentityExtractor.callTileNames(in: marked), ["Jordan Rivera"])

    let bare = (0..<4).map { meetRow("David Zhang\nPriya Natarajan", minute: $0) }
    XCTAssertEqual(
      OnDeviceMeetingIdentityExtractor.callTileNames(in: bare, ownerNames: ["David Zhang"]), ["Priya Natarajan"])
    XCTAssertEqual(
      OnDeviceMeetingIdentityExtractor.callTileNames(in: bare, ownerEmails: ["david.zhang@example.com"]),
      ["Priya Natarajan"])
  }

  func testAIAgentTilesNeverBecomeHumanParticipants() {
    let rows = (0..<4).map {
      meetRow("Ash Kalb\nBoardy Boardman\nFireflies Notetaker\nOtter Bot\nOmi Agent\nMeetbot Recorder", minute: $0)
    }
    XCTAssertEqual(OnDeviceMeetingIdentityExtractor.callTileNames(in: rows), ["Ash Kalb"])
  }

  func testAgentMarkersAreWholeTokensSoHumanSurnamesSurvive() {
    let rows = (0..<4).map {
      meetRow("James Talbot\nAlice Abbot\nTomorrow Inc - NoteTaker\nTomorrow Inc NoteTaker", minute: $0)
    }
    XCTAssertEqual(OnDeviceMeetingIdentityExtractor.callTileNames(in: rows), ["James Talbot", "Alice Abbot"])
    XCTAssertFalse(OnDeviceMeetingIdentityExtractor.isAIAgentTileName("James Talbot"))
    XCTAssertTrue(OnDeviceMeetingIdentityExtractor.isAIAgentTileName("Tomorrow Inc NoteTaker"))
    XCTAssertTrue(OnDeviceMeetingIdentityExtractor.isAIAgentTileName("Chatbot Helper"))
  }

  /// Expected values are the backend's own `call_tile_names` output for these rows: keys fold like
  /// Python's `str.casefold()`, so "Groß"/"Gross" and a final/medial sigma are the same person.
  func testOwnerAndTileKeysUseFullUnicodeCaseFolding() {
    let gross = (0..<4).map { meetRow("Hans Groß\nPriya Natarajan", minute: $0) }
    XCTAssertEqual(
      OnDeviceMeetingIdentityExtractor.callTileNames(in: gross, ownerNames: ["Hans Gross"]), ["Priya Natarajan"])

    let sigma = (0..<4).map { meetRow("Νίκος Παππάς\nPriya Natarajan", minute: $0) }
    XCTAssertEqual(
      OnDeviceMeetingIdentityExtractor.callTileNames(in: sigma, ownerNames: ["Νίκος Παππάσ"]), ["Priya Natarajan"])

    let marked = (0..<4).map { meetRow("Hans Groß (You)\nHans Gross\nPriya Natarajan", minute: $0) }
    XCTAssertEqual(OnDeviceMeetingIdentityExtractor.callTileNames(in: marked), ["Priya Natarajan"])
  }

  func testTooFewCallRowsOrTooSmallAShareYieldsNoTile() {
    XCTAssertEqual(
      OnDeviceMeetingIdentityExtractor.callTileNames(in: (0..<2).map { meetRow("Jordan Rivera", minute: $0) }), [])

    let rows = (0..<20).map { meetRow($0 < 4 ? "Jordan Rivera" : "10:\($0) AM", minute: $0) }
    XCTAssertEqual(OnDeviceMeetingIdentityExtractor.callTileNames(in: rows), [], "4 of 20 rows is below 25%")
  }

  private func meetRow(_ ocr: String, minute: Int) -> MeetingScreenActivitySnapshot {
    MeetingScreenActivitySnapshot(
      timestamp: Date(timeIntervalSince1970: 1_790_769_600 + Double(minute) * 60),
      appName: "Google Chrome",
      windowTitle: "Meet - abc-defg-hij",
      ocrText: ocr)
  }

  private func participantNames(
    _ snapshots: [MeetingScreenActivitySnapshot],
    ownerNames: [String] = [],
    ownerEmails: [String] = []
  ) -> [String] {
    let interval = DateInterval(
      start: snapshots.first?.timestamp ?? Date(timeIntervalSince1970: 0),
      end: (snapshots.last?.timestamp ?? Date(timeIntervalSince1970: 0)).addingTimeInterval(60))
    return OnDeviceMeetingIdentityExtractor.payload(
      from: snapshots, overlapping: interval, ownerNames: ownerNames, ownerEmails: ownerEmails
    )?.participants.compactMap(\.name) ?? []
  }
}
