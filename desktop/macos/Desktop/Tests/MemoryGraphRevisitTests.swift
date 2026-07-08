import XCTest

/// Guards the brain-map revisit behavior: the graph view model is
/// session-persistent and page visits must not refetch, re-run the force
/// layout, or rebuild the SceneKit scene unless the graph actually changed.
/// (Regression: every Memories visit used to fetch the full graph, run 800
/// physics ticks, rebuild the scene, and replay a 3s settle animation.)
final class MemoryGraphRevisitTests: XCTestCase {
    func testGraphSurfacesUseInjectedPersistentViewModel() throws {
        let source = try graphSource()

        XCTAssertFalse(
            source.contains("@StateObject private var viewModel = MemoryGraphViewModel()"),
            "Graph surfaces must not own their view model — page-local @StateObject dies on every tab switch and rebuilds the scene per visit"
        )
        XCTAssertTrue(source.contains("@ObservedObject var viewModel: MemoryGraphViewModel"))

        let container = try containerSource()
        XCTAssertTrue(
            container.contains("let memoryGraphViewModel = MemoryGraphViewModel()"),
            "The shared graph view model lives in ViewModelContainer so it survives navigation"
        )
    }

    func testPrepareGraphIsThrottledAndSingleFlight() throws {
        let source = try graphSource()
        let method = try methodBody(named: "prepareGraph", in: source)

        XCTAssertTrue(method.contains("guard !isPreparing else { return }"))
        XCTAssertTrue(method.contains("PollingConfig.shouldAllowActivationRefresh(lastRefresh: lastLoadedAt)"))
        XCTAssertTrue(
            method.contains("if isEmpty && !hasRunEmptyBootstrap {"),
            "The empty-graph rebuild+poll bootstrap must run once per session, not on every visit"
        )
        XCTAssertTrue(
            method.contains("guard await rebuildGraph() else { return }"),
            "A failed rebuild request must not spend the one-shot empty-graph bootstrap latch"
        )
    }

    func testLoadGraphSkipsResimulationForUnchangedGraph() throws {
        let source = try graphSource()
        let method = try methodBody(named: "loadGraph", in: source)

        XCTAssertTrue(method.contains("let signature = Self.graphSignature(of: response)"))
        XCTAssertTrue(
            method.contains("if signature == loadedGraphSignature {"),
            "An unchanged graph must keep the settled scene — no repopulate, no runSync, no camera reset"
        )
        XCTAssertTrue(
            method.contains("let showSpinner = isEmpty"),
            "Freshness checks over a rendered scene must not flash the loading spinner"
        )
    }

    // MARK: - Helpers

    private func graphSource() throws -> String {
        try source(at: "Sources/MainWindow/Pages/MemoryGraph/MemoryGraphPage.swift")
    }

    private func containerSource() throws -> String {
        try source(at: "Sources/ViewModelContainer.swift")
    }

    private func source(at relativePath: String) throws -> String {
        let testsURL = URL(fileURLWithPath: #filePath).deletingLastPathComponent()
        let sourceURL = testsURL
            .deletingLastPathComponent()
            .appendingPathComponent(relativePath)
        return try String(contentsOf: sourceURL, encoding: .utf8)
    }

    private func methodBody(named name: String, in source: String) throws -> String {
        let pattern = #"(?:private )?func \#(name)\([^\)]*\)[^{]*\{([\s\S]*?)\n  \}"#
        let regex = try NSRegularExpression(pattern: pattern)
        let range = NSRange(source.startIndex..<source.endIndex, in: source)
        let match = try XCTUnwrap(regex.firstMatch(in: source, range: range))
        let bodyRange = try XCTUnwrap(Range(match.range(at: 1), in: source))
        return String(source[bodyRange])
    }
}
