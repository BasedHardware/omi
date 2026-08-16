import SwiftUI

struct MemoryAtlasNodePlacement: Identifiable {
  let node: KnowledgeGraphNode
  let cluster: MemoryAtlasCluster?
  let normalizedPosition: CGPoint
  let degree: Int
  let clusterRank: Int
  /// Presentation-only catalog records represent a canonical memory without
  /// asserting a semantic entity or relationship. Layout is the authoritative
  /// source for this classification; no id convention is involved.
  let isCatalog: Bool

  init(
    node: KnowledgeGraphNode,
    cluster: MemoryAtlasCluster?,
    normalizedPosition: CGPoint,
    degree: Int,
    clusterRank: Int,
    isCatalog: Bool
  ) {
    self.node = node
    self.cluster = cluster
    self.normalizedPosition = normalizedPosition
    self.degree = degree
    self.clusterRank = clusterRank
    self.isCatalog = isCatalog
  }

  var id: String { node.id }
}

enum MemoryAtlasNodeVisualPolicy {
  /// Deep inspection keeps dots at a stable, usable size. The dynamic maximum
  /// zoom adds label fidelity; it must not make a node harder to see or target.
  static func radius(
    clusterRank: Int,
    zoom: CGFloat,
    compact: Bool,
    isFullyLabelled: Bool,
    isInspect: Bool,
    isFocus: Bool,
    isSmallAtlas: Bool = false
  ) -> CGFloat {
    if isFullyLabelled || isInspect {
      return clusterRank == 0 ? 16 : 12
    }
    // A 2.1pt dot is the right mark among thousands of peers and far too timid
    // when there are two dozen. Scale the mark to the graph, not just the zoom.
    if isSmallAtlas && !compact && !isFocus {
      return clusterRank == 0 ? 9 : 6
    }
    if isFocus {
      return clusterRank == 0 ? 10 : 7.2
    }
    if clusterRank == 0 {
      if compact { return 5 }
      return zoom >= 4.2 ? 8 : 6
    }
    if compact { return zoom >= 1.2 ? 2.4 : 2.1 }
    if zoom >= 4.2 { return 4.8 }
    return zoom >= 1.45 ? 2.8 : 2.1
  }
}

extension MemoryAtlasRenderPlanner {
  /// Preserve the precomputed per-cluster salience order while avoiding a
  /// single dense cluster monopolizing a capped detail viewport.
  static func fairPrefix(
    _ candidates: [MemoryAtlasNodePlacement],
    limit: Int,
    prioritizeCatalog: Bool = false
  ) -> [MemoryAtlasNodePlacement] {
    var unclustered: [MemoryAtlasNodePlacement] = []
    var byCluster: [MemoryAtlasCluster: [MemoryAtlasNodePlacement]] = [:]
    for placement in candidates {
      if let cluster = placement.cluster {
        byCluster[cluster, default: []].append(placement)
      } else {
        unclustered.append(placement)
      }
    }

    // The anchor is an unclustered semantic node; catalog records are also
    // unclustered but are intentionally background material until a search or
    // selection asks for them. Otherwise a large historical catalog would
    // crowd all assertion-backed constellations out of an overview.
    let semanticUnclustered = unclustered.filter { !$0.isCatalog }
    let catalogUnclustered = unclustered.filter(\.isCatalog)
    // A search tier is the user explicitly asking to see matching memories.
    // Admit its catalog matches before semantic background so a broad result
    // cannot disappear merely because an assertion constellation is denser.
    var result = Array((prioritizeCatalog ? catalogUnclustered : semanticUnclustered).prefix(limit))
    var nextIndexes = [Int](repeating: 0, count: MemoryAtlasCluster.allCases.count)
    while result.count < limit {
      var appended = false
      for (clusterIndex, cluster) in MemoryAtlasCluster.allCases.enumerated() where result.count < limit {
        let index = nextIndexes[clusterIndex]
        guard let placements = byCluster[cluster], index < placements.count else { continue }
        result.append(placements[index])
        nextIndexes[clusterIndex] = index + 1
        appended = true
      }
      if !appended { break }
    }
    if result.count < limit, prioritizeCatalog {
      result.append(contentsOf: semanticUnclustered.prefix(limit - result.count))
    }
    if result.count < limit {
      result.append(contentsOf: catalogUnclustered.prefix(limit - result.count))
    }
    return result
  }
}
