import Accelerate
import Foundation

/// Actor-based service for embeddings using Gemini (3072-dim)
actor EmbeddingService {
  static let shared = EmbeddingService()

  /// Gemini embedding-001 outputs 3072 dimensions by default
  static let embeddingDimension = 3072
  static let modelName = "gemini-embedding-001"

  /// In-memory index: action_item.id -> normalized embedding
  private var index: [Int64: [Float]] = [:]
  private var isIndexLoaded = false

  /// Cap in-memory embeddings to limit memory (~12KB each, 5000 = ~60MB max)
  private let maxIndexSize = 5000

  /// Read GEMINI_API_KEY lazily from the C environment (set by loadEnvironment/setenv).
  /// ProcessInfo.processInfo.environment is a launch-time snapshot and misses keys
  /// loaded from .env files after startup.
  private var geminiApiKey: String? {
    if let cString = getenv("GEMINI_API_KEY") {
      return String(validatingUTF8: cString)
    }
    return nil
  }

  private init() {}

  // MARK: - Embedding API

  /// Generate embedding for a single text using Gemini (3072-dim)
  /// - Parameters:
  ///   - text: Text to embed
  ///   - taskType: Optional Gemini task type (e.g. "RETRIEVAL_DOCUMENT", "RETRIEVAL_QUERY")
  func embed(text: String, taskType: String? = nil) async throws -> [Float] {
    guard let apiKey = geminiApiKey else {
      throw EmbeddingError.missingAPIKey
    }

    let modelName = Self.modelName
    var requestBody: [String: Any] = [
      "model": "models/\(modelName)",
      "content": [
        "parts": [["text": text]]
      ],
    ]
    if let taskType = taskType {
      requestBody["taskType"] = taskType
    }

    let url = URL(
      string:
        "https://generativelanguage.googleapis.com/v1beta/models/\(modelName):embedContent?key=\(apiKey)"
    )!
    var request = URLRequest(url: url)
    request.httpMethod = "POST"
    request.setValue("application/json", forHTTPHeaderField: "Content-Type")
    request.timeoutInterval = 30
    request.httpBody = try JSONSerialization.data(withJSONObject: requestBody)

    let (data, _) = try await URLSession.shared.data(for: request)

    guard let json = try JSONSerialization.jsonObject(with: data) as? [String: Any],
      let embedding = json["embedding"] as? [String: Any],
      let values = embedding["values"] as? [Double]
    else {
      throw EmbeddingError.invalidResponse
    }

    let floats = values.map { Float($0) }
    return normalize(floats)
  }

  /// Batch embed multiple texts using Gemini (3072-dim, up to 100 per call)
  /// - Parameters:
  ///   - texts: Texts to embed
  ///   - taskType: Optional Gemini task type (e.g. "RETRIEVAL_DOCUMENT", "RETRIEVAL_QUERY")
  func embedBatch(texts: [String], taskType: String? = nil) async throws -> [[Float]] {
    guard let apiKey = geminiApiKey else {
      throw EmbeddingError.missingAPIKey
    }

    let modelName = Self.modelName
    let requests = texts.map { text in
      var req: [String: Any] = [
        "model": "models/\(modelName)",
        "content": [
          "parts": [["text": text]]
        ],
      ]
      if let taskType = taskType {
        req["taskType"] = taskType
      }
      return req
    }

    let requestBody: [String: Any] = ["requests": requests]

    let url = URL(
      string:
        "https://generativelanguage.googleapis.com/v1beta/models/\(modelName):batchEmbedContents?key=\(apiKey)"
    )!
    var request = URLRequest(url: url)
    request.httpMethod = "POST"
    request.setValue("application/json", forHTTPHeaderField: "Content-Type")
    request.timeoutInterval = 60
    request.httpBody = try JSONSerialization.data(withJSONObject: requestBody)

    let (data, _) = try await URLSession.shared.data(for: request)

    guard let json = try JSONSerialization.jsonObject(with: data) as? [String: Any],
      let embeddings = json["embeddings"] as? [[String: Any]]
    else {
      throw EmbeddingError.invalidResponse
    }

    return embeddings.compactMap { embedding in
      guard let values = embedding["values"] as? [Double] else { return nil }
      return normalize(values.map { Float($0) })
    }
  }

  // MARK: - In-Memory Index

  /// Load embeddings from SQLite into memory (action_items + staged_tasks, capped)
  func loadIndex() async {
    do {
      let rows = try await ActionItemStorage.shared.getAllEmbeddings()
      index.removeAll(keepingCapacity: true)
      // Only keep the most recent embeddings (suffix = highest IDs = newest)
      for (id, data) in rows.suffix(maxIndexSize) {
        if let floats = dataToFloats(data) {
          index[id] = floats
        }
      }
      let actionCount = index.count

      // Also load staged task embeddings (fill remaining capacity)
      let remaining = maxIndexSize - index.count
      if remaining > 0 {
        let stagedRows = try await StagedTaskStorage.shared.getAllEmbeddings()
        for (id, data) in stagedRows.suffix(remaining) {
          if let floats = dataToFloats(data) {
            index[id] = floats
          }
        }
      }

      isIndexLoaded = true
      log(
        "EmbeddingService: Loaded \(index.count) embeddings into memory (\(actionCount) action_items, \(index.count - actionCount) staged_tasks, cap=\(maxIndexSize))"
      )
    } catch {
      logError("EmbeddingService: Failed to load index", error: error)
    }
  }

  /// Add a single embedding to the in-memory index (respects maxIndexSize)
  func addToIndex(id: Int64, embedding: [Float]) {
    // If at capacity and this is a new key, evict the oldest (lowest ID)
    if index[id] == nil && index.count >= maxIndexSize {
      if let oldestKey = index.keys.min() {
        index.removeValue(forKey: oldestKey)
      }
    }
    index[id] = embedding
  }

  /// Remove an entry from the index
  func removeFromIndex(id: Int64) {
    index.removeValue(forKey: id)
  }

  /// Search for similar items using cosine similarity via Accelerate/vDSP
  func searchSimilar(query: [Float], topK: Int = 10) -> [(id: Int64, similarity: Float)] {
    guard !index.isEmpty else { return [] }

    var results: [(id: Int64, similarity: Float)] = []
    results.reserveCapacity(index.count)

    for (id, stored) in index {
      let sim = cosineSimilarity(query, stored)
      results.append((id, sim))
    }

    // Sort descending by similarity and take topK
    results.sort { $0.similarity > $1.similarity }
    return Array(results.prefix(topK))
  }

  /// Whether the index has been loaded
  var indexLoaded: Bool { isIndexLoaded }

  /// Number of items in the index
  var indexSize: Int { index.count }

  // MARK: - Backfill

  /// Batch-embed all tasks missing embeddings (action_items + staged_tasks)
  func backfillIfNeeded() async {
    let batchSize = 100
    var totalProcessed = 0

    do {
      // Backfill action_items
      while true {
        let items = try await ActionItemStorage.shared.getItemsMissingEmbeddings(limit: batchSize)
        if items.isEmpty { break }

        let texts = items.map { $0.description }
        let embeddings = try await embedBatch(texts: texts)

        for (i, embedding) in embeddings.enumerated() where i < items.count {
          let item = items[i]
          let data = floatsToData(embedding)
          try await ActionItemStorage.shared.updateEmbedding(id: item.id, embedding: data)
          addToIndex(id: item.id, embedding: embedding)
        }

        totalProcessed += items.count
        log("EmbeddingService: Backfill progress: \(totalProcessed) action_items")

        // Small delay to avoid rate limiting
        try await Task.sleep(nanoseconds: 200_000_000)  // 200ms
      }

      // Backfill staged_tasks
      while true {
        let items = try await StagedTaskStorage.shared.getItemsMissingEmbeddings(limit: batchSize)
        if items.isEmpty { break }

        let texts = items.map { $0.description }
        let embeddings = try await embedBatch(texts: texts)

        for (i, embedding) in embeddings.enumerated() where i < items.count {
          let item = items[i]
          let data = floatsToData(embedding)
          try await StagedTaskStorage.shared.updateEmbedding(id: item.id, embedding: data)
          addToIndex(id: item.id, embedding: embedding)
        }

        totalProcessed += items.count
        log("EmbeddingService: Backfill progress: \(totalProcessed) total (incl. staged)")

        try await Task.sleep(nanoseconds: 200_000_000)  // 200ms
      }

      if totalProcessed > 0 {
        log("EmbeddingService: Backfill complete — \(totalProcessed) items embedded")
      }
    } catch {
      logError("EmbeddingService: Backfill failed after \(totalProcessed) items", error: error)
    }
  }

  // MARK: - Helpers

  /// Cosine similarity using Accelerate vDSP for performance
  private func cosineSimilarity(_ a: [Float], _ b: [Float]) -> Float {
    guard a.count == b.count, !a.isEmpty else { return 0 }
    var dot: Float = 0
    vDSP_dotpr(a, 1, b, 1, &dot, vDSP_Length(a.count))
    // Vectors are pre-normalized, so dot product = cosine similarity
    return dot
  }

  /// Normalize a vector to unit length
  private func normalize(_ vector: [Float]) -> [Float] {
    var norm: Float = 0
    vDSP_svesq(vector, 1, &norm, vDSP_Length(vector.count))
    norm = sqrt(norm)
    guard norm > 0 else { return vector }
    var result = [Float](repeating: 0, count: vector.count)
    var divisor = norm
    vDSP_vsdiv(vector, 1, &divisor, &result, 1, vDSP_Length(vector.count))
    return result
  }

  /// Convert [Float] to Data (for SQLite BLOB storage)
  func floatsToData(_ floats: [Float]) -> Data {
    return floats.withUnsafeBufferPointer { buffer in
      Data(buffer: buffer)
    }
  }

  /// Convert Data (BLOB) back to [Float] (expects 3072-dim Gemini embeddings)
  func dataToFloats(_ data: Data) -> [Float]? {
    let floatSize = MemoryLayout<Float>.size
    let floatCount = data.count / floatSize

    guard floatCount == Self.embeddingDimension else {
      return nil
    }

    return data.withUnsafeBytes { raw in
      Array(raw.bindMemory(to: Float.self))
    }
  }

  // MARK: - Errors

  enum EmbeddingError: LocalizedError {
    case missingAPIKey
    case invalidResponse

    var errorDescription: String? {
      switch self {
      case .missingAPIKey: return "AI features are not configured. Please update the app."
      case .invalidResponse: return "AI service returned an unexpected response. Please try again."
      }
    }
  }
}
