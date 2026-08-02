import XCTest

@testable import Omi_Computer

final class ScreenKnowledgeGraphExtractorTests: XCTestCase {
  override func tearDown() async throws {
    await ScreenKnowledgeGraphExtractor.shared.reset()
    try await super.tearDown()
  }

  func testParseExtractionJSONBuildsRecordsWithLabelDedup() {
    let json = """
      {
        "nodes": [
          {"id": "acme", "label": "Acme Corp", "node_type": "organization"},
          {"id": "acme_dup", "label": "acme corp", "node_type": "organization"}
        ],
        "edges": [
          {"source_id": "jane", "target_id": "acme_dup", "label": "works_at"}
        ]
      }
      """

    let parsed = KnowledgeGraphRecordBuilder.parseExtractionJSON(json)
    guard let parsed else {
      XCTFail("expected parsed extraction JSON")
      return
    }
    let records = KnowledgeGraphRecordBuilder.buildRecords(nodes: parsed.nodes, edges: parsed.edges)
    XCTAssertEqual(records.nodes.count, 1)
    XCTAssertEqual(records.nodes.first?.nodeId, "acme")
    XCTAssertEqual(records.edges.first?.sourceNodeId, "jane")
    XCTAssertEqual(records.edges.first?.targetNodeId, "acme")
  }

  func testContentHashIsStableForSameInput() {
    let input = ScreenKnowledgeGraphExtractor.makeInput(
      ocrText: "Quarterly planning with Jane Doe at Acme",
      appName: "Slack",
      windowTitle: "# eng")
    let a = ScreenKnowledgeGraphExtractor.contentHash(input)
    let b = ScreenKnowledgeGraphExtractor.contentHash(input)
    XCTAssertEqual(a, b)
  }

  func testContentHashUsesFullOCRTextBeyondTruncation() {
    let prefix = String(repeating: "A", count: 6_000)
    let left = prefix + "unique-tail-alpha"
    let right = prefix + "unique-tail-beta"
    let leftHash = ScreenKnowledgeGraphExtractor.contentHash(
      ocrText: left, appName: "Pages", windowTitle: "Doc")
    let rightHash = ScreenKnowledgeGraphExtractor.contentHash(
      ocrText: right, appName: "Pages", windowTitle: "Doc")
    XCTAssertNotEqual(leftHash, rightHash)

    // Truncated model inputs share a prefix, but dedup must not collapse them.
    let leftInput = ScreenKnowledgeGraphExtractor.makeInput(
      ocrText: left, appName: "Pages", windowTitle: "Doc")
    let rightInput = ScreenKnowledgeGraphExtractor.makeInput(
      ocrText: right, appName: "Pages", windowTitle: "Doc")
    XCTAssertEqual(leftInput.ocrText, rightInput.ocrText)
  }

  func testQueueSkipsShortOCR() async {
    let extractor = ScreenKnowledgeGraphExtractor(
      extractEntitiesForTesting: { _ in "{\"nodes\":[],\"edges\":[]}" },
      markExtractedForTesting: { _ in })
    await extractor.queueScreenshot(
      id: 1, ocrText: "too short", appName: "Notes", windowTitle: nil)
    let pending = await extractor.pendingCount
    XCTAssertEqual(pending, 0)
  }

  func testResetDropsPendingQueue() async {
    let extractor = ScreenKnowledgeGraphExtractor(
      extractEntitiesForTesting: { _ in "{\"nodes\":[],\"edges\":[]}" },
      markExtractedForTesting: { _ in })
    await extractor.queueScreenshot(
      id: 9,
      ocrText: String(repeating: "on-screen entity text ", count: 3),
      appName: "Safari",
      windowTitle: "Docs")
    var pending = await extractor.pendingCount
    XCTAssertEqual(pending, 1)

    await extractor.reset()
    pending = await extractor.pendingCount
    XCTAssertEqual(pending, 0)
  }

