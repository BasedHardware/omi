import XCTest

final class DesktopAutomationBridgeRouteTests: XCTestCase {
  func testOpenImportRouteIsDiscoverableInCapabilities() throws {
    let source = try bridgeSource()
    let capabilitiesBody = try caseBody(named: "(\"GET\", \"/capabilities\")", in: source)

    XCTAssertTrue(capabilitiesBody.contains("\"POST /open-import\""))
  }

  func testOpenImportDecodeFailuresAreClientErrors() throws {
    let source = try bridgeSource()
    let openImportBody = try caseBody(named: "(\"POST\", \"/open-import\")", in: source)
    let decodeErrorBody = try sourceSlice(
      from: "let payload: DesktopAutomationOpenImportRequest",
      to: "let knownIDs =",
      in: openImportBody
    )

    XCTAssertTrue(decodeErrorBody.contains("JSONDecoder().decode"))
    XCTAssertTrue(decodeErrorBody.contains("statusCode: 400"))
    XCTAssertFalse(decodeErrorBody.contains("statusCode: 500"))
  }

  private func bridgeSource() throws -> String {
    let url = URL(fileURLWithPath: #filePath)
      .deletingLastPathComponent()
      .deletingLastPathComponent()
      .appendingPathComponent("Sources/DesktopAutomationBridge.swift")
    return try String(contentsOf: url, encoding: .utf8)
  }

  private func caseBody(named marker: String, in source: String) throws -> String {
    guard let start = source.range(of: "case \(marker):") else {
      throw XCTSkip("case \(marker) not found")
    }
    let tail = source[start.lowerBound...]
    guard let nextCase = tail.dropFirst().range(of: "\n    case ") else {
      return String(tail)
    }
    return String(tail[..<nextCase.lowerBound])
  }

  private func sourceSlice(from startMarker: String, to endMarker: String, in source: String) throws -> String {
    guard let start = source.range(of: startMarker),
          let end = source[start.upperBound...].range(of: endMarker)
    else {
      throw XCTSkip("source slice markers not found")
    }
    return String(source[start.lowerBound..<end.lowerBound])
  }
}
