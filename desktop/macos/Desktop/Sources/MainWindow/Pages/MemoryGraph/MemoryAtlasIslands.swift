import CoreGraphics
import Foundation

/// Turns the layout's neighbourhoods into coastlines.
///
/// A neighbourhood used to be drawn as the ellipse covering most of its
/// members, which is the shape of an average rather than the shape of a group.
/// Two of them near each other overlapped, so the map could not honestly draw
/// either one's edge, and a group with two lobes got a single oval spanning the
/// gulf between them and claiming everything in it.
///
/// This draws the territory instead. Every member spreads a little influence
/// around itself; each patch of canvas belongs to whichever neighbourhood has
/// the most influence there, and holds land at all only where that influence
/// clears sea level. The coast is the line where one of those answers changes.
///
/// Two properties fall out of that and are the reason for the whole approach:
///
/// - **Territories tile.** Ownership is a single winner per patch, so no two
///   islands overlap and a shared coast means exactly "past here, the nearest
///   neighbourhood is a different one". The border is true by construction,
///   which is what lets the map draw every one of them.
/// - **A neighbourhood may be an archipelago.** A group living in two places
///   gets two islands, because nothing forces its land to be connected. That is
///   the honest picture: it says the group is split, where one oval would have
///   claimed the water in between.
enum MemoryAtlasIslands {
  /// Cells across the field. Sets how fine a bay or a strait can be, and costs
  /// its square in memory — at 192 the whole field is under 150 KB and a coast
  /// wanders at about the scale of the gap between two entities, which is the
  /// scale worth resolving.
  static let resolution = 128

  /// How far one entity's influence spreads, as a multiple of how far apart
  /// the entities on this particular map actually are.
  ///
  /// The one parameter that decides whether the map reads as islands or as a
  /// continent, and it cannot be an absolute distance. "Close together" means
  /// something different on an account with a thousand entities than on one
  /// with nine: a fixed radius tuned for the dense case leaves the sparse one
  /// with no land anywhere, which is exactly what happened — a nine-entity
  /// account lost its regions entirely while the thousand-entity one looked
  /// right. Measuring the map's own spacing first makes the shape depend on
  /// how the entities sit relative to each other rather than on how many of
  /// them there are.
  ///
  /// At this multiple, a group's members merge into one island while the gap
  /// to the next group stays water.
  static let reachInNeighbourGaps = 2.5

  /// Bounds on the measured spacing, for the degenerate maps where it is not a
  /// useful number: a handful of entities piled on one spot, or two entities on
  /// opposite corners.
  private static let reachRange = 0.006...0.2

  /// Influence a patch needs before it is land at all.
  ///
  /// Above one deliberately, because one entity's influence peaks at exactly
  /// one: past this line no single entity can mint a territory of its own, and
  /// being somewhere takes company. Set below it, eight entities scattered
  /// across the map produced eight separate islands, each a ring drawn around
  /// a dot that was already visible.
  ///
  /// Costs nothing on real groups. A dozen entities sitting within a `reach`
  /// of each other pile up an influence well over ten, so this only ever trims
  /// the thin tail at the coast — every one of the thirty groups on a
  /// 1,100-entity fixture keeps its island unchanged from a sea level a third
  /// as high.
  static let seaLevel = 1.1

  /// How far ahead the winner has to be before the ground is really theirs.
  ///
  /// Owning a patch of canvas by a hair is not owning it. Where two
  /// neighbourhoods are about equally present — which is most of what lies
  /// between two interleaved groups — declaring a winner would draw a hard
  /// border through genuinely mixed ground and state something the data does
  /// not support. Below this margin the patch stays water, so contested
  /// ground reads as the strait it is.
  static let decisiveMargin = 1.25

  /// The smallest island worth drawing, as a share of the whole field.
  ///
  /// A stray member far from its group would otherwise mint a speck of its
  /// territory where it stands. Two entities' worth of land is a place; one
  /// entity's worth is a dot that already has a dot.
  static let smallestIsland = 0.0008

  /// Margin around the unit square, so a group at the edge of the map still
  /// has water to have a coastline in. Without it a contour runs off the side
  /// of the field and never closes.
  private static let margin = 0.08

  /// A closed ring of a territory's coast, in normalized map coordinates.
  typealias Ring = [CGPoint]

