import SwiftUI
import OmiSupport
import OmiTheme
import OSLog

private let memoryAtlasLogger = Logger(
  subsystem: Bundle.main.bundleIdentifier ?? "com.omi.desktop",
  category: "MemoryAtlas"
)

extension Notification.Name {
  static let desktopAutomationOpenMemoryAtlasRequested = Notification.Name(
    "desktopAutomationOpenMemoryAtlasRequested"
  )
  static let desktopAutomationMemoryAtlasViewportRequested = Notification.Name(
    "desktopAutomationMemoryAtlasViewportRequested"
  )
  static let desktopAutomationMemoryAtlasSelectionRequested = Notification.Name(
    "desktopAutomationMemoryAtlasSelectionRequested"
  )
}

// MARK: - Atlas Layout

enum MemoryAtlasCluster: String, CaseIterable, Identifiable {
  case projects
  case collaborators
  case tools

  var id: String { rawValue }

  var title: String {
    switch self {
    case .projects: return "Projects & ideas"
    case .collaborators: return "People & organizations"
    case .tools: return "Tools & places"
    }
  }

  var color: Color {
    switch self {
    case .projects: return Color(red: 0.33, green: 0.84, blue: 0.67)
    case .collaborators: return Color(red: 0.96, green: 0.66, blue: 0.22)
    case .tools: return Color(red: 0.27, green: 0.63, blue: 0.96)
    }
  }

  var symbolName: String {
    switch self {
    case .projects: return "folder.fill"
    case .collaborators: return "person.2.fill"
    case .tools: return "wrench.and.screwdriver.fill"
    }
  }

  var center: CGPoint {
    switch self {
    case .projects: return CGPoint(x: 0.24, y: 0.45)
    case .collaborators: return CGPoint(x: 0.51, y: 0.42)
    case .tools: return CGPoint(x: 0.78, y: 0.45)
    }
  }
}

struct MemoryAtlasNodePlacement: Identifiable {
  let node: KnowledgeGraphNode
  let cluster: MemoryAtlasCluster?
  let communityID: String?
  let normalizedPosition: CGPoint
  let degree: Int
  let clusterRank: Int
  /// Zero (stale) through one (most recent), relative to the newest entity in
  /// this snapshot so fixture and offline layouts stay stable.
  let recencyScore: Double
  /// Number of unique canonical memories supporting this entity.
  let evidenceCount: Int
  /// Bounded visual reinforcement derived only from unique memory references.
  /// Degree remains a separate prominence signal and is never called reinforcement.
  let reinforcementScore: Int

  var id: String { node.id }
}

struct MemoryAtlasEdgePlacement: Identifiable {
  let edge: KnowledgeGraphEdge
  let source: CGPoint
  let target: CGPoint
  let cluster: MemoryAtlasCluster
  let isCrossCommunity: Bool
  /// A deterministic bend used to route dense relationships through their
  /// semantic cluster instead of drawing an unreadable owner fan.
  let routeControl: CGPoint

  var id: String { edge.id }
}

struct MemoryAtlasCommunityPlacement: Identifiable {
  let community: MemoryAtlasCommunityProjection.Community
  let center: CGPoint
  let memberCount: Int

  var id: String { community.id }
}

struct MemoryAtlasSnapshot {
  let nodes: [MemoryAtlasNodePlacement]
  let edges: [MemoryAtlasEdgePlacement]
  let anchorNodeID: String?
  let nodeByID: [String: MemoryAtlasNodePlacement]
  /// Edge order is computed once when the graph is received. Camera updates can
  /// then filter this stable order instead of sorting the whole graph per frame.
  let rankedEdges: [MemoryAtlasEdgePlacement]
  let overviewEdges: [MemoryAtlasEdgePlacement]
  let neighborhoodEdges: [MemoryAtlasEdgePlacement]
  let detailEdges: [MemoryAtlasEdgePlacement]
  let edgesByNodeID: [String: [MemoryAtlasEdgePlacement]]
  let neighborIDsByNodeID: [String: Set<String>]
  let communityProjection: MemoryAtlasCommunityProjection
  let communities: [MemoryAtlasCommunityPlacement]
  let communityByID: [String: MemoryAtlasCommunityPlacement]

  init(
    nodes: [MemoryAtlasNodePlacement],
    edges: [MemoryAtlasEdgePlacement],
    anchorNodeID: String?,
    communityProjection: MemoryAtlasCommunityProjection,
    communities: [MemoryAtlasCommunityPlacement]
  ) {
    self.nodes = nodes
    self.edges = edges
    self.anchorNodeID = anchorNodeID
    self.communityProjection = communityProjection
    self.communities = communities
    communityByID = Dictionary(lastWriteWins: communities.map { ($0.id, $0) })
    let indexedNodes = Dictionary(lastWriteWins: nodes.map { ($0.id, $0) })
    nodeByID = indexedNodes

    let sortedEdges = edges.sorted { lhs, rhs in
      let lhsRank = MemoryAtlasSnapshot.edgeRank(lhs, nodes: indexedNodes)
      let rhsRank = MemoryAtlasSnapshot.edgeRank(rhs, nodes: indexedNodes)
      return lhsRank < rhsRank
    }
    rankedEdges = sortedEdges

    overviewEdges = sortedEdges.filter { edge in
      !MemoryAtlasSnapshot.touchesAnchor(edge, anchorNodeID: anchorNodeID)
        && MemoryAtlasSnapshot.maximumEndpointRank(edge, nodes: indexedNodes) < 8
    }
    neighborhoodEdges = sortedEdges.filter { edge in
      (!MemoryAtlasSnapshot.touchesAnchor(edge, anchorNodeID: anchorNodeID)
        || MemoryAtlasSnapshot.maximumEndpointRank(edge, nodes: indexedNodes) < 3)
        && MemoryAtlasSnapshot.maximumEndpointRank(edge, nodes: indexedNodes) < 10
    }
    detailEdges = sortedEdges.filter { edge in
      MemoryAtlasSnapshot.maximumEndpointRank(edge, nodes: indexedNodes) < 12
    }

    var indexedEdges: [String: [MemoryAtlasEdgePlacement]] = [:]
    var indexedNeighbors: [String: Set<String>] = [:]
    for placement in sortedEdges {
      let sourceID = placement.edge.sourceId
      let targetID = placement.edge.targetId
      indexedEdges[sourceID, default: []].append(placement)
      indexedEdges[targetID, default: []].append(placement)
      indexedNeighbors[sourceID, default: []].insert(targetID)
      indexedNeighbors[targetID, default: []].insert(sourceID)
    }
    edgesByNodeID = indexedEdges
    neighborIDsByNodeID = indexedNeighbors
  }

  func rankedEdges(for detailLevel: MemoryAtlasDetailLevel) -> [MemoryAtlasEdgePlacement] {
    switch detailLevel {
    case .overview: overviewEdges
    case .neighborhood: neighborhoodEdges
    case .detail: detailEdges
    case .focus: detailEdges
    case .inspect: detailEdges
    }
  }

  private static func edgeRank(
    _ placement: MemoryAtlasEdgePlacement,
    nodes: [String: MemoryAtlasNodePlacement]
  ) -> (Int, Int, String) {
    let sourceRank = nodes[placement.edge.sourceId]?.clusterRank ?? .max
    let targetRank = nodes[placement.edge.targetId]?.clusterRank ?? .max
    return (min(sourceRank, targetRank), max(sourceRank, targetRank), placement.id)
  }

  private static func maximumEndpointRank(
    _ placement: MemoryAtlasEdgePlacement,
    nodes: [String: MemoryAtlasNodePlacement]
  ) -> Int {
    max(
      nodes[placement.edge.sourceId]?.clusterRank ?? .max,
      nodes[placement.edge.targetId]?.clusterRank ?? .max
    )
  }

  private static func touchesAnchor(
    _ placement: MemoryAtlasEdgePlacement,
    anchorNodeID: String?
  ) -> Bool {
    guard let anchorNodeID else { return false }
    return placement.edge.sourceId == anchorNodeID || placement.edge.targetId == anchorNodeID
  }
}

enum MemoryAtlasDetailLevel: Equatable {
  case overview
  case neighborhood
  case detail
  case focus
  case inspect
}

enum MemoryAtlasZoomPolicy {
  static let minimumZoom: CGFloat = 0.75
  static let compactMaximumZoom: CGFloat = 1.35
  static let expandedMaximumZoom: CGFloat = 5
  static let focusModeZoom: CGFloat = 3.2
  static let inspectModeZoom: CGFloat = 7.5
  static let focusTargetZoom: CGFloat = 4

  static func maximumZoom(compact: Bool) -> CGFloat {
    compact ? compactMaximumZoom : expandedMaximumZoom
  }

  static func focusedZoom(currentZoom: CGFloat, compact: Bool) -> CGFloat {
    min(max(currentZoom, focusTargetZoom), maximumZoom(compact: compact))
  }
}

struct MemoryAtlasRenderPlan {
  let visibleNodes: [MemoryAtlasNodePlacement]
  let visibleEdges: [MemoryAtlasEdgePlacement]
  let interactiveNodes: [MemoryAtlasNodePlacement]
  let labelNodeIDs: Set<String>
  let relatedNodeIDs: Set<String>
  let detailLevel: MemoryAtlasDetailLevel
  /// A bounded subset whose semantics are worth rendering at the current
  /// level. The UI never needs to scan or sort every visible edge per frame.
  let relationshipLabelEdges: [MemoryAtlasEdgePlacement]
}

