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
    let expected = [
      ScreenDerivedContent.untrustedPreamble,
      "Produce a 150-400 token ambient narrative and discrete factual records. Facts are",
      "proposals; include an identifier, surviving evidence text, and evidence ref for each.",
      "App: Xcode",
      "Window: PR-123",
      "Evidence ref: screenshot:42",
    ].joined(separator: "\n")

    XCTAssertEqual(prompt, expected)
  }

  func testExtractionPromptFallsBackToVisitEvidenceRefWithoutScreenshot() {
    let frame = CapturedFrame(jpegData: Data(), appName: "Safari", frameNumber: 8)
    let fence = ContextVisitFence(
      visitID: 123, contextGeneration: 3, poolEpoch: 4, bucketID: "bucket", startedAt: Date(timeIntervalSince1970: 1))

    let prompt = ContextProactivityPromptBuilder.extractionPrompt(frame: frame, fence: fence)

    XCTAssertTrue(prompt.hasSuffix("App: Safari\nWindow: \nEvidence ref: visit:123"))
  }

  func testDirectorPromptContainsSafetyPreambleBucketTasksAndFrameMetadata() {
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
      frame: frame)
    let bucket = String(data: ContextBucketPromptAssembler.assemble(snapshot), encoding: .utf8) ?? ""
    let expected = [
      ScreenDerivedContent.untrustedPreamble,
      "Decide whether interrupting now adds concrete value. Return silence unless the validated",
      "facts support a specific, timely action. Use only supplied bucket-entry refs.",
      "Use resurface or suggest for an actionable open task supplied below. Entries marked",
      "reference-only are identity context: do not notify about or recreate them yet. Use",
      "task_candidate only for a new validated commitment absent from the supplied task list.",
      "",
      bucket,
      "",
      "== OPEN OR OVERDUE TASKS ==",
      "- Review PR-123\n  Due at (UTC): 2023-11-14T23:13:20.000Z\n- Send release notes",
      "",
      "== CURRENT FRAME METADATA ==",
      "App: Terminal",
      "Window: deploy.sh",
      "Captured at (UTC): 2023-11-14T22:13:20.000Z",
    ].joined(separator: "\n")

    XCTAssertEqual(prompt, expected)
    XCTAssertTrue(prompt.contains("== BUCKET HEADER ==\nPersistent work context; 2 qualifying visits."))
    XCTAssertTrue(prompt.contains("== FROZEN RANKED CONTEXT ==\nfrozen:entry-1"))
    XCTAssertTrue(prompt.contains("== RECENT TAIL ==\ntail:entry-2"))
    XCTAssertTrue(prompt.contains("== VALIDATED FACTS ==\nfact:PR-123"))
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
