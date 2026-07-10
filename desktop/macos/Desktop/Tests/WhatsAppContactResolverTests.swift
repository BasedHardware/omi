import XCTest
@testable import Omi_Computer

@MainActor
final class WhatsAppContactResolverTests: XCTestCase {
  private func contact(
    jid: String,
    contactName: String? = nil,
    whatsappName: String? = nil,
    phoneNumber: String? = nil,
    canonicalJid: String? = nil
  ) -> WhatsAppContact {
    WhatsAppContact(
      jid: jid,
      contactName: contactName,
      whatsappName: whatsappName,
      phoneNumber: phoneNumber,
      canonicalJid: canonicalJid
    )
  }

  // MARK: - displayName

  func testDisplayNamePrefersContactThenWhatsAppThenPhoneThenJid() {
    let full = contact(
      jid: "15551234567@s.whatsapp.net",
      contactName: "Alice",
      whatsappName: "alice_wa",
      phoneNumber: "+15551234567"
    )
    XCTAssertEqual(full.displayName, "Alice")

    let noContact = contact(
      jid: "15551234567@s.whatsapp.net",
      whatsappName: "alice_wa",
      phoneNumber: "+15551234567"
    )
    XCTAssertEqual(noContact.displayName, "alice_wa")

    let phoneOnly = contact(jid: "15551234567@s.whatsapp.net", phoneNumber: "+15551234567")
    XCTAssertEqual(phoneOnly.displayName, "+15551234567")

    let jidOnly = contact(jid: "15551234567@s.whatsapp.net")
    XCTAssertEqual(jidOnly.displayName, "15551234567@s.whatsapp.net")
  }

  // MARK: - canonicalJid

  func testCanonicalJidFollowsAliasChain() {
    let resolver = WhatsAppContactResolver(testingContacts: [
      "111@lid": contact(jid: "111@lid", canonicalJid: "222@s.whatsapp.net"),
      "222@s.whatsapp.net": contact(jid: "222@s.whatsapp.net", contactName: "Bob"),
    ])
    XCTAssertEqual(resolver.canonicalJid(for: "111@lid"), "222@s.whatsapp.net")
    XCTAssertEqual(resolver.canonicalJid(for: "111@LID"), "222@s.whatsapp.net")
  }

  func testCanonicalJidReturnsStableCycleRepresentative() {
    let resolver = WhatsAppContactResolver(testingContacts: [
      "aaa@lid": contact(jid: "aaa@lid", canonicalJid: "bbb@s.whatsapp.net"),
      "bbb@s.whatsapp.net": contact(jid: "bbb@s.whatsapp.net", canonicalJid: "ccc@s.whatsapp.net"),
      "ccc@s.whatsapp.net": contact(jid: "ccc@s.whatsapp.net", canonicalJid: "aaa@lid"),
    ])
    XCTAssertEqual(resolver.canonicalJid(for: "aaa@lid"), "aaa@lid")
    XCTAssertEqual(resolver.canonicalJid(for: "bbb@s.whatsapp.net"), "aaa@lid")
  }

  func testStableCycleRepresentativePicksLexicographicMinimum() {
    let resolver = WhatsAppContactResolver(testingContacts: [:])
    XCTAssertEqual(
      resolver.testing_stableCycleRepresentative(["zzz@lid", "aaa@lid", "mmm@lid"]),
      "aaa@lid"
    )
  }

  func testRememberAliasSkipsCyclicAlias() {
    let resolver = WhatsAppContactResolver(testingContacts: [
      "111@lid": contact(jid: "111@lid", canonicalJid: "222@s.whatsapp.net"),
      "222@s.whatsapp.net": contact(jid: "222@s.whatsapp.net"),
    ])
    resolver.rememberAlias(jid: "222@s.whatsapp.net", canonicalJid: "111@lid")
    XCTAssertNil(resolver.contactsByJid["222@s.whatsapp.net"]?.canonicalJid)
  }

  // MARK: - phone helpers

