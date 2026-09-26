import AppKit
import OmiSupport
import SwiftUI

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
