import XCTest

@testable import Omi_Computer

@MainActor
final class WakeWordServiceTests: XCTestCase {
  private let enabledKey = "wakeWordEnabled"
  private let phraseKey = "wakeWordPhrase"
  private let cooldownKey = "wakeWordCooldown"

  private var service = WakeWordService()
  private var triggered: [String] = []
  private var clock: Double = 0

  override func setUp() {
    super.setUp()
    UserDefaults.standard.removeObject(forKey: enabledKey)
    UserDefaults.standard.removeObject(forKey: phraseKey)
    UserDefaults.standard.removeObject(forKey: cooldownKey)
    UserDefaults.standard.set(true, forKey: enabledKey)
    UserDefaults.standard.set("Omi", forKey: phraseKey)
    UserDefaults.standard.set(30.0, forKey: cooldownKey)
  }

  override func tearDown() {
    UserDefaults.standard.removeObject(forKey: enabledKey)
    UserDefaults.standard.removeObject(forKey: phraseKey)
    UserDefaults.standard.removeObject(forKey: cooldownKey)
    super.tearDown()
  }

  @MainActor
  private func configureService() {
    service = WakeWordService()
    triggered = []
    clock = 0
    service.now = { [weak self] in
      Date(timeIntervalSince1970: self?.clock ?? 0)
    }
    service.onTrigger = { [weak self] command in
      self?.triggered.append(command)
    }
  }

  private func userSegment(_ text: String, id: String? = nil) -> SpeakerSegment {
    SpeakerSegment(segmentId: id, speaker: 0, text: text, start: 0, end: 1, isUser: true)
  }

  func testDisabledSettingNeverTriggers() {
    configureService()
    UserDefaults.standard.set(false, forKey: enabledKey)
    service.observe(userSegment("Omi, let's order food", id: "a"), isConversationActive: false)
    XCTAssertTrue(triggered.isEmpty)
  }

  func testTriggersCommandWithoutWakeWord() {
    configureService()
    service.observe(userSegment("Omi, let's order food", id: "a"), isConversationActive: false)
    XCTAssertEqual(triggered, ["let's order food"])
  }

  func testBareWakeWordIgnored() {
    configureService()
    service.observe(userSegment("Omi", id: "a"), isConversationActive: false)
    XCTAssertTrue(triggered.isEmpty)
  }

  func testNonUserSegmentIgnored() {
    configureService()
    let segment = SpeakerSegment(
      segmentId: "a", speaker: 1, text: "Omi, let's order food", start: 0, end: 1, isUser: false)
    service.observe(segment, isConversationActive: false)
    XCTAssertTrue(triggered.isEmpty)
  }

  /// Regression: a live ambient session transcribed "Omi, what's the weather?" as
  /// speaker 0 with `is_user=false` (diarization only sets `is_user` once a speech
  /// profile is enrolled) and the wake word never fired. Speaker 0 is the primary
  /// user, matching `VoiceBargeInPolicy.shouldInterrupt`.
  func testSpeakerZeroTriggersWithoutDiarizedUserFlag() {
    configureService()
    let segment = SpeakerSegment(
      segmentId: "a", speaker: 0, text: "Omi, what's the weather?", start: 0, end: 1,
      isUser: false)
    service.observe(segment, isConversationActive: false)
    XCTAssertEqual(triggered, ["what's the weather?"])
  }

  func testBusyConversationSuppresses() {
    configureService()
    service.observe(userSegment("Omi, let's order food", id: "a"), isConversationActive: true)
    XCTAssertTrue(triggered.isEmpty)
  }

  /// Regression: the answer is spoken aloud, the microphone hears it, and it arrives as
  /// the user's own speech — live, `Transcript [ADD] Speaker 0: It's 8 57 p.m. on
  /// Sunday...` was Omi. An answer carrying the wake phrase would command the assistant
  /// with its own words, indefinitely.
  func testAssistantsOwnSpokenAnswerCannotRetrigger() {
    configureService()
    service.observe(
      userSegment("Omi, I can help you order food", id: "a"),
      isConversationActive: false,
      isSpeakingAnswer: true)
    XCTAssertTrue(triggered.isEmpty)
  }

