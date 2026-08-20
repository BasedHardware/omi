import AppKit
import OSLog
import OmiSupport
import OmiTheme
import SwiftUI

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
  static let desktopAutomationMemoryAtlasTimeRequested = Notification.Name(
    "desktopAutomationMemoryAtlasTimeRequested"
  )
  /// Selecting an entity or a connection is otherwise only reachable by
  /// clicking the canvas, which puts the inspector out of reach of every
  /// cursor-free check.
  static let desktopAutomationMemoryAtlasSelectRequested = Notification.Name(
    "desktopAutomationMemoryAtlasSelectRequested"
  )
  /// Going into a neighbourhood is otherwise only reachable by clicking its
  /// caption, which is a small target computed from the live camera — so the
  /// one interaction the territory layer exists for was the one no check could
  /// reach.
  static let desktopAutomationMemoryAtlasRegionRequested = Notification.Name(
    "desktopAutomationMemoryAtlasRegionRequested"
  )
}

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

enum MemoryAtlasRenderPlanner {
  static func makePlan(
    snapshot: MemoryAtlasSnapshot,
    viewportSize: CGSize,
    zoom: CGFloat,
    pan: CGSize,
    compact: Bool,
    selectedNodeID: String?,
    matchingNodeIDs: Set<String>?,
    matchingEdges: [MemoryAtlasEdgePlacement]? = nil,
    asOf: Date? = nil,
    timeline: MemoryAtlasTimeline? = nil,
    timeCursor: Double? = nil
  ) -> MemoryAtlasRenderPlan {
    let fullyLabelledZoom = MemoryAtlasZoomPolicy.fullyLabelledZoom(
      nodeCount: snapshot.nodes.count
    )
    let isFullyLabelled = !compact && zoom >= fullyLabelledZoom
    let usesCanvasLabels =
      !compact
      && zoom
        >= MemoryAtlasZoomPolicy.automaticCanvasLabelZoom(
          nodeCount: snapshot.nodes.count
        )
    let detailLevel: MemoryAtlasDetailLevel =
      if zoom < MemoryAtlasZoomPolicy.neighborhoodZoom {
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

    // Detail must be additive. The previous planner reduced the node budget
    // from 1,200 to 600 immediately after overview, which made visible dots
    // disappear on a small zoom-in. Keep a stable, salience-ordered cohort and
    // only add more of it as fidelity increases.
    let maximumNodeLimit: Int =
      if isFullyLabelled {
        snapshot.nodes.count
      } else {
        switch detailLevel {
        case .overview: 1_200
        case .neighborhood: 1_600
        case .detail: 2_400
        case .focus, .inspect: 3_200
        }
      }
    // The mesh is the structure, so it is not rationed at overview any more.
    //
    // Thirty-six of roughly fourteen hundred connections left the whole map to
    // be read from the positions of dots alone: clustering was there, and
    // invisible, because the thing that shows a group is dense wiring inside it
    // and sparse wiring out of it. Average degree on a real account is under
    // three, so the full mesh drawn as faint hairlines is a texture rather than
    // a thicket. The node budget above still bounds how many endpoints exist.
    let edgeLimit: Int =
      switch detailLevel {
      case .overview: 2_000
      case .neighborhood: 2_400
      case .detail: 3_000
      case .focus: 3_600
      case .inspect: 4_200
      }
    // These budgets exist to keep a multi-thousand-entity graph legible. An
    // atlas small enough to name in full needs no rationing: withholding
    // labels there just leaves unreadable dots on an empty canvas. Collision
    // admission still decides what actually fits.
    let isSmallAtlas = !compact && snapshot.nodes.count <= MemoryAtlasZoomPolicy.smallAtlasCeiling
    let labelsPerCluster: Int =
      if isSmallAtlas {
        snapshot.nodes.count
      } else {
        switch detailLevel {
        case .overview: compact ? 2 : 3
        case .neighborhood: compact ? 4 : 7
        case .detail: compact ? 5 : 11
        case .focus: compact ? 5 : 24
        case .inspect: compact ? 5 : 96
        }
      }
    let labelLimit: Int =
      if isSmallAtlas {
        snapshot.nodes.count
      } else {
        switch detailLevel {
        case .overview: 12
        case .neighborhood: 24
        case .detail: 36
        case .focus: 72
        case .inspect: 96
        }
      }

    var relatedNodeIDs: Set<String> = []
    if let selectedNodeID {
      relatedNodeIDs = snapshot.neighborIDsByNodeID[selectedNodeID] ?? []
      relatedNodeIDs.insert(selectedNodeID)
    }

    // The time cursor is a visibility filter layered over the stable layout: a
    // node keeps its position and simply has not been "born" yet. The anchor is
    // always present — "you" are the constant the rest of the memory accretes
    // around.
    let timeFilteredNodes: [MemoryAtlasNodePlacement]
    if let timeline, let timeCursor, timeCursor < 0.9995 {
      timeFilteredNodes = snapshot.nodes.filter { placement in
        placement.id == snapshot.anchorNodeID || timeline.isVisible(nodeID: placement.id, at: timeCursor)
      }
    } else if let asOf {
      timeFilteredNodes = snapshot.nodes.filter { placement in
        placement.id == snapshot.anchorNodeID || placement.node.createdAt <= asOf
      }
    } else {
      timeFilteredNodes = snapshot.nodes
    }

    // Camera movement changes where a node is painted, not whether it belongs
    // to the rendered cohort. Canvas clipping handles off-screen content while
    // this stable source order guarantees that zoom never drops entities just
    // because a threshold or viewport candidate set changed.
    let visibleNodes = priorityOrderedPrefix(
      timeFilteredNodes,
      limit: maximumNodeLimit,
      anchorNodeID: snapshot.anchorNodeID,
      selectedNodeID: selectedNodeID,
      relatedNodeIDs: relatedNodeIDs,
      matchingNodeIDs: matchingNodeIDs,
      includeBackgroundNodes: true
    )
    let visibleNodeIDs = Set(visibleNodes.map(\.id))

    let edgeCandidates: [MemoryAtlasEdgePlacement]
    if let selectedNodeID {
      edgeCandidates = snapshot.edgesByNodeID[selectedNodeID] ?? []
    } else if let matchingNodeIDs {
      edgeCandidates =
        matchingEdges
        ?? snapshot.rankedEdges.filter { edge in
          matchingNodeIDs.contains(edge.edge.sourceId) || matchingNodeIDs.contains(edge.edge.targetId)
        }
    } else {
      edgeCandidates = snapshot.rankedEdges
    }

    let selectedEdgeLimit = selectedNodeID == nil ? edgeLimit : min(edgeLimit, 80)
    let visibleEdges = Array(
      edgeCandidates.lazy
        .filter { edge in
          let isWithinTimeline =
            timeline.flatMap { timeline in
              timeCursor.map { cursor in
                cursor >= 0.9995 || timeline.fraction(for: edge.edge.createdAt) <= cursor
              }
            } ?? true
          let isBeforeAsOf = asOf.map { edge.edge.createdAt <= $0 } ?? true
          return isWithinTimeline
            && isBeforeAsOf
            && visibleNodeIDs.contains(edge.edge.sourceId) && visibleNodeIDs.contains(edge.edge.targetId)
        }
        .prefix(selectedEdgeLimit)
    )
    let labelableNodes = visibleNodes.filter {
      MemoryAtlasCatalogLayout.allowsAutomaticLabel(
        isCatalog: $0.isCatalog, id: $0.id, selectedNodeID: selectedNodeID, matchingNodeIDs: matchingNodeIDs)
    }
    let labelCandidates: [MemoryAtlasNodePlacement]
    if detailLevel == .inspect {
      labelCandidates = labelableNodes
    } else if selectedNodeID != nil {
      labelCandidates = labelableNodes.filter { relatedNodeIDs.contains($0.id) }
    } else if let matchingNodeIDs {
      labelCandidates = labelableNodes.filter { matchingNodeIDs.contains($0.id) }
    } else {
      labelCandidates = labelableNodes.filter { placement in
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
      forcedNodeIDs: Set([selectedNodeID, snapshot.anchorNodeID].compactMap { $0 }),
      allowsFlipAbove: isSmallAtlas
    )

    return MemoryAtlasRenderPlan(
      visibleNodes: visibleNodes,
      visibleEdges: visibleEdges,
      // Every entity remains on the Canvas at deep zoom, while the expensive
      // SwiftUI hit-target/label overlay stays bounded and grows gradually.
      interactiveNodes: labels.placements,
      // Once inspection has enough density-aware space, labels move into
      // Canvas immediately. They therefore appear while panning/zooming and
      // are not gated by selection or by the bounded SwiftUI overlay.
      labelNodeIDs: usesCanvasLabels ? [] : Set(labels.placements.map(\.id)),
      labelAboveNodeIDs: usesCanvasLabels ? [] : labels.aboveNodeIDs,
      canvasLabelNodes: usesCanvasLabels ? labelableNodes : [],
      usesCanvasLabels: usesCanvasLabels,
      isFullyLabelled: isFullyLabelled,
      relatedNodeIDs: relatedNodeIDs,
      detailLevel: detailLevel
    )
  }

  /// Fixed, non-interactive overview used by the Memories page. It keeps the
  /// preview cheap even for large graphs and deliberately does no camera work.
  static func makePreviewPlan(
    snapshot: MemoryAtlasSnapshot,
    nodeLimit: Int = 260,
    edgeLimit: Int = 24
  ) -> MemoryAtlasRenderPlan {
    let visibleNodes = priorityOrderedPrefix(
      snapshot.nodes,
      limit: nodeLimit,
      anchorNodeID: snapshot.anchorNodeID,
      selectedNodeID: nil,
      relatedNodeIDs: [],
      matchingNodeIDs: nil,
      includeBackgroundNodes: true
    )
    let visibleNodeIDs = Set(visibleNodes.map(\.id))
    let visibleEdges = Array(
      snapshot.overviewEdges.lazy
        .filter {
          visibleNodeIDs.contains($0.edge.sourceId) && visibleNodeIDs.contains($0.edge.targetId)
        }
        .prefix(edgeLimit)
    )
    return MemoryAtlasRenderPlan(
      visibleNodes: visibleNodes,
      visibleEdges: visibleEdges,
      interactiveNodes: [],
      labelNodeIDs: [],
      labelAboveNodeIDs: [],
      canvasLabelNodes: [],
      usesCanvasLabels: false,
      isFullyLabelled: false,
      relatedNodeIDs: [],
      detailLevel: .overview
    )
  }

  static func renderedPoint(
    for normalized: CGPoint,
    viewportSize: CGSize,
    zoom: CGFloat,
    pan: CGSize
  ) -> CGPoint {
    // Must use the same square span as the drawing path's `point(for:in:)`:
    // min(width, height) for both axes. Scaling x by the full viewport width
    // and y by the full height made collision detection believe horizontally
    // adjacent labels were farther apart than their rendered positions on
    // wide desktop windows, admitting labels that overlapped on the canvas.
    let span = MemoryAtlasLayoutEngine.projectionSpan(of: viewportSize)
    return CGPoint(
      x: (normalized.x - 0.5) * span * zoom + viewportSize.width / 2 + pan.width,
      y: (normalized.y - 0.5) * span * zoom + viewportSize.height / 2 + pan.height
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
      result.append(
        contentsOf: fairPrefix(
          tiers[tierIndex],
          limit: remaining,
          prioritizeCatalog: matchingNodeIDs != nil && tierIndex <= 1
        )
      )
    }
    return result
  }

  /// Labels admitted without collision, plus the subset drawn above their mark.
  private struct AdmittedLabels {
    var placements: [MemoryAtlasNodePlacement] = []
    var aboveNodeIDs: Set<String> = []
  }

  private static func admitLabels(
    _ candidates: [MemoryAtlasNodePlacement],
    limit: Int,
    viewportSize: CGSize,
    zoom: CGFloat,
    pan: CGSize,
    compact: Bool,
    forcedNodeIDs: Set<String>,
    allowsFlipAbove: Bool
  ) -> AdmittedLabels {
    var result = AdmittedLabels()
    var occupied: [CGRect] = []
    result.placements.reserveCapacity(limit)
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
      let height: CGFloat = compact ? 22 : 26
      let gap: CGFloat = compact ? 10 : 13
      let x = center.x - estimatedWidth / 2
      let below = CGRect(x: x, y: center.y + gap, width: estimatedWidth, height: height)
        .insetBy(dx: -5, dy: -3)
      // Flipping above is a second chance at the same name, not a second label.
      // A dense atlas cannot afford one — there, a collision still means the
      // name is dropped, because thousands of names never fit either way.
      let above = CGRect(x: x, y: center.y - gap - height, width: estimatedWidth, height: height)
        .insetBy(dx: -5, dy: -3)

      let forced = forcedNodeIDs.contains(placement.id)
      let fitsBelow = !occupied.contains { $0.intersects(below) }
      let fitsAbove = allowsFlipAbove && !occupied.contains { $0.intersects(above) }

      let chosen: CGRect
      if fitsBelow || forced {
        chosen = below
      } else if fitsAbove {
        chosen = above
        result.aboveNodeIDs.insert(placement.id)
      } else {
        continue
      }

      result.placements.append(placement)
      occupied.append(chosen)
      if result.placements.count == limit { break }
    }
    return result
  }
}

enum MemoryAtlasLayoutEngine {
  static func makeSnapshot(
    graph: KnowledgeGraphResponse,
    userName: String?
  ) -> MemoryAtlasSnapshot {
    // Graph responses are external data. Coalesce duplicate identifiers at the
    // boundary so a malformed server response cannot trap while building a UI.
    var nodes = uniqueNodes(from: graph.atlasNodes)
    let assertionNodeIDs = Set(nodes.map(\.id))
    // A canonical memory without a verified relationship is still a real
    // memory. It belongs in the atlas as a neutral, explicitly unconnected
    // mark rather than being silently removed from the user's browser. Keep it
    // out of the semantic layout below: using a type field or an inferred edge
    // here would make an unsupported claim about what that memory relates to.
    let catalogNodes = uniqueNodes(from: graph.catalogNodes ?? [])
      .filter { !assertionNodeIDs.contains($0.id) }
    let edges = uniqueEdges(from: graph.edges).filter {
      assertionNodeIDs.contains($0.sourceId) && assertionNodeIDs.contains($0.targetId)
    }
    var degree: [String: Int] = [:]
    for edge in edges {
      degree[edge.sourceId, default: 0] += 1
      degree[edge.targetId, default: 0] += 1
    }

    let owner = MemoryAtlasOwnerIdentity.resolve(nodes: nodes, userName: userName)
    let anchor: KnowledgeGraphNode? = owner.anchor.map { rawAnchor in
      guard let userName, !userName.isEmpty, MemoryAtlasOwnerIdentity.isSelfNode(rawAnchor)
      else { return rawAnchor }
      return KnowledgeGraphNode(
        id: rawAnchor.id,
        label: userName,
        nodeType: rawAnchor.nodeType,
        aliases: rawAnchor.aliases + [rawAnchor.label],
        memoryIds: rawAnchor.memoryIds,
        createdAt: rawAnchor.createdAt,
        updatedAt: rawAnchor.updatedAt
      )
    }
    if owner.isSynthetic, let anchor { nodes.append(anchor) }

    guard !nodes.isEmpty || !catalogNodes.isEmpty else {
      return MemoryAtlasSnapshot(nodes: [], edges: [], anchorNodeID: nil, clusterCenters: [:])
    }

    // Merge generic account-holder aliases into one identifiable center.
    let collapsedIDs: Set<String> = {
      guard let anchor else { return [] }
      return Set(
        nodes.filter { node in
          guard node.id != anchor.id else { return false }
          let label = node.label.lowercased()
          let normalizedUserName = userName?.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
          if let normalizedUserName, !normalizedUserName.isEmpty, label == normalizedUserName {
            return true
          }
          return MemoryAtlasOwnerIdentity.isSelfNode(node)
        }.map(\.id)
      )
    }()

    var grouped: [MemoryAtlasCluster: [KnowledgeGraphNode]] = [:]
    for node in nodes where node.id != anchor?.id && !collapsedIDs.contains(node.id) {
      grouped[cluster(for: node), default: []].append(node)
    }
    let activeClusters = MemoryAtlasCluster.allCases.filter { !(grouped[$0] ?? []).isEmpty }
    let clusterCenters = MemoryAtlasCluster.centers(for: activeClusters)

    let canonicalID: (String) -> String = { id in
      guard let anchorID = anchor?.id, collapsedIDs.contains(id) else { return id }
      return anchorID
    }

    // Every id that will actually receive a placement: the anchor plus every
    // grouped node. An edge naming anything else is either a dangling server
    // reference to a node absent from `graph.nodes`, or was already folded
    // into the anchor by `canonicalID`.
    var placeableNodeIDs: Set<String> = []
    if let anchor { placeableNodeIDs.insert(anchor.id) }
    for groupNodes in grouped.values {
      for node in groupNodes { placeableNodeIDs.insert(node.id) }
    }

    // Reroute every edge onto its canonical (post-collapse) endpoints before
    // merging parallel edges, so a relationship the collapsed self-node had
    // with some entity is considered for merging against the anchor's own
    // edge to that same entity rather than kept as a separate pair.
    let reroutedEdges: [KnowledgeGraphEdge] = edges.compactMap { edge in
      let sourceId = canonicalID(edge.sourceId)
      let targetId = canonicalID(edge.targetId)
      // A relationship the collapsed self-node had with the anchor becomes a
      // self-loop after rerouting — drop it rather than draw a node to itself.
      guard sourceId != targetId else { return nil }
      guard placeableNodeIDs.contains(sourceId), placeableNodeIDs.contains(targetId) else { return nil }
      // Only rebuild the edge when an endpoint actually moved, so neighbor and
      // evidence lookups resolve against the single center node.
      if sourceId == edge.sourceId && targetId == edge.targetId { return edge }
      return KnowledgeGraphEdge(
        id: edge.id,
        sourceId: sourceId,
        targetId: targetId,
        label: edge.label,
        memoryIds: edge.memoryIds,
        createdAt: edge.createdAt
      )
    }

    // The server can emit several edges for what is really one relationship
    // between two entities — e.g. "includes" and "with" for the same pair —
    // which otherwise doubles both the drawn line and the inspector's
    // Connections row for it. Merge by unordered endpoint pair before laying
    // out nodes, so a node's distinct-neighbor count (not its raw edge-touch
    // count) is what decides leaf/isolate placement below.
    let mergedEdges = mergeParallelEdges(reroutedEdges)

    var neighborIDs: [String: Set<String>] = [:]
    for merged in mergedEdges {
      neighborIDs[merged.edge.sourceId, default: []].insert(merged.edge.targetId)
      neighborIDs[merged.edge.targetId, default: []].insert(merged.edge.sourceId)
    }

    // Relatedness, from both signals the client already holds: the edges the
    // extractor drew, and the memories two entities were extracted from
    // together. The second matters more than it sounds — it finds
    // relationships nobody wrote down, which is most of them.
    //
    // The anchor is deliberately absent: they appear in nearly every memory, so
    // projecting them would make "was in a memory with you" the strongest
    // signal about every entity, which is the one thing that is true of all of
    // them. `coOccurrenceLinks` enforces this itself; not building the entry
    // just avoids collecting memories only to drop them.
    var memoryIDsByNodeID: [String: [String]] = [:]
    for groupNodes in grouped.values {
      for node in groupNodes { memoryIDsByNodeID[node.id] = node.memoryIds }
    }

    let relatedness =
      MemoryAtlasForceLayout.explicitLinks(
        edges: mergedEdges.map {
          (
            sourceID: $0.edge.sourceId, targetID: $0.edge.targetId,
            memoryCount: $0.edge.memoryIds.count
          )
        })
      + MemoryAtlasForceLayout.coOccurrenceLinks(
        memoryIDsByNodeID: memoryIDsByNodeID, excluding: anchor?.id)

    // Type stops deciding where a node goes and becomes a weak field it can
    // overrule: the constellation centres are now only somewhere a node drifts
    // toward when nothing it is related to pulls harder.
    var typeTargets: [String: CGPoint] = [:]
    for cluster in activeClusters {
      guard let center = clusterCenters[cluster] else { continue }
      for node in grouped[cluster] ?? [] { typeTargets[node.id] = center }
    }

    let layout = MemoryAtlasForceLayout.layout(
      nodeIDs: Array(placeableNodeIDs),
      links: relatedness,
      anchorID: anchor?.id,
      typeTargets: typeTargets,
      area: Self.layoutArea)

    var placements: [MemoryAtlasNodePlacement] = []
    if let anchor {
      placements.append(
        MemoryAtlasNodePlacement(
          node: anchor,
          cluster: nil,
          normalizedPosition: layout.positions[anchor.id] ?? MemoryAtlasCluster.starCenter,
          degree: neighborIDs[anchor.id]?.count ?? 0,
          clusterRank: 0,
          isCatalog: false
        )
      )
    }

    // Salience order no longer decides position, but it still decides which
    // names win a crowded viewport, so the rank the render planner reads is
    // computed exactly as before.
    for cluster in activeClusters {
      let sorted = (grouped[cluster] ?? []).sorted {
        let lhsScore = salience(node: $0, degree: degree[$0.id] ?? 0)
        let rhsScore = salience(node: $1, degree: degree[$1.id] ?? 0)
        if lhsScore == rhsScore { return $0.label.localizedCaseInsensitiveCompare($1.label) == .orderedAscending }
        return lhsScore > rhsScore
      }

      for (index, node) in sorted.enumerated() {
        placements.append(
          MemoryAtlasNodePlacement(
            node: node,
            cluster: cluster,
            normalizedPosition: layout.positions[node.id] ?? MemoryAtlasCluster.starCenter,
            degree: neighborIDs[node.id]?.count ?? 0,
            clusterRank: index,
            isCatalog: false
          )
        )
      }
    }
    let assertionPositions = Dictionary(lastWriteWins: placements.map { ($0.id, $0.normalizedPosition) })
    let catalogPositions = MemoryAtlasCatalogLayout.positions(
      catalog: catalogNodes,
      assertions: nodes.filter { $0.id != anchor?.id && !collapsedIDs.contains($0.id) },
      communities: layout.communities,
      assertionPositions: assertionPositions,
      ownerID: anchor?.id,
      area: Self.layoutArea)
    for (index, node) in catalogNodes.sorted(by: { $0.id < $1.id }).enumerated() {
      placements.append(
        MemoryAtlasNodePlacement(
          node: node,
          cluster: nil,
          normalizedPosition: catalogPositions[node.id] ?? MemoryAtlasCluster.starCenter,
          degree: 0,
          clusterRank: index + 1,
          isCatalog: true
        )
      )
    }
    let positions = Dictionary(lastWriteWins: placements.map { ($0.id, $0.normalizedPosition) })
    let clusters = Dictionary(
      lastWriteWins: placements.compactMap { placement in
        placement.cluster.map { (placement.id, $0) }
      })

    let edgePlacements = mergedEdges.map { merged -> MemoryAtlasEdgePlacement in
      let source = positions[merged.edge.sourceId] ?? MemoryAtlasCluster.starCenter
      let target = positions[merged.edge.targetId] ?? MemoryAtlasCluster.starCenter
      let cluster = clusters[merged.edge.sourceId] ?? clusters[merged.edge.targetId] ?? .concept
      let sourceGroup = layout.communities[merged.edge.sourceId]
      return MemoryAtlasEdgePlacement(
        edge: merged.edge,
        source: source,
        target: target,
        cluster: cluster,
        relationshipLabels: merged.relationshipLabels,
        weight: merged.weight,
        withinNeighbourhood: sourceGroup != nil
          && sourceGroup == layout.communities[merged.edge.targetId]
      )
    }

    return MemoryAtlasSnapshot(
      nodes: placements,
      edges: edgePlacements,
      anchorNodeID: anchor?.id,
      clusterCenters: centroids(of: placements, activeClusters: activeClusters),
      neighbourhoods: neighbourhoods(communities: layout.communities, placements: placements)
    )
  }

