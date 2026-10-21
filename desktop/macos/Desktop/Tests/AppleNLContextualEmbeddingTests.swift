import Foundation
import XCTest

@testable import Omi_Computer

@MainActor
final class AppleNLContextualEmbeddingTests: XCTestCase {
  func testSystemEngineProbeReportsAssetsUnavailableOrEmbeds() async throws {
    let engine = AppleNLContextualEmbeddingEngine()
    let probe = await LocalEmbeddingProbe.run(engine)
    if probe.reason == LocalEmbeddingAssetStatus.assetsUnavailable.rawValue {
      XCTAssertFalse(probe.assetsAvailable)
      XCTAssertFalse(probe.permits(engine, budget: .seconds(2)))
      return
    }
    guard probe.reason.isEmpty else { return }
    XCTAssertTrue(probe.permits(engine, budget: .seconds(2)))
    let vectors = try await engine.embed(["hello local retrieval fixture"], task: .document)
    XCTAssertEqual(vectors.count, 1)
    XCTAssertEqual(vectors[0].count, engine.dimension)
    XCTAssertTrue(LocalEmbeddingProbe.valid(vectors[0], dimension: engine.dimension))
  }

  func testMeanPoolIsL2NormalizedAndChunksLongInput() async throws {
    let tokenA: [Float] = [3, 0, 0, 0]
    let tokenB: [Float] = [0, 3, 0, 0]
    let engine = AppleNLContextualEmbeddingEngine(
      modelID: "fixture-nlce",
      dimension: 4,
      maxSequenceLength: 4,
      prepare: { _ in .available },
      tokenVectors: { text, _ in
        XCTAssertLessThanOrEqual(text.count, 4)
        return [tokenA, tokenB]
      })
    XCTAssertEqual(AppleNLContextualEmbeddingEngine.chunks("abcdefgh", maxLength: 4), ["abcd", "efgh"])
    let pooled = AppleNLContextualEmbeddingEngine.meanPoolNormalized([tokenA, tokenB])
    XCTAssertEqual(pooled.count, 4)
    let norm = sqrt(pooled.reduce(Float(0)) { $0 + $1 * $1 })
    XCTAssertEqual(norm, 1, accuracy: 0.0001)
    let vectors = try await engine.embed(["abcdefghij"], task: .document)
    XCTAssertEqual(vectors.count, 1)
    XCTAssertEqual(vectors[0].count, 4)
    XCTAssertTrue(LocalEmbeddingProbe.valid(vectors[0], dimension: 4))
  }

  func testFixtureAssetsUnavailableDoesNotEmbed() async {
    let engine = AppleNLContextualEmbeddingEngine(
      modelID: "fixture-nlce",
      dimension: 4,
      maxSequenceLength: 8,
      prepare: { _ in .assetsUnavailable },
      tokenVectors: { _, _ in
        XCTFail("unavailable assets must not embed")
        return []
      })
    let probe = await LocalEmbeddingProbe.run(engine)
    XCTAssertEqual(probe.reason, LocalEmbeddingAssetStatus.assetsUnavailable.rawValue)
    XCTAssertFalse(probe.permits(engine, budget: .seconds(2)))
  }

  func testNonEnglishEmbedRequestsSelectedModelAssets() async throws {
    let requested = AssetLanguageBox()
    let engine = AppleNLContextualEmbeddingEngine(
      modelID: "fixture-nlce",
      dimension: 4,
      maxSequenceLength: 64,
      prepare: { englishDominant in
        requested.append(englishDominant)
        return .available
      },
      tokenVectors: { _, _ in [[1, 0, 0, 0]] })
    let status = await engine.prepareAssets(englishDominant: false)
    XCTAssertEqual(status, .available)
    XCTAssertEqual(requested.snapshot(), [false])
    _ = try await engine.embed(
      ["Bonjour le monde, aujourd'hui nous parlons uniquement en français pendant toute cette phrase."],
      task: .document)
    XCTAssertFalse(requested.snapshot().isEmpty)
  }
}

private final class AssetLanguageBox: @unchecked Sendable {
  private let lock = NSLock()
  private var values: [Bool] = []
  func append(_ value: Bool) {
    lock.lock()
    values.append(value)
    lock.unlock()
  }
  func snapshot() -> [Bool] {
    lock.lock()
    defer { lock.unlock() }
    return values
  }
}
