import XCTest

@testable import Omi_Computer

/// The atlas snapshot is built inside a SwiftUI `init`, so it is memoized. A
/// memo is only safe if its key covers everything the layout reads — a key that
/// misses something serves back the previous map and looks exactly like a
/// rebuild that silently did nothing.
final class MemoryAtlasSnapshotCacheTests: XCTestCase {
  private var cache: MemoryAtlasSnapshotCache { MemoryAtlasSnapshotCache.shared }

  override func setUp() {
    super.setUp()
    cache.resetForTesting()
  }

  override func tearDown() {
    cache.resetForTesting()
    super.tearDown()
  }

  func testAnUnchangedGraphIsLaidOutOnce() {
    let graph = makeGraph(memoryIDsByNode: ["a": ["m1"], "b": ["m1"]])

    let first = cache.snapshot(for: graph, userName: "David")
    let second = cache.snapshot(for: graph, userName: "David")

    XCTAssertEqual(cache.computeCount, 1)
    XCTAssertEqual(cache.reuseCount, 1)
    XCTAssertEqual(first.nodes.map(\.normalizedPosition), second.nodes.map(\.normalizedPosition))
  }

  /// The defect this test exists for: relatedness comes from *which* memories
  /// two entities share, so swapping one memory for another rearranges the map
  /// while leaving every count — and every timestamp — untouched.
  func testSwappingAMemoryForAnotherIsNotServedFromTheMemo() {
    let before = makeGraph(memoryIDsByNode: ["a": ["m1"], "b": ["m1"]])
    let after = makeGraph(memoryIDsByNode: ["a": ["m2"], "b": ["m1"]])

    _ = cache.snapshot(for: before, userName: "David")
    _ = cache.snapshot(for: after, userName: "David")

    XCTAssertEqual(cache.computeCount, 2, "Same counts, different memories, different map")
    XCTAssertEqual(cache.reuseCount, 0)
  }

  func testTheAnchorsNameIsPartOfTheKey() {
    let graph = makeGraph(memoryIDsByNode: ["a": ["m1"], "b": ["m1"]])

    _ = cache.snapshot(for: graph, userName: "David")
    _ = cache.snapshot(for: graph, userName: "Someone Else")

    XCTAssertEqual(cache.computeCount, 2)
  }

  private func makeGraph(memoryIDsByNode: [String: [String]]) -> KnowledgeGraphResponse {
    let nodes = memoryIDsByNode.keys.sorted().map { id in
      KnowledgeGraphNode(
        id: id,
        label: id.uppercased(),
        nodeType: .concept,
        memoryIds: memoryIDsByNode[id] ?? [],
        createdAt: Date(timeIntervalSince1970: 1),
        updatedAt: Date(timeIntervalSince1970: 2))
    }
    return KnowledgeGraphResponse(nodes: nodes, edges: [])
  }
}
