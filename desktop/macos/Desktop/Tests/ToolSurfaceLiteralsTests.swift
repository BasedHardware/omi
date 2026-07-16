import Foundation
import XCTest

@testable import Omi_Computer

final class ToolSurfaceLiteralsTests: XCTestCase {
  private let dispatchFiles: Set<String> = [
    "Desktop/Sources/FloatingControlBar/RealtimeHubController.swift"
  ]

  func testToolDispatchLiteralsAreConfinedToGeneratedSurfaces() throws {
    let desktopRoot = URL(fileURLWithPath: #filePath)
      .deletingLastPathComponent()
      .deletingLastPathComponent()
    let sourcesRoot = desktopRoot.appendingPathComponent("Sources")
    let manifestNames = Set(GeneratedSwiftTool.allCases.map(\.rawValue))
      .union(GeneratedToolExecutors.aliasToCanonical.keys)
      .union(GeneratedToolCapabilities.realtimeToolNames)
      .union(["get_local_status", "get_file_scan_results", "start_file_scan", "load_skill"])

    let swiftFiles = try FileManager.default.subpathsOfDirectory(atPath: sourcesRoot.path)
      .filter { $0.hasSuffix(".swift") }
      .map { "Desktop/Sources/\($0)" }

    let pattern = try NSRegularExpression(pattern: #"case\s+\"([a-z][a-z0-9_]{2,})\""#)
    var violations: [String] = []

    for relativePath in swiftFiles where dispatchFiles.contains(relativePath) {
      let text = try String(
        contentsOf: sourcesRoot.appendingPathComponent(String(relativePath.dropFirst("Desktop/Sources/".count))))
      let range = NSRange(text.startIndex..<text.endIndex, in: text)
      for match in pattern.matches(in: text, range: range) {
        guard let nameRange = Range(match.range(at: 1), in: text) else { continue }
        let candidate = String(text[nameRange])
        if manifestNames.contains(candidate) {
          violations.append("\(relativePath): case \"\(candidate)\"")
        }
      }
    }

    XCTAssertTrue(
      violations.isEmpty,
      "Tool dispatch literals must route through generated identifiers:\n" + violations.joined(separator: "\n"))
  }
}
