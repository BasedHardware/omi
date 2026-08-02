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

  func testQueueSkipsShortOCR() async {
    await ScreenKnowledgeGraphExtractor.shared.reset()
    await ScreenKnowledgeGraphExtractor.shared.queueScreenshot(
      id: 1, ocrText: "too short", appName: "Notes", windowTitle: nil)
    let pending = await ScreenKnowledgeGraphExtractor.shared.pendingCount
    XCTAssertEqual(pending, 0)
  }

  func testResetDropsPendingQueue() async {
    await ScreenKnowledgeGraphExtractor.shared.reset()
    await ScreenKnowledgeGraphExtractor.shared.queueScreenshot(
      id: 9,
      ocrText: String(repeating: "on-screen entity text ", count: 3),
      appName: "Safari",
      windowTitle: "Docs")
    var pending = await ScreenKnowledgeGraphExtractor.shared.pendingCount
    XCTAssertEqual(pending, 1)

    await ScreenKnowledgeGraphExtractor.shared.reset()
    pending = await ScreenKnowledgeGraphExtractor.shared.pendingCount
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
}

private actor LockedBox<T> {
  private(set) var value: T

  init(_ value: T) {
    self.value = value
  }

  func append(contentsOf elements: [Int64]) where T == [Int64] {
    value.append(contentsOf: elements)
  }

  func increment() where T == Int {
    value += 1
  }
}
