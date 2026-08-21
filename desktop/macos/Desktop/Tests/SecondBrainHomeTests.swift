import XCTest

@testable import Omi_Computer

final class SecondBrainHomeTests: XCTestCase {
  func testReturningHomeLeadsWithAQuestionFromTheUsersContext() {
    let snapshot = SecondBrainHomeSnapshot.compose(
      conversations: 12,
      memories: 34,
      tasks: 5,
      screenCount: 1_200,
      personalizedPrompts: ["What did Priya need from me after our launch review?"],
      onboardingPrompts: [],
      opener: nil,
      contextEvidence: [
        .init(kind: .conversation, text: "Launch review with Priya"),
        .init(kind: .task, text: "Send revised rollout plan"),
      ])

    XCTAssertEqual(snapshot.phase, .ready)
    XCTAssertEqual(snapshot.headline, "What do you want to know?")
    XCTAssertEqual(snapshot.total, 1_251)
    XCTAssertEqual(snapshot.sources.map(\.title), ["Conversations", "Screen", "Memories", "Tasks"])
    XCTAssertEqual(
      snapshot.sources.map(\.detail),
      ["12 conversations", "1,200 screen moments", "34 memories", "5 open tasks"])
    XCTAssertEqual(snapshot.heroPrompt, "What did Priya need from me after our launch review?")
    XCTAssertTrue(snapshot.secondaryPrompts.contains(HomeSuggestionComposer.universalFirstQuestion))
    XCTAssertEqual(snapshot.evidence.map(\.text), ["Launch review with Priya", "Send revised rollout plan"])
  }

  func testPostOnboardingHomeKeepsGreetingAndDoesNotRenderZeroProof() {
    let opener = OnboardingOpenerContent(
      greeting: "Morning, Sam",
      subline: "Two meetings today. I'll be listening.",
      starters: [
        "Prep me for product review",
        "What should I do today?",
        "Prep me for product review",
      ])

    let snapshot = SecondBrainHomeSnapshot.compose(
      conversations: 0,
      memories: 0,
      tasks: 0,
      screenCount: 0,
      personalizedPrompts: [],
      onboardingPrompts: [],
      opener: opener)

    XCTAssertEqual(snapshot.phase, .activation)
    XCTAssertEqual(snapshot.headline, "Morning, Sam.")
    XCTAssertEqual(snapshot.supportingCopy, opener.subline)
    XCTAssertEqual(snapshot.heroPrompt, "Prep me for product review")
    XCTAssertEqual(snapshot.secondaryPrompts.first, "What should I do today?")
    XCTAssertFalse(snapshot.secondaryPrompts.contains("What did I spend my time on this week?"))
    XCTAssertTrue(snapshot.sources.isEmpty)
    XCTAssertFalse(snapshot.sourceSummary.contains("0"))
  }

  func testOnboardingAnswerBecomesAnEphemeralProofReceipt() throws {
    let receipt = try XCTUnwrap(
      OnboardingProofReceipt.setupAnswer(
        "  You are reviewing the launch plan.\nThe open issue is rollout ownership.  "))
    let opener = OnboardingOpenerContent(
      greeting: "Afternoon, Alex",
      subline: "I'm set up and listening.",
      starters: ["What should I do next?"],
      proofReceipt: receipt)

    let snapshot = SecondBrainHomeSnapshot.compose(
      conversations: 0,
      memories: 0,
      tasks: 0,
      screenCount: nil,
      personalizedPrompts: [],
      onboardingPrompts: [],
      opener: opener)

    XCTAssertEqual(snapshot.headline, "You asked. Omi answered.")
    XCTAssertEqual(
      snapshot.proofReceipt?.answerExcerpt,
      "You are reviewing the launch plan. The open issue is rollout ownership.")
    XCTAssertEqual(snapshot.proofReceipt?.sourceLabel, "Answered during your screen demo")
    XCTAssertEqual(snapshot.heroPrompt, "What should I focus on based on what's on my screen?")
  }

