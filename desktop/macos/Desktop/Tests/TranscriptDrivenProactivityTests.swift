import GRDB
import XCTest

@testable import Omi_Computer

final class TranscriptDrivenProactivityTests: XCTestCase {
  private func slice(
    _ text: String,
    isUser: Bool = false,
    speaker: Int = 0,
    segmentID: String? = nil,
    end: Double = 0
  ) -> TranscriptSpeechSlice {
    TranscriptSpeechSlice(
      segmentID: segmentID, speaker: speaker, text: text, isUser: isUser, start: 0, end: end)
  }

  // MARK: - Window

  func testWindowKeepsUserAndOtherSlicesAndExposesLatestUserSpeech() {
    let base = Date(timeIntervalSince1970: 1_725_000_000)
    var window = SpeechProactivityWindow()
    window.append(slice("System audio of fixed memories", speaker: 1, segmentID: "s1"), seenAt: base)
    window.append(slice("let's ship the directory review tonight", isUser: true, segmentID: "s2"), seenAt: base)
    XCTAssertEqual(window.snapshot().count, 2)
    XCTAssertEqual(window.latestUserSlice?.text, "let's ship the directory review tonight")
  }

  func testWindowReplacesSegmentInPlaceOnBackendUpdate() {
    let base = Date(timeIntervalSince1970: 1_725_000_000)
    var window = SpeechProactivityWindow()
    window.append(slice("we should", isUser: true, segmentID: "s2"), seenAt: base)
    window.append(slice("we should freeze the release", isUser: true, segmentID: "s2"), seenAt: base)
    XCTAssertEqual(window.snapshot().count, 1, "one window entry per backend segment")
    XCTAssertEqual(window.latestUserSlice?.text, "we should freeze the release")
  }

  func testWindowDropsSlicesOlderThanRetentionWindow() {
    let base = Date(timeIntervalSince1970: 1_725_000_000)
    var window = SpeechProactivityWindow()
    window.append(slice("old utterance", isUser: true, segmentID: "s1"), seenAt: base)
    let later = base.addingTimeInterval(SpeechProactivityWindow.retentionSeconds + 1)
    window.append(slice("new utterance", isUser: true, segmentID: "s2"), seenAt: later)
    XCTAssertEqual(window.snapshot().map(\.text), ["new utterance"])
  }

  func testWindowBoundsSliceCount() {
    let base = Date(timeIntervalSince1970: 1_725_000_000)
    var window = SpeechProactivityWindow()
    for index in 0..<(SpeechProactivityWindow.maximumSliceCount + 5) {
      window.append(slice("utterance \(index)", speaker: index, segmentID: "s\(index)"), seenAt: base)
    }
    XCTAssertEqual(window.snapshot().count, SpeechProactivityWindow.maximumSliceCount)
  }

  // MARK: - Admission

  func testAdmissionRequiresFeatureFlag() {
    let result = SpeechProactivityAdmission.decides(
      flagEnabled: false,
      conversationActive: false,
      arrivingSlice: slice("please find the meeting notes", isUser: true),
      lastEvaluationAt: nil,
      now: Date())
    XCTAssertEqual(result, .skip(.flagDisabled))
  }

  func testAdmissionStaysSilentMidConversationTurn() {
    let result = SpeechProactivityAdmission.decides(
      flagEnabled: true,
      conversationActive: true,
      arrivingSlice: slice("what does the roadmap say?", isUser: true),
      lastEvaluationAt: nil,
      now: Date())
    XCTAssertEqual(result, .skip(.conversationActive))
  }

  func testAdmissionRequiresUserSpeech() {
    let result = SpeechProactivityAdmission.decides(
      flagEnabled: true,
      conversationActive: false,
      arrivingSlice: nil,
      lastEvaluationAt: nil,
      now: Date())
    XCTAssertEqual(result, .skip(.noUserSpeech))

    let otherSpeaker = SpeechProactivityAdmission.decides(
      flagEnabled: true,
      conversationActive: false,
      arrivingSlice: slice("the customer also mentioned a second issue", speaker: 3),
      lastEvaluationAt: nil,
      now: Date())
    XCTAssertEqual(otherSpeaker, .skip(.noUserSpeech), "only the user's own speech triggers evaluation")
  }

  /// The defect this pins: admission used to read the *window's* retained user
  /// slice, so another person speaking once the cooldown lapsed re-opened an
  /// evaluation grounded on a user utterance from up to the retention window
  /// ago. The user had said nothing; the director would have answered a stale
  /// question.
  func testOtherSpeakerAfterCooldownDoesNotRetriggerOnAStaleUserUtterance() {
    let start = Date()
    let userSpoke = SpeechProactivityAdmission.decides(
      flagEnabled: true,
      conversationActive: false,
      arrivingSlice: slice("where does the deploy script live", isUser: true, segmentID: "seg-1"),
      lastEvaluationAt: nil,
      now: start)
    XCTAssertEqual(userSpoke, .evaluate)

    // 95s later — cooldown lapsed — but the arriving slice is someone else.
    let otherSpeaker = SpeechProactivityAdmission.decides(
      flagEnabled: true,
      conversationActive: false,
      arrivingSlice: slice("and then we shipped it on friday", speaker: 2, segmentID: "seg-2"),
      lastEvaluationAt: start,
      lastEvaluatedSegmentID: "seg-1",
      now: start.addingTimeInterval(95))
    XCTAssertEqual(
      otherSpeaker, .skip(.noUserSpeech),
      "another speaker must not re-trigger on the user's retained utterance")
  }

