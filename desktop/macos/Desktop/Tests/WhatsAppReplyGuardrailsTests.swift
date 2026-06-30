import XCTest

@testable import Omi_Computer

@MainActor
final class WhatsAppReplyGuardrailsTests: XCTestCase {
  private var suiteName: String!
  private var defaults: UserDefaults!
  private var settings: WhatsAppReplySettings!

  override func setUp() {
    super.setUp()
    suiteName = "WhatsAppReplyGuardrailsTests.\(UUID().uuidString)"
    defaults = UserDefaults(suiteName: suiteName)!
    defaults.removePersistentDomain(forName: suiteName)
    settings = WhatsAppReplySettings(defaults: defaults)
  }

  override func tearDown() {
    defaults.removePersistentDomain(forName: suiteName)
    settings = nil
    defaults = nil
    suiteName = nil
    super.tearDown()
  }

  private func makeMessage(
    chatJid: String = "15551234567@s.whatsapp.net",
    senderJid: String = "15551234567@s.whatsapp.net",
    text: String = "Hello there",
    fromMe: Bool = false,
    isGroup: Bool = false
  ) -> WAIncomingMessage {
    WAIncomingMessage(
      id: "msg-1",
      chatJid: chatJid,
      senderJid: senderJid,
      senderName: nil,
      text: text,
      fromMe: fromMe,
      isGroup: isGroup,
      timestamp: Date()
    )!
  }

  private func dateAtHour(_ hour: Int) -> Date {
    var components = Calendar.current.dateComponents([.year, .month, .day], from: Date())
    components.hour = hour
    components.minute = 30
    return Calendar.current.date(from: components)!
  }

  // MARK: - preDraftDecision

  func testPreDraftDecisionKillSwitch() {
    settings.killSwitchEnabled = true
    let decision = settings.preDraftDecision(for: makeMessage())
    XCTAssertEqual(decision, .ignore(reason: "kill_switch"))
  }

  func testPreDraftDecisionModeOff() {
    settings.mode = .off
    let decision = settings.preDraftDecision(for: makeMessage())
    XCTAssertEqual(decision, .ignore(reason: "mode_off"))
  }

  func testPreDraftDecisionFromMeIgnored() {
    let decision = settings.preDraftDecision(for: makeMessage(fromMe: true))
    XCTAssertEqual(decision, .ignore(reason: "loop_prevention"))
  }

  func testPreDraftDecisionBroadcastIgnored() {
    let decision = settings.preDraftDecision(
      for: makeMessage(chatJid: "status@broadcast", senderJid: "status@broadcast")
    )
    XCTAssertEqual(decision, .ignore(reason: "loop_prevention"))
  }

  func testPreDraftDecisionAllowsNormalMessage() {
    XCTAssertNil(settings.preDraftDecision(for: makeMessage()))
  }

  // MARK: - autoDecision

  func testAutoDecisionKillSwitch() {
    settings.killSwitchEnabled = true
    let decision = settings.autoDecision(for: makeMessage(), draftText: "Sure")
    XCTAssertEqual(decision, .ignore(reason: "kill_switch"))
  }

  func testAutoDecisionModeOff() {
    settings.mode = .off
    let decision = settings.autoDecision(for: makeMessage(), draftText: "Sure")
    XCTAssertEqual(decision, .ignore(reason: "mode_off"))
  }

  func testAutoDecisionFromMeIgnored() {
    let decision = settings.autoDecision(for: makeMessage(fromMe: true), draftText: "Sure")
    XCTAssertEqual(decision, .ignore(reason: "loop_prevention"))
  }

  func testAutoDecisionGroupChatDrafts() {
    settings.addAllowlistedJid("120363012345678901@g.us")
    let decision = settings.autoDecision(
      for: makeMessage(chatJid: "120363012345678901@g.us", senderJid: "15559876543@s.whatsapp.net", isGroup: true),
      draftText: "Sounds good"
    )
    XCTAssertEqual(decision, .draft(reason: "group_chat"))
  }

  func testAutoDecisionNotAllowlisted() {
    let decision = settings.autoDecision(for: makeMessage(), draftText: "Sure")
    XCTAssertEqual(decision, .draft(reason: "not_allowlisted"))
  }

  func testAutoDecisionQuietHours() {
    settings.addAllowlistedJid("15551234567@s.whatsapp.net")
    settings.quietHoursEnabled = true
    settings.quietHoursStart = 10
    settings.quietHoursEnd = 10
    let decision = settings.autoDecision(for: makeMessage(), draftText: "Sure")
    XCTAssertEqual(decision, .draft(reason: "quiet_hours"))
  }

