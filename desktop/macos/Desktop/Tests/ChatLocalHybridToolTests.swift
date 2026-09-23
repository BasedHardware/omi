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
    // Anchor relative to now: the tool searches a [now-7d, now] window, so a
    // fixed epoch fixture silently fell out of range after 2026-09-17.
    let started = Date().addingTimeInterval(-3_600)
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
    XCTAssertTrue(
      result.range(of: "\\d{4}", options: .regularExpression) != nil, result)
  }
}
