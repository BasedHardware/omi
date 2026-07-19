import XCTest

@testable import Omi_Computer

/// Regression test for the embedding-index rowid collision: `action_items` and
/// `staged_tasks` are separate tables whose autoincrement rowids both start at 1.
/// The old index was keyed by raw `Int64`, so a staged task and an action item
/// with the same id overwrote each other, and search results resolved to the
/// wrong table (the two consumers even guessed in opposite orders). The index is
/// now keyed by (source, id), so colliding ids coexist and resolve deterministically.
final class EmbeddingIndexSourceTests: XCTestCase {

  /// A 3072-dim one-hot unit vector (matches Gemini's embedding dimension).
  private func oneHot(_ index: Int) -> [Float] {
    var v = [Float](repeating: 0, count: EmbeddingService.embeddingDimension)
    v[index] = 1
    return v
  }

  private let collidingID: Int64 = 987_654_321

  override func tearDown() async throws {
    // Clean up the shared singleton's index so we don't leak into other tests.
    await EmbeddingService.shared.removeFromIndex(source: .actionItem, id: collidingID)
    await EmbeddingService.shared.removeFromIndex(source: .staged, id: collidingID)
    try await super.tearDown()
  }

  func testSameRowidDifferentSourceDoNotOverwrite() async {
    let svc = EmbeddingService.shared
    let sizeBefore = await svc.indexSize

    // Same rowid, different source — the classic collision.
    await svc.addToIndex(source: .actionItem, id: collidingID, embedding: oneHot(0))
    await svc.addToIndex(source: .staged, id: collidingID, embedding: oneHot(1))

    let sizeAfter = await svc.indexSize
    XCTAssertEqual(
      sizeAfter - sizeBefore, 2,
      "colliding action_item/staged rowids must coexist, not overwrite")
  }

  func testSearchResolvesToTheCorrectSource() async {
    let svc = EmbeddingService.shared
    let actionVec = oneHot(0)
    let stagedVec = oneHot(1)  // orthogonal to actionVec

    await svc.addToIndex(source: .actionItem, id: collidingID, embedding: actionVec)
    await svc.addToIndex(source: .staged, id: collidingID, embedding: stagedVec)

    // Querying with the action_item's own vector must surface the action_item
    // entry for this id (similarity 1.0) ahead of the staged one (similarity 0).
    let byAction = await svc.searchSimilar(query: actionVec, topK: EmbeddingService.embeddingDimension)
    XCTAssertEqual(byAction.first { $0.id == collidingID }?.source, .actionItem)

    let byStaged = await svc.searchSimilar(query: stagedVec, topK: EmbeddingService.embeddingDimension)
    XCTAssertEqual(byStaged.first { $0.id == collidingID }?.source, .staged)
  }
}
