import XCTest

@testable import Omi_Computer

/// The gate is the cost contract. `4584c0a9` established that proactive screen analysis
/// must not run when the user will never see the output; these tests pin that every
/// blocking condition short-circuits *before* a model call, and that an idle user (no
/// context switch) costs nothing at all.
final class SuggestionGatePolicyTests: XCTestCase {
  private let now = Date(timeIntervalSince1970: 1_800_000_000)

  private func decide(
    isEnabled: Bool = true,
    isAppExcluded: Bool = false,
    lastEvaluationAt: Date? = nil,
    cooldown: TimeInterval = 180,
    dwell: TimeInterval = 999,
    requiredDwell: TimeInterval = 30,
    evaluationsToday: Int = 0,
    dailyBudget: Int = 40
  ) -> SuggestionGateDecision {
    SuggestionGatePolicy.decide(
      isEnabled: isEnabled,
      isAppExcluded: isAppExcluded,
      now: now,
      lastEvaluationAt: lastEvaluationAt,
      cooldown: cooldown,
      dwell: dwell,
      requiredDwell: requiredDwell,
      evaluationsToday: evaluationsToday,
      dailyBudget: dailyBudget
    )
  }

  func testEvaluatesWhenEverythingIsClear() {
    XCTAssertEqual(decide(), .evaluate)
    XCTAssertTrue(decide().allowsEvaluation)
  }

  func testDisabledAssistantNeverEvaluates() {
    XCTAssertEqual(decide(isEnabled: false), .skippedDisabled)
    XCTAssertFalse(decide(isEnabled: false).allowsEvaluation)
  }

  func testExcludedAppNeverEvaluates() {
    XCTAssertEqual(decide(isAppExcluded: true), .skippedExcludedApp)
  }

  /// Hiding the floating bar is about the bar, not delivery: the gate no longer has a
  /// snooze input at all, so a hidden bar cannot silently mute an hour of nudges the way
  /// "Disable for 2 hours" once did (the compiler now enforces what this test documents).
  func testHiddenBarStillEvaluates() {
    XCTAssertEqual(decide(), .evaluate)
  }

  func testCooldownBlocksUntilItHasFullyElapsed() {
    let justEvaluated = now.addingTimeInterval(-179)
    XCTAssertEqual(decide(lastEvaluationAt: justEvaluated), .skippedCooldown)

    let exactlyElapsed = now.addingTimeInterval(-180)
    XCTAssertEqual(decide(lastEvaluationAt: exactlyElapsed), .evaluate)

    let longAgo = now.addingTimeInterval(-3600)
    XCTAssertEqual(decide(lastEvaluationAt: longAgo), .evaluate)
  }

  /// Disabled must win over every other condition — a disabled assistant should not even
  /// reach the point of reading exclusion lists or cooldown state.
  func testDisabledTakesPrecedenceOverOtherBlockers() {
    let decision = decide(
      isEnabled: false,
      isAppExcluded: true,
      lastEvaluationAt: now
    )
    XCTAssertEqual(decision, .skippedDisabled)
  }

  /// A privacy exclusion must outrank cooldown: "do not look at this app" is a
  /// stronger statement than "not right now".
  func testExclusionTakesPrecedenceOverCooldown() {
    let decision = decide(isAppExcluded: true, lastEvaluationAt: now)
    XCTAssertEqual(decision, .skippedExcludedApp)
  }

  /// Maximum (5) is the "nudge me in seconds" demo mode: 4 s dwell. Everything below —
  /// including Balanced (3) — keeps the deliberate 30 s so ordinary use is unchanged.
  func testDwellIsFourSecondsOnlyAtMaximumLevel() {
    XCTAssertEqual(SuggestionGatePolicy.requiredDwell(frequencyLevel: 5), 4)
    XCTAssertEqual(SuggestionGatePolicy.requiredDwell(frequencyLevel: 4), 30)
    XCTAssertEqual(SuggestionGatePolicy.requiredDwell(frequencyLevel: 3), 30)
    XCTAssertEqual(SuggestionGatePolicy.requiredDwell(frequencyLevel: 0), 30)
  }

  /// Maximum caps the between-nudge cooldown at 30 s; other levels keep the user's
  /// configured value (180 s default) untouched.
  func testCooldownCapsAtTwentySecondsOnlyAtMaximumLevel() {
    XCTAssertEqual(SuggestionGatePolicy.cooldown(base: 180, frequencyLevel: 5), 20)
    XCTAssertEqual(SuggestionGatePolicy.cooldown(base: 20, frequencyLevel: 5), 20)
    XCTAssertEqual(SuggestionGatePolicy.cooldown(base: 180, frequencyLevel: 4), 180)
    XCTAssertEqual(SuggestionGatePolicy.cooldown(base: 180, frequencyLevel: 3), 180)
  }

  func testFirstEverEvaluationIsNotBlockedByAbsentHistory() {
    XCTAssertEqual(decide(lastEvaluationAt: nil, cooldown: 86400), .evaluate)
  }

  // MARK: - Cost gates

  /// Switching apps is not a request for advice — people do it hundreds of times a day.
  func testPassingThroughAWindowDoesNotEvaluate() {
    XCTAssertEqual(decide(dwell: 0), .skippedDwell)
    XCTAssertEqual(decide(dwell: 29.9), .skippedDwell)
    XCTAssertEqual(decide(dwell: 30), .evaluate)
  }

  /// Dwell must outrank cooldown: a context the user has not settled in should not consume
  /// the cooldown slot that a context they are actually working in would use.
  func testDwellIsCheckedBeforeCooldown() {
    XCTAssertEqual(decide(lastEvaluationAt: now, dwell: 0), .skippedDwell)
  }

  func testDailyBudgetCapsSpendRegardlessOfActivity() {
    XCTAssertEqual(decide(evaluationsToday: 39, dailyBudget: 40), .evaluate)
    XCTAssertEqual(decide(evaluationsToday: 40, dailyBudget: 40), .skippedDailyBudget)
    XCTAssertEqual(decide(evaluationsToday: 400, dailyBudget: 40), .skippedDailyBudget)
  }