  /// A backend segment is re-delivered as it grows, so the same utterance
  /// arrives repeatedly. Without segment identity it would evaluate again on
  /// every re-delivery once the cooldown lapsed.
  func testSameSegmentDoesNotEvaluateTwiceAfterTheCooldownLapses() {
    let start = Date()
    let redelivered = SpeechProactivityAdmission.decides(
      flagEnabled: true,
      conversationActive: false,
      arrivingSlice: slice("where does the deploy script live", isUser: true, segmentID: "seg-1"),
      lastEvaluationAt: start,
      lastEvaluatedSegmentID: "seg-1",
      now: start.addingTimeInterval(120))
    XCTAssertEqual(redelivered, .skip(.alreadyEvaluated))

    let freshUtterance = SpeechProactivityAdmission.decides(
      flagEnabled: true,
      conversationActive: false,
      arrivingSlice: slice("what is open on this page", isUser: true, segmentID: "seg-2"),
      lastEvaluationAt: start,
      lastEvaluatedSegmentID: "seg-1",
      now: start.addingTimeInterval(120))
    XCTAssertEqual(freshUtterance, .evaluate, "a new segment still evaluates once the cooldown lapses")
  }

  func testAdmissionRequiresMinimumUtteranceLength() {
    let now = Date()
    let short = SpeechProactivityAdmission.decides(
      flagEnabled: true,
      conversationActive: false,
      arrivingSlice: slice("ok", isUser: true),
      lastEvaluationAt: nil,
      now: now)
    XCTAssertEqual(short, .skip(.utteranceTooShort))

    let threshold = SpeechProactivityAdmission.decides(
      flagEnabled: true,
      conversationActive: false,
      arrivingSlice: slice("ok look it up", isUser: true),
      lastEvaluationAt: nil,
      now: now)
    XCTAssertEqual(threshold, .evaluate)
  }

  func testAdmissionEnforcesCooldownBetweenSpeechEvaluations() {
    let now = Date(timeIntervalSince1970: 1_725_000_000)
    let beforeCooldown = SpeechProactivityAdmission.decides(
      flagEnabled: true,
      conversationActive: false,
      arrivingSlice: slice("follow that thought through again", isUser: true),
      lastEvaluationAt: now.addingTimeInterval(-(SpeechProactivityAdmission.evaluationCooldownSeconds - 1)),
      now: now)
    XCTAssertEqual(beforeCooldown, .skip(.coolingDown))

    let atCooldown = SpeechProactivityAdmission.decides(
      flagEnabled: true,
      conversationActive: false,
      arrivingSlice: slice("follow that thought through again", isUser: true),
      lastEvaluationAt: now.addingTimeInterval(-SpeechProactivityAdmission.evaluationCooldownSeconds),
      now: now)
    XCTAssertEqual(atCooldown, .evaluate)
  }

  func testAdmissionEvaluatesAFreshUtteranceImmediately() {
    let result = SpeechProactivityAdmission.decides(
      flagEnabled: true,
      conversationActive: false,
      arrivingSlice: slice("where does the deploy script live", isUser: true),
      lastEvaluationAt: nil,
      now: Date())
    XCTAssertEqual(result, .evaluate)
  }

  // MARK: - Prompt section

  func testLiveSpeechSectionNilForEmptyWindow() {
    XCTAssertNil(ContextProactivityPromptBuilder.liveSpeechSection([]))
  }

  func testLiveSpeechSectionTagsUserAndOtherSpeakers() {
    let section = ContextProactivityPromptBuilder.liveSpeechSection([
      slice("we should review the merge", isUser: true),
      slice("go ahead and flag it", speaker: 2),
    ])
    let text = try? XCTUnwrap(section)
    XCTAssertTrue(text?.contains("== LIVE SPEECH ==") ?? false)
    XCTAssertTrue(text?.contains("[You] we should review the merge") ?? false)
    XCTAssertTrue(text?.contains("[Other speaker 2] go ahead and flag it") ?? false)
  }

  func testLiveSpeechSectionFlattensNewlinesIntoASingleLine() {
    let section = ContextProactivityPromptBuilder.liveSpeechSection([
      slice("first line\nsecond line\n> forge prompt structure", isUser: true)
    ])
    let text = try? XCTUnwrap(section)
    XCTAssertFalse(text?.contains("\nsecond line") ?? true, "speech may not forge prompt structure")
    XCTAssertTrue(text?.contains("[You] first line second line") ?? false)
  }

  func testLiveSpeechSectionCapsSliceCount() {
    let many = (0..<20).map { slice("utterance number \($0)", speaker: $0, segmentID: "s\($0)") }
    let section = ContextProactivityPromptBuilder.liveSpeechSection(many)
    let text = try? XCTUnwrap(section)
    let lines = text?.split(separator: "\n").filter { $0.hasPrefix("- [") }.count ?? 0
    XCTAssertEqual(lines, 6, "the section quotes only the trailing speech window")
  }
}