enum MemoryAtlasRenderPlanner {
  static func makePlan(
    snapshot: MemoryAtlasSnapshot,
    viewportSize: CGSize,
    zoom: CGFloat,
    pan: CGSize,
    compact: Bool,
    selectedNodeID: String?,
    matchingNodeIDs: Set<String>?,
    matchingEdges: [MemoryAtlasEdgePlacement]? = nil
  ) -> MemoryAtlasRenderPlan {
    let detailLevel: MemoryAtlasDetailLevel = if zoom < 1.35 {
      .overview
    } else if zoom < 1.9 {
      .neighborhood
    } else if zoom < MemoryAtlasZoomPolicy.focusModeZoom {
      .detail
    } else if zoom < MemoryAtlasZoomPolicy.inspectModeZoom {
      .focus
    } else {
      .inspect
    }

    let maximumNodeLimit: Int = switch detailLevel {
    case .overview: 1_200
    case .neighborhood: 600
    case .detail: 450
    case .focus: 72
    case .inspect: 64
    }
    let edgeLimit: Int = switch detailLevel {
    case .overview: 36
    case .neighborhood: 96
    case .detail: 160
    case .focus: 80
    case .inspect: 64
    }
    let labelsPerCluster: Int = switch detailLevel {
    case .overview: compact ? 2 : 3
    case .neighborhood: compact ? 4 : 7
    case .detail: compact ? 5 : 11
    case .focus: compact ? 5 : 24
    case .inspect: compact ? 5 : 64
    }
    let labelLimit: Int = switch detailLevel {
    case .overview: 12
    case .neighborhood: 24
    case .detail: 36
    case .focus: 72
    case .inspect: 64
    }

    var relatedNodeIDs: Set<String> = []
    if let selectedNodeID {
      relatedNodeIDs = snapshot.neighborIDsByNodeID[selectedNodeID] ?? []
      relatedNodeIDs.insert(selectedNodeID)
    }

    let paddedBounds = CGRect(origin: .zero, size: viewportSize).insetBy(dx: -48, dy: -48)
    let viewportCandidates = snapshot.nodes.filter { placement in
      if placement.id == selectedNodeID { return true }
      if selectedNodeID != nil && (detailLevel == .focus || detailLevel == .inspect) {
        return relatedNodeIDs.contains(placement.id)
      }
      return paddedBounds.contains(
        renderedPoint(
          for: placement.normalizedPosition,
          viewportSize: viewportSize,
          zoom: zoom,
          pan: pan
        )
      )
    }
    // At focus zoom, cap based on viewport density so the scene deliberately
    // becomes an inspectable set of circles rather than a smaller dot cloud.
    let nodeLimit: Int = if detailLevel == .focus {
      min(maximumNodeLimit, max(40, viewportCandidates.count / 3))
    } else if detailLevel == .inspect {
      min(maximumNodeLimit, viewportCandidates.count)
    } else {
      maximumNodeLimit
    }

    let visibleNodes = priorityOrderedPrefix(
      viewportCandidates,
      limit: nodeLimit,
      anchorNodeID: snapshot.anchorNodeID,
      selectedNodeID: selectedNodeID,
      relatedNodeIDs: relatedNodeIDs,
      matchingNodeIDs: matchingNodeIDs,
      includeBackgroundNodes: (detailLevel != .focus && detailLevel != .inspect) || selectedNodeID == nil
    )
    let visibleNodeIDs = Set(visibleNodes.map(\.id))

    let edgeCandidates: [MemoryAtlasEdgePlacement]
    if let selectedNodeID {
      edgeCandidates = snapshot.edgesByNodeID[selectedNodeID] ?? []
    } else if let matchingNodeIDs {
      edgeCandidates = matchingEdges ?? snapshot.rankedEdges.filter { edge in
        matchingNodeIDs.contains(edge.edge.sourceId) || matchingNodeIDs.contains(edge.edge.targetId)
      }
    } else {
      edgeCandidates = snapshot.rankedEdges(for: detailLevel)
    }

    let selectedEdgeLimit = selectedNodeID == nil ? edgeLimit : min(edgeLimit, 80)
    let visibleEdges = Array(
      edgeCandidates.lazy
        .filter {
          visibleNodeIDs.contains($0.edge.sourceId) && visibleNodeIDs.contains($0.edge.targetId)
        }
        .prefix(selectedEdgeLimit)
    )

    let labelCandidates: [MemoryAtlasNodePlacement]
    if detailLevel == .inspect {
      labelCandidates = visibleNodes
    } else if selectedNodeID != nil {
      labelCandidates = visibleNodes.filter { relatedNodeIDs.contains($0.id) }
    } else if let matchingNodeIDs {
      labelCandidates = visibleNodes.filter { matchingNodeIDs.contains($0.id) }
    } else {
      labelCandidates = visibleNodes.filter { placement in
        placement.id == snapshot.anchorNodeID || placement.clusterRank < labelsPerCluster
      }
    }
    let labels = admitLabels(
      labelCandidates,
      limit: labelLimit,
      viewportSize: viewportSize,
      zoom: zoom,
      pan: pan,
      compact: compact,
      forcedNodeIDs: Set([selectedNodeID, snapshot.anchorNodeID].compactMap { $0 })
    )

    let inspectNodeIDs = Set(visibleNodes.map(\.id))
    let interactiveNodes = detailLevel == .inspect ? visibleNodes : labels
    let labelNodeIDs = detailLevel == .inspect ? inspectNodeIDs : Set(labels.map(\.id))
    let relationshipLabelLimit: Int = switch detailLevel {
    case .overview, .neighborhood: 0
    case .detail: selectedNodeID == nil ? 0 : 6
    case .focus: 12
    case .inspect: 16
    }
    let relationshipLabelEdges = Array(visibleEdges.prefix(relationshipLabelLimit))

    return MemoryAtlasRenderPlan(
      visibleNodes: visibleNodes,
      visibleEdges: visibleEdges,
      interactiveNodes: interactiveNodes,
      labelNodeIDs: labelNodeIDs,
      relatedNodeIDs: relatedNodeIDs,
      detailLevel: detailLevel,
      relationshipLabelEdges: relationshipLabelEdges
    )
  }

  static func renderedPoint(
    for normalized: CGPoint,
    viewportSize: CGSize,
    zoom: CGFloat,
    pan: CGSize
  ) -> CGPoint {
    CGPoint(
      x: (normalized.x * viewportSize.width - viewportSize.width / 2) * zoom
        + viewportSize.width / 2 + pan.width,
      y: (normalized.y * viewportSize.height - viewportSize.height / 2) * zoom
        + viewportSize.height / 2 + pan.height
    )
  }

  private static func priorityTier(
    for placement: MemoryAtlasNodePlacement,
    anchorNodeID: String?,
    selectedNodeID: String?,
    relatedNodeIDs: Set<String>,
    matchingNodeIDs: Set<String>?
  ) -> Int {
    if placement.id == selectedNodeID {
      return 0
    } else if matchingNodeIDs?.contains(placement.id) == true {
      return 1
    } else if relatedNodeIDs.contains(placement.id) {
      return 2
    } else if placement.id == anchorNodeID {
      return 3
    } else {
      return 4
    }
  }

  /// Stable, allocation-light priority selection for gesture updates. The
  /// layout already orders each cluster by salience, so a per-frame sort would
  /// only spend main-thread time rediscovering that same order.
  private static func priorityOrderedPrefix(
    _ candidates: [MemoryAtlasNodePlacement],
    limit: Int,
    anchorNodeID: String?,
    selectedNodeID: String?,
    relatedNodeIDs: Set<String>,
    matchingNodeIDs: Set<String>?,
    includeBackgroundNodes: Bool
  ) -> [MemoryAtlasNodePlacement] {
    var tiers = Array(repeating: [MemoryAtlasNodePlacement](), count: 5)
    for placement in candidates {
      let tier = priorityTier(
        for: placement,
        anchorNodeID: anchorNodeID,
        selectedNodeID: selectedNodeID,
        relatedNodeIDs: relatedNodeIDs,
        matchingNodeIDs: matchingNodeIDs
      )
      tiers[tier].append(placement)
    }

    var result: [MemoryAtlasNodePlacement] = []
    result.reserveCapacity(min(limit, candidates.count))
    let tierCount = includeBackgroundNodes ? tiers.count : 3
    for tierIndex in 0..<tierCount where result.count < limit {
      let remaining = limit - result.count
      result.append(contentsOf: fairPrefix(tiers[tierIndex], limit: remaining))
    }
    return result
  }

  /// Preserve the precomputed per-cluster salience order while avoiding a
  /// single dense cluster monopolizing a capped detail viewport.
  private static func fairPrefix(
    _ candidates: [MemoryAtlasNodePlacement],
    limit: Int
  ) -> [MemoryAtlasNodePlacement] {
    var unclustered: [MemoryAtlasNodePlacement] = []
    var byCommunity: [String: [MemoryAtlasNodePlacement]] = [:]
    for placement in candidates {
      if let communityID = placement.communityID {
        byCommunity[communityID, default: []].append(placement)
      } else {
        unclustered.append(placement)
      }
    }

    var result = Array(unclustered.prefix(limit))
    let communityIDs = byCommunity.keys.sorted()
    var nextIndexes = Dictionary(lastWriteWins: communityIDs.map { ($0, 0) })
    while result.count < limit {
      var appended = false
      for communityID in communityIDs where result.count < limit {
        let index = nextIndexes[communityID] ?? 0
        guard let placements = byCommunity[communityID], index < placements.count else { continue }
        result.append(placements[index])
        nextIndexes[communityID] = index + 1
        appended = true
      }
      if !appended { break }
    }
    return result
  }

  private static func admitLabels(
    _ candidates: [MemoryAtlasNodePlacement],
    limit: Int,
    viewportSize: CGSize,
    zoom: CGFloat,
    pan: CGSize,
    compact: Bool,
    forcedNodeIDs: Set<String>
  ) -> [MemoryAtlasNodePlacement] {
    var admitted: [MemoryAtlasNodePlacement] = []
    var occupied: [CGRect] = []
    admitted.reserveCapacity(limit)
    occupied.reserveCapacity(limit)

    for placement in candidates {
      let center = renderedPoint(
        for: placement.normalizedPosition,
        viewportSize: viewportSize,
        zoom: zoom,
        pan: pan
      )
      let estimatedWidth = min(
        compact ? 112.0 : 152.0,
        max(44.0, CGFloat(placement.node.label.count) * (compact ? 5.7 : 6.4) + 18)
      )
      let rect = CGRect(
        x: center.x - estimatedWidth / 2,
        y: center.y + (compact ? 10 : 13),
        width: estimatedWidth,
        height: compact ? 22 : 26
      )
      let paddedRect = rect.insetBy(dx: -5, dy: -3)
      let forced = forcedNodeIDs.contains(placement.id)
      guard forced || !occupied.contains(where: { $0.intersects(paddedRect) }) else { continue }
      admitted.append(placement)
      occupied.append(paddedRect)
      if admitted.count == limit { break }
    }
    return admitted
  }
}