  /// The budget is the last gate: a blocked-for-another-reason context must not be
  /// reported as budget-exhausted, or the logs mislead about why nothing fires.
  func testEarlierGatesReportTheirOwnReasonAtBudgetExhaustion() {
    XCTAssertEqual(decide(isEnabled: false, evaluationsToday: 999), .skippedDisabled)
    XCTAssertEqual(decide(isAppExcluded: true, evaluationsToday: 999), .skippedExcludedApp)
    XCTAssertEqual(decide(dwell: 0, evaluationsToday: 999), .skippedDwell)
  }
}

/// The ceiling has to be a real daily number, not a counter that only resets on relaunch.
final class SuggestionDailyBudgetTests: XCTestCase {
  private let noon = Date(timeIntervalSince1970: 1_800_000_000)

  func testCountAccumulatesWithinADay() {
    var budget = SuggestionDailyBudget()
    XCTAssertEqual(budget.countToday(now: noon), 0)
    budget.recordEvaluation(now: noon)
    budget.recordEvaluation(now: noon.addingTimeInterval(60))
    XCTAssertEqual(budget.countToday(now: noon.addingTimeInterval(120)), 2)
  }

  func testCountResetsOnTheNextCalendarDay() {
    var budget = SuggestionDailyBudget()
    budget.recordEvaluation(now: noon)
    budget.recordEvaluation(now: noon)
    XCTAssertEqual(budget.countToday(now: noon), 2)

    let tomorrow = noon.addingTimeInterval(24 * 60 * 60)
    XCTAssertEqual(budget.countToday(now: tomorrow), 0, "budget must reset, not carry over")

    budget.recordEvaluation(now: tomorrow)
    XCTAssertEqual(budget.countToday(now: tomorrow), 1)
  }

  func testRecordingAcrossADayBoundaryStartsTheNewDayAtOne() {
    var budget = SuggestionDailyBudget()
    budget.recordEvaluation(now: noon)
    budget.recordEvaluation(now: noon.addingTimeInterval(24 * 60 * 60))
    XCTAssertEqual(budget.countToday(now: noon.addingTimeInterval(24 * 60 * 60)), 1)
  }
}

/// Gemini bills images as 768px tiles, so resolution is money.
final class SuggestionFramePreviewTests: XCTestCase {
  private func jpeg(width: Int, height: Int) throws -> Data {
    let context = try XCTUnwrap(
      CGContext(
        data: nil, width: width, height: height, bitsPerComponent: 8, bytesPerRow: 0,
        space: CGColorSpaceCreateDeviceRGB(), bitmapInfo: CGImageAlphaInfo.noneSkipLast.rawValue))
    context.setFillColor(CGColor(red: 0.4, green: 0.6, blue: 0.8, alpha: 1))
    context.fill(CGRect(x: 0, y: 0, width: width, height: height))
    let image = try XCTUnwrap(context.makeImage())
    let out = NSMutableData()
    let dest = try XCTUnwrap(
      CGImageDestinationCreateWithData(out, "public.jpeg" as CFString, 1, nil))
    CGImageDestinationAddImage(dest, image, nil)
    XCTAssertTrue(CGImageDestinationFinalize(dest))
    return out as Data
  }

  private func pixelSize(of data: Data) throws -> (width: Int, height: Int) {
    let source = try XCTUnwrap(CGImageSourceCreateWithData(data as CFData, nil))
    let image = try XCTUnwrap(CGImageSourceCreateImageAtIndex(source, 0, nil))
    return (image.width, image.height)
  }

  func testOversizedFrameIsDownscaledToTheTileBudget() throws {
    let large = try jpeg(width: 3000, height: 1950)
    let preview = SuggestionFramePreview.downscaledJPEG(from: large)

    XCTAssertEqual(try pixelSize(of: preview).width, SuggestionFramePreview.maxWidth)
    XCTAssertLessThan(preview.count, large.count, "downscaling must actually shrink the payload")
  }

  func testAspectRatioIsPreserved() throws {
    let preview = SuggestionFramePreview.downscaledJPEG(from: try jpeg(width: 3000, height: 1500))
    let size = try pixelSize(of: preview)
    XCTAssertEqual(Double(size.width) / Double(size.height), 2.0, accuracy: 0.02)
  }

  func testAlreadySmallFrameIsPassedThroughUntouched() throws {
    let small = try jpeg(width: 800, height: 600)
    XCTAssertEqual(SuggestionFramePreview.downscaledJPEG(from: small), small)
  }

  /// A frame we cannot decode must still be sent — the suggestion is worth more than the
  /// saving, and silently dropping it would look like the feature is broken.
  func testUndecodableDataIsReturnedUnchangedRatherThanDropped() {
    let garbage = Data([0x00, 0x01, 0x02, 0x03])
    XCTAssertEqual(SuggestionFramePreview.downscaledJPEG(from: garbage), garbage)
  }
}

/// Repeat suppression. The model rephrases the same idea across context switches, so exact
/// string matching would let obvious duplicates through and re-annoy the user.
final class SuggestionDeduplicationTests: XCTestCase {
  func testIdenticalSuggestionIsDuplicate() {
    let recent = ["You told Sarah you'd send the deck Friday"]
    XCTAssertTrue(
      SuggestionDeduplication.isDuplicate("You told Sarah you'd send the deck Friday", of: recent)
    )
  }

  func testRewordedSuggestionIsStillDuplicate() {
    let recent = ["You told Sarah you'd send the deck Friday"]
    XCTAssertTrue(
      SuggestionDeduplication.isDuplicate("You told Sarah that you would send the deck on Friday", of: recent)
    )
  }

  func testUnrelatedSuggestionIsNotDuplicate() {
    let recent = ["You told Sarah you'd send the deck Friday"]
    XCTAssertFalse(
      SuggestionDeduplication.isDuplicate("Sensitive credentials visible in terminal", of: recent)
    )
  }

  func testEmptyHistoryNeverSuppresses() {
    XCTAssertFalse(SuggestionDeduplication.isDuplicate("Anything at all", of: []))
  }

  func testCasingAndPunctuationDoNotDefeatSuppression() {
    let recent = ["Sensitive credentials visible in terminal — mask before sharing"]
    XCTAssertTrue(
      SuggestionDeduplication.isDuplicate("SENSITIVE CREDENTIALS VISIBLE IN TERMINAL: mask before sharing!", of: recent)
    )
  }

