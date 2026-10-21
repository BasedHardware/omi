import AppKit
import OmiSupport
import SwiftUI

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