  /// Turns the layout's group numbers into regions the map can name.
  ///
  /// Two rules keep this from labelling noise. A region must be big enough to
  /// be a place — a modularity pass on a real account emits a long tail of
  /// three-entity groups, and captioning those would bury the handful that
  /// matter. And its extent is the distance covering most of its members, not
  /// all of them, so one entity that drifted across the map does not inflate a
  /// tight neighbourhood into a claim over half the canvas.
  static func neighbourhoods(
    communities: [String: Int],
    placements: [MemoryAtlasNodePlacement],
    captionMembers: Int = captionNames
  ) -> [MemoryAtlasNeighbourhood] {
    guard !communities.isEmpty else { return [] }
    let placementByID = Dictionary(lastWriteWins: placements.map { ($0.id, $0) })

    var membersByGroup: [Int: [String]] = [:]
    for id in communities.keys.sorted() {
      guard let group = communities[id], placementByID[id] != nil else { continue }
      membersByGroup[group, default: []].append(id)
    }

    // Scaled to the map: six entities is a neighbourhood on a small account and
    // rounding error on a large one.
    let floor = max(6, Int(Double(placementByID.count) * 0.015))

    // Every group over the floor competes for ground, including the ones too
    // small or too crowded to end up captioned. Leaving one out would not make
    // it disappear — it would hand its land to whichever neighbour is nearest,
    // and draw a coast through the middle of a group that is still on screen.
    var contenders: [Int: [CGPoint]] = [:]
    for group in membersByGroup.keys.sorted() {
      let members = membersByGroup[group] ?? []
      guard members.count >= floor else { continue }
      contenders[group] = members.compactMap { placementByID[$0]?.normalizedPosition }
    }
    let coastlines = MemoryAtlasIslands.coastlines(members: contenders)

    var regions: [MemoryAtlasNeighbourhood] = []
    for group in membersByGroup.keys.sorted() {
      let members = membersByGroup[group] ?? []
      guard members.count >= floor else { continue }
      let points = members.compactMap { placementByID[$0]?.normalizedPosition }
      guard !points.isEmpty else { continue }
      // A group whose members are spread too thin to hold any ground has no
      // territory to draw and no border to claim.
      let coastline = coastlines[group] ?? []
      guard !coastline.isEmpty else { continue }

      let center = CGPoint(
        x: points.map(\.x).reduce(0, +) / CGFloat(points.count),
        y: points.map(\.y).reduce(0, +) / CGFloat(points.count)
      )
      let distances = points.map { hypot($0.x - center.x, $0.y - center.y) }.sorted()
      let radius = distances[min(distances.count - 1, Int(Double(distances.count) * 0.8))]

      let own = Set(members)
      var inside = 0
      var mine = 0
      for placement in placements
      where memoryAtlasCoastlineContains(coastline, placement.normalizedPosition) {
        inside += 1
        if own.contains(placement.id) { mine += 1 }
      }

      // Most connected first, so the caption names the entities a person would
      // actually recognise the region by.
      let ranked =
        members
        .compactMap { placementByID[$0] }
        .sorted {
          if $0.degree == $1.degree {
            return $0.node.label.localizedCaseInsensitiveCompare($1.node.label) == .orderedAscending
          }
          return $0.degree > $1.degree
        }

      regions.append(
        MemoryAtlasNeighbourhood(
          id: group,
          memberIDs: members,
          caption: caption(from: ranked, count: captionMembers),
          center: center,
          radius: max(radius, 0.01),
          coastline: coastline,
          purity: inside == 0 ? 0 : Double(mine) / Double(inside)
        )
      )
    }

    return regions.sorted {
      $0.memberCount == $1.memberCount ? $0.id < $1.id : $0.memberCount > $1.memberCount
    }
  }

  /// The longest a member's label may be and still work as part of a region's
  /// name. Roughly a long proper noun — "Ho Chi Minh City", "Omi Desktop App".
  static let captionNameCeiling = 26

  /// The most a region's name may be and still be read at a glance.
  ///
  /// A place on a map is one word you recognise, not a list. Three names joined
  /// by separators ran to the width of a paragraph, truncated mid-word into
  /// things like "ORACLE ACCESS · CONSULT-ORACLE · DAVI…", and took longer to
  /// parse than the dots underneath it — so the map read as a wall of log lines
  /// laid over a graph. One name is a landmark: you either know it or you zoom
  /// in, and both are faster than reading three.
  static let captionNames = 1

  /// Picks the few names that describe a region.
  ///
  /// Connectedness alone is not enough, because the extractor does not only
  /// mint names. It also mints entities whose label is an entire sentence — a
  /// calendar invite's full subject line, a GitHub issue title with its quotes
  /// intact — and those are frequently a region's best-connected members. Taken
  /// literally, one of them produced a region caption 1,200 points wide that
  /// covered a quarter of the map and named nothing.
  ///
  /// So the caption prefers members whose labels read as names, and only falls
  /// back to truncating a sentence when a region has nothing shorter to offer.
  /// Reading like a name means short *and* few words: "Omi Desktop App" is a
  /// landmark and "explicit request by David" is a sentence that happens to fit.
  static func caption(
    from ranked: [MemoryAtlasNodePlacement], count: Int, ceiling: Int = captionNameCeiling
  ) -> String {
    func words(_ label: String) -> Int {
      label.split(whereSeparator: \.isWhitespace).count
    }
    var chosen =
      ranked
      .filter { $0.node.label.count <= ceiling && words($0.node.label) <= 3 }
      .prefix(count).map(\.node.label)
    if chosen.count < count {
      let already = Set(chosen)
      for placement in ranked
      where chosen.count < count && !already.contains(placement.node.label)
        && placement.node.label.count <= ceiling
      {
        chosen.append(placement.node.label)
      }
    }
    if chosen.count < count {
      let already = Set(chosen)
      for placement in ranked where chosen.count < count {
        let label = placement.node.label
        guard !already.contains(label), label.count > ceiling else { continue }
        chosen.append(String(label.prefix(ceiling - 1)).trimmingCharacters(in: .whitespaces) + "…")
      }
    }
    return chosen.joined(separator: " · ")
  }

  /// The region the relaxed map may occupy. Isolates are parked in the margin
  /// outside it, so it stops short of the canvas edge.
  ///
  /// Square, because the canvas it lands on is projected square. The map uses
  /// almost the available height: a smaller square created a visible box of
  /// empty space around dense accounts even though the underlying layout was
  /// circular. A wide box would stretch that circle into a desktop smear.
  static let layoutArea = CGRect(x: 0.06, y: 0.06, width: 0.88, height: 0.88)

  /// How many points one unit of normalized map space is worth on screen.
  ///
  /// Deliberately one number rather than one per axis. The relaxation works in
  /// a square and knows nothing about the window; projecting each axis onto its
  /// own side of the viewport distorted whatever shape it found by the window's
  /// aspect ratio, which on a wide desktop meant every account was drawn as a
  /// horizontal band. Taking the shorter side for both axes leaves the map's
  /// proportions alone and spends the extra width as margin — which is what the
  /// graph views this one is measured against do.
  static func projectionSpan(of size: CGSize) -> CGFloat { min(size.width, size.height) }

  /// One phrasing for "how big is this map", so the header and the timeline
  /// footer cannot describe the same thing in two different ways.
  static func countLabel(entities: Int, memories: Int? = nil, connections: Int) -> String {
    let entityLabel = "\(entities) entit\(entities == 1 ? "y" : "ies")"
    let connectionLabel = "\(connections) connection\(connections == 1 ? "" : "s")"
    guard let memories else { return "\(entityLabel) · \(connectionLabel)" }
    return "\(entityLabel) · \(memories) memor\(memories == 1 ? "y" : "ies") · \(connectionLabel)"
  }

  /// Whether the account holder's own connections should recede into the
  /// background rather than being drawn like every other relationship.
  ///
  /// They are the least informative lines on the map — everything is connected
  /// to you — and by far the most numerous, so at full strength a few hundred
  /// straight spokes cross every neighbourhood and the map reads as a star no
  /// matter where its entities actually sit. The exception is the one moment
  /// they *are* the subject: selecting the account holder is asking "what am I
  /// connected to", and the answer has to be drawn.
  static func anchorConnectionsRecede(anchorID: String?, selectedNodeID: String?) -> Bool {
    guard let anchorID else { return false }
    return selectedNodeID != anchorID
  }

  /// Where each type actually ended up, rather than where it was assigned.
  ///
  /// A type no longer owns a region of the canvas, so labelling a fixed petal
  /// "People" would point at empty space. The caption instead sits at the mean
  /// position of that type's entities — which is honest, and lands somewhere
  /// useful precisely because the weak type field keeps each type loosely
  /// gathered.
  static func centroids(
    of placements: [MemoryAtlasNodePlacement],
    activeClusters: [MemoryAtlasCluster]
  ) -> [MemoryAtlasCluster: CGPoint] {
    var totals: [MemoryAtlasCluster: (x: CGFloat, y: CGFloat, count: Int)] = [:]
    for placement in placements {
      guard let cluster = placement.cluster else { continue }
      var running = totals[cluster] ?? (0, 0, 0)
      running.x += placement.normalizedPosition.x
      running.y += placement.normalizedPosition.y
      running.count += 1
      totals[cluster] = running
    }

    var result: [MemoryAtlasCluster: CGPoint] = [:]
    for cluster in activeClusters {
      guard let running = totals[cluster], running.count > 0 else { continue }
      result[cluster] = CGPoint(
        x: running.x / CGFloat(running.count),
        y: running.y / CGFloat(running.count))
    }
    return result
  }

  /// One placement's worth of collapsed parallel edges: the representative
  /// edge (first-seen orientation and id), every distinct relationship label
  /// merged in, the union of citing memory ids, and how many raw edges fed
  /// into it.
  private struct MergedEdge {
    private(set) var edge: KnowledgeGraphEdge
    private(set) var relationshipLabels: [String]
    private(set) var weight: Int
    private var seenNormalizedLabels: Set<String>
    private var memoryIds: [String]
    private var seenMemoryIds: Set<String>

    init(edge: KnowledgeGraphEdge) {
      self.edge = edge
      relationshipLabels = [edge.label]
      seenNormalizedLabels = [MemoryAtlasLayoutEngine.normalizeRelationship(edge.label)]
      weight = 1
      memoryIds = edge.memoryIds
      seenMemoryIds = Set(edge.memoryIds)
    }

    mutating func merge(_ other: KnowledgeGraphEdge) {
      weight += 1
      let normalized = MemoryAtlasLayoutEngine.normalizeRelationship(other.label)
      if seenNormalizedLabels.insert(normalized).inserted {
        relationshipLabels.append(other.label)
      }
      var memoryIdsChanged = false
      for id in other.memoryIds where seenMemoryIds.insert(id).inserted {
        memoryIds.append(id)
        memoryIdsChanged = true
      }
      guard memoryIdsChanged else { return }
      // Keep the representative edge's own `memoryIds` in sync with the
      // union so a caller reading `edge.memoryIds` directly (evidence
      // resolution) sees every citing memory, not just the first edge's.
      edge = KnowledgeGraphEdge(
        id: edge.id,
        sourceId: edge.sourceId,
        targetId: edge.targetId,
        label: edge.label,
        memoryIds: memoryIds,
        createdAt: edge.createdAt
      )
    }
  }

