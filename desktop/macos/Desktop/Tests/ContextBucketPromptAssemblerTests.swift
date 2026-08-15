import XCTest

@testable import Omi_Computer

final class ContextBucketPromptAssemblerTests: XCTestCase {
  func testCompactionStartsBeforeAnEntryFallsOutsideTheRetainedTail() {
    XCTAssertFalse(
      ContextBucketCompactionPolicy.shouldCompact(uncompressedCount: 5))
    XCTAssertTrue(
      ContextBucketCompactionPolicy.shouldCompact(uncompressedCount: 6),
      "The sixth short narrative must move into frozen context instead of disappearing")
  }

  func testExtractionPromptPreservesSafetyPreambleAndScreenshotEvidenceRef() {
    let frame = CapturedFrame(
      jpegData: Data(), appName: "Xcode", windowTitle: "PR-123", frameNumber: 7, screenshotId: 42)
    let fence = ContextVisitFence(
      visitID: 99, contextGeneration: 3, poolEpoch: 4, bucketID: "bucket", startedAt: Date(timeIntervalSince1970: 1))

    let prompt = ContextProactivityPromptBuilder.extractionPrompt(frame: frame, fence: fence)
    let expected =
      [
        ScreenDerivedContent.untrustedPreamble,
        "Write a 150-400 token summary of what is happening, then discrete factual records.",
        "Each statement must be a plain declarative sentence a colleague could act on. Do not",
        "label, number, or prefix statements.",
        "Good: Nik asked for the demo recording before tomorrow's launch video.",
        "Bad: Ambient narrative: the user appears to be coordinating a recording workflow.",
        "Fill identifiers with names, ticket numbers, or other handles copied from the quoted",
        "on-screen text. Fill evidence_text with that supporting on-screen wording. Put this",
        "ref in every evidence_refs list: screenshot:42",
        "App: Xcode",
        "Window: PR-123",
      ].joined(separator: "\n")
      // Xcode is not a browser, so destination routing must not be offered here —
      // only the abstention that satisfies the strict-schema required field.
      + "\n\nSet \"destination\" to \"\(ContextDestinationKey.abstention)\"."

    XCTAssertEqual(prompt, expected)
  }

  func testExtractionPromptFallsBackToVisitEvidenceRefWithoutScreenshot() {
    let frame = CapturedFrame(jpegData: Data(), appName: "Safari", frameNumber: 8)
    let fence = ContextVisitFence(
      visitID: 123, contextGeneration: 3, poolEpoch: 4, bucketID: "bucket", startedAt: Date(timeIntervalSince1970: 1))

    let prompt = ContextProactivityPromptBuilder.extractionPrompt(frame: frame, fence: fence)

    // Safari is a browser, but a blank window title carries no destination signal,
    // so this must still fall through to abstention rather than inviting a guess.
    XCTAssertTrue(prompt.contains("App: Safari\nWindow: "))
    XCTAssertTrue(prompt.contains("ref in every evidence_refs list: visit:123"))
    XCTAssertTrue(prompt.hasSuffix("Set \"destination\" to \"\(ContextDestinationKey.abstention)\"."))
    XCTAssertFalse(prompt.contains("page-group"))
  }

