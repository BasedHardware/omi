import XCTest

@testable import Omi_Computer

final class MemoryAtlasPlaybackTests: XCTestCase {
  func testReplayDurationIsFourSecondsOnceThereAreMoreThanAFewEntities() {
    XCTAssertEqual(MemoryAtlasPlayback.duration(entityCount: 4), 2)
    XCTAssertEqual(MemoryAtlasPlayback.duration(entityCount: 12), 2)
    XCTAssertEqual(MemoryAtlasPlayback.duration(entityCount: 13), 4)
    XCTAssertEqual(MemoryAtlasPlayback.duration(entityCount: 1_200), 4)
  }

  func testEpochPlaceholdersDoNotOwnTheTimelineStart() throws {
    let real = Date(timeIntervalSince1970: 1_700_000_000)
    let graph = KnowledgeGraphResponse(
      nodes: [
        KnowledgeGraphNode(
          id: "missing-stamp", label: "Imported", nodeType: .concept,
          createdAt: Date(timeIntervalSince1970: 0)),
        KnowledgeGraphNode(id: "david", label: "David", nodeType: .person, createdAt: real),
        KnowledgeGraphNode(
          id: "later", label: "Later", nodeType: .thing, createdAt: real.addingTimeInterval(86_400)),
      ],
      edges: []
    )

    let timeline = try XCTUnwrap(
      MemoryAtlasLayoutEngine.makeSnapshot(graph: graph, userName: "David").timeline)

    XCTAssertEqual(timeline.start, real)
    XCTAssertGreaterThan(timeline.start, MemoryAtlasPlayback.earliestCredibleDate)
    XCTAssertEqual(timeline.date(atFraction: 0), real)
  }

  func testAllUnknownTimestampsDoNotBecomeToday() {
    let epoch = Date(timeIntervalSince1970: 0)
    let laterEpoch = epoch.addingTimeInterval(1)
    let dates = MemoryAtlasPlayback.effectiveDates(from: [epoch, laterEpoch])
    XCTAssertEqual(dates, [epoch, epoch])
    XCTAssertFalse(dates.contains { MemoryAtlasPlayback.isCredible($0) })
    XCTAssertLessThan(dates[0].timeIntervalSince1970, 1_000)
  }

  func testAYearOfSilenceOccupiesLittleReplayTime() throws {
    let base = Date(timeIntervalSince1970: 1_700_000_000)
    let graph = KnowledgeGraphResponse(
      nodes: [
        KnowledgeGraphNode(id: "early", label: "Early", nodeType: .person, createdAt: base),
        KnowledgeGraphNode(
          id: "late-a", label: "Late A", nodeType: .concept,
          createdAt: base.addingTimeInterval(365 * 86_400)),
        KnowledgeGraphNode(
          id: "late-b", label: "Late B", nodeType: .concept,
          createdAt: base.addingTimeInterval(365 * 86_400 + 3_600)),
      ],
      edges: []
    )

    let timeline = try XCTUnwrap(
      MemoryAtlasLayoutEngine.makeSnapshot(graph: graph, userName: nil).timeline)
    let early = try XCTUnwrap(timeline.entries.first { $0.nodeID == "early" })
    let lateA = try XCTUnwrap(timeline.entries.first { $0.nodeID == "late-a" })

    XCTAssertLessThan(
      lateA.playbackFraction - early.playbackFraction,
      0.65,
      "A silent year must not consume most of the replay")
    XCTAssertGreaterThan(
      lateA.playbackFraction - early.playbackFraction,
      0.05,
      "The later cluster should still arrive after the earlier one")
  }

