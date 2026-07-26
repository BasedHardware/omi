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
    case .person: return Color(red: 0.31, green: 0.77, blue: 0.96)
    case .organization: return Color(red: 0.96, green: 0.66, blue: 0.22)
    case .place: return Color(red: 0.33, green: 0.84, blue: 0.67)
    case .thing: return OmiColors.textSecondary
    case .concept: return Color(red: 0.27, green: 0.63, blue: 0.96)
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

/// The time axis behind the atlas. Built from entity `createdAt` timestamps so
/// the user can scrub — or watch — their memory come into being. Playback is
/// density-aware: a tight imported/backfilled cluster is expanded into a short,
/// deterministic sequence instead of appearing as one unreadable burst. Dates
/// shown to the user always remain the original dates from memory data.
struct MemoryAtlasTimeline: Equatable {
  struct Entry: Equatable {
    let nodeID: String
    let createdAt: Date
    let playbackFraction: Double
  }

  let start: Date
  let end: Date
  /// Entity-birth counts across the density-expanded playback axis, for the
  /// histogram. This describes animation pacing, not rewritten history.
  let buckets: [Int]
  let entries: [Entry]
  let playbackFractionByNodeID: [String: Double]

  var hasChronologicalRange: Bool { end > start }
  var span: TimeInterval { max(end.timeIntervalSince(start), 1) }

  func date(atFraction fraction: Double) -> Date {
    let clamped = min(max(fraction, 0), 1)
    guard let first = entries.first else {
      return start.addingTimeInterval(span * clamped)
    }
    guard clamped > first.playbackFraction else { return first.createdAt }
    // This deliberately steps to the last real creation date rather than
    // interpolating an invented timestamp between two memories.
    return entries[max(firstPlaybackIndex(after: clamped) - 1, 0)].createdAt
  }

  func fraction(for date: Date) -> Double {
    guard let first = entries.first, let last = entries.last else { return 1 }
    guard date > first.createdAt else { return first.playbackFraction }
    guard date < last.createdAt else { return last.playbackFraction }
    return entries[max(firstDateIndex(after: date) - 1, 0)].playbackFraction
  }

  func isVisible(nodeID: String, at fraction: Double) -> Bool {
    (playbackFractionByNodeID[nodeID] ?? 1) <= min(max(fraction, 0), 1)
  }

  func visibleNodeCount(at fraction: Double) -> Int {
    let clamped = min(max(fraction, 0), 1)
    return firstPlaybackIndex(after: clamped)
  }

  func spawnProgress(nodeID: String, at fraction: Double) -> Double {
    guard let bornAt = playbackFractionByNodeID[nodeID] else { return 0 }
    let age = fraction - bornAt
    let window = max(0.012, min(0.05, 5 / Double(max(entries.count, 1))))
    guard age >= 0, age < window else { return 0 }
    return 1 - age / window
  }

  /// Retained for the legacy Date-based preview path. Live replay uses
  /// `spawnProgress(nodeID:at:)` so dense imports bloom one-at-a-time.
  var spawnWindow: TimeInterval { span / 26 }

  private func firstPlaybackIndex(after fraction: Double) -> Int {
    var lower = 0
    var upper = entries.count
    while lower < upper {
      let middle = lower + (upper - lower) / 2
      if entries[middle].playbackFraction > fraction {
        upper = middle
      } else {
        lower = middle + 1
      }
    }
    return lower
  }

  private func firstDateIndex(after date: Date) -> Int {
    var lower = 0
    var upper = entries.count
    while lower < upper {
      let middle = lower + (upper - lower) / 2
      if entries[middle].createdAt > date {
        upper = middle
      } else {
        lower = middle + 1
      }
    }
    return lower
  }

  static func make(from nodes: [KnowledgeGraphNode], bucketCount: Int = 40) -> MemoryAtlasTimeline? {
    let orderedNodes = nodes.sorted {
      if $0.createdAt == $1.createdAt { return $0.id < $1.id }
      return $0.createdAt < $1.createdAt
    }
    guard orderedNodes.count > 1, let start = orderedNodes.first?.createdAt, let end = orderedNodes.last?.createdAt
    else {
      return nil
    }

    let hasChronologicalRange = end > start
    let chronologicalSpan = max(end.timeIntervalSince(start), 1)
    // Chronology remains the majority signal for naturally distributed
    // memories, while rank gives dense imports enough playback room to be
    // comprehensible. Both inputs are monotonic, so this cannot reorder data
    // or fabricate a date.
    let chronologicalWeight = hasChronologicalRange ? 0.32 : 0
    let densityWeight = 1 - chronologicalWeight
    let denominator = Double(max(orderedNodes.count - 1, 1))
    let entries = orderedNodes.enumerated().map { index, node in
      let chronologicalFraction =
        hasChronologicalRange
        ? node.createdAt.timeIntervalSince(start) / chronologicalSpan
        : 0
      let densityFraction = Double(index) / denominator
      return Entry(
        nodeID: node.id,
        createdAt: node.createdAt,
        playbackFraction: chronologicalWeight * chronologicalFraction + densityWeight * densityFraction
      )
    }

    var buckets = Array(repeating: 0, count: max(bucketCount, 1))
    for entry in entries {
      let index = min(
        buckets.count - 1,
        max(0, Int(entry.playbackFraction * Double(buckets.count)))
      )
      buckets[index] += 1
    }
    return MemoryAtlasTimeline(
      start: start,
      end: end,
      buckets: buckets,
      entries: entries,
      playbackFractionByNodeID: Dictionary(lastWriteWins: entries.map { ($0.nodeID, $0.playbackFraction) })
    )
  }
}

