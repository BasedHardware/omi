import Dispatch
import XCTest

@testable import Omi_Computer

final class MemoryExportSetupTests: XCTestCase {
  @MainActor
  func testWorkspaceFallbackReroutesFailedApplicationLaunchToMainActor() async {
    let exportURL = URL(fileURLWithPath: "/tmp/memory-export.md")
    let installedApplicationURL = URL(fileURLWithPath: "/Applications/Installed.app")
    let defaultApplicationURL = URL(fileURLWithPath: "/Applications/Default.app")
    let fallbackOpened = expectation(description: "workspace fallback opened on main actor")
    var openedApplications: [URL] = []
    let workspace = MemoryExportWorkspace(
      installedApplicationURL: { _ in installedApplicationURL },
      defaultApplicationURL: { _ in defaultApplicationURL },
      openWithApplication: { _, applicationURL, _, completion in
        openedApplications.append(applicationURL)
        DispatchQueue.global().async {
          completion(URLError(.cannotOpenFile))
        }
      },
      open: { url in
        XCTAssertTrue(Thread.isMainThread)
        XCTAssertEqual(url, exportURL)
        fallbackOpened.fulfill()
      })
    var model: MemoryExportDestinationSheetModel? = MemoryExportDestinationSheetModel(workspace: workspace)
    weak var weakModel: MemoryExportDestinationSheetModel?
    weakModel = model

    model?.openDestination(for: .chatgpt, url: exportURL)
    model = nil

    await fulfillment(of: [fallbackOpened], timeout: 1)
    XCTAssertEqual(openedApplications, [installedApplicationURL, defaultApplicationURL])
    XCTAssertNil(weakModel)
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