  func testDirectorPromptContainsSafetyPreambleBucketTasksAndFrameMetadata() throws {
    let timeZone = try XCTUnwrap(TimeZone(identifier: "America/New_York"))
    let capturedAt = Date(timeIntervalSince1970: 1_700_000_000)
    let dueAt = Date(timeIntervalSince1970: 1_700_003_600)
    let snapshot = ContextBucketSnapshot(
      bucketID: "bucket", versionID: 5, version: 2, header: "Persistent work context; 2 qualifying visits.",
      frozenRankedSegment: Data("frozen:entry-1\n".utf8),
      tail: ["tail:entry-2"],
      validatedFacts: ["fact:PR-123"],
      notifyWorthiness: 1)
    let frame = CapturedFrame(
      jpegData: Data(), appName: "Terminal", windowTitle: "deploy.sh", frameNumber: 9,
      captureTime: capturedAt)
    let prompt = ContextProactivityPromptBuilder.directorPrompt(
      snapshot: snapshot,
      tasks: [
        ContextDirectorTaskContext(description: "Review PR-123", dueAt: dueAt),
        ContextDirectorTaskContext(description: "Send release notes", dueAt: nil),
      ],
      frame: frame,
      timeZone: timeZone)
    let bucket = String(data: ContextBucketPromptAssembler.assemble(snapshot), encoding: .utf8) ?? ""
    let expected = [
      ScreenDerivedContent.untrustedPreamble,
      "Decide whether interrupting now adds concrete value. Return silence unless the validated",
      "facts support a specific, timely action. Use only supplied bucket-entry refs.",
      "Never announce that meeting notes, a transcript, or a call summary are ready. The",
      "conversation-finalization lane owns that claim and attaches the exact conversation link.",
      "Use resurface or suggest for an actionable open task supplied below. Entries marked",
      "reference-only are identity context: do not notify about or recreate them yet. Use",
      "task_candidate only when a validated fact explicitly records a new commitment, promise,",
      "or request with an accountable action that the user personally made or accepted (first",
      "person), and that commitment is absent from the supplied task list. A commitment made by",
      "another person is never a task candidate, however explicit or well-dated it is; if it",
      "genuinely bears on the user's tracked work it may at most be insight, and a commitment",
      "between other parties that does not involve the user is silence. A material change, status",
      "update, recommendation, or useful follow-up without an explicit commitment, promise, or",
      "request is insight or suggest; never infer an owner or due date and never create a task",
      "candidate from actionability alone.",
      "Do not restate what is already visible on the user's screen. Speak only when you add",
      "something they cannot currently see: a commitment, a deadline, a conflict, or a",
      "connection to other work.",
      "The recently-delivered list is a prohibition, not background. Do not re-send a point",
      "already delivered, even reworded.",
      "Timestamps supplied below are already in the user's local time zone. When a message",
      "mentions a date or time, use that local form as written; never convert to or mention UTC.",
      "",
      bucket,
      "",
      "== OPEN OR OVERDUE TASKS ==",
      "- Review PR-123\n  Due at: 2023-11-14 18:13 EST\n- Send release notes",
      "",
      "== CURRENT FRAME METADATA ==",
      "App: Terminal",
      "Window: deploy.sh",
      "Captured at: 2023-11-14 17:13 EST",
    ].joined(separator: "\n")

    XCTAssertEqual(prompt, expected)
    XCTAssertTrue(prompt.contains("== BUCKET HEADER ==\nPersistent work context; 2 qualifying visits."))
    XCTAssertTrue(prompt.contains("== FROZEN RANKED CONTEXT ==\nfrozen:entry-1"))
    XCTAssertTrue(prompt.contains("== RECENT TAIL ==\ntail:entry-2"))
    XCTAssertTrue(prompt.contains("== VALIDATED FACTS ==\nfact:PR-123"))
    XCTAssertFalse(prompt.contains("== RECENTLY DELIVERED FOR THIS BUCKET =="))
  }

