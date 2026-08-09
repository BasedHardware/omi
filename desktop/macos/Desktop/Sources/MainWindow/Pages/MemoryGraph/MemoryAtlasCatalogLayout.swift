import CoreGraphics
import Foundation

/// Places canonical-memory records near verified evidence without making that
/// proximity a semantic edge, cluster membership, or graph-force input.
enum MemoryAtlasCatalogLayout {
  static func allowsAutomaticLabel(
    isCatalog: Bool,
    id: String,
    selectedNodeID: String?,
    matchingNodeIDs: Set<String>?
  ) -> Bool {
    !isCatalog || id == selectedNodeID || matchingNodeIDs?.contains(id) == true
  }

  static func positions(
    catalog: [KnowledgeGraphNode],
    assertions: [KnowledgeGraphNode],
    communities: [String: Int],
    assertionPositions: [String: CGPoint],
    ownerID: String?,
    area: CGRect
  ) -> [String: CGPoint] {
    var assertionsByMemory: [String: [KnowledgeGraphNode]] = [:]
    for assertion in assertions where assertion.id != ownerID {
      for memoryID in assertion.memoryIds {
        assertionsByMemory[memoryID, default: []].append(assertion)
      }
    }

    let records = catalog.sorted { $0.id < $1.id }
    let spacing = CGFloat(
      max(0.006, min(0.014, 0.48 * sqrt(Double(area.width * area.height) / Double(max(records.count, 1)))))
    )
    let owner = ownerID.flatMap { assertionPositions[$0] }
    var occupied = assertionPositions.values.sorted { lhs, rhs in
      lhs.x == rhs.x ? lhs.y < rhs.y : lhs.x < rhs.x
    }
    var result: [String: CGPoint] = [:]

    for record in records {
      let evidence = evidenceIDs(for: record)
      let matchingAssertions = evidence.flatMap { assertionsByMemory[$0] ?? [] }
        .filter { assertionPositions[$0.id] != nil }
      let selected = preferredAssertions(matchingAssertions, communities: communities)

      guard !selected.isEmpty else {
        // A memory without verified entity evidence remains present, but it is
        // a softly distributed background mark in a disk, never a rectangular
        // grid or a synthetic community.
        let point = settled(orphanPoint(for: record.id, in: area), awayFrom: occupied, spacing: spacing, in: area)
        occupied.append(point)
        result[record.id] = point
        continue
      }

      let center = weightedCenter(of: selected, positions: assertionPositions)
      let angle = MemoryAtlasForceLayout.stableFraction("\(record.id)|petal-angle") * .pi * 2
      let radius = spacing * CGFloat(1.2 + MemoryAtlasForceLayout.stableFraction("\(record.id)|petal-radius") * 3.8)
      var point = CGPoint(
        x: center.x + cos(angle) * radius,
        y: center.y + sin(angle) * radius
      )
      if let owner, distance(point, owner) < spacing * 2.2 {
        point = CGPoint(
          x: point.x + cos(angle) * spacing * 2.2,
          y: point.y + sin(angle) * spacing * 2.2
        )
      }
      point = MemoryAtlasGeometry.constrainedToDisk(point, in: area, radiusFraction: 0.495)
      point = settled(point, awayFrom: occupied, spacing: spacing, in: area)
      occupied.append(point)
      result[record.id] = point
    }
    return result
  }

  private static func evidenceIDs(for record: KnowledgeGraphNode) -> [String] {
    var evidence = record.memoryIds
    if record.id.hasPrefix("memory:") {
      evidence.append(String(record.id.dropFirst("memory:".count)))
    }
    return Array(Set(evidence)).sorted()
  }

  /// Chooses an assertion neighbourhood using only exact shared memory IDs.
  /// Ties are settled by the stable sorted assertion identity, not API order.
  private static func preferredAssertions(
    _ matches: [KnowledgeGraphNode],
    communities: [String: Int]
  ) -> [KnowledgeGraphNode] {
    let unique = Dictionary(lastWriteWins: matches.map { ($0.id, $0) })
    let grouped = Dictionary(grouping: unique.values) { communities[$0.id] }
    guard !grouped.isEmpty else { return [] }

    let ranked = grouped.map { community, nodes in
      let sorted = nodes.sorted { $0.id < $1.id }
      let score = sorted.reduce(0.0) { partial, node in
        partial + 1 / sqrt(Double(max(node.memoryIds.count, 1)))
      }
      return (community, sorted, score, sorted.map(\.id).joined(separator: "|"))
    }
    return ranked.sorted {
      if $0.2 != $1.2 { return $0.2 > $1.2 }
      return $0.3 < $1.3
    }.first?.1 ?? []
  }

  private static func weightedCenter(
    of nodes: [KnowledgeGraphNode],
    positions: [String: CGPoint]
  ) -> CGPoint {
    let weighted = nodes.compactMap { node -> (CGPoint, Double)? in
      guard let point = positions[node.id] else { return nil }
      return (point, 1 / sqrt(Double(max(node.memoryIds.count, 1))))
    }
    let total = weighted.reduce(0.0) { $0 + $1.1 }
    guard total > 0 else { return .zero }
    return weighted.reduce(CGPoint.zero) { partial, pair in
      CGPoint(x: partial.x + pair.0.x * pair.1 / total, y: partial.y + pair.0.y * pair.1 / total)
    }
  }

  /// A uniform-area disk keeps unmatched memories legible as a loose cloud.
  /// It intentionally has neither a perimeter ring nor rectangular clipping.
  private static func orphanPoint(for id: String, in area: CGRect) -> CGPoint {
    let center = CGPoint(x: area.midX, y: area.midY)
    let radius =
      min(area.width, area.height) * 0.495
      * sqrt(MemoryAtlasForceLayout.stableFraction("\(id)|orphan-radius"))
    let angle = MemoryAtlasForceLayout.stableFraction("\(id)|orphan-angle") * .pi * 2
    return CGPoint(x: center.x + cos(angle) * radius, y: center.y + sin(angle) * radius)
  }

  private static func distance(_ lhs: CGPoint, _ rhs: CGPoint) -> CGFloat {
    hypot(lhs.x - rhs.x, lhs.y - rhs.y)
  }

  /// Display-only separation for marks with exactly shared evidence. It never
  /// affects edges, force layout, or community membership.
  private static func settled(
    _ initial: CGPoint,
    awayFrom occupied: [CGPoint],
    spacing: CGFloat,
    in area: CGRect
  ) -> CGPoint {
    guard !occupied.isEmpty else { return initial }
    var point = initial
    let step = max(spacing * 1.35, 0.008)
    for attempt in 0..<8 where occupied.contains(where: { distance(point, $0) < spacing }) {
      let angle = CGFloat(attempt) * .pi * (3 - sqrt(5))
      point = MemoryAtlasGeometry.constrainedToDisk(
        CGPoint(x: initial.x + cos(angle) * step, y: initial.y + sin(angle) * step),
        in: area,
        radiusFraction: 0.495)
    }
    return point
  }

}
