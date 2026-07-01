import XCTest

@testable import Omi_Computer

final class MemoryExportStatusTests: XCTestCase {
  override func setUp() {
    super.setUp()
    resetMemoryExportDefaults()
  }

  override func tearDown() {
    resetMemoryExportDefaults()
    super.tearDown()
  }

  func testStoredMCPKeyDoesNotMarkAgentDestinationsConnected() async {
    UserDefaults.standard.set("test-key", forKey: "memoryExportMCPApiKey")

    let codexStatus = await MemoryExportService.shared.status(for: .codex)
    let claudeCodeStatus = await MemoryExportService.shared.status(for: .claudeCode)

    XCTAssertTrue(codexStatus.isConfigured)
    XCTAssertTrue(claudeCodeStatus.isConfigured)
    XCTAssertFalse(codexStatus.hasConnection)
    XCTAssertFalse(claudeCodeStatus.hasConnection)
  }

  func testMarkConnectedIsPerDestination() async {
    UserDefaults.standard.set("test-key", forKey: "memoryExportMCPApiKey")

    await MemoryExportService.shared.markConnected(.openclaw)

    let openClawStatus = await MemoryExportService.shared.status(for: .openclaw)
    let hermesStatus = await MemoryExportService.shared.status(for: .hermes)

    XCTAssertTrue(openClawStatus.hasConnection)
    XCTAssertFalse(hermesStatus.hasConnection)
  }

  func testMemoryPackExportStillCountsAsConnectionHistory() async {
    UserDefaults.standard.set(7, forKey: "memoryExportExportedCount.claude")

    let status = await MemoryExportService.shared.status(for: .claude)

    XCTAssertTrue(status.isConfigured)
    XCTAssertTrue(status.hasConnection)
  }

  private func resetMemoryExportDefaults() {
    let defaults = UserDefaults.standard
    defaults.removeObject(forKey: "memoryExportMCPApiKey")
    defaults.removeObject(forKey: "localAgentAPIEnabled")
    defaults.removeObject(forKey: "localAgentAPIToken")

    for destination in MemoryExportDestination.allCases {
      defaults.removeObject(forKey: "memoryExportExportedCount.\(destination.rawValue)")
      defaults.removeObject(forKey: "memoryExportLastExportedAt.\(destination.rawValue)")
      defaults.removeObject(forKey: "memoryExportDetail.\(destination.rawValue)")
      defaults.removeObject(forKey: "memoryExportLastExportPath.\(destination.rawValue)")
      defaults.removeObject(forKey: "memoryExportConnectedAt.\(destination.rawValue)")
    }
  }
}