  func testDirectorPromptIncludesBoundedRecentDeliveriesForThisBucket() throws {
    let timeZone = try XCTUnwrap(TimeZone(identifier: "America/New_York"))
    let capturedAt = Date(timeIntervalSince1970: 1_700_000_000)
    let snapshot = ContextBucketSnapshot(
      bucketID: "bucket", versionID: 1, version: 1, header: "header",
      frozenRankedSegment: Data(), tail: [], validatedFacts: ["fact"], notifyWorthiness: 1)
    let frame = CapturedFrame(
      jpegData: Data(), appName: "Notes", frameNumber: 10, captureTime: capturedAt)
    let prompt = ContextProactivityPromptBuilder.directorPrompt(
      snapshot: snapshot,
      tasks: [],
      frame: frame,
      recentDeliveries: [
        ContextBucketRecentDelivery(
          decisionType: "resurface",
          message: "Keep the investigation open",
          deliveredAt: capturedAt.addingTimeInterval(-65)),
        ContextBucketRecentDelivery(
          decisionType: "insight",
          message: "Status changed",
          deliveredAt: capturedAt.addingTimeInterval(-26 * 60)),
      ],
      timeZone: timeZone)
    let bucket = String(data: ContextBucketPromptAssembler.assemble(snapshot), encoding: .utf8) ?? ""
    let expected = [
      ScreenDerivedContent.untrustedPreamble,
      "Decide whether interrupting now adds concrete value. Return silence unless the validated",
      "facts support a specific, timely action. Use only supplied bucket-entry refs.",
      "Never announce that meeting notes, a transcript, or a call summary are ready. The",
      "conversation-finalization lane owns that claim and attaches the exact conversation link.",
      "Use resurface or suggest for an actionable open task supplied below. Entries marked",
      "reference-only are identity context: do not notify about or recreate them yet. Use",
      "task_candidate only when a validated fact explicitly records a new commitment, promise,",
      "or request with an accountable action that the user personally made or accepted (first",
      "person), and that commitment is absent from the supplied task list. A commitment made by",
      "another person is never a task candidate, however explicit or well-dated it is; if it",
      "genuinely bears on the user's tracked work it may at most be insight, and a commitment",
      "between other parties that does not involve the user is silence. A material change, status",
      "update, recommendation, or useful follow-up without an explicit commitment, promise, or",
      "request is insight or suggest; never infer an owner or due date and never create a task",
      "candidate from actionability alone.",
      "Do not restate what is already visible on the user's screen. Speak only when you add",
      "something they cannot currently see: a commitment, a deadline, a conflict, or a",
      "connection to other work.",
      "The recently-delivered list is a prohibition, not background. Do not re-send a point",
      "already delivered, even reworded.",
      "Timestamps supplied below are already in the user's local time zone. When a message",
      "mentions a date or time, use that local form as written; never convert to or mention UTC.",
      "",
      bucket,
      "",
      "== OPEN OR OVERDUE TASKS ==",
      "",
      "",
      "== CURRENT FRAME METADATA ==",
      "App: Notes",
      "Window: ",
      "Captured at: 2023-11-14 17:13 EST",
      "",
      "== RECENTLY DELIVERED FOR THIS BUCKET ==",
      "Do not re-send any of these points, even reworded.",
      "- resurface (1m ago): Keep the investigation open",
      "- insight (26m ago): Status changed",
    ].joined(separator: "\n")

    XCTAssertEqual(prompt, expected)
  }

  func testDirectorPromptKeepsLocalDateWhenUTCHasAlreadyRolledToTheNextDay() throws {
    // 2026-08-11T03:59:00Z is 2026-08-10 23:59 in New York (DST on). This is the
    // #11392 failure shape: a due-tonight task whose UTC date reads as tomorrow.
    let timeZone = try XCTUnwrap(TimeZone(identifier: "America/New_York"))
    let dueAt = Date(timeIntervalSince1970: 1_786_420_740)
    let frame = CapturedFrame(
      jpegData: Data(), appName: "Notes", frameNumber: 1,
      captureTime: dueAt.addingTimeInterval(-600))
    let prompt = ContextProactivityPromptBuilder.directorVolatilePrompt(
      tasks: [ContextDirectorTaskContext(description: "File the report", dueAt: dueAt)],
      frame: frame,
      timeZone: timeZone)
    XCTAssertTrue(prompt.contains("Due at: 2026-08-10 23:59 EDT"), prompt)
    XCTAssertFalse(prompt.contains("2026-08-11"))
  }