enum MemoryAtlasLayoutEngine {
  static func makeSnapshot(
    graph: KnowledgeGraphResponse,
    userName: String?,
    previousCommunityProjection: MemoryAtlasCommunityProjection? = nil
  ) -> MemoryAtlasSnapshot {
    // Graph responses are external data. Coalesce duplicate identifiers at the
    // boundary so a malformed server response cannot trap while building a UI.
    let nodes = uniqueNodes(from: graph.nodes)
    let edges = uniqueEdges(from: graph.edges)

    guard !nodes.isEmpty else {
      let projection = MemoryAtlasCommunityProjection(version: 1, communities: [], communityIDByNodeID: [:])
      return MemoryAtlasSnapshot(
        nodes: [], edges: [], anchorNodeID: nil,
        communityProjection: projection, communities: []
      )
    }

    var degree: [String: Int] = [:]
    var evidenceIDs: [String: Set<String>] = [:]
    var relationLabels: [String: [String]] = [:]
    for edge in edges {
      degree[edge.sourceId, default: 0] += 1
      degree[edge.targetId, default: 0] += 1
      evidenceIDs[edge.sourceId, default: []].formUnion(edge.memoryIds)
      evidenceIDs[edge.targetId, default: []].formUnion(edge.memoryIds)
      relationLabels[edge.sourceId, default: []].append(edge.label)
      relationLabels[edge.targetId, default: []].append(edge.label)
    }
    for node in nodes {
      evidenceIDs[node.id, default: []].formUnion(node.memoryIds)
    }
    let newestUpdate = nodes.map(\.updatedAt).max() ?? Date(timeIntervalSince1970: 0)

    let normalizedUserName = userName?.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
    let anchor = nodes.first {
      $0.nodeType == .person && normalizedUserName != nil && $0.label.lowercased() == normalizedUserName
    } ?? nodes.filter { $0.nodeType == .person }.max {
      (degree[$0.id] ?? 0) < (degree[$1.id] ?? 0)
    } ?? nodes.max {
      (degree[$0.id] ?? 0) < (degree[$1.id] ?? 0)
    }

    var anchorRelationLabels: [String: [String]] = [:]
    if let anchor {
      for edge in edges {
        if edge.sourceId == anchor.id {
          anchorRelationLabels[edge.targetId, default: []].append(edge.label)
        } else if edge.targetId == anchor.id {
          anchorRelationLabels[edge.sourceId, default: []].append(edge.label)
        }
      }
    }

    let communityProjection = MemoryAtlasCommunityDetector.detect(
      graph: KnowledgeGraphResponse(nodes: nodes, edges: edges),
      ownerNodeID: anchor?.id,
      previous: previousCommunityProjection
    )
    let communityPlacements = communityProjection.communities.map { community in
      MemoryAtlasCommunityPlacement(
        community: community,
        center: communityCenter(for: community.layoutSlot),
        memberCount: communityProjection.communityIDByNodeID.values.filter { $0 == community.id }.count
      )
    }
    let communityCenterByID = Dictionary(lastWriteWins: communityPlacements.map { ($0.id, $0.center) })

    var grouped: [String: [KnowledgeGraphNode]] = [:]
    for node in nodes where node.id != anchor?.id {
      if let communityID = communityProjection.communityIDByNodeID[node.id] {
        grouped[communityID, default: []].append(node)
      }
    }

    var placements: [MemoryAtlasNodePlacement] = []
    if let anchor {
      placements.append(
        MemoryAtlasNodePlacement(
          node: anchor,
          cluster: nil,
          communityID: communityProjection.communityIDByNodeID[anchor.id],
          normalizedPosition: CGPoint(x: 0.5, y: 0.77),
          degree: degree[anchor.id] ?? 0,
          clusterRank: 0,
          recencyScore: recencyScore(updatedAt: anchor.updatedAt, relativeTo: newestUpdate),
          evidenceCount: evidenceIDs[anchor.id]?.count ?? 0,
          reinforcementScore: reinforcementScore(evidenceCount: evidenceIDs[anchor.id]?.count ?? 0)
        )
      )
    }

    for community in communityPlacements {
      let sorted = (grouped[community.id] ?? []).sorted {
        let lhsScore = salience(node: $0, degree: degree[$0.id] ?? 0)
        let rhsScore = salience(node: $1, degree: degree[$1.id] ?? 0)
        if lhsScore == rhsScore { return $0.label.localizedCaseInsensitiveCompare($1.label) == .orderedAscending }
        return lhsScore > rhsScore
      }

      for (index, node) in sorted.enumerated() {
        placements.append(
            MemoryAtlasNodePlacement(
              node: node,
              cluster: cluster(for: node, relationLabels: anchorRelationLabels[node.id] ?? relationLabels[node.id] ?? []),
              communityID: community.id,
              normalizedPosition: position(
                around: community.center,
                index: index,
                count: sorted.count,
                nodeID: node.id
            ),
            degree: degree[node.id] ?? 0,
            clusterRank: index,
            recencyScore: recencyScore(updatedAt: node.updatedAt, relativeTo: newestUpdate),
            evidenceCount: evidenceIDs[node.id]?.count ?? 0,
            reinforcementScore: reinforcementScore(evidenceCount: evidenceIDs[node.id]?.count ?? 0)
          )
        )
      }
    }

    let positions = Dictionary(lastWriteWins: placements.map { ($0.id, $0.normalizedPosition) })
    let clusters = Dictionary(lastWriteWins: placements.compactMap { placement in
      placement.cluster.map { (placement.id, $0) }
    })
    let communityIDs = Dictionary(lastWriteWins: placements.compactMap { placement in
      placement.communityID.map { (placement.id, $0) }
    })
    let edgePlacements = edges.compactMap { edge -> MemoryAtlasEdgePlacement? in
      guard let source = positions[edge.sourceId], let target = positions[edge.targetId] else { return nil }
      let cluster = clusters[edge.sourceId] ?? clusters[edge.targetId] ?? .collaborators
      let sourceCommunityID = communityIDs[edge.sourceId]
      let targetCommunityID = communityIDs[edge.targetId]
      return MemoryAtlasEdgePlacement(
        edge: edge,
        source: source,
        target: target,
        cluster: cluster,
        isCrossCommunity: sourceCommunityID != nil && targetCommunityID != nil && sourceCommunityID != targetCommunityID,
        routeControl: routeControl(
          source: source,
          target: target,
          sourceCommunityCenter: sourceCommunityID.flatMap { communityCenterByID[$0] },
          targetCommunityCenter: targetCommunityID.flatMap { communityCenterByID[$0] },
          anchorID: anchor?.id,
          edge: edge
        )
      )
    }

    return MemoryAtlasSnapshot(
      nodes: placements,
      edges: edgePlacements,
      anchorNodeID: anchor?.id,
      communityProjection: communityProjection,
      communities: communityPlacements
    )
  }

  private static func uniqueNodes(from nodes: [KnowledgeGraphNode]) -> [KnowledgeGraphNode] {
    var seenIDs: Set<String> = []
    let newestFirst = nodes.reversed().compactMap { node -> KnowledgeGraphNode? in
      seenIDs.insert(node.id).inserted ? node : nil
    }
    return Array(newestFirst.reversed())
  }

  private static func uniqueEdges(from edges: [KnowledgeGraphEdge]) -> [KnowledgeGraphEdge] {
    var seenIDs: Set<String> = []
    let newestFirst = edges.reversed().compactMap { edge -> KnowledgeGraphEdge? in
      seenIDs.insert(edge.id).inserted ? edge : nil
    }
    return Array(newestFirst.reversed())
  }

  static func cluster(
    for node: KnowledgeGraphNode,
    relationLabels: [String]
  ) -> MemoryAtlasCluster {
    let labels = relationLabels.map(normalizeRelationship)
    if labels.contains(where: { projectsRelationships.contains($0) }) { return .projects }
    if labels.contains(where: { collaboratorRelationships.contains($0) }) { return .collaborators }
    if labels.contains(where: { toolRelationships.contains($0) }) { return .tools }

    switch node.nodeType {
    case .person, .organization: return .collaborators
    case .place, .thing: return .tools
    case .concept: return .projects
    }
  }

  static func relationshipDisplayName(_ rawValue: String) -> String {
    normalizeRelationship(rawValue).replacingOccurrences(of: "_", with: " ")
  }

  private static func recencyScore(updatedAt: Date, relativeTo newestUpdate: Date) -> Double {
    let ageDays = max(0, newestUpdate.timeIntervalSince(updatedAt) / 86_400)
    return 1 / (1 + ageDays / 30)
  }

  private static func reinforcementScore(evidenceCount: Int) -> Int {
    guard evidenceCount > 0 else { return 0 }
    return min(100, Int((log2(Double(evidenceCount) + 1) / log2(17)) * 100))
  }

  private static func routeControl(
    source: CGPoint,
    target: CGPoint,
    sourceCommunityCenter: CGPoint?,
    targetCommunityCenter: CGPoint?,
    anchorID: String?,
    edge: KnowledgeGraphEdge
  ) -> CGPoint {
    let touchesAnchor = edge.sourceId == anchorID || edge.targetId == anchorID
    if touchesAnchor {
      return sourceCommunityCenter ?? targetCommunityCenter
        ?? CGPoint(x: (source.x + target.x) / 2, y: (source.y + target.y) / 2)
    }
    if let sourceCommunityCenter, let targetCommunityCenter,
      sourceCommunityCenter != targetCommunityCenter
    {
      return CGPoint(
        x: (sourceCommunityCenter.x + targetCommunityCenter.x) / 2,
        y: min(sourceCommunityCenter.y, targetCommunityCenter.y) - 0.04
      )
    }
    if let center = sourceCommunityCenter ?? targetCommunityCenter {
      return center
    }
    if abs(source.x - target.x) > 0.18 {
      return CGPoint(x: (source.x + target.x) / 2, y: min(source.y, target.y) - 0.055)
    }
    return CGPoint(x: (source.x + target.x) / 2, y: (source.y + target.y) / 2)
  }

