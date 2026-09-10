import Foundation

/// On-device embedding boundary. Implementations must not use a network provider.
enum LocalEmbeddingTask: Sendable { case document, query }

struct LocalEmbeddingCapabilities: Sendable {
  let assetsAvailable: Bool
  let requiresAppleSilicon: Bool
  let maxBatchSize: Int
}

protocol LocalEmbeddingService: Sendable {
  var engineID: String { get }
  var modelID: String { get }
  var dimension: Int { get }
  var capabilities: LocalEmbeddingCapabilities { get }
  func embed(_ texts: [String], task: LocalEmbeddingTask) async throws -> [[Float]]
}

struct LocalEmbeddingProbe: Sendable, Equatable {
  let appleSilicon: Bool
  let assetsAvailable: Bool
  let fixtureSucceeded: Bool
  let elapsed: Duration
  let dimension: Int

  // Exactly 32 whitespace-delimited tokens; synthetic, never user content.
  static let fixture =
    "The local search fixture describes a quiet morning reviewing a project plan with notes about design testing storage retrieval privacy and useful information saved on this computer for later recall and review"

  func permits(_ engine: any LocalEmbeddingService, budget: Duration) -> Bool {
    (!engine.capabilities.requiresAppleSilicon || appleSilicon)
      && assetsAvailable && fixtureSucceeded && elapsed <= budget
      && dimension > 0 && dimension == engine.dimension
      && !engine.modelID.isEmpty && engine.capabilities.maxBatchSize > 0
  }

  static func run(_ engine: any LocalEmbeddingService) async -> LocalEmbeddingProbe {
    #if arch(arm64)
      let silicon = true
    #else
      let silicon = false
    #endif
    let start = ContinuousClock.now
    guard engine.capabilities.assetsAvailable,
      !engine.capabilities.requiresAppleSilicon || silicon
    else {
      return Self(
        appleSilicon: silicon, assetsAvailable: engine.capabilities.assetsAvailable,
        fixtureSucceeded: false, elapsed: .zero, dimension: 0)
    }
    let vectors = try? await engine.embed([fixture], task: .document)
    let vector = vectors?.first ?? []
    return Self(
      appleSilicon: silicon, assetsAvailable: true,
      fixtureSucceeded: vectors?.count == 1 && valid(vector, dimension: engine.dimension),
      elapsed: start.duration(to: .now), dimension: vector.count)
  }

  static func valid(_ vector: [Float], dimension: Int) -> Bool {
    dimension > 0 && vector.count == dimension && vector.allSatisfy(\.isFinite)
      && vector.contains(where: { $0 != 0 })
  }
}