  func testDirectorPromptCapsRecentDeliveriesAndOmitsTheSectionWhenEmpty() {
    let capturedAt = Date(timeIntervalSince1970: 1_700_000_000)
    let snapshot = ContextBucketSnapshot(
      bucketID: "bucket", versionID: 1, version: 1, header: "header",
      frozenRankedSegment: Data(), tail: [], validatedFacts: ["fact"], notifyWorthiness: 1)
    let frame = CapturedFrame(
      jpegData: Data(), appName: "Notes", frameNumber: 10, captureTime: capturedAt)
    let empty = ContextProactivityPromptBuilder.directorPrompt(
      snapshot: snapshot, tasks: [], frame: frame, recentDeliveries: [])
    XCTAssertFalse(empty.contains("== RECENTLY DELIVERED FOR THIS BUCKET =="))

    let overflow = (0..<8).map { index in
      ContextBucketRecentDelivery(
        decisionType: "resurface",
        message: "nudge-\(index)",
        deliveredAt: capturedAt.addingTimeInterval(TimeInterval(-60 * (index + 1))))
    }
    let capped = ContextProactivityPromptBuilder.directorPrompt(
      snapshot: snapshot, tasks: [], frame: frame, recentDeliveries: overflow)
    XCTAssertEqual(
      ContextProactivityPromptBuilder.recentDeliveriesSection(overflow, now: capturedAt),
      """
      == RECENTLY DELIVERED FOR THIS BUCKET ==
      Do not re-send any of these points, even reworded.
      - resurface (1m ago): nudge-0
      - resurface (2m ago): nudge-1
      - resurface (3m ago): nudge-2
      - resurface (4m ago): nudge-3
      - resurface (5m ago): nudge-4
      - resurface (6m ago): nudge-5
      """)
    XCTAssertTrue(capped.contains("- resurface (1m ago): nudge-0"))
    XCTAssertTrue(capped.contains("- resurface (6m ago): nudge-5"))
    XCTAssertFalse(capped.contains("nudge-6"))
    XCTAssertFalse(capped.contains("nudge-7"))
  }

  func testBoundedSummaryKeepsDistinguishingContentPastTheOldTruncatePoint() {
    let distinguishing = "the beta rollout is still incomplete because the legacy PostHog path is live"
    let shortEnough = String(repeating: "x", count: 120) + distinguishing
    XCTAssertTrue(shortEnough.count > 120)
    XCTAssertTrue(shortEnough.count < ContextBucketRecentDelivery.summaryCharacterLimit)
    XCTAssertEqual(
      ContextProactivityPromptBuilder.boundedSummary(shortEnough),
      shortEnough)
    let overLimit = String(repeating: "y", count: ContextBucketRecentDelivery.summaryCharacterLimit + 40)
    XCTAssertEqual(
      ContextProactivityPromptBuilder.boundedSummary(overLimit).count,
      ContextBucketRecentDelivery.summaryCharacterLimit)
  }

  func testDirectorTaskContextBoundsDescription() {
    let task = ContextDirectorTaskContext(
      description: String(repeating: "x", count: ContextDirectorTaskContext.maximumDescriptionLength + 10),
      dueAt: nil)

    XCTAssertEqual(task.description.count, ContextDirectorTaskContext.maximumDescriptionLength)
  }

  func testDirectorTaskSelectionIncludesFarFutureAsReferenceAfterActionableTasks() {
    let now = Date(timeIntervalSince1970: 1_700_000_000)
    let tasks = [
      task("tomorrow", dueAt: now.addingTimeInterval(24 * 60 * 60)),
      task("undated", dueAt: nil),
      task("far", dueAt: now.addingTimeInterval(72 * 60 * 60)),
      task("done", completed: true, dueAt: now.addingTimeInterval(60)),
    ]

    XCTAssertEqual(
      ContextDirectorTaskSelection.select(from: tasks, now: now).map(\.description),
      ["tomorrow", "undated", "far"])
  }

