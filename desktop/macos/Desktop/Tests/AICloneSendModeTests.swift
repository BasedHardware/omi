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
    XCTAssertEqual(AIClonePlatform.of(contactId: "whatsapp:14155550123"), .whatsapp)
    // iMessage handles are stored unprefixed (phone or email).
    XCTAssertEqual(AIClonePlatform.of(contactId: "+14155550123"), .imessage)
    XCTAssertEqual(AIClonePlatform.of(contactId: "friend@example.com"), .imessage)
  }

  func testAllPlatformsCanSend() {
    // WhatsApp gained a real send backend (local Baileys sidecar); the other two were
    // already sendable. If a platform ever regresses to import-only, this must be a
    // deliberate change.
    XCTAssertTrue(AIClonePlatform.imessage.canSend)
    XCTAssertTrue(AIClonePlatform.telegram.canSend)
    XCTAssertTrue(AIClonePlatform.whatsapp.canSend)
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

  // MARK: - WhatsApp autonomous acknowledgment gate

  /// The WhatsApp-specific extra safety step: Autonomous on a WhatsApp contact needs the
  /// one-time unofficial-connection acknowledgment. Exhaustive (mode × platform × ack)
  /// matrix, mirroring the kill-switch matrix above.
  func testWhatsAppAutonomousGateMatrix() {
    let contactsByPlatform: [(id: String, isWhatsApp: Bool)] = [
      ("+14155550123", false),  // iMessage
      ("telegram:12345", false),
      ("whatsapp:14155550123", true),
      ("whatsapp:WhatsApp Chat with Mom.txt", true),
    ]
    for (contactId, isWhatsApp) in contactsByPlatform {
      for mode in SendMode.allCases {
        for acknowledged in [true, false] {
          let required = AICloneSendModeService.requiresWhatsAppAutonomousAcknowledgment(
            mode: mode, contactId: contactId, acknowledged: acknowledged)
          // The gate fires ONLY for (autonomous, whatsapp, not-yet-acknowledged).
          let expected = mode == .autonomous && isWhatsApp && !acknowledged
          XCTAssertEqual(
            required, expected,
            "gate mismatch for \(contactId) mode=\(mode) acknowledged=\(acknowledged)")
        }
      }
    }
  }

  func testWhatsAppGateNeverBlocksManualOrDraftReview() {
    for contactId in ["whatsapp:14155550123", "whatsapp:chat.txt"] {
      for acknowledged in [true, false] {
        XCTAssertFalse(
          AICloneSendModeService.requiresWhatsAppAutonomousAcknowledgment(
            mode: .manual, contactId: contactId, acknowledged: acknowledged))
        XCTAssertFalse(
          AICloneSendModeService.requiresWhatsAppAutonomousAcknowledgment(
            mode: .draftReview, contactId: contactId, acknowledged: acknowledged))
      }
    }
  }

  // MARK: - WhatsApp send-target resolution

  func testWhatsAppDirectTargetAcceptsPhonesAndJids() {
    XCTAssertEqual(AICloneSendModeService.whatsAppDirectTarget(rawId: "14155550123"), "14155550123")
    XCTAssertEqual(
      AICloneSendModeService.whatsAppDirectTarget(rawId: "+1 (415) 555-0123"), "14155550123")
    XCTAssertEqual(
      AICloneSendModeService.whatsAppDirectTarget(rawId: "14155550123@s.whatsapp.net"),
      "14155550123@s.whatsapp.net")
  }

  func testWhatsAppDirectTargetRejectsImportFilenamesAndJunk() {
    // Imported-export contact ids are filenames — never directly addressable.
    XCTAssertNil(AICloneSendModeService.whatsAppDirectTarget(rawId: "WhatsApp Chat with Mom.txt"))
    XCTAssertNil(AICloneSendModeService.whatsAppDirectTarget(rawId: "_chat.txt"))
    XCTAssertNil(AICloneSendModeService.whatsAppDirectTarget(rawId: ""))
    XCTAssertNil(AICloneSendModeService.whatsAppDirectTarget(rawId: "123"))  // too short
  }

  // MARK: - WhatsApp incoming-contact resolution

  private let activeWhatsAppContacts: [(id: String, displayName: String)] = [
    (id: "whatsapp:14155550123", displayName: "Alice"),
    (id: "whatsapp:WhatsApp Chat with Mom.txt", displayName: "Mom"),
    (id: "whatsapp:WhatsApp Chat with Bob.txt", displayName: "Bob"),
  ]

  func testIncomingResolvesDirectPhoneId() {
    XCTAssertEqual(
      AICloneSendModeService.resolveWhatsAppContactId(
        phone: "14155550123", senderName: "Someone Else",
        activeWhatsAppContacts: activeWhatsAppContacts, phoneMap: [:]),
      "whatsapp:14155550123")
  }

  func testIncomingResolvesViaLearnedPhoneMapping() {
    XCTAssertEqual(
      AICloneSendModeService.resolveWhatsAppContactId(
        phone: "4915550001", senderName: nil,
        activeWhatsAppContacts: activeWhatsAppContacts,
        phoneMap: ["whatsapp:WhatsApp Chat with Mom.txt": "4915550001"]),
      "whatsapp:WhatsApp Chat with Mom.txt")
  }

  func testIncomingResolvesViaUniqueNameMatchCaseInsensitive() {
    XCTAssertEqual(
      AICloneSendModeService.resolveWhatsAppContactId(
        phone: "4915550002", senderName: "  mom ",
        activeWhatsAppContacts: activeWhatsAppContacts, phoneMap: [:]),
      "whatsapp:WhatsApp Chat with Mom.txt")
  }

  func testIncomingRefusesAmbiguousNameMatch() {
    let ambiguous = activeWhatsAppContacts + [(id: "whatsapp:mom2.txt", displayName: "Mom")]
    XCTAssertNil(
      AICloneSendModeService.resolveWhatsAppContactId(
        phone: "4915550003", senderName: "Mom",
        activeWhatsAppContacts: ambiguous, phoneMap: [:]))
  }

  func testIncomingUnknownSenderResolvesToNothing() {
    XCTAssertNil(
      AICloneSendModeService.resolveWhatsAppContactId(
        phone: "4915550004", senderName: "Stranger",
        activeWhatsAppContacts: activeWhatsAppContacts, phoneMap: [:]))
    XCTAssertNil(
      AICloneSendModeService.resolveWhatsAppContactId(
        phone: "4915550005", senderName: nil,
        activeWhatsAppContacts: activeWhatsAppContacts, phoneMap: [:]))
    XCTAssertNil(
      AICloneSendModeService.resolveWhatsAppContactId(
        phone: "4915550006", senderName: "   ",
        activeWhatsAppContacts: activeWhatsAppContacts, phoneMap: [:]))
  }

  // MARK: - WhatsApp link-state mapping (sidecar JSON → Swift state)

  func testLinkStateMappingFromSidecarJson() {
    XCTAssertEqual(
      WhatsAppSendService.linkState(fromStatusJson: ["state": "linked", "phone": "14155550123"]),
      .linked(phone: "14155550123"))
    XCTAssertEqual(
      WhatsAppSendService.linkState(fromStatusJson: [
        "state": "waiting_qr", "qrDataUrl": "data:image/png;base64,AAA",
      ]),
      .waitingScan(qrDataUrl: "data:image/png;base64,AAA"))
    // waiting_qr without a QR yet degrades to connecting (poll again shortly).
    XCTAssertEqual(
      WhatsAppSendService.linkState(fromStatusJson: ["state": "waiting_qr"]), .connecting)
    XCTAssertEqual(WhatsAppSendService.linkState(fromStatusJson: ["state": "connecting"]), .connecting)
    XCTAssertEqual(WhatsAppSendService.linkState(fromStatusJson: ["state": "unlinked"]), .unlinked)
    XCTAssertEqual(WhatsAppSendService.linkState(fromStatusJson: ["state": "logged_out"]), .loggedOut)
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
