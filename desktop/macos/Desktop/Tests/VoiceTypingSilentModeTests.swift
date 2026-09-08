import XCTest

@testable import Omi_Computer

/// Silent Type: dictation still types into the focused app, but the turn never
/// reaches the chat transcript, so voice-typed text stays out of Omi's chat
/// context. Off by default — dictations are journaled as they always were.
@MainActor
final class VoiceTypingSilentModeTests: XCTestCase {
  private static let defaultsKey = DefaultsKey.shortcutSilentTypeEnabled.rawValue
  private var savedSetting: Bool?
  private var hadSavedSetting = false

  override func setUp() async throws {
    hadSavedSetting = UserDefaults.standard.object(forKey: Self.defaultsKey) != nil
    savedSetting = hadSavedSetting ? UserDefaults.standard.bool(forKey: Self.defaultsKey) : nil
  }

  override func tearDown() async throws {
    if let savedSetting {
      UserDefaults.standard.set(savedSetting, forKey: Self.defaultsKey)
    } else {
      UserDefaults.standard.removeObject(forKey: Self.defaultsKey)
    }
    ShortcutSettings.shared.silentTypeEnabled = savedSetting ?? false
    savedSetting = nil
    hadSavedSetting = false
  }

  func testDictationIsJournaledWhenSilentTypeIsOff() {
    let decision = VoiceTypingChatRecordPolicy.decide(silentTypeEnabled: false)
    XCTAssertTrue(
      decision.journalsExchange,
      "with Silent Type off a delivered dictation must still enter the chat transcript")
    XCTAssertFalse(
      decision.retiresReservedEvidence,
      "the journal path binds its own reserved source; retiring it here would drop late OCR")
    XCTAssertFalse(
      decision.suppressesJournalRecovery,
      "a journaled turn stands recovery down with its accepted receipt, not a suppression")
  }

  func testSilentTypeKeepsDictationOutOfChatAndFencesReservedEvidence() {
    let decision = VoiceTypingChatRecordPolicy.decide(silentTypeEnabled: true)
    XCTAssertFalse(
      decision.journalsExchange,
      "Silent Type must not write the dictation to the chat transcript")
    XCTAssertTrue(
      decision.retiresReservedEvidence,
      "no producing row will exist, so the reserved native source must be fenced "
        + "or a late extraction can invent an admission for an unwritten turn")
    XCTAssertTrue(
      decision.suppressesJournalRecovery,
      "an unwritten turn has no accepted receipt, so recovery must be barred explicitly")
  }

  /// The gap this closes: interrupted-turn recovery normally stands down because
  /// the turn already has an accepted persistence receipt. A Silent Type turn is
  /// never written, so it has none — without an explicit suppression a later
  /// provider failure would journal the very text the user kept out of the chat.
  func testSuppressedTurnIsNeverRecoveredIntoTheJournal() {
    XCTAssertFalse(
      RealtimeHubController.recoversInterruptedTurn(
        continuityKey: "voice:A", suppressedKey: "voice:A"),
      "a Silent Type turn's transcript must not be resurrected by recovery")
  }

  func testRecoveryStillRunsForOtherTurns() {
    XCTAssertTrue(
      RealtimeHubController.recoversInterruptedTurn(
        continuityKey: "voice:B", suppressedKey: "voice:A"),
      "suppressing one dictation must not disable recovery for every later turn")
    XCTAssertTrue(
      RealtimeHubController.recoversInterruptedTurn(
        continuityKey: "voice:B", suppressedKey: nil),
      "an ordinary turn keeps provider-failure continuity")
    XCTAssertTrue(
      RealtimeHubController.recoversInterruptedTurn(continuityKey: "", suppressedKey: nil),
      "an unkeyed turn is not treated as suppressed")
  }

  func testSilentTypeIsOffForAUserWhoNeverChoseIt() {
    UserDefaults.standard.removeObject(forKey: Self.defaultsKey)
    XCTAssertFalse(
      UserDefaults.standard.object(forKey: Self.defaultsKey) as? Bool ?? false,
      "Silent Type ships off: dictation keeps its existing chat-transcript behavior")
    XCTAssertTrue(
      VoiceTypingChatRecordPolicy.decide(
        silentTypeEnabled: UserDefaults.standard.object(forKey: Self.defaultsKey) as? Bool ?? false
      ).journalsExchange)
  }

  func testTogglingSilentTypePersistsAcrossLaunches() {
    ShortcutSettings.shared.silentTypeEnabled = true
    XCTAssertTrue(
      UserDefaults.standard.bool(forKey: Self.defaultsKey),
      "the toggle must survive a relaunch, like every other push-to-talk preference")
    XCTAssertFalse(
      VoiceTypingChatRecordPolicy.decide(
        silentTypeEnabled: UserDefaults.standard.bool(forKey: Self.defaultsKey)
      ).journalsExchange)

    ShortcutSettings.shared.silentTypeEnabled = false
    XCTAssertFalse(UserDefaults.standard.bool(forKey: Self.defaultsKey))
  }

  func testSilentTypeIsSearchableFromTheTranscriptionTab() {
    let item = SettingsSearchItem.allSearchableItems.first { $0.settingId == "transcription.silenttype" }
    XCTAssertNotNil(item, "the Silent Type card must be reachable from settings search")
    XCTAssertEqual(item?.section, .transcription)
  }
}
