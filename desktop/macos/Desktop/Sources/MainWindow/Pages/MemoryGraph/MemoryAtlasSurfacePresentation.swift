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
    // An empty server graph still used to mint a synthetic owner projection.
    // Presence of that object is not readiness — it is the lonely-node flash.
    if hasProjection && !isEmpty { return .ready }
    if isLoading || !hasAttemptedLoad { return .loading }
    return .empty
  }

  /// Whether the Canvas alone should paint the map for this frame.
  ///
  /// While the camera moves with nothing on the map that needs view-level
  /// emphasis — no selection, no search matches — the interactive SwiftUI
  /// overlay (glass marks, name labels, hit targets) steps aside and the
  /// Canvas paints the cohort's marks and admitted names itself, exactly the
  /// same inputs the render-plan cache gates on. Repositioning a few hundred
  /// composed views every gesture frame is the difference between the map
  /// tracking the hand and lagging behind it; a selection or search keeps the
  /// overlay up because emphasis is the point of those states, and their
  /// gestures bypass the plan cache anyway.
  static func canvasOwnsMarks(
    isCameraMoving: Bool,
    selectedNodeID: String?,
    matchingNodeIDs: Set<String>?,
    matchingEdges: [MemoryAtlasEdgePlacement]?
  ) -> Bool {
    isCameraMoving && selectedNodeID == nil && matchingNodeIDs == nil && matchingEdges == nil
  }
}
