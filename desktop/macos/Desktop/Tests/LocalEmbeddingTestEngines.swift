import CryptoKit
import Foundation
import XCTest

@testable import Omi_Computer

/// Deterministic synthetic engine, compiled only into the test target.
struct HashEmbeddingEngine: LocalEmbeddingService {
  let engineID = "test_hash"
  var modelID = "test-hash-v1"
  let dimension = 8
  let capabilities = LocalEmbeddingCapabilities(assetsAvailable: true, requiresAppleSilicon: false, maxBatchSize: 32)

  func embed(_ texts: [String], task: LocalEmbeddingTask) async throws -> [[Float]] {
    texts.map { text in
      Array(SHA256.hash(data: Data(text.utf8)).prefix(dimension)).map { Float($0) + 1 }
    }
  }
}

struct ForbiddenEmbeddingHTTPClient: LocalInferenceHTTPClient {
  func send(_ request: URLRequest) async throws -> (Data, URLResponse) {
    XCTFail("local runtime invoked HTTP")
    throw LocalInferenceError.engineFailed("HTTP is forbidden")
  }
}

struct HTTPTrapEmbeddingEngine: LocalEmbeddingService {
  let engineID = "http-trap"
  let modelID = "http-trap"
  let dimension = 8
  let capabilities = LocalEmbeddingCapabilities(assetsAvailable: true, requiresAppleSilicon: false, maxBatchSize: 1)
  let client: any LocalInferenceHTTPClient
  func embed(_ texts: [String], task: LocalEmbeddingTask) async throws -> [[Float]] {
    _ = try await client.send(URLRequest(url: URL(fileURLWithPath: "/forbidden-http")))
    return []
  }
}

struct FailingQueryEmbeddingEngine: LocalEmbeddingService {
  let base = HashEmbeddingEngine()
  var engineID: String { base.engineID }
  var modelID: String { base.modelID }
  var dimension: Int { base.dimension }
  var capabilities: LocalEmbeddingCapabilities { base.capabilities }
  func embed(_ texts: [String], task: LocalEmbeddingTask) async throws -> [[Float]] {
    if case .query = task { throw LocalInferenceError.engineFailed("synthetic") }
    return try await base.embed(texts, task: task)
  }
}
