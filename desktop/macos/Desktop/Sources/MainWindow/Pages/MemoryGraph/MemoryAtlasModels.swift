import AppKit
import OmiSupport
import OmiTheme
import SwiftUI

// MARK: - Atlas Layout

enum MemoryAtlasCluster: String, CaseIterable, Identifiable {
  case person
  case organization
  case place
  case thing
  case concept

  var id: String { rawValue }

  var title: String {
    switch self {
    case .person: return "People"
    case .organization: return "Organizations"
    case .place: return "Places"
    case .thing: return "Things"
    case .concept: return "Concepts"
    }
  }

  var color: Color {
    switch self {
    case .person: return Color(nsColor: .systemTeal)
    case .organization: return Color(nsColor: .systemOrange)
    case .place: return Color(nsColor: .systemGreen)
    case .thing: return Ink.secondary
    case .concept: return Color(nsColor: .systemBlue)
    }
  }

  /// Present types orbit the person at the center as a shallow five-petal
  /// constellation. The two radii counterbalance the wide desktop canvas so
  /// the ring reads as a circle rather than a flattened row.
  static let starCenter = CGPoint(x: 0.5, y: 0.5)
  private static let starHorizontalRadius: CGFloat = 0.15
  private static let starVerticalRadius: CGFloat = 0.25

  static func centers(for activeClusters: [Self]) -> [Self: CGPoint] {
    guard !activeClusters.isEmpty else { return [:] }

    // A single active type has no constellation to form. Parking it on the ring
    // would strand every node in one corner of the canvas and leave the rest
    // empty, so it takes the center and orbits the anchor directly.
    if activeClusters.count == 1 {
      return [activeClusters[0]: starCenter]
    }

    let startingAngle = -Double.pi / 2
    let angularStep = 2 * Double.pi / Double(activeClusters.count)
    var result: [Self: CGPoint] = [:]
    for (index, cluster) in activeClusters.enumerated() {
      let angle = startingAngle + Double(index) * angularStep
      result[cluster] = CGPoint(
        x: starCenter.x + CGFloat(cos(angle)) * starHorizontalRadius,
        y: starCenter.y + CGFloat(sin(angle)) * starVerticalRadius
      )
    }
    return result
  }
}

struct MemoryAtlasEdgePlacement: Identifiable {
  let edge: KnowledgeGraphEdge
  let source: CGPoint
  let target: CGPoint
  let cluster: MemoryAtlasCluster
  /// Distinct relationship labels merged from parallel server edges between
  /// this pair (same endpoints, different verbs), in first-seen order. `edge`
  /// carries the first label for callers that only read a single verb;
  /// `MemoryAtlasLayoutEngine.combinedRelationshipDisplayName` renders all of
  /// them together for the inspector.
  let relationshipLabels: [String]
  /// Count of underlying server edges collapsed into this placement.
  /// Deliberately unused by rendering today — preserved as spring-strength
  /// input for a future force-directed layout.
  let weight: Int
  /// Whether both ends of this connection sit in the same neighbourhood.
  ///
  /// What lets the wiring itself show the grouping: drawn a little brighter
  /// inside a region than between two, the mesh thickens where a group is
  /// dense and thins at its edges, so the structure is legible without
  /// reading the territory layer at all.
  let withinNeighbourhood: Bool

  var id: String { edge.id }
}

/// A region of the map the layout found by structure rather than by type.
///
/// The relaxation already has to detect these to draw them apart. Naming them
/// is what turns "the dots are arranged meaningfully" into something a person
/// can act on: a place they can see from across the map and decide to enter.
struct MemoryAtlasNeighbourhood: Identifiable, Equatable {
  /// Opaque. Group numbers come out of a modularity pass and carry no meaning
  /// across rebuilds, so nothing user-facing may be derived from this.
  let id: Int
  let memberIDs: [String]
  /// Its most-connected few members, named.
  ///
  /// Deliberately not a generated title. A model asked to name this group
  /// would happily answer "Career" or "Family", and be confidently wrong in a
  /// way the user cannot check. Listing who is actually in it says exactly what
  /// the algorithm did and nothing more, and is falsifiable at a glance.
  let caption: String
  /// Normalized centre of its members.
  let center: CGPoint
  /// Normalized radius covering most of them. No longer the drawn shape — the
  /// coastline is — but still what decides where a caption goes and how far the
  /// camera pulls back when the region is entered.
  let radius: CGFloat
  /// The territory this neighbourhood holds, as closed rings in normalized map
  /// coordinates. Usually one; more than one when the group lives in two places
  /// and the map declines to invent a land bridge between them.
  let coastline: [[CGPoint]]
  /// Of the entities standing on this territory, the share that belong to it.
  ///
  /// Whether the region is a place or merely an average. A neighbourhood can be
  /// perfectly well detected and still be smeared through two others, and the
  /// difference is invisible in the caption: both are a list of names over a
  /// patch of canvas. Kept as the map's own check on the shape it drew, and
  /// measured against the coastline rather than a disc so it describes the
  /// ground actually claimed.
  let purity: Double