  func testFlushMarksExtractedAfterSuccessfulExtraction() async throws {
    let marked = LockedBox<[Int64]>([])
    let extractor = ScreenKnowledgeGraphExtractor(
      extractEntitiesForTesting: { _ in
        """
        {"nodes":[],"edges":[]}
        """
      },
      markExtractedForTesting: { ids in
        await marked.append(contentsOf: ids)
      })

    await extractor.queueScreenshot(
      id: 42,
      ocrText: String(repeating: "Project X roadmap details ", count: 3),
      appName: "Linear",
      windowTitle: "ENG")
    await extractor.flushPendingExtractions()

    let ids = await marked.value
    XCTAssertEqual(ids, [42])
  }

  func testDuplicateContentHashMarksWithoutReextracting() async {
    let extractCount = LockedBox(0)
    let marked = LockedBox<[Int64]>([])
    let text = String(repeating: "duplicate entity payload ", count: 3)

    let extractor = ScreenKnowledgeGraphExtractor(
      extractEntitiesForTesting: { _ in
        await extractCount.increment()
        return "{\"nodes\":[],\"edges\":[]}"
      },
      markExtractedForTesting: { ids in
        await marked.append(contentsOf: ids)
      })

    await extractor.queueScreenshot(id: 1, ocrText: text, appName: "Mail", windowTitle: "Inbox")
    await extractor.flushPendingExtractions()

    await extractor.queueScreenshot(id: 2, ocrText: text, appName: "Mail", windowTitle: "Inbox")

    let count = await extractCount.value
    XCTAssertEqual(count, 1)
    let ids = await marked.value
    XCTAssertEqual(ids, [1, 2])
  }

  func testExpectedProductStateDoesNotMarkExtracted() async {
    let marked = LockedBox<[Int64]>([])
    let extractor = ScreenKnowledgeGraphExtractor(
      extractEntitiesForTesting: { _ in
        throw GeminiClient.GeminiClientError.apiError("trial_expired")
      },
      markExtractedForTesting: { ids in
        await marked.append(contentsOf: ids)
      })

    await extractor.queueScreenshot(
      id: 7,
      ocrText: String(repeating: "gated entity payload ", count: 3),
      appName: "Notes",
      windowTitle: nil)
    await extractor.flushPendingExtractions()

    let ids = await marked.value
    XCTAssertTrue(ids.isEmpty)
    let pending = await extractor.pendingCount
    XCTAssertEqual(pending, 0)
  }

  func testProductGateResumeAllowsNewScreenshotsAndBackfill() async {
    let extractCount = LockedBox(0)
    let marked = LockedBox<[Int64]>([])
    let remaining = LockedBox(
      [
        (
          id: Int64(99),
          ocrText: String(repeating: "backfill after upgrade ", count: 3),
          appName: "Notes",
          windowTitle: nil as String?
        )
      ])
    let shouldGate = LockedBox(true)

    let extractor = ScreenKnowledgeGraphExtractor(
      extractEntitiesForTesting: { _ in
        if await shouldGate.value {
          throw GeminiClient.GeminiClientError.apiError("trial_expired")
        }
        await extractCount.increment()
        return "{\"nodes\":[],\"edges\":[]}"
      },
      markExtractedForTesting: { ids in
        await marked.append(contentsOf: ids)
      },
      fetchPendingForTesting: { limit in
        await remaining.takePrefix(limit)
      })

    await extractor.queueScreenshot(
      id: 7,
      ocrText: String(repeating: "gated entity payload ", count: 3),
      appName: "Notes",
      windowTitle: nil)
    await extractor.flushPendingExtractions()
    XCTAssertEqual(await extractor.pendingCount, 0)
    XCTAssertTrue(await marked.value.isEmpty)

    await shouldGate.set(false)
    await extractor.queueScreenshot(
      id: 8,
      ocrText: String(repeating: "post upgrade capture ", count: 3),
      appName: "Notes",
      windowTitle: nil)

    let ids = await marked.value
    XCTAssertTrue(ids.contains(8))
    XCTAssertTrue(ids.contains(99), "live resume must reschedule backfill for gated rows")
    XCTAssertGreaterThanOrEqual(await extractCount.value, 2)
  }

