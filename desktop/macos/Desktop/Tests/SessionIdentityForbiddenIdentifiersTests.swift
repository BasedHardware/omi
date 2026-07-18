import XCTest

@testable import Omi_Computer

final class SessionIdentityForbiddenIdentifiersTests: XCTestCase {
  // Protocol-layer files that decode wire session ids from the bundled agent runtime.
  private let protocolLayerFiles: Set<String> = [
    "Desktop/Sources/Chat/AgentBridge.swift",  // query result wire decode
    "Desktop/Sources/Chat/AgentRuntimeProcess.swift",  // JSONL transport decode
    "Desktop/Sources/Chat/AgentClient.swift",  // facade over AgentBridge.QueryResult
  ]

  private let forbiddenIdentifiers = [
    "sessionkey",
    "omisessionid",
    "legacyclientscope",
    "resume:",
  ]

  func testForbiddenSessionIdentityIdentifiersAbsentOutsideProtocolLayer() throws {
    let desktopRoot = URL(fileURLWithPath: #filePath)
      .deletingLastPathComponent()
      .deletingLastPathComponent()
    let sourcesRoot = desktopRoot.appendingPathComponent("Sources")

    let swiftFiles = try FileManager.default.subpathsOfDirectory(atPath: sourcesRoot.path)
      .filter { $0.hasSuffix(".swift") }
      .map { "Desktop/Sources/\($0)" }
      .filter { relativePath in
        !relativePath.hasPrefix("Desktop/Sources/Generated/") && !protocolLayerFiles.contains(relativePath)
      }

    var violations: [String] = []
    for relativePath in swiftFiles {
      let fullPath = desktopRoot.appendingPathComponent(String(relativePath.dropFirst("Desktop/".count)))
      let text = try String(contentsOf: fullPath)
      for line in text.components(separatedBy: .newlines) {
        let trimmed = line.trimmingCharacters(in: .whitespaces)
        if trimmed.hasPrefix("//") { continue }
        let lower = line.lowercased()
        for identifier in forbiddenIdentifiers {
          let containsForbiddenIdentifier: Bool
          if identifier == "resume:" {
            containsForbiddenIdentifier =
              lower.contains("resume")
              && lower.range(
                of: #"(?<![a-z0-9_])resume\s*:"#,
                options: .regularExpression
              ) != nil
          } else {
            containsForbiddenIdentifier = lower.contains(identifier)
          }
          if containsForbiddenIdentifier {
            violations.append("\(relativePath): contains forbidden identifier `\(identifier)` — \(trimmed)")
          }
        }
      }
    }

    XCTAssertTrue(
      violations.isEmpty,
      "Forbidden session identity identifiers must stay in the protocol layer:\n" + violations.joined(separator: "\n"))
  }

  func testAgentBridgeConstructionIsConfined() throws {
    let desktopRoot = URL(fileURLWithPath: #filePath)
      .deletingLastPathComponent()
      .deletingLastPathComponent()
    let sourcesRoot = desktopRoot.appendingPathComponent("Sources")

    let allowedConstructors: Set<String> = [
      "Desktop/Sources/Chat/AgentClient.swift"
    ]

    let swiftFiles = try FileManager.default.subpathsOfDirectory(atPath: sourcesRoot.path)
      .filter { $0.hasSuffix(".swift") }
      .map { "Desktop/Sources/\($0)" }

    var violations: [String] = []
    for relativePath in swiftFiles where !allowedConstructors.contains(relativePath) {
      let fullPath = desktopRoot.appendingPathComponent(String(relativePath.dropFirst("Desktop/".count)))
      let text = try String(contentsOf: fullPath)
      if text.contains("AgentBridge(") {
        violations.append(relativePath)
      }
    }

    XCTAssertTrue(
      violations.isEmpty,
      "AgentBridge must only be constructed in AgentClient and ChatProvider:\n" + violations.joined(separator: "\n"))
  }
}
