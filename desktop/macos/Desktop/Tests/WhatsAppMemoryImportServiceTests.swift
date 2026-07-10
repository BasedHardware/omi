import XCTest

@testable import Omi_Computer

@MainActor
final class WhatsAppMemoryImportServiceTests: XCTestCase {
  private let service = WhatsAppMemoryImportService.shared

  func testParseMessagesFromDataEnvelope() {
    let json = """
    {
      "data": [
        {
          "chatJid": "15551234567@s.whatsapp.net",
          "senderJid": "15551234567@s.whatsapp.net",
          "text": "Synced hello",
          "id": "msg-42",
          "timestamp": 1710000000,
          "fromMe": false
        }
      ]
    }
    """
    let messages = service.parseMessages(from: json)
    XCTAssertEqual(messages.count, 1)
    XCTAssertEqual(messages.first?.id, "msg-42")
    XCTAssertEqual(messages.first?.chatJid, "15551234567@s.whatsapp.net")
    XCTAssertEqual(messages.first?.text, "Synced hello")
    XCTAssertFalse(messages.first?.fromMe ?? true)
    XCTAssertFalse(messages.first?.isGroup ?? true)
  }

  func testParseMessagesCollectsNestedMessages() {
    let json = """
    {
      "messages": [
        {
          "chatJid": "120363012345678901@g.us",
          "senderJid": "15559876543@s.whatsapp.net",
          "text": "Group note",
          "timestamp": 1710000100,
          "isGroup": true
        }
      ]
    }
    """
    let messages = service.parseMessages(from: json)
    XCTAssertEqual(messages.count, 1)
    XCTAssertTrue(messages.first?.isGroup ?? false)
    XCTAssertEqual(messages.first?.chatJid, "120363012345678901@g.us")
  }

  func testParseMessagesSkipsEmptyText() {
    let json = """
    {
      "messages": [
        {
          "chatJid": "15551234567@s.whatsapp.net",
          "senderJid": "15551234567@s.whatsapp.net",
          "text": "   "
        }
      ]
    }
    """
    XCTAssertTrue(service.parseMessages(from: json).isEmpty)
  }

  func testStableFallbackMessageIDIsDeterministic() {
    let timestamp = Date(timeIntervalSince1970: 1_710_000_000)
    let first = service.stableFallbackMessageID(
      chatJid: "15551234567@s.whatsapp.net",
      senderJid: "15559876543@s.whatsapp.net",
      timestamp: timestamp,
      text: "Fallback text",
      sourcePosition: "root.messages.0"
    )
    let second = service.stableFallbackMessageID(
      chatJid: "15551234567@s.whatsapp.net",
      senderJid: "15559876543@s.whatsapp.net",
      timestamp: timestamp,
      text: "Fallback text",
      sourcePosition: "root.messages.0"
    )
    XCTAssertEqual(first, second)
    XCTAssertEqual(first.count, 64)
  }

  func testStableFallbackMessageIDUsesSourcePositionWhenTimestampMissing() {
    let withTimestamp = service.stableFallbackMessageID(
      chatJid: "15551234567@s.whatsapp.net",
      senderJid: "15559876543@s.whatsapp.net",
      timestamp: Date(timeIntervalSince1970: 1_710_000_000),
      text: "Fallback text",
      sourcePosition: "root.messages.0"
    )
    let withoutTimestamp = service.stableFallbackMessageID(
      chatJid: "15551234567@s.whatsapp.net",
      senderJid: "15559876543@s.whatsapp.net",
      timestamp: nil,
      text: "Fallback text",
      sourcePosition: "root.messages.0"
    )
    XCTAssertNotEqual(withTimestamp, withoutTimestamp)
  }

  func testDedupeKeyIncludesChatSenderIDAndTimestamp() {
    let message = WhatsAppSyncedMessage(
      id: "msg-1",
      chatJid: "15551234567@s.whatsapp.net",
      senderJid: "15559876543@s.whatsapp.net",
      senderName: nil,
      text: "Hello",
      fromMe: false,
      timestamp: Date(timeIntervalSince1970: 1_710_000_000),
      isGroup: false
    )
    XCTAssertEqual(
      service.dedupeKey(for: message),
      "15551234567@s.whatsapp.net|15559876543@s.whatsapp.net|msg-1|1710000000"
    )
  }

  func testParseMessagesUsesStableFallbackIDWhenMissingMessageID() {
    let json = """
    {
      "messages": [
        {
          "chatJid": "15551234567@s.whatsapp.net",
          "senderJid": "15559876543@s.whatsapp.net",
          "text": "No explicit id",
          "timestamp": 1710000000
        }
      ]
    }
    """
    let messages = service.parseMessages(from: json)
    XCTAssertEqual(messages.count, 1)
    let expectedID = service.stableFallbackMessageID(
      chatJid: "15551234567@s.whatsapp.net",
      senderJid: "15559876543@s.whatsapp.net",
      timestamp: Date(timeIntervalSince1970: 1_710_000_000),
      text: "No explicit id",
      sourcePosition: "root.messages.0"
    )
    XCTAssertEqual(messages.first?.id, expectedID)
  }
}