  func testShortTokensAreIgnoredSoStopwordsDoNotInflateSimilarity() {
    // These share only short filler words; they must not read as the same suggestion.
    XCTAssertFalse(
      SuggestionDeduplication.isDuplicate("You are on the wrong branch", of: ["You are in the old tab"])
    )
  }

  func testSimilarityIsBoundedAndSymmetric() {
    let a = "You stashed changes 2 hours ago"
    let b = "You stashed changes two hours ago"
    XCTAssertEqual(SuggestionDeduplication.similarity(a, b), SuggestionDeduplication.similarity(b, a))
    XCTAssertLessThanOrEqual(SuggestionDeduplication.similarity(a, b), 1.0)
    XCTAssertEqual(SuggestionDeduplication.similarity(a, a), 1.0)
  }

  func testEmptyStringsScoreZeroRatherThanCrashing() {
    XCTAssertEqual(SuggestionDeduplication.similarity("", "anything"), 0)
    XCTAssertEqual(SuggestionDeduplication.similarity("", ""), 0)
  }
}

/// Field regression, beta 0.12.172: "Lead the call for Nik Shevchenko — it's due today"
/// was delivered three times in quick succession at Maximum frequency. Dedup ran every
/// time, but the window it compared against had been trimmed to Maximum's zero screen-nudge
/// depth right after each delivery, so the identical task nudge escaped as "novel" on every
/// cycle. These tests drive the same deliver → remember → compare loop the assistant runs.
final class SuggestionDedupWindowTests: XCTestCase {
  private let taskNudge = "Lead the call for Nik Shevchenko — it's due today"

  /// One pass of the delivery loop: fire if not a duplicate, then remember what fired.
  private func deliver(
    _ text: String,
    category: SuggestionCategory,
    window: inout [SuggestionDeduplication.Remembered],
    level: Int
  ) -> Bool {
    guard !SuggestionDeduplication.isDuplicate(text, of: window.map(\.text)) else { return false }
    window = SuggestionDeduplication.remembering(
      .init(text: text, category: category), in: window, frequencyLevel: level)
    return true
  }

  /// The reproduction: three identical due-today task nudges, ~30s apart, at Maximum.
  /// Before category-aware retention every one of them fired.
  func testIdenticalTaskNudgeFiresOnlyOnceAtMaximum() {
    var window: [SuggestionDeduplication.Remembered] = []
    var fired = 0
    for _ in 0..<3 where deliver(taskNudge, category: .commitment, window: &window, level: 5) {
      fired += 1
    }
    XCTAssertEqual(fired, 1, "the same task must not re-fire within its dedup window")
  }

  /// A genuinely different task is not collateral damage of the repeat suppression.
  func testDifferentTaskNudgeStillFiresAtMaximum() {
    var window: [SuggestionDeduplication.Remembered] = []
    XCTAssertTrue(deliver(taskNudge, category: .commitment, window: &window, level: 5))
    XCTAssertTrue(
      deliver(
        "Send the budget review draft to Adam — due tomorrow",
        category: .commitment, window: &window, level: 5))
  }

  /// Maximum's screen-nudge cadence is by design: staying on the feed keeps producing
  /// repeats, so screen nudges must stay unremembered there — even delivered right after
  /// a task nudge, which must itself stay remembered.
  func testMaximumStillRepeatsScreenNudgesAndKeepsTaskMemoryIntact() {
    var window: [SuggestionDeduplication.Remembered] = []
    XCTAssertTrue(deliver(taskNudge, category: .commitment, window: &window, level: 5))
    let screenNudge = "Twenty minutes on the feed — the launch doc is still open"
    XCTAssertTrue(deliver(screenNudge, category: .opportunity, window: &window, level: 5))
    XCTAssertTrue(
      deliver(screenNudge, category: .opportunity, window: &window, level: 5),
      "Maximum's repeat cadence for screen nudges is the level's contract")
    XCTAssertFalse(
      deliver(taskNudge, category: .commitment, window: &window, level: 5),
      "screen-nudge deliveries must not evict the remembered task")
  }

  /// Calm levels keep the long-standing 10-deep window for every category.
  func testCalmLevelsRememberEveryCategory() {
    for level in [0, 1, 2, 3, 4] {
      var window: [SuggestionDeduplication.Remembered] = []
      XCTAssertTrue(deliver(taskNudge, category: .commitment, window: &window, level: level))
      XCTAssertFalse(deliver(taskNudge, category: .commitment, window: &window, level: level))
      let screenNudge = "Twenty minutes on the feed — the launch doc is still open"
      XCTAssertTrue(deliver(screenNudge, category: .opportunity, window: &window, level: level))
      XCTAssertFalse(deliver(screenNudge, category: .opportunity, window: &window, level: level))
    }
  }

  /// The task window is still a window: the eleventh distinct task evicts the first.
  func testCommitmentMemoryStaysBounded() {
    var window: [SuggestionDeduplication.Remembered] = []
    XCTAssertTrue(deliver(taskNudge, category: .commitment, window: &window, level: 5))
    let distinctTasks = [
      "Review the quarterly budget spreadsheet before finance sync",
      "Email Sarah the onboarding checklist",
      "Renew the office wifi router contract",
      "Book flights for the Denver conference",
      "Fix the login crash on older phones",
      "Water the plants and clean the desk",
      "Draft a blog post about privacy features",
      "Schedule the dentist appointment for Thursday",
      "Upload the podcast episode artwork",
      "Pay the contractor invoice from July",
    ]
    for task in distinctTasks {
      XCTAssertTrue(deliver(task, category: .commitment, window: &window, level: 5))
    }
    XCTAssertEqual(window.count, 10)
    XCTAssertFalse(window.contains(.init(text: taskNudge, category: .commitment)))
  }
}

/// Regression: a live run against a Safari window titled `Start Page (Private Browsing)`
/// raised `fts5: syntax error near "("` and silently dropped screen-history grounding.
/// `RewindDatabase.search` does not sanitize its query, so the caller must.
final class SuggestionSearchTermTests: XCTestCase {
  func testParenthesesAreStrippedSoFTS5DoesNotRaise() {
    XCTAssertEqual(
      SuggestionSearchTerm.sanitize("Start Page (Private Browsing)"),
      "Start Page Private Browsing"
    )
  }