  func testDirectorPromptMarksFarFutureTaskReferenceOnly() {
    let now = Date(timeIntervalSince1970: 1_700_000_000)
    let snapshot = ContextBucketSnapshot(
      bucketID: "bucket", versionID: 1, version: 1, header: "header",
      frozenRankedSegment: Data(), tail: [], validatedFacts: ["fact"], notifyWorthiness: 1)
    let prompt = ContextProactivityPromptBuilder.directorPrompt(
      snapshot: snapshot,
      tasks: [
        ContextDirectorTaskContext(
          description: "Far task", dueAt: now.addingTimeInterval(72 * 60 * 60))
      ],
      frame: CapturedFrame(jpegData: Data(), appName: "Notes", frameNumber: 10, captureTime: now))

    XCTAssertTrue(
      prompt.contains("Reference only: already exists; do not resurface or create it yet."))
  }

  func testFrozenRankedSegmentIsConcatenatedByteForByte() {
    let frozen = Data([0x2D, 0x20, 0xC3, 0xA9, 0x0A])
    let snapshot = ContextBucketSnapshot(
      bucketID: "b", versionID: 1, version: 1, header: "h",
      frozenRankedSegment: frozen, tail: ["new"], validatedFacts: ["fact"], notifyWorthiness: 1)
    let prompt = ContextBucketPromptAssembler.assemble(snapshot)
    XCTAssertNotNil(prompt.range(of: frozen))
    XCTAssertEqual(prompt.subdata(in: try XCTUnwrap(prompt.range(of: frozen))), frozen)
  }

  func testOnlyResolvableIdentifiedFactsValidate() {
    XCTAssertEqual(
      BucketFactValidator.validity(
        identifiers: ["PR-123"], evidenceText: "PR-123 is blocked", evidenceRefs: ["visit:1"],
        duplicate: false),
      .validated)
    XCTAssertEqual(
      BucketFactValidator.validity(
        identifiers: [], evidenceText: "do this immediately", evidenceRefs: ["visit:1"],
        duplicate: false),
      .needsReview)
    XCTAssertEqual(
      BucketFactValidator.validity(
        identifiers: ["PR-123"], evidenceText: "same", evidenceRefs: ["visit:1"], duplicate: true),
      .superseded)
  }

  func testAcceptedIdentifiersDropBookkeepingAndHandlesAbsentFromQuotedText() {
    XCTAssertEqual(
      BucketFactValidator.acceptedIdentifiers(
        ["fact-001", "f-002", "FTN-003", "visit:327", "screenshot:42", "PR-123", "Nik"],
        evidenceText: "Nik asked for the demo recording. PR-123 is the launch blocker."),
      ["PR-123", "Nik"])
    XCTAssertEqual(
      BucketFactValidator.acceptedIdentifiers(["Acme"], evidenceText: "the board was lying"),
      [])
  }

  func testAcceptedIdentifiersMatchCaseInsensitivelyButKeepTheOriginalCasing() {
    XCTAssertEqual(
      BucketFactValidator.acceptedIdentifiers(
        ["pr-123"], evidenceText: "PR-123 is the launch blocker."),
      ["pr-123"],
      "a differently-cased on-screen quote must not discard an otherwise-valid identifier")
    XCTAssertEqual(
      BucketFactValidator.acceptedIdentifiers(
        ["NIK"], evidenceText: "nik asked for the demo recording."),
      ["NIK"])
  }

  func testExtractionSchemaOmitsWorkstream() throws {
    let properties = try XCTUnwrap(
      ContextBucketRollupWriter.schema["properties"] as? [String: Any])
    let facts = try XCTUnwrap(properties["facts"] as? [String: Any])
    let items = try XCTUnwrap(facts["items"] as? [String: Any])
    let factProperties = try XCTUnwrap(items["properties"] as? [String: Any])
    let required = try XCTUnwrap(items["required"] as? [String])
    XCTAssertNil(factProperties["workstream"])
    XCTAssertFalse(required.contains("workstream"))
    XCTAssertEqual(
      Set(required),
      [
        "statement", "identifiers", "evidence_text", "evidence_refs", "confidence",
        "notify_worthiness",
      ])
  }