  func testStaticCheckerAtlasEscapeJoinsTheWindowMonitorAtContentPriority() throws {
    let testsDirectory = URL(fileURLWithPath: #filePath).deletingLastPathComponent()
    let sourceURL =
      testsDirectory
      .deletingLastPathComponent()
      .appendingPathComponent("Sources/MainWindow/Pages/MemoryGraph/CanonicalMemoryAtlasView.swift")
    // omi-test-quality: source-inspection -- static contract: atlas Escape must register on WindowEscapeKeyMonitor at content priority so Chat-first navigation cannot leave Brain Map before a selection is cleared; the competing local monitor is the defect this wiring prevents.
    let source = try String(contentsOf: sourceURL, encoding: .utf8)

    XCTAssertTrue(
      source.contains(".onEscapeKey(priority: .content)"),
      "Brain Map Escape must run at content priority, ahead of leaving the page")
    XCTAssertFalse(
      source.contains("event.keyCode == 53"),
      "A racing AppKit Escape monitor is what used to exit Brain Map while a node was selected")
    XCTAssertTrue(
      source.contains("MemoryAtlasPlayback.duration(entityCount:"),
      "Replay duration must come from the shared four-second policy")
  }

  func testCompressedOffsetsCapCalendarGaps() {
    let base = Date(timeIntervalSince1970: 1_700_000_000)
    let dates = [
      base,
      base.addingTimeInterval(60),
      base.addingTimeInterval(365 * 86_400),
    ]
    let offsets = MemoryAtlasPlayback.compressedOffsets(for: dates)

    XCTAssertEqual(offsets.count, 3)
    XCTAssertEqual(offsets[0], 0)
    XCTAssertEqual(offsets[1], 60)
    XCTAssertEqual(offsets[2], 60 + MemoryAtlasPlayback.maxUncompressedGap)
  }
}

final class MemoryAtlasCameraTests: XCTestCase {
  func testALoneNodeKeepsTheCrosshairFocusZoom() {
    let camera = MemoryAtlasZoomPolicy.focusedNeighborhood(
      positions: [CGPoint(x: 0.7, y: 0.3)],
      viewport: CGSize(width: 900, height: 700),
      currentZoom: 1,
      zoomRange: MemoryAtlasZoomPolicy.minimumZoom...16
    )

    XCTAssertEqual(camera.zoom, MemoryAtlasZoomPolicy.focusTargetZoom)
    XCTAssertNotEqual(camera.pan, .zero)
  }

  func testConnectedNodesStayInsideTheFramedViewport() {
    let positions = [
      CGPoint(x: 0.45, y: 0.48),
      CGPoint(x: 0.55, y: 0.52),
      CGPoint(x: 0.50, y: 0.44),
    ]
    let viewport = CGSize(width: 900, height: 700)
    let camera = MemoryAtlasZoomPolicy.focusedNeighborhood(
      positions: positions,
      viewport: viewport,
      currentZoom: 1,
      zoomRange: MemoryAtlasZoomPolicy.minimumZoom...16
    )

    XCTAssertGreaterThan(camera.zoom, 1)
    for position in positions {
      let point = MemoryAtlasRenderPlanner.renderedPoint(
        for: position, viewportSize: viewport, zoom: camera.zoom, pan: camera.pan)
      XCTAssertTrue(
        (0...viewport.width).contains(point.x) && (0...viewport.height).contains(point.y),
        "A highlighted neighbour must remain on screen after focus")
    }
  }
}

final class MemoryAtlasSurfacePresentationTests: XCTestCase {
  func testFirstVisitShowsALoaderInsteadOfAnEmptyMap() {
    XCTAssertEqual(
      MemoryAtlasSurfacePresentation.phase(
        isLoading: false, isEmpty: true, hasProjection: false, hasAttemptedLoad: false),
      .loading)
    XCTAssertEqual(
      MemoryAtlasSurfacePresentation.phase(
        isLoading: true, isEmpty: true, hasProjection: false, hasAttemptedLoad: false),
      .loading)
  }

  func testAResolvedEmptyGraphIsEmptyNotLoading() {
    XCTAssertEqual(
      MemoryAtlasSurfacePresentation.phase(
        isLoading: false, isEmpty: true, hasProjection: false, hasAttemptedLoad: true),
      .empty)
  }

  func testALoadedProjectionIsReadyEvenIfARefreshIsInFlight() {
    XCTAssertEqual(
      MemoryAtlasSurfacePresentation.phase(
        isLoading: true, isEmpty: false, hasProjection: true, hasAttemptedLoad: true),
      .ready)
  }

  func testASyntheticOwnerProjectionIsNotReady() {
    XCTAssertEqual(
      MemoryAtlasSurfacePresentation.phase(
        isLoading: false, isEmpty: true, hasProjection: true, hasAttemptedLoad: true),
      .empty)
  }
}
