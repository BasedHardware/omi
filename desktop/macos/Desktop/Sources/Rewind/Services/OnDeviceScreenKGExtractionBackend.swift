import Foundation

/// On-device screen→KG extraction via Apple Foundation Models when available.
/// Falls back to `GeminiProxyScreenKGBackend` via `ScreenKGExtractionBackendSelector`.
///
/// Privacy: OCR text stays on-device; no image data is ever passed to this backend.
enum OnDeviceScreenKGExtractionBackend {
  static var isAvailable: Bool {
    #if canImport(FoundationModels)
      if #available(macOS 26.0, *) {
        return FoundationModelsScreenKGAvailability.isModelAvailable
      }
    #endif
    return false
  }

  static let shared: any ScreenKGExtractionBackend = {
    #if canImport(FoundationModels)
      if #available(macOS 26.0, *) {
        return FoundationModelsScreenKGBackend()
      }
    #endif
    return UnavailableOnDeviceScreenKGBackend()
  }()
}

#if canImport(FoundationModels)
  import FoundationModels

  @available(macOS 26.0, *)
  private enum FoundationModelsScreenKGAvailability {
    static var isModelAvailable: Bool {
      SystemLanguageModel.default.isAvailable
    }
  }

  @available(macOS 26.0, *)
  private struct FoundationModelsScreenKGBackend: ScreenKGExtractionBackend {
    let name = "foundation_models"

    func extractEntities(from input: ScreenKGExtractionInput) async throws -> String {
      let session = LanguageModelSession(instructions: ScreenKGExtractionPrompt.systemPrompt)
      let prompt = ScreenKGExtractionPrompt.userPrompt(for: input)
      let response = try await session.respond(to: prompt)
      let text = response.content.trimmingCharacters(in: .whitespacesAndNewlines)
      guard KnowledgeGraphRecordBuilder.parseExtractionJSON(text) != nil else {
        throw ScreenKGExtractionError.invalidStructuredOutput
      }
      return text
    }
  }
#endif

private struct UnavailableOnDeviceScreenKGBackend: ScreenKGExtractionBackend {
  let name = "on_device_unavailable"

  func extractEntities(from input: ScreenKGExtractionInput) async throws -> String {
    throw ScreenKGExtractionError.onDeviceUnavailable
  }
}

enum ScreenKGExtractionError: Error {
  case onDeviceUnavailable
  case invalidStructuredOutput
}