  var memberCount: Int { memberIDs.count }
}

struct MemoryAtlasSnapshot {
  let nodes: [MemoryAtlasNodePlacement]
  let edges: [MemoryAtlasEdgePlacement]
  let anchorNodeID: String?
  /// Largest first. Empty on maps too small or too sparse to have regions.
  let neighbourhoods: [MemoryAtlasNeighbourhood]
  let activeClusters: [MemoryAtlasCluster]
  let clusterCenters: [MemoryAtlasCluster: CGPoint]
  let nodeByID: [String: MemoryAtlasNodePlacement]
  /// Edge order is computed once when the graph is received. Camera updates can
  /// then filter this stable order instead of sorting the whole graph per frame.
  let rankedEdges: [MemoryAtlasEdgePlacement]
  let overviewEdges: [MemoryAtlasEdgePlacement]
  let neighborhoodEdges: [MemoryAtlasEdgePlacement]
  let detailEdges: [MemoryAtlasEdgePlacement]
  let edgesByNodeID: [String: [MemoryAtlasEdgePlacement]]
  let neighborIDsByNodeID: [String: Set<String>]
  /// The time axis for this graph, or `nil` when timestamps carry no spread.
  let timeline: MemoryAtlasTimeline?

  init(
    nodes: [MemoryAtlasNodePlacement],
    edges: [MemoryAtlasEdgePlacement],
    anchorNodeID: String?,
    clusterCenters: [MemoryAtlasCluster: CGPoint],
    neighbourhoods: [MemoryAtlasNeighbourhood] = []
  ) {
    self.nodes = nodes
    self.edges = edges
    self.anchorNodeID = anchorNodeID
    self.neighbourhoods = neighbourhoods
    self.activeClusters = MemoryAtlasCluster.allCases.filter { clusterCenters[$0] != nil }
    self.clusterCenters = clusterCenters
    self.timeline = MemoryAtlasTimeline.make(from: nodes.map(\.node))
    let indexedNodes = Dictionary(lastWriteWins: nodes.map { ($0.id, $0) })
    nodeByID = indexedNodes

    let keptSpokes = MemoryAtlasSnapshot.spokesWorthDrawing(
      edges, nodes: indexedNodes, anchorID: anchorNodeID)
    let sortedEdges = edges.sorted { lhs, rhs in
      let lhsRank = MemoryAtlasSnapshot.edgeRank(
        lhs, nodes: indexedNodes, anchorID: anchorNodeID, keptSpokes: keptSpokes)
      let rhsRank = MemoryAtlasSnapshot.edgeRank(
        rhs, nodes: indexedNodes, anchorID: anchorNodeID, keptSpokes: keptSpokes)
      return lhsRank < rhsRank
    }
    rankedEdges = sortedEdges

    overviewEdges = sortedEdges.filter { edge in
      MemoryAtlasSnapshot.maximumEndpointRank(edge, nodes: indexedNodes) < 4
    }
    neighborhoodEdges = sortedEdges.filter { edge in
      MemoryAtlasSnapshot.maximumEndpointRank(edge, nodes: indexedNodes) < 8
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

  func center(for cluster: MemoryAtlasCluster) -> CGPoint {
    clusterCenters[cluster] ?? MemoryAtlasCluster.starCenter
  }

  /// What gets drawn first when there is only room for a few dozen lines.
  ///
  /// The account holder's own connections sort last, however prominent their
  /// endpoints are. They used to sort *first* — the anchor's rank is zero, so
  /// every edge touching it led the order — and the budget is small enough
  /// (36 lines at overview) that on a real account it was spent entirely on
  /// them. The map reported 1,377 connections and drew a hundred copies of the
  /// one fact the user already knows: that everything here is theirs. The
  /// relationships between two other entities, which are the only ones that
  /// can tell them something, never made the cut.
  /// How many of the account holder's own connections still compete for the
  /// budget on merit.
  ///
  /// Not zero. Sending *every* spoke to the back leaves the one entity the user
  /// is certain is connected to everything drawn with no lines at all — the
  /// opposite lie from the starburst, and just as wrong. A handful, to their
  /// most prominent partners, says "you are in this" without saying it a
  /// hundred times.
  static let spokesDrawnOnMerit = 6

  static func spokesWorthDrawing(
    _ edges: [MemoryAtlasEdgePlacement],
    nodes: [String: MemoryAtlasNodePlacement],
    anchorID: String?
  ) -> Set<String> {
    guard let anchorID else { return [] }
    let partnerRank: (MemoryAtlasEdgePlacement) -> Int = { placement in
      let other =
        placement.edge.sourceId == anchorID ? placement.edge.targetId : placement.edge.sourceId
      return nodes[other]?.clusterRank ?? .max
    }
    return Set(
      edges
        .filter { $0.edge.sourceId == anchorID || $0.edge.targetId == anchorID }
        .sorted {
          partnerRank($0) == partnerRank($1) ? $0.id < $1.id : partnerRank($0) < partnerRank($1)
        }
        .prefix(spokesDrawnOnMerit)
        .map(\.id))
  }

  /// What gets drawn first when there is only room for a few dozen lines.
  ///
  /// The account holder's connections sort last beyond the first few, however
  /// prominent their endpoints are. They used to sort *first* — the anchor's
  /// rank is zero, so every edge touching it led the order — and the budget is
  /// small enough (36 lines at overview) that on a real account it was spent
  /// entirely on them. The map reported 1,377 connections and drew a hundred
  /// copies of the one fact the user already knows: that everything here is
  /// theirs. The relationships between two other entities, which are the only
  /// ones that can tell them something, never made the cut.
  static func edgeRank(
    _ placement: MemoryAtlasEdgePlacement,
    nodes: [String: MemoryAtlasNodePlacement],
    anchorID: String?,
    keptSpokes: Set<String> = []
  ) -> (Int, Int, Int, String) {
    let sourceRank = nodes[placement.edge.sourceId]?.clusterRank ?? .max
    let targetRank = nodes[placement.edge.targetId]?.clusterRank ?? .max
    let demoted =
      anchorID != nil
      && (placement.edge.sourceId == anchorID || placement.edge.targetId == anchorID)
      && !keptSpokes.contains(placement.id)
    return (demoted ? 1 : 0, min(sourceRank, targetRank), max(sourceRank, targetRank), placement.id)
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
}

enum MemoryAtlasDetailLevel: Equatable {
  case overview
  case neighborhood
  case detail
  case focus
  case inspect
}

struct MemoryAtlasRenderPlan {
  let visibleNodes: [MemoryAtlasNodePlacement]
  let visibleEdges: [MemoryAtlasEdgePlacement]
  let interactiveNodes: [MemoryAtlasNodePlacement]
  let labelNodeIDs: Set<String>
  /// Entities whose name is drawn above the mark instead of below it. Labels
  /// default to hanging below; flipping is how a sparse atlas keeps a name that
  /// would otherwise collide with an already-placed one and be dropped.
  let labelAboveNodeIDs: Set<String>
  /// Canvas labels from the automatic inspection threshold onward. Keeping
  /// these outside the SwiftUI overlay means a large graph can label every
  /// on-screen dot without building thousands of view/hit-test nodes per
  /// frame.
  let canvasLabelNodes: [MemoryAtlasNodePlacement]
  let usesCanvasLabels: Bool
  let isFullyLabelled: Bool
  let relatedNodeIDs: Set<String>
  let detailLevel: MemoryAtlasDetailLevel
}
