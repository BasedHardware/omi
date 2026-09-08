import CoreGraphics
import XCTest

@testable import Omi_Computer

/// Connections are things you can click, not captions. These cover the two
/// halves of that: picking a painted line out of the canvas, and following a
/// listed connection to the entity on its other end.
final class MemoryAtlasConnectionSelectionTests: XCTestCase {

  // MARK: Picking a line off the canvas

  func testClickOnAConnectionPicksIt() {
    let segments = [
      MemoryAtlasHitTesting.Segment(
        id: "a-b", start: CGPoint(x: 0, y: 0), end: CGPoint(x: 100, y: 0))
    ]

    XCTAssertEqual(
      MemoryAtlasHitTesting.nearestSegment(
        to: CGPoint(x: 50, y: 2), among: segments,
        within: MemoryAtlasHitTesting.connectionTolerance),
      "a-b"
    )
  }

  func testClickAwayFromEveryConnectionPicksNothing() {
    let segments = [
      MemoryAtlasHitTesting.Segment(
        id: "a-b", start: CGPoint(x: 0, y: 0), end: CGPoint(x: 100, y: 0))
    ]

    // Empty canvas clicks must stay inert; a generous tolerance would make the
    // map select a relationship every time the user tried to pan.
    XCTAssertNil(
      MemoryAtlasHitTesting.nearestSegment(
        to: CGPoint(x: 50, y: 40), among: segments,
        within: MemoryAtlasHitTesting.connectionTolerance)
    )
  }

  /// A click past a segment's end is off that connection, even though it is
  /// still on the infinite line the segment lies along.
  func testClickBeyondAConnectionEndpointIsNotOnIt() {
    let segments = [
      MemoryAtlasHitTesting.Segment(
        id: "a-b", start: CGPoint(x: 0, y: 0), end: CGPoint(x: 100, y: 0))
    ]

    XCTAssertNil(
      MemoryAtlasHitTesting.nearestSegment(
        to: CGPoint(x: 140, y: 0), among: segments,
        within: MemoryAtlasHitTesting.connectionTolerance)
    )
  }

  func testNearestConnectionWinsWhenSeveralAreInRange() {
    let segments = [
      MemoryAtlasHitTesting.Segment(
        id: "far", start: CGPoint(x: 0, y: 4), end: CGPoint(x: 100, y: 4)),
      MemoryAtlasHitTesting.Segment(
        id: "near", start: CGPoint(x: 0, y: 0), end: CGPoint(x: 100, y: 0)),
    ]

    XCTAssertEqual(
      MemoryAtlasHitTesting.nearestSegment(
        to: CGPoint(x: 50, y: 1), among: segments,
        within: MemoryAtlasHitTesting.connectionTolerance),
      "near"
    )
  }

  func testZeroLengthConnectionIsMeasuredAsAPoint() {
    let segments = [
      MemoryAtlasHitTesting.Segment(
        id: "degenerate", start: CGPoint(x: 10, y: 10), end: CGPoint(x: 10, y: 10))
    ]

    // Two entities can land on the same normalized position; the projection
    // maths divides by segment length, so this must not produce NaN and swallow
    // every click on the canvas.
    XCTAssertEqual(
      MemoryAtlasHitTesting.nearestSegment(
        to: CGPoint(x: 11, y: 10), among: segments,
        within: MemoryAtlasHitTesting.connectionTolerance),
      "degenerate"
    )
    XCTAssertNil(
      MemoryAtlasHitTesting.nearestSegment(
        to: CGPoint(x: 60, y: 10), among: segments,
        within: MemoryAtlasHitTesting.connectionTolerance)
    )
  }

  /// Every entity sits on at least one connection, so a line whose pick radius
  /// reached as far as a dot's would make dots feel unclickable exactly where
  /// they matter. The node hit radius floors at 12pt.
  func testConnectionToleranceStaysInsideTheEntityHitRadius() {
    XCTAssertLessThan(MemoryAtlasHitTesting.connectionTolerance, 12)
  }

  // MARK: Following a listed connection

  func testConnectionRowCarriesTheEntityOnItsOtherEnd() {
    let row = MemoryAtlasRelationshipRow(
      id: "edge-1",
      otherNodeID: "node-telegram",
      otherLabel: "Telegram",
      relationship: "shows conversation with",
      accent: .white
    )

    // Without the destination the inspector could name the far end but not
    // open it, which is what made connections read as captions.
    XCTAssertEqual(row.otherNodeID, "node-telegram")
  }

  func testInspectorSubjectDescribesEntitiesAndRelationshipsDistinctly() {
    let entity = MemoryAtlasInspectorSubject.entity(
      title: "Nik Shevchenko", typeName: "People", connectionSummary: "6 connections")
    XCTAssertEqual(entity.title, "Nik Shevchenko")
    XCTAssertEqual(entity.subtitle, "People · 6 connections")
    XCTAssertEqual(entity.relatedSectionTitle, "Connections")

    let relationship = MemoryAtlasInspectorSubject.relationship(
      sourceLabel: "Nik Shevchenko", targetLabel: "Telegram", verb: "shows conversation with")
    XCTAssertEqual(relationship.title, "Nik Shevchenko → Telegram")
    XCTAssertEqual(relationship.subtitle, "shows conversation with")
    XCTAssertEqual(relationship.relatedSectionTitle, "Between")
  }