  private static let projectsRelationships: Set<String> = [
    "works_on", "builds", "built", "maintains", "created", "founded", "develops",
  ]
  private static let collaboratorRelationships: Set<String> = [
    "works_with", "collaborates_with", "plans_with", "knows", "reports_to", "manages",
  ]
  private static let toolRelationships: Set<String> = [
    "uses", "opens", "stores_work_in", "checks", "prefers", "runs_on", "lives_in",
  ]

  private static func normalizeRelationship(_ value: String) -> String {
    value
      .trimmingCharacters(in: .whitespacesAndNewlines)
      .lowercased()
      .replacingOccurrences(of: "-", with: "_")
      .replacingOccurrences(of: " ", with: "_")
  }

  private static func salience(node: KnowledgeGraphNode, degree: Int) -> Int {
    let typeBonus: Int
    switch node.nodeType {
    case .organization: typeBonus = 16
    case .person: typeBonus = 10
    case .concept: typeBonus = 4
    case .place: typeBonus = 3
    case .thing: typeBonus = 0
    }
    let genericPenalty = genericLabels.contains(node.label.lowercased()) ? 10_000 : 0
    return degree * 20 + node.memoryIds.count * 4 + min(node.aliases.count, 3) + typeBonus - genericPenalty
  }

  private static let genericLabels: Set<String> = [
    "app", "apps", "user", "calendar event", "document", "documents", "download", "downloads",
  ]

  private static func communityCenter(for slot: Int) -> CGPoint {
    let centers = [
      CGPoint(x: 0.22, y: 0.31), CGPoint(x: 0.5, y: 0.27), CGPoint(x: 0.78, y: 0.31),
      CGPoint(x: 0.18, y: 0.52), CGPoint(x: 0.43, y: 0.49), CGPoint(x: 0.7, y: 0.5),
      CGPoint(x: 0.32, y: 0.65), CGPoint(x: 0.66, y: 0.65),
    ]
    return centers[min(max(slot, 0), centers.count - 1)]
  }

  private static func position(
    around center: CGPoint,
    index: Int,
    count: Int,
    nodeID: String
  ) -> CGPoint {
    guard count > 0 else { return center }
    if index == 0 { return center }

    let ringIndex = index - 1
    let jitter = stableFraction(nodeID)
    let angle = Double(ringIndex) * 2.399_963_229_728_653 + (jitter - 0.5) * 0.7
    let normalizedIndex = Double(ringIndex + 1) / Double(max(count, 1))
    let radialJitter = 0.9 + jitter * 0.2
    let radiusX = (0.035 + 0.075 * sqrt(normalizedIndex)) * radialJitter
    let radiusY = (0.03 + 0.065 * sqrt(normalizedIndex)) * radialJitter
    let x = center.x + cos(angle) * radiusX
    let y = center.y + sin(angle) * radiusY
    return CGPoint(
      x: min(max(x, 0.08), 0.92),
      y: min(max(y, 0.2), 0.68)
    )
  }

  private static func stableFraction(_ value: String) -> Double {
    var hash: UInt64 = 0xcbf2_9ce4_8422_2325
    for byte in value.utf8 {
      hash ^= UInt64(byte)
      hash = hash &* 0x0000_0100_0000_01b3
    }
    return Double(hash % 10_000) / 10_000
  }
}

// MARK: - Canonical Atlas Containers

private enum MemoryAtlasCommunityProjectionStore {
  private static let detectorVersion = 1

  private static var key: String {
    let userID = UserDefaults.standard.string(forKey: "auth_userId") ?? "anonymous"
    return "memoryAtlas.communityProjection.v\(detectorVersion).\(userID)"
  }

  static func load() -> MemoryAtlasCommunityProjection? {
    guard let data = UserDefaults.standard.data(forKey: key) else { return nil }
    return try? JSONDecoder().decode(MemoryAtlasCommunityProjection.self, from: data)
  }

  static func save(_ projection: MemoryAtlasCommunityProjection) {
    guard let data = try? JSONEncoder().encode(projection) else { return }
    if UserDefaults.standard.data(forKey: key) != data {
      UserDefaults.standard.set(data, forKey: key)
    }
  }
}

struct CanonicalMemoryAtlasInlineCard: View {
  @ObservedObject var viewModel: MemoryGraphViewModel
  let onViewEvidence: ([String]) -> Void
  @State private var showExpandedAtlas = false

  var body: some View {
    VStack(alignment: .leading, spacing: 12) {
      HStack(spacing: 10) {
        VStack(alignment: .leading, spacing: 2) {
          Text("Memory atlas")
            .scaledFont(size: 15, weight: .semibold)
            .foregroundColor(OmiColors.textPrimary)
          Text("Explore how the people, projects, and tools in your memories connect")
            .scaledFont(size: 12)
            .foregroundColor(OmiColors.textTertiary)
        }

        Spacer()

        Button {
          showExpandedAtlas = true
        } label: {
          Label("Open atlas", systemImage: "arrow.up.left.and.arrow.down.right")
            .scaledFont(size: 12, weight: .medium)
            .foregroundColor(OmiColors.textSecondary)
            .padding(.horizontal, 12)
            .frame(height: 32)
            .omiControlSurface(fill: OmiColors.backgroundRaised, radius: 12)
        }
        .buttonStyle(.plain)
        .accessibilityIdentifier("memory_atlas_expand")
      }

      atlasContent(compact: true)
        .frame(height: 460)
        .clipShape(RoundedRectangle(cornerRadius: 20, style: .continuous))
    }
    .padding(16)
    .omiPanel(
      fill: OmiColors.backgroundSecondary,
      radius: 24,
      stroke: OmiColors.border.opacity(0.14),
      shadowOpacity: 0.14,
      shadowRadius: 12,
      shadowY: 8
    )
    .task { await viewModel.prepareCanonicalAtlas() }
    .sheet(isPresented: $showExpandedAtlas) {
      CanonicalMemoryAtlasPage(
        viewModel: viewModel,
        onViewEvidence: onViewEvidence
      )
      .frame(minWidth: 1120, idealWidth: 1320, minHeight: 740, idealHeight: 860)
    }
    .onReceive(NotificationCenter.default.publisher(for: .desktopAutomationOpenMemoryAtlasRequested)) { _ in
      showExpandedAtlas = true
    }
  }

  @ViewBuilder
  private func atlasContent(compact: Bool) -> some View {
    if viewModel.isLoading && viewModel.graphResponse.nodes.isEmpty {
      ZStack {
        OmiColors.backgroundPrimary
        ProgressView().tint(OmiColors.textTertiary)
      }
    } else if viewModel.graphResponse.nodes.isEmpty {
      MemoryAtlasEmptyState()
    } else {
      CanonicalMemoryAtlasSurface(
        graph: viewModel.graphResponse,
        compact: compact,
        onViewEvidence: onViewEvidence
      )
    }
  }
}

private struct CanonicalMemoryAtlasPage: View {
  @ObservedObject var viewModel: MemoryGraphViewModel
  let onViewEvidence: ([String]) -> Void
  @Environment(\.dismiss) private var dismiss

  var body: some View {
    VStack(spacing: 0) {
      HStack(spacing: 12) {
        Button { dismiss() } label: {
          Image(systemName: "xmark")
            .scaledFont(size: 12, weight: .semibold)
            .foregroundColor(OmiColors.textSecondary)
            .frame(width: 30, height: 30)
            .omiControlSurface(fill: OmiColors.backgroundRaised, radius: 11)
        }
        .buttonStyle(.plain)

        VStack(alignment: .leading, spacing: 2) {
          Text("Memory atlas")
            .scaledFont(size: 17, weight: .semibold)
            .foregroundColor(OmiColors.textPrimary)
          Text("A living map of what you know")
            .scaledFont(size: 11)
            .foregroundColor(OmiColors.textTertiary)
        }

        Spacer()

        Text("\(viewModel.graphResponse.nodes.count) entities · \(viewModel.graphResponse.edges.count) connections")
          .scaledFont(size: 12)
          .foregroundColor(OmiColors.textTertiary)
      }
      .padding(.horizontal, 18)
      .frame(height: 56)
      .background(OmiColors.backgroundSecondary)

      Divider().overlay(OmiColors.border.opacity(0.25))

      CanonicalMemoryAtlasSurface(
        graph: viewModel.graphResponse,
        compact: false,
        onViewEvidence: { memoryIds in
          dismiss()
          DispatchQueue.main.asyncAfter(deadline: .now() + 0.2) {
            onViewEvidence(memoryIds)
          }
        }
      )
    }
    .background(OmiColors.backgroundPrimary)
    .task { await viewModel.prepareCanonicalAtlas() }
    .onAppear {
      memoryAtlasLogger.info(
        "Expanded atlas opened nodes=\(viewModel.graphResponse.nodes.count, privacy: .public) edges=\(viewModel.graphResponse.edges.count, privacy: .public)"
      )
    }
  }
}

private struct MemoryAtlasEmptyState: View {
  var body: some View {
    ZStack {
      OmiColors.backgroundPrimary
      VStack(spacing: 8) {
        ZStack {
          Circle()
            .fill(OmiColors.backgroundRaised)
            .frame(width: 52, height: 52)
          Image(systemName: "point.3.connected.trianglepath.dotted")
            .scaledFont(size: 21)
            .foregroundColor(OmiColors.textSecondary)
        }
        Text("Your memory atlas is taking shape")
          .scaledFont(size: 14, weight: .medium)
          .foregroundColor(OmiColors.textPrimary)
        Text("Connected entities will appear as long-term memories grow.")
          .scaledFont(size: 12)
          .foregroundColor(OmiColors.textTertiary)
      }
    }
  }
}

// MARK: - Interactive Atlas Surface

