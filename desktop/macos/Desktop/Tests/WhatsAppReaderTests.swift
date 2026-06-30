import XCTest

@testable import Omi_Computer

@MainActor
final class WhatsAppReaderTests: XCTestCase {
  func testUnwrapJSONEnvelopeExtractsDataKey() {
    let payload: [String: Any] = [
      "data": [
        ["jid": "15551234567@s.whatsapp.net", "title": "Alice", "text": "Hi"],
      ],
    ]
    let unwrapped = WhatsAppReader.testingUnwrapJSONEnvelope(payload) as? [[String: Any]]
    XCTAssertEqual(unwrapped?.count, 1)
    XCTAssertEqual(unwrapped?.first?["jid"] as? String, "15551234567@s.whatsapp.net")
  }

  func testUnwrapJSONEnvelopeReturnsRootWhenNoDataKey() {
    let payload: [String: Any] = ["jid": "15551234567@s.whatsapp.net"]
    let unwrapped = WhatsAppReader.testingUnwrapJSONEnvelope(payload) as? [String: Any]
    XCTAssertEqual(unwrapped?["jid"] as? String, "15551234567@s.whatsapp.net")
  }

  func testParseChatsFromDataEnvelope() async {
    let json: [String: Any] = [
      "data": [
        [
          "jid": "15551234567@s.whatsapp.net",
          "title": "Alice",
          "lastMessageText": "See you soon",
          "timestamp": 1_710_000_000,
        ],
      ],
    ]
    let chats = await WhatsAppReader.testingParseChats(from: json)
    XCTAssertEqual(chats.count, 1)
    XCTAssertEqual(chats.first?.id, "15551234567@s.whatsapp.net")
    XCTAssertEqual(chats.first?.title, "Alice")
    XCTAssertEqual(chats.first?.lastMessagePreview, "See you soon")
    XCTAssertFalse(chats.first?.isGroup ?? true)
  }

  func testParseChatsFromNestedChatsCollection() async {
    let json: [String: Any] = [
      "chats": [
        [
          "jid": "120363012345678901@g.us",
          "title": "Team Chat",
          "isGroup": true,
          "last_message": "Updated docs",
          "last_message_ts": 1_710_000_100,
        ],
      ],
    ]
    let chats = await WhatsAppReader.testingParseChats(from: json)
    XCTAssertEqual(chats.count, 1)
    XCTAssertEqual(chats.first?.id, "120363012345678901@g.us")
    XCTAssertTrue(chats.first?.isGroup ?? false)
    XCTAssertEqual(chats.first?.subtitle, "Group")
  }

  func testParseMessagesFromDataEnvelope() async {
    let json: [String: Any] = [
      "data": [
        [
          "id": "abc123",
          "text": "Hello",
          "senderJid": "15551234567@s.whatsapp.net",
          "timestamp": 1_710_000_000,
          "fromMe": false,
        ],
      ],
    ]
    let messages = await WhatsAppReader.testingParseMessages(from: json)
    XCTAssertEqual(messages.count, 1)
    XCTAssertEqual(messages.first?.id, "abc123")
    XCTAssertEqual(messages.first?.text, "Hello")
    XCTAssertFalse(messages.first?.isFromMe ?? true)
  }

  func testParseMessagesSkipsPlaceholderWithoutMediaMetadata() async {
    let json: [String: Any] = [
      "messages": [
        [
          "DisplayText": "(message)",
          "text": "",
        ],
      ],
    ]
    let messages = await WhatsAppReader.testingParseMessages(from: json)
    XCTAssertTrue(messages.isEmpty)
  }

  func testIsPlaceholderMessageRequiresEmptyRawTextAndMessageLabel() {
    let object: [String: Any] = ["MediaType": ""]
    XCTAssertTrue(
      WhatsAppReader.testingIsPlaceholderMessage(rawText: "", displayText: "(message)", object: object)
    )
    XCTAssertFalse(
      WhatsAppReader.testingIsPlaceholderMessage(rawText: "photo", displayText: "(message)", object: object)
    )
    XCTAssertFalse(
      WhatsAppReader.testingIsPlaceholderMessage(rawText: "", displayText: "Hello", object: object)
    )
  }

  func testStableFallbackMessageIDIsDeterministic() {
    let timestamp = Date(timeIntervalSince1970: 1_710_000_000)
    let first = WhatsAppReader.testingStableFallbackMessageID(
      senderJid: "15551234567@s.whatsapp.net",
      timestamp: timestamp,
      text: "Hello"
    )
    let second = WhatsAppReader.testingStableFallbackMessageID(
      senderJid: "15551234567@s.whatsapp.net",
      timestamp: timestamp,
      text: "Hello"
    )
    XCTAssertEqual(first, second)
    XCTAssertEqual(first.count, 64)
  }

  func testDisplayTitleFallsBackToPhoneNumberWhenTitleIsJidLike() async {
    let jid = "15558887766@s.whatsapp.net"
    let title = await WhatsAppReader.testingDisplayTitle(
      for: jid,
      rawTitle: jid,
      isGroup: false
    )
    XCTAssertEqual(title, "+15558887766")
  }

  func testParseMessagesUsesStableFallbackIDWhenMissingMessageID() async {
    let timestamp = Date(timeIntervalSince1970: 1_710_000_000)
    let json: [String: Any] = [
      "messages": [
        [
          "text": "No explicit id",
          "senderJid": "15551234567@s.whatsapp.net",
          "timestamp": timestamp.timeIntervalSince1970,
        ],
      ],
    ]
    let messages = await WhatsAppReader.testingParseMessages(from: json)
    XCTAssertEqual(messages.count, 1)
    let expectedID = WhatsAppReader.testingStableFallbackMessageID(
      senderJid: "15551234567@s.whatsapp.net",
      timestamp: timestamp,
      text: "No explicit id"
    )
    XCTAssertEqual(messages.first?.id, expectedID)
  }
}