  func testStaleExpectedOwnerIsRejected() async {
    let owner = LockedBox("owner-a")
    let marked = LockedBox<[Int64]>([])
    let extractor = ScreenKnowledgeGraphExtractor(
      extractEntitiesForTesting: { _ in "{\"nodes\":[],\"edges\":[]}" },
      markExtractedForTesting: { ids in
        await marked.append(contentsOf: ids)
      },
      activeOwnerIDForTesting: { await owner.value })

    await extractor.queueScreenshot(
      id: 1,
      ocrText: String(repeating: "owner a screen text ", count: 3),
      appName: "Mail",
      windowTitle: nil,
      expectedOwnerID: "owner-a")
    XCTAssertEqual(await extractor.pendingCount, 1)

    await owner.set("owner-b")
    await extractor.queueScreenshot(
      id: 2,
      ocrText: String(repeating: "stale owner a screen text ", count: 3),
      appName: "Mail",
      windowTitle: nil,
      expectedOwnerID: "owner-a")
    XCTAssertEqual(await extractor.pendingCount, 1, "stale capture owner must not enqueue")

    await extractor.flushPendingExtractions()
    XCTAssertTrue(
      await marked.value.isEmpty,
      "pending from previous owner must not mark after owner change without reset")
  }

  func testMarkFailureDoesNotRecordDedupHash() async {
    let markShouldFail = LockedBox(true)
    let extractCount = LockedBox(0)
    let marked = LockedBox<[Int64]>([])
    let text = String(repeating: "hash ordering payload ", count: 3)

    let extractor = ScreenKnowledgeGraphExtractor(
      extractEntitiesForTesting: { _ in
        await extractCount.increment()
        return "{\"nodes\":[],\"edges\":[]}"
      },
      markExtractedForTesting: { ids in
        if await markShouldFail.value {
          throw NSError(domain: "ScreenKGTest", code: 1)
        }
        await marked.append(contentsOf: ids)
      })

    await extractor.queueScreenshot(id: 1, ocrText: text, appName: "Docs", windowTitle: nil)
    await extractor.flushPendingExtractions()
    XCTAssertEqual(await extractCount.value, 1)
    XCTAssertTrue(await marked.value.isEmpty)
    XCTAssertEqual(await extractor.pendingCount, 1, "failed mark must re-queue for retry")

    await markShouldFail.set(false)
    await extractor.flushPendingExtractions()
    XCTAssertEqual(await marked.value, [1])

    await extractor.queueScreenshot(id: 2, ocrText: text, appName: "Docs", windowTitle: nil)
    XCTAssertEqual(await extractCount.value, 1, "hash dedup only after successful mark")
    XCTAssertEqual(await marked.value, [1, 2])
  }

  func testBackfillStopsWithoutCountingWhenFlushStalls() async {
    let fetchCalls = LockedBox(0)
    let remaining = LockedBox(
      (1...80).map { id -> (id: Int64, ocrText: String, appName: String, windowTitle: String?) in
        (
          id: Int64(id),
          ocrText: String(repeating: "stall entity \(id) ", count: 3),
          appName: "App",
          windowTitle: nil
        )
      })

    let extractor = ScreenKnowledgeGraphExtractor(
      extractEntitiesForTesting: { _ in
        "not-json{{{broken"
      },
      markExtractedForTesting: { _ in },
      fetchPendingForTesting: { limit in
        await fetchCalls.increment()
        return await remaining.takePrefix(limit)
      })

    await extractor.scheduleBackfillIfNeeded()

    let calls = await fetchCalls.value
    XCTAssertEqual(calls, 1, "stalled flush must not keep refetching the same pending rows")
    XCTAssertEqual(await remaining.value.count, 30)
  }

