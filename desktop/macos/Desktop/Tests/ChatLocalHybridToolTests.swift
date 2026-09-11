import Foundation
import XCTest

@testable import Omi_Computer

@MainActor
final class ChatLocalHybridToolTests: XCTestCase {
  private var userDir: URL?

  override func setUp() async throws {
    let fixture = try await RewindStorageTestIsolation.setUp(userIdPrefix: "local-hybrid-tool")
    userDir = fixture.userDir
  }

  override func tearDown() async throws {
    await LocalEmbeddingIndexer.shared.drainForTesting()
    await RewindStorageTestIsolation.tearDown(userDir: userDir)
  }

  func testTranscriptHitsIncludeBoundedTextAndTimestamp() async throws {
    guard let owner = RewindCaptureOwnerSnapshot.capture(), owner.isCurrent() else {
      return XCTFail("owner required")
    }
    let store = try await RewindDatabase.shared.localEmbeddingStore(owner: owner)
    let sessionId = try await TranscriptionStorage.shared.startSession(source: "desktop")
    let started = Date(timeIntervalSince1970: 1_789_000_000)
    let text = "northwind ledger review on the call"
    _ = try await store.upsertTranscriptChunks(
      [
        TranscriptChunkRecord(
          id: nil, sessionId: sessionId, chunkIndex: 0, text: text,
          textSha256: LocalEmbeddingStore.textHash(text), startedAt: started)
      ], authorization: .unrestricted)
    let runtime = LocalEmbeddingRuntime(engines: [], record: { _, _ in })
    let result = await ChatLocalHybridTool.execute(
      ["query": "northwind"], runID: nil, attemptID: nil, expectedOwnerID: nil,
      sourceKinds: [.transcriptChunk], runtime: runtime)
    XCTAssertTrue(result.contains("northwind ledger review on the call"), result)
    XCTAssertTrue(result.contains("Content:"), result)
    XCTAssertTrue(result.contains("2026"), result)
  }
}