  // MARK: Static checkers

  func testStaticCheckerCanvasTapRoutesThroughTheElementPicker() throws {
    // STATIC CHECKER. The tap handler is private to a SwiftUI view, so the
    // ordering rule — entities tested before connections — cannot be reached
    // behaviorally without a window. The geometry itself is covered above.
    let source = try atlasSource()
    guard let picker = source.range(of: "private func selectAtlasElement(") else {
      return XCTFail("The canvas tap must route through selectAtlasElement")
    }
    let body = String(source[picker.lowerBound...].prefix(1400))

    guard
      let nodeProbe = body.range(of: "nearestNode(to: location"),
      let edgeProbe = body.range(of: "MemoryAtlasHitTesting.nearestSegment(")
    else {
      return XCTFail("selectAtlasElement must test entities and connections")
    }
    XCTAssertLessThan(
      nodeProbe.lowerBound, edgeProbe.lowerBound,
      "Entities must be tested before connections, or dots become unclickable")

    XCTAssertTrue(
      source.contains("SpatialTapGesture().onEnded { value in")
        && source.contains("selectAtlasElement(at: value.location"),
      "The canvas tap gesture must use the element picker, not a node-only one")
  }

  func testStaticCheckerEvidenceLoadClearsStaleResultsBeforeReading() throws {
    // STATIC CHECKER. The inspector's evidence lives in view state that only a
    // rendered window drives. Showing the previous entity's memories under the
    // new entity's name is a correctness bug, not a cosmetic one.
    let source = try atlasSource()
    guard let load = source.range(of: "private func loadEvidence() async {") else {
      return XCTFail("The inspector must resolve evidence through loadEvidence()")
    }
    let body = String(source[load.lowerBound...].prefix(900))

    guard
      let clear = body.range(of: "evidence = []\n    requestedEvidenceIDs = ids"),
      let read = body.range(of: "await evidenceProvider(ids)")
    else {
      return XCTFail("loadEvidence must clear stale evidence before reading")
    }
    XCTAssertLessThan(clear.lowerBound, read.lowerBound)
    XCTAssertTrue(
      body.contains("guard !Task.isCancelled else { return }"),
      "A superseded lookup must not overwrite the current selection's evidence")
  }

  func testStaticCheckerFollowingAConnectionIsReversible() throws {
    // STATIC CHECKER. The trail is SwiftUI view state driven by taps. The rule
    // it encodes: only following a listed connection extends the trail, and
    // every other way of selecting starts a fresh one — otherwise "back" walks
    // through entities the user reached by clicking the canvas, which is not
    // where they were.
    let source = try atlasSource()

    guard let open = source.range(of: "private func openRelated(") else {
      return XCTFail("Connections must be followed through one entry point")
    }
    let openBody = String(source[open.lowerBound...].prefix(400))
    XCTAssertTrue(
      openBody.contains("selectionTrail.append(current)"),
      "Following a connection must remember where it came from")

    guard let back = source.range(of: "private func goBack() {") else {
      return XCTFail("The inspector must offer a way back")
    }
    XCTAssertTrue(
      String(source[back.lowerBound...].prefix(300)).contains("selectionTrail.popLast()"))

    guard let picker = source.range(of: "private func selectAtlasElement(") else {
      return XCTFail("The canvas tap must route through selectAtlasElement")
    }
    XCTAssertTrue(
      String(source[picker.lowerBound...].prefix(1600)).contains("selectionTrail.removeAll()"),
      "Reaching for something on the canvas must start a fresh trail")
    XCTAssertTrue(
      String(source[picker.lowerBound...].prefix(1600)).contains("adoptSelection("),
      "Selecting an entity must reuse the Focus camera so the neighbourhood is framed")

    guard let clear = source.range(of: "private func clearSelection(") else {
      return XCTFail("Clearing the selection must be one entry point")
    }
    XCTAssertTrue(
      String(source[clear.lowerBound...].prefix(400)).contains("selectionTrail.removeAll()"),
      "Closing the inspector must not leave a trail behind for the next selection")
    XCTAssertTrue(
      String(source[clear.lowerBound...].prefix(400)).contains(
        "resetViewport(preservingNeighbourhood: true)"),
      "Homed camera after clearing a selection must keep the neighbourhood layer for the next Escape")
  }

  private func atlasSource() throws -> String {
    let url = URL(fileURLWithPath: #filePath)
      .deletingLastPathComponent()
      .deletingLastPathComponent()
      .appendingPathComponent(
        "Sources/MainWindow/Pages/MemoryGraph/CanonicalMemoryAtlasView.swift")
    // omi-test-quality: source-inspection -- static contract: the atlas inspector is a SwiftUI view that only exists inside a rendered window, so its wiring has no runnable seam; these cases are labelled STATIC CHECKER and assert structure, not behaviour.
    return try String(contentsOf: url, encoding: .utf8)
  }
}
