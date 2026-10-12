import XCTest

@testable import Omi_Computer

final class MessagingHandleTests: XCTestCase {
  private func same(_ stored: String, _ requested: String, region: String?) -> Bool {
    MessagingHandle.isSame(stored, requested, region: region)
  }

  // MARK: - Different people never match

  func testDifferentInternationalNumbersNeverMatch() {
    XCTAssertFalse(same("+914155550123", "+14155550123", region: "US"), "+1 vs +91")
    XCTAssertFalse(same("+614155550123", "+14155550123", region: "US"), "+1 vs +61")
    XCTAssertFalse(same("+244207946000", "+44207946000", region: "GB"), "+44 vs +244")
    XCTAssertFalse(same("+914155550123", "+14155550123", region: "IN"))
    XCTAssertFalse(
      same("+14155550123", "+4155550123", region: "US"), "two international forms never go through the region")
  }

  func testShortNationalNumberDoesNotMatchAForeignNumberEndingTheSameWay() {
    XCTAssertFalse(same("+85291234567", "91234567", region: "US"))
    XCTAssertFalse(same("+6591234567", "91234567", region: "US"))
    XCTAssertFalse(same("+12391234567", "91234567", region: "US"))
  }

  func testNationalNumberDoesNotMatchAnotherCountrysNumber() {
    XCTAssertFalse(same("+14412345678", "0412345678", region: "AU"), "AU 04… vs Bermuda +1441…")
    XCTAssertFalse(same("+14412345678", "0412345678", region: "US"))
    XCTAssertFalse(same("+914155550123", "(415) 555-0123", region: "US"))
  }

  func testNationalAndInternationalNeedAKnownRegion() {
    XCTAssertFalse(same("+14155550123", "(415) 555-0123", region: nil))
    XCTAssertFalse(same("+14155550123", "(415) 555-0123", region: "001"), "the World region has no calling code")
    XCTAssertFalse(same("+14155550123", "(415) 555-0123", region: "ZZ"))
    XCTAssertFalse(same("+14155550123", "14155550123", region: nil), "without a region only same-form spellings match")
    XCTAssertTrue(same("+14155550123", "+1 415 555 0123", region: nil))
    XCTAssertTrue(same("+14155550123", "0014155550123", region: "001"))
  }

  func testTrunkPrefixesOtherThanZero() {
    XCTAssertTrue(same("+74951234567", "8 495 123-45-67", region: "RU"))
    XCTAssertTrue(same("+375291234567", "8 029 123 45 67", region: "BY"))
    XCTAssertTrue(same("+37061234567", "8 612 34567", region: "LT"))
    XCTAssertTrue(same("+37061234567", "0 612 34567", region: "LT"))
    XCTAssertTrue(same("+3612345678", "06 1 234 5678", region: "HU"))
    XCTAssertTrue(same("+14155550123", "1 (415) 555-0123", region: "US"))
    XCTAssertFalse(same("+74951234567", "8 495 123-45-67", region: "GB"), "8 is not a trunk prefix in the UK")
  }

  func testNorthAmericanInternationalPrefix() {
    XCTAssertTrue(same("+447700900123", "011 44 7700 900123", region: "US"))
    XCTAssertFalse(same("+447700900123", "011 44 7700 900123", region: "JP"), "011 is a Sapporo area code in Japan")
    XCTAssertTrue(same("+81111234567", "011-123-4567", region: "JP"), "a Sapporo number stays national in Japan")
  }

  func testBracketedTrunkZeroInsideAnInternationalNumber() {
    XCTAssertTrue(same("+447700900123", "+44 (0) 7700 900123", region: "US"))
    XCTAssertTrue(same("+447700900123", "0044 (0)7700 900123", region: nil))
  }

  func testExtensionsAreIgnored() {
    XCTAssertTrue(same("+14155550123", "(415) 555-0123 ext. 45", region: "US"))
    XCTAssertTrue(same("+14155550123", "+14155550123;45", region: nil))
    XCTAssertTrue(same("+14155550123", "415-555-0123 x45", region: "US"))
  }

  func testArgentineMobilesWrittenWithFifteenDoNotMatch() {
    // Documented limit: "15" is not rewritten to the international "9".
    XCTAssertFalse(same("+5491123456789", "011 15 2345-6789", region: "AR"))
  }

  func testOneNationalNumberCanStandForTwoStoredNumbersInItaly() {
    XCTAssertTrue(same("+390612345678", "06 1234 5678", region: "IT"))
    XCTAssertTrue(same("+39612345678", "06 1234 5678", region: "IT"))
    XCTAssertNotEqual(
      MessagingHandle.identityKey("+390612345678", region: "IT"),
      MessagingHandle.identityKey("+39612345678", region: "IT"))
    XCTAssertEqual(
      MessagingHandle.identityKey("+14155550123", region: "US"), MessagingHandle.identityKey("4155550123", region: "US")
    )
  }

  func testNearMissNumbersDoNotMatch() {
    XCTAssertFalse(same("+14155550123", "+14155550124", region: "US"))
    XCTAssertFalse(same("+14155550123", "0123", region: "US"))
    XCTAssertFalse(same("512345", "12345", region: "US"))
    XCTAssertFalse(same("sam@example.com", "sam@example.org", region: "US"))
    XCTAssertFalse(same("", "", region: "US"))
  }

  // MARK: - The same person matches

  func testUSNationalNumberMatchesItsInternationalForm() {
    XCTAssertTrue(same("+14155550123", "(415) 555-0123", region: "US"))
    XCTAssertTrue(same("+14155550123", "415.555.0123", region: "CA"))
  }