  func testPhoneNumberFromJid() {
    let resolver = WhatsAppContactResolver(testingContacts: [:])
    XCTAssertEqual(resolver.testing_phoneNumber(from: "15551234567@s.whatsapp.net"), "+15551234567")
    XCTAssertNil(resolver.testing_phoneNumber(from: "111@lid"))
    XCTAssertNil(resolver.testing_phoneNumber(from: "123@s.whatsapp.net"))
  }

  func testPhoneDigits() {
    let resolver = WhatsAppContactResolver(testingContacts: [
      "15551234567@s.whatsapp.net": contact(
        jid: "15551234567@s.whatsapp.net",
        phoneNumber: "+1 (555) 123-4567"
      ),
    ])
    XCTAssertEqual(resolver.phoneDigits(for: "15551234567@s.whatsapp.net"), "15551234567")
    XCTAssertNil(resolver.phoneDigits(for: "111@lid"))
  }

  func testJidFromPhone() {
    let resolver = WhatsAppContactResolver(testingContacts: [:])
    XCTAssertEqual(resolver.testing_jidFromPhone("+1 (555) 123-4567"), "15551234567@s.whatsapp.net")
    XCTAssertNil(resolver.testing_jidFromPhone("12345"))
  }

  // MARK: - detailLabel

  func testDetailLabelForLinkedContactWithoutCache() {
    let resolver = WhatsAppContactResolver(testingContacts: [:])
    XCTAssertEqual(resolver.detailLabel(for: "111@lid"), "111@lid")
  }

  func testDetailLabelForLinkedContactWithCache() {
    let resolver = WhatsAppContactResolver(testingContacts: [
      "111@lid": contact(jid: "111@lid", contactName: "Alice"),
    ])
    XCTAssertEqual(resolver.detailLabel(for: "111@lid"), "WhatsApp linked contact")
  }

  func testDetailLabelForPhoneJid() {
    let resolver = WhatsAppContactResolver(testingContacts: [:])
    XCTAssertEqual(
      resolver.detailLabel(for: "15551234567@s.whatsapp.net"),
      "+15551234567 - 15551234567@s.whatsapp.net"
    )
  }

  // MARK: - displayName via resolver

  func testDisplayNameUsesCachedContactAndFallback() {
    let resolver = WhatsAppContactResolver(testingContacts: [
      "15551234567@s.whatsapp.net": contact(
        jid: "15551234567@s.whatsapp.net",
        contactName: "Carol"
      ),
    ])
    XCTAssertEqual(resolver.displayName(for: "15551234567@s.whatsapp.net"), "Carol")
    XCTAssertEqual(resolver.displayName(for: "19998887777@s.whatsapp.net", fallback: "Dave"), "Dave")
    XCTAssertEqual(resolver.displayName(for: "19998887777@s.whatsapp.net"), "+19998887777")
  }

  // MARK: - isJidLike

  func testIsJidLikeAcceptsKnownServers() {
    let resolver = WhatsAppContactResolver(testingContacts: [:])
    XCTAssertTrue(resolver.testing_isJidLike("15551234567@s.whatsapp.net"))
    XCTAssertTrue(resolver.testing_isJidLike("120363123456789012@g.us"))
    XCTAssertTrue(resolver.testing_isJidLike("111@lid"))
    XCTAssertTrue(resolver.testing_isJidLike("status@broadcast"))
  }

  func testIsJidLikeRejectsInvalidValues() {
    let resolver = WhatsAppContactResolver(testingContacts: [:])
    XCTAssertFalse(resolver.testing_isJidLike("not-a-jid"))
    XCTAssertFalse(resolver.testing_isJidLike("user@unknown.server"))
    XCTAssertFalse(resolver.testing_isJidLike("a@b@c"))
    XCTAssertFalse(resolver.testing_isJidLike("@s.whatsapp.net"))
  }

  // MARK: - collectContacts

