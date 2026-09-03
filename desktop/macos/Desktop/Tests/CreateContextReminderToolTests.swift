import XCTest

@testable import Omi_Computer

final class CreateContextReminderToolTests: XCTestCase {
  private var ownerFixture: RuntimeOwnerAuthorityTestFixture?

  override func setUp() async throws {
    try await super.setUp()
    let fixture = await RuntimeOwnerAuthorityTestFixture()
    await fixture.establish(authOwnerID: "context-reminder-tool-owner")
    ownerFixture = fixture
  }

  override func tearDown() async throws {
    await ownerFixture?.restore()
    ownerFixture = nil
    try await super.tearDown()
  }

  func testCreateContextReminderIsHandledByExecutor() async {
    let toolCall = ToolCall(
      name: "create_context_reminder",
      arguments: [:],
      thoughtSignature: nil
    )

    let result = await ChatToolExecutor.execute(toolCall)

    XCTAssertFalse(result.hasPrefix("Unknown tool"), "create_context_reminder must be handled directly")
    XCTAssertTrue(result.contains("text is required"))
  }
}
