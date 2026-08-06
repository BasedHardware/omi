import CoreGraphics
import XCTest

@testable import Omi_Computer

final class MemoryAtlasCatalogLayoutTests: XCTestCase {
  private let unitArea = CGRect(x: 0, y: 0, width: 1, height: 1)

  func testPositionsAreDeterministicWhenCatalogAndAssertionInputsAreReversed() {
    let catalog = [
      KnowledgeGraphNode(id: "memory:alpha", label: "Alpha", nodeType: .concept, memoryIds: ["shared"]),
      KnowledgeGraphNode(id: "memory:beta", label: "Beta", nodeType: .concept, memoryIds: ["beta"]),
      KnowledgeGraphNode(id: "memory:orphan", label: "Orphan", nodeType: .concept),
    ]
    let assertions = [
      KnowledgeGraphNode(id: "assertion-a", label: "A", nodeType: .concept, memoryIds: ["shared"]),
      KnowledgeGraphNode(id: "assertion-b", label: "B", nodeType: .concept, memoryIds: ["beta"]),
    ]
    let assertionPositions = [
      "assertion-a": CGPoint(x: 0.35, y: 0.4),
      "assertion-b": CGPoint(x: 0.65, y: 0.6),
    ]
    let communities = ["assertion-a": 1, "assertion-b": 1]

    let first = MemoryAtlasCatalogLayout.positions(
      catalog: catalog, assertions: assertions, communities: communities,
      assertionPositions: assertionPositions, ownerID: nil, area: unitArea)
    let reversed = MemoryAtlasCatalogLayout.positions(
      catalog: Array(catalog.reversed()), assertions: Array(assertions.reversed()), communities: communities,
      assertionPositions: assertionPositions, ownerID: nil, area: unitArea)

    XCTAssertEqual(Set(first.keys), Set(reversed.keys))
    for id in first.keys { XCTAssertEqual(first[id], reversed[id], "Position changed for \(id)") }
  }

  func testExactEvidenceKeepsCatalogMarkNearAssertionAndUnmatchedMarkValid() throws {
    let assertion = KnowledgeGraphNode(
      id: "assertion", label: "Assertion", nodeType: .concept, memoryIds: ["evidence-1"])
    let catalog = [
      KnowledgeGraphNode(id: "memory:matched", label: "Matched", nodeType: .concept, memoryIds: ["evidence-1"]),
      KnowledgeGraphNode(id: "memory:unmatched", label: "Unmatched", nodeType: .concept),
    ]
    let assertionPosition = CGPoint(x: 0.5, y: 0.5)
    let positions = MemoryAtlasCatalogLayout.positions(
      catalog: catalog, assertions: [assertion], communities: [:],
      assertionPositions: [assertion.id: assertionPosition], ownerID: nil, area: unitArea)

    let matchedPosition = try XCTUnwrap(positions["memory:matched"])
    let unmatchedPosition = try XCTUnwrap(positions["memory:unmatched"])
    XCTAssertLessThan(hypot(matchedPosition.x - assertionPosition.x, matchedPosition.y - assertionPosition.y), 0.1)
    XCTAssertTrue(isInsideCircularSafeArea(unmatchedPosition, in: unitArea))
  }

  func testWideAreaKeepsCatalogMarksInsideCircularSafeAreaInsteadOfRectangularCorners() {
    let wideArea = CGRect(x: 0, y: 0, width: 2, height: 1)
    let catalog = (0..<8).map {
      KnowledgeGraphNode(id: "memory:\($0)", label: "Memory \($0)", nodeType: .concept)
    }
    let positions = MemoryAtlasCatalogLayout.positions(
      catalog: catalog, assertions: [], communities: [:], assertionPositions: [:], ownerID: nil, area: wideArea)

    XCTAssertEqual(positions.count, catalog.count)
    for (id, position) in positions {
      XCTAssertTrue(isInsideCircularSafeArea(position, in: wideArea), "\(id) escaped the circular safe area")
    }
  }

  func testMatchedCatalogMarksSettleAwayFromTheirAssertion() throws {
    let assertion = KnowledgeGraphNode(id: "assertion", label: "Assertion", nodeType: .concept, memoryIds: ["shared"])
    let catalog = (0..<4).map {
      KnowledgeGraphNode(id: "memory:\($0)", label: "Record \($0)", nodeType: .concept, memoryIds: ["shared"])
    }
    let assertionPosition = CGPoint(x: 0.5, y: 0.5)
    let positions = MemoryAtlasCatalogLayout.positions(
      catalog: catalog, assertions: [assertion], communities: [:],
      assertionPositions: [assertion.id: assertionPosition], ownerID: nil, area: unitArea)

    XCTAssertEqual(Set(positions.keys), Set(catalog.map(\.id)))
    for position in positions.values {
      XCTAssertGreaterThan(hypot(position.x - assertionPosition.x, position.y - assertionPosition.y), 0.004)
    }
  }

  private func isInsideCircularSafeArea(_ point: CGPoint, in area: CGRect) -> Bool {
    hypot(point.x - area.midX, point.y - area.midY) <= min(area.width, area.height) / 2 + 0.000_001
  }
}