  func testFTS5OperatorCharactersAreRemoved() {
    for raw in ["a \"quoted\" title", "title: subtitle", "foo* AND bar", "a-b^c", "x OR (y)"] {
      let sanitized = SuggestionSearchTerm.sanitize(raw)
      for forbidden in ["(", ")", "\"", ":", "*", "^", "-"] {
        XCTAssertFalse(
          sanitized.contains(forbidden),
          "sanitized \"\(sanitized)\" from \"\(raw)\" still contains \(forbidden)"
        )
      }
    }
  }

  func testMeaningfulTokensSurvive() {
    XCTAssertEqual(SuggestionSearchTerm.sanitize("Sarah Chen — Messages"), "Sarah Chen Messages")
    XCTAssertEqual(SuggestionSearchTerm.sanitize("PR #10581: fix the thing"), "PR 10581 fix the thing")
  }

  func testCollapsesWhitespaceRatherThanLeavingEmptyTokens() {
    XCTAssertEqual(SuggestionSearchTerm.sanitize("a   ---   b"), "a b")
    XCTAssertEqual(SuggestionSearchTerm.sanitize("((()))"), "")
    XCTAssertEqual(SuggestionSearchTerm.sanitize(""), "")
  }
}

/// The grounding bundle is what makes a suggestion carry information the user does not
/// already have. An empty section must be omitted entirely rather than rendered as an
/// encouraging-looking but vacuous heading the model might try to fill.
final class SuggestionGroundingTests: XCTestCase {
  func testEmptyGroundingRendersNothing() {
    let grounding = SuggestionGrounding()
    XCTAssertTrue(grounding.isEmpty)
    XCTAssertEqual(grounding.promptSections(), "")
  }

  func testOnlyPopulatedSectionsAppear() {
    var grounding = SuggestionGrounding()
    grounding.openCommitments = ["Send Sarah the deck"]

    let rendered = grounding.promptSections()
    XCTAssertTrue(rendered.contains("OPEN COMMITMENTS"))
    XCTAssertTrue(rendered.contains("Send Sarah the deck"))
    XCTAssertFalse(rendered.contains("WHAT OMI KNOWS"))
    XCTAssertFalse(rendered.contains("RELATED THINGS"))
    XCTAssertFalse(grounding.isEmpty)
  }

  func testAllSectionsRenderWhenPopulated() {
    var grounding = SuggestionGrounding()
    grounding.memories = ["Sarah leads the platform team"]
    grounding.openCommitments = ["Send Sarah the deck"]
    grounding.relatedScreens = ["Jul 24 09:12 · Slack — Sarah Chen: deck?"]

    let rendered = grounding.promptSections()
    XCTAssertTrue(rendered.contains("WHAT OMI KNOWS ABOUT THE USER"))
    XCTAssertTrue(rendered.contains("OPEN COMMITMENTS"))
    XCTAssertTrue(rendered.contains("RELATED THINGS THE USER SAW RECENTLY"))
  }
}

/// The default prompt is shipped data: the daily-task nudge (distracted screen + tasks
/// due today → name the task) is a product behavior that lives entirely in this text.
/// This is a data-contract tripwire, not behavioral coverage of the model — it pins the
/// prompt's contract to the grounding section header the assistant actually renders, so
/// a prompt edit cannot silently retire the nudge or orphan it from its data source.
final class SuggestionPromptContractTests: XCTestCase {
  @MainActor
  func testDefaultPromptCarriesTheDailyTaskNudgeContract() {
    let prompt = SuggestionAssistantSettings.defaultAnalysisPrompt
    XCTAssertTrue(prompt.contains("daily-task nudge"))
    // The nudge is keyed to the exact section name promptSections() emits.
    XCTAssertTrue(prompt.contains("OPEN COMMITMENTS"))
    var grounding = SuggestionGrounding()
    grounding.openCommitments = ["Send that email to Bob"]
    XCTAssertTrue(grounding.promptSections().contains("OPEN COMMITMENTS"))
  }
}

/// The card Omi delivered at 90% on 2026-08-10: "You still haven't sent the investor update
/// to Bob." Bob existed only in the prompt's worked examples — the user had no such task.
/// A fabricated commitment clears the confidence bar (it scores *higher* than grounded
/// ones) and clears dedup (it is novel), so the only thing that can catch it is asking
/// whether the work it names is in the grounding at all.
final class SuggestionCommitmentGuardTests: XCTestCase {
  /// The user's real open tasks at the time of the incident.
  private let realCommitments = [
    "Exchange weekly tasks with accountability partner and update the shared Google Doc tracker",
    "Record the Instagram demo video walkthrough",
    "Follow up on the Figma comments from Sarah (due 2026-08-10)",
  ]

  private func isGrounded(
    _ suggestion: String,
    category: SuggestionCategory = .commitment,
    commitments: [String]? = nil
  ) -> Bool {
    SuggestionCommitmentGuard.isGrounded(
      suggestion: suggestion,
      category: category,
      openCommitments: commitments ?? realCommitments
    )
  }

  func testRejectsTheFabricatedInvestorUpdateNudge() {
    XCTAssertFalse(isGrounded("You still haven't sent the investor update to Bob."))
  }

  func testRejectsEveryNameLiftedFromThePromptExamples() {
    XCTAssertFalse(isGrounded("You still haven't sent that email to Bob — good moment to knock it out"))
    XCTAssertFalse(isGrounded("You told Sarah you'd send the deck Friday — this is that thread"))
  }

  func testAdmitsTheGroundedNudgeDeliveredInTheSameSession() {
    XCTAssertTrue(isGrounded("Follow up on Sarah's Figma comments (due 2026-08-10)"))
  }

  /// A nudge names the task in fewer words than the task itself, so coverage is measured
  /// against the commitment rather than requiring the two to look alike.
  func testAdmitsAShorterParaphraseOfARealCommitment() {
    XCTAssertTrue(isGrounded("Still owe the Instagram demo walkthrough"))
  }

