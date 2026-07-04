import XCTest

@testable import Omi_Computer

final class SessionIdentityForbiddenIdentifiersTests: XCTestCase {
  private let protocolLayerFiles: Set<String> = [
    "Desktop/Sources/Chat/AgentBridge.swift",
    "Desktop/Sources/Chat/AgentRuntimeProcess.swift",
    "Desktop/Sources/Chat/AgentClient.swift",
    "Desktop/Sources/Chat/AgentArtifactProjection.swift",
    "Desktop/Sources/Chat/ChatResource.swift",
    "Desktop/Sources/Chat/AgentControlService.swift",
    "Desktop/Sources/Chat/DesktopCoordinatorService.swift",
  ]

  private let forbiddenIdentifiers = [
    "sessionKey",
    "omiSessionId",
    "legacyClientScope",
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
        for identifier in forbiddenIdentifiers {
          if line.contains(identifier) {
            violations.append("\(relativePath): contains `\(identifier)` — \(trimmed)")
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
      "Desktop/Sources/Chat/AgentClient.swift",
      "Desktop/Sources/Providers/ChatProvider.swift",
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
