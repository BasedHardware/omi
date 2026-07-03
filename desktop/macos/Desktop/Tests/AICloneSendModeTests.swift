import XCTest

@testable import Omi_Computer

/// Logic tests for the AI Clone send-mode system. These cover the pure, side-effect-free
/// parts — platform routing, the incoming-action decision (the autonomous kill switch), and
/// mode labels — so the safety-critical rule ("Autonomous NEVER sends while paused") is
/// verified without touching the network, Messages.app, or any real contact.
final class AICloneSendModeTests: XCTestCase {

  // MARK: - Platform routing

  func testPlatformRoutingByContactIdPrefix() {
    XCTAssertEqual(AIClonePlatform.of(contactId: "telegram:12345"), .telegram)
    XCTAssertEqual(AIClonePlatform.of(contactId: "whatsapp:chat.txt"), .whatsapp)
    // iMessage handles are stored unprefixed (phone or email).
    XCTAssertEqual(AIClonePlatform.of(contactId: "+14155550123"), .imessage)
    XCTAssertEqual(AIClonePlatform.of(contactId: "friend@example.com"), .imessage)
  }

  func testOnlyWhatsAppCannotSend() {
    XCTAssertTrue(AIClonePlatform.imessage.canSend)
    XCTAssertTrue(AIClonePlatform.telegram.canSend)
    XCTAssertFalse(AIClonePlatform.whatsapp.canSend)
  }

  // MARK: - Incoming-action decision (the kill switch)

  func testManualNeverActsOnIncoming() {
    XCTAssertEqual(AICloneSendModeService.action(for: .manual, isPaused: true), .ignore)
    XCTAssertEqual(AICloneSendModeService.action(for: .manual, isPaused: false), .ignore)
  }

  func testDraftReviewAlwaysDraftsNeverSends() {
    XCTAssertEqual(AICloneSendModeService.action(for: .draftReview, isPaused: true), .draft)
    XCTAssertEqual(AICloneSendModeService.action(for: .draftReview, isPaused: false), .draft)
  }

  /// The core safety guarantee: an Autonomous contact must NOT auto-send while the global
  /// switch is paused — it degrades to a draft instead.
  func testAutonomousPausedDegradesToDraftAndNeverSends() {
    XCTAssertEqual(AICloneSendModeService.action(for: .autonomous, isPaused: true), .draft)
    XCTAssertNotEqual(AICloneSendModeService.action(for: .autonomous, isPaused: true), .autoSend)
  }

  func testAutonomousActiveAutoSends() {
    XCTAssertEqual(AICloneSendModeService.action(for: .autonomous, isPaused: false), .autoSend)
  }

  /// Exhaustive matrix — no (mode, paused) combination other than (autonomous, active)
  /// may ever resolve to `.autoSend`.
  func testAutoSendOnlyWhenAutonomousAndActive() {
    for mode in SendMode.allCases {
      for paused in [true, false] {
        let action = AICloneSendModeService.action(for: mode, isPaused: paused)
        if action == .autoSend {
          XCTAssertEqual(mode, .autonomous)
          XCTAssertFalse(paused)
        }
      }
    }
  }

  // MARK: - Codable + labels

  func testSendModeRoundTrips() throws {
    for mode in SendMode.allCases {
      let data = try JSONEncoder().encode(mode)
      let decoded = try JSONDecoder().decode(SendMode.self, from: data)
      XCTAssertEqual(decoded, mode)
    }
  }

  func testSendModeDefaultRawValues() {
    XCTAssertEqual(SendMode.manual.rawValue, "manual")
    XCTAssertEqual(SendMode.draftReview.rawValue, "draftReview")
    XCTAssertEqual(SendMode.autonomous.rawValue, "autonomous")
  }

  func testSentLogEntryRoundTrips() throws {
    let entry = AICloneSentLogEntry(
      contactId: "telegram:42", contactDisplayName: "Saved Messages",
      text: "hello", mode: .manual, timestamp: Date(timeIntervalSince1970: 1_700_000_000))
    let data = try JSONEncoder().encode(entry)
    let decoded = try JSONDecoder().decode(AICloneSentLogEntry.self, from: data)
    XCTAssertEqual(decoded.contactId, entry.contactId)
    XCTAssertEqual(decoded.text, "hello")
    XCTAssertEqual(decoded.mode, .manual)
  }
}