  func testEmptyCommitmentsRejectEveryCommitmentNudge() {
    XCTAssertFalse(isGrounded("You still haven't sent the investor update to Bob.", commitments: []))
    XCTAssertFalse(isGrounded("Follow up on Sarah's Figma comments", commitments: []))
  }

  /// Only `commitment` claims work Omi holds; the rest describe the screen, which this
  /// guard cannot see and must not veto.
  func testOtherCategoriesArePassedThrough() {
    for category in [SuggestionCategory.mistake, .opportunity, .connection, .other] {
      XCTAssertTrue(
        isGrounded("Sensitive credentials visible in terminal — mask before sharing", category: category),
        "category \(category) must not be gated on commitments"
      )
    }
  }

  /// A long commitment is not a higher bar. This is Nik's real task, ten content words
  /// long; a concise nudge naming the distinctive part of it must be admitted, and under
  /// pure proportional coverage it was not.
  func testConciseNudgeForALongCommitmentIsAdmitted() {
    let long = ["Exchange weekly tasks with accountability partner and update the shared Google Doc tracker"]
    XCTAssertTrue(isGrounded("Still owe the weekly exchange with your accountability partner", commitments: long))
    XCTAssertTrue(isGrounded("The Google Doc tracker is still not updated", commitments: long))
  }

  /// Length must not be gameable in the other direction either: sharing only doing-words
  /// with a long task is still not a reference to it.
  func testGenericOverlapWithALongCommitmentIsStillRejected() {
    let long = ["Exchange weekly tasks with accountability partner and update the shared Google Doc tracker"]
    XCTAssertFalse(isGrounded("You should send an update", commitments: long))
  }

  /// "send" and "update" appear in most commitments. Echoing a commitment's two most
  /// generic words while dropping everything that identifies it — quarterly, board, deck,
  /// investors — is not a reference to it.
  func testGenericVerbsAloneDoNotVouchForACommitment() {
    XCTAssertFalse(
      isGrounded(
        "You still need to send the update",
        commitments: ["Send the quarterly board update deck to the investors"]
      )
    )
  }
}

/// On 2026-08-10 six consecutive TikTok contexts lasted 6s or less — not because the user
/// left, but because TikTok rewrites the tab title on every video and each rewrite counted
/// as a fresh context. Dwell never reached 30s, so every decision logged `skippedDwell` and
/// the distraction nudge could not fire on the one activity it was written for.
final class SuggestionDwellAnchorTests: XCTestCase {
  private let start = Date(timeIntervalSince1970: 1_800_000_000)

  private func anchor(
    current: Date?,
    fromApp: String?,
    fromTitle: String?,
    toApp: String,
    toTitle: String?,
    at offset: TimeInterval
  ) -> Date {
    SuggestionDwellAnchor.anchor(
      current: current,
      currentApp: fromApp,
      currentWindowTitle: fromTitle,
      newApp: toApp,
      newWindowTitle: toTitle,
      now: start.addingTimeInterval(offset)
    )
  }

  func testTitleChurnWithinOneSittingKeepsTheClockRunning() {
    let a = anchor(
      current: start, fromApp: "Google Chrome", fromTitle: "TikTok - Make Your Day",
      toApp: "Google Chrome", toTitle: "Watch trending videos for you | TikTok 🔊", at: 3)
    XCTAssertEqual(a, start)
  }

  /// The real trace: title churn every few seconds, still one sitting. Pre-fix dwell here
  /// was 3s; it must now be the full 33s.
  func testDwellSurvivesRepeatedTitleChurnAndClearsTheGate() {
    var current = start
    var title = "TikTok - Make Your Day"
    for second in stride(from: 3, through: 33, by: 3) {
      let next = "(\(second)) TikTok - Make Your Day 🔊"
      current = anchor(
        current: current, fromApp: "Google Chrome", fromTitle: title,
        toApp: "Google Chrome", toTitle: next, at: TimeInterval(second))
      title = next
    }
    let dwell = start.addingTimeInterval(33).timeIntervalSince(current)
    XCTAssertEqual(dwell, 33)
    XCTAssertGreaterThanOrEqual(dwell, 30, "33s of unbroken TikTok must clear the 30s bar")
  }

  /// The regression the reviewer caught: ten minutes on a work page then one tab change to
  /// a feed must NOT inherit that dwell and fire immediately.
  func testSwitchingToADifferentPageInTheSameAppRestartsTheClock() {
    let switched = anchor(
      current: start, fromApp: "Google Chrome",
      fromTitle: "BasedHardware/omi: AI wearable — pull requests",
      toApp: "Google Chrome", toTitle: "TikTok - Make Your Day", at: 600)
    XCTAssertEqual(
      switched, start.addingTimeInterval(600),
      "a work page and a feed are different contexts; dwell must not carry over")
  }

  func testSwitchingAppsRestartsTheClock() {
    let switched = anchor(
      current: start, fromApp: "Google Chrome", fromTitle: "TikTok - Make Your Day",
      toApp: "Warp", toTitle: "zsh", at: 20)
    XCTAssertEqual(switched, start.addingTimeInterval(20))
  }

  /// After an evaluation consumes the pending context, the next switch starts fresh.
  func testFirstSwitchAfterAnEvaluationAnchorsToNow() {
    let a = anchor(
      current: nil, fromApp: nil, fromTitle: nil,
      toApp: "Google Chrome", toTitle: "TikTok - Make Your Day", at: 0)
    XCTAssertEqual(a, start)
  }

  /// An unreadable title is not evidence the sitting ended.
  func testUnreadableTitleDoesNotEndASitting() {
    XCTAssertTrue(SuggestionDwellAnchor.isSameContext("TikTok - Make Your Day", nil))
    XCTAssertTrue(SuggestionDwellAnchor.isSameContext(nil, nil))
  }

  func testContextIdentityIgnoresGenericChrome() {
    // "New Tab" carries no identity, so it must not vouch for a match.
    XCTAssertFalse(
      SuggestionDwellAnchor.isSameContext("New Tab", "TikTok - Make Your Day"),
      "a blank new tab is not the same place as a feed")
    XCTAssertTrue(
      SuggestionDwellAnchor.isSameContext(
        "Peter Steinberger — YouTube", "Rick Astley — YouTube"))
  }
}