  /// Coastlines for each neighbourhood, keyed the same way the input is.
  ///
  /// Every neighbourhood competing for territory must be passed in, including
  /// ones the map will not name: an unnamed group still holds the ground it
  /// sits on, and leaving it out would hand its land to whichever named
  /// neighbourhood happens to be nearest.
  static func coastlines(members: [Int: [CGPoint]]) -> [Int: [Ring]] {
    let groups = members.keys.sorted()
    guard !groups.isEmpty else { return [:] }

    let cells = resolution * resolution
    var best = [Double](repeating: 0, count: cells)
    var runnerUp = [Double](repeating: 0, count: cells)
    // Sorted iteration plus a strict `>` means the lowest group id wins a tie,
    // so the same input always yields the same map.
    var owner = [Int32](repeating: -1, count: cells)
    var field = [Double](repeating: 0, count: cells)

    let stencil = stencil(reach: reach(of: groups.compactMap { members[$0] }.flatMap { $0 }))
    for group in groups {
      guard let points = members[group], !points.isEmpty else { continue }
      // Only the cells this group touched need clearing, which is what keeps
      // one scratch buffer cheaper than one buffer per group.
      var touched: [Int] = []
      for point in points {
        splat(point, into: &field, touched: &touched, stencil: stencil)
      }
      for index in touched {
        let value = field[index]
        if value > best[index] {
          runnerUp[index] = best[index]
          best[index] = value
          owner[index] = Int32(group)
        } else if value > runnerUp[index] {
          runnerUp[index] = value
        }
      }
      for index in touched { field[index] = 0 }
    }

    var result: [Int: [Ring]] = [:]
    let floor = smallestIsland * Double(cells)
    for group in groups {
      // Softened before tracing, so the coast curves the way a shoreline does
      // instead of stepping along the cells that produced it.
      let mask = blurred(
        ownership(of: Int32(group), owner: owner, best: best, runnerUp: runnerUp))
      let rings = trace(mask)
        .filter { abs(area(of: $0)) >= floor }
        .map { $0.map(normalize) }
      if !rings.isEmpty { result[group] = rings }
    }
    return result
  }

  // MARK: - Field

  /// Influence values for one entity, over the block of cells it can reach.
  ///
  /// Precomputed once and reused for every entity, which turns the field from
  /// a million calls to `exp` into a million additions. It costs snapping each
  /// entity to its nearest cell: at this resolution that moves it by at most
  /// an eighth of `reach`, well under the width of the coastline it produces.
  /// How far apart the entities on this map typically sit: the median distance
  /// from one to its nearest neighbour, times `reachInNeighbourGaps`.
  ///
  /// The median rather than the mean, because a graph layout always leaves a
  /// few entities stranded a long way out and their gaps are enormous. Sampled
  /// rather than exhaustive — the median settles long before the thousandth
  /// point, and every pair would be a million distances for a number that only
  /// needs to be right to within a factor of two.
  private static func reach(of points: [CGPoint]) -> Double {
    guard points.count > 1 else { return reachRange.upperBound }
    let stride = max(1, points.count / 300)
    var gaps: [Double] = []
    for index in Swift.stride(from: 0, to: points.count, by: stride) {
      var nearest = Double.infinity
      for other in points where other != points[index] {
        nearest = min(
          nearest, hypot(Double(points[index].x - other.x), Double(points[index].y - other.y)))
      }
      if nearest.isFinite { gaps.append(nearest) }
    }
    guard !gaps.isEmpty else { return reachRange.upperBound }
    gaps.sort()
    let typical = gaps[gaps.count / 2] * reachInNeighbourGaps
    return min(max(typical, reachRange.lowerBound), reachRange.upperBound)
  }

  private static func stencil(reach: Double) -> (radius: Int, values: [Double]) {
    let scale = Double(resolution - 1) / (1 + 2 * margin)
    let radius = max(1, Int((3 * reach * scale).rounded()))
    let span = radius * 2 + 1
    var values = [Double](repeating: 0, count: span * span)
    for row in 0..<span {
      for column in 0..<span {
        let dy = Double(row - radius) / scale
        let dx = Double(column - radius) / scale
        values[row * span + column] = exp(-(dx * dx + dy * dy) / (2 * reach * reach))
      }
    }
    return (radius, values)
  }

  private static func splat(
    _ point: CGPoint, into field: inout [Double], touched: inout [Int],
    stencil: (radius: Int, values: [Double])
  ) {
    let scale = Double(resolution - 1) / (1 + 2 * margin)
    let centerColumn = Int(((Double(point.x) + margin) * scale).rounded())
    let centerRow = Int(((Double(point.y) + margin) * scale).rounded())
    let radius = stencil.radius
    let span = radius * 2 + 1

    for row in max(0, centerRow - radius)...min(resolution - 1, centerRow + radius) {
      guard centerRow - radius <= resolution - 1, centerRow + radius >= 0 else { return }
      for column in max(0, centerColumn - radius)...min(resolution - 1, centerColumn + radius) {
        let index = row * resolution + column
        if field[index] == 0 { touched.append(index) }
        field[index] +=
          stencil.values[(row - centerRow + radius) * span + (column - centerColumn + radius)]
      }
    }
  }

  private static func ownership(
    of group: Int32, owner: [Int32], best: [Double], runnerUp: [Double]
  ) -> [Double] {
    var mask = [Double](repeating: 0, count: owner.count)
    for index in 0..<owner.count
    where owner[index] == group
      && best[index] >= seaLevel
      && best[index] >= runnerUp[index] * decisiveMargin
    {
      mask[index] = 1
    }
    return mask
  }

