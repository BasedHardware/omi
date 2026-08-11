import XCTest

@testable import Omi_Computer

final class ContextBucketPromptAssemblerTests: XCTestCase {
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
