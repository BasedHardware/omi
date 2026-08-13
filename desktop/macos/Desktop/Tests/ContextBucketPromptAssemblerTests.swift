import XCTest

@testable import Omi_Computer

final class ContextBucketPromptAssemblerTests: XCTestCase {
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
    let snapshot = ContextBucketSnapshot(
      bucketID: "bucket", versionID: 5, version: 2, header: "Persistent work context; 2 qualifying visits.",
      frozenRankedSegment: Data("frozen:entry-1\n".utf8),
      tail: ["tail:entry-2"],
      validatedFacts: ["fact:PR-123"],
      notifyWorthiness: 1)
    let frame = CapturedFrame(
      jpegData: Data(), appName: "Terminal", windowTitle: "deploy.sh", frameNumber: 9)
    let prompt = ContextProactivityPromptBuilder.directorPrompt(
      snapshot: snapshot,
      tasks: ["Review PR-123", "Send release notes"],
      frame: frame)
    let bucket = String(data: ContextBucketPromptAssembler.assemble(snapshot), encoding: .utf8) ?? ""
    let expected = [
      ScreenDerivedContent.untrustedPreamble,
      "Decide whether interrupting now adds concrete value. Return silence unless the validated",
      "facts support a specific, timely action. Use only supplied bucket-entry refs.",
      "",
      bucket,
      "",
      "== OPEN OR OVERDUE TASKS ==",
      "- Review PR-123\n- Send release notes",
      "",
      "== CURRENT FRAME METADATA ==",
      "App: Terminal",
      "Window: deploy.sh",
    ].joined(separator: "\n")

    XCTAssertEqual(prompt, expected)
    XCTAssertTrue(prompt.contains("== BUCKET HEADER ==\nPersistent work context; 2 qualifying visits."))
    XCTAssertTrue(prompt.contains("== FROZEN RANKED CONTEXT ==\nfrozen:entry-1"))
    XCTAssertTrue(prompt.contains("== RECENT TAIL ==\ntail:entry-2"))
    XCTAssertTrue(prompt.contains("== VALIDATED FACTS ==\nfact:PR-123"))
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
}