private struct CanonicalMemoryAtlasSurface: View {
  let graph: KnowledgeGraphResponse
  let compact: Bool
  let onViewEvidence: ([String]) -> Void
  private let snapshot: MemoryAtlasSnapshot

  @State private var searchText = ""
  @State private var selectedNodeID: String?
  @State private var zoom: CGFloat = 1
  @State private var settledZoom: CGFloat = 1
  @State private var pan: CGSize = .zero
  @State private var settledPan: CGSize = .zero
  @State private var viewportSize: CGSize = .zero
  @State private var isCameraMoving = false
  @State private var matchingNodeIDs: Set<String>? = nil
  @State private var matchingEdges: [MemoryAtlasEdgePlacement]? = nil
  @State private var selectionHistory: [String] = []
  @State private var selectionHistoryIndex = -1

  init(
    graph: KnowledgeGraphResponse,
    compact: Bool,
    onViewEvidence: @escaping ([String]) -> Void
  ) {
    self.graph = graph
    self.compact = compact
    self.onViewEvidence = onViewEvidence
    let givenName = AuthService.shared.givenName.trimmingCharacters(in: .whitespacesAndNewlines)
    let previousProjection = MemoryAtlasCommunityProjectionStore.load()
    let nextSnapshot = MemoryAtlasLayoutEngine.makeSnapshot(
      graph: graph,
      userName: givenName.isEmpty ? nil : givenName,
      previousCommunityProjection: previousProjection
    )
    snapshot = nextSnapshot
    MemoryAtlasCommunityProjectionStore.save(nextSnapshot.communityProjection)
  }

  private var selectedNode: MemoryAtlasNodePlacement? {
    guard let selectedNodeID else { return nil }
    return snapshot.nodeByID[selectedNodeID]
  }

  private var selectedEdges: [MemoryAtlasEdgePlacement] {
    guard let selectedNodeID else { return [] }
    return snapshot.edgesByNodeID[selectedNodeID] ?? []
  }

  private var recentConnectionCount: Int {
    let threshold = Date().addingTimeInterval(-7 * 24 * 60 * 60)
    return graph.edges.filter { $0.createdAt >= threshold }.count
  }

  private var recentConnectionLabel: String {
    recentConnectionCount > 99 ? "99+ new connections" : "\(recentConnectionCount) new connections"
  }

