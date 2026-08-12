import Dispatch
import XCTest

@testable import Omi_Computer

final class MemoryExportSetupTests: XCTestCase {
  func testWorkspaceFallbackReroutesBackgroundCompletionToMainActor() async {
    let callbackStarted = expectation(description: "background callback started")
    let actionCompleted = expectation(description: "workspace fallback ran on main actor")

    DispatchQueue.global().async {
      XCTAssertFalse(Thread.isMainThread)
      MemoryExportDestinationSheetModel.performOnMainActor {
        XCTAssertTrue(Thread.isMainThread)
        actionCompleted.fulfill()
      }
      callbackStarted.fulfill()
    }

    await fulfillment(of: [callbackStarted, actionCompleted], timeout: 1)
  }

  func testOpenClawManualSetupUsesMCPConfigNotMemoryPromptSecret() throws {
    let setup = try XCTUnwrap(MemoryExportDestination.openclaw.mcpSetup(key: "test-key"))
    let copyText = try XCTUnwrap(setup.copyText)

    XCTAssertEqual(setup.copyTitle, "Copy command")
    XCTAssertTrue(copyText.contains("openclaw mcp set omi-memory"))
    XCTAssertTrue(copyText.contains("\"transport\":\"streamable-http\""))
    XCTAssertTrue(copyText.contains("\"Authorization\":\"Bearer test-key\""))
    XCTAssertTrue(copyText.contains("openclaw mcp reload"))
    XCTAssertFalse(copyText.contains("SOUL.md"))
    XCTAssertFalse(copyText.contains("MEMORY.md"))
    XCTAssertFalse(copyText.contains("MCP: https://"))
    XCTAssertFalse(copyText.contains("\nAdd this note"))
    XCTAssertFalse(copyText.contains("\n# Then add this note"))
    XCTAssertEqual(copyText.split(separator: "\n").count, 2)
    XCTAssertFalse(setup.steps.joined(separator: " ").contains("MEMORY.md"))
    XCTAssertTrue(setup.steps.joined(separator: " ").contains("Reload OpenClaw MCP"))
    XCTAssertTrue(setup.steps.joined(separator: " ").contains("SOUL.md"))
  }
}