  /// Collapses edges that share the same unordered endpoint pair into one
  /// `MergedEdge`, preserving the order pairs were first encountered so the
  /// result is deterministic for a fixed input order.
  private static func mergeParallelEdges(_ edges: [KnowledgeGraphEdge]) -> [MergedEdge] {
    var order: [String] = []
    var groups: [String: MergedEdge] = [:]
    for edge in edges {
      let pairKey =
        edge.sourceId <= edge.targetId
        ? "\(edge.sourceId)\u{0}\(edge.targetId)"
        : "\(edge.targetId)\u{0}\(edge.sourceId)"
      if var existing = groups[pairKey] {
        existing.merge(edge)
        groups[pairKey] = existing
      } else {
        groups[pairKey] = MergedEdge(edge: edge)
        order.append(pairKey)
      }
    }
    return order.compactMap { groups[$0] }
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

  static func cluster(for node: KnowledgeGraphNode) -> MemoryAtlasCluster {
    switch node.nodeType {
    case .person: return .person
    case .organization: return .organization
    case .place: return .place
    case .thing: return .thing
    case .concept: return .concept
    }
  }

  static func relationshipDisplayName(_ rawValue: String) -> String {
    normalizeRelationship(rawValue).replacingOccurrences(of: "_", with: " ")
  }

  /// Display text for a placement whose parallel edges carry more than one
  /// distinct verb. A merged pair reads as one relationship described two
  /// ways ("includes & with"), not two separate relationships, so the
  /// Connections list shows a single combined row per neighbor rather than
  /// one row per verb — that keeps the list's row count matching the actual
  /// number of distinct entities a node touches.
  static func combinedRelationshipDisplayName(_ rawValues: [String]) -> String {
    rawValues.map(relationshipDisplayName).joined(separator: " & ")
  }

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

}

// MARK: - Node Inspector

/// One memory backing a selected entity, flattened so the atlas surface does
/// not depend on the memories layer. The panel renders these directly instead
/// of navigating away, which is what makes the Brain Map a place you can stay
/// in while reading what an entity is made of.
struct MemoryAtlasEvidence: Identifiable, Equatable {
  let id: String
  let content: String
  let createdAt: Date?

  /// Resolves cited memory ids against whatever the memories layer has loaded,
  /// preserving that order so the inspector reads newest-first like the list.
  /// Ids with no loaded memory are simply absent — the panel reports the gap
  /// rather than the surface pretending the entity has less evidence than it
  /// does.
  static func resolve(_ ids: [String], in memories: [ServerMemory]) -> [MemoryAtlasEvidence] {
    let wanted = Set(ids)
    guard !wanted.isEmpty else { return [] }
    return memories.filter { wanted.contains($0.id) }.map {
      MemoryAtlasEvidence(id: $0.id, content: $0.content, createdAt: $0.createdAt)
    }
  }
}

/// What the inspector is describing.
///
/// The Brain Map has two things worth clicking — the entities and the
/// connections between them — and both answer the same three questions: what
/// is this, what does it touch, and which memories produced it. One panel
/// shape for both keeps traversal continuous instead of making a relationship
/// a dead end.
enum MemoryAtlasInspectorSubject: Equatable {
  case entity(title: String, typeName: String?, connectionSummary: String)
  case relationship(sourceLabel: String, targetLabel: String, verb: String)

  var title: String {
    switch self {
    case .entity(let title, _, _):
      return title
    case .relationship(let sourceLabel, let targetLabel, _):
      return "\(sourceLabel) → \(targetLabel)"
    }
  }

  var subtitle: String {
    switch self {
    case .entity(_, let typeName, let connectionSummary):
      return [typeName, connectionSummary].compactMap { $0 }.joined(separator: " · ")
    case .relationship(_, _, let verb):
      return verb
    }
  }

  /// Header for the section listing what this subject connects to.
  var relatedSectionTitle: String {
    switch self {
    case .entity: return "Connections"
    case .relationship: return "Between"
    }
  }
}

/// Right-hand inspector for the current selection.
///
/// Replaces the "View evidence" jump to Memories: selecting a node used to
/// change pages, which lost the camera, the time cursor, and the selection.
struct MemoryAtlasDetailPanel: View {
  let subject: MemoryAtlasInspectorSubject
  let accent: Color
  let related: [MemoryAtlasRelationshipRow]
  let evidence: [MemoryAtlasEvidence]
  let evidenceIsLoading: Bool
  let unresolvedEvidenceCount: Int
  let onOpenRelated: (MemoryAtlasRelationshipRow) -> Void
  /// Opens a cited memory on the Memories page with its detail panel showing.
  /// The inspector deliberately shows the whole memory in place, but a memory
  /// is also a thing you act on — edit it, check its provenance, delete it —
  /// and none of that belongs in a graph inspector.
  let onOpenMemory: (MemoryAtlasEvidence) -> Void
  /// Present once the user has followed a connection. Traversal without a way
  /// back turns every hop into a dead end you can only escape by hunting for
  /// the previous dot on the canvas.
  let onBack: (() -> Void)?
  let onFocus: () -> Void
  let onClose: () -> Void

  @State private var hoveredRelatedID: String?
  @State private var hoveredEvidenceID: String?

  var body: some View {
    VStack(alignment: .leading, spacing: 0) {
      header

      Divider().overlay(Ink.separator.opacity(0.2))

      ScrollView {
        VStack(alignment: .leading, spacing: 18) {
          if !related.isEmpty {
            section(subject.relatedSectionTitle) {
              VStack(alignment: .leading, spacing: 2) {
                ForEach(related) { row in
                  relatedRow(row)
                }
              }
              // Rows carry their own inset so the hover fill reads as a
              // target; pulling it back keeps their text on the same margin
              // as the section title.
              .padding(.horizontal, -6)
            }
          }

          section("From your memories") {
            evidenceSection
          }
        }
        .padding(16)
      }
    }
    .frame(width: 320)
    .background(Ink.rowFill)
    .overlay(alignment: .leading) {
      Rectangle().fill(Ink.separator.opacity(0.25)).frame(width: 1)
    }
    .accessibilityIdentifier("memory_atlas_detail_panel")
  }

  @ViewBuilder
  private var evidenceSection: some View {
    if evidenceIsLoading && evidence.isEmpty {
      HStack(spacing: 7) {
        ProgressView()
          .controlSize(.small)
          .tint(Ink.secondary)
        Text("Reading your memories…")
          .scaledFont(size: 11)
          .foregroundColor(Ink.secondary)
      }
    } else if evidence.isEmpty && unresolvedEvidenceCount == 0 {
      Text("Source memories are still being linked for this entity.")
        .scaledFont(size: 11)
        .foregroundColor(Ink.secondary)
        .fixedSize(horizontal: false, vertical: true)
    } else {
      ForEach(evidence) { item in
        evidenceRow(item)
      }
      if unresolvedEvidenceCount > 0 {
        // Evidence resolves against the full local cache, so a remaining gap
        // means the cited memory genuinely is not on this device — not that
        // the list simply had not paged far enough yet.
        Text(
          "\(unresolvedEvidenceCount) cited memor\(unresolvedEvidenceCount == 1 ? "y" : "ies") could not be found on this device"
        )
        .scaledFont(size: 10)
        .foregroundColor(Ink.secondary)
        .fixedSize(horizontal: false, vertical: true)
      }
    }
  }

  private var header: some View {
    HStack(alignment: .top, spacing: 10) {
      if let onBack {
        Button(action: onBack) {
          Image(systemName: "chevron.left")
            .scaledFont(size: 11, weight: .semibold)
            .foregroundColor(Ink.secondary)
            .frame(width: 22, height: 30)
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .help("Back to the previous entity")
        .accessibilityIdentifier("memory_atlas_inspector_back")
      }

      Circle()
        .fill(accent.opacity(0.14))
        .overlay(Circle().stroke(accent, lineWidth: 1.5))
        .frame(width: 30, height: 30)

      VStack(alignment: .leading, spacing: 3) {
        Text(subject.title)
          .scaledFont(size: 15, weight: .semibold)
          .foregroundColor(Ink.primary)
          .fixedSize(horizontal: false, vertical: true)
        Text(subject.subtitle)
          .scaledFont(size: 11)
          .foregroundColor(Ink.secondary)
          .fixedSize(horizontal: false, vertical: true)
      }

      Spacer(minLength: 4)

      Button(action: onFocus) {
        Image(systemName: "scope")
          .scaledFont(size: 11, weight: .medium)
          .foregroundColor(Ink.secondary)
          .frame(width: 24, height: 24)
          .contentShape(Rectangle())
      }
      .buttonStyle(.plain)
      .help("Center the map on this entity")
      .accessibilityIdentifier("memory_atlas_focus_selection")

      Button(action: onClose) {
        Image(systemName: "xmark")
          .scaledFont(size: 10, weight: .semibold)
          .foregroundColor(Ink.secondary)
          .frame(width: 24, height: 24)
          .contentShape(Rectangle())
      }
      .buttonStyle(.plain)
      .help("Clear selection (Esc)")
      .accessibilityIdentifier("memory_atlas_clear_selection")
    }
    .padding(.horizontal, 16)
    .padding(.vertical, 14)
  }

  @ViewBuilder
  private func section<Content: View>(
    _ title: String,
    @ViewBuilder content: () -> Content
  ) -> some View {
    VStack(alignment: .leading, spacing: 8) {
      Text(title.uppercased())
        .scaledFont(size: 9.5, weight: .semibold)
        .foregroundColor(Ink.secondary)
        .tracking(0.6)
      content()
    }
    .frame(maxWidth: .infinity, alignment: .leading)
  }

  /// A connection is a way through the graph, not a caption. Clicking one
  /// moves the inspector to the entity on the other end, so following a chain
  /// of relationships never requires hunting for the next dot on the canvas.
  private func relatedRow(_ row: MemoryAtlasRelationshipRow) -> some View {
    let isHovered = hoveredRelatedID == row.id
    return Button {
      onOpenRelated(row)
    } label: {
      HStack(alignment: .top, spacing: 8) {
        Circle()
          .fill(row.accent)
          .frame(width: 5, height: 5)
          .padding(.top, 5)
        VStack(alignment: .leading, spacing: 1) {
          Text(row.otherLabel)
            .scaledFont(size: 12, weight: .medium)
            .foregroundColor(isHovered ? Ink.primary : Ink.secondary)
            .fixedSize(horizontal: false, vertical: true)
          Text(row.relationship)
            .scaledFont(size: 10)
            .foregroundColor(Ink.secondary)
            .fixedSize(horizontal: false, vertical: true)
        }
        Spacer(minLength: 4)
        Image(systemName: "chevron.right")
          .scaledFont(size: 9, weight: .semibold)
          .foregroundColor(Ink.secondary)
          .opacity(isHovered ? 1 : 0)
          .padding(.top, 3)
      }
      .padding(.vertical, 5)
      .padding(.horizontal, 6)
      .frame(maxWidth: .infinity, alignment: .leading)
      .background(
        RoundedRectangle(cornerRadius: 7, style: .continuous)
          .fill(isHovered ? Ink.rowFill.opacity(0.7) : Color.clear)
      )
      .contentShape(Rectangle())
    }
    .buttonStyle(.plain)
    .onHover { hovering in
      if hovering {
        hoveredRelatedID = row.id
      } else if hoveredRelatedID == row.id {
        hoveredRelatedID = nil
      }
    }
    .help("Open \(row.otherLabel)")
    .accessibilityIdentifier("memory_atlas_connection_row")
  }

  private func evidenceRow(_ item: MemoryAtlasEvidence) -> some View {
    let isHovered = hoveredEvidenceID == item.id
    return Button {
      onOpenMemory(item)
    } label: {
      VStack(alignment: .leading, spacing: 4) {
        Text(item.content)
          .scaledFont(size: 11.5)
          .foregroundColor(isHovered ? Ink.primary : Ink.secondary)
          .fixedSize(horizontal: false, vertical: true)
          .frame(maxWidth: .infinity, alignment: .leading)
        // The date holds this row whether or not the cursor is here, so the
        // "Open" affordance can fade in without the row changing height.
        HStack(spacing: 4) {
          if let createdAt = item.createdAt {
            Text(createdAt.formatted(date: .abbreviated, time: .shortened))
              .scaledFont(size: 9.5)
              .foregroundColor(Ink.secondary)
          }
          Spacer(minLength: 4)
          HStack(spacing: 3) {
            Text("Open")
              .scaledFont(size: 9.5, weight: .medium)
            Image(systemName: "arrow.up.right")
              .scaledFont(size: 8, weight: .semibold)
          }
          .foregroundColor(Ink.secondary)
          .opacity(isHovered ? 1 : 0)
        }
      }
      .frame(maxWidth: .infinity, alignment: .leading)
      .padding(10)
      .background(
        RoundedRectangle(cornerRadius: 10, style: .continuous)
          .fill(Ink.rowFill.opacity(isHovered ? 0.95 : 0.6))
      )
      .contentShape(Rectangle())
    }
    .buttonStyle(.plain)
    .onHover { hovering in
      if hovering {
        hoveredEvidenceID = item.id
      } else if hoveredEvidenceID == item.id {
        hoveredEvidenceID = nil
      }
    }
    .help("Open this memory on the Memories page")
    .accessibilityIdentifier("memory_atlas_evidence_row")
  }
}

struct MemoryAtlasRelationshipRow: Identifiable, Equatable {
  let id: String
  /// Where clicking this row goes. Without it the inspector could name the
  /// entity on the other end but not open it.
  let otherNodeID: String
  let otherLabel: String
  let relationship: String
  let accent: Color
}

/// Picking a painted connection out of the atlas.
///
/// Lives outside the view so the two rules that matter — a line is only picked
/// when the click is genuinely on it, and the nearest one wins — are testable
/// without a window or a gesture.
enum MemoryAtlasHitTesting {
  struct Segment {
    let id: String
    let start: CGPoint
    let end: CGPoint
  }

  static func distance(from point: CGPoint, toSegmentFrom start: CGPoint, to end: CGPoint) -> CGFloat {
    let run = end.x - start.x
    let rise = end.y - start.y
    let lengthSquared = run * run + rise * rise
    // A zero-length segment is a point; projecting onto it would divide by zero.
    guard lengthSquared > 0 else { return hypot(point.x - start.x, point.y - start.y) }
    let projection = ((point.x - start.x) * run + (point.y - start.y) * rise) / lengthSquared
    let clamped = min(1, max(0, projection))
    let nearest = CGPoint(x: start.x + clamped * run, y: start.y + clamped * rise)
    return hypot(point.x - nearest.x, point.y - nearest.y)
  }

  /// How far off a painted line a click may land and still count, in points.
  /// Connections are drawn under 2pt wide, so this is forgiveness for aim, not
  /// a hit area wide enough to steal clicks from a neighbouring line.
  static let connectionTolerance: CGFloat = 5

  static func nearestSegment(
    to point: CGPoint,
    among segments: [Segment],
    within tolerance: CGFloat
  ) -> String? {
    var best: (id: String, distance: CGFloat)?
    for segment in segments {
      let distance = distance(from: point, toSegmentFrom: segment.start, to: segment.end)
      guard distance <= tolerance else { continue }
      if best.map({ distance < $0.distance }) ?? true {
        best = (segment.id, distance)
      }
    }
    return best?.id
  }
}

// MARK: - Canonical Atlas Containers

/// Holds the canvas until a complete graph is ready, so the first visit cannot
/// paint a synthetic owner as the whole map.
private struct CanonicalMemoryAtlasLoadGate<Content: View>: View {
  @ObservedObject var viewModel: MemoryGraphViewModel
  @ViewBuilder var content: () -> Content

  var body: some View {
    switch MemoryAtlasSurfacePresentation.phase(
      isLoading: viewModel.isLoading,
      isEmpty: viewModel.isEmpty,
      hasProjection: viewModel.canonicalAtlasProjection != nil,
      hasAttemptedLoad: viewModel.hasAttemptedCanonicalAtlasLoad
    ) {
    case .loading:
      ZStack {
        Color.clear
        ProgressView()
          .controlSize(.regular)
          .tint(Ink.secondary)
      }
      .frame(maxWidth: .infinity, maxHeight: .infinity)
      .accessibilityIdentifier("canonical_memory_atlas_loading")
    case .empty:
      VStack(spacing: OmiSpacing.sm) {
        Image(systemName: "brain")
          .scaledFont(size: OmiType.heading)
          .foregroundColor(Ink.secondary)
        Text("Brain map will appear once enough linked memories are available.")
          .scaledFont(size: 12.5)
          .foregroundColor(Ink.secondary)
          .multilineTextAlignment(.center)
      }
      .padding(OmiSpacing.lg)
      .frame(maxWidth: .infinity, maxHeight: .infinity)
      .accessibilityIdentifier("canonical_memory_atlas_empty")
    case .ready:
      content()
    }
  }
}

struct CanonicalMemoryAtlasPage: View {
  @ObservedObject var viewModel: MemoryGraphViewModel
  let onBack: () -> Void
  let evidenceProvider: ([String]) async -> [MemoryAtlasEvidence]
  /// Opens a cited memory on the Memories surface this page came from.
  let onOpenMemory: (String) -> Void

  /// Reads the memoized snapshot drawn below, so the counts cannot drift.
  private var headerCountLabel: String {
    if let projection = viewModel.canonicalAtlasProjection {
      return MemoryAtlasLayoutEngine.countLabel(
        entities: projection.snapshot.nodes.filter { !$0.isCatalog }.count,
        memories: projection.snapshot.nodes.filter(\.isCatalog).count,
        connections: projection.snapshot.edges.count)
    }
    return MemoryAtlasLayoutEngine.countLabel(
      entities: viewModel.graphResponse.atlasNodes.count,
      memories: viewModel.graphResponse.catalogNodes?.count,
      connections: viewModel.graphResponse.edges.count)
  }

