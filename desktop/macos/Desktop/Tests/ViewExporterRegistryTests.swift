import XCTest

@testable import Omi_Computer

/// The export registry and its count are declared separately; `runBatch`
/// iterates the count, so a count past the registry spawns failing
/// "unknown-N" exports and a count short of it silently skips renders.
final class ViewExporterRegistryTests: XCTestCase {
  @MainActor
  func testStandaloneViewCountMatchesTheRegistry() {
    let count = ViewExporter.standaloneViewCount
    XCTAssertNotNil(ViewExporter.standaloneViewAt(count - 1), "the last index the batch visits is a real render")
    XCTAssertNil(ViewExporter.standaloneViewAt(count), "the batch stops exactly where the registry ends")
    XCTAssertEqual(ViewExporter.standaloneViewAt(count - 1)?.0, "20-brain-map-building")
  }
}