/// "call mom" was stored as 2026-08-11 03:59 UTC — 23:59 tonight in EDT — and the raw
/// `ISO8601DateFormatter` rendered it as *tomorrow*. The model scored a due-today task as
/// not-yet-urgent (80%), it fell under the 85% bar, and Nik got nothing. Local calendar
/// days, not UTC.
final class SuggestionDueDescriptionTests: XCTestCase {
  private func calendar() throws -> Calendar {
    var c = Calendar(identifier: .gregorian)
    c.timeZone = try XCTUnwrap(TimeZone(identifier: "America/New_York"))
    return c
  }

  private func date(_ iso: String) throws -> Date {
    let f = ISO8601DateFormatter()
    f.formatOptions = [.withInternetDateTime]
    return try XCTUnwrap(f.date(from: iso))
  }

  func testLateEveningTaskIsDueTodayNotTomorrow() throws {
    // 2026-08-11T03:59Z == 2026-08-10 23:59 EDT
    let due = try date("2026-08-11T03:59:00Z")
    let now = try date("2026-08-10T23:18:00Z")  // 19:18 EDT, when Nik was on TikTok
    XCTAssertEqual(
      SuggestionDueDescription.phrase(for: due, now: now, calendar: try calendar()),
      "due today"
    )
  }

  func testTomorrowIsStillTomorrow() throws {
    // 2026-08-11T15:00Z == 2026-08-11 11:00 EDT — genuinely the next calendar day.
    let due = try date("2026-08-11T15:00:00Z")
    let now = try date("2026-08-10T23:18:00Z")
    XCTAssertEqual(
      SuggestionDueDescription.phrase(for: due, now: now, calendar: try calendar()),
      "due tomorrow"
    )
  }

  func testFurtherOutCountsDays() throws {
    let due = try date("2026-08-12T15:00:00Z")
    let now = try date("2026-08-10T23:18:00Z")
    XCTAssertEqual(
      SuggestionDueDescription.phrase(for: due, now: now, calendar: try calendar()),
      "due in 2 days"
    )
  }

  func testOverdueReadsAsOverdue() throws {
    let now = try date("2026-08-10T23:18:00Z")
    XCTAssertEqual(
      SuggestionDueDescription.phrase(for: try date("2026-08-09T15:00:00Z"), now: now, calendar: try calendar()),
      "overdue by a day"
    )
    XCTAssertEqual(
      SuggestionDueDescription.phrase(for: try date("2026-07-24T04:00:00Z"), now: now, calendar: try calendar()),
      "overdue by 17 days"
    )
  }

  /// The phrase is what the model quotes, so it must never contain a machine date.
  func testPhraseNeverContainsAnISODate() throws {
    let now = try date("2026-08-10T23:18:00Z")
    for iso in ["2026-08-11T03:59:00Z", "2026-08-11T15:00:00Z", "2026-07-24T04:00:00Z"] {
      let phrase = SuggestionDueDescription.phrase(for: try date(iso), now: now, calendar: try calendar())
      XCTAssertFalse(phrase.contains("2026"), "\(phrase) leaks a machine date into the card")
      XCTAssertFalse(phrase.contains("-"), "\(phrase) leaks a machine date into the card")
    }
  }
}

/// "The model produced a suggestion" and "the user saw a card" are different claims. The
/// first version of the automation probe reported `produced` after calling delivery and
/// never observed the result, so a card silently dropped by the confidence bar, dedup, or
/// the commitment guard still read as a working delivery path.
final class SuggestionDeliveryPolicyTests: XCTestCase {
  private func decide(
    hasOwner: Bool = true,
    confidence: Double = 0.9,
    threshold: Double = 0.85,
    isDuplicate: Bool = false,
    isGroundedCommitment: Bool = true
  ) -> SuggestionAssistantTelemetry.DeliveryOutcome {
    SuggestionDeliveryPolicy.decide(
      hasOwner: hasOwner,
      confidence: confidence,
      threshold: threshold,
      isDuplicate: isDuplicate,
      isGroundedCommitment: isGroundedCommitment
    )
  }

  func testDeliversWhenEveryFilterPasses() {
    XCTAssertEqual(decide(), .delivered)
  }

  func testEachFilterIsReportedDistinctly() {
    XCTAssertEqual(decide(hasOwner: false), .rejectedOwner)
    XCTAssertEqual(decide(confidence: 0.80), .filteredLowConfidence)
    XCTAssertEqual(decide(isDuplicate: true), .filteredDuplicate)
    XCTAssertEqual(decide(isGroundedCommitment: false), .filteredUngroundedCommitment)
  }

  /// The real 80% "call parents" card, and the real 95% ungrounded tally: neither reached
  /// Nik, and neither may be reported as delivered.
  func testRealWorldSuppressionsAreNotDelivered() {
    XCTAssertNotEqual(decide(confidence: 0.80), .delivered)
    XCTAssertNotEqual(decide(confidence: 0.95, isGroundedCommitment: false), .delivered)
  }

  func testThresholdBoundaryDelivers() {
    XCTAssertEqual(decide(confidence: 0.85, threshold: 0.85), .delivered)
    XCTAssertEqual(decide(confidence: 0.8499, threshold: 0.85), .filteredLowConfidence)
  }

  /// Owner rejection outranks everything: a card must never land on the wrong account, even
  /// if it would otherwise have been a perfect suggestion.
  func testOwnerRejectionOutranksOtherFilters() {
    XCTAssertEqual(
      decide(hasOwner: false, confidence: 0.2, isDuplicate: true, isGroundedCommitment: false),
      .rejectedOwner
    )
  }
}

/// Goals are personal. `APIClient.getGoals()` documents that its short-lived shared cache
/// is NOT owner-validated, so an unsnapshotted fetch can return the *previous* account's
/// goals — which would then sit in the assistant's 10-minute cache and be pasted into the
/// next owner's prompt. These pin the capture/pass/validate contract at the authority
/// level: a snapshot taken before an account switch must not validate after it.
final class SuggestionGoalOwnerScopingTests: XCTestCase {
  private let authority = RuntimeOwnerAuthorizationAuthority.shared

