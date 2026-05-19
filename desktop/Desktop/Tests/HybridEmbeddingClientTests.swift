import XCTest

@testable import Omi_Computer

final class HybridEmbeddingClientTests: XCTestCase {
  func testLoadProviderConfigParsesOpenAICompatible() {
    let settings = [
      LocalDaemonSetting(
        key: "embedding_provider",
        valueJson: """
          {"kind":"openai_compatible","base_url":"http://127.0.0.1:11434/v1","model":"nomic-embed-text","api_key":"k"}
          """,
        updatedAt: Date()
      )
    ]
    let config = HybridEmbeddingClient.loadProviderConfig(from: settings)
    XCTAssertEqual(config?.baseURL, "http://127.0.0.1:11434/v1")
    XCTAssertEqual(config?.model, "nomic-embed-text")
  }

  func testCompatibilityRejectsMixedDimensions() {
    XCTAssertFalse(
      HybridEmbeddingClient.isCompatibleEmbedding(
        storedModel: "nomic-embed-text",
        storedDim: 768,
        activeModel: "nomic-embed-text",
        activeDim: 384
      )
    )
    XCTAssertTrue(
      HybridEmbeddingClient.isCompatibleEmbedding(
        storedModel: nil,
        storedDim: nil,
        activeModel: HybridEmbeddingClient.legacyGeminiModelId,
        activeDim: HybridEmbeddingClient.legacyGeminiDimension
      )
    )
  }
}