  var body: some View {
    VStack(spacing: 0) {
      HStack(spacing: 12) {
        Button(action: onBack) {
          Label("Memories", systemImage: "chevron.left")
            .scaledFont(size: 12, weight: .semibold)
            .foregroundColor(Ink.secondary)
            .padding(.horizontal, 10)
            .frame(height: 30)
            .glassChip()
        }
        .buttonStyle(.plain)
        .accessibilityIdentifier("memory_atlas_back_to_memories")

        // "Brain Map" everywhere the user can see it: the atlas replaces the
        // legacy graph on the destination that already had that name, so
        // introducing a second name for the same place only splits the domain
        // vocabulary. "Atlas" survives in type and symbol names only.
        Text("Brain Map")
          .scaledFont(size: 17, weight: .semibold)
          .foregroundColor(Ink.primary)

        Spacer()

        // Show the semantic map and the complete canonical-memory catalog as
        // distinct counts; catalog records are visible but never fake edges.
        Text(headerCountLabel)
          .scaledFont(size: 12)
          .foregroundColor(Ink.secondary)
          .accessibilityIdentifier("memory_atlas_header_counts")
      }
      .padding(.horizontal, 18)
      .frame(height: 44)
      .background(Ink.rowFill)

      Divider().overlay(Ink.separator.opacity(0.25))

      CanonicalMemoryAtlasLoadGate(viewModel: viewModel) {
        CanonicalMemoryAtlasSurface(
          graph: viewModel.canonicalAtlasProjection?.graph ?? viewModel.graphResponse,
          projection: viewModel.canonicalAtlasProjection,
          compact: false,
          evidenceProvider: evidenceProvider,
          onOpenMemory: onOpenMemory,
          onRebuild: { Task { await viewModel.rebuildCanonicalAtlas() } },
          isRebuilding: viewModel.isRebuilding,
          onLeave: onBack
        )
      }
    }
    .background(Color.clear)
    .accessibilityIdentifier("canonical_memory_atlas_page")
    .task { await viewModel.prepareCanonicalAtlas() }
    .onAppear {
      memoryAtlasLogger.info(
        "Atlas page opened nodes=\(viewModel.graphResponse.atlasNodes.count, privacy: .public) edges=\(viewModel.graphResponse.edges.count, privacy: .public)"
      )
    }
  }
}

/// Memory hub presentation of the atlas.
///
/// The hub already owns navigation chrome (the Memory menu selects the
/// destination), so this variant renders the surface full-bleed instead of
/// stacking the page's own back/title bar underneath the hub bar. It is the
/// assertion-backed counterpart to `MemoryGraphPage`, which fills the same tab
/// for users still on the legacy graph.
struct CanonicalMemoryAtlasTabView: View {
  @ObservedObject var viewModel: MemoryGraphViewModel
  let evidenceProvider: ([String]) async -> [MemoryAtlasEvidence]
  /// Opens a cited memory on the hub's Memories destination.
  let onOpenMemory: (String) -> Void
  /// Where Escape goes once the map has nothing of its own left to undo.
  var onLeave: (() -> Void)?

  var body: some View {
    CanonicalMemoryAtlasLoadGate(viewModel: viewModel) {
      CanonicalMemoryAtlasSurface(
        graph: viewModel.canonicalAtlasProjection?.graph ?? viewModel.graphResponse,
        projection: viewModel.canonicalAtlasProjection,
        compact: false,
        evidenceProvider: evidenceProvider,
        onOpenMemory: onOpenMemory,
        onRebuild: { Task { await viewModel.rebuildCanonicalAtlas() } },
        isRebuilding: viewModel.isRebuilding,
        onLeave: onLeave
      )
    }
    .background(Color.clear)
    .accessibilityIdentifier("canonical_memory_atlas_tab")
    .task { await viewModel.prepareCanonicalAtlas() }
    .onAppear {
      memoryAtlasLogger.info(
        "Atlas tab opened nodes=\(viewModel.graphResponse.atlasNodes.count, privacy: .public) edges=\(viewModel.graphResponse.edges.count, privacy: .public)"
      )
    }
  }
}

// MARK: - Interactive Atlas Surface

private struct CanonicalMemoryAtlasSurface: View {
  let graph: KnowledgeGraphResponse
  /// Normal app surfaces pass the prebuilt projection from their view model.
  /// Export previews retain the lightweight fallback so they remain
  /// self-contained fixtures.
  let projection: MemoryAtlasProjection?
  let compact: Bool
  /// Resolves the memory ids an entity cites into readable evidence for the
  /// inspector. The surface stays independent of the memories layer; callers
  /// that have no memories to offer (offscreen exports) return nothing.
  ///
  /// Asynchronous because resolving a citation is a cache read, not a scan of
  /// whatever the memories list happens to be showing.
  let evidenceProvider: ([String]) async -> [MemoryAtlasEvidence]
  /// Leaves the atlas for a cited memory. Absent on surfaces with nowhere to
  /// go (offscreen exports, the inline preview).
  let onOpenMemory: ((String) -> Void)?
  /// Regenerating the server-side graph. Absent on surfaces that have no
  /// view model to drive it (the inline preview, offscreen export renders).
  let onRebuild: (() -> Void)?
  let isRebuilding: Bool
  /// Where Escape goes once the map itself has nothing left to undo. Absent on
  /// surfaces with nowhere to go, which is how those keep passing the key on.
  let onLeave: (() -> Void)?
  private let snapshot: MemoryAtlasSnapshot
  private let renderPlanCache: MemoryAtlasRenderPlanCache
  /// The cursor at which each relationship can first be painted. Precomputing
  /// this avoids walking every edge again on every 30 Hz replay frame.
  private let connectionBirthFractions: [Double]
  /// Deterministic offscreen renders (ViewExporter QA) pin the time cursor and
  /// suppress auto-play so the timeline captures a stable frame.
  private let previewTimeCursor: Double?
  private let previewEvidence: [MemoryAtlasEvidence]

  @State private var searchText = ""
  @State private var selectedNodeID: String?
  /// Set when the user clicked a painted connection rather than an entity.
  /// `selectedNodeID` still holds one endpoint so the map keeps its existing
  /// neighborhood emphasis; this only redirects the inspector to the
  /// relationship itself.
  @State private var selectedEdgeID: String?
  /// Entities the user followed connections away from, most recent last.
  @State private var selectionTrail: [String] = []
  @State private var evidence: [MemoryAtlasEvidence] = []
  @State private var evidenceIsLoading = false
  /// The ids the current evidence answers, so "how many are missing" compares
  /// against what was actually asked for rather than the live selection.
  @State private var requestedEvidenceIDs: [String] = []
  /// The neighbourhood the user went into, if any.
  ///
  /// Entering a place is a mode, not just a camera move. Inside one, the map
  /// stops drawing everyone else's coastline and gives the entities their names
  /// back — which is the trade the territory layer makes in the first place:
  /// names are hidden under a caption while you are reading the map as a whole,
  /// and handed back the moment you pick somewhere to look.
  @State private var enteredRegionID: Int?
  /// The zoom at which the user counts as having zoomed back out of the place
  /// they went into. Set from the camera entering actually used, because a
  /// fixed threshold throws the user out of any island big enough to be framed
  /// below it — which is every island on a map with only a few regions on it.
  @State private var departureZoom: CGFloat?
  @State private var zoom: CGFloat = 1
  @State private var settledZoom: CGFloat = 1
  @State private var pan: CGSize = .zero
  @State private var settledPan: CGSize = .zero
  @State private var viewportSize: CGSize = .zero
  @State private var isCameraMoving = false
  @State private var matchingNodeIDs: Set<String>? = nil
  @State private var matchingEdges: [MemoryAtlasEdgePlacement]? = nil
  /// Normalized as-of position on the time axis, 1 == now (show everything).
  @State private var timeCursor: Double = 1
  @State private var isTimePlaying = false
  @State private var didAutoplay = false
  @State private var playbackTask: Task<Void, Never>? = nil
  @FocusState private var searchIsFocused: Bool
  /// Persisted: once the user pauses or scrubs the timeline, the atlas stops
  /// auto-playing its growth animation on open. Playing all the way through is
  /// the delightful default; interrupting it is an explicit opt-out.
  @AppStorage("memory_atlas_timeline_autoplay") private var autoplayEnabled = true
  @Environment(\.accessibilityReduceMotion) private var reduceMotion

  init(
    graph: KnowledgeGraphResponse,
    projection: MemoryAtlasProjection? = nil,
    compact: Bool,
    evidenceProvider: @escaping ([String]) async -> [MemoryAtlasEvidence] = { _ in [] },
    onOpenMemory: ((String) -> Void)? = nil,
    onRebuild: (() -> Void)? = nil,
    isRebuilding: Bool = false,
    onLeave: (() -> Void)? = nil,
    previewTimeCursor: Double? = nil,
    /// Deterministic offscreen renders open the inspector, which is otherwise
    /// only reachable by tapping the canvas.
    previewSelectedNodeID: String? = nil,
    /// Selecting a connection, for the render that has to prove the
    /// relationship inspector exists.
    previewSelectedEdgeID: String? = nil,
    /// Offscreen renders capture a frame before an asynchronous cache read
    /// could land, so the export seeds the inspector's evidence directly
    /// instead of photographing a spinner.
    previewEvidence: [MemoryAtlasEvidence] = []
  ) {
    self.graph = graph
    self.projection = projection
    self.compact = compact
    self.evidenceProvider = evidenceProvider
    self.onOpenMemory = onOpenMemory
    self.onRebuild = onRebuild
    self.isRebuilding = isRebuilding
    self.onLeave = onLeave
    self.previewTimeCursor = previewTimeCursor
    self.previewEvidence = previewEvidence
    _timeCursor = State(initialValue: previewTimeCursor ?? 1)
    _selectedNodeID = State(initialValue: previewSelectedNodeID)
    _selectedEdgeID = State(initialValue: previewSelectedEdgeID)
    _evidence = State(initialValue: previewEvidence)
    _requestedEvidenceIDs = State(initialValue: previewEvidence.map(\.id))
    let atlasSnapshot: MemoryAtlasSnapshot
    if let projection {
      atlasSnapshot = projection.snapshot
    } else {
      let givenName = AuthService.shared.givenName.trimmingCharacters(in: .whitespacesAndNewlines)
      let displayName = AuthService.shared.displayName.trimmingCharacters(in: .whitespacesAndNewlines)
      let ownerName = givenName.isEmpty ? displayName : givenName
      atlasSnapshot = MemoryAtlasSnapshotCache.shared.snapshot(
        for: graph,
        userName: ownerName.isEmpty ? nil : ownerName
      )
    }
    snapshot = atlasSnapshot
    renderPlanCache = projection?.renderPlanCache ?? MemoryAtlasRenderPlanCache(snapshot: atlasSnapshot)
    if let projection {
      connectionBirthFractions = projection.connectionBirthFractions
    } else if let timeline = atlasSnapshot.timeline {
      connectionBirthFractions = atlasSnapshot.edges.map { placement in
        let endpointBirth =
          [placement.edge.sourceId, placement.edge.targetId].map { nodeID in
            nodeID == atlasSnapshot.anchorNodeID ? 0 : (timeline.playbackFractionByNodeID[nodeID] ?? 1)
          }.max() ?? 1
        return max(timeline.fraction(for: placement.edge.createdAt), endpointBirth)
      }
      .sorted()
    } else {
      connectionBirthFractions = []
    }
  }

  private var selectedNode: MemoryAtlasNodePlacement? {
    guard let selectedNodeID else { return nil }
    return snapshot.nodeByID[selectedNodeID]
  }

  private var selectedEdges: [MemoryAtlasEdgePlacement] {
    guard let selectedNodeID else { return [] }
    return snapshot.edgesByNodeID[selectedNodeID] ?? []
  }

  /// Selecting an edge always anchors `selectedNodeID` to one of its endpoints,
  /// so the lookup stays within that node's degree instead of the whole graph.
  private var selectedEdge: MemoryAtlasEdgePlacement? {
    guard let selectedEdgeID else { return nil }
    return selectedEdges.first { $0.id == selectedEdgeID }
  }

  /// The memory ids the current selection cites, newest-relationship-first and
  /// de-duplicated. An edge answers for itself; an entity answers for all of
  /// its connections.
  private var citedMemoryIDs: [String] {
    if let selectedEdge { return selectedEdge.edge.memoryIds }
    var seen = Set<String>()
    var ordered: [String] = []
    // Seed from the selected entity's own memory IDs first. The backend
    // writes memory_ids directly onto every extracted node independently of
    // its edges, so isolated entities — and memories that mention an entity
    // without producing a relationship — show no evidence if only edge IDs
    // are collected.
    if let selectedNode {
      for id in selectedNode.node.memoryIds where seen.insert(id).inserted {
        ordered.append(id)
      }
    }
    for id in selectedEdges.flatMap(\.edge.memoryIds) where seen.insert(id).inserted {
      ordered.append(id)
    }
    return ordered
  }

  /// Changing either half of the selection is a new evidence question.
  private var evidenceSelectionKey: String {
    "\(selectedNodeID ?? "")|\(selectedEdgeID ?? "")"
  }

  private var unresolvedEvidenceCount: Int {
    evidenceIsLoading ? 0 : max(0, requestedEvidenceIDs.count - evidence.count)
  }

  private var recentConnectionCount: Int {
    let threshold = Date().addingTimeInterval(-7 * 24 * 60 * 60)
    return graph.edges.filter { $0.createdAt >= threshold }.count
  }

  private var timeline: MemoryAtlasTimeline? { snapshot.timeline }

  /// The active as-of date, or `nil` when the cursor is parked at "now" (which
  /// means: render the whole atlas, no time filtering).
  private var asOfDate: Date? {
    guard let timeline, timeCursor < 0.9995 else { return nil }
    return timeline.date(atFraction: timeCursor)
  }

  private var visibleEntityCount: Int {
    guard let timeline, timeCursor < 0.9995 else { return snapshot.nodes.count }
    let anchorIsOutsideCursor = snapshot.anchorNodeID.map { !timeline.isVisible(nodeID: $0, at: timeCursor) } ?? false
    return timeline.visibleNodeCount(at: timeCursor) + (anchorIsOutsideCursor ? 1 : 0)
  }

  private var visibleConnectionCount: Int {
    guard timeline != nil, timeCursor < 0.9995 else { return snapshot.edges.count }
    return firstConnectionBirthIndex(after: timeCursor)
  }

  private func firstConnectionBirthIndex(after fraction: Double) -> Int {
    var lower = 0
    var upper = connectionBirthFractions.count
    while lower < upper {
      let middle = lower + (upper - lower) / 2
      if connectionBirthFractions[middle] > fraction {
        upper = middle
      } else {
        lower = middle + 1
      }
    }
    return lower
  }

  private var recentConnectionLabel: String {
    recentConnectionCount > 99 ? "99+ new connections" : "\(recentConnectionCount) new connections"
  }

  var body: some View {
    // The inspector is a sibling of the whole map, not an overlay on it: the
    // canvas keeps its full height and the map simply narrows, so opening an
    // entity never hides the part of the map you were looking at.
    HStack(spacing: 0) {
      mapColumn

      if !compact, let selectedNode {
        inspector(anchoredAt: selectedNode)
          .transition(.move(edge: .trailing).combined(with: .opacity))
      }
    }
    .animation(OmiMotion.gated(.easeOut(duration: 0.18)), value: selectedNodeID)
    .task(id: evidenceSelectionKey) { await loadEvidence() }
    .onEscapeKey(priority: .content) {
      guard !compact else { return false }
      return dismissTopmostState()
    }
  }

  @ViewBuilder
  private func inspector(anchoredAt placement: MemoryAtlasNodePlacement) -> some View {
    if let selectedEdge {
      relationshipPanel(for: selectedEdge, anchor: placement)
    } else {
      detailPanel(for: placement)
    }
  }

  /// Resolves the selection's citations through the provider.
  ///
  /// Stale evidence is cleared before the read rather than after it, so
  /// switching entities never shows the previous entity's memories under the
  /// new entity's name while the lookup is in flight.
  private func loadEvidence() async {
    guard previewEvidence.isEmpty else { return }
    let ids = citedMemoryIDs
    guard !ids.isEmpty else {
      evidence = []
      requestedEvidenceIDs = []
      evidenceIsLoading = false
      return
    }
    evidence = []
    requestedEvidenceIDs = ids
    evidenceIsLoading = true
    let resolved = await evidenceProvider(ids)
    guard !Task.isCancelled else { return }
    evidence = resolved
    evidenceIsLoading = false
  }

  private var mapColumn: some View {
    VStack(spacing: 0) {
      atlasToolbar

      GeometryReader { proxy in
        let plan = renderPlanCache.makePlan(
          viewportSize: proxy.size,
          zoom: zoom,
          pan: pan,
          compact: compact,
          selectedNodeID: selectedNodeID,
          matchingNodeIDs: matchingNodeIDs,
          matchingEdges: matchingEdges,
          asOf: asOfDate,
          timeline: timeline,
          timeCursor: timeCursor,
          isCameraMoving: isCameraMoving
        )

        // One placement pass per frame, shared by the tint the canvas paints
        // and the buttons laid over it, so the two cannot disagree about where
        // a region's name is.
        let (regions, quietened) = territory(in: proxy.size, plan: plan)

        ZStack {
          Color.black  // The mat. See `.glassMediaMat` on `.clipped()` below.

          atlasCanvas(size: proxy.size, plan: plan, regions: regions, quietened: quietened)
            // Camera gestures belong to the painted atlas only. Keeping them
            // off the enclosing ZStack prevents a click on zoom, playback, or
            // the selection strip from also selecting a node behind the control.
            .contentShape(Rectangle())
            .gesture(panGesture)
            .simultaneousGesture(magnificationGesture(in: proxy.size))
            .simultaneousGesture(
              SpatialTapGesture().onEnded { value in
                selectAtlasElement(at: value.location, in: proxy.size, plan: plan)
              }
            )

          if !isCameraMoving {
            ForEach(plan.interactiveNodes) { placement in
              nodeButton(
                placement,
                size: proxy.size,
                relatedNodeIDs: plan.relatedNodeIDs,
                showLabel: plan.labelNodeIDs.contains(placement.id)
                  && !quietened.contains(placement.id),
                labelAbove: plan.labelAboveNodeIDs.contains(placement.id)
              )
            }

            // Above the entities: a region name that an entity's own label
            // could cover would be the one label on the map with nothing
            // underneath it to explain itself.
            neighbourhoodCaptions(regions: regions)
          }

          zoomControls
            .padding(compact ? 8 : 12)
            .padding(.bottom, selectedNode == nil ? 0 : (compact ? 50 : 56))
            .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .bottomLeading)

          // Compact surfaces have no room for a side panel, so they keep the
          // strip. Wide surfaces use the inspector instead.
          if compact, let selectedNode {
            selectionStrip(for: selectedNode)
              .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .bottom)
          }

          if !compact {
            MemoryAtlasInputMonitor(
              onScroll: { delta, location in
                scrollZoom(by: delta, anchoredAt: location, in: proxy.size)
              },
              onFocusSearch: { searchIsFocused = true }
            )
            .accessibilityHidden(true)
          }
        }
        .onAppear { viewportSize = proxy.size }
        .onChange(of: proxy.size) { _, newSize in viewportSize = newSize }
        // Zooming back out is leaving the place you were in, pressed or not. Without this the
        // map keeps hiding every other coastline long after the user stopped looking at one,
        // and the only way back is a control they have no reason to know about.
        .onChange(of: zoom) { _, level in
          guard enteredRegionID != nil, let departureZoom, level < departureZoom else { return }
          leaveNeighbourhood()
        }
        // A neighbourhood id belongs to the snapshot that detected it: rebuild and the same
        // ground can return under a different number, or not at all. Being inside a place that
        // no longer exists is a mode with nothing on screen to explain it and no way out.
        .onChange(of: snapshot.neighbourhoods.map(\.id)) { _, regions in
          guard let entered = enteredRegionID, !regions.contains(entered) else { return }
          leaveNeighbourhood()
        }
        // The one dark surface a content page may draw: the map is emissive (light nodes, haloes
        // and labels, like a star chart) and vanished on the panel's near-white ground. The mat
        // also flips the environment so `Ink` resolves *up* for the chrome laid over it.
        .clipped().glassMediaMat()
      }