  var body: some View {
    VStack(spacing: 0) {
      atlasToolbar

      GeometryReader { proxy in
        let plan = MemoryAtlasRenderPlanner.makePlan(
          snapshot: snapshot,
          viewportSize: proxy.size,
          zoom: zoom,
          pan: pan,
          compact: compact,
          selectedNodeID: selectedNodeID,
          matchingNodeIDs: matchingNodeIDs,
          matchingEdges: matchingEdges
        )

        ZStack {
          OmiColors.backgroundPrimary

          atlasField(size: proxy.size)

          atlasCanvas(size: proxy.size, plan: plan)

          if !isCameraMoving {
            relationshipLabels(size: proxy.size, plan: plan)
          }

          if zoom < 1.9 && !isCameraMoving {
            clusterTitles(size: proxy.size)
          }

          if !isCameraMoving {
            ForEach(plan.interactiveNodes) { placement in
              nodeButton(
                placement,
                size: proxy.size,
                relatedNodeIDs: plan.relatedNodeIDs,
                showLabel: plan.labelNodeIDs.contains(placement.id)
              )
            }
          }

          zoomControls
            .padding(compact ? 10 : 16)
            .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .bottomLeading)

          if !compact && selectedNode == nil {
            minimap(canvasSize: proxy.size)
              .padding(16)
              .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .bottomTrailing)
          }

          if !compact, let selectedNode {
            inspector(for: selectedNode)
              .padding(14)
              .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .trailing)
              .transition(.move(edge: .trailing).combined(with: .opacity))
          }
        }
        .contentShape(Rectangle())
        .gesture(panGesture)
        .simultaneousGesture(magnificationGesture(in: proxy.size))
        .simultaneousGesture(
          SpatialTapGesture().onEnded { value in
            selectNearestNode(to: value.location, in: proxy.size)
          }
        )
        .onAppear { viewportSize = proxy.size }
        .onChange(of: proxy.size) { _, newSize in viewportSize = newSize }
        .clipped()
      }

      if let selectedNode, compact {
        selectionStrip(for: selectedNode)
      } else if !compact {
        atlasLegend
      }
    }
    .background(OmiColors.backgroundPrimary)
    .accessibilityElement(children: .contain)
    .accessibilityIdentifier("canonical_memory_atlas")
    .onReceive(NotificationCenter.default.publisher(for: .desktopAutomationMemoryAtlasViewportRequested)) {
      notification in
      let target = notification.userInfo?["target"] as? String ?? "expanded"
      guard (target == "inline") == compact else { return }
      if notification.userInfo?["reset"] as? Bool == true {
        resetViewport()
        clearSelection()
        return
      }
      if let requestedZoom = notification.userInfo?["zoom"] as? Double {
        updateZoom(CGFloat(requestedZoom))
        memoryAtlasLogger.debug(
          "Automation viewport target=\(target, privacy: .public) zoom=\(requestedZoom, privacy: .public)"
        )
      }
      let requestedPanX = notification.userInfo?["pan_x"] as? Double
      let requestedPanY = notification.userInfo?["pan_y"] as? Double
      if requestedPanX != nil || requestedPanY != nil {
        pan = CGSize(
          width: CGFloat(requestedPanX ?? Double(pan.width)),
          height: CGFloat(requestedPanY ?? Double(pan.height))
        )
        settledPan = pan
      }
    }
    .onReceive(NotificationCenter.default.publisher(for: .desktopAutomationMemoryAtlasSelectionRequested)) {
      notification in
      let target = notification.userInfo?["target"] as? String ?? "expanded"
      guard (target == "inline") == compact,
        let nodeID = notification.userInfo?["node_id"] as? String
      else { return }
      select(nodeID, focusCamera: !compact)
    }
  }

  private var atlasToolbar: some View {
    HStack(spacing: 12) {
      if !compact {
        HStack(spacing: 7) {
          Image(systemName: "circle.hexagongrid.fill")
            .scaledFont(size: 12)
          Text(atlasLevelLabel)
            .scaledFont(size: 11, weight: .semibold)
            .lineLimit(1)
        }
        .foregroundColor(OmiColors.textSecondary)
        .frame(width: 110, alignment: .leading)
      }

      HStack(spacing: 8) {
        Image(systemName: "magnifyingglass")
          .scaledFont(size: 12)
          .foregroundColor(OmiColors.textTertiary)

        TextField("Search people, projects, and tools", text: $searchText)
          .textFieldStyle(.plain)
          .scaledFont(size: 12)
          .foregroundColor(OmiColors.textPrimary)
          .onSubmit { selectFirstSearchResult() }
          .onChange(of: searchText) { _, newValue in
            updateSearchMatches(newValue)
          }

        if !searchText.isEmpty {
          Button {
            searchText = ""
          } label: {
            Image(systemName: "xmark.circle.fill")
              .scaledFont(size: 11)
              .foregroundColor(OmiColors.textTertiary)
          }
          .buttonStyle(.plain)
        }
      }
      .padding(.horizontal, 12)
      .frame(width: compact ? 260 : 340, height: 34)
      .omiControlSurface(fill: OmiColors.backgroundRaised, radius: 13, stroke: OmiColors.border.opacity(0.3))

      Spacer()

      if let matchingNodeIDs {
        Text("\(matchingNodeIDs.count) match\(matchingNodeIDs.count == 1 ? "" : "es")")
          .scaledFont(size: 10, weight: .medium)
          .foregroundColor(OmiColors.textTertiary)
      } else if !compact {
        Text("Drag to move  ·  Pinch to explore")
          .scaledFont(size: 10)
          .foregroundColor(OmiColors.textQuaternary)
      }

      if recentConnectionCount > 0 {
        HStack(spacing: 6) {
          Circle()
            .fill(MemoryAtlasCluster.projects.color)
            .frame(width: 6, height: 6)
          Text(recentConnectionLabel)
            .scaledFont(size: 11, weight: .medium)
        }
        .foregroundColor(OmiColors.textSecondary)
      }
    }
    .padding(.horizontal, compact ? 12 : 18)
    .frame(height: compact ? 48 : 56)
    .background(OmiColors.backgroundPrimary)
  }

  private func atlasField(size: CGSize) -> some View {
    Canvas(opaque: false, colorMode: .linear) { context, _ in
      let spacing: CGFloat = compact ? 28 : 32
      let dot = OmiColors.textQuaternary.opacity(0.11)
      let offsetX = pan.width.truncatingRemainder(dividingBy: spacing)
      let offsetY = pan.height.truncatingRemainder(dividingBy: spacing)
      var path = Path()
      for x in stride(from: offsetX, through: size.width, by: spacing) {
        for y in stride(from: offsetY, through: size.height, by: spacing) {
          path.addEllipse(in: CGRect(x: x, y: y, width: 1.2, height: 1.2))
        }
      }
      context.fill(path, with: .color(dot))
    }
    .accessibilityHidden(true)
  }

  private func atlasCanvas(size: CGSize, plan: MemoryAtlasRenderPlan) -> some View {
    Canvas(opaque: false, colorMode: .linear) { context, _ in
      drawClusterContours(context: &context, size: size)
      drawEdges(context: &context, size: size, plan: plan)
      drawNodes(context: &context, size: size, plan: plan)
    }
    .accessibilityHidden(true)
  }

  private func drawClusterContours(context: inout GraphicsContext, size: CGSize) {
    for community in snapshot.communities {
      let center = point(for: community.center, in: size)
      let density = min(1, sqrt(Double(max(community.memberCount, 1))) / 16)
      let width = size.width * (0.16 + density * 0.07) * zoom
      let height = size.height * (0.18 + density * 0.09) * zoom
      let rect = CGRect(
        x: center.x - width / 2,
        y: center.y - height / 2,
        width: width,
        height: height
      )
      context.fill(
        Path(ellipseIn: rect),
        with: .radialGradient(
          Gradient(colors: [OmiColors.textSecondary.opacity(0.045), Color.clear]),
          center: center,
          startRadius: 0,
          endRadius: max(width, height) / 2
        )
      )
    }
  }

  private func drawEdges(
    context: inout GraphicsContext,
    size: CGSize,
    plan: MemoryAtlasRenderPlan
  ) {
    var crossCommunityPath = Path()
    for placement in plan.visibleEdges where placement.isCrossCommunity {
      crossCommunityPath.move(to: point(for: placement.source, in: size))
      crossCommunityPath.addQuadCurve(
        to: point(for: placement.target, in: size),
        control: point(for: placement.routeControl, in: size)
      )
    }
    if !crossCommunityPath.isEmpty {
      context.stroke(
        crossCommunityPath,
        with: .color(OmiColors.textQuaternary.opacity(selectedNodeID == nil ? 0.24 : 0.5)),
        lineWidth: selectedNodeID == nil ? 0.9 : 1.5
      )
    }

    for cluster in MemoryAtlasCluster.allCases {
      var path = Path()
      for placement in plan.visibleEdges where placement.cluster == cluster && !placement.isCrossCommunity {
        path.move(to: point(for: placement.source, in: size))
        path.addQuadCurve(
          to: point(for: placement.target, in: size),
          control: point(for: placement.routeControl, in: size)
        )
      }
      guard !path.isEmpty else { continue }
      context.stroke(
        path,
        with: .color(cluster.color.opacity(selectedNodeID == nil ? 0.25 : 0.74)),
        lineWidth: selectedNodeID == nil ? 0.85 : 1.7
      )
    }
  }

  private func drawNodes(
    context: inout GraphicsContext,
    size: CGSize,
    plan: MemoryAtlasRenderPlan
  ) {
    for cluster in MemoryAtlasCluster.allCases {
      var primaryPath = Path()
      var mutedPath = Path()
      for placement in plan.visibleNodes where placement.cluster == cluster {
        guard placement.id != selectedNodeID else { continue }
        let related = selectedNodeID == nil || plan.relatedNodeIDs.contains(placement.id)
        let matches = matchingNodeIDs == nil || matchingNodeIDs?.contains(placement.id) == true
        let radius = nodeRadius(for: placement)
        let center = point(for: placement.normalizedPosition, in: size)
        let rect = CGRect(
          x: center.x - radius,
          y: center.y - radius,
          width: radius * 2,
          height: radius * 2
        )
        if related && matches {
          primaryPath.addEllipse(in: rect)
        } else {
          mutedPath.addEllipse(in: rect)
        }
      }
      if !primaryPath.isEmpty {
        context.fill(primaryPath, with: .color(cluster.color.opacity(0.78)))
      }
      if !mutedPath.isEmpty {
        context.fill(mutedPath, with: .color(cluster.color.opacity(0.1)))
      }
    }

    if let anchorNodeID = snapshot.anchorNodeID,
       let anchor = plan.visibleNodes.first(where: { $0.id == anchorNodeID }) {
      drawSpecialNode(
        anchor,
        radius: compact ? 6 : (isInspectMode ? 18 : (isFocusMode ? 12 : 7)),
        color: OmiColors.textPrimary,
        opacity: selectedNodeID == nil || plan.relatedNodeIDs.contains(anchor.id) ? 0.86 : 0.16,
        context: &context,
        size: size
      )
    }

    if let selectedNode {
      drawSpecialNode(
        selectedNode,
        radius: compact ? 7 : (isInspectMode ? 26 : (isFocusMode ? 18 : 9)),
        color: selectedNode.cluster?.color ?? OmiColors.textPrimary,
        opacity: 0.95,
        context: &context,
        size: size
      )
    }
  }

  private func drawSpecialNode(
    _ placement: MemoryAtlasNodePlacement,
    radius: CGFloat,
    color: Color,
    opacity: Double,
    context: inout GraphicsContext,
    size: CGSize
  ) {
    let center = point(for: placement.normalizedPosition, in: size)
    let rect = CGRect(
      x: center.x - radius,
      y: center.y - radius,
      width: radius * 2,
      height: radius * 2
    )
    context.fill(Path(ellipseIn: rect), with: .color(color.opacity(opacity)))
  }

  private func nodeRadius(for placement: MemoryAtlasNodePlacement) -> CGFloat {
    if isInspectMode {
      return placement.clusterRank == 0 ? 16 : 12
    }
    if isFocusMode {
      return placement.clusterRank == 0 ? 10 : 7.2
    }
    if placement.clusterRank == 0 {
      if compact { return 5 }
      return zoom >= 4.2 ? 8 : 6
    }
    if compact { return zoom >= 1.2 ? 2.4 : 2.1 }
    if zoom >= 4.2 { return 4.8 }
    return zoom >= 1.45 ? 2.8 : 2.1
  }

  @ViewBuilder
  private func clusterTitles(size: CGSize) -> some View {
    ForEach(snapshot.communities) { community in
      Text(community.community.displayName)
        .scaledFont(size: compact ? 10 : 11, weight: .semibold)
        .textCase(.uppercase)
        .tracking(0.7)
        .foregroundColor(OmiColors.textTertiary)
        .lineLimit(1)
        .truncationMode(.tail)
        .frame(maxWidth: compact ? 120 : 170)
        .position(
          x: point(for: CGPoint(x: community.center.x, y: community.center.y - 0.11), in: size).x,
          y: max(18, point(for: CGPoint(x: community.center.x, y: community.center.y - 0.11), in: size).y)
        )
    }
  }

  private func nodeButton(
    _ placement: MemoryAtlasNodePlacement,
    size: CGSize,
    relatedNodeIDs: Set<String>,
    showLabel: Bool
  ) -> some View {
    let selected = selectedNodeID == placement.id
    let related = selectedNodeID == nil || relatedNodeIDs.contains(placement.id)
    let matches = matchingNodeIDs == nil || matchingNodeIDs?.contains(placement.id) == true
    let color = placement.cluster?.color ?? OmiColors.textPrimary
    let diameter = nodeDiameter(placement, selected: selected)

    return Button {
      if selected {
        clearSelection()
      } else {
        select(placement.id, focusCamera: !compact)
      }
    } label: {
      VStack(spacing: 5) {
        ZStack {
          if placement.recencyScore > 0.34 {
            Circle()
              .fill(color.opacity(0.05 + placement.recencyScore * 0.08))
              .frame(width: diameter + 18, height: diameter + 18)
              .blur(radius: 5)
          }
          if selected {
            Circle()
              .stroke(color.opacity(0.16), lineWidth: 8)
              .frame(width: diameter + 14, height: diameter + 14)
          }
          Circle()
            .fill(OmiColors.backgroundRaised)
            .overlay(Circle().stroke(color.opacity(selected ? 1 : 0.72), lineWidth: selected ? 2.2 : 1.2))
            .frame(width: diameter, height: diameter)
          if placement.reinforcementScore > 0 && diameter >= 18 {
            Circle()
              .trim(from: 0, to: CGFloat(placement.reinforcementScore) / 100)
              .stroke(color, style: StrokeStyle(lineWidth: 2.2, lineCap: .round))
              .rotationEffect(.degrees(-90))
              .frame(width: diameter + 7, height: diameter + 7)
          }
          if placement.id == snapshot.anchorNodeID {
            Image(systemName: "person.fill")
              .scaledFont(size: max(9, diameter * 0.38))
              .foregroundColor(OmiColors.textPrimary)
          } else if (isFocusMode || isInspectMode), let cluster = placement.cluster {
            Image(systemName: cluster.symbolName)
              .scaledFont(size: max(8, diameter * 0.3), weight: .medium)
              .foregroundColor(color.opacity(0.9))
          }
        }

        if showLabel {
          Text(placement.node.label)
            .scaledFont(
              size: compact ? 9.5 : (isInspectMode ? 14 : (isFocusMode ? 13 : 11)),
              weight: selected ? .semibold : .medium
            )
            .foregroundColor(OmiColors.textPrimary)
            .lineLimit(1)
            .truncationMode(.tail)
            .multilineTextAlignment(.center)
            .frame(maxWidth: compact ? 110 : 150)
            .padding(.horizontal, 6)
            .padding(.vertical, 3)
            .background(OmiColors.backgroundPrimary.opacity(0.9), in: Capsule())
        }
      }
      .contentShape(Rectangle())
      .opacity((related && matches) ? 1 : 0.2)
    }
    .buttonStyle(.plain)
    .position(point(for: placement.normalizedPosition, in: size))
    .help(placement.node.label)
    .accessibilityLabel(placement.node.label)
    .accessibilityValue(placement.node.nodeType.rawValue)
  }

  @ViewBuilder
  private func relationshipLabels(size: CGSize, plan: MemoryAtlasRenderPlan) -> some View {
    ForEach(plan.relationshipLabelEdges) { placement in
      Text(MemoryAtlasLayoutEngine.relationshipDisplayName(placement.edge.label))
        .scaledFont(size: 9, weight: .medium)
        .foregroundColor(OmiColors.textSecondary)
        .padding(.horizontal, 6)
        .padding(.vertical, 3)
        .background(OmiColors.backgroundRaised.opacity(0.94), in: Capsule())
        .overlay(Capsule().stroke(OmiColors.border.opacity(0.25), lineWidth: 0.5))
        .position(point(for: placement.routeControl, in: size))
        .allowsHitTesting(false)
    }
  }

  private func minimap(canvasSize: CGSize) -> some View {
    GeometryReader { proxy in
      let mapSize = proxy.size
      ZStack {
        RoundedRectangle(cornerRadius: 11, style: .continuous)
          .fill(OmiColors.backgroundRaised.opacity(0.96))
        RoundedRectangle(cornerRadius: 11, style: .continuous)
          .stroke(OmiColors.border.opacity(0.35), lineWidth: 0.7)

        Canvas { context, _ in
          for community in snapshot.communities {
            let center = CGPoint(
              x: community.center.x * mapSize.width,
              y: community.center.y * mapSize.height
            )
            context.stroke(
              Path(ellipseIn: CGRect(x: center.x - 4, y: center.y - 4, width: 8, height: 8)),
              with: .color(OmiColors.textSecondary.opacity(0.45)),
              lineWidth: 0.8
            )
          }
          for placement in snapshot.nodes.prefix(240) {
            let point = CGPoint(
              x: placement.normalizedPosition.x * mapSize.width,
              y: placement.normalizedPosition.y * mapSize.height
            )
            let color = placement.cluster?.color ?? OmiColors.textPrimary
            context.fill(
              Path(ellipseIn: CGRect(x: point.x - 1.2, y: point.y - 1.2, width: 2.4, height: 2.4)),
              with: .color(color.opacity(0.66))
            )
          }

          let visibleWidth = min(1, 1 / max(zoom, 0.01))
          let visibleHeight = min(1, 1 / max(zoom, 0.01))
          let centerX = 0.5 - pan.width / max(canvasSize.width * zoom, 1)
          let centerY = 0.5 - pan.height / max(canvasSize.height * zoom, 1)
          let viewport = CGRect(
            x: (centerX - visibleWidth / 2) * mapSize.width,
            y: (centerY - visibleHeight / 2) * mapSize.height,
            width: visibleWidth * mapSize.width,
            height: visibleHeight * mapSize.height
          )
          context.stroke(Path(roundedRect: viewport, cornerRadius: 2), with: .color(.white.opacity(0.72)), lineWidth: 1)
        }
      }
      .contentShape(Rectangle())
      .gesture(
        DragGesture(minimumDistance: 0).onChanged { value in
          let normalized = CGPoint(
            x: min(max(value.location.x / max(mapSize.width, 1), 0), 1),
            y: min(max(value.location.y / max(mapSize.height, 1), 0), 1)
          )
          pan = CGSize(
            width: (0.5 - normalized.x) * canvasSize.width * zoom,
            height: (0.5 - normalized.y) * canvasSize.height * zoom
          )
          settledPan = pan
        }
      )
    }
    .frame(width: 144, height: 92)
    .accessibilityLabel("Memory atlas minimap")
    .accessibilityIdentifier("memory_atlas_minimap")
  }

  private func inspector(for placement: MemoryAtlasNodePlacement) -> some View {
    let relationships = Array(selectedEdges.prefix(12))
    let evidenceIds = Array(Set(placement.node.memoryIds + selectedEdges.flatMap(\.edge.memoryIds)))
    let color = placement.cluster?.color ?? OmiColors.textPrimary

    return VStack(alignment: .leading, spacing: 0) {
      HStack(spacing: 8) {
        Button { navigateHistory(by: -1) } label: {
          Image(systemName: "chevron.left").frame(width: 24, height: 24)
        }
        .disabled(selectionHistoryIndex <= 0)
        Button { navigateHistory(by: 1) } label: {
          Image(systemName: "chevron.right").frame(width: 24, height: 24)
        }
        .disabled(selectionHistoryIndex < 0 || selectionHistoryIndex >= selectionHistory.count - 1)
        Spacer()
        Button { clearSelection() } label: {
          Image(systemName: "xmark").frame(width: 24, height: 24)
        }
        .accessibilityIdentifier("memory_atlas_close_inspector")
      }
      .buttonStyle(.plain)
      .foregroundColor(OmiColors.textTertiary)

      VStack(alignment: .leading, spacing: 8) {
        HStack(spacing: 10) {
          Circle()
            .fill(color.opacity(0.14))
            .overlay(Circle().stroke(color.opacity(0.8), lineWidth: 1.2))
            .frame(width: 38, height: 38)
            .overlay(Image(systemName: placement.cluster?.symbolName ?? "person.fill").foregroundColor(color))
          VStack(alignment: .leading, spacing: 2) {
            Text(placement.node.label)
              .scaledFont(size: 17, weight: .semibold)
              .foregroundColor(OmiColors.textPrimary)
              .lineLimit(2)
            Text(placement.node.nodeType.rawValue.capitalized)
              .scaledFont(size: 10, weight: .medium)
              .foregroundColor(OmiColors.textTertiary)
          }
        }

        HStack(spacing: 8) {
          metricPill(icon: "clock", text: relativeUpdateText(placement.node.updatedAt))
          metricPill(icon: "circle.hexagongrid", text: "\(placement.degree) links")
        }

        VStack(alignment: .leading, spacing: 5) {
          HStack {
            Text("Reinforcement")
            Spacer()
            Text("\(placement.evidenceCount) memor\(placement.evidenceCount == 1 ? "y" : "ies")")
          }
          .scaledFont(size: 10, weight: .medium)
          .foregroundColor(OmiColors.textSecondary)
          GeometryReader { proxy in
            Capsule().fill(OmiColors.backgroundPrimary)
              .overlay(alignment: .leading) {
                Capsule()
                  .fill(color.opacity(0.8))
                  .frame(width: proxy.size.width * CGFloat(placement.reinforcementScore) / 100)
              }
          }
          .frame(height: 5)
        }
      }
      .padding(.vertical, 14)

      Divider().overlay(OmiColors.border.opacity(0.25))

      Text("RELATIONSHIPS")
        .scaledFont(size: 9, weight: .semibold)
        .tracking(0.8)
        .foregroundColor(OmiColors.textQuaternary)
        .padding(.vertical, 11)

      ScrollView {
        LazyVStack(spacing: 5) {
          ForEach(relationships) { relationship in
            let otherID = relationship.edge.sourceId == placement.id
              ? relationship.edge.targetId : relationship.edge.sourceId
            if let other = snapshot.nodeByID[otherID] {
              Button { select(other.id, focusCamera: true) } label: {
                HStack(spacing: 9) {
                  Circle().fill((other.cluster?.color ?? OmiColors.textTertiary).opacity(0.75))
                    .frame(width: 6, height: 6)
                  VStack(alignment: .leading, spacing: 2) {
                    Text(other.node.label).lineLimit(1)
                    Text(MemoryAtlasLayoutEngine.relationshipDisplayName(relationship.edge.label))
                      .foregroundColor(OmiColors.textQuaternary)
                  }
                  .scaledFont(size: 10, weight: .medium)
                  Spacer()
                  Image(systemName: "chevron.right").scaledFont(size: 8)
                }
                .foregroundColor(OmiColors.textSecondary)
                .padding(.horizontal, 9)
                .frame(height: 42)
                .background(OmiColors.backgroundPrimary.opacity(0.72), in: RoundedRectangle(cornerRadius: 9))
              }
              .buttonStyle(.plain)
            }
          }
        }
      }

      Spacer(minLength: 10)

      Button { onViewEvidence(evidenceIds) } label: {
        Label("View supporting memories", systemImage: "doc.text.magnifyingglass")
          .scaledFont(size: 11, weight: .semibold)
          .frame(maxWidth: .infinity)
          .frame(height: 34)
          .foregroundColor(OmiColors.textPrimary)
          .background(OmiColors.backgroundPrimary, in: RoundedRectangle(cornerRadius: 10))
      }
      .buttonStyle(.plain)
      .disabled(evidenceIds.isEmpty)
      .accessibilityIdentifier("memory_atlas_view_evidence")
    }
    .padding(14)
    .frame(width: 310)
    .frame(maxHeight: 560)
    .background(OmiColors.backgroundSecondary.opacity(0.98), in: RoundedRectangle(cornerRadius: 18, style: .continuous))
    .overlay(RoundedRectangle(cornerRadius: 18).stroke(OmiColors.border.opacity(0.28), lineWidth: 0.7))
    .shadow(color: .black.opacity(0.24), radius: 18, y: 8)
    .accessibilityIdentifier("memory_atlas_inspector")
  }

  private func metricPill(icon: String, text: String) -> some View {
    Label(text, systemImage: icon)
      .scaledFont(size: 9, weight: .medium)
      .foregroundColor(OmiColors.textTertiary)
      .padding(.horizontal, 7)
      .frame(height: 24)
      .background(OmiColors.backgroundRaised, in: Capsule())
  }

  private func relativeUpdateText(_ date: Date) -> String {
    let days = max(0, Int(Date().timeIntervalSince(date) / 86_400))
    if days == 0 { return "Updated today" }
    if days == 1 { return "Updated yesterday" }
    if days < 30 { return "Updated \(days)d ago" }
    return "Updated \(max(1, days / 30))mo ago"
  }

  private func selectionStrip(for placement: MemoryAtlasNodePlacement) -> some View {
    let primaryEdge = selectedEdges.first
    let sourceNode = primaryEdge.flatMap { snapshot.nodeByID[$0.edge.sourceId] }
    let targetNode = primaryEdge.flatMap { snapshot.nodeByID[$0.edge.targetId] }
    let evidenceIds = Array(Set(selectedEdges.flatMap(\.edge.memoryIds)))
    let relationshipText: String = {
      guard let primaryEdge, let sourceNode, let targetNode else {
        return "\(placement.degree) connection\(placement.degree == 1 ? "" : "s")"
      }
      return "\(sourceNode.node.label) \(MemoryAtlasLayoutEngine.relationshipDisplayName(primaryEdge.edge.label)) \(targetNode.node.label)"
    }()

    return HStack(spacing: 14) {
      Circle()
        .fill((placement.cluster?.color ?? OmiColors.textPrimary).opacity(0.14))
        .overlay(Circle().stroke(placement.cluster?.color ?? OmiColors.textPrimary, lineWidth: 1.5))
        .frame(width: 34, height: 34)

      VStack(alignment: .leading, spacing: 2) {
        HStack(spacing: 7) {
          Text(placement.node.label)
            .scaledFont(size: compact ? 12 : 14, weight: .semibold)
            .foregroundColor(OmiColors.textPrimary)
          if !compact {
            Text(placement.node.nodeType.rawValue.replacingOccurrences(of: "_", with: " ").uppercased())
              .scaledFont(size: 8, weight: .semibold)
              .tracking(0.5)
              .foregroundColor(OmiColors.textTertiary)
              .padding(.horizontal, 6)
              .padding(.vertical, 3)
              .background(OmiColors.backgroundRaised, in: Capsule())
          }
        }
        Text(relationshipText)
          .scaledFont(size: compact ? 10 : 12)
          .foregroundColor(OmiColors.textTertiary)
          .lineLimit(1)
      }

      Spacer()

      if !compact {
        VStack(alignment: .trailing, spacing: 2) {
          Text("\(placement.degree)")
            .scaledFont(size: 12, weight: .semibold)
            .foregroundColor(OmiColors.textSecondary)
          Text("connections")
            .scaledFont(size: 9)
            .foregroundColor(OmiColors.textQuaternary)
        }
      }

      if !compact {
        Button {
          focus(on: placement)
        } label: {
          Label("Focus", systemImage: "scope")
            .scaledFont(size: 11, weight: .medium)
            .foregroundColor(OmiColors.textSecondary)
        }
        .buttonStyle(.plain)
        .accessibilityIdentifier("memory_atlas_focus_selection")
      }

      if evidenceIds.isEmpty {
        Text("Source details are still being linked")
          .scaledFont(size: 10)
          .foregroundColor(OmiColors.textQuaternary)
      } else {
        Button {
          onViewEvidence(evidenceIds)
        } label: {
          Label("View evidence", systemImage: "arrow.right")
            .scaledFont(size: 11, weight: .medium)
            .foregroundColor(placement.cluster?.color ?? OmiColors.textSecondary)
        }
        .buttonStyle(.plain)
        .accessibilityIdentifier("memory_atlas_view_evidence")
      }
    }
    .padding(.horizontal, compact ? 12 : 18)
    .frame(height: compact ? 58 : 72)
    .background(OmiColors.backgroundSecondary)
    .overlay(alignment: .top) {
      Divider().overlay(OmiColors.border.opacity(0.24))
    }
  }

  private var atlasLegend: some View {
    HStack(spacing: 18) {
      Text("Select a node to reveal its neighborhood")
        .scaledFont(size: 10)
        .foregroundColor(OmiColors.textQuaternary)

      Spacer()

      ForEach(MemoryAtlasCluster.allCases) { cluster in
        HStack(spacing: 5) {
          Circle().fill(cluster.color).frame(width: 6, height: 6)
          Text(cluster.title)
        }
        .scaledFont(size: 10)
        .foregroundColor(OmiColors.textTertiary)
      }
    }
    .padding(.horizontal, 18)
    .frame(height: 44)
    .background(OmiColors.backgroundSecondary)
  }

  private var zoomControls: some View {
    HStack(spacing: 1) {
      Button { updateZoom(zoom - 0.2) } label: {
        Image(systemName: "minus").frame(width: 28, height: 28)
      }
      .accessibilityIdentifier("memory_atlas_zoom_out")
      Button { resetViewport() } label: {
        Text("\(Int(zoom * 100))%")
          .scaledFont(size: 9, weight: .medium)
          .frame(width: 40, height: 28)
      }
      .help("Return to overview")
      .accessibilityIdentifier("memory_atlas_reset_viewport")
      Button { updateZoom(zoom + 0.2) } label: {
        Image(systemName: "plus").frame(width: 28, height: 28)
      }
      .disabled(zoom >= maximumZoom)
      .help(compact ? "Open the atlas for deeper exploration" : "Zoom in")
      .accessibilityIdentifier("memory_atlas_zoom_in")
    }
    .scaledFont(size: 10)
    .foregroundColor(OmiColors.textSecondary)
    .omiControlSurface(fill: OmiColors.backgroundRaised.opacity(0.96), radius: 10, stroke: OmiColors.border.opacity(0.3))
    .buttonStyle(.plain)
  }

  private var panGesture: some Gesture {
    DragGesture(minimumDistance: 3)
      .onChanged { value in
        isCameraMoving = true
        pan = CGSize(
          width: settledPan.width + value.translation.width,
          height: settledPan.height + value.translation.height
        )
      }
      .onEnded { _ in
        settledPan = pan
        isCameraMoving = false
      }
  }

  private func magnificationGesture(in size: CGSize) -> some Gesture {
    MagnifyGesture()
      .onChanged { value in
        isCameraMoving = true
        let nextZoom = min(
          max(settledZoom * value.magnification, MemoryAtlasZoomPolicy.minimumZoom),
          maximumZoom
        )
        let ratio = nextZoom / settledZoom
        let anchor = CGPoint(
          x: value.startAnchor.x * size.width,
          y: value.startAnchor.y * size.height
        )
        zoom = nextZoom
        pan = CGSize(
          width: (1 - ratio) * (anchor.x - size.width / 2) + ratio * settledPan.width,
          height: (1 - ratio) * (anchor.y - size.height / 2) + ratio * settledPan.height
        )
      }
      .onEnded { _ in
        settledZoom = zoom
        settledPan = pan
        isCameraMoving = false
      }
  }

  private var maximumZoom: CGFloat { MemoryAtlasZoomPolicy.maximumZoom(compact: compact) }

  private var isFocusMode: Bool {
    !compact && (selectedNodeID != nil || zoom >= MemoryAtlasZoomPolicy.focusModeZoom)
  }

  private var isInspectMode: Bool {
    !compact && zoom >= MemoryAtlasZoomPolicy.inspectModeZoom
  }

  private var atlasLevelLabel: String {
    if selectedNodeID != nil { return "Focus" }
    if isFocusMode { return "Focus" }
    if zoom < 1.35 { return "Overview" }
    if zoom < 1.9 { return "Neighborhood" }
    return "Detail"
  }

  private func point(for normalized: CGPoint, in size: CGSize) -> CGPoint {
    CGPoint(
      x: (normalized.x * size.width - size.width / 2) * zoom + size.width / 2 + pan.width,
      y: (normalized.y * size.height - size.height / 2) * zoom + size.height / 2 + pan.height
    )
  }

  private func nodeDiameter(_ placement: MemoryAtlasNodePlacement, selected: Bool) -> CGFloat {
    if isInspectMode {
      if selected { return 64 }
      if placement.id == snapshot.anchorNodeID { return 50 }
      if placement.clusterRank == 0 { return 42 }
      return 34
    }
    if selected { return compact ? 28 : (isFocusMode ? 50 : 34) }
    if placement.id == snapshot.anchorNodeID { return compact ? 24 : (isFocusMode ? 38 : 29) }
    if placement.clusterRank == 0 { return compact ? 19 : (isFocusMode ? 32 : 23) }
    return compact ? 10 : (isFocusMode ? 22 : 13)
  }

  private func nodeMatchesSearch(_ node: KnowledgeGraphNode) -> Bool {
    guard !searchText.isEmpty else { return true }
    return node.label.localizedCaseInsensitiveContains(searchText)
      || node.aliases.contains { $0.localizedCaseInsensitiveContains(searchText) }
  }

  private func updateSearchMatches(_ query: String) {
    guard !query.isEmpty else {
      matchingNodeIDs = nil
      matchingEdges = nil
      return
    }
    let matches = Set(snapshot.nodes.lazy.filter { placement in
      placement.node.label.localizedCaseInsensitiveContains(query)
        || placement.node.aliases.contains { $0.localizedCaseInsensitiveContains(query) }
    }.map(\.id))
    matchingNodeIDs = matches
    matchingEdges = snapshot.rankedEdges.filter { edge in
      matches.contains(edge.edge.sourceId) || matches.contains(edge.edge.targetId)
    }
  }

  private func selectFirstSearchResult() {
    guard let matchingNodeIDs, !matchingNodeIDs.isEmpty else { return }
    if let id = snapshot.nodes.first(where: { matchingNodeIDs.contains($0.id) })?.id {
      select(id, focusCamera: !compact)
    }
  }

  private func selectNearestNode(to location: CGPoint, in size: CGSize) {
    let hitRadius = max(12, 18 / zoom)
    var nearest: (placement: MemoryAtlasNodePlacement, distance: CGFloat)?
    for placement in snapshot.nodes {
      let rendered = point(for: placement.normalizedPosition, in: size)
      let distance = hypot(rendered.x - location.x, rendered.y - location.y)
      if distance <= hitRadius && (nearest == nil || distance < nearest!.distance) {
        nearest = (placement, distance)
      }
    }
    if let nearest { select(nearest.placement.id, focusCamera: !compact) }
  }

  private func updateZoom(_ value: CGFloat) {
    zoom = min(max(value, MemoryAtlasZoomPolicy.minimumZoom), maximumZoom)
    settledZoom = zoom
  }

  private func focus(on placement: MemoryAtlasNodePlacement) {
    guard viewportSize.width > 0, viewportSize.height > 0 else { return }
    let focusedZoom = MemoryAtlasZoomPolicy.focusedZoom(currentZoom: zoom, compact: compact)
    let focusedPan = CGSize(
      width: (0.5 - placement.normalizedPosition.x) * viewportSize.width * focusedZoom,
      height: (0.5 - placement.normalizedPosition.y) * viewportSize.height * focusedZoom
    )
    withAnimation(.easeOut(duration: 0.22)) {
      zoom = focusedZoom
      settledZoom = focusedZoom
      pan = focusedPan
      settledPan = focusedPan
    }
  }

  private func select(_ id: String, focusCamera: Bool) {
    guard let placement = snapshot.nodeByID[id] else { return }
    if selectionHistoryIndex < selectionHistory.count - 1 {
      selectionHistory = Array(selectionHistory.prefix(selectionHistoryIndex + 1))
    }
    if selectionHistory.last != id {
      selectionHistory.append(id)
      selectionHistoryIndex = selectionHistory.count - 1
    }
    withAnimation(.easeOut(duration: 0.22)) {
      selectedNodeID = id
    }
    if focusCamera { focus(on: placement) }
  }

  private func navigateHistory(by offset: Int) {
    let next = selectionHistoryIndex + offset
    guard selectionHistory.indices.contains(next) else { return }
    selectionHistoryIndex = next
    let id = selectionHistory[next]
    selectedNodeID = id
    if let placement = snapshot.nodeByID[id] { focus(on: placement) }
  }

  private func clearSelection() {
    withAnimation(.easeOut(duration: 0.18)) {
      selectedNodeID = nil
    }
  }

  private func resetViewport() {
    withAnimation(.easeOut(duration: 0.2)) {
      zoom = 1
      settledZoom = 1
      pan = .zero
      settledPan = .zero
    }
  }
}
