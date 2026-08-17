import Foundation

/// What the Brain Map tab shows before a canonical graph is ready.
///
/// The surface used to mount on an empty response and invent a synthetic
/// owner node, so the first visit painted one lonely person for several
/// seconds while pages were still arriving. Loading and emptiness are
/// distinct: a spinner while the fetch is in flight, the empty copy only
/// after that fetch has resolved to nothing.
enum MemoryAtlasSurfacePresentation {
  enum Phase: Equatable {
    case loading
    case empty
    case ready
  }

  static func phase(
    isLoading: Bool,
    isEmpty: Bool,
    hasProjection: Bool,
    hasAttemptedLoad: Bool
  ) -> Phase {
    if hasProjection { return .ready }
    if isLoading || !hasAttemptedLoad { return .loading }
    return isEmpty ? .empty : .ready
  }
}
