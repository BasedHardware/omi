import CoreGraphics
import XCTest

@testable import Omi_Computer

/// The two promises the territory layer makes, and one it deliberately does
/// not.
///
/// Both are things the ellipse this replaced got wrong, so each test is written
/// to fail against a shape fitted to a group's members rather than to the
/// ground they hold.
final class MemoryAtlasIslandsTests: XCTestCase {
  /// A blob of members around a point, tight enough to hold land.
  private func cluster(around center: CGPoint, count: Int = 14, spread: CGFloat = 0.03)
    -> [CGPoint]
  {
    (0..<count).map { index in
      let angle = Double(index) * 2.399_963_229_728_653
      let radius = spread * CGFloat((Double(index) / Double(count)).squareRoot())
      return CGPoint(x: center.x + radius * CGFloat(cos(angle)), y: center.y + radius * CGFloat(sin(angle)))
    }
  }

  /// A group living in two places is two islands, and the water between them
  /// stays water.
  ///
  /// This is the failure the ellipse could not avoid: fitted to the members of
  /// a split group it spans the gulf, and then claims every unrelated entity
  /// standing in it. Drawing two shapes says the true thing — this group is in
  /// two places — where one shape invents a territory nobody lives in.
  func testAGroupThatLivesInTwoPlacesIsDrawnAsTwoPlaces() {
    let split = cluster(around: CGPoint(x: 0.2, y: 0.5)) + cluster(around: CGPoint(x: 0.8, y: 0.5))
    let coastlines = MemoryAtlasIslands.coastlines(members: [0: split])

    let rings = try? XCTUnwrap(coastlines[0])
    XCTAssertEqual(rings?.count, 2, "Two lobes, two islands")
    XCTAssertFalse(
      memoryAtlasCoastlineContains(coastlines[0] ?? [], CGPoint(x: 0.5, y: 0.5)),
      "The gulf between the two lobes is not this group's territory")
    // Each lobe is genuinely covered, or "two islands" would just mean the
    // shape collapsed into speckle.
    XCTAssertTrue(memoryAtlasCoastlineContains(coastlines[0] ?? [], CGPoint(x: 0.2, y: 0.5)))
    XCTAssertTrue(memoryAtlasCoastlineContains(coastlines[0] ?? [], CGPoint(x: 0.8, y: 0.5)))
  }

  /// Two groups sitting in each other's laps get no territory there.
  ///
  /// Ownership by a hair is not ownership. Where the detector splits one dense
  /// patch of the map into two groups whose members are mixed together — the
  /// common case in the middle of a real account — every point in that patch
  /// has both of them equally present, and awarding it to whichever is ahead by
  /// a fraction draws a hard border through ground nobody owns. Leaving it as
  /// water says the true thing: something is here, and it is not one place.
  ///
  /// Two groups merely sitting *next* to each other are a different matter and
  /// deliberately not covered: adjacent blobs do have a real dividing line, and
  /// they share a coast along it.
  func testTwoNeighbourhoodsMixedThroughEachOtherOwnNoneOfThatGround() {
    let blob = cluster(around: CGPoint(x: 0.5, y: 0.5), count: 40, spread: 0.08)
    // Alternating members, so the two groups occupy exactly the same ground.
    let interleaved = [
      0: blob.enumerated().filter { $0.offset.isMultiple(of: 2) }.map(\.element),
      1: blob.enumerated().filter { !$0.offset.isMultiple(of: 2) }.map(\.element),
    ]
    let mixed = MemoryAtlasIslands.coastlines(members: interleaved)

    for probe in [CGPoint(x: 0.5, y: 0.5), CGPoint(x: 0.46, y: 0.52), CGPoint(x: 0.54, y: 0.48)] {
      XCTAssertFalse(memoryAtlasCoastlineContains(mixed[0] ?? [], probe), "\(probe) went to 0")
      XCTAssertFalse(memoryAtlasCoastlineContains(mixed[1] ?? [], probe), "\(probe) went to 1")
    }

    // The same two groups pulled apart do each hold their own ground, so
    // "contested" is a fact about the arrangement and not a way of never
    // drawing anything.
    let apart = MemoryAtlasIslands.coastlines(members: [
      0: cluster(around: CGPoint(x: 0.28, y: 0.5), count: 20, spread: 0.05),
      1: cluster(around: CGPoint(x: 0.72, y: 0.5), count: 20, spread: 0.05),
    ])
    XCTAssertTrue(memoryAtlasCoastlineContains(apart[0] ?? [], CGPoint(x: 0.28, y: 0.5)))
    XCTAssertTrue(memoryAtlasCoastlineContains(apart[1] ?? [], CGPoint(x: 0.72, y: 0.5)))
    XCTAssertFalse(memoryAtlasCoastlineContains(apart[0] ?? [], CGPoint(x: 0.5, y: 0.5)))
    XCTAssertFalse(memoryAtlasCoastlineContains(apart[1] ?? [], CGPoint(x: 0.5, y: 0.5)))
  }

  /// A group whose entities are strewn across the map holds no ground, while a
  /// group of the same size sitting together on the same map does.
  ///
  /// The alternative is a territory per stray entity, which would put a border
  /// around single dots that already have one.
  ///
  /// Both groups have to be on the same map for the question to mean anything.
  /// "Scattered" is not an absolute distance — eight entities evenly spread
  /// over an otherwise empty canvas are as together as anything there is — so
  /// the comparison is against the spacing of the map they are actually on.
  func testEntitiesStrewnAcrossTheMapGetNoTerritoryWhileTheirNeighboursDo() {
    let strewn = (0..<8).map { CGPoint(x: 0.1 + 0.1 * CGFloat($0), y: 0.15 + 0.09 * CGFloat($0)) }
    let together = cluster(around: CGPoint(x: 0.75, y: 0.3), count: 20, spread: 0.04)

    let coastlines = MemoryAtlasIslands.coastlines(members: [0: strewn, 1: together])

    XCTAssertNil(coastlines[0], "Eight entities nowhere near each other are not a place")
    XCTAssertNotNil(coastlines[1], "Twenty entities on top of each other are")
  }

  func testTheSameGroupsAlwaysProduceTheSameCoast() {
    let members = [0: cluster(around: CGPoint(x: 0.35, y: 0.4)), 1: cluster(around: CGPoint(x: 0.7, y: 0.62))]

    let first = MemoryAtlasIslands.coastlines(members: members)
    let second = MemoryAtlasIslands.coastlines(members: members)

    XCTAssertEqual(first.keys.sorted(), second.keys.sorted())
    for group in first.keys {
      XCTAssertEqual(first[group], second[group], "Group \(group) drifted between runs")
    }
  }
}