struct MemoryAtlasNodePlacement: Identifiable {
  let node: KnowledgeGraphNode
  let cluster: MemoryAtlasCluster?
  let normalizedPosition: CGPoint
  let degree: Int
  let clusterRank: Int

  var id: String { node.id }
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

  var id: String { edge.id }
}

struct MemoryAtlasSnapshot {
  let nodes: [MemoryAtlasNodePlacement]
  let edges: [MemoryAtlasEdgePlacement]
  let anchorNodeID: String?
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
    clusterCenters: [MemoryAtlasCluster: CGPoint]
  ) {
    self.nodes = nodes
    self.edges = edges
    self.anchorNodeID = anchorNodeID
    self.activeClusters = MemoryAtlasCluster.allCases.filter { clusterCenters[$0] != nil }
    self.clusterCenters = clusterCenters
    self.timeline = MemoryAtlasTimeline.make(from: nodes.map(\.node))
    let indexedNodes = Dictionary(lastWriteWins: nodes.map { ($0.id, $0) })
    nodeByID = indexedNodes

    let sortedEdges = edges.sorted { lhs, rhs in
      let lhsRank = MemoryAtlasSnapshot.edgeRank(lhs, nodes: indexedNodes)
      let rhsRank = MemoryAtlasSnapshot.edgeRank(rhs, nodes: indexedNodes)
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
}

enum MemoryAtlasDetailLevel: Equatable {
  case overview
  case neighborhood
  case detail
  case focus
  case inspect
}

enum MemoryAtlasZoomPolicy {
  /// At or below this entity count the whole atlas fits on one screen, so the
  /// density budgets tuned for thousands of entities stop being a kindness and
  /// start being the reason the page looks empty.
  static let smallAtlasCeiling = 60
  static let minimumZoom: CGFloat = 0.75
  static let compactMaximumZoom: CGFloat = 1.35
  static let focusModeZoom: CGFloat = 3.2
  static let inspectModeZoom: CGFloat = 7.5
  static let focusTargetZoom: CGFloat = 4

  /// The final inspection level needs enough screen-space for every entity to
  /// have a readable label. A square-root curve tracks the area required by a
  /// larger graph: four times as many entities need roughly twice the zoom.
  /// This intentionally has no arbitrary product ceiling, so a growing memory
  /// graph always has a reachable all-labelled state.
  static func fullyLabelledZoom(nodeCount: Int) -> CGFloat {
    // Labels need substantially more room than dots. The 3.6x factor comes
    // from the label footprint rather than node radius, then rounds to a
    // usable 500% increment for the zoom control. This yields 16,000% for
    // the sampled ~1,946-entity graph, leaving dense constellations legible.
    let densityScaledZoom = ceil(sqrt(CGFloat(max(nodeCount, 1))) * 3.6 / 5) * 5
    return max(16, densityScaledZoom)
  }

  /// Begins Canvas-based labels before the final all-labelled state. This uses
  /// the same density curve as the maximum zoom, so a larger memory graph
  /// earns more room before every visible dot is named. At this level Canvas
  /// draws labels only for nodes inside the current viewport; it never creates
  /// a SwiftUI label view per entity.
  static func automaticCanvasLabelZoom(nodeCount: Int) -> CGFloat {
    let threshold = fullyLabelledZoom(nodeCount: nodeCount) * 0.25
    return max(inspectModeZoom, ceil(threshold * 2) / 2)
  }

  static func maximumZoom(nodeCount: Int, compact: Bool) -> CGFloat {
    compact ? compactMaximumZoom : fullyLabelledZoom(nodeCount: nodeCount)
  }

  static func focusedZoom(currentZoom: CGFloat, nodeCount: Int, compact: Bool) -> CGFloat {
    min(max(currentZoom, focusTargetZoom), maximumZoom(nodeCount: nodeCount, compact: compact))
  }

  static func panPreservingCenterZoom(
    _ pan: CGSize,
    from currentZoom: CGFloat,
    to nextZoom: CGFloat
  ) -> CGSize {
    let ratio = nextZoom / max(currentZoom, minimumZoom)
    return CGSize(width: pan.width * ratio, height: pan.height * ratio)
  }
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
      if zoom < 1.35 {
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
    let edgeLimit: Int =
      switch detailLevel {
      case .overview: 36
      case .neighborhood: 96
      case .detail: 160
      case .focus: 260
      case .inspect: 360
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
      canvasLabelNodes: usesCanvasLabels ? visibleNodes : [],
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
    var byCluster: [MemoryAtlasCluster: [MemoryAtlasNodePlacement]] = [:]
    for placement in candidates {
      if let cluster = placement.cluster {
        byCluster[cluster, default: []].append(placement)
      } else {
        unclustered.append(placement)
      }
    }

    var result = Array(unclustered.prefix(limit))
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
    let nodes = uniqueNodes(from: graph.nodes)
    let edges = uniqueEdges(from: graph.edges)

    guard !nodes.isEmpty else {
      return MemoryAtlasSnapshot(nodes: [], edges: [], anchorNodeID: nil, clusterCenters: [:])
    }

    var degree: [String: Int] = [:]
    for edge in edges {
      degree[edge.sourceId, default: 0] += 1
      degree[edge.targetId, default: 0] += 1
    }

    let normalizedUserName = userName?.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()

    // Entities that stand in for the account holder rather than naming them.
    let selfSynonyms: Set<String> = ["user", "me", "myself", "i", "the user"]

    let rawAnchor =
      nodes.first {
        $0.nodeType == .person && normalizedUserName != nil && $0.label.lowercased() == normalizedUserName
      } ?? nodes.filter { $0.nodeType == .person }.max {
        (degree[$0.id] ?? 0) < (degree[$1.id] ?? 0)
      }
      ?? nodes.max {
        (degree[$0.id] ?? 0) < (degree[$1.id] ?? 0)
      }

    // The center of your own map should say your name. The extractor writes a
    // generic "The User" whenever no memory happens to name you, and collapsing
    // the synonyms onto that node still left the anchor labelled "The User" —
    // the one dot the user can identify on sight was the one not identified.
    // The generic label survives as an alias so search still finds it.
    let anchor = rawAnchor.map { node -> KnowledgeGraphNode in
      guard let userName, !userName.isEmpty, selfSynonyms.contains(node.label.lowercased())
      else { return node }
      return KnowledgeGraphNode(
        id: node.id,
        label: userName,
        nodeType: node.nodeType,
        aliases: node.aliases + [node.label],
        memoryIds: node.memoryIds,
        createdAt: node.createdAt,
        updatedAt: node.updatedAt
      )
    }

    // Collapse every entity that stands in for the account holder — a generic
    // "User"/"Me" node, or a second person node sharing the user's name — into
    // the single anchor. Two ego nodes ("User" floating apart from "David") read
    // as a data bug; the atlas should have exactly one unmistakable "you" at the
    // center. Their relationships are rerouted onto the anchor below.
    let collapsedIDs: Set<String> = {
      guard let anchor else { return [] }
      return Set(
        nodes.filter { node in
          guard node.id != anchor.id else { return false }
          let label = node.label.lowercased()
          if let normalizedUserName, !normalizedUserName.isEmpty, label == normalizedUserName {
            return true
          }
          return node.nodeType == .person && selfSynonyms.contains(label)
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
    var memoryIDsByNodeID: [String: [String]] = [:]
    if let anchor { memoryIDsByNodeID[anchor.id] = anchor.memoryIds }
    for groupNodes in grouped.values {
      for node in groupNodes { memoryIDsByNodeID[node.id] = node.memoryIds }
    }
    // A self-node folded into the anchor brings its memories with it, or the
    // anchor loses the co-occurrence its own entity earned.
    if let anchorID = anchor?.id {
      for node in nodes where collapsedIDs.contains(node.id) {
        memoryIDsByNodeID[anchorID, default: []].append(contentsOf: node.memoryIds)
      }
    }

    let relatedness =
      MemoryAtlasForceLayout.explicitLinks(
        edges: mergedEdges.map {
          (
            sourceID: $0.edge.sourceId, targetID: $0.edge.targetId,
            memoryCount: $0.edge.memoryIds.count
          )
        })
      + MemoryAtlasForceLayout.coOccurrenceLinks(memoryIDsByNodeID: memoryIDsByNodeID)

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
          clusterRank: 0
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
            clusterRank: index
          )
        )
      }
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
      return MemoryAtlasEdgePlacement(
        edge: merged.edge,
        source: source,
        target: target,
        cluster: cluster,
        relationshipLabels: merged.relationshipLabels,
        weight: merged.weight
      )
    }

    return MemoryAtlasSnapshot(
      nodes: placements,
      edges: edgePlacements,
      anchorNodeID: anchor?.id,
      clusterCenters: centroids(of: placements, activeClusters: activeClusters)
    )
  }

  /// The region the relaxed map may occupy. Isolates are parked in the margin
  /// outside it, so it stops short of the canvas edge.
  static let layoutArea = CGRect(x: 0.12, y: 0.16, width: 0.76, height: 0.68)

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

      Divider().overlay(OmiColors.border.opacity(0.2))

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
    .background(OmiColors.backgroundSecondary)
    .overlay(alignment: .leading) {
      Rectangle().fill(OmiColors.border.opacity(0.25)).frame(width: 1)
    }
    .accessibilityIdentifier("memory_atlas_detail_panel")
  }

  @ViewBuilder
  private var evidenceSection: some View {
    if evidenceIsLoading && evidence.isEmpty {
      HStack(spacing: 7) {
        ProgressView()
          .controlSize(.small)
          .tint(OmiColors.textTertiary)
        Text("Reading your memories…")
          .scaledFont(size: 11)
          .foregroundColor(OmiColors.textQuaternary)
      }
    } else if evidence.isEmpty && unresolvedEvidenceCount == 0 {
      Text("Source memories are still being linked for this entity.")
        .scaledFont(size: 11)
        .foregroundColor(OmiColors.textQuaternary)
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
        .foregroundColor(OmiColors.textQuaternary)
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
            .foregroundColor(OmiColors.textSecondary)
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
          .foregroundColor(OmiColors.textPrimary)
          .fixedSize(horizontal: false, vertical: true)
        Text(subject.subtitle)
          .scaledFont(size: 11)
          .foregroundColor(OmiColors.textTertiary)
          .fixedSize(horizontal: false, vertical: true)
      }

      Spacer(minLength: 4)

      Button(action: onFocus) {
        Image(systemName: "scope")
          .scaledFont(size: 11, weight: .medium)
          .foregroundColor(OmiColors.textSecondary)
          .frame(width: 24, height: 24)
          .contentShape(Rectangle())
      }
      .buttonStyle(.plain)
      .help("Center the map on this entity")
      .accessibilityIdentifier("memory_atlas_focus_selection")

      Button(action: onClose) {
        Image(systemName: "xmark")
          .scaledFont(size: 10, weight: .semibold)
          .foregroundColor(OmiColors.textTertiary)
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
        .foregroundColor(OmiColors.textQuaternary)
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
            .foregroundColor(isHovered ? OmiColors.textPrimary : OmiColors.textSecondary)
            .fixedSize(horizontal: false, vertical: true)
          Text(row.relationship)
            .scaledFont(size: 10)
            .foregroundColor(OmiColors.textQuaternary)
            .fixedSize(horizontal: false, vertical: true)
        }
        Spacer(minLength: 4)
        Image(systemName: "chevron.right")
          .scaledFont(size: 9, weight: .semibold)
          .foregroundColor(OmiColors.textQuaternary)
          .opacity(isHovered ? 1 : 0)
          .padding(.top, 3)
      }
      .padding(.vertical, 5)
      .padding(.horizontal, 6)
      .frame(maxWidth: .infinity, alignment: .leading)
      .background(
        RoundedRectangle(cornerRadius: 7, style: .continuous)
          .fill(isHovered ? OmiColors.backgroundRaised.opacity(0.7) : Color.clear)
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
          .foregroundColor(isHovered ? OmiColors.textPrimary : OmiColors.textSecondary)
          .fixedSize(horizontal: false, vertical: true)
          .frame(maxWidth: .infinity, alignment: .leading)
        // The date holds this row whether or not the cursor is here, so the
        // "Open" affordance can fade in without the row changing height.
        HStack(spacing: 4) {
          if let createdAt = item.createdAt {
            Text(createdAt.formatted(date: .abbreviated, time: .shortened))
              .scaledFont(size: 9.5)
              .foregroundColor(OmiColors.textQuaternary)
          }
          Spacer(minLength: 4)
          HStack(spacing: 3) {
            Text("Open")
              .scaledFont(size: 9.5, weight: .medium)
            Image(systemName: "arrow.up.right")
              .scaledFont(size: 8, weight: .semibold)
          }
          .foregroundColor(OmiColors.textTertiary)
          .opacity(isHovered ? 1 : 0)
        }
      }
      .frame(maxWidth: .infinity, alignment: .leading)
      .padding(10)
      .background(
        RoundedRectangle(cornerRadius: 10, style: .continuous)
          .fill(OmiColors.backgroundRaised.opacity(isHovered ? 0.95 : 0.6))
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

struct CanonicalMemoryAtlasPage: View {
  @ObservedObject var viewModel: MemoryGraphViewModel
  let onBack: () -> Void
  let evidenceProvider: ([String]) async -> [MemoryAtlasEvidence]
  /// Opens a cited memory on the Memories surface this page came from.
  let onOpenMemory: (String) -> Void

  var body: some View {
    VStack(spacing: 0) {
      HStack(spacing: 12) {
        Button(action: onBack) {
          Label("Memories", systemImage: "chevron.left")
            .scaledFont(size: 12, weight: .semibold)
            .foregroundColor(OmiColors.textSecondary)
            .padding(.horizontal, 10)
            .frame(height: 30)
            .omiControlSurface(fill: OmiColors.backgroundRaised, radius: 11)
        }
        .buttonStyle(.plain)
        .accessibilityIdentifier("memory_atlas_back_to_memories")

        // "Brain Map" everywhere the user can see it: the atlas replaces the
        // legacy graph on the destination that already had that name, so
        // introducing a second name for the same place only splits the domain
        // vocabulary. "Atlas" survives in type and symbol names only.
        Text("Brain Map")
          .scaledFont(size: 17, weight: .semibold)
          .foregroundColor(OmiColors.textPrimary)

        Spacer()

        Text("\(viewModel.graphResponse.nodes.count) entities · \(viewModel.graphResponse.edges.count) connections")
          .scaledFont(size: 12)
          .foregroundColor(OmiColors.textTertiary)
      }
      .padding(.horizontal, 18)
      .frame(height: 44)
      .background(OmiColors.backgroundSecondary)

      Divider().overlay(OmiColors.border.opacity(0.25))

      CanonicalMemoryAtlasSurface(
        graph: viewModel.graphResponse,
        compact: false,
        evidenceProvider: evidenceProvider,
        onOpenMemory: onOpenMemory,
        onRebuild: { Task { await viewModel.rebuildGraph() } },
        isRebuilding: viewModel.isRebuilding
      )
    }
    .background(OmiColors.backgroundPrimary)
    .accessibilityIdentifier("canonical_memory_atlas_page")
    .task { await viewModel.prepareCanonicalAtlas() }
    .onAppear {
      memoryAtlasLogger.info(
        "Atlas page opened nodes=\(viewModel.graphResponse.nodes.count, privacy: .public) edges=\(viewModel.graphResponse.edges.count, privacy: .public)"
      )
    }
  }
}

/// Memory hub presentation of the atlas.
///
/// The hub already owns navigation chrome (the Memory menu selects the
/// destination), so this variant renders the surface full-bleed instead of
/// stacking the page's own back/title bar underneath the hub bar. It is the
/// canonical-cohort counterpart to `MemoryGraphPage`, which fills the same tab
/// for users still on the legacy graph.
struct CanonicalMemoryAtlasTabView: View {
  @ObservedObject var viewModel: MemoryGraphViewModel
  let evidenceProvider: ([String]) async -> [MemoryAtlasEvidence]
  /// Opens a cited memory on the hub's Memories destination.
  let onOpenMemory: (String) -> Void

  var body: some View {
    CanonicalMemoryAtlasSurface(
      graph: viewModel.graphResponse,
      compact: false,
      evidenceProvider: evidenceProvider,
      onOpenMemory: onOpenMemory,
      onRebuild: { Task { await viewModel.rebuildGraph() } },
      isRebuilding: viewModel.isRebuilding
    )
    .background(OmiColors.backgroundPrimary)
    .accessibilityIdentifier("canonical_memory_atlas_tab")
    .task { await viewModel.prepareCanonicalAtlas() }
    .onAppear {
      memoryAtlasLogger.info(
        "Atlas tab opened nodes=\(viewModel.graphResponse.nodes.count, privacy: .public) edges=\(viewModel.graphResponse.edges.count, privacy: .public)"
      )
    }
  }
}

// MARK: - Interactive Atlas Surface

private struct CanonicalMemoryAtlasSurface: View {
  let graph: KnowledgeGraphResponse
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
    compact: Bool,
    evidenceProvider: @escaping ([String]) async -> [MemoryAtlasEvidence] = { _ in [] },
    onOpenMemory: ((String) -> Void)? = nil,
    onRebuild: (() -> Void)? = nil,
    isRebuilding: Bool = false,
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
    self.compact = compact
    self.evidenceProvider = evidenceProvider
    self.onOpenMemory = onOpenMemory
    self.onRebuild = onRebuild
    self.isRebuilding = isRebuilding
    self.previewTimeCursor = previewTimeCursor
    self.previewEvidence = previewEvidence
    _timeCursor = State(initialValue: previewTimeCursor ?? 1)
    _selectedNodeID = State(initialValue: previewSelectedNodeID)
    _selectedEdgeID = State(initialValue: previewSelectedEdgeID)
    _evidence = State(initialValue: previewEvidence)
    _requestedEvidenceIDs = State(initialValue: previewEvidence.map(\.id))
    let givenName = AuthService.shared.givenName.trimmingCharacters(in: .whitespacesAndNewlines)
    // Memoized: SwiftUI re-runs this initializer on every parent re-render, and
    // the layout now relaxes the whole graph rather than evaluating a formula
    // per node.
    let atlasSnapshot = MemoryAtlasSnapshotCache.shared.snapshot(
      for: graph,
      userName: givenName.isEmpty ? nil : givenName
    )
    snapshot = atlasSnapshot
    renderPlanCache = MemoryAtlasRenderPlanCache(snapshot: atlasSnapshot)
    if let timeline = atlasSnapshot.timeline {
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

        ZStack {
          OmiColors.backgroundPrimary

          atlasCanvas(size: proxy.size, plan: plan)
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
                showLabel: plan.labelNodeIDs.contains(placement.id),
                labelAbove: plan.labelAboveNodeIDs.contains(placement.id)
              )
            }
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
              onEscape: clearTransientState,
              onFocusSearch: { searchIsFocused = true }
            )
            .accessibilityHidden(true)
          }
        }
        .onAppear { viewportSize = proxy.size }
        .onChange(of: proxy.size) { _, newSize in viewportSize = newSize }
        .clipped()
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
    .background(OmiColors.backgroundPrimary)
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
        selectedNodeID = edge.edge.sourceId
        selectedEdgeID = edgeID
        return
      }
      if let nodeID = notification.userInfo?["node_id"] as? String,
        snapshot.nodeByID[nodeID] != nil
      {
        selectionTrail.removeAll()
        selectedEdgeID = nil
        selectedNodeID = nodeID
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
          .foregroundColor(OmiColors.textTertiary)

        TextField("Search your entities", text: $searchText)
          .textFieldStyle(.plain)
          .focused($searchIsFocused)
          .scaledFont(size: 12)
          .foregroundColor(OmiColors.textPrimary)
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
              .foregroundColor(OmiColors.textTertiary)
          }
          .buttonStyle(.plain)
          .help("Clear search (Esc)")
          .accessibilityLabel("Clear search")
        }
      }
      .padding(.horizontal, 12)
      .frame(width: compact ? 250 : 320, height: 30)
      .omiControlSurface(fill: OmiColors.backgroundRaised, radius: 11, stroke: OmiColors.border.opacity(0.3))

      Spacer()

      if !compact {
        typeKey
      }

      if recentConnectionCount > 0 {
        HStack(spacing: 6) {
          Circle()
            .fill(snapshot.activeClusters.first?.color ?? OmiColors.textSecondary)
            .frame(width: 6, height: 6)
          Text(recentConnectionLabel)
            .scaledFont(size: 11, weight: .medium)
        }
        .foregroundColor(OmiColors.textSecondary)
      }

      // The legacy Brain Map carried a rebuild control; without it a thin or
      // stale server graph has no recovery path from inside the atlas.
      if let onRebuild {
        Button(action: onRebuild) {
          Image(systemName: "arrow.clockwise")
            .scaledFont(size: 11, weight: .medium)
            .foregroundColor(OmiColors.textSecondary.opacity(isRebuilding ? 0.35 : 1))
            .frame(width: 26, height: 26)
            .omiControlSurface(fill: OmiColors.backgroundRaised, radius: 9)
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
    .background(OmiColors.backgroundPrimary)
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
            .foregroundColor(OmiColors.textTertiary)
        }
      }
    }
    .accessibilityIdentifier("memory_atlas_type_key")
  }

  private func atlasCanvas(size: CGSize, plan: MemoryAtlasRenderPlan) -> some View {
    Canvas(opaque: false, colorMode: .linear) { context, _ in
      drawEdges(context: &context, size: size, plan: plan)
      drawNodes(context: &context, size: size, plan: plan)
      drawCanvasLabels(context: &context, size: size, plan: plan)
    }
    .accessibilityHidden(true)
  }

  private func drawEdges(
    context: inout GraphicsContext,
    size: CGSize,
    plan: MemoryAtlasRenderPlan
  ) {
    let paintBounds = canvasPaintBounds(for: size)
    for cluster in snapshot.activeClusters {
      var path = Path()
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
        path.move(to: source)
        path.addLine(to: target)
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
    // While the time cursor is engaged, an entity that was just "born" blooms
    // briefly as the playhead sweeps past its creation date, then settles into
    // the constellation — the atlas visibly grows rather than snapping in.
    let replayCursor = timeCursor < 0.9995 ? timeCursor : nil
    let paintBounds = canvasPaintBounds(for: size)

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

  private func drawCanvasLabels(
    context: inout GraphicsContext,
    size: CGSize,
    plan: MemoryAtlasRenderPlan
  ) {
    guard plan.usesCanvasLabels else { return }

    // From the density-aware inspection threshold onward, every dot on this
    // canvas gets a label. Skip labels outside the clipped canvas before
    // resolving Text, which makes a 10k-node graph cost proportional to the
    // current viewport rather than the total graph size.
    let visibleBounds = CGRect(origin: .zero, size: size)
    for placement in plan.canvasLabelNodes {
      let center = point(for: placement.normalizedPosition, in: size)
      guard visibleBounds.contains(center) else { continue }

      let color = placement.cluster?.color ?? OmiColors.textPrimary
      let estimatedLabelWidth = min(
        152.0,
        max(44.0, CGFloat(placement.node.label.count) * 6.4 + 18)
      )
      let labelCenterX = min(
        max(center.x, estimatedLabelWidth / 2),
        size.width - estimatedLabelWidth / 2
      )
      let text = Text(placement.node.label)
        .font(.system(size: 11, weight: placement.id == snapshot.anchorNodeID ? .semibold : .medium))
        .foregroundStyle(OmiColors.textPrimary)
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
      .foregroundColor(OmiColors.textPrimary)
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
    let color = placement.cluster?.color ?? OmiColors.textPrimary
    let diameter = nodeDiameter(placement, selected: selected)

    // Keeping the label out of the laid-out frame is what makes the ring land
    // on the node. A VStack of ring-over-label is centered by `.position`, so
    // the ring floats above the point while the Canvas paints the dot on it —
    // two marks per entity, visibly offset once dots are more than a few px.
    let hitDiameter = max(diameter, 24)

    return Button {
      selectionTrail.removeAll()
      selectedEdgeID = nil
      selectedNodeID = selected ? nil : placement.id
    } label: {
      ZStack {
        if selected {
          Circle()
            .stroke(color.opacity(0.22), lineWidth: 7)
            .frame(width: diameter + 14, height: diameter + 14)
        }
        Circle()
          .fill(OmiColors.backgroundRaised)
          .overlay(Circle().stroke(color, lineWidth: selected ? 2.2 : 1.4))
          .frame(width: diameter, height: diameter)
        if placement.id == snapshot.anchorNodeID {
          Image(systemName: "person.fill")
            .scaledFont(size: max(9, diameter * 0.38))
            .foregroundColor(OmiColors.textPrimary)
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
        accent: other.cluster?.color ?? OmiColors.textTertiary
      )
    }

    return MemoryAtlasDetailPanel(
      subject: .entity(
        title: placement.node.label,
        typeName: placement.cluster?.title,
        connectionSummary: "\(placement.degree) connection\(placement.degree == 1 ? "" : "s")"
      ),
      accent: placement.cluster?.color ?? OmiColors.textPrimary,
      related: relationships,
      evidence: evidence,
      evidenceIsLoading: evidenceIsLoading,
      unresolvedEvidenceCount: unresolvedEvidenceCount,
      onOpenRelated: openRelated,
      onOpenMemory: openCitedMemory,
      onBack: backAction,
      onFocus: { focus(on: placement) },
      onClose: clearSelection
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
        accent: endpoint.cluster?.color ?? OmiColors.textTertiary
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
      onClose: clearSelection
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
    selectedEdgeID = nil
    selectedNodeID = row.otherNodeID
  }

  private func goBack() {
    guard let previous = selectionTrail.popLast() else { return }
    selectedEdgeID = nil
    selectedNodeID = previous
  }

  private func clearSelection() {
    selectionTrail.removeAll()
    selectedEdgeID = nil
    selectedNodeID = nil
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
        .fill((placement.cluster?.color ?? OmiColors.textPrimary).opacity(0.14))
        .overlay(Circle().stroke(placement.cluster?.color ?? OmiColors.textPrimary, lineWidth: 1.5))
        .frame(width: 34, height: 34)

      VStack(alignment: .leading, spacing: 2) {
        Text(placement.node.label)
          .scaledFont(size: compact ? 12 : 14, weight: .semibold)
          .foregroundColor(OmiColors.textPrimary)
        Text(relationshipText)
          .scaledFont(size: compact ? 10 : 12)
          .foregroundColor(OmiColors.textTertiary)
          .lineLimit(1)
      }

      Spacer()

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

      // Compact surfaces cannot fit the inspector, so the strip reports the
      // evidence count rather than offering a jump that would leave the map.
      Text(
        evidenceIds.isEmpty
          ? "Source details are still being linked"
          : "\(evidenceIds.count) source memor\(evidenceIds.count == 1 ? "y" : "ies")"
      )
      .scaledFont(size: 10)
      .foregroundColor(OmiColors.textQuaternary)

      Button {
        clearSelection()
      } label: {
        Image(systemName: "xmark")
          .scaledFont(size: 10, weight: .semibold)
          .foregroundColor(OmiColors.textTertiary)
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
    .background(OmiColors.backgroundSecondary)
    .overlay(alignment: .top) {
      Divider().overlay(OmiColors.border.opacity(0.24))
    }
  }

  private var atlasLegend: some View {
    HStack(spacing: 18) {
      Text(atlasLevelLabel)
        .scaledFont(size: 11, weight: .medium)
        .foregroundColor(OmiColors.textSecondary)

      Spacer()
    }
    .padding(.horizontal, 18)
    .frame(height: 36)
    .background(OmiColors.backgroundSecondary)
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
            Circle().fill(OmiColors.textPrimary).frame(width: 22, height: 22)
            Image(systemName: isTimePlaying ? "pause.fill" : "play.fill")
              .scaledFont(size: 9, weight: .bold)
              .foregroundColor(OmiColors.backgroundPrimary)
              .offset(x: isTimePlaying ? 0 : 1)
          }
        }
        .buttonStyle(.plain)
        .help(isTimePlaying ? "Pause" : "Play your memory forward")
        .accessibilityLabel(isTimePlaying ? "Pause memory timeline" : "Play memory timeline")
        .accessibilityIdentifier("memory_atlas_timeline_play")

        Text(asOfLabel)
          .scaledFont(size: 11, weight: .semibold)
          .foregroundColor(OmiColors.textPrimary)
          .lineLimit(1)

        Text("\(visibleEntityCount) entities · \(visibleConnectionCount) connections")
          .scaledFont(size: 10)
          .foregroundColor(OmiColors.textTertiary)
          .monospacedDigit()
          .lineLimit(1)

        Spacer(minLength: 8)

        Text(atlasLevelLabel)
          .scaledFont(size: 10, weight: .medium)
          .foregroundColor(OmiColors.textTertiary)
          .lineLimit(1)

        if timeCursor < 0.9995 {
          Button(action: jumpToNow) {
            Text("Now")
              .scaledFont(size: 10, weight: .semibold)
              .foregroundColor(OmiColors.textSecondary)
              .padding(.horizontal, 8)
              .frame(height: 18)
              .omiControlSurface(fill: OmiColors.backgroundRaised, radius: 6)
          }
          .buttonStyle(.plain)
          .accessibilityIdentifier("memory_atlas_timeline_now")
        }
      }

      // The range endpoints flank the scrubber instead of taking a third row.
      HStack(spacing: 8) {
        Text(shortDate(timeline?.start))
          .scaledFont(size: 9)
          .foregroundColor(OmiColors.textQuaternary)
          .lineLimit(1)

        timelineTrack

        Text(timeline?.hasChronologicalRange == true ? "Now" : "Imported")
          .scaledFont(size: 9)
          .foregroundColor(OmiColors.textQuaternary)
          .lineLimit(1)
      }
    }
    .padding(.horizontal, 18)
    .padding(.vertical, 8)
    .background(OmiColors.backgroundSecondary)
    .overlay(alignment: .top) {
      Divider().overlay(OmiColors.border.opacity(0.24))
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
        with: .color(OmiColors.textPrimary.opacity(born ? 0.3 : 0.08))
      )
    }

    var baseline = Path()
    baseline.move(to: CGPoint(x: 0, y: baseY))
    baseline.addLine(to: CGPoint(x: size.width, y: baseY))
    context.stroke(baseline, with: .color(OmiColors.border.opacity(0.5)), lineWidth: 1)

    var filled = Path()
    filled.move(to: CGPoint(x: 0, y: baseY))
    filled.addLine(to: CGPoint(x: cursorX, y: baseY))
    context.stroke(filled, with: .color(OmiColors.textPrimary.opacity(0.85)), lineWidth: 1.5)

    var playhead = Path()
    playhead.move(to: CGPoint(x: cursorX, y: 0))
    playhead.addLine(to: CGPoint(x: cursorX, y: size.height))
    context.stroke(playhead, with: .color(OmiColors.textPrimary.opacity(0.85)), lineWidth: 1.5)

    context.fill(
      Path(ellipseIn: CGRect(x: cursorX - 5, y: baseY - 5, width: 10, height: 10)),
      with: .color(OmiColors.textPrimary)
    )
  }

  private var asOfLabel: String {
    guard let asOf = asOfDate else { return "Now — the whole map" }
    let formatter = DateFormatter()
    formatter.dateStyle = .medium
    formatter.timeStyle = .none
    if timeline?.hasChronologicalRange == false {
      return "Import replay · \(formatter.string(from: asOf))"
    }
    return "Replay · \(formatter.string(from: asOf))"
  }

  private func shortDate(_ date: Date?) -> String {
    guard let date else { return "" }
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
      let totalSeconds = 6.5
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
    .foregroundColor(OmiColors.textSecondary)
    .omiControlSurface(
      fill: OmiColors.backgroundRaised.opacity(0.96), radius: 10, stroke: OmiColors.border.opacity(0.3)
    )
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

  private func canvasPaintBounds(for size: CGSize) -> CGRect {
    CGRect(x: -28, y: -28, width: size.width + 56, height: size.height + 56)
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
    selectionTrail.removeAll()
    selectedEdgeID = nil
    selectedNodeID =
      snapshot.nodes.first {
        matchingNodeIDs.contains($0.id) && nodeIsVisibleAtCurrentTime($0)
      }?.id
  }

  /// Routes a click on the canvas to whatever it landed on.
  ///
  /// Entities are tested first and win outright: every dot sits on at least one
  /// line, so letting a line take the hit near a dot would make dots feel
  /// unclickable at the exact places they matter most.
  private func selectAtlasElement(at location: CGPoint, in size: CGSize, plan: MemoryAtlasRenderPlan) {
    if let node = nearestNode(to: location, in: size) {
      // Reaching for something on the canvas starts a fresh trail; only
      // following a listed connection extends one.
      selectionTrail.removeAll()
      selectedEdgeID = nil
      selectedNodeID = node.id
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
    selectedNodeID = hit.edge.sourceId
    selectedEdgeID = hit.id
  }

  private func nearestNode(to location: CGPoint, in size: CGSize) -> MemoryAtlasNodePlacement? {
    let hitRadius = max(12, 18 / zoom)
    var nearest: (placement: MemoryAtlasNodePlacement, distance: CGFloat)?
    for placement in snapshot.nodes where nodeIsVisibleAtCurrentTime(placement) {
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
    let focusedZoom = MemoryAtlasZoomPolicy.focusedZoom(
      currentZoom: zoom,
      nodeCount: snapshot.nodes.count,
      compact: compact
    )
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

  private func resetViewport() {
    withAnimation(.easeOut(duration: 0.2)) {
      zoom = 1
      settledZoom = 1
      pan = .zero
      settledPan = .zero
    }
  }

  private func clearTransientState() {
    searchIsFocused = false
    searchText = ""
    matchingNodeIDs = nil
    matchingEdges = nil
    clearSelection()
  }
}

/// SwiftUI has no view-local scroll-wheel gesture on the macOS 14 deployment
/// floor. This passive bridge observes the Atlas viewport without entering the
/// hit-test chain, so normal dragging, tapping, and control interaction remain
/// owned by SwiftUI.
private struct MemoryAtlasInputMonitor: NSViewRepresentable {
  let onScroll: (CGFloat, CGPoint) -> Void
  let onEscape: () -> Void
  let onFocusSearch: () -> Void

  func makeCoordinator() -> Coordinator {
    Coordinator(onScroll: onScroll, onEscape: onEscape, onFocusSearch: onFocusSearch)
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
    context.coordinator.onEscape = onEscape
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
    var onEscape: () -> Void
    var onFocusSearch: () -> Void
    fileprivate var windowNumber: Int?
    fileprivate var frameInWindow: CGRect = .zero
    private var eventMonitor: Any?

    init(
      onScroll: @escaping (CGFloat, CGPoint) -> Void,
      onEscape: @escaping () -> Void,
      onFocusSearch: @escaping () -> Void
    ) {
      self.onScroll = onScroll
      self.onEscape = onEscape
      self.onFocusSearch = onFocusSearch
    }

    func installMonitor() {
      eventMonitor = NSEvent.addLocalMonitorForEvents(matching: [.scrollWheel, .keyDown]) {
        [weak self] event in
        guard let self, event.windowNumber == self.windowNumber else {
          return event
        }

        if event.type == .keyDown, event.keyCode == 53 {
          self.onEscape()
          return nil
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