  func testResetAllowsBackfillToBeRescheduled() async {
    let fetchCalls = LockedBox(0)
    let extractor = ScreenKnowledgeGraphExtractor(
      extractEntitiesForTesting: { _ in "{\"nodes\":[],\"edges\":[]}" },
      markExtractedForTesting: { _ in },
      fetchPendingForTesting: { _ in
        await fetchCalls.increment()
        return []
      })

    await extractor.scheduleBackfillIfNeeded()
    XCTAssertEqual(await fetchCalls.value, 1)

    await extractor.scheduleBackfillIfNeeded()
    XCTAssertEqual(await fetchCalls.value, 1, "second schedule is a no-op until reset")

    await extractor.reset()
    await extractor.scheduleBackfillIfNeeded()
    XCTAssertEqual(await fetchCalls.value, 2, "reset must allow backfill to run again")
  }

  func testOwnerRetargetReschedulesScreenKGBackfill() throws {
    // omi-test-quality: source-inspection -- static contract: owner retarget must
    // reschedule ScreenKnowledgeGraphExtractor backfill after reset; RuntimeOwnerIdentity
    // transition has no injectable seam for hermetic scheduling assertions.
    let source = try XCTUnwrap(
      String(
        contentsOfFile: RewindIndexerSourcePath.runtimeOwnerIdentitySwift,
        encoding: .utf8))
    XCTAssertTrue(source.contains("ScreenKnowledgeGraphExtractor.shared.reset()"))
    XCTAssertTrue(
      source.contains("ScreenKnowledgeGraphExtractor.shared.scheduleBackfillIfNeeded()"),
      "owner retarget must reschedule KG backfill after reset")
  }

  func testInvalidExtractionJSONDoesNotMarkExtracted() async {
    let marked = LockedBox<[Int64]>([])
    let extractor = ScreenKnowledgeGraphExtractor(
      extractEntitiesForTesting: { _ in
        "not-json{{{broken"
      },
      markExtractedForTesting: { ids in
        await marked.append(contentsOf: ids)
      })

    await extractor.queueScreenshot(
      id: 11,
      ocrText: String(repeating: "parse failure payload ", count: 3),
      appName: "Safari",
      windowTitle: "Tab")
    await extractor.flushPendingExtractions()

    let ids = await marked.value
    XCTAssertTrue(ids.isEmpty)
    let pending = await extractor.pendingCount
    XCTAssertEqual(pending, 1)
  }

  func testBackfillProcessesMultipleBatches() async {
    let marked = LockedBox<[Int64]>([])
    let fetchCalls = LockedBox(0)
    let remaining = LockedBox(
      (1...120).map { id -> (id: Int64, ocrText: String, appName: String, windowTitle: String?) in
        (
          id: Int64(id),
          ocrText: String(repeating: "backfill entity \(id) ", count: 3),
          appName: "App",
          windowTitle: nil
        )
      })

    let extractor = ScreenKnowledgeGraphExtractor(
      extractEntitiesForTesting: { _ in
        "{\"nodes\":[],\"edges\":[]}"
      },
      markExtractedForTesting: { ids in
        await marked.append(contentsOf: ids)
      },
      fetchPendingForTesting: { limit in
        await fetchCalls.increment()
        return await remaining.takePrefix(limit)
      })

    await extractor.scheduleBackfillIfNeeded()

    let calls = await fetchCalls.value
    XCTAssertGreaterThanOrEqual(calls, 3)
    let ids = await marked.value
    XCTAssertEqual(ids.count, 120)
  }

