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
      latestUserSlice: slice("please find the meeting notes", isUser: true),
      lastEvaluationAt: nil,
      now: Date())
    XCTAssertEqual(result, .skip(.flagDisabled))
  }

  func testAdmissionStaysSilentMidConversationTurn() {
    let result = SpeechProactivityAdmission.decides(
      flagEnabled: true,
      conversationActive: true,
      latestUserSlice: slice("what does the roadmap say?", isUser: true),
      lastEvaluationAt: nil,
      now: Date())
    XCTAssertEqual(result, .skip(.conversationActive))
  }

  func testAdmissionRequiresUserSpeech() {
    let result = SpeechProactivityAdmission.decides(
      flagEnabled: true,
      conversationActive: false,
      latestUserSlice: nil,
      lastEvaluationAt: nil,
      now: Date())
    XCTAssertEqual(result, .skip(.noUserSpeech))

    let otherSpeaker = SpeechProactivityAdmission.decides(
      flagEnabled: true,
      conversationActive: false,
      latestUserSlice: slice("the customer also mentioned a second issue", speaker: 3),
      lastEvaluationAt: nil,
      now: Date())
    XCTAssertEqual(otherSpeaker, .skip(.noUserSpeech), "only the user's own speech triggers evaluation")
  }

  func testAdmissionRequiresMinimumUtteranceLength() {
    let now = Date()
    let short = SpeechProactivityAdmission.decides(
      flagEnabled: true,
      conversationActive: false,
      latestUserSlice: slice("ok", isUser: true),
      lastEvaluationAt: nil,
      now: now)
    XCTAssertEqual(short, .skip(.utteranceTooShort))

    let threshold = SpeechProactivityAdmission.decides(
      flagEnabled: true,
      conversationActive: false,
      latestUserSlice: slice("ok look it up", isUser: true),
      lastEvaluationAt: nil,
      now: now)
    XCTAssertEqual(threshold, .evaluate)
  }

  func testAdmissionEnforcesCooldownBetweenSpeechEvaluations() {
    let now = Date(timeIntervalSince1970: 1_725_000_000)
    let beforeCooldown = SpeechProactivityAdmission.decides(
      flagEnabled: true,
      conversationActive: false,
      latestUserSlice: slice("follow that thought through again", isUser: true),
      lastEvaluationAt: now.addingTimeInterval(-(SpeechProactivityAdmission.evaluationCooldownSeconds - 1)),
      now: now)
    XCTAssertEqual(beforeCooldown, .skip(.coolingDown))

    let atCooldown = SpeechProactivityAdmission.decides(
      flagEnabled: true,
      conversationActive: false,
      latestUserSlice: slice("follow that thought through again", isUser: true),
      lastEvaluationAt: now.addingTimeInterval(-SpeechProactivityAdmission.evaluationCooldownSeconds),
      now: now)
    XCTAssertEqual(atCooldown, .evaluate)
  }

  func testAdmissionEvaluatesAFreshUtteranceImmediately() {
    let result = SpeechProactivityAdmission.decides(
      flagEnabled: true,
      conversationActive: false,
      latestUserSlice: slice("where does the deploy script live", isUser: true),
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