  func testAutoDecisionSensitiveIncomingMessage() {
    settings.addAllowlistedJid("15551234567@s.whatsapp.net")
    settings.quietHoursEnabled = false
    let decision = settings.autoDecision(
      for: makeMessage(text: "Can you send the bank details?"),
      draftText: "Sure"
    )
    XCTAssertEqual(decision, .draft(reason: "sensitive_content"))
  }

  func testAutoDecisionSensitiveDraftText() {
    settings.addAllowlistedJid("15551234567@s.whatsapp.net")
    settings.quietHoursEnabled = false
    let decision = settings.autoDecision(
      for: makeMessage(text: "Need help"),
      draftText: "I'll send the payment tonight"
    )
    XCTAssertEqual(decision, .draft(reason: "sensitive_content"))
  }

  func testAutoDecisionRateLimited() {
    settings.addAllowlistedJid("15551234567@s.whatsapp.net")
    settings.quietHoursEnabled = false
    settings.rateLimitPerHour = 1
    settings.markAutoSent(to: "15551234567@s.whatsapp.net")
    let decision = settings.autoDecision(for: makeMessage(), draftText: "Sure")
    XCTAssertEqual(decision, .draft(reason: "rate_limited"))
  }

  func testAutoDecisionAllowedWhenAllChecksPass() {
    settings.addAllowlistedJid("15551234567@s.whatsapp.net")
    settings.quietHoursEnabled = false
    settings.rateLimitPerHour = 5
    let decision = settings.autoDecision(for: makeMessage(), draftText: "Sure thing")
    XCTAssertEqual(decision, .auto)
  }

  // MARK: - isQuietHoursActive

  func testQuietHoursDisabled() {
    settings.quietHoursEnabled = false
    settings.quietHoursStart = 22
    settings.quietHoursEnd = 7
    XCTAssertFalse(settings.isQuietHoursActive(at: dateAtHour(23)))
  }

  func testQuietHoursSameStartAndEndAlwaysActive() {
    settings.quietHoursEnabled = true
    settings.quietHoursStart = 10
    settings.quietHoursEnd = 10
    XCTAssertTrue(settings.isQuietHoursActive(at: dateAtHour(0)))
    XCTAssertTrue(settings.isQuietHoursActive(at: dateAtHour(12)))
  }

  func testQuietHoursNormalWindow() {
    settings.quietHoursEnabled = true
    settings.quietHoursStart = 10
    settings.quietHoursEnd = 14
    XCTAssertFalse(settings.isQuietHoursActive(at: dateAtHour(9)))
    XCTAssertTrue(settings.isQuietHoursActive(at: dateAtHour(11)))
    XCTAssertFalse(settings.isQuietHoursActive(at: dateAtHour(14)))
  }

  func testQuietHoursWrapAroundWindow() {
    settings.quietHoursEnabled = true
    settings.quietHoursStart = 22
    settings.quietHoursEnd = 7
    XCTAssertTrue(settings.isQuietHoursActive(at: dateAtHour(23)))
    XCTAssertTrue(settings.isQuietHoursActive(at: dateAtHour(5)))
    XCTAssertFalse(settings.isQuietHoursActive(at: dateAtHour(12)))
  }

  // MARK: - containsSensitiveContent

  func testContainsSensitiveContentDetectsFinancialTerms() {
    XCTAssertTrue(settings.containsSensitiveContent("Please send bank details"))
    XCTAssertFalse(settings.containsSensitiveContent("See you at the park"))
  }

  func testContainsSensitiveContentIsCaseInsensitive() {
    XCTAssertTrue(settings.containsSensitiveContent("LEGAL review needed"))
  }

  // MARK: - canAttemptManualSend

  func testManualSendBlockedByKillSwitch() {
    settings.killSwitchEnabled = true
    XCTAssertEqual(
      settings.canAttemptManualSend(clientMessageID: "client-1"),
      .blocked("WhatsApp kill switch is enabled")
    )
  }

  func testManualSendAllowsFirstClientMessageID() {
    XCTAssertEqual(settings.canAttemptManualSend(clientMessageID: "client-1"), .allowed)
  }

  func testManualSendDedupesRepeatedClientMessageID() {
    XCTAssertEqual(settings.canAttemptManualSend(clientMessageID: "client-1"), .allowed)
    XCTAssertEqual(settings.canAttemptManualSend(clientMessageID: "client-1"), .duplicate)
  }

  func testManualSendAllowsNilOrEmptyClientMessageIDRepeatedly() {
    XCTAssertEqual(settings.canAttemptManualSend(clientMessageID: nil), .allowed)
    XCTAssertEqual(settings.canAttemptManualSend(clientMessageID: nil), .allowed)
    XCTAssertEqual(settings.canAttemptManualSend(clientMessageID: ""), .allowed)
    XCTAssertEqual(settings.canAttemptManualSend(clientMessageID: ""), .allowed)
  }
}