      VStack(spacing: 0) {
        if !compact, timeline != nil {
          timelineBar
        } else if !compact {
          // No meaningful timestamp spread — keep the legacy legend so the
          // level indicator and type key stay available.
          atlasLegend
        }
      }
    }
    .background(Color.clear)
    .accessibilityElement(children: .contain)
    .accessibilityIdentifier("canonical_memory_atlas")
    .onAppear(perform: maybeAutoplayTimeline)
    .onDisappear { stopPlayback(userInitiated: false) }
    .onReceive(NotificationCenter.default.publisher(for: .desktopAutomationMemoryAtlasViewportRequested)) {
      notification in
      let target = notification.userInfo?["target"] as? String ?? "page"
      let isInlineTarget = target == "inline"
      guard isInlineTarget == compact else { return }
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
    .onReceive(
      NotificationCenter.default.publisher(for: .desktopAutomationMemoryAtlasRegionRequested)
    ) { notification in
      let target = notification.userInfo?["target"] as? String ?? "page"
      guard (target == "inline") == compact else { return }
      if notification.userInfo?["leave"] as? Bool == true { return leaveNeighbourhood() }
      guard let wanted = notification.userInfo?["caption"] as? String,
        let match = snapshot.neighbourhoods.first(where: {
          $0.caption.localizedCaseInsensitiveContains(wanted)
        })
      else { return }
      // Its biggest island, which is the one a person would have pressed.
      let biggest =
        match.coastline
        .enumerated()
        .max { frame(of: $0.element)?.1 ?? 0 < frame(of: $1.element)?.1 ?? 0 }
      enter(
        MemoryAtlasNeighbourhoodLabels.Placed(
          regionID: match.id, index: biggest?.offset ?? 0, caption: match.caption, rect: .zero,
          ring: biggest?.element ?? []))
    }
    .onReceive(
      NotificationCenter.default.publisher(for: .desktopAutomationMemoryAtlasSelectRequested)
    ) { notification in
      let target = notification.userInfo?["target"] as? String ?? "page"
      guard (target == "inline") == compact else { return }
      if notification.userInfo?["clear"] as? Bool == true {
        clearSelection()
        return
      }
      // Drives the same state a canvas click would, so an automated check
      // exercises the real inspector rather than a parallel preview path.
      if let edgeID = notification.userInfo?["edge_id"] as? String,
        let edge = snapshot.edges.first(where: { $0.id == edgeID }),
        snapshot.nodeByID[edge.edge.sourceId] != nil
      {
        selectionTrail.removeAll()
        adoptSelection(edge.edge.sourceId, edgeID: edgeID)
        return
      }
      // By name as well as by id, because an entity's id is a server key
      // nothing on screen shows. Selecting the entity a QA step is actually
      // talking about otherwise means clicking a dot by pixel — which is not
      // reachable from a headless check, and on a multi-display machine is not
      // reliably reachable from a cursor either.
      let named = (notification.userInfo?["label"] as? String).flatMap { wanted in
        snapshot.nodes.first { $0.node.label.localizedCaseInsensitiveCompare(wanted) == .orderedSame }
          ?? snapshot.nodes.first { $0.node.label.localizedCaseInsensitiveContains(wanted) }
      }
      if let nodeID = (notification.userInfo?["node_id"] as? String).flatMap({
        snapshot.nodeByID[$0] != nil ? $0 : nil
      }) ?? named?.id {
        selectionTrail.removeAll()
        adoptSelection(nodeID)
      }
    }
    .onReceive(NotificationCenter.default.publisher(for: .desktopAutomationMemoryAtlasTimeRequested)) {
      notification in
      let target = notification.userInfo?["target"] as? String ?? "page"
      guard (target == "inline") == compact else { return }
      if notification.userInfo?["reset"] as? Bool == true {
        stopPlayback(userInitiated: true)
        withAnimation(.easeOut(duration: 0.2)) { timeCursor = 1 }
        return
      }
      if let fraction = notification.userInfo?["fraction"] as? Double {
        stopPlayback(userInitiated: true)
        timeCursor = min(max(fraction, 0), 1)
        clearSelectionIfHiddenAtCurrentTime()
      }
      if let play = notification.userInfo?["play"] as? Bool {
        if play {
          startPlayback(resetToStart: notification.userInfo?["reset_to_start"] as? Bool ?? false)
        } else {
          stopPlayback(userInitiated: true)
        }
      }
      memoryAtlasLogger.debug(
        "Automation timeline target=\(target, privacy: .public) cursor=\(timeCursor, privacy: .public) playing=\(isTimePlaying, privacy: .public)"
      )
    }
  }

  private var atlasToolbar: some View {
    HStack(spacing: 12) {
      HStack(spacing: 8) {
        Image(systemName: "magnifyingglass")
          .scaledFont(size: 12)
          .foregroundColor(Ink.secondary)

        TextField("Search your entities", text: $searchText)
          .textFieldStyle(.plain)
          .focused($searchIsFocused)
          .scaledFont(size: 12)
          .foregroundColor(Ink.primary)
          .onSubmit { selectFirstSearchResult() }
          .onChange(of: searchText) { _, newValue in
            updateSearchMatches(newValue)
          }
          .accessibilityLabel("Search entities")
          .accessibilityIdentifier("memory_atlas_search")

        if !searchText.isEmpty {
          Button {
            searchText = ""
          } label: {
            Image(systemName: "xmark.circle.fill")
              .scaledFont(size: 11)
              .foregroundColor(Ink.secondary)
          }
          .buttonStyle(.plain)
          .help("Clear search (Esc)")
          .accessibilityLabel("Clear search")
        }
      }
      .padding(.horizontal, 12)
      .frame(width: compact ? 250 : 320, height: 30)
      .glassChip()

      Spacer()

      if !compact {
        typeKey
      }

      if recentConnectionCount > 0 {
        HStack(spacing: 6) {
          Circle()
            .fill(snapshot.activeClusters.first?.color ?? Ink.secondary)
            .frame(width: 6, height: 6)
          Text(recentConnectionLabel)
            .scaledFont(size: 11, weight: .medium)
        }
        .foregroundColor(Ink.secondary)
      }

      // The legacy Brain Map carried a rebuild control; without it a thin or
      // stale server graph has no recovery path from inside the atlas.
      if let onRebuild {
        Button(action: onRebuild) {
          Image(systemName: "arrow.clockwise")
            .scaledFont(size: 11, weight: .medium)
            .foregroundColor(Ink.secondary.opacity(isRebuilding ? 0.35 : 1))
            .frame(width: 26, height: 26)
            .glassChip()
        }
        .buttonStyle(.plain)
        .disabled(isRebuilding)
        .help(isRebuilding ? "Rebuilding your Brain Map…" : "Rebuild the Brain Map from your memories")
        .accessibilityLabel("Rebuild Brain Map")
        .accessibilityIdentifier("memory_atlas_rebuild")
      }
    }
    .padding(.horizontal, compact ? 12 : 18)
    .frame(height: compact ? 40 : 44)
    .background(Color.clear)
    .accessibilityHint("Press Command-F to search. Press Return to select the first visible result.")
  }

  /// Which colour means which kind of entity.
  ///
  /// This used to be printed on the canvas at each type's centre. That made
  /// sense when a type owned a region; now that entities are placed by what
  /// they relate to, a type's mean position is often somewhere none of its
  /// entities actually are — and on a real account the "Places" caption landed
  /// on top of the Singapore node's own name. A key states the same thing
  /// without claiming a location for it.
  private var typeKey: some View {
    HStack(spacing: 11) {
      ForEach(snapshot.activeClusters) { cluster in
        HStack(spacing: 5) {
          Circle().fill(cluster.color).frame(width: 5, height: 5)
          Text(cluster.title)
            .scaledFont(size: 10)
            .foregroundColor(Ink.secondary)
        }
      }
    }
    .accessibilityIdentifier("memory_atlas_type_key")
  }

  private func atlasCanvas(
    size: CGSize, plan: MemoryAtlasRenderPlan,
    regions: [MemoryAtlasNeighbourhoodLabels.Placed],
    quietened: Set<String>
  ) -> some View {
    Canvas(opaque: false, colorMode: .linear) { context, _ in
      drawTerritories(context: &context, size: size, regions: regions)
      drawEdges(context: &context, size: size, plan: plan)
      drawNodes(context: &context, size: size, plan: plan)
      drawCanvasLabels(context: &context, size: size, plan: plan, quietened: quietened)
    }
    .accessibilityHidden(true)
  }

  /// What the map draws as territory right now, and whose names it hides to do
  /// it.
  ///
  /// One function because the two answers depend on each other. An entity
  /// standing on a named island loses its label to that island's caption, so
  /// the caption must not be pushed off its own ground avoiding a name that is
  /// about to disappear — which is what left most territories unnamed, and
  /// therefore undrawn, when the two were computed separately.
  private func territory(
    in size: CGSize, plan: MemoryAtlasRenderPlan
  ) -> (islands: [MemoryAtlasNeighbourhoodLabels.Placed], quietened: Set<String>) {
    // The replay and live camera gestures deliberately suppress SwiftUI
    // labels/targets. Re-solving caption placement during those frames would
    // still walk every visible entity against every coastline, despite none of
    // those captions being shown. Keep the camera/replay path to Canvas-only
    // work; territories return as soon as the frame settles.
    guard !isCameraMoving, !compact, matchingNodeIDs == nil,
      MemoryAtlasNeighbourhoodLabels.areVisible(
        detailLevel: plan.detailLevel, hasSelection: selectedNodeID != nil,
        isInsideNeighbourhood: enteredRegionID != nil)
    else { return ([], []) }

    let found = MemoryAtlasNeighbourhoodLabels.islands(
      snapshot.neighbourhoods,
      in: size,
      project: { point(for: $0, in: size) },
      focused: enteredRegionID)

    let captions = Dictionary(lastWriteWins: snapshot.neighbourhoods.map { ($0.id, $0.caption) })
    let budget = enteredRegionID == nil ? MemoryAtlasNeighbourhoodLabels.limit : Int.max

    // The entity names on the canvas, as boxes to stay out of. They hang below
    // their mark, and their width tracks the same estimate the canvas labeller
    // uses.
    func nameBoxes(hiding hidden: Set<String>) -> [CGRect] {
      plan.visibleNodes
        .filter { plan.labelNodeIDs.contains($0.id) && !hidden.contains($0.id) }
        .map { placement in
          let mark = point(for: placement.normalizedPosition, in: size)
          let width = min(160, max(48, CGFloat(placement.node.label.count) * 6.4 + 16))
          let above = plan.labelAboveNodeIDs.contains(placement.id)
          return CGRect(
            x: mark.x - width / 2, y: mark.y + (above ? -30 : 8), width: width, height: 20)
        }
    }

    /// Entities standing on ground the map has named. Inside a place, its own
    /// entities are the subject and they keep their names.
    ///
    /// Every visible entity against every island's outline is a hundred
    /// thousand edge crossings a frame, and this runs twice. The bounding box
    /// settles almost all of it in four comparisons: a territory covers a small
    /// part of the map, so nearly every entity is nowhere near nearly every
    /// island.
    func standingOn(_ islands: [MemoryAtlasNeighbourhoodLabels.Placed]) -> Set<String> {
      guard enteredRegionID == nil else { return [] }
      let bounded = islands.compactMap { island -> (CGRect, [CGPoint])? in
        guard let first = island.ring.first else { return nil }
        var minimum = first
        var maximum = first
        for vertex in island.ring {
          minimum = CGPoint(x: min(minimum.x, vertex.x), y: min(minimum.y, vertex.y))
          maximum = CGPoint(x: max(maximum.x, vertex.x), y: max(maximum.y, vertex.y))
        }
        return (
          CGRect(
            x: minimum.x, y: minimum.y, width: maximum.x - minimum.x,
            height: maximum.y - minimum.y), island.ring
        )
      }

      var hidden: Set<String> = []
      for placement in plan.visibleNodes
      where placement.id != snapshot.anchorNodeID && placement.id != selectedNodeID {
        let position = placement.normalizedPosition
        if bounded.contains(where: {
          $0.0.contains(position) && memoryAtlasCoastlineContains([$0.1], position)
        }) {
          hidden.insert(placement.id)
        }
      }
      return hidden
    }

    // Placed twice, because the two answers define each other: which names to
    // hide depends on which islands are drawn, and which islands can be drawn
    // depends on which names are in the way. The first pass finds the islands
    // by dodging every name; the second re-places them now that the names
    // standing on them are gone.
    //
    // One pass either way is wrong, and both ways were tried. Dodging every
    // name pushes captions off their own island for labels that are about to
    // disappear. Dodging none of them puts a caption on top of an entity that
    // then keeps its label, which is how "X (TWITTER)" ended up printed across
    // "Ho Chi Minh City".
    let candidates = MemoryAtlasNeighbourhoodLabels.place(
      found, captions: captions, in: size, avoiding: nameBoxes(hiding: []), limit: budget)
    let placed = MemoryAtlasNeighbourhoodLabels.place(
      found, captions: captions, in: size,
      avoiding: nameBoxes(hiding: standingOn(candidates)), limit: budget,
      insisting: enteredRegionID != nil)
    return (placed, standingOn(placed))
  }

  /// The land each neighbourhood holds, drawn under everything.
  ///
  /// Deliberately colourless. Type already owns hue on this canvas, and a
  /// second colour scale over the top of it would leave the user decoding two
  /// palettes at once — with thirty-odd regions to distinguish, one of them
  /// unwinnable. A region reads as a patch of ground, not as a category.
  ///
  /// And deliberately quiet. The wiring between entities is what says how the
  /// map is organised; territory is the annotation over it. Painted any
  /// stronger, the two layers compete and the result is neither a graph nor a
  /// map. The coast carries most of what little weight this layer has, because
  /// a line is legible at a fraction of the ink a fill needs.
  private func drawTerritories(
    context: inout GraphicsContext,
    size: CGSize,
    regions: [MemoryAtlasNeighbourhoodLabels.Placed]
  ) {
    for region in regions {
      guard region.ring.count >= 3 else { continue }
      var shape = Path()
      shape.move(to: point(for: region.ring[0], in: size))
      for vertex in region.ring.dropFirst() { shape.addLine(to: point(for: vertex, in: size)) }
      shape.closeSubpath()
      // The place the user went into is the one thing on the map they chose,
      // so it is drawn as chosen. Not loudly — a shade more ink than the
      // others is enough when it is also the only coast still on screen, and
      // it is what keeps the island reading as the frame once an entity
      // inside it is selected and the inspector takes over the right-hand
      // side.
      let entered = region.regionID == enteredRegionID
      // Even-odd, so an enclave inside a territory is drawn as the hole it is
      // rather than being filled over.
      context.fill(
        shape, with: .color(Ink.primary.opacity(entered ? 0.07 : 0.05)),
        style: FillStyle(eoFill: true))
      context.stroke(
        shape, with: .color(Ink.primary.opacity(entered ? 0.5 : 0.34)), lineWidth: 1)
    }
  }

  /// Region names as real controls rather than painted text.
  ///
  /// There are at most eight, so the cost of a view each is nothing, and it
  /// buys the two things a canvas cannot: a press that lands exactly where the
  /// caption is drawn, and a name VoiceOver can read. A territory you can see
  /// but not enter would be a worse map than one with no territories on it.
  @ViewBuilder
  private func neighbourhoodCaptions(
    regions: [MemoryAtlasNeighbourhoodLabels.Placed]
  ) -> some View {
    ForEach(regions) { region in
      MemoryAtlasNeighbourhoodCaption(
        caption: region.caption,
        size: region.rect.size,
        enter: { enter(region) }
      )
      .position(x: region.rect.midX, y: region.rect.midY)
      .help(enteredRegionID == region.regionID ? "Leave this neighbourhood" : "Go to \(region.caption)")
      .accessibilityLabel("Neighbourhood around \(region.caption)")
      .accessibilityHint(
        enteredRegionID == region.regionID
          ? "Returns to the whole map" : "Goes to this neighbourhood and names its entities"
      )
      .accessibilityIdentifier("memory_atlas_neighbourhood_\(region.regionID)")
    }
  }

