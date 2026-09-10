import VoiceTurnDomain
import XCTest

@testable import Omi_Computer

/// Silent Type: dictation still types into the focused app, but the turn never
/// reaches the chat transcript, so voice-typed text stays out of Omi's chat
/// context. Off by default — dictations are journaled as they always were.
@MainActor
final class VoiceTypingSilentModeTests: XCTestCase {
  private static let defaultsKey = DefaultsKey.shortcutSilentTypeEnabled.rawValue
  private static let managerSourceName = "PushToTalkManager.swift"
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

  func testTogglingSilentTypePersistsAcrossLaunches() throws {
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

    // The writes above only exercise the `didSet` writer in this process. A
    // relaunch restores the toggle through the launch read, so prove that read
    // against a fresh defaults domain, the way a fresh settings instance sees it.
    let launchDomain = "omi-silent-type-relaunch-\(UUID().uuidString)"
    let launchDefaults = try XCTUnwrap(UserDefaults(suiteName: launchDomain))
    defer { launchDefaults.removePersistentDomain(forName: launchDomain) }
    XCTAssertFalse(
      ShortcutSettings.persistedSilentTypeEnabled(from: launchDefaults),
      "an absent key reads false — Silent Type ships off for a fresh install")
    launchDefaults.set(true, forKey: Self.defaultsKey)
    let restored = ShortcutSettings.persistedSilentTypeEnabled(from: launchDefaults)
    XCTAssertTrue(
      restored,
      "the launch read must restore exactly what the toggle persisted")
    XCTAssertFalse(
      VoiceTypingChatRecordPolicy.decide(silentTypeEnabled: restored).journalsExchange,
      "the restored toggle keeps the dictation out of the chat transcript")
  }

  /// The race this closes. Suppression used to latch only in the delivery
  /// close path, so a realtime provider failure while the dictation was still
  /// finalizing reached `captureInterruptedTurnPayloadIfNeeded` with no
  /// suppression receipt — and recovery journaled the very text the user asked
  /// to keep out of the chat. The turn now names itself as suppressed at its
  /// start, before anything can fail mid-turn.
  func testProviderFailureDuringFinalizationKeepsASilentTypeDictationOutOfRecovery() {
    ShortcutSettings.shared.silentTypeEnabled = true
    let hub = RealtimeHubController.shared
    let coordinator = VoiceTurnCoordinator.shared
    PushToTalkManager.shared.cleanup()
    let turnID = coordinator.begin(intent: .hold, ownerID: "silent-type-race-owner")
    defer {
      hub.turnTranscript = ""
      hub.turnIdempotencyKey = ""
      hub.journalSuppressedContinuityKey = nil
      coordinator.reset()
    }
    coordinator.publish(.selectRoute(turnID: turnID, route: .hub(sessionID: nil)))

    // Mid-finalization: the provider has already streamed the dictation back
    // as this turn's transcript, nothing has been delivered yet, and no
    // persistence receipt exists — then the socket fails.
    hub.turnIdempotencyKey = RealtimeHubController.voiceContinuityKey(for: turnID)
    hub.turnTranscript = "type hello from the privacy race"
    hub.journalSuppressedContinuityKey = nil

    // Turn start, not delivery, latches the suppression.
    PushToTalkManager.shared.latchSilentTypeForTurnStart(turnID: turnID)

    XCTAssertNil(
      hub.captureInterruptedTurnPayloadIfNeeded(),
      "a provider failure during finalization must not hand a Silent Type "
        + "dictation's transcript to interrupted-turn recovery")
    XCTAssertEqual(
      hub.journalSuppressedContinuityKey,
      RealtimeHubController.voiceContinuityKey(for: turnID),
      "the suppression receipt must stay standing for the whole turn")
  }