  func testIndianTrunkPrefixedNumberMatchesItsInternationalForm() {
    XCTAssertTrue(same("+919876543210", "09876543210", region: "IN"))
    XCTAssertTrue(same("+919876543210", "98765 43210", region: "IN"))
    XCTAssertFalse(same("+919876543210", "09876543210", region: "US"))
  }

  func testOtherSpellingsOfTheSameNumberMatch() {
    XCTAssertTrue(same("+447700900123", "07700 900123", region: "GB"))
    XCTAssertTrue(same("+390612345678", "06 1234 5678", region: "IT"), "Italian landlines keep the 0")
    XCTAssertTrue(same("+14155550123", "001 415 555 0123", region: "GB"), "00 is an international prefix")
    XCTAssertTrue(same("+14155550123", "+1 (415) 555-0123", region: nil))
    XCTAssertTrue(same("12345", "12345", region: nil))
    XCTAssertTrue(same("Sam@Example.com", "sam@example.com", region: nil))
  }

  func testCallingCodeTable() {
    XCTAssertEqual(MessagingHandle.callingCode(forRegion: "US"), "1")
    XCTAssertEqual(MessagingHandle.callingCode(forRegion: "in"), "91")
    XCTAssertEqual(MessagingHandle.callingCode(forRegion: "GB"), "44")
    XCTAssertEqual(MessagingHandle.callingCode(forRegion: "AO"), "244")
    XCTAssertEqual(MessagingHandle.callingCode(forRegion: "HK"), "852")
    XCTAssertEqual(MessagingHandle.callingCode(forRegion: "AC"), "247")
    XCTAssertNil(MessagingHandle.callingCode(forRegion: "001"))
    XCTAssertNil(MessagingHandle.callingCode(forRegion: "ZZ"))
  }

  // MARK: - One chat lookup rule for reading and checking

  func testReadMessageHistoryFindsTheChatTheSendCheckUses() async throws {
    let history = try MessagesHistoryFixture()
    defer { history.remove() }
    let chat = try history.directChat(with: "+14155550123")
    _ = try history.directChat(with: "+914155550123")
    try history.addMessage(
      chat: chat, text: "hello", at: Date(timeIntervalSince1970: 1_800_000_000), fromMe: false, sent: false,
      delivered: true)

    let messages = try await MessagesReaderService.shared.readHistory(
      chatID: nil, handle: "(415) 555-0123", limit: 10, storeOverride: history.url, region: "US")

    XCTAssertEqual(messages.map(\.chatID), [chat])
  }

  func testReadMessageHistoryStillPrefersTheDirectChat() async throws {
    let history = try MessagesHistoryFixture()
    defer { history.remove() }
    let group = try history.chat(
      handles: [history.handle("+14155550123"), history.handle("+14155550199")], service: "iMessage")
    let direct = try history.directChat(with: "+14155550123")
    try history.addMessage(
      chat: group, text: "group", at: Date(timeIntervalSince1970: 1_800_000_100), fromMe: false, sent: false,
      delivered: true)
    try history.addMessage(
      chat: direct, text: "direct", at: Date(timeIntervalSince1970: 1_800_000_000), fromMe: false, sent: false,
      delivered: true)

    let messages = try await MessagesReaderService.shared.readHistory(
      chatID: nil, handle: "+14155550123", limit: 10, storeOverride: history.url, region: "US")

    XCTAssertEqual(messages.map(\.text), ["direct"])
  }

  func testReadMessageHistoryMatchesTheSamePersonAcrossSpellings() async throws {
    let history = try MessagesHistoryFixture()
    defer { history.remove() }
    let older = try history.directChat(with: "+14155550123")
    let newer = try history.directChat(with: "4155550123", service: "SMS")
    let emailChat = try history.directChat(with: "Sam@Example.com")
    try history.addMessage(
      chat: older, text: "older", at: Date(timeIntervalSince1970: 1_800_000_000), fromMe: false, sent: false,
      delivered: true)
    try history.addMessage(
      chat: newer, text: "newer", at: Date(timeIntervalSince1970: 1_800_000_100), fromMe: false, sent: false,
      delivered: true)
    try history.addMessage(
      chat: emailChat, text: "mail", at: Date(timeIntervalSince1970: 1_800_000_000), fromMe: false, sent: false,
      delivered: true)

    // An exact request now also matches the national spelling of the same
    // number, and the more recently active direct chat wins.
    let byExact = try await MessagesReaderService.shared.readHistory(
      chatID: nil, handle: "+14155550123", limit: 10, storeOverride: history.url, region: "US")
    XCTAssertEqual(byExact.map(\.chatID), [newer])

    let byEmail = try await MessagesReaderService.shared.readHistory(
      chatID: nil, handle: "sam@example.com", limit: 10, storeOverride: history.url, region: "US")
    XCTAssertEqual(byEmail.map(\.chatID), [emailChat], "emails match without case")
  }

  // MARK: - Busy store

  func testALockedStoreWaitsForTheBusyTimeoutBeforeFailing() throws {
    let history = try MessagesHistoryFixture(wal: false)
    defer { history.remove() }
    _ = try history.directChat(with: "+14155550123")

    // omi-test-quality: wall-clock-wait -- the property under test is SQLite's own busy wait on a locked file; no injectable clock reaches it
    let waited = try history.whileLocked { () -> TimeInterval in
      let started = Date()
      let semaphore = DispatchSemaphore(value: 0)
      Task {
        _ = try? await MessagesReaderService.shared.latestMessageRowID(storeOverride: history.url)
        semaphore.signal()
      }
      semaphore.wait()
      return Date().timeIntervalSince(started)
    }

    XCTAssertGreaterThanOrEqual(waited, 0.2, "the reader should wait out a brief lock instead of failing at once")
  }
}