  /// Takes the camera into a region: close enough that its entities are named,
  /// far enough that you can still see its edges.
  private func enter(_ region: MemoryAtlasNeighbourhoodLabels.Placed) {
    // Pressing the place you are already in is the way back out, because it is
    // the control the user's attention is already on. Without it, leaving means
    // guessing that the zoom-out button also drops the mode.
    guard enteredRegionID != region.regionID else { return leaveNeighbourhood() }
    guard viewportSize.width > 0, viewportSize.height > 0,
      let neighbourhood = snapshot.neighbourhoods.first(where: { $0.id == region.regionID })
    else { return }

    // Framed on the island that was pressed, not on the average of the group's
    // members. For a neighbourhood spread over two pieces of ground the average
    // is the water between them: entering one sent the camera to open sea, with
    // the island itself off the side of the canvas and nothing on screen to say
    // where the user had just arrived.
    let framed = frame(of: region.ring) ?? (neighbourhood.center, neighbourhood.radius)
    let camera = MemoryAtlasNeighbourhoodLabels.entering(
      center: framed.0,
      radius: framed.1,
      viewport: viewportSize,
      zoomRange: MemoryAtlasZoomPolicy.minimumZoom...maximumZoom)
    departureZoom = MemoryAtlasNeighbourhoodLabels.departureZoom(
      enteredAt: camera.zoom, neighbourhoodZoom: MemoryAtlasZoomPolicy.neighborhoodZoom,
      minimumZoom: MemoryAtlasZoomPolicy.minimumZoom)
    withAnimation(OmiMotion.gated(.easeOut(duration: 0.26))) {
      enteredRegionID = region.regionID
      zoom = camera.zoom
      settledZoom = camera.zoom
      pan = camera.pan
      settledPan = camera.pan
    }
  }

  /// The middle of an island and how far it reaches, in normalized map
  /// coordinates. Half the diagonal rather than half a side, so a long thin
  /// island is framed by its length and not cropped to its width.
  private func frame(of ring: [CGPoint]) -> (CGPoint, CGFloat)? {
    guard let first = ring.first else { return nil }
    var minimum = first
    var maximum = first
    for vertex in ring {
      minimum = CGPoint(x: min(minimum.x, vertex.x), y: min(minimum.y, vertex.y))
      maximum = CGPoint(x: max(maximum.x, vertex.x), y: max(maximum.y, vertex.y))
    }
    return (
      CGPoint(x: (minimum.x + maximum.x) / 2, y: (minimum.y + maximum.y) / 2),
      hypot(maximum.x - minimum.x, maximum.y - minimum.y) / 2
    )
  }

  /// Back out to the whole map, without moving the camera.
  ///
  /// Deliberately not a zoom-out. The user came in to look at something and is
  /// probably still looking at it; snapping the camera away would undo the
  /// thing they asked for. Only the mode ends — every coastline comes back and
  /// the captions take their entities' names again.
  private func leaveNeighbourhood() {
    departureZoom = nil
    withAnimation(OmiMotion.gated(.easeOut(duration: 0.2))) { enteredRegionID = nil }
  }

  private func drawEdges(
    context: inout GraphicsContext,
    size: CGSize,
    plan: MemoryAtlasRenderPlan
  ) {
    let paintBounds = canvasPaintBounds(for: size)
    let anchorID = snapshot.anchorNodeID
    let spokesAreBackground = MemoryAtlasLayoutEngine.anchorConnectionsRecede(
      anchorID: anchorID, selectedNodeID: selectedNodeID)

    for cluster in snapshot.activeClusters {
      var path = Path()
      var within = Path()
      var spokes = Path()
      for placement in plan.visibleEdges where placement.cluster == cluster {
        let source = point(for: placement.source, in: size)
        let target = point(for: placement.target, in: size)
        let segmentBounds = CGRect(
          x: min(source.x, target.x) - 1,
          y: min(source.y, target.y) - 1,
          width: max(abs(source.x - target.x), 2),
          height: max(abs(source.y - target.y), 2)
        )
        // The rendered segment lies inside its bounding box, so a disjoint
        // box cannot cross the viewport. This is paint-only culling: the plan
        // and its stable entity cohort remain unchanged.
        guard segmentBounds.intersects(paintBounds) else { continue }
        let touchesAnchor =
          placement.edge.sourceId == anchorID || placement.edge.targetId == anchorID
        if spokesAreBackground && touchesAnchor {
          spokes.move(to: source)
          spokes.addLine(to: target)
        } else if placement.withinNeighbourhood && selectedNodeID == nil {
          within.move(to: source)
          within.addLine(to: target)
        } else {
          path.move(to: source)
          path.addLine(to: target)
        }
      }
      // Hairlines. With the whole mesh drawn rather than a few dozen of it,
      // the per-connection weight that used to read as one relationship now
      // has to read as texture — at the old 0.25 the map was a wall of lines.
      // A connection crossing between two neighbourhoods is drawn fainter than
      // one inside a neighbourhood, so density falls off at a group's edge the
      // way the graph says it does.
      if !path.isEmpty {
        context.stroke(
          path,
          with: .color(cluster.color.opacity(selectedNodeID == nil ? 0.055 : 0.74)),
          lineWidth: selectedNodeID == nil ? 0.6 : 1.7
        )
      }
      if !within.isEmpty {
        context.stroke(within, with: .color(cluster.color.opacity(0.14)), lineWidth: 0.7)
      }
      // The account holder's own spokes, fainter again — and much fainter than
      // they were, because the budget that used to let only a few dozen lines
      // onto the map was holding this back by accident. Drawn in full at the
      // old weight, eight hundred tethers to the middle of the map buried every
      // other connection under a starburst. "You are connected to this" is the
      // least informative thing the map can say, so it is the first thing that
      // gives way.
      if !spokes.isEmpty {
        context.stroke(
          spokes,
          with: .color(cluster.color.opacity(selectedNodeID == nil ? 0.028 : 0.16)),
          lineWidth: 0.5
        )
      }
    }
  }