  private func signIn(_ owner: String) {
    authority.beginTransition()
    authority.endTransition(ownerID: owner)
  }

  func testSnapshotFromPreviousOwnerDoesNotValidateAfterSwitch() throws {
    signIn("owner-a")
    let snapshot = try XCTUnwrap(authority.capture(ownerID: "owner-a", expectedOwnerID: nil))
    XCTAssertTrue(authority.isCurrent(snapshot, ownerID: "owner-a"))

    signIn("owner-b")
    XCTAssertFalse(
      authority.isCurrent(snapshot, ownerID: "owner-b"),
      "goals fetched as owner-a must be dropped once owner-b is signed in"
    )
  }

  /// Mid-transition there is no owner to attribute a fetch to, so nothing may be cached.
  func testNoSnapshotIsIssuedDuringATransition() {
    signIn("owner-a")
    authority.beginTransition()
    XCTAssertNil(
      authority.capture(ownerID: nil, expectedOwnerID: nil),
      "a goal fetch must not start while ownership is in flight"
    )
    authority.endTransition(ownerID: "owner-a")
  }

  /// Re-signing the same account still advances the generation, so a snapshot straddling
  /// the boundary is stale even though the owner id is unchanged.
  func testSameOwnerReSignInvalidatesEarlierSnapshots() throws {
    signIn("owner-a")
    let snapshot = try XCTUnwrap(authority.capture(ownerID: "owner-a", expectedOwnerID: nil))
    signIn("owner-a")
    XCTAssertFalse(authority.isCurrent(snapshot, ownerID: "owner-a"))
  }
}

/// The automation probe falls back to capturing the active window when no frame is pending.
/// `latestCapturedFrame` is nil whenever the user is moving around — but it is *also* nil
/// precisely when the frontmost app is privacy-excluded, because the capture gate refuses
/// those. Without an exclusion check the probe would photograph exactly the apps the user
/// told Omi never to look at and send them to a model.
@MainActor
final class SuggestionProbePrivacyTests: XCTestCase {
  /// Exclusions live in shared settings, so each test restores what it found. Done inline
  /// rather than in setUp/tearDown, which are nonisolated and cannot touch MainActor state.
  private func withExclusions(_ apps: Set<String>, _ body: () -> Void) {
    let saved = RewindSettings.shared.excludedApps
    defer { RewindSettings.shared.excludedApps = saved }
    RewindSettings.shared.excludedApps = apps
    body()
  }

  func testExcludedAppIsRefusedByTheProbePredicate() {
    withExclusions(["1Password"]) {
      XCTAssertTrue(
        SuggestionProbePrivacy.isExcluded("1Password"),
        "the probe must not capture an app the user excluded from recording")
    }
  }

  func testNonExcludedAppIsAllowed() {
    withExclusions(["1Password"]) {
      XCTAssertFalse(SuggestionProbePrivacy.isExcluded("Google Chrome"))
    }
  }

  /// Exclusion is exact-name, so the predicate must not be fooled by a near-miss either way.
  func testExclusionIsExactName() {
    withExclusions(["Messages"]) {
      XCTAssertTrue(SuggestionProbePrivacy.isExcluded("Messages"))
      XCTAssertFalse(SuggestionProbePrivacy.isExcluded("Messages Beta"))
    }
  }
}

/// Capturing is async, so checking exclusions only before the shutter leaves a window in
/// which the user can cmd-tab into an excluded app and its pixels come back anyway. Both
/// ends must be clear.
final class SuggestionProbeCaptureRaceTests: XCTestCase {
  private func allows(before: String?, after: String?, excluded: Set<String> = ["1Password"]) -> Bool {
    SuggestionProbePrivacy.allowsCapture(
      before: before, after: after, isExcluded: { excluded.contains($0) })
  }

  func testAllowsWhenBothEndsAreTheSameAllowedApp() {
    XCTAssertTrue(allows(before: "Google Chrome", after: "Google Chrome"))
  }

  func testRefusesWhenTheAppWasExcludedBeforeTheCapture() {
    XCTAssertFalse(allows(before: "1Password", after: "1Password"))
  }

  /// The race the reviewer caught: allowed at the shutter, excluded by the time the pixels
  /// arrived.
  func testRefusesWhenAnExcludedAppBecameFrontmostDuringTheCapture() {
    XCTAssertFalse(allows(before: "Google Chrome", after: "1Password"))
  }

  /// Even between two permitted apps, a switch mid-capture means the frame cannot be
  /// attributed with confidence — and an unattributable frame must not reach a model.
  func testRefusesWhenTheAppChangedMidCaptureEvenIfBothAreAllowed() {
    XCTAssertFalse(allows(before: "Google Chrome", after: "Warp"))
  }

  /// The flicker the window-ID binding exists for: allowed at both ends, excluded in the
  /// middle. An app-name comparison cannot see this, which is why the probe captures the
  /// window ID it authorised rather than "whatever is active now" — this test pins that the
  /// before/after check alone is NOT treated as sufficient.
  func testBeforeAfterCheckAloneCannotSeeAnAllowedExcludedAllowedFlicker() {
    // Both observations say Chrome; an excluded app was frontmost only between them.
    XCTAssertTrue(
      allows(before: "Google Chrome", after: "Google Chrome"),
      "the app-name check passes here by construction — the capture must therefore be bound "
        + "to the pre-authorised window ID, which is what actually prevents the leak")
  }

  /// An unresolvable app name is not evidence of permission on the excluded side, but it
  /// must not block an otherwise clean capture either.
  func testUnknownAppNamesDoNotFabricateAMismatch() {
    XCTAssertTrue(allows(before: nil, after: nil))
    XCTAssertTrue(allows(before: "Google Chrome", after: nil))
    XCTAssertFalse(allows(before: nil, after: "1Password"))
  }
}

