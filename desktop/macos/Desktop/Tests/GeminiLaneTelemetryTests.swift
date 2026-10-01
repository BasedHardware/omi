import XCTest

@testable import Omi_Computer

final class GeminiLaneTelemetryTests: XCTestCase {

  func testHeaderHelperAppliesBoundedAttributionAndPlatform() throws {
    var request = URLRequest(url: URL(string: "https://api.example.test/v1/proxy/gemini")!)
    request.applyGeminiProxyHeaders(
      lane: .memory, workload: .extraction, authorization: "Bearer tok")

    XCTAssertEqual(request.value(forHTTPHeaderField: "Authorization"), "Bearer tok")
    XCTAssertEqual(request.value(forHTTPHeaderField: "X-Omi-Lane"), "memory")
    XCTAssertEqual(request.value(forHTTPHeaderField: "X-Omi-Workload"), "extraction")
    XCTAssertEqual(request.value(forHTTPHeaderField: "X-App-Platform"), "macos")
  }

  func testHeaderHelperOverwritesStaleAttribution() throws {
    var request = URLRequest(url: URL(string: "https://api.example.test")!)
    request.setValue("bogus", forHTTPHeaderField: "X-Omi-Lane")
    request.applyGeminiProxyHeaders(
      lane: .dictation, workload: .interactive, authorization: "Bearer t")
    XCTAssertEqual(request.value(forHTTPHeaderField: "X-Omi-Lane"), "dictation")
  }

  // omi-test-quality: source-inspection -- static contract: a dropped required
  // lane/workload init parameter can only be caught by the compiler.
  func testGeminiClientRequiresLaneAndWorkload() throws {
    _ = try? GeminiClient(model: "gemini-2.5-flash", lane: .focus, workload: .interactive)
    _ = try? GeminiClient(lane: .liveNotes, workload: .extraction)
  }

  func testAllCasesMatchCanonicalJson() throws {
    let canonical = try String(
      contentsOf: repositoryRoot()
        .appendingPathComponent("backend/config/desktop_gemini_attribution.json"),
      encoding: .utf8)
    let data = try XCTUnwrap(canonical.data(using: .utf8))
    let json = try XCTUnwrap(
      JSONSerialization.jsonObject(with: data) as? [String: Any])
    let lanes = try XCTUnwrap(json["lanes"] as? [String: String])
    let workloads = try XCTUnwrap(json["workloads"] as? [String])

    XCTAssertEqual(GeminiLane.allCases.count, lanes.count)
    for (caseName, wire) in lanes {
      XCTAssertTrue(
        GeminiLane.allCases.contains { $0.rawValue == wire },
        "generated enum is missing a case for canonical lane \(caseName)")
    }
    XCTAssertEqual(
      Set(GeminiLane.allCases.map(\.rawValue)), Set(lanes.values))
    XCTAssertEqual(
      GeminiWorkloadClass.allCases.map(\.rawValue).sorted(), workloads.sorted())
  }

  private func repositoryRoot() -> URL {
    URL(fileURLWithPath: #filePath)
      .deletingLastPathComponent()
      .deletingLastPathComponent()
      .deletingLastPathComponent()
      .deletingLastPathComponent()
      .deletingLastPathComponent()
  }
}
