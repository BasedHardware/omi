import XCTest

@testable import Omi_Computer

final class ChatContentBlockToolActivityTests: XCTestCase {

  func testApplyToolActivityCreatesRunningToolCall() {
    var blocks: [ChatContentBlock] = []

    ChatContentBlock.applyToolActivity(
      to: &blocks,
      toolName: "Bash",
      status: .running,
      toolUseId: "tool-1",
      input: ["command": "pwd"]
    )

    XCTAssertEqual(blocks.count, 1)
    assertToolCall(
      blocks[0],
      name: "Bash",
      status: .running,
      toolUseId: "tool-1",
      inputSummary: "pwd"
    )
  }

  func testApplyToolActivityUpdatesExistingInFlightBlockWithInputByToolUseId() {
    var blocks: [ChatContentBlock] = [
      .toolCall(id: "existing", name: "Bash", status: .running, toolUseId: "tool-1")
    ]

    ChatContentBlock.applyToolActivity(
      to: &blocks,
      toolName: "Bash",
      status: .running,
      toolUseId: "tool-1",
      input: ["command": "ls -la"]
    )

    XCTAssertEqual(blocks.count, 1)
    assertToolCall(
      blocks[0],
      id: "existing",
      name: "Bash",
      status: .running,
      toolUseId: "tool-1",
      inputSummary: "ls -la"
    )
  }

  func testApplyToolActivityUpdatesLegacyInFlightBlockByNameWhenToolUseIdArrivesLater() {
    var blocks: [ChatContentBlock] = [
      .toolCall(id: "legacy", name: "execute_sql", status: .slow, toolUseId: nil)
    ]

    ChatContentBlock.applyToolActivity(
      to: &blocks,
      toolName: "execute_sql",
      status: .running,
      toolUseId: "tool-2",
      input: ["query": "select * from conversations"]
    )

    XCTAssertEqual(blocks.count, 1)
    assertToolCall(
      blocks[0],
      id: "legacy",
      name: "execute_sql",
      status: .slow,
      toolUseId: "tool-2",
      inputSummary: "select * from conversations"
    )
  }

  func testApplyToolActivityResolvesTerminalStatusByToolUseIdBeforeName() {
    var blocks: [ChatContentBlock] = [
      .toolCall(id: "first", name: "Bash", status: .running, toolUseId: "tool-1"),
      .toolCall(id: "second", name: "Bash", status: .stalled, toolUseId: "tool-2"),
    ]

    ChatContentBlock.applyToolActivity(
      to: &blocks,
      toolName: "Bash",
      status: .completed,
      toolUseId: "tool-1"
    )

    assertToolCall(blocks[0], id: "first", name: "Bash", status: .completed, toolUseId: "tool-1")
    assertToolCall(blocks[1], id: "second", name: "Bash", status: .stalled, toolUseId: "tool-2")
  }

  func testApplyToolActivityResolvesLatestInFlightBlockByNameWhenToolUseIdMissing() {
    var blocks: [ChatContentBlock] = [
      .toolCall(id: "old", name: "Bash", status: .running, toolUseId: nil),
      .toolCall(id: "new", name: "Bash", status: .slow, toolUseId: nil),
    ]

    ChatContentBlock.applyToolActivity(
      to: &blocks,
      toolName: "Bash",
      status: .failed
    )

    assertToolCall(blocks[0], id: "old", name: "Bash", status: .running, toolUseId: nil)
    assertToolCall(blocks[1], id: "new", name: "Bash", status: .failed, toolUseId: nil)
  }

  func testApplyToolActivityDoesNotRewriteTerminalBlock() {
    var blocks: [ChatContentBlock] = [
      .toolCall(id: "done", name: "Bash", status: .completed, toolUseId: "tool-1")
    ]

    ChatContentBlock.applyToolActivity(
      to: &blocks,
      toolName: "Bash",
      status: .failed,
      toolUseId: "tool-1"
    )

    XCTAssertEqual(blocks.count, 1)
    assertToolCall(blocks[0], id: "done", name: "Bash", status: .completed, toolUseId: "tool-1")
  }

  private func assertToolCall(
    _ block: ChatContentBlock,
    id expectedId: String? = nil,
    name expectedName: String,
    status expectedStatus: ToolCallStatus,
    toolUseId expectedToolUseId: String?,
    inputSummary expectedInputSummary: String? = nil,
    file: StaticString = #filePath,
    line: UInt = #line
  ) {
    guard case .toolCall(let id, let name, let status, let toolUseId, let input, _) = block else {
      XCTFail("Expected toolCall block", file: file, line: line)
      return
    }

    if let expectedId {
      XCTAssertEqual(id, expectedId, file: file, line: line)
    }
    XCTAssertEqual(name, expectedName, file: file, line: line)
    XCTAssertEqual(status, expectedStatus, file: file, line: line)
    XCTAssertEqual(toolUseId, expectedToolUseId, file: file, line: line)
    XCTAssertEqual(input?.summary, expectedInputSummary, file: file, line: line)
  }
}
