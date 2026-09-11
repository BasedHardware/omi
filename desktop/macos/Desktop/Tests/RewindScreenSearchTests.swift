import Foundation
import XCTest

@testable import Omi_Computer

private final class CallCounter: @unchecked Sendable {
  var count = 0
  func increment() { count += 1 }
}

@MainActor
final class RewindScreenSearchTests: XCTestCase {
  func testFreePlanRewindSearchNeverInvokesGemini() async throws {
    let engine = HashEmbeddingEngine()
    let runtime = LocalEmbeddingRuntime(
      engines: [engine], defaultEngineID: engine.engineID, record: { _, _ in })
    let policy = ScreenEmbeddingPolicy(
      plan: .basic, status: .active, localRoute: .engine(engine), killSwitches: .enabled)
    let hit = LocalHybridHit(
      sourceKind: .screenshot, sourceId: 7, fusedScore: 0.9, matchedBy: .both,
      capturedAt: Date(timeIntervalSince1970: 1_789_000_000), appName: "Editor")
    let screenshot = Screenshot(
      id: 7, timestamp: Date(timeIntervalSince1970: 1_789_000_000), appName: "Editor",
      windowTitle: "Plan", ocrText: "budget review")
    let geminiCalls = CallCounter()
    let localCalls = CallCounter()
    var dependencies = RewindScreenSearch.Dependencies(
      runtime: runtime, policy: policy, defaults: nil)
    dependencies.gemini = { _, _ in
      geminiCalls.increment()
      XCTFail("free Rewind search must not embed the query with Gemini")
      return [(99, 0.99)]
    }
    dependencies.fts = { _, _ in
      XCTFail("free local route must not take the Gemini FTS merge")
      return []
    }
    dependencies.localHits = { _, _, selected in
      localCalls.increment()
      XCTAssertNotNil(selected)
      return [hit]
    }
    dependencies.screenshot = { id in
      XCTAssertEqual(id, 7)
      return screenshot
    }
    let results = try await RewindScreenSearch.search(query: "budget", appFilter: nil, dependencies: dependencies)
    XCTAssertEqual(geminiCalls.count, 0)
    XCTAssertEqual(localCalls.count, 1)
    XCTAssertEqual(results.compactMap(\.id), [7])
  }

  func testPaidHardKillRewindSearchKeepsFTSThenGeminiOrdering() async throws {
    let runtime = LocalEmbeddingRuntime(
      engines: [],
      killSwitches: LocalEmbeddingKillSwitches(isDisabled: true, forcedEngineRaw: nil), record: { _, _ in })
    let fts = Screenshot(
      id: 1, timestamp: Date(timeIntervalSince1970: 1), appName: "Editor", ocrText: "budget")
    let vectorOnly = Screenshot(
      id: 2, timestamp: Date(timeIntervalSince1970: 2), appName: "Editor", ocrText: "related")
    let geminiCalls = CallCounter()
    var dependencies = RewindScreenSearch.Dependencies(runtime: runtime, defaults: nil)
    dependencies.fts = { query, app in
      XCTAssertEqual(query, "budget")
      XCTAssertEqual(app, "Editor")
      return [fts]
    }
    dependencies.gemini = { query, app in
      geminiCalls.increment()
      XCTAssertEqual(query, "budget")
      XCTAssertEqual(app, "Editor")
      return [(1, 0.9), (2, 0.6), (3, 0.4)]
    }
    dependencies.screenshot = { id in
      XCTAssertEqual(id, 2)
      return vectorOnly
    }
    dependencies.localHits = { _, _, _ in
      XCTFail("hard kill must not use the local index")
      return []
    }
    let results = try await RewindScreenSearch.search(
      query: "budget", appFilter: "Editor", dependencies: dependencies)
    XCTAssertEqual(geminiCalls.count, 1)
    XCTAssertEqual(results.compactMap(\.id), [1, 2])
  }
}