  func testProofReceiptIsBoundedAndDoesNotPersistRawWhitespace() throws {
    let raw = String(repeating: "personal context ", count: 30)
    let receipt = try XCTUnwrap(OnboardingProofReceipt.setupAnswer("\n\(raw)\n"))

    XCTAssertLessThanOrEqual(receipt.answerExcerpt.count, OnboardingProofReceipt.maxExcerptLength)
    XCTAssertTrue(receipt.answerExcerpt.hasSuffix("…"))
    XCTAssertFalse(receipt.answerExcerpt.contains("\n"))
    XCTAssertNil(OnboardingProofReceipt.setupAnswer(" \n "))
  }

  func testUnavailableScreenCountIsAnHonestLoadingStateRatherThanAFalseZero() {
    let snapshot = SecondBrainHomeSnapshot.compose(
      conversations: 2,
      memories: 3,
      tasks: 1,
      screenCount: nil,
      personalizedPrompts: [],
      onboardingPrompts: [],
      opener: nil)

    XCTAssertNil(snapshot.total)
    XCTAssertEqual(
      snapshot.sources.first(where: { $0.kind == .screen })?.detail,
      "Screen history isn't ready yet")
    XCTAssertFalse(snapshot.sourceSummary.contains("0"))
  }

  func testBadCountsCannotProduceNegativeOrZeroProof() {
    let snapshot = SecondBrainHomeSnapshot.compose(
      conversations: -4,
      memories: -3,
      tasks: -2,
      screenCount: -1,
      personalizedPrompts: [],
      onboardingPrompts: [],
      opener: nil)

    XCTAssertEqual(snapshot.phase, .gathering)
    XCTAssertEqual(snapshot.total, 0)
    XCTAssertTrue(snapshot.sources.isEmpty)
    XCTAssertFalse(snapshot.sourceSummary.contains("-"))
    XCTAssertFalse(snapshot.sourceSummary.contains("0"))
  }

  func testEvidenceIsCollapsedDeduplicatedAndBounded() {
    let long = String(repeating: "launch ", count: 30)
    let snapshot = SecondBrainHomeSnapshot.compose(
      conversations: 1,
      memories: 1,
      tasks: 1,
      screenCount: 1,
      personalizedPrompts: [],
      onboardingPrompts: [],
      opener: nil,
      contextEvidence: [
        .init(kind: .conversation, text: "  Launch\nreview  "),
        .init(kind: .memory, text: "launch review"),
        .init(kind: .task, text: long),
        .init(kind: .task, text: "Fourth item is intentionally capped out"),
      ])

    XCTAssertEqual(snapshot.evidence.count, 3)
    XCTAssertEqual(snapshot.evidence.first?.text, "Launch review")
    XCTAssertLessThanOrEqual(snapshot.evidence[1].text.count, 96)
    XCTAssertTrue(snapshot.evidence[1].text.hasSuffix("…"))
  }

  func testExistingTranscriptWinsOverOverviewUnlessOnboardingIsHandingOff() {
    XCTAssertFalse(
      SecondBrainHomePresentationPolicy.showsOverview(
        requested: true, hasMessages: true, hasOnboardingOpener: false, isSending: false))
    XCTAssertTrue(
      SecondBrainHomePresentationPolicy.showsOverview(
        requested: true, hasMessages: true, hasOnboardingOpener: true, isSending: false))
    XCTAssertTrue(
      SecondBrainHomePresentationPolicy.showsOverview(
        requested: true, hasMessages: false, hasOnboardingOpener: false, isSending: false))
    XCTAssertFalse(
      SecondBrainHomePresentationPolicy.showsOverview(
        requested: true, hasMessages: false, hasOnboardingOpener: true, isSending: true))
  }

  func testSuggestionNeverOverwritesAComposerDraft() {
    XCTAssertTrue(SecondBrainPromptPolicy.canUseSuggestion(draft: "  "))
    XCTAssertFalse(SecondBrainPromptPolicy.canUseSuggestion(draft: "my own question"))
  }

  func testSearchIsCompactOnlyOnTheRestingAnswerSurface() {
    XCTAssertTrue(HomeSearchPresentationPolicy.isCompact(mode: .answer, isExpanded: false))
    XCTAssertFalse(HomeSearchPresentationPolicy.isCompact(mode: .answer, isExpanded: true))
    XCTAssertFalse(HomeSearchPresentationPolicy.isCompact(mode: .results, isExpanded: false))
  }
}
