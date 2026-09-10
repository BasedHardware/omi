import Foundation

/// On-device embedding boundary. Implementations must not use a network provider.
enum LocalEmbeddingTask: Sendable { case document, query }

enum LocalEmbeddingAssetStatus: String, Sendable, Equatable {
  case available
  case assetsUnavailable = "assets_unavailable"
}

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
  func prepareAssets() async -> LocalEmbeddingAssetStatus
}

extension LocalEmbeddingService {
  func prepareAssets() async -> LocalEmbeddingAssetStatus {
    capabilities.assetsAvailable ? .available : .assetsUnavailable
  }
}

struct LocalEmbeddingProbe: Sendable, Equatable {
  let appleSilicon: Bool
  let assetsAvailable: Bool
  let fixtureSucceeded: Bool
  let elapsed: Duration
  let dimension: Int
  let reason: String

  // Exactly 32 whitespace-delimited tokens; synthetic, never user content.
  static let fixture =
    "The local search fixture describes a quiet morning reviewing a project plan with notes about design testing storage retrieval privacy and useful information saved on this computer for later recall and review"

  init(
    appleSilicon: Bool,
    assetsAvailable: Bool,
    fixtureSucceeded: Bool,
    elapsed: Duration,
    dimension: Int,
    reason: String = ""
  ) {
    self.appleSilicon = appleSilicon
    self.assetsAvailable = assetsAvailable
    self.fixtureSucceeded = fixtureSucceeded
    self.elapsed = elapsed
    self.dimension = dimension
    self.reason = reason
  }

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
    let assetStatus = await engine.prepareAssets()
    guard assetStatus == .available, !engine.capabilities.requiresAppleSilicon || silicon else {
      return Self(
        appleSilicon: silicon,
        assetsAvailable: assetStatus == .available,
        fixtureSucceeded: false,
        elapsed: start.duration(to: .now),
        dimension: 0,
        reason: assetStatus == .available ? "capability_mismatch" : assetStatus.rawValue)
    }
    let vectors = try? await engine.embed([fixture], task: .document)
    let vector = vectors?.first ?? []
    let succeeded = vectors?.count == 1 && valid(vector, dimension: engine.dimension)
    return Self(
      appleSilicon: silicon, assetsAvailable: true,
      fixtureSucceeded: succeeded, elapsed: start.duration(to: .now), dimension: vector.count,
      reason: succeeded ? "" : "fixture_failed")
  }

  static func valid(_ vector: [Float], dimension: Int) -> Bool {
    dimension > 0 && vector.count == dimension && vector.allSatisfy(\.isFinite)
      && vector.contains(where: { $0 != 0 })
  }
}