  func testBatteryOCRBackfillQueuesScreenKGExtraction() throws {
    // omi-test-quality: source-inspection -- static contract: battery OCR backfill must
    // queue ScreenKnowledgeGraphExtractor after updateOCRResult; RewindIndexer has no
    // injectable seam for hermetic OCR/storage, so behavioral coverage of that path
    // cannot run in the Linux/macOS unit host without a full Rewind stack.
    let source = try XCTUnwrap(
      String(
        contentsOfFile: RewindIndexerSourcePath.rewindIndexerSwift,
        encoding: .utf8))
    XCTAssertTrue(source.contains("func backfillUnindexedScreenshots"))
    XCTAssertTrue(source.contains("updateOCRResult(id: id, ocrResult: ocrResult)"))
    XCTAssertTrue(
      source.contains("ScreenKnowledgeGraphExtractor.shared.queueScreenshot"),
      "battery OCR backfill must queue KG extraction for newly indexed screenshots")
    XCTAssertTrue(
      source.contains("expectedOwnerID: captureOwnerID"),
      "capture paths must fence queueScreenshot with the capture-time owner")

    if let updateRange = source.range(of: "updateOCRResult(id: id, ocrResult: ocrResult)"),
      let backfillRange = source.range(of: "func backfillUnindexedScreenshots")
    {
      let afterUpdate = source[updateRange.upperBound...]
      let queueRange = afterUpdate.range(
        of: "ScreenKnowledgeGraphExtractor.shared.queueScreenshot")
      XCTAssertNotNil(queueRange, "queueScreenshot must follow updateOCRResult in OCR backfill")
      XCTAssertTrue(backfillRange.lowerBound < updateRange.lowerBound)
    } else {
      XCTFail("expected updateOCRResult inside backfillUnindexedScreenshots")
    }
  }

  func testDistinctLongCapturesAreNotCollapsedByTruncation() async {
    let extractCount = LockedBox(0)
    let marked = LockedBox<[Int64]>([])
    let prefix = String(repeating: "shared-prefix-content ", count: 300)  // > 6000 chars
    let first = prefix + " FIRST-TAIL-ENTITY-ALPHA"
    let second = prefix + " SECOND-TAIL-ENTITY-BETA"

    let extractor = ScreenKnowledgeGraphExtractor(
      extractEntitiesForTesting: { _ in
        await extractCount.increment()
        return "{\"nodes\":[],\"edges\":[]}"
      },
      markExtractedForTesting: { ids in
        await marked.append(contentsOf: ids)
      })

    await extractor.queueScreenshot(id: 1, ocrText: first, appName: "Docs", windowTitle: "Long")
    await extractor.flushPendingExtractions()
    await extractor.queueScreenshot(id: 2, ocrText: second, appName: "Docs", windowTitle: "Long")
    await extractor.flushPendingExtractions()

    let count = await extractCount.value
    XCTAssertEqual(count, 2)
    let ids = await marked.value
    XCTAssertEqual(ids, [1, 2])
  }
}

private enum RewindIndexerSourcePath {
  static var desktopSourcesRoot: URL {
    URL(fileURLWithPath: #filePath)
      .deletingLastPathComponent()  // Tests/
      .deletingLastPathComponent()  // Desktop/
      .appendingPathComponent("Sources")
  }

  static var rewindIndexerSwift: String {
    desktopSourcesRoot.appendingPathComponent("Rewind/Services/RewindIndexer.swift").path
  }

  static var runtimeOwnerIdentitySwift: String {
    desktopSourcesRoot.appendingPathComponent("Chat/RuntimeOwnerIdentity.swift").path
  }
}

private actor LockedBox<T> {
  private(set) var value: T

  init(_ value: T) {
    self.value = value
  }

  func set(_ value: T) {
    self.value = value
  }

  func append(contentsOf elements: [Int64]) where T == [Int64] {
    value.append(contentsOf: elements)
  }

  func increment() where T == Int {
    value += 1
  }

  func takePrefix(_ limit: Int) -> T where T == [(id: Int64, ocrText: String, appName: String, windowTitle: String?)] {
    let batch = Array(value.prefix(limit))
    value.removeFirst(batch.count)
    return batch
  }
}
