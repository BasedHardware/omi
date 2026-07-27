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
    isSnoozed: Bool = false,
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
      isSnoozed: isSnoozed,
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

  func testSnoozedBarDoesNotEvaluate() {
    XCTAssertEqual(decide(isSnoozed: true), .skippedSnoozed)
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
      isSnoozed: true,
      lastEvaluationAt: now
    )
    XCTAssertEqual(decision, .skippedDisabled)
  }

  /// A privacy exclusion must outrank snooze and cooldown: "do not look at this app" is a
  /// stronger statement than "not right now".
  func testExclusionTakesPrecedenceOverSnoozeAndCooldown() {
    let decision = decide(isAppExcluded: true, isSnoozed: true, lastEvaluationAt: now)
    XCTAssertEqual(decision, .skippedExcludedApp)
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
