import Accelerate
import Foundation
import NaturalLanguage

/// Apple on-device contextual embeddings (macOS 14+, OS-managed assets, no download in-app).
/// NaturalLanguage types stay inside this actor; they are not Sendable.
actor AppleNLContextualEmbeddingEngine: LocalEmbeddingService {
  nonisolated let engineID = "apple_nlce"
  nonisolated let modelID: String
  nonisolated let dimension: Int
  nonisolated let capabilities: LocalEmbeddingCapabilities

  private let maxSequenceLength: Int
  private let assetTimeout: Duration
  private let english: NLContextualEmbedding?
  private let multilingual: NLContextualEmbedding?
  private var requestedAssets = false
  private var loadedEnglish = false
  private var loadedMultilingual = false
  private let prepareOverride: (@Sendable () async -> LocalEmbeddingAssetStatus)?
  private let vectorsOverride: (@Sendable (String, Bool) throws -> [[Float]])?

  nonisolated static let defaultEngineID = "apple_nlce"
  static let shared = AppleNLContextualEmbeddingEngine()

  init(assetTimeout: Duration = .milliseconds(1500)) {
    let english = NLContextualEmbedding(language: .english)
    let multilingual = NLContextualEmbedding(script: .latin) ?? english
    self.english = english
    self.multilingual = multilingual
    self.modelID = english?.modelIdentifier ?? "nlce-en-mac14"
    self.dimension = Int(english?.dimension ?? 0)
    self.maxSequenceLength = max(1, Int(english?.maximumSequenceLength ?? 256))
    self.assetTimeout = assetTimeout
    self.capabilities = LocalEmbeddingCapabilities(
      assetsAvailable: english?.hasAvailableAssets == true,
      requiresAppleSilicon: false,
      maxBatchSize: 8)
    self.prepareOverride = nil
    self.vectorsOverride = nil
  }

  /// Test seam: deterministic pooling/chunking without NaturalLanguage assets.
  init(
    modelID: String,
    dimension: Int,
    maxSequenceLength: Int,
    assetTimeout: Duration = .milliseconds(1500),
    prepare: @escaping @Sendable () async -> LocalEmbeddingAssetStatus,
    tokenVectors: @escaping @Sendable (String, Bool) throws -> [[Float]]
  ) {
    self.english = nil
    self.multilingual = nil
    self.modelID = modelID
    self.dimension = dimension
    self.maxSequenceLength = max(1, maxSequenceLength)
    self.assetTimeout = assetTimeout
    self.capabilities = LocalEmbeddingCapabilities(
      assetsAvailable: false, requiresAppleSilicon: false, maxBatchSize: 8)
    self.prepareOverride = prepare
    self.vectorsOverride = tokenVectors
  }

  func prepareAssets() async -> LocalEmbeddingAssetStatus {
    if let prepareOverride {
      return await prepareOverride()
    }
    guard let english else { return .assetsUnavailable }
    if english.hasAvailableAssets { return .available }
    guard !requestedAssets else { return .assetsUnavailable }
    requestedAssets = true
    let timeout = assetTimeout
    let box = LocalEmbeddingAssetResume()
    let ready = await withCheckedContinuation { (continuation: CheckedContinuation<Bool, Never>) in
      english.requestAssets { result, _ in
        box.resume(continuation, result == .available)
      }
      Task {
        try? await Task.sleep(for: timeout)
        box.resume(continuation, false)
      }
    }
    return ready ? .available : .assetsUnavailable
  }

  func embed(_ texts: [String], task: LocalEmbeddingTask) async throws -> [[Float]] {
    var output: [[Float]] = []
    output.reserveCapacity(texts.count)
    for text in texts {
      try Task.checkCancellation()
      let englishDominant = Self.isEnglish(text)
      let tokens = try await tokenVectors(for: text, englishDominant: englishDominant)
      let pooled = Self.meanPoolNormalized(tokens)
      guard LocalEmbeddingProbe.valid(pooled, dimension: dimension) else {
        throw LocalInferenceError.invalidResponse("invalid local vector shape")
      }
      output.append(pooled)
    }
    return output
  }

  private func tokenVectors(for text: String, englishDominant: Bool) async throws -> [[Float]] {
    if let vectorsOverride {
      var collected: [[Float]] = []
      for chunk in Self.chunks(text, maxLength: maxSequenceLength) {
        collected.append(contentsOf: try vectorsOverride(chunk, englishDominant))
      }
      return collected
    }
    let status = await prepareAssets()
    guard status == .available else {
      throw LocalInferenceError.engineFailed("assets_unavailable")
    }
    guard let embedding = (englishDominant ? english : multilingual) ?? english else {
      throw LocalInferenceError.engineFailed("apple nlce missing")
    }
    try loadIfNeeded(embedding, englishDominant: englishDominant)
    var collected: [[Float]] = []
    for chunk in Self.chunks(text, maxLength: maxSequenceLength) {
      let language: NLLanguage? = englishDominant ? .english : nil
      let result = try embedding.embeddingResult(for: chunk, language: language)
      var tokenCount = 0
      result.enumerateTokenVectors(in: chunk.startIndex..<chunk.endIndex) { vector, _ in
        collected.append(vector.map { Float($0) })
        tokenCount += 1
        return true
      }
      if tokenCount == 0 {
        throw LocalInferenceError.invalidResponse("invalid local vector shape")
      }
    }
    return collected
  }

  private func loadIfNeeded(_ embedding: NLContextualEmbedding, englishDominant: Bool) throws {
    if englishDominant {
      guard !loadedEnglish else { return }
      try embedding.load()
      loadedEnglish = true
    } else {
      guard !loadedMultilingual else { return }
      try embedding.load()
      loadedMultilingual = true
    }
  }

  static func isEnglish(_ text: String) -> Bool {
    let recognizer = NLLanguageRecognizer()
    recognizer.processString(text)
    guard let language = recognizer.dominantLanguage else { return true }
    return language == .english || language == .undetermined
  }

  static func chunks(_ text: String, maxLength: Int) -> [String] {
    let trimmed = text.trimmingCharacters(in: .whitespacesAndNewlines)
    guard !trimmed.isEmpty else { return [""] }
    guard maxLength > 0, trimmed.count > maxLength else { return [trimmed] }
    var parts: [String] = []
    var index = trimmed.startIndex
    while index < trimmed.endIndex {
      let end = trimmed.index(index, offsetBy: maxLength, limitedBy: trimmed.endIndex) ?? trimmed.endIndex
      parts.append(String(trimmed[index..<end]))
      index = end
    }
    return parts
  }

  static func meanPoolNormalized(_ tokens: [[Float]]) -> [Float] {
    guard let width = tokens.first?.count, width > 0, tokens.allSatisfy({ $0.count == width }) else {
      return []
    }
    var acc = [Float](repeating: 0, count: width)
    var validCount: Float = 0
    for token in tokens {
      guard token.allSatisfy(\.isFinite) else { continue }
      vDSP_vadd(acc, 1, token, 1, &acc, 1, vDSP_Length(width))
      validCount += 1
    }
    guard validCount > 0 else { return [] }
    var scale = validCount
    vDSP_vsdiv(acc, 1, &scale, &acc, 1, vDSP_Length(width))
    var sumSquares: Float = 0
    vDSP_svesq(acc, 1, &sumSquares, vDSP_Length(width))
    let norm = sqrt(sumSquares)
    guard norm.isFinite, norm > 0 else { return [] }
    var divisor = norm
    vDSP_vsdiv(acc, 1, &divisor, &acc, 1, vDSP_Length(width))
    return acc
  }
}

/// Completes a bounded asset request exactly once. NaturalLanguage types stay on the engine actor.
private final class LocalEmbeddingAssetResume: @unchecked Sendable {
  private let lock = NSLock()
  private var resumed = false

  func resume(_ continuation: CheckedContinuation<Bool, Never>, _ value: Bool) {
    lock.lock()
    defer { lock.unlock() }
    guard !resumed else { return }
    resumed = true
    continuation.resume(returning: value)
  }
}
