import Foundation

struct MemoryAtlasCommunityProjection: Codable, Equatable {
  struct Community: Codable, Equatable, Identifiable {
    let id: String
    let anchorNodeID: String
    let fallbackNodeIDs: [String]
    let displayName: String
    let orderingKey: String
    let layoutSlot: Int
  }

  let version: Int
  let communities: [Community]
  let communityIDByNodeID: [String: String]
  let graphFingerprint: UInt64?

  init(
    version: Int,
    communities: [Community],
    communityIDByNodeID: [String: String],
    graphFingerprint: UInt64? = nil
  ) {
    self.version = version
    self.communities = communities
    self.communityIDByNodeID = communityIDByNodeID
    self.graphFingerprint = graphFingerprint
  }

  private enum CodingKeys: String, CodingKey {
    case version, communities, communityIDByNodeID, graphFingerprint
  }

  init(from decoder: Decoder) throws {
    let container = try decoder.container(keyedBy: CodingKeys.self)
    version = try container.decode(Int.self, forKey: .version)
    communities = try container.decode([Community].self, forKey: .communities)
    communityIDByNodeID = try container.decode([String: String].self, forKey: .communityIDByNodeID)
    graphFingerprint = try container.decodeIfPresent(UInt64.self, forKey: .graphFingerprint)
  }

  func encode(to encoder: Encoder) throws {
    var container = encoder.container(keyedBy: CodingKeys.self)
    try container.encode(version, forKey: .version)
    try container.encode(communities, forKey: .communities)
    try container.encode(communityIDByNodeID, forKey: .communityIDByNodeID)
    try container.encodeIfPresent(graphFingerprint, forKey: .graphFingerprint)
  }
}

/// A deterministic, persistence-agnostic projection of a changing knowledge graph.
/// Recency is deliberately absent: it can decorate the atlas without moving its landmarks.
enum MemoryAtlasCommunityDetector {
  struct Configuration {
    var minimumCommunityCount = 4
    var maximumCommunityCount = 7
    var reassignmentMargin = 1.2
    var propagationPassLimit = 12
  }

  private struct Neighbor {
    let id: String
    let weight: Double
  }

  private struct Candidate {
    let communityID: String
    let affinity: Double
    let distance: Int
  }

  static func detect(
    graph: KnowledgeGraphResponse,
    ownerNodeID: String? = nil,
    previous: MemoryAtlasCommunityProjection? = nil,
    configuration: Configuration = Configuration()
  ) -> MemoryAtlasCommunityProjection {
    let graphFingerprint = fingerprint(graph)
    if let previous, previous.graphFingerprint == graphFingerprint {
      return previous
    }
    let nodes = coalescedNodes(graph.nodes)
    guard !nodes.isEmpty else {
      return MemoryAtlasCommunityProjection(
        version: 1, communities: [], communityIDByNodeID: [:], graphFingerprint: graphFingerprint
      )
    }
    let nodeByID = Dictionary(lastWriteWins: nodes.map { ($0.id, $0) })
    let adjacency = makeAdjacency(graph.edges, nodeIDs: Set(nodeByID.keys), ownerNodeID: ownerNodeID)
    let sizeBasedCount = configuration.minimumCommunityCount + max(0, (nodes.count - 1) / 300)
    let targetCount = min(max(1, sizeBasedCount), min(configuration.maximumCommunityCount, nodes.count))

    var usedAnchors: Set<String> = []
    var communities: [MemoryAtlasCommunityProjection.Community] = []
    for old in previous?.communities.sorted(by: { $0.orderingKey < $1.orderingKey }) ?? [] {
      let candidates = [old.anchorNodeID] + old.fallbackNodeIDs
      guard let anchor = candidates.first(where: {
        nodeByID[$0] != nil && !usedAnchors.contains($0) && $0 != ownerNodeID
      }) else { continue }
      usedAnchors.insert(anchor)
      communities.append(makeCommunity(
        id: old.id, anchor: anchor, layoutSlot: old.layoutSlot, nodes: nodeByID, adjacency: adjacency
      ))
      if communities.count == targetCount { break }
    }

    while communities.count < targetCount {
      guard let anchor = selectAnchor(
        nodes: nodes, excluding: usedAnchors, existingAnchors: communities.map(\.anchorNodeID),
        adjacency: adjacency, ownerNodeID: ownerNodeID
      ) else { break }
      usedAnchors.insert(anchor.id)
      let occupiedSlots = Set(communities.map(\.layoutSlot))
      let slot = (0..<8).first { !occupiedSlots.contains($0) } ?? communities.count % 8
      communities.append(makeCommunity(
        id: "community:\(anchor.id)", anchor: anchor.id, layoutSlot: slot, nodes: nodeByID, adjacency: adjacency
      ))
    }
    communities.sort { $0.orderingKey < $1.orderingKey }

    let candidates = propagate(communities: communities, adjacency: adjacency, passLimit: configuration.propagationPassLimit)
    var membership: [String: String] = [:]
    for node in nodes.sorted(by: { $0.id < $1.id }) {
      let ranked = candidates[node.id, default: []].sorted(by: candidatePrecedes)
      guard let best = ranked.first else {
        membership[node.id] = nearestFallbackCommunity(nodeID: node.id, communities: communities)
        continue
      }
      if let oldID = previous?.communityIDByNodeID[node.id],
         communities.contains(where: { $0.id == oldID }),
         let old = ranked.first(where: { $0.communityID == oldID }),
         best.communityID != oldID,
         best.affinity < old.affinity * configuration.reassignmentMargin {
        membership[node.id] = oldID
      } else {
        membership[node.id] = best.communityID
      }
    }
    for community in communities { membership[community.anchorNodeID] = community.id }

    return MemoryAtlasCommunityProjection(
      version: 1,
      communities: communities,
      communityIDByNodeID: membership,
      graphFingerprint: graphFingerprint
    )
  }