  /// With the toggle off the latch is inert: the turn keeps the recovery that
  /// provider-failure continuity depends on, byte-identical to the journaled
  /// behavior Silent Type opted out of.
  func testTurnStartLatchIsInertWhileSilentTypeIsOff() {
    ShortcutSettings.shared.silentTypeEnabled = false
    let hub = RealtimeHubController.shared
    let coordinator = VoiceTurnCoordinator.shared
    PushToTalkManager.shared.cleanup()
    let turnID = coordinator.begin(intent: .hold, ownerID: "journaled-turn-owner")
    defer {
      hub.turnTranscript = ""
      hub.turnIdempotencyKey = ""
      hub.journalSuppressedContinuityKey = nil
      coordinator.reset()
    }
    coordinator.publish(.selectRoute(turnID: turnID, route: .hub(sessionID: nil)))
    hub.turnIdempotencyKey = RealtimeHubController.voiceContinuityKey(for: turnID)
    hub.turnTranscript = "what is on my calendar tomorrow"
    hub.journalSuppressedContinuityKey = nil

    PushToTalkManager.shared.latchSilentTypeForTurnStart(turnID: turnID)

    XCTAssertNil(
      hub.journalSuppressedContinuityKey,
      "a journaled turn must not carry a suppression receipt")
    XCTAssertNotNil(
      hub.captureInterruptedTurnPayloadIfNeeded(),
      "with Silent Type off a failed turn keeps its provider-failure recovery")
  }

  /// The toggle is read once, at turn start. A flip mid-turn must not split the
  /// turn: one that began with Silent Type off keeps journaling semantics, and
  /// one that began with it on stays suppressed.
  func testMidTurnToggleFlipDoesNotSplitTheTurn() {
    let hub = RealtimeHubController.shared
    let coordinator = VoiceTurnCoordinator.shared
    PushToTalkManager.shared.cleanup()
    let offThenOnTurn = coordinator.begin(intent: .hold, ownerID: "mid-turn-flip-owner")
    defer {
      hub.turnTranscript = ""
      hub.turnIdempotencyKey = ""
      hub.journalSuppressedContinuityKey = nil
      coordinator.reset()
    }
    coordinator.publish(.selectRoute(turnID: offThenOnTurn, route: .hub(sessionID: nil)))
    hub.turnIdempotencyKey = RealtimeHubController.voiceContinuityKey(for: offThenOnTurn)
    hub.turnTranscript = "type a note about the flip"
    hub.journalSuppressedContinuityKey = nil

    ShortcutSettings.shared.silentTypeEnabled = false
    PushToTalkManager.shared.latchSilentTypeForTurnStart(turnID: offThenOnTurn)
    ShortcutSettings.shared.silentTypeEnabled = true

    XCTAssertNil(
      hub.journalSuppressedContinuityKey,
      "a turn that started with Silent Type off is not suppressed by a mid-turn flip on")
  }

  /// The latch is only as good as its wiring: both physical turn starts must
  /// arm it, and the delivery close path must decide with the latched value
  /// rather than a fresh read.
  func testTurnStartsLatchTheSuppressionAndDeliveryDecidesWithTheLatch() throws {
    let testFile = URL(fileURLWithPath: #filePath)
    // omi-test-quality: source-inspection -- static contract: both turn starts must arm the Silent Type latch, delivery decides with the latched value
    let source = try String(
      contentsOf:
        testFile
        .deletingLastPathComponent()
        .deletingLastPathComponent()
        .appendingPathComponent("Sources/FloatingControlBar")
        .appendingPathComponent(Self.managerSourceName),
      encoding: .utf8)
    XCTAssertEqual(
      source.components(
        separatedBy: "latchSilentTypeForTurnStart(turnID: currentVoiceTurnID)"
      ).count - 1,
      2,
      "hold and locked turn starts must both latch Silent Type at the turn's start")
    XCTAssertTrue(
      source.contains("silentTypeEnabled: voiceTypingSilentTypeEnabled"),
      "the delivery close path must decide with the turn-start latch, not a fresh read")
  }

  func testSilentTypeIsSearchableFromTheTranscriptionTab() {
    let item = SettingsSearchItem.allSearchableItems.first { $0.settingId == "transcription.silenttype" }
    XCTAssertNotNil(item, "the Silent Type card must be reachable from settings search")
    XCTAssertEqual(item?.section, .transcription)
  }
}
