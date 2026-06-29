import Foundation

struct SpatialOverlayDesktopSnapshot: Equatable {
  let screens: [SpatialOverlayScreen]
  let windows: [SpatialOverlayWindow]
  let candidates: [SpatialOverlayAnchorCandidate]

  init(
    screens: [SpatialOverlayScreen],
    windows: [SpatialOverlayWindow] = [],
    candidates: [SpatialOverlayAnchorCandidate] = []
  ) {
    self.screens = screens
    self.windows = windows
    self.candidates = candidates
  }
}

struct SpatialOverlayAnchorSpec: Equatable {
  let id: String
  let use: SpatialOverlayAnchorUse
  let minimumConfidence: Double
  let preferredSources: [SpatialOverlayTargetSource]

  init(
    id: String,
    use: SpatialOverlayAnchorUse,
    minimumConfidence: Double,
    preferredSources: [SpatialOverlayTargetSource] = [
      .accessibility,
      .ocr,
      .semanticState,
      .layoutHeuristic,
      .fixedScreenAnchor,
      .appWindow,
      .cgWindowList,
    ]
  ) {
    self.id = id
    self.use = use
    self.minimumConfidence = minimumConfidence
    self.preferredSources = preferredSources
  }
}

struct SpatialOverlayAnchorResolution: Equatable {
  let spec: SpatialOverlayAnchorSpec
  let candidate: SpatialOverlayAnchorCandidate
}

enum SpatialOverlayResolutionFailure: Error, Equatable, CustomStringConvertible {
  case noCandidates
  case noCandidateAllowedForUse(SpatialOverlayAnchorUse)
  case belowConfidenceThreshold(required: Double, best: Double)

  var description: String {
    switch self {
    case .noCandidates:
      return "No anchor candidates were available"
    case .noCandidateAllowedForUse(let use):
      return "No anchor candidate is allowed for \(use)"
    case .belowConfidenceThreshold(let required, let best):
      return "Best anchor confidence \(best) is below required threshold \(required)"
    }
  }
}

protocol SpatialOverlayTargetProvider {
  func candidates(in snapshot: SpatialOverlayDesktopSnapshot, for spec: SpatialOverlayAnchorSpec)
    -> [SpatialOverlayAnchorCandidate]
}

struct SpatialOverlayStaticTargetProvider: SpatialOverlayTargetProvider {
  func candidates(in snapshot: SpatialOverlayDesktopSnapshot, for spec: SpatialOverlayAnchorSpec)
    -> [SpatialOverlayAnchorCandidate]
  {
    snapshot.candidates.filter { candidateMatches($0, spec: spec) }
  }

  private func candidateMatches(
    _ candidate: SpatialOverlayAnchorCandidate, spec: SpatialOverlayAnchorSpec
  )
    -> Bool
  {
    let specTokens = Set(
      spec.id
        .split(separator: ".")
        .map(String.init)
        .filter { token in
          !["claude", "chatgpt", "guidance", "click", "display", "perform", "anchor", "target"]
            .contains(token)
        })
    guard !specTokens.isEmpty else { return true }

    let searchable =
      ([candidate.id]
      + candidate.evidence.flatMap { evidence in
        [evidence.label ?? ""] + evidence.diagnostics
      })
      .joined(separator: " ")
      .lowercased()

    return specTokens.contains { searchable.contains($0.lowercased()) }
  }
}

struct SpatialOverlayAnchorResolver {
  let providers: [SpatialOverlayTargetProvider]

  init(providers: [SpatialOverlayTargetProvider] = [SpatialOverlayStaticTargetProvider()]) {
    self.providers = providers
  }

  func resolve(
    _ spec: SpatialOverlayAnchorSpec,
    in snapshot: SpatialOverlayDesktopSnapshot
  ) -> Result<SpatialOverlayAnchorResolution, SpatialOverlayResolutionFailure> {
    let candidates = providers.flatMap { $0.candidates(in: snapshot, for: spec) }
    guard !candidates.isEmpty else {
      return .failure(.noCandidates)
    }

    let allowed = candidates.filter { candidateIsAllowed($0, for: spec.use) }
    guard !allowed.isEmpty else {
      return .failure(.noCandidateAllowedForUse(spec.use))
    }

    let confident = allowed.filter { $0.confidence >= spec.minimumConfidence }
    guard !confident.isEmpty else {
      let bestConfidence = allowed.map(\.confidence).max() ?? 0
      return .failure(
        .belowConfidenceThreshold(required: spec.minimumConfidence, best: bestConfidence))
    }

    let ranked = confident.sorted { lhs, rhs in
      let lhsRank = sourceRank(lhs, spec: spec)
      let rhsRank = sourceRank(rhs, spec: spec)
      if lhsRank != rhsRank {
        return lhsRank < rhsRank
      }
      if lhs.confidence != rhs.confidence {
        return lhs.confidence > rhs.confidence
      }
      return lhs.id < rhs.id
    }

    guard let best = ranked.first else {
      return .failure(.noCandidates)
    }

    return .success(SpatialOverlayAnchorResolution(spec: spec, candidate: best))
  }

  private func sourceRank(
    _ candidate: SpatialOverlayAnchorCandidate, spec: SpatialOverlayAnchorSpec
  )
    -> Int
  {
    let sources = candidate.evidence.map(\.source)
    return spec.preferredSources.enumerated().compactMap { index, source in
      sources.contains(source) ? index : nil
    }.min() ?? spec.preferredSources.count
  }

  private func candidateIsAllowed(
    _ candidate: SpatialOverlayAnchorCandidate,
    for use: SpatialOverlayAnchorUse
  ) -> Bool {
    guard candidate.allowedUses.contains(use) else { return false }
    guard use == .performClick else { return true }
    return candidate.evidence.contains { $0.source == .accessibility || $0.source == .ocr }
  }
}

struct SpatialOverlayReplayFixture: Equatable {
  let id: String
  let snapshot: SpatialOverlayDesktopSnapshot
  let placementSpec: SpatialOverlayPlacementSpec

  init(
    id: String,
    snapshot: SpatialOverlayDesktopSnapshot,
    placementSpec: SpatialOverlayPlacementSpec
  ) {
    self.id = id
    self.snapshot = snapshot
    self.placementSpec = placementSpec
  }

  func place(_ anchorSpec: SpatialOverlayAnchorSpec)
    -> Result<SpatialOverlayPlacementResult, Error>
  {
    let resolver = SpatialOverlayAnchorResolver()
    switch resolver.resolve(anchorSpec, in: snapshot) {
    case .success(let resolution):
      switch SpatialOverlayPlacementSolver.place(target: resolution.candidate, spec: placementSpec)
      {
      case .success(let placement):
        return .success(placement)
      case .failure(let failure):
        return .failure(failure)
      }
    case .failure(let failure):
      return .failure(failure)
    }
  }
}
