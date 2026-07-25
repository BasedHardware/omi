import Foundation

enum RealtimeHubControllerSourceTestSupport {
  static func source(named name: String, testFilePath: String = #filePath) throws -> String {
    let floatingControlBar = URL(fileURLWithPath: testFilePath)
      .deletingLastPathComponent()
      .deletingLastPathComponent()
      .appendingPathComponent("Sources/FloatingControlBar")
    return try String(contentsOf: floatingControlBar.appendingPathComponent(name), encoding: .utf8)
  }

  static func moduleSource(testFilePath: String = #filePath) throws -> String {
    let floatingControlBar = URL(fileURLWithPath: testFilePath)
      .deletingLastPathComponent()
      .deletingLastPathComponent()
      .appendingPathComponent("Sources/FloatingControlBar")
    let names = try FileManager.default.contentsOfDirectory(atPath: floatingControlBar.path)
      .filter { $0.hasPrefix("RealtimeHubController") && $0.hasSuffix(".swift") }
      .sorted()

    return try names.map { try source(named: $0, testFilePath: testFilePath) }.joined(separator: "\n")
  }
}