  private static func fingerprint(_ graph: KnowledgeGraphResponse) -> UInt64 {
    var hash: UInt64 = 0xcbf2_9ce4_8422_2325
    func mix(_ value: String) {
      for byte in value.utf8 {
        hash = (hash ^ UInt64(byte)) &* 0x0000_0100_0000_01b3
      }
    }
    for node in graph.nodes.sorted(by: { $0.id < $1.id }) {
      mix(node.id)
      mix(node.label)
      mix(node.nodeType.rawValue)
      mix("n\(Set(node.memoryIds).count)")
    }
    for edge in graph.edges.sorted(by: { $0.id < $1.id }) {
      mix(edge.id)
      mix(edge.sourceId)
      mix(edge.targetId)
      mix(edge.label)
      mix("e\(Set(edge.memoryIds).count)")
    }
    return hash
  }

  private static func coalescedNodes(_ nodes: [KnowledgeGraphNode]) -> [KnowledgeGraphNode] {
    var result: [String: KnowledgeGraphNode] = [:]
    for node in nodes { result[node.id] = node }
    return result.values.sorted { $0.id < $1.id }
  }

  private static func makeAdjacency(
    _ edges: [KnowledgeGraphEdge], nodeIDs: Set<String>, ownerNodeID: String?
  ) -> [String: [Neighbor]] {
    struct PairEvidence {
      var memoryIDs: Set<String> = []
      var hasSpecificRelationship = false
    }
    var pairs: [String: PairEvidence] = [:]
    for edge in edges.sorted(by: { $0.id < $1.id }) where nodeIDs.contains(edge.sourceId) && nodeIDs.contains(edge.targetId) {
      guard edge.sourceId != edge.targetId else { continue }
      let normalized = normalize(edge.label)
      let endpoints = [edge.sourceId, edge.targetId].sorted()
      let key = endpoints[0] + "\u{1f}" + endpoints[1]
      pairs[key, default: PairEvidence()].memoryIDs.formUnion(edge.memoryIds)
      pairs[key, default: PairEvidence()].hasSpecificRelationship =
        pairs[key, default: PairEvidence()].hasSpecificRelationship || !genericRelationships.contains(normalized)
    }
    var combined: [String: [String: Double]] = [:]
    for (key, evidence) in pairs {
      let endpoints = key.split(separator: "\u{1f}", omittingEmptySubsequences: false).map(String.init)
      guard endpoints.count == 2 else { continue }
      var weight = 1 + log2(Double(evidence.memoryIDs.count) + 1)
      weight += evidence.hasSpecificRelationship ? 0.65 : 0
      if endpoints.contains(ownerNodeID ?? "") { weight *= 0.08 }
      if !evidence.hasSpecificRelationship { weight *= 0.35 }
      combined[endpoints[0], default: [:]][endpoints[1]] = weight
      combined[endpoints[1], default: [:]][endpoints[0]] = weight
    }
    return combined.mapValues { neighbors in
      neighbors.map { Neighbor(id: $0.key, weight: $0.value) }.sorted { $0.id < $1.id }
    }
  }

  private static func selectAnchor(
    nodes: [KnowledgeGraphNode], excluding: Set<String>, existingAnchors: [String],
    adjacency: [String: [Neighbor]], ownerNodeID: String?
  ) -> KnowledgeGraphNode? {
    let distances = distancesFromAnchors(existingAnchors, adjacency: adjacency)
    return nodes.filter {
      !excluding.contains($0.id) && $0.id != ownerNodeID && !genericLabels.contains(normalize($0.label))
    }.max { lhs, rhs in
      let left = anchorScore(lhs, distance: distances[lhs.id] ?? 8, hasAnchors: !existingAnchors.isEmpty, adjacency: adjacency)
      let right = anchorScore(rhs, distance: distances[rhs.id] ?? 8, hasAnchors: !existingAnchors.isEmpty, adjacency: adjacency)
      return left == right ? lhs.id > rhs.id : left < right
    } ?? nodes.first { !excluding.contains($0.id) && $0.id != ownerNodeID }
  }