  /// A separable three-tap blur. Enough to round the cell steps off a coast
  /// without dissolving the lobes that make one territory recognisable.
  private static func blurred(_ mask: [Double]) -> [Double] {
    var pass = mask
    var out = mask
    for row in 0..<resolution {
      for column in 0..<resolution {
        let index = row * resolution + column
        let left = column > 0 ? mask[index - 1] : 0
        let right = column < resolution - 1 ? mask[index + 1] : 0
        pass[index] = (left + 2 * mask[index] + right) / 4
      }
    }
    for row in 0..<resolution {
      for column in 0..<resolution {
        let index = row * resolution + column
        let up = row > 0 ? pass[index - resolution] : 0
        let down = row < resolution - 1 ? pass[index + resolution] : 0
        out[index] = (up + 2 * pass[index] + down) / 4
      }
    }
    return out
  }

  // MARK: - Tracing

  /// Where the coast crosses one edge of the grid, identified rather than
  /// positioned.
  ///
  /// Two neighbouring cells compute the same crossing from the same pair of
  /// values, so naming the edge lets the rings be stitched with integer
  /// equality. Matching on the coordinates instead would work right up until a
  /// rounding difference left a ring with an invisible gap in it.
  private static func horizontal(_ row: Int, _ column: Int) -> Int { row * resolution + column }
  private static func vertical(_ row: Int, _ column: Int) -> Int {
    resolution * resolution + row * resolution + column
  }

  private static func trace(_ mask: [Double]) -> [[CGPoint]] {
    let level = 0.5
    var crossings: [Int: CGPoint] = [:]
    var links: [Int: [Int]] = [:]

    func cross(_ a: Double, _ b: Double) -> Double { (level - a) / (b - a) }
    func connect(_ first: Int, _ second: Int) {
      links[first, default: []].append(second)
      links[second, default: []].append(first)
    }

    for row in 0..<(resolution - 1) {
      for column in 0..<(resolution - 1) {
        let bottomLeft = mask[row * resolution + column]
        let bottomRight = mask[row * resolution + column + 1]
        let topRight = mask[(row + 1) * resolution + column + 1]
        let topLeft = mask[(row + 1) * resolution + column]

        var code = 0
        if bottomLeft >= level { code |= 1 }
        if bottomRight >= level { code |= 2 }
        if topRight >= level { code |= 4 }
        if topLeft >= level { code |= 8 }
        guard code != 0, code != 15 else { continue }

        let bottom = horizontal(row, column)
        let top = horizontal(row + 1, column)
        let left = vertical(row, column)
        let right = vertical(row, column + 1)
        crossings[bottom] = CGPoint(
          x: Double(column) + cross(bottomLeft, bottomRight), y: Double(row))
        crossings[top] = CGPoint(x: Double(column) + cross(topLeft, topRight), y: Double(row + 1))
        crossings[left] = CGPoint(x: Double(column), y: Double(row) + cross(bottomLeft, topLeft))
        crossings[right] = CGPoint(
          x: Double(column + 1), y: Double(row) + cross(bottomRight, topRight))

        switch code {
        case 1, 14: connect(left, bottom)
        case 2, 13: connect(bottom, right)
        case 3, 12: connect(left, right)
        case 4, 11: connect(right, top)
        case 6, 9: connect(bottom, top)
        case 7, 8: connect(left, top)
        // The two ambiguous cells, where opposite corners are land and the
        // other two are water. The average of the four says whether the middle
        // is an isthmus joining them or a channel keeping them apart.
        case 5:
          if (bottomLeft + bottomRight + topRight + topLeft) / 4 >= level {
            connect(left, top)
            connect(bottom, right)
          } else {
            connect(left, bottom)
            connect(right, top)
          }
        case 10:
          if (bottomLeft + bottomRight + topRight + topLeft) / 4 >= level {
            connect(left, bottom)
            connect(right, top)
          } else {
            connect(left, top)
            connect(bottom, right)
          }
        default: break
        }
      }
    }

    var rings: [[CGPoint]] = []
    var visited = Set<Int>()
    for start in links.keys.sorted() where !visited.contains(start) {
      var ring: [CGPoint] = []
      var current = start
      var previous = -1
      while !visited.contains(current) {
        visited.insert(current)
        if let point = crossings[current] { ring.append(point) }
        guard let next = links[current]?.first(where: { $0 != previous && !visited.contains($0) })
        else { break }
        previous = current
        current = next
      }
      if ring.count >= 4 { rings.append(ring) }
    }
    return rings
  }

  private static func area(of ring: [CGPoint]) -> Double {
    guard ring.count >= 3 else { return 0 }
    var total = 0.0
    for index in 0..<ring.count {
      let a = ring[index]
      let b = ring[(index + 1) % ring.count]
      total += Double(a.x * b.y - b.x * a.y)
    }
    return total / 2
  }

  /// Grid cell back to the normalized map coordinates the caller works in.
  private static func normalize(_ point: CGPoint) -> CGPoint {
    let scale = Double(resolution - 1) / (1 + 2 * margin)
    return CGPoint(x: Double(point.x) / scale - margin, y: Double(point.y) / scale - margin)
  }
}