  private func drawNodes(
    context: inout GraphicsContext,
    size: CGSize,
    plan: MemoryAtlasRenderPlan
  ) {
    // While the time cursor is engaged, an entity that was just "born" blooms
    // briefly as the playhead sweeps past its creation date, then settles into
    // the constellation — the atlas visibly grows rather than snapping in.
    let replayCursor = timeCursor < 0.9995 ? timeCursor : nil
    let paintBounds = canvasPaintBounds(for: size)

    var catalogPrimaryPath = Path()
    var catalogMutedPath = Path()
    for placement in plan.visibleNodes where placement.isCatalog && placement.id != selectedNodeID {
      let related = selectedNodeID == nil || plan.relatedNodeIDs.contains(placement.id)
      let matches = matchingNodeIDs == nil || matchingNodeIDs?.contains(placement.id) == true
      let radius = nodeRadius(for: placement)
      let center = point(for: placement.normalizedPosition, in: size)
      guard
        paintBounds.intersects(
          CGRect(x: center.x - radius, y: center.y - radius, width: radius * 2, height: radius * 2)
        )
      else { continue }
      let rect = CGRect(x: center.x - radius, y: center.y - radius, width: radius * 2, height: radius * 2)
      if related && matches {
        catalogPrimaryPath.addEllipse(in: rect)
      } else {
        catalogMutedPath.addEllipse(in: rect)
      }
    }
    if !catalogPrimaryPath.isEmpty {
      context.fill(catalogPrimaryPath, with: .color(Ink.secondary.opacity(0.28)))
    }
    if !catalogMutedPath.isEmpty {
      context.fill(catalogMutedPath, with: .color(Ink.secondary.opacity(0.055)))
    }

    for cluster in snapshot.activeClusters {
      var primaryPath = Path()
      var mutedPath = Path()
      for placement in plan.visibleNodes where placement.cluster == cluster {
        guard placement.id != selectedNodeID else { continue }
        let related = selectedNodeID == nil || plan.relatedNodeIDs.contains(placement.id)
        let matches = matchingNodeIDs == nil || matchingNodeIDs?.contains(placement.id) == true
        var radius = nodeRadius(for: placement)
        let center = point(for: placement.normalizedPosition, in: size)

        // Canvas otherwise builds paths for every deep-zoom entity, including
        // those far outside the clipped viewport. Culling here keeps maximum
        // zoom scalable without changing which nodes exist or can appear as
        // the user pans back to them.
        guard
          paintBounds.intersects(
            CGRect(
              x: center.x - radius,
              y: center.y - radius,
              width: radius * 2,
              height: radius * 2
            ))
        else { continue }

        var pop = 0.0
        if let replayCursor, let timeline {
          pop = timeline.spawnProgress(nodeID: placement.id, at: replayCursor)
        }
        if pop > 0 {
          radius *= CGFloat(1 + 0.9 * pop)
          let bloom = radius * 2.6
          context.fill(
            Path(
              ellipseIn: CGRect(
                x: center.x - bloom / 2, y: center.y - bloom / 2, width: bloom, height: bloom
              )),
            with: .color(cluster.color.opacity(0.3 * pop))
          )
        }

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
      let anchor = plan.visibleNodes.first(where: { $0.id == anchorNodeID })
    {
      drawSpecialNode(
        anchor,
        radius: compact ? 6 : (isInspectMode ? 18 : (isFocusMode ? 12 : 7)),
        color: Ink.primary,
        opacity: selectedNodeID == nil || plan.relatedNodeIDs.contains(anchor.id) ? 0.86 : 0.16,
        context: &context,
        size: size
      )
    }

    if let selectedNode {
      drawSpecialNode(
        selectedNode,
        radius: compact ? 7 : (isInspectMode ? 26 : (isFocusMode ? 18 : 9)),
        color: selectedNode.cluster?.color ?? Ink.primary,
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

  private func drawCanvasLabels(
    context: inout GraphicsContext,
    size: CGSize,
    plan: MemoryAtlasRenderPlan,
    /// Entities standing on a named territory, whose name the caption is
    /// currently speaking for.
    quietened: Set<String>
  ) {
    guard plan.usesCanvasLabels else { return }

    // From the density-aware inspection threshold onward, every dot on this
    // canvas gets a label. Skip labels outside the clipped canvas before
    // resolving Text, which makes a 10k-node graph cost proportional to the
    // current viewport rather than the total graph size.
    let visibleBounds = CGRect(origin: .zero, size: size)
    for placement in plan.canvasLabelNodes where !quietened.contains(placement.id) {
      let center = point(for: placement.normalizedPosition, in: size)
      guard visibleBounds.contains(center) else { continue }

      let color = placement.cluster?.color ?? Ink.primary
      let rawLabel = placement.node.label.trimmingCharacters(in: .whitespacesAndNewlines)
      let displayLabel =
        rawLabel.count > 80
        ? String(rawLabel.prefix(79)).trimmingCharacters(in: .whitespacesAndNewlines) + "…"
        : rawLabel
      let estimatedLabelWidth = min(
        152.0,
        max(44.0, CGFloat(displayLabel.count) * 6.4 + 18)
      )
      let labelCenterX = min(
        max(center.x, estimatedLabelWidth / 2),
        size.width - estimatedLabelWidth / 2
      )
      let text = Text(displayLabel)
        .font(.system(size: 11, weight: placement.id == snapshot.anchorNodeID ? .semibold : .medium))
        .foregroundStyle(Ink.primary)
      let labelOffset: CGFloat =
        if placement.id == selectedNodeID {
          34
        } else if placement.id == snapshot.anchorNodeID {
          24
        } else {
          nodeRadius(for: placement) + 5
        }
      context.draw(text, at: CGPoint(x: labelCenterX, y: center.y + labelOffset), anchor: .top)

      // A small leading color marker keeps labels scannable while preserving
      // the neutral text treatment used elsewhere in the Atlas.
      context.fill(
        Path(ellipseIn: CGRect(x: center.x - 3, y: center.y + labelOffset + 4, width: 3, height: 3)),
        with: .color(color)
      )
    }
  }

  private var isSmallAtlas: Bool {
    !compact && snapshot.nodes.count <= MemoryAtlasZoomPolicy.smallAtlasCeiling
  }

  private func nodeRadius(for placement: MemoryAtlasNodePlacement) -> CGFloat {
    MemoryAtlasNodeVisualPolicy.radius(
      clusterRank: placement.clusterRank,
      zoom: zoom,
      compact: compact,
      isFullyLabelled: isFullyLabelledMode,
      isInspect: isInspectMode,
      isFocus: isFocusMode,
      isSmallAtlas: isSmallAtlas
    )
  }

  private func nodeLabel(
    _ placement: MemoryAtlasNodePlacement,
    selected: Bool
  ) -> some View {
    Text(placement.node.label)
      .scaledFont(
        size: compact ? 9.5 : (isInspectMode ? 14 : (isFocusMode ? 13 : 11)),
        weight: selected ? .semibold : .medium
      )
      .foregroundColor(Ink.primary)
      .lineLimit(1)
      .truncationMode(.tail)
      .multilineTextAlignment(.center)
      .fixedSize()
      .frame(maxWidth: compact ? 110 : 150)
      .allowsHitTesting(false)
  }

  private func nodeButton(
    _ placement: MemoryAtlasNodePlacement,
    size: CGSize,
    relatedNodeIDs: Set<String>,
    showLabel: Bool,
    labelAbove: Bool
  ) -> some View {
    let selected = selectedNodeID == placement.id
    let related = selectedNodeID == nil || relatedNodeIDs.contains(placement.id)
    let matches = matchingNodeIDs == nil || matchingNodeIDs?.contains(placement.id) == true
    let color = placement.cluster?.color ?? Ink.primary
    let diameter = nodeDiameter(placement, selected: selected)

    // Keeping the label out of the laid-out frame is what makes the ring land
    // on the node. A VStack of ring-over-label is centered by `.position`, so
    // the ring floats above the point while the Canvas paints the dot on it —
    // two marks per entity, visibly offset once dots are more than a few px.
    let hitDiameter = max(diameter, 24)

    return Button {
      if selected {
        clearSelection(resetCamera: true)
      } else {
        selectionTrail.removeAll()
        adoptSelection(placement.id)
      }
    } label: {
      ZStack {
        if selected {
          Circle()
            .stroke(color.opacity(0.22), lineWidth: 7)
            .frame(width: diameter + 14, height: diameter + 14)
        }
        Circle()
          .fill(Ink.rowFill)
          .overlay(Circle().stroke(color, lineWidth: selected ? 2.2 : 1.4))
          .frame(width: diameter, height: diameter)
        if placement.id == snapshot.anchorNodeID {
          Image(systemName: "person.fill")
            .scaledFont(size: max(9, diameter * 0.38))
            .foregroundColor(Ink.primary)
        }
      }
      .frame(width: hitDiameter, height: hitDiameter)
      // Both overlays hang the name outside the laid-out frame, so the frame
      // stays centered on the entity's own position. `.top`/`.bottom` anchor
      // the opposite edge of the text, which is what makes the same gap read
      // identically whether the name sits under the mark or over it.
      .overlay(alignment: .top) {
        if showLabel && !labelAbove {
          nodeLabel(placement, selected: selected)
            .offset(y: hitDiameter / 2 + diameter / 2 + 5)
        }
      }
      .overlay(alignment: .bottom) {
        if showLabel && labelAbove {
          nodeLabel(placement, selected: selected)
            .offset(y: -(hitDiameter / 2 + diameter / 2 + 5))
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

  /// `nil` collapses the header's back affordance; the ternary needs the
  /// explicit optional-closure type to stay unambiguous.
  private var backAction: (() -> Void)? {
    selectionTrail.isEmpty ? nil : { goBack() }
  }

  private func detailPanel(for placement: MemoryAtlasNodePlacement) -> some View {
    let relationships: [MemoryAtlasRelationshipRow] = selectedEdges.compactMap { edge in
      let otherID = edge.edge.sourceId == placement.id ? edge.edge.targetId : edge.edge.sourceId
      guard let other = snapshot.nodeByID[otherID] else { return nil }
      return MemoryAtlasRelationshipRow(
        id: edge.id,
        otherNodeID: otherID,
        otherLabel: other.node.label,
        relationship: MemoryAtlasLayoutEngine.combinedRelationshipDisplayName(edge.relationshipLabels),
        accent: other.cluster?.color ?? Ink.secondary
      )
    }

    return MemoryAtlasDetailPanel(
      subject: .entity(
        title: placement.node.label,
        typeName: placement.cluster?.title,
        connectionSummary: "\(placement.degree) connection\(placement.degree == 1 ? "" : "s")"
      ),
      accent: placement.cluster?.color ?? Ink.primary,
      related: relationships,
      evidence: evidence,
      evidenceIsLoading: evidenceIsLoading,
      unresolvedEvidenceCount: unresolvedEvidenceCount,
      onOpenRelated: openRelated,
      onOpenMemory: openCitedMemory,
      onBack: backAction,
      onFocus: { focus(on: placement) },
      onClose: { clearSelection(resetCamera: true) }
    )
  }

  /// Inspector for a single connection: which two entities it joins, and the
  /// memories that produced that specific claim rather than everything either
  /// endpoint happens to be involved in.
  private func relationshipPanel(
    for edge: MemoryAtlasEdgePlacement,
    anchor: MemoryAtlasNodePlacement
  ) -> some View {
    let source = snapshot.nodeByID[edge.edge.sourceId]
    let target = snapshot.nodeByID[edge.edge.targetId]
    let endpoints: [MemoryAtlasRelationshipRow] = [source, target].compactMap { endpoint in
      guard let endpoint else { return nil }
      return MemoryAtlasRelationshipRow(
        id: "endpoint-\(endpoint.id)",
        otherNodeID: endpoint.id,
        otherLabel: endpoint.node.label,
        relationship: endpoint.cluster?.title ?? "Entity",
        accent: endpoint.cluster?.color ?? Ink.secondary
      )
    }

    return MemoryAtlasDetailPanel(
      subject: .relationship(
        sourceLabel: source?.node.label ?? edge.edge.sourceId,
        targetLabel: target?.node.label ?? edge.edge.targetId,
        verb: MemoryAtlasLayoutEngine.combinedRelationshipDisplayName(edge.relationshipLabels)
      ),
      accent: edge.cluster.color,
      related: endpoints,
      evidence: evidence,
      evidenceIsLoading: evidenceIsLoading,
      unresolvedEvidenceCount: unresolvedEvidenceCount,
      onOpenRelated: openRelated,
      onOpenMemory: openCitedMemory,
      onBack: backAction,
      onFocus: { focus(on: anchor) },
      onClose: { clearSelection(resetCamera: true) }
    )
  }

  /// A cited memory is readable here, but acting on it — editing, checking its
  /// provenance, deleting it — belongs on the Memories page. Opening it there
  /// with its detail panel showing is the one hop that does not lose the thread.
  private func openCitedMemory(_ item: MemoryAtlasEvidence) {
    onOpenMemory?(item.id)
  }

  private func openRelated(_ row: MemoryAtlasRelationshipRow) {
    guard snapshot.nodeByID[row.otherNodeID] != nil else { return }
    if let current = selectedNodeID, current != row.otherNodeID {
      selectionTrail.append(current)
    }
    adoptSelection(row.otherNodeID)
  }

  private func goBack() {
    guard let previous = selectionTrail.popLast() else { return }
    adoptSelection(previous)
  }

  private func adoptSelection(_ nodeID: String, edgeID: String? = nil) {
    selectedEdgeID = edgeID
    selectedNodeID = nodeID
    if let placement = snapshot.nodeByID[nodeID] {
      focus(on: placement)
    }
  }

  private func clearSelection(resetCamera: Bool = false) {
    selectionTrail.removeAll()
    selectedEdgeID = nil
    selectedNodeID = nil
    if resetCamera { resetViewport(preservingNeighbourhood: true) }
  }

  private func selectionStrip(for placement: MemoryAtlasNodePlacement) -> some View {
    let primaryEdge = selectedEdges.first
    let sourceNode = primaryEdge.flatMap { snapshot.nodeByID[$0.edge.sourceId] }
    let targetNode = primaryEdge.flatMap { snapshot.nodeByID[$0.edge.targetId] }
    let evidenceIds = citedMemoryIDs
    let relationshipText: String = {
      guard let primaryEdge, let sourceNode, let targetNode else {
        return "\(placement.degree) connection\(placement.degree == 1 ? "" : "s")"
      }
      return
        "\(sourceNode.node.label) \(MemoryAtlasLayoutEngine.combinedRelationshipDisplayName(primaryEdge.relationshipLabels)) \(targetNode.node.label)"
    }()

    return HStack(spacing: 14) {
      Circle()
        .fill((placement.cluster?.color ?? Ink.primary).opacity(0.14))
        .overlay(Circle().stroke(placement.cluster?.color ?? Ink.primary, lineWidth: 1.5))
        .frame(width: 34, height: 34)

      VStack(alignment: .leading, spacing: 2) {
        Text(placement.node.label)
          .scaledFont(size: compact ? 12 : 14, weight: .semibold)
          .foregroundColor(Ink.primary)
        Text(relationshipText)
          .scaledFont(size: compact ? 10 : 12)
          .foregroundColor(Ink.secondary)
          .lineLimit(1)
      }

      Spacer()

      if !compact {
        Button {
          focus(on: placement)
        } label: {
          Label("Focus", systemImage: "scope")
            .scaledFont(size: 11, weight: .medium)
            .foregroundColor(Ink.secondary)
        }
        .buttonStyle(.plain)
        .accessibilityIdentifier("memory_atlas_focus_selection")
      }

      // Compact surfaces cannot fit the inspector, so the strip reports the
      // evidence count rather than offering a jump that would leave the map.
      Text(
        evidenceIds.isEmpty
          ? "Source details are still being linked"
          : "\(evidenceIds.count) source memor\(evidenceIds.count == 1 ? "y" : "ies")"
      )
      .scaledFont(size: 10)
      .foregroundColor(Ink.secondary)

      Button {
        clearSelection(resetCamera: true)
      } label: {
        Image(systemName: "xmark")
          .scaledFont(size: 10, weight: .semibold)
          .foregroundColor(Ink.secondary)
          .frame(width: 24, height: 24)
          .contentShape(Rectangle())
      }
      .buttonStyle(.plain)
      .help("Clear selection (Esc)")
      .accessibilityLabel("Clear selection")
      .accessibilityIdentifier("memory_atlas_clear_selection")
    }
    .padding(.horizontal, compact ? 12 : 18)
    .frame(height: compact ? 50 : 56)
    .background(Ink.rowFill)
    .overlay(alignment: .top) {
      Divider().overlay(Ink.separator.opacity(0.24))
    }
  }

  private var atlasLegend: some View {
    HStack(spacing: 18) {
      Text(atlasLevelLabel)
        .scaledFont(size: 11, weight: .medium)
        .foregroundColor(Ink.secondary)

      Spacer()
    }
    .padding(.horizontal, 18)
    .frame(height: 36)
    .background(Ink.rowFill)
  }

  // MARK: - Time axis

  /// Two tight rows: state on top, scrubber below. Everything here is
  /// secondary to the atlas itself, so the bar stays a footer and never takes
  /// canvas away from the graph.
  private var timelineBar: some View {
    VStack(spacing: 5) {
      HStack(spacing: 8) {
        Button(action: togglePlayback) {
          ZStack {
            Circle().fill(Ink.primary).frame(width: 22, height: 22)
            Image(systemName: isTimePlaying ? "pause.fill" : "play.fill")
              .scaledFont(size: 9, weight: .bold)
              .foregroundColor(Ink.surface)
              .offset(x: isTimePlaying ? 0 : 1)
          }
        }
        .buttonStyle(.plain)
        .help(isTimePlaying ? "Pause" : "Play your memory forward")
        .accessibilityLabel(isTimePlaying ? "Pause memory timeline" : "Play memory timeline")
        .accessibilityIdentifier("memory_atlas_timeline_play")

        Text(asOfLabel)
          .scaledFont(size: 11, weight: .semibold)
          .foregroundColor(Ink.primary)
          .lineLimit(1)

        Text(
          MemoryAtlasLayoutEngine.countLabel(
            entities: visibleEntityCount, connections: visibleConnectionCount)
        )
        .scaledFont(size: 10)
        .foregroundColor(Ink.secondary)
        .monospacedDigit()
        .lineLimit(1)

        Spacer(minLength: 8)

        Text(atlasLevelLabel)
          .scaledFont(size: 10, weight: .medium)
          .foregroundColor(Ink.secondary)
          .lineLimit(1)

        if timeCursor < 0.9995 {
          Button(action: jumpToNow) {
            Text("Now")
              .scaledFont(size: 10, weight: .semibold)
              .foregroundColor(Ink.secondary)
              .padding(.horizontal, 8)
              .frame(height: 18)
              .glassChip()
          }
          .buttonStyle(.plain)
          .accessibilityIdentifier("memory_atlas_timeline_now")
        }
      }

      // The range endpoints flank the scrubber instead of taking a third row.
      HStack(spacing: 8) {
        Text(shortDate(timeline?.start))
          .scaledFont(size: 9)
          .foregroundColor(Ink.secondary)
          .lineLimit(1)

        timelineTrack

        Text(timeline?.hasChronologicalRange == true ? "Now" : "Imported")
          .scaledFont(size: 9)
          .foregroundColor(Ink.secondary)
          .lineLimit(1)
      }
    }
    .padding(.horizontal, 18)
    .padding(.vertical, 8)
    .background(Ink.rowFill)
    .overlay(alignment: .top) {
      Divider().overlay(Ink.separator.opacity(0.24))
    }
    .accessibilityIdentifier("memory_atlas_timeline")
  }

  private var timelineTrack: some View {
    GeometryReader { geo in
      Canvas(opaque: false, colorMode: .linear) { context, size in
        drawTimeline(context: &context, size: size)
      }
      .contentShape(Rectangle())
      .gesture(
        DragGesture(minimumDistance: 0)
          .onChanged { value in scrub(to: value.location.x / max(geo.size.width, 1)) }
      )
    }
    .frame(height: 20)
    .accessibilityIdentifier("memory_atlas_timeline_track")
    .accessibilityElement()
    .accessibilityLabel("Memory timeline")
    .accessibilityValue(asOfLabel)
    .accessibilityHint("Adjust to replay the atlas over time")
    .accessibilityAdjustableAction { direction in
      let step = 0.05
      switch direction {
      case .increment:
        scrub(to: min(timeCursor + step, 1))
      case .decrement:
        scrub(to: max(timeCursor - step, 0))
      @unknown default:
        break
      }
    }
  }

  private func drawTimeline(context: inout GraphicsContext, size: CGSize) {
    guard let timeline else { return }
    let buckets = timeline.buckets
    let maxCount = CGFloat(max(buckets.max() ?? 1, 1))
    let barWidth = size.width / CGFloat(max(buckets.count, 1))
    let cursorX = CGFloat(timeCursor) * size.width
    let baseY = size.height - 6

    for (index, count) in buckets.enumerated() {
      let barHeight = CGFloat(count) / maxCount * (size.height - 12)
      let x = CGFloat(index) * barWidth
      let born = (x + barWidth / 2) <= cursorX
      let rect = CGRect(
        x: x + 1, y: baseY - barHeight, width: max(barWidth - 2, 1), height: max(barHeight, 0.5)
      )
      context.fill(
        Path(roundedRect: rect, cornerRadius: 1),
        with: .color(Ink.primary.opacity(born ? 0.3 : 0.08))
      )
    }

    var baseline = Path()
    baseline.move(to: CGPoint(x: 0, y: baseY))
    baseline.addLine(to: CGPoint(x: size.width, y: baseY))
    context.stroke(baseline, with: .color(Ink.separator.opacity(0.5)), lineWidth: 1)

    var filled = Path()
    filled.move(to: CGPoint(x: 0, y: baseY))
    filled.addLine(to: CGPoint(x: cursorX, y: baseY))
    context.stroke(filled, with: .color(Ink.primary.opacity(0.85)), lineWidth: 1.5)

    var playhead = Path()
    playhead.move(to: CGPoint(x: cursorX, y: 0))
    playhead.addLine(to: CGPoint(x: cursorX, y: size.height))
    context.stroke(playhead, with: .color(Ink.primary.opacity(0.85)), lineWidth: 1.5)

    context.fill(
      Path(ellipseIn: CGRect(x: cursorX - 5, y: baseY - 5, width: 10, height: 10)),
      with: .color(Ink.primary)
    )
  }

  private var asOfLabel: String {
    guard let asOf = asOfDate else { return "Now — the whole map" }
    guard MemoryAtlasPlayback.isCredible(asOf) else { return "Import replay" }
    let formatter = DateFormatter()
    formatter.dateStyle = .medium
    formatter.timeStyle = .none
    if timeline?.hasChronologicalRange == false {
      return "Import replay · \(formatter.string(from: asOf))"
    }
    return "Replay · \(formatter.string(from: asOf))"
  }

  private func shortDate(_ date: Date?) -> String {
    guard let date, MemoryAtlasPlayback.isCredible(date) else { return "" }
    let formatter = DateFormatter()
    formatter.dateFormat = "MMM d, yyyy"
    return formatter.string(from: date)
  }

  private func maybeAutoplayTimeline() {
    guard previewTimeCursor == nil else { return }
    guard !compact, timeline != nil, autoplayEnabled, !didAutoplay, !reduceMotion else { return }
    didAutoplay = true
    startPlayback(resetToStart: true)
  }

  private func togglePlayback() {
    if isTimePlaying {
      stopPlayback(userInitiated: true)
    } else {
      startPlayback(resetToStart: timeCursor >= 0.9995)
    }
  }

  private func startPlayback(resetToStart: Bool) {
    guard timeline != nil else { return }
    playbackTask?.cancel()
    if resetToStart || timeCursor >= 0.9995 {
      timeCursor = 0
      clearSelectionIfHiddenAtCurrentTime()
    }
    isTimePlaying = true
    // Suppress the interactive overlay + floating titles for a clean, smooth
    // growth animation; restored the moment playback ends.
    isCameraMoving = true
    playbackTask = Task { @MainActor in
      var last = Date()
      let totalSeconds = MemoryAtlasPlayback.duration(entityCount: snapshot.nodes.count)
      while !Task.isCancelled {
        try? await Task.sleep(nanoseconds: 33_000_000)
        if Task.isCancelled { return }
        let now = Date()
        let delta = now.timeIntervalSince(last)
        last = now
        let next = timeCursor + delta / totalSeconds
        if next >= 1 {
          timeCursor = 1
          finishPlaybackNaturally()
          return
        }
        timeCursor = next
      }
    }
  }

  /// Playing to the end is not an opt-out — the delightful default survives.
  private func finishPlaybackNaturally() {
    playbackTask = nil
    isTimePlaying = false
    isCameraMoving = false
  }

  private func stopPlayback(userInitiated: Bool) {
    playbackTask?.cancel()
    playbackTask = nil
    if isTimePlaying { isCameraMoving = false }
    isTimePlaying = false
    if userInitiated { autoplayEnabled = false }
  }

  private func scrub(to fraction: Double) {
    if isTimePlaying || playbackTask != nil {
      stopPlayback(userInitiated: true)
    } else {
      // Grabbing the timeline is an explicit opt-out of auto-play on open.
      autoplayEnabled = false
    }
    timeCursor = min(max(fraction, 0), 1)
    clearSelectionIfHiddenAtCurrentTime()
  }

  private func jumpToNow() {
    stopPlayback(userInitiated: true)
    withAnimation(.easeOut(duration: 0.25)) { timeCursor = 1 }
  }

  private var zoomControls: some View {
    HStack(spacing: 1) {
      Button {
        zoomOut()
      } label: {
        Image(systemName: "minus").frame(width: 28, height: 28)
      }
      .accessibilityIdentifier("memory_atlas_zoom_out")
      .accessibilityLabel("Zoom out")
      Button {
        resetViewport()
      } label: {
        Text("\(Int(zoom * 100))%")
          .scaledFont(size: 9, weight: .medium)
          .frame(width: 40, height: 28)
      }
      .help("Return to overview")
      .accessibilityIdentifier("memory_atlas_reset_viewport")
      .accessibilityLabel("Reset Brain Map viewport")
      .accessibilityValue("\(Int(zoom * 100)) percent")
      Button {
        zoomIn()
      } label: {
        Image(systemName: "plus").frame(width: 28, height: 28)
      }
      .disabled(zoom >= maximumZoom)
      .help(compact ? "Open the Brain Map for deeper exploration" : "Zoom in (accelerates for large maps)")
      .accessibilityIdentifier("memory_atlas_zoom_in")
      .accessibilityLabel("Zoom in")
    }
    .scaledFont(size: 10)
    .foregroundColor(Ink.secondary)
    .glassChip()
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

  private func scrollZoom(by delta: CGFloat, anchoredAt pointer: CGPoint, in size: CGSize) {
    guard delta != 0, size.width > 0, size.height > 0 else { return }
    let nextZoom = min(
      max(zoom * CGFloat(exp(Double(delta))), MemoryAtlasZoomPolicy.minimumZoom),
      maximumZoom
    )
    guard nextZoom != zoom else { return }

    let ratio = nextZoom / zoom
    pan = CGSize(
      width: (1 - ratio) * (pointer.x - size.width / 2) + ratio * pan.width,
      height: (1 - ratio) * (pointer.y - size.height / 2) + ratio * pan.height
    )
    zoom = nextZoom
    settledZoom = nextZoom
    settledPan = pan
  }

  private var maximumZoom: CGFloat {
    MemoryAtlasZoomPolicy.maximumZoom(nodeCount: snapshot.nodes.count, compact: compact)
  }

  private var isFullyLabelledMode: Bool {
    !compact && zoom >= maximumZoom
  }

  private var isFocusMode: Bool {
    !compact && zoom >= MemoryAtlasZoomPolicy.focusModeZoom
  }

  private var isInspectMode: Bool {
    !compact && zoom >= MemoryAtlasZoomPolicy.inspectModeZoom
  }

  private var atlasLevelLabel: String {
    if isFullyLabelledMode { return "All labelled" }
    if isInspectMode { return "Inspect" }
    if isFocusMode { return "Focus" }
    if zoom < MemoryAtlasZoomPolicy.neighborhoodZoom { return "Overview" }
    if zoom < 1.9 { return "Neighborhood" }
    return "Detail"
  }

  private func point(for normalized: CGPoint, in size: CGSize) -> CGPoint {
    MemoryAtlasRenderPlanner.renderedPoint(
      for: normalized, viewportSize: size, zoom: zoom, pan: pan)
  }

  private func canvasPaintBounds(for size: CGSize) -> CGRect {
    CGRect(x: -28, y: -28, width: size.width + 56, height: size.height + 56)
  }

  private func nodeDiameter(_ placement: MemoryAtlasNodePlacement, selected: Bool) -> CGFloat {
    if isInspectMode {
      if selected { return 64 }
      if placement.id == snapshot.anchorNodeID { return 50 }
      if placement.isCatalog { return 34 }
      if placement.clusterRank == 0 { return 42 }
      return 34
    }
    if selected { return compact ? 28 : (isFocusMode ? 50 : 34) }
    if placement.id == snapshot.anchorNodeID { return compact ? 24 : (isFocusMode ? 38 : 29) }
    if placement.isCatalog { return compact ? 10 : (isFocusMode ? 22 : 13) }
    if placement.clusterRank == 0 { return compact ? 19 : (isFocusMode ? 32 : 23) }
    return compact ? 10 : (isFocusMode ? 22 : 13)
  }

  private func nodeMatchesSearch(_ node: KnowledgeGraphNode) -> Bool {
    guard !searchText.isEmpty else { return true }
    return node.label.localizedCaseInsensitiveContains(searchText)
      || node.aliases.contains { $0.localizedCaseInsensitiveContains(searchText) }
  }

  /// The replay filters membership by its density-aware axis. Hit testing and
  /// keyboard search use the same predicate so a future entity cannot be
  /// selected while it is still absent from the canvas.
  private func nodeIsVisibleAtCurrentTime(_ placement: MemoryAtlasNodePlacement) -> Bool {
    guard let timeline, timeCursor < 0.9995 else { return true }
    return placement.id == snapshot.anchorNodeID || timeline.isVisible(nodeID: placement.id, at: timeCursor)
  }

  private func clearSelectionIfHiddenAtCurrentTime() {
    guard let selectedNodeID, let placement = snapshot.nodeByID[selectedNodeID], !nodeIsVisibleAtCurrentTime(placement)
    else {
      return
    }
    clearSelection()
  }

  private func updateSearchMatches(_ query: String) {
    guard !query.isEmpty else {
      matchingNodeIDs = nil
      matchingEdges = nil
      return
    }
    let matches = Set(
      snapshot.nodes.lazy.filter { placement in
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
    guard
      let nodeID = snapshot.nodes.first(where: {
        matchingNodeIDs.contains($0.id) && nodeIsVisibleAtCurrentTime($0)
      })?.id
    else { return }
    selectionTrail.removeAll()
    adoptSelection(nodeID)
  }

  /// Routes a click on the canvas to whatever it landed on.
  ///
  /// Entities are tested first and win outright: every dot sits on at least one
  /// line, so letting a line take the hit near a dot would make dots feel
  /// unclickable at the exact places they matter most.
  private func selectAtlasElement(at location: CGPoint, in size: CGSize, plan: MemoryAtlasRenderPlan) {
    if let node = nearestNode(to: location, in: size, visibleNodes: plan.visibleNodes) {
      // Reaching for something on the canvas starts a fresh trail; only
      // following a listed connection extends one.
      selectionTrail.removeAll()
      adoptSelection(node.id)
      return
    }

    let segments = plan.visibleEdges.map {
      MemoryAtlasHitTesting.Segment(
        id: $0.id,
        start: point(for: $0.source, in: size),
        end: point(for: $0.target, in: size)
      )
    }
    guard
      let hitID = MemoryAtlasHitTesting.nearestSegment(
        to: location,
        among: segments,
        within: MemoryAtlasHitTesting.connectionTolerance
      ),
      let hit = plan.visibleEdges.first(where: { $0.id == hitID }),
      // The inspector anchors to an endpoint for map emphasis, so a connection
      // whose endpoint is not in the snapshot cannot be presented.
      snapshot.nodeByID[hit.edge.sourceId] != nil
    else { return }
    selectionTrail.removeAll()
    adoptSelection(hit.edge.sourceId, edgeID: hit.id)
  }

  private func nearestNode(to location: CGPoint, in size: CGSize, visibleNodes: [MemoryAtlasNodePlacement] = [])
    -> MemoryAtlasNodePlacement?
  {
    let hitRadius = max(12, 18 / zoom)
    var nearest: (placement: MemoryAtlasNodePlacement, distance: CGFloat)?
    // Hit-test only nodes in the current render plan. On graphs larger than
    // the current detail-level node budget, the canvas paints only visible
    // nodes, but searching every node in the snapshot would let a tap on an
    // apparently blank area select an omitted node and open its inspector.
    let visibleIDs = visibleNodes.isEmpty ? nil : Set(visibleNodes.map { $0.id })
    for placement in snapshot.nodes where nodeIsVisibleAtCurrentTime(placement) {
      if let visibleIDs, !visibleIDs.contains(placement.id) { continue }
      let rendered = point(for: placement.normalizedPosition, in: size)
      let distance = hypot(rendered.x - location.x, rendered.y - location.y)
      if distance <= hitRadius && (nearest.map { distance < $0.distance } ?? true) {
        nearest = (placement, distance)
      }
    }
    return nearest?.placement
  }

  private func updateZoom(_ value: CGFloat) {
    let nextZoom = min(max(value, MemoryAtlasZoomPolicy.minimumZoom), maximumZoom)
    // Buttons, automation, and selection focus zoom around the atlas center.
    // Scaling pan by the same ratio keeps a focused entity in place instead of
    // throwing it off-screen as deep zoom increases.
    pan = MemoryAtlasZoomPolicy.panPreservingCenterZoom(
      pan,
      from: zoom,
      to: nextZoom
    )
    settledPan = pan
    zoom = nextZoom
    settledZoom = nextZoom
  }

  private func zoomIn() {
    let increment = max(0.2, zoom * 0.25)
    updateZoom(min(zoom + increment, maximumZoom))
  }

  private func zoomOut() {
    guard zoom > MemoryAtlasZoomPolicy.minimumZoom else { return }
    let decrementedZoom = zoom > 2 ? zoom / 1.25 : zoom - 0.2
    updateZoom(max(decrementedZoom, MemoryAtlasZoomPolicy.minimumZoom))
  }

  private func focus(on placement: MemoryAtlasNodePlacement) {
    guard viewportSize.width > 0, viewportSize.height > 0 else { return }
    var positions = [placement.normalizedPosition]
    if let neighborIDs = snapshot.neighborIDsByNodeID[placement.id] {
      for neighborID in neighborIDs {
        if let neighbor = snapshot.nodeByID[neighborID] {
          positions.append(neighbor.normalizedPosition)
        }
      }
    }
    let camera = MemoryAtlasZoomPolicy.focusedNeighborhood(
      positions: positions,
      viewport: viewportSize,
      currentZoom: zoom,
      zoomRange: MemoryAtlasZoomPolicy.minimumZoom...maximumZoom
    )
    withAnimation(.easeOut(duration: 0.22)) {
      zoom = camera.zoom
      settledZoom = camera.zoom
      pan = camera.pan
      settledPan = camera.pan
    }
  }

  private func resetViewport(preservingNeighbourhood: Bool = false) {
    if preservingNeighbourhood, enteredRegionID != nil {
      departureZoom = MemoryAtlasNeighbourhoodLabels.overviewDepartureZoom(
        neighbourhoodZoom: MemoryAtlasZoomPolicy.neighborhoodZoom,
        minimumZoom: MemoryAtlasZoomPolicy.minimumZoom)
    }
    withAnimation(.easeOut(duration: 0.2)) {
      zoom = 1
      settledZoom = 1
      pan = .zero
      settledPan = .zero
    }
  }

  /// Undo the innermost thing the user has done, and say whether there was
  /// one. A press the map has no use for is handed back so the page around it
  /// can take the user out of the map.
  private func dismissTopmostState() -> Bool {
    switch MemoryAtlasDismissal.next(
      isSearching: searchIsFocused || !searchText.isEmpty,
      hasSelection: selectedNodeID != nil || selectedEdgeID != nil,
      hasTrail: !selectionTrail.isEmpty,
      isInsideNeighbourhood: enteredRegionID != nil)
    {
    case .search:
      searchIsFocused = false
      searchText = ""
      matchingNodeIDs = nil
      matchingEdges = nil
    case .selectionStep:
      goBack()
    case .selection:
      clearSelection(resetCamera: true)
    case .neighbourhood:
      leaveNeighbourhood()
    case .passThrough:
      // The last layer is the map itself. Handing the key back to the window
      // instead was the tidy-looking version and it did nothing: the atlas is
      // a canvas, so there is no focused control for a cancel to travel up
      // from, and Escape on a page with nothing selected was simply swallowed.
      guard let onLeave else { return false }
      onLeave()
    }
    return true
  }
}

/// SwiftUI has no view-local scroll-wheel gesture on the macOS 14 deployment
/// floor. This passive bridge observes the Atlas viewport without entering the
/// hit-test chain, so normal dragging, tapping, and control interaction remain
/// owned by SwiftUI.
private struct MemoryAtlasInputMonitor: NSViewRepresentable {
  let onScroll: (CGFloat, CGPoint) -> Void
  let onFocusSearch: () -> Void

  func makeCoordinator() -> Coordinator {
    Coordinator(onScroll: onScroll, onFocusSearch: onFocusSearch)
  }

  func makeNSView(context: Context) -> PassiveEventView {
    let view = PassiveEventView()
    let coordinator = context.coordinator
    view.geometryDidChange = { [weak coordinator] windowNumber, frameInWindow in
      coordinator?.windowNumber = windowNumber
      coordinator?.frameInWindow = frameInWindow
    }
    context.coordinator.installMonitor()
    return view
  }

  func updateNSView(_ nsView: PassiveEventView, context: Context) {
    context.coordinator.onScroll = onScroll
    context.coordinator.onFocusSearch = onFocusSearch
  }

  static func dismantleNSView(_ nsView: PassiveEventView, coordinator: Coordinator) {
    nsView.geometryDidChange = nil
    coordinator.removeMonitor()
  }

  final class PassiveEventView: NSView {
    var geometryDidChange: ((Int?, CGRect) -> Void)?

    override var isFlipped: Bool { true }
    override func hitTest(_ point: NSPoint) -> NSView? { nil }

    override func viewDidMoveToWindow() {
      super.viewDidMoveToWindow()
      publishGeometry()
    }

    override func layout() {
      super.layout()
      publishGeometry()
    }

    private func publishGeometry() {
      guard let window else {
        geometryDidChange?(nil, .zero)
        return
      }
      geometryDidChange?(window.windowNumber, convert(bounds, to: nil))
    }
  }

  final class Coordinator {
    var onScroll: (CGFloat, CGPoint) -> Void
    var onFocusSearch: () -> Void
    fileprivate var windowNumber: Int?
    fileprivate var frameInWindow: CGRect = .zero
    private var eventMonitor: Any?

    init(
      onScroll: @escaping (CGFloat, CGPoint) -> Void,
      onFocusSearch: @escaping () -> Void
    ) {
      self.onScroll = onScroll
      self.onFocusSearch = onFocusSearch
    }

    func installMonitor() {
      eventMonitor = NSEvent.addLocalMonitorForEvents(matching: [.scrollWheel, .keyDown]) {
        [weak self] event in
        guard let self, event.windowNumber == self.windowNumber else {
          return event
        }

        if event.type == .keyDown,
          event.modifierFlags.contains(.command),
          event.charactersIgnoringModifiers?.lowercased() == "f"
        {
          self.onFocusSearch()
          return nil
        }

        guard event.type == .scrollWheel else { return event }
        let frameInWindow = self.frameInWindow
        guard frameInWindow.contains(event.locationInWindow) else { return event }
        guard abs(event.scrollingDeltaY) > abs(event.scrollingDeltaX) else { return event }

        let sensitivity: CGFloat = event.hasPreciseScrollingDeltas ? 0.012 : 0.12
        let scaledDelta = min(max(event.scrollingDeltaY * sensitivity, -0.18), 0.18)
        let location = CGPoint(
          x: event.locationInWindow.x - frameInWindow.minX,
          y: frameInWindow.maxY - event.locationInWindow.y
        )
        self.onScroll(scaledDelta, location)
        return nil
      }
    }

    func removeMonitor() {
      guard let eventMonitor else { return }
      NSEvent.removeMonitor(eventMonitor)
      self.eventMonitor = nil
    }

    deinit {
      removeMonitor()
    }
  }
}

// MARK: - Export / QA preview

/// Deterministic, data-backed atlas for offscreen `ViewExporter` renders. The
/// live atlas needs a signed-in account and a server graph, so QA has no way to
/// visually regression-test the timeline without this fixed sample. Same file as
/// the private surface so it can construct it directly.
@MainActor
enum MemoryAtlasExportPreview {
  static func surface(timeCursor: Double = 0.55) -> AnyView {
    AnyView(
      CanonicalMemoryAtlasSurface(
        graph: sampleGraph(),
        compact: false,
        evidenceProvider: { _ in [] },
        previewTimeCursor: timeCursor
      )
    )
  }

  private static func sampleGraph() -> KnowledgeGraphResponse {
    let now = Date(timeIntervalSince1970: 1_752_000_000)
    let span: TimeInterval = 120 * 24 * 60 * 60
    var seed: UInt64 = 0x9e37_79b9_7f4a_7c15
    func rand() -> Double {
      seed ^= seed << 13
      seed ^= seed >> 7
      seed ^= seed << 17
      return Double(seed % 10_000) / 10_000
    }

    let clusters: [(KnowledgeGraphNodeType, [String], Int)] = [
      (.person, ["Sarah", "Alex", "Priya", "Marcus", "Elena", "Mom"], 34),
      (.organization, ["Google Cloud", "Omi", "Stripe", "Anthropic", "Notion"], 26),
      (.place, ["New York City", "San Francisco", "Tokyo", "Blue Bottle"], 22),
      (.thing, ["Telegram", "MacBook", "iPhone", "Tesla", "AirPods"], 40),
      (.concept, ["burnout", "sleep", "running", "design", "focus", "pricing"], 48),
    ]

    var nodes: [KnowledgeGraphNode] = [
      KnowledgeGraphNode(
        id: "david", label: "David", nodeType: .person, memoryIds: ["m0"],
        createdAt: now.addingTimeInterval(-span)
      ),
      // A generic self node so the render exercises the center-collapse too.
      KnowledgeGraphNode(
        id: "user", label: "User", nodeType: .person,
        createdAt: now.addingTimeInterval(-span * 0.9)
      ),
    ]
    var edges: [KnowledgeGraphEdge] = []

    for (type, names, count) in clusters {
      for index in 0..<count {
        let id = "\(type.rawValue)-\(index)"
        let name = index < names.count ? names[index] : "\(names[index % names.count]) \(index)"
        let created = now.addingTimeInterval(-span * (1 - rand()))
        nodes.append(
          KnowledgeGraphNode(
            id: id, label: name, nodeType: type, memoryIds: ["mem-\(id)"], createdAt: created
          )
        )
        if index < 3 {
          edges.append(
            KnowledgeGraphEdge(
              id: "edge-\(id)",
              sourceId: index == 0 ? "user" : "david",
              targetId: id,
              label: "knows",
              memoryIds: ["mem-\(id)"],
              createdAt: created
            )
          )
        }
      }
    }

    return KnowledgeGraphResponse(nodes: nodes, edges: edges)
  }

  /// A one-type atlas — the shape a narrow or young account actually has, and
  /// the case that regressed into a small knot in the upper middle of an
  /// otherwise empty canvas. Kept as its own export so that layout stays
  /// reviewable without an account that happens to have only one entity type.
  static func singleTypeSurface(timeCursor: Double = 1) -> AnyView {
    AnyView(
      CanonicalMemoryAtlasSurface(
        graph: singleTypeGraph(),
        compact: false,
        evidenceProvider: { _ in [] },
        onRebuild: {},
        previewTimeCursor: timeCursor
      )
    )
  }

  /// Same sparse atlas with an entity selected, so the inspector's real
  /// layout (connections, evidence, and the map narrowing beside it) is
  /// captured rather than described.
  static func inspectorSurface() -> AnyView {
    AnyView(
      CanonicalMemoryAtlasSurface(
        graph: singleTypeGraph(),
        compact: false,
        onRebuild: {},
        previewTimeCursor: 1,
        previewSelectedNodeID: "concept-2",
        previewEvidence: Self.sampleEvidence.enumerated().map { index, content in
          MemoryAtlasEvidence(
            id: "evidence-\(index)",
            content: content,
            createdAt: Date(timeIntervalSince1970: 1_752_000_000 - Double(index) * 86_400)
          )
        }
      )
    )
  }

  /// Same atlas with a connection selected rather than an entity. Connections
  /// are clickable, so the relationship inspector is a real destination and
  /// gets a real render.
  static func connectionInspectorSurface() -> AnyView {
    AnyView(
      CanonicalMemoryAtlasSurface(
        graph: singleTypeGraph(),
        compact: false,
        onRebuild: {},
        previewTimeCursor: 1,
        previewSelectedNodeID: "david",
        previewSelectedEdgeID: "edge-concept-2",
        previewEvidence: Self.sampleEvidence.prefix(2).enumerated().map { index, content in
          MemoryAtlasEvidence(
            id: "evidence-\(index)",
            content: content,
            createdAt: Date(timeIntervalSince1970: 1_752_000_000 - Double(index) * 86_400)
          )
        }
      )
    )
  }

  private static let sampleEvidence = [
    "David runs hermes-m4 as the default agent for Multica work and prefers it over other Codex agents unless told otherwise.",
    "Debug symbol uploads to Sentry need SENTRY_AUTH_TOKEN present in the release lane, or the upload silently no-ops.",
    "Long-running agent tasks should run under tmux or screen so closing the terminal session does not kill them.",
  ]

  private static func singleTypeGraph() -> KnowledgeGraphResponse {
    let now = Date(timeIntervalSince1970: 1_752_000_000)
    let span: TimeInterval = 120 * 24 * 60 * 60
    let labels = [
      "portable mechanics", "SENTRY_AUTH_TOKEN", "hermes-m4", "debug symbol upload",
      "long-running tasks", "incident or trace", "production deploy", "403 error",
      "GitHub Discussion", "Discord Issues", "canonical pull request", "Skill Hub",
      "autonomy", "private fork bin", "break-glass hatch", "tmux", "screen",
      "deliverable", "GitHub issue", "release pointer", "worktree", "merge queue",
      "failure class", "ratchet baseline", "changelog fragment",
    ]

    var nodes: [KnowledgeGraphNode] = [
      KnowledgeGraphNode(
        id: "david", label: "David", nodeType: .person, memoryIds: ["m0"],
        createdAt: now.addingTimeInterval(-span)
      )
    ]
    var edges: [KnowledgeGraphEdge] = []

    for (index, label) in labels.enumerated() {
      let id = "concept-\(index)"
      let created = now.addingTimeInterval(-span * (1 - Double(index) / Double(labels.count)))
      nodes.append(
        KnowledgeGraphNode(
          id: id, label: label, nodeType: .concept, memoryIds: ["mem-\(id)"], createdAt: created
        )
      )
      edges.append(
        KnowledgeGraphEdge(
          id: "edge-\(id)", sourceId: "david", targetId: id, label: "relates_to",
          memoryIds: ["mem-\(id)"], createdAt: created
        )
      )
    }

    return KnowledgeGraphResponse(nodes: nodes, edges: edges)
  }
}