  private static func anchorScore(
    _ node: KnowledgeGraphNode, distance: Int, hasAnchors: Bool, adjacency: [String: [Neighbor]]
  ) -> Double {
    let evidence = Set(node.memoryIds).count
    let degreeWeight = adjacency[node.id, default: []].reduce(0) { $0 + $1.weight }
    let durability = 1 + log2(Double(evidence) + 1) * 2 + min(degreeWeight, 30) * 0.25
    guard hasAnchors else { return durability }
    return durability * (1 + Double(max(1, min(distance, 6))) * 0.12)
  }

  private static func distancesFromAnchors(
    _ anchors: [String], adjacency: [String: [Neighbor]]
  ) -> [String: Int] {
    guard !anchors.isEmpty else { return [:] }
    var distances = Dictionary(lastWriteWins: anchors.map { ($0, 0) })
    var frontier = anchors.sorted()
    for distance in 1...8 {
      var next: [String] = []
      for nodeID in frontier {
        for neighbor in adjacency[nodeID, default: []] where distances[neighbor.id] == nil {
          distances[neighbor.id] = distance
          next.append(neighbor.id)
        }
      }
      if next.isEmpty { break }
      frontier = next.sorted()
    }
    return distances
  }

  private static func makeCommunity(
    id: String, anchor: String, layoutSlot: Int, nodes: [String: KnowledgeGraphNode], adjacency: [String: [Neighbor]]
  ) -> MemoryAtlasCommunityProjection.Community {
    let fallback = adjacency[anchor, default: []]
      .sorted { $0.weight == $1.weight ? $0.id < $1.id : $0.weight > $1.weight }
      .map(\.id).filter { nodes[$0] != nil }.prefix(3)
    let name = nodes[anchor]?.label.trimmingCharacters(in: .whitespacesAndNewlines)
    return .init(
      id: id, anchorNodeID: anchor, fallbackNodeIDs: Array(fallback),
      displayName: name?.isEmpty == false ? name! : "Community", orderingKey: id, layoutSlot: layoutSlot
    )
  }

  private static func propagate(
    communities: [MemoryAtlasCommunityProjection.Community], adjacency: [String: [Neighbor]], passLimit: Int
  ) -> [String: [Candidate]] {
    var result: [String: [Candidate]] = [:]
    var frontier = communities.map { Candidate(communityID: $0.id, affinity: 1, distance: 0) }
    var frontierNodes = communities.map(\.anchorNodeID)
    for (index, nodeID) in frontierNodes.enumerated() { result[nodeID] = [frontier[index]] }
    for _ in 0..<max(1, passLimit) {
      var next: [(String, Candidate)] = []
      for (index, candidate) in frontier.enumerated() {
        for neighbor in adjacency[frontierNodes[index], default: []] {
          let affinity = candidate.affinity * (neighbor.weight / (neighbor.weight + 1))
          let proposed = Candidate(communityID: candidate.communityID, affinity: affinity, distance: candidate.distance + 1)
          let current = result[neighbor.id, default: []].first { $0.communityID == proposed.communityID }
          if current == nil || candidatePrecedes(proposed, current!) {
            result[neighbor.id, default: []].removeAll { $0.communityID == proposed.communityID }
            result[neighbor.id, default: []].append(proposed)
            next.append((neighbor.id, proposed))
          }
        }
      }
      if next.isEmpty { break }
      next.sort { $0.0 == $1.0 ? candidatePrecedes($0.1, $1.1) : $0.0 < $1.0 }
      frontierNodes = next.map(\.0)
      frontier = next.map(\.1)
    }
    return result
  }

  private static func candidatePrecedes(_ lhs: Candidate, _ rhs: Candidate) -> Bool {
    if abs(lhs.affinity - rhs.affinity) > 0.000_000_1 { return lhs.affinity > rhs.affinity }
    if lhs.distance != rhs.distance { return lhs.distance < rhs.distance }
    return lhs.communityID < rhs.communityID
  }

  private static func nearestFallbackCommunity(
    nodeID: String, communities: [MemoryAtlasCommunityProjection.Community]
  ) -> String? {
    communities.min { lhs, rhs in
      stableHash(nodeID + lhs.id) < stableHash(nodeID + rhs.id)
    }?.id
  }

  private static func stableHash(_ value: String) -> UInt64 {
    value.utf8.reduce(0xcbf2_9ce4_8422_2325) { ($0 ^ UInt64($1)) &* 0x0000_0100_0000_01b3 }
  }

  private static func normalize(_ value: String) -> String {
    value.lowercased().replacingOccurrences(of: "-", with: "_").replacingOccurrences(of: " ", with: "_")
  }

  private static let genericRelationships: Set<String> = ["related_to", "associated_with", "mentions", "knows"]
  private static let genericLabels: Set<String> = [
    "app", "apps", "document", "documents", "download", "downloads", "thing", "user",
  ]
}
