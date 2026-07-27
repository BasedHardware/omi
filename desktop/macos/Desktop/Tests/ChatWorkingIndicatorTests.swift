import XCTest

@testable import Omi_Computer

final class ChatWorkingIndicatorTests: XCTestCase {
  func testIdleAndNonAssistantMessagesUseThinkingProjection() {
    XCTAssertEqual(ChatWorkingStatus.label(for: nil), "Thinking")
    XCTAssertEqual(
      ChatWorkingStatus.label(for: ChatMessage(text: "hello", sender: .user)),
      "Thinking"
    )
    XCTAssertEqual(ChatWorkingStatus.motion(for: nil), .gather)
  }

  func testLatestInFlightToolDrivesTheVisibleLabel() {
    let message = ChatMessage(
      text: "",
      sender: .ai,
      contentBlocks: [
        .toolCall(id: "done", name: "Read", status: .completed),
        .toolCall(id: "fetch", name: "WebFetch", status: .running),
      ]
    )

    XCTAssertEqual(ChatWorkingStatus.label(for: message), "Fetching page")
    XCTAssertEqual(ChatWorkingStatus.motion(for: message), .gather)
  }

  func testLatestInFlightToolWinsAcrossSlowAndStalledStates() {
    let message = ChatMessage(
      text: "",
      sender: .ai,
      contentBlocks: [
        .toolCall(id: "fetch", name: "WebFetch", status: .slow),
        .toolCall(id: "write", name: "Write", status: .stalled),
      ]
    )

    XCTAssertEqual(ChatWorkingStatus.label(for: message), "Writing file")
    XCTAssertEqual(ChatWorkingStatus.motion(for: message), .wave)
  }

  func testToolMotionClassificationCoversReadWriteAndMCPNames() {
    XCTAssertEqual(ChatMarkMotion.forTool("Read"), .gather)
    XCTAssertEqual(ChatMarkMotion.forTool("WebFetch"), .gather)
    XCTAssertEqual(ChatMarkMotion.forTool("Write"), .wave)
    XCTAssertEqual(ChatMarkMotion.forTool("mcp__filesystem__edit"), .wave)
  }

  @MainActor
  func testReduceMotionKeepsWorkingMarkAtRest() {
    let model = ChatMarkModel()
    let start = Date(timeIntervalSinceReferenceDate: 100)

    for frame in 0..<120 {
      model.advance(
        to: start.addingTimeInterval(Double(frame) / 60),
        motion: .wave,
        reduceMotion: true
      )
    }

    XCTAssertEqual(model.snapshot.intensity, 0, accuracy: 0.001)
    XCTAssertEqual(model.snapshot.phase, 0, accuracy: 0.001)
  }

  @MainActor
  func testWorkingMarkEntersAndReturnsToRest() {
    let model = ChatMarkModel()
    let start = Date(timeIntervalSinceReferenceDate: 200)

    for frame in 0..<120 {
      model.advance(
        to: start.addingTimeInterval(Double(frame) / 60),
        motion: .wave,
        reduceMotion: false
      )
    }

    XCTAssertGreaterThan(model.snapshot.intensity, 0.9)
    XCTAssertGreaterThan(model.snapshot.phase, 0)
    XCTAssertEqual(model.snapshot.motion, .wave)

    for frame in 120..<420 {
      model.advance(
        to: start.addingTimeInterval(Double(frame) / 60),
        motion: nil,
        reduceMotion: false
      )
    }

    XCTAssertEqual(model.snapshot.intensity, 0, accuracy: 0.001)
    XCTAssertEqual(model.snapshot.phase, 0, accuracy: 0.001)
  }
}