  func testCollectContactsFromFlatObject() {
    let resolver = WhatsAppContactResolver(testingContacts: [:])
    let json: [String: Any] = [
      "jid": "15551234567@s.whatsapp.net",
      "contact_name": "Eve",
      "pushName": "Evie",
      "phone": "+15551234567",
    ]
    let contacts = resolver.testing_collectContacts(from: json)
    XCTAssertEqual(contacts.count, 1)
    XCTAssertEqual(contacts[0].jid, "15551234567@s.whatsapp.net")
    XCTAssertEqual(contacts[0].contactName, "Eve")
    XCTAssertEqual(contacts[0].whatsappName, "Evie")
    XCTAssertEqual(contacts[0].phoneNumber, "+15551234567")
  }

  func testCollectContactsFromNestedArraysAndUserServerJid() {
    let resolver = WhatsAppContactResolver(testingContacts: [:])
    let json: [String: Any] = [
      "chats": [
        [
          "chatJid": [
            "User": "120363123456789012",
            "Server": "g.us",
          ],
          "chatName": "Team Chat",
        ],
        [
          "id": "15559876543@s.whatsapp.net",
          "fullName": "Frank",
        ],
      ]
    ]
    let contacts = resolver.testing_collectContacts(from: json)
    XCTAssertEqual(contacts.count, 2)
    XCTAssertTrue(contacts.contains { $0.jid == "120363123456789012@g.us" && $0.whatsappName == "Team Chat" })
    XCTAssertTrue(contacts.contains { $0.jid == "15559876543@s.whatsapp.net" && $0.contactName == "Frank" })
  }

  func testContactsFromJSONString() {
    let resolver = WhatsAppContactResolver(testingContacts: [:])
    let json = """
    [{"jid":"15551112222@s.whatsapp.net","name":"Grace"}]
    """
    let contacts = resolver.testing_contacts(fromJSON: json)
    XCTAssertEqual(contacts.count, 1)
    XCTAssertEqual(contacts[0].contactName, "Grace")
  }

  // MARK: - resolveRecipient

  func testResolveRecipientEmptyInputThrows() async {
    let resolver = WhatsAppContactResolver(testingContacts: [:])
    do {
      _ = try await resolver.resolveRecipient("   ")
      XCTFail("Expected emptyInput")
    } catch WhatsAppContactResolutionError.emptyInput {
    } catch {
      XCTFail("Unexpected error: \(error)")
    }
  }

  func testResolveRecipientJidLikeInputReturnsCanonicalJid() async throws {
    let resolver = WhatsAppContactResolver(testingContacts: [
      "111@lid": contact(jid: "111@lid", canonicalJid: "15551234567@s.whatsapp.net"),
    ])
    let resolved = try await resolver.resolveRecipient("111@lid")
    XCTAssertEqual(resolved, "15551234567@s.whatsapp.net")
  }

  func testResolveRecipientPhoneInputReturnsJid() async throws {
    let resolver = WhatsAppContactResolver(testingContacts: [:])
    let resolved = try await resolver.resolveRecipient("+1 (555) 999-0000")
    XCTAssertEqual(resolved, "15559990000@s.whatsapp.net")
  }

  func testResolveRecipientSingleLocalMatch() async throws {
    let resolver = WhatsAppContactResolver(testingContacts: [
      "15551230001@s.whatsapp.net": contact(
        jid: "15551230001@s.whatsapp.net",
        contactName: "Helen"
      ),
    ])
    let resolved = try await resolver.resolveRecipient("helen")
    XCTAssertEqual(resolved, "15551230001@s.whatsapp.net")
  }

  func testResolveRecipientAmbiguousLocalMatchesThrow() async {
    let resolver = WhatsAppContactResolver(testingContacts: [
      "15551230001@s.whatsapp.net": contact(jid: "15551230001@s.whatsapp.net", contactName: "Sam Alpha"),
      "15551230002@s.whatsapp.net": contact(jid: "15551230002@s.whatsapp.net", contactName: "Sam Beta"),
    ])
    do {
      _ = try await resolver.resolveRecipient("sam")
      XCTFail("Expected ambiguous")
    } catch WhatsAppContactResolutionError.ambiguous(let input) {
      XCTAssertEqual(input, "sam")
    } catch {
      XCTFail("Unexpected error: \(error)")
    }
  }
}