final class SuggestionPacingTests: XCTestCase {
  /// Maximum (5) is the demo-grade cadence: nudge within seconds, repeat under half a
  /// minute. Every other level must keep the long-standing calm defaults untouched.
  func testMaximumLevelPacesFastEveryOtherLevelStaysCalm() {
    XCTAssertEqual(SuggestionPacing.requiredDwell(frequencyLevel: 5), 4)
    XCTAssertEqual(SuggestionPacing.settleInterval(frequencyLevel: 5), 2)
    XCTAssertEqual(SuggestionPacing.cooldown(base: 180, frequencyLevel: 5), 20)
    XCTAssertEqual(SuggestionPacing.dailyEvaluationBudget(frequencyLevel: 5), 600)
    XCTAssertEqual(SuggestionPacing.minConfidence(base: 0.85, frequencyLevel: 5), 0.65)
    // Maximum forgets screen nudges instantly (sustained repeats are the level's point)
    // but never task nudges — the same task re-firing every cooldown is the 0.12.172 bug.
    XCTAssertEqual(SuggestionPacing.dedupMemory(frequencyLevel: 5, category: .opportunity), 0)
    XCTAssertEqual(SuggestionPacing.dedupMemory(frequencyLevel: 5, category: .commitment), 10)

    for level in [0, 1, 2, 3, 4] {
      XCTAssertEqual(SuggestionPacing.requiredDwell(frequencyLevel: level), 30)
      XCTAssertEqual(SuggestionPacing.settleInterval(frequencyLevel: level), 6)
      XCTAssertEqual(SuggestionPacing.cooldown(base: 180, frequencyLevel: level), 180)
      XCTAssertEqual(SuggestionPacing.dailyEvaluationBudget(frequencyLevel: level), 40)
      XCTAssertEqual(SuggestionPacing.minConfidence(base: 0.85, frequencyLevel: level), 0.85)
      XCTAssertEqual(SuggestionPacing.dedupMemory(frequencyLevel: level, category: .opportunity), 10)
      XCTAssertEqual(SuggestionPacing.dedupMemory(frequencyLevel: level, category: .commitment), 10)
    }
  }

  /// A user-configured value already below the Maximum cap is respected, not raised.
  func testMaximumCapsNeverRaiseUserConfiguredValues() {
    XCTAssertEqual(SuggestionPacing.cooldown(base: 10, frequencyLevel: 5), 10)
    XCTAssertEqual(SuggestionPacing.minConfidence(base: 0.6, frequencyLevel: 5), 0.6)
  }

  /// Maximum keeps the context armed after an evaluation so staying on one feed keeps
  /// nudging; calm levels stay one-shot per arrival.
  func testOnlyMaximumRearmsAfterEvaluation() {
    XCTAssertTrue(SuggestionPacing.rearmsAfterEvaluation(frequencyLevel: 5))
    for level in [0, 1, 2, 3, 4] {
      XCTAssertFalse(SuggestionPacing.rearmsAfterEvaluation(frequencyLevel: level))
    }
  }

  /// Maximum forces a real frame every base heartbeat; calm levels keep the preview path.
  func testOnlyMaximumForcesHeartbeatCapture() {
    XCTAssertTrue(SuggestionPacing.forcesHeartbeatCapture(frequencyLevel: 5))
    for level in [0, 1, 2, 3, 4] {
      XCTAssertFalse(SuggestionPacing.forcesHeartbeatCapture(frequencyLevel: level))
    }
  }

  /// Fresh context at Maximum waives leftover cooldown; same-context repeats stay paced,
  /// and calm levels never waive.
  func testMaximumWaivesCooldownOnlyForFreshContext() {
    let last = Date(timeIntervalSince1970: 1_000_000)
    let freshAnchor = last.addingTimeInterval(5)
    let staleAnchor = last.addingTimeInterval(-40)
    XCTAssertNil(
      SuggestionPacing.effectiveLastEvaluation(
        lastEvaluationAt: last, anchor: freshAnchor, frequencyLevel: 5))
    XCTAssertEqual(
      SuggestionPacing.effectiveLastEvaluation(
        lastEvaluationAt: last, anchor: staleAnchor, frequencyLevel: 5), last)
    XCTAssertEqual(
      SuggestionPacing.effectiveLastEvaluation(
        lastEvaluationAt: last, anchor: freshAnchor, frequencyLevel: 3), last)
  }

  /// The trigger's own idle check must honor the level-aware window: at Maximum with
  /// 120s of stillness a heartbeat capture is still reachable; calm levels skip at 60s.
  func testMaximumIdleOverrideReachesHeartbeatCaptureAtTwoMinutesStill() {
    var trigger = ProactiveCaptureTrigger(idleThreshold: 60, heartbeatInterval: 9)
    let t0 = Date(timeIntervalSince1970: 1_000_000)
    // Prime the context (first sight of the app is a capture).
    XCTAssertEqual(
      trigger.nextDecision(
        app: "TikTok", windowTitle: "For You", idleSeconds: 0, now: t0,
        forceHeartbeatCapture: true,
        idleThresholdOverride: SuggestionPacing.captureIdleThreshold(frequencyLevel: 5, base: 60)),
      .capture)
    // Two minutes of stillness later: Maximum still captures on heartbeat…
    XCTAssertEqual(
      trigger.nextDecision(
        app: "TikTok", windowTitle: "For You", idleSeconds: 120, now: t0.addingTimeInterval(10),
        forceHeartbeatCapture: true,
        idleThresholdOverride: SuggestionPacing.captureIdleThreshold(frequencyLevel: 5, base: 60)),
      .capture)
    // …while a calm level's unchanged 60s threshold skips.
    XCTAssertEqual(
      trigger.nextDecision(
        app: "TikTok", windowTitle: "For You", idleSeconds: 120, now: t0.addingTimeInterval(20),
        idleThresholdOverride: SuggestionPacing.captureIdleThreshold(frequencyLevel: 3, base: 60)),
      .skip)
  }

  /// Passive watching produces no input; Maximum keeps capture alive for five minutes of
  /// stillness while calmer levels keep the long-standing 60s gate.
  func testMaximumExtendsCaptureIdleWindowOnly() {
    XCTAssertEqual(SuggestionPacing.captureIdleThreshold(frequencyLevel: 5, base: 60), 300)
    for level in [0, 1, 2, 3, 4] {
      XCTAssertEqual(SuggestionPacing.captureIdleThreshold(frequencyLevel: level, base: 60), 60)
    }
  }
}
