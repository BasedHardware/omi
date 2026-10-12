import XCTest

@testable import Omi_Computer

final class MessagingHandleTests: XCTestCase {
  private func same(_ stored: String, _ requested: String, region: String?) -> Bool {
    MessagingHandle.isSame(stored, requested, callingCode: region.flatMap(MessagingHandle.callingCode(forRegion:)))
  }

  // MARK: - Different people never match

  func testDifferentInternationalNumbersNeverMatch() {
    XCTAssertFalse(same("+914155550123", "+14155550123", region: "US"), "+1 vs +91")
    XCTAssertFalse(same("+614155550123", "+14155550123", region: "US"), "+1 vs +61")
    XCTAssertFalse(same("+244207946000", "+44207946000", region: "GB"), "+44 vs +244")
    XCTAssertFalse(same("+914155550123", "+14155550123", region: "IN"))
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
    XCTAssertFalse(same("+14155550123", "(415) 555-0123", region: "ZZ"))
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
      chatID: nil, handle: "(415) 555-0123", limit: 10, storeOverride: history.url, callingCode: "1")

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
      chatID: nil, handle: "+14155550123", limit: 10, storeOverride: history.url, callingCode: "1")

    XCTAssertEqual(messages.map(\.text), ["direct"])
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