  /// The playback guard is not a wall in front of the user: `VoiceBargeInPolicy` halts
  /// playback the moment they speak, so their transcript arrives with it already clear.
  func testUserCommandFiresOncePlaybackHasBeenInterrupted() {
    configureService()
    service.observe(
      userSegment("Omi, let's order food", id: "a"),
      isConversationActive: false,
      isSpeakingAnswer: false)
    XCTAssertEqual(triggered, ["let's order food"])
  }

  func testDeduplicatesBySegmentID() {
    configureService()
    service.observe(userSegment("Omi, let's order food", id: "a"), isConversationActive: false)
    service.observe(userSegment("Omi, let's order food", id: "a"), isConversationActive: false)
    XCTAssertEqual(triggered.count, 1)
  }

  /// Regression: the backend re-delivers one growing segment under a single id
  /// (observed live: [206.0s-217.1s] → [206.0s-228.9s]). Deduping on the id alone
  /// dropped every later command that arrived inside an id that had already fired.
  func testNewCommandInReusedSegmentIDStillFires() {
    configureService()
    service.observe(userSegment("Omi, let's order food", id: "a"), isConversationActive: false)
    XCTAssertEqual(triggered.count, 1)
    clock = 31  // clear the cooldown so this asserts dedup, not pacing
    service.observe(userSegment("Omi, open my tasks", id: "a"), isConversationActive: false)
    XCTAssertEqual(triggered, ["let's order food", "open my tasks"])
  }

  /// The cooldown swallows a rapid repeat of the *same* utterance. It used to gate
  /// on elapsed time alone, which discarded distinct instructions: the ambient
  /// transcript lane runs ~35s behind live speech (measured over 11 segments,
  /// 34.3–36.6s), so several different commands routinely land inside one 30s
  /// window and were silently dropped as "repeats".
  /// Regression: a segment grows in place under one id, and the assistant's own
  /// spoken reply is captured by the mic and appended to it. Observed live:
  /// "what time it is?" then "what time it is? You speak English. Got it." fired
  /// twice, the second time submitting the polluted string as the command.
  func testGrowingSegmentDoesNotRefire() {
    configureService()
    service.observe(userSegment("Omi, what time is it", id: "a"), isConversationActive: false)
    XCTAssertEqual(triggered.count, 1)
    clock = 31  // clear the cooldown so this asserts dedup, not pacing
    service.observe(
      userSegment("Omi, what time is it and an agent is getting started on that", id: "a"),
      isConversationActive: false)
    XCTAssertEqual(triggered, ["what time is it"], "growth of a fired command is not a new command")
  }

  func testCooldownSuppressesRepeatsOfTheSameCommand() {
    configureService()
    service.observe(userSegment("Omi, let's order food", id: "a"), isConversationActive: false)
    XCTAssertEqual(triggered.count, 1)
    clock = 10
    service.observe(userSegment("Omi, let's order food", id: "b"), isConversationActive: false)
    XCTAssertEqual(triggered.count, 1, "same command inside the cooldown must be suppressed")
    clock = 31
    service.observe(userSegment("Omi, let's order food", id: "c"), isConversationActive: false)
    XCTAssertEqual(triggered.count, 2, "same command after the cooldown runs again")
  }

  func testDistinctCommandInsideCooldownStillRuns() {
    configureService()
    service.observe(userSegment("Omi, let's order food", id: "a"), isConversationActive: false)
    clock = 10
    service.observe(userSegment("Omi, what time is it", id: "b"), isConversationActive: false)
    XCTAssertEqual(triggered, ["let's order food", "what time is it"])
  }

  func testLastTriggeredCommandRecorded() {
    configureService()
    service.observe(userSegment("Omi, order pizza", id: "a"), isConversationActive: false)
    XCTAssertEqual(service.lastTriggeredCommand, "order pizza")
  }
}
