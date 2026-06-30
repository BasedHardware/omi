import XCTest
@testable import Omi_Computer

final class WhatsAppIncomingMessageTests: XCTestCase {
  func testInitFromDirectEventFields() {
    let event: [String: Any] = [
      "id": "msg-1",
      "chatJid": "15551234567@s.whatsapp.net",
      "senderJid": "15559876543@s.whatsapp.net",
      "senderName": "Alice",
      "text": "Hello there",
      "fromMe": false,
      "timestamp": 1_700_000_000.0,
    ]

    let message = WAIncomingMessage(event: event)
    XCTAssertNotNil(message)
    XCTAssertEqual(message?.id, "msg-1")
    XCTAssertEqual(message?.chatJid, "15551234567@s.whatsapp.net")
    XCTAssertEqual(message?.senderJid, "15559876543@s.whatsapp.net")
    XCTAssertEqual(message?.senderName, "Alice")
    XCTAssertEqual(message?.text, "Hello there")
    XCTAssertFalse(message?.fromMe ?? true)
    XCTAssertEqual(message?.timestamp, Date(timeIntervalSince1970: 1_700_000_000))
  }

  func testInitFromNestedDataMessageEnvelope() {
    let event: [String: Any] = [
      "data": [
        "message": [
          "ChatJID": "120363123456789012@g.us",
          "SenderJID": "15551112222@s.whatsapp.net",
          "PushName": "Bob",
          "body": "Group hello",
          "from_me": "false",
        ]
      ]
    ]

    let message = WAIncomingMessage(event: event)
    XCTAssertNotNil(message)
    XCTAssertEqual(message?.chatJid, "120363123456789012@g.us")
    XCTAssertEqual(message?.senderJid, "15551112222@s.whatsapp.net")
    XCTAssertEqual(message?.senderName, "Bob")
    XCTAssertEqual(message?.text, "Group hello")
    XCTAssertTrue(message?.isGroup ?? false)
  }

  func testInitParsesJidUserServerObjects() {
    let event: [String: Any] = [
      "message": [
        "chat": [
          "user": "15554443333",
          "server": "s.whatsapp.net",
        ],
        "sender": [
          "User": "15556667777",
          "Server": "s.whatsapp.net",
        ],
        "text": "Nested JIDs",
      ]
    ]

    let message = WAIncomingMessage(event: event)
    XCTAssertNotNil(message)
    XCTAssertEqual(message?.chatJid, "15554443333@s.whatsapp.net")
    XCTAssertEqual(message?.senderJid, "15556667777@s.whatsapp.net")
  }

  func testInitCoercesBoolAndDateVariants() {
    let event: [String: Any] = [
      "chatJid": "15551234567@s.whatsapp.net",
      "senderJid": "15559876543@s.whatsapp.net",
      "text": "Coerced values",
      "fromMe": "1",
      "is_group": "yes",
      "timestamp": "1700000000000",
    ]

    let message = WAIncomingMessage(event: event)
    XCTAssertNotNil(message)
    XCTAssertTrue(message?.fromMe ?? false)
    XCTAssertTrue(message?.isGroup ?? false)
    XCTAssertEqual(message?.timestamp, Date(timeIntervalSince1970: 1_700_000_000))
  }

  func testInitParsesISO8601Timestamp() {
    let event: [String: Any] = [
      "chatJid": "15551234567@s.whatsapp.net",
      "senderJid": "15559876543@s.whatsapp.net",
      "text": "ISO date",
      "createdAt": "2024-01-15T12:00:00Z",
    ]

    let message = WAIncomingMessage(event: event)
    XCTAssertNotNil(message)
    XCTAssertNotNil(message?.timestamp)
  }

  func testInitReturnsNilForMissingRequiredFields() {
    XCTAssertNil(WAIncomingMessage(event: ["chatJid": "15551234567@s.whatsapp.net"]))
    XCTAssertNil(WAIncomingMessage(event: ["text": "only text"]))
  }

  func testIsStatusOrBroadcast() {
    let status = WAIncomingMessage(
      id: "1",
      chatJid: "status@broadcast",
      senderJid: "15551234567@s.whatsapp.net",
      senderName: nil,
      text: "Update",
      fromMe: false,
      isGroup: false,
      timestamp: nil
    )
    XCTAssertTrue(status?.isStatusOrBroadcast ?? false)

    let normal = WAIncomingMessage(
      id: "2",
      chatJid: "15551234567@s.whatsapp.net",
      senderJid: "15559876543@s.whatsapp.net",
      senderName: nil,
      text: "Hi",
      fromMe: false,
      isGroup: false,
      timestamp: nil
    )
    XCTAssertFalse(normal?.isStatusOrBroadcast ?? true)
  }

  func testIsGroupInferredFromChatJid() {
    let message = WAIncomingMessage(
      id: "3",
      chatJid: "120363123456789012@g.us",
      senderJid: "15551112222@s.whatsapp.net",
      senderName: nil,
      text: "Group msg",
      fromMe: false,
      isGroup: false,
      timestamp: nil
    )
    XCTAssertTrue(message?.isGroup ?? false)
  }

  func testDisplaySenderUsesNameWhenPresent() {
    let message = WAIncomingMessage(
      id: "4",
      chatJid: "15551234567@s.whatsapp.net",
      senderJid: "15559876543@s.whatsapp.net",
      senderName: "Carol",
      text: "Hey",
      fromMe: false,
      isGroup: false,
      timestamp: nil
    )
    XCTAssertEqual(message?.displaySender, "Carol")

    let unnamed = WAIncomingMessage(
      id: "5",
      chatJid: "15551234567@s.whatsapp.net",
      senderJid: "15559876543@s.whatsapp.net",
      senderName: nil,
      text: "Hey",
      fromMe: false,
      isGroup: false,
      timestamp: nil
    )
    XCTAssertEqual(unnamed?.displaySender, "15559876543@s.whatsapp.net")
  }
}