  func testCanonicalIdentifierSetKeyIsNormalizationOnlyAndKeepsDistinctSetsSeparate() {
    XCTAssertEqual(
      BucketFactValidator.canonicalIdentifierSetKey([" Handoff-013 ", "handoff-013", ""]),
      "[\"handoff-013\"]")
    XCTAssertEqual(
      BucketFactValidator.canonicalIdentifierSetKey(["task-014", "task-013"]),
      BucketFactValidator.canonicalIdentifierSetKey([" TASK-013 ", "task-014 "]))
    XCTAssertNotEqual(
      BucketFactValidator.canonicalIdentifierSetKey(["task-013"]),
      BucketFactValidator.canonicalIdentifierSetKey(["task-014"]))
    XCTAssertNil(BucketFactValidator.canonicalIdentifierSetKey([" ", "\n"]))
  }

  func testParaphraseShadowMatchRequiresDifferentStatementAndSameIdentifierSet() {
    let existing = [
      BucketFactValidator.ExistingFactIdentity(
        statement: "Check the handoff status.", identifiers: ["handoff-013"])
    ]
    XCTAssertTrue(
      BucketFactValidator.hasParaphraseMatch(
        statement: "Verify the handoff is complete.",
        identifiers: [" HANDOFF-013 "],
        existingFacts: existing))
    XCTAssertFalse(
      BucketFactValidator.hasParaphraseMatch(
        statement: "Check the handoff status.",
        identifiers: ["handoff-013"],
        existingFacts: existing))
    XCTAssertFalse(
      BucketFactValidator.hasParaphraseMatch(
        statement: "Verify another handoff.", identifiers: ["handoff-014"], existingFacts: existing))
  }

  func testShadowParaphraseObservationDoesNotSuppressAChangedClaim() {
    let existing = [
      BucketFactValidator.ExistingFactIdentity(
        statement: "The handoff is pending.", identifiers: ["handoff-013"])
    ]
    XCTAssertTrue(
      BucketFactValidator.hasParaphraseMatch(
        statement: "The handoff is complete.",
        identifiers: ["handoff-013"],
        existingFacts: existing))
    XCTAssertEqual(
      BucketFactValidator.validity(
        identifiers: ["handoff-013"],
        evidenceText: "The handoff is complete.",
        evidenceRefs: ["visit:2"],
        duplicate: false),
      .validated)
  }

  func testEvidenceRefsMustResolveAgainstTheCompletedVisit() {
    let refs = BucketFactValidator.resolvableEvidenceRefs(
      ["screenshot:42", "screenshot:999", "instructions:ignore-policy"],
      allowed: ["visit:7", "screenshot:42"])

    XCTAssertEqual(refs, ["screenshot:42"])
  }

  func testPromptAssemblyHonorsInjectionBudget() {
    let snapshot = ContextBucketSnapshot(
      bucketID: "bucket", versionID: 1, version: 1, header: String(repeating: "h", count: 500),
      frozenRankedSegment: Data(String(repeating: "f", count: 6_000).utf8),
      tail: Array(repeating: String(repeating: "t", count: 2_400), count: 5),
      validatedFacts: Array(repeating: String(repeating: "v", count: 1_500), count: 20),
      notifyWorthiness: 1)

    let assembled = ContextBucketPromptAssembler.assemble(snapshot)

    XCTAssertLessThanOrEqual(assembled.count, ContextBucketPromptAssembler.injectionTokenBudget * 4)
    XCTAssertTrue(assembled.contains(snapshot.frozenRankedSegment))
    XCTAssertNotNil(String(data: assembled, encoding: .utf8))
  }

  private func task(
    _ description: String,
    completed: Bool = false,
    dueAt: Date?
  ) -> TaskActionItem {
    TaskActionItem(
      id: description,
      description: description,
      completed: completed,
      createdAt: Date(timeIntervalSince1970: 1_699_999_000),
      dueAt: dueAt,
      source: "manual")
  }
}
