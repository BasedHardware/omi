import SwiftUI
import XCTest

@testable import Omi_Computer

final class ChatWorkingIndicatorTests: XCTestCase {
  @MainActor
  func testCompletedMarkHasNoAnimationFrameSchedule() {
    XCTAssertEqual(
      ChatOmiMark.frameSchedule(motion: nil, reduceMotion: false),
      .staticResting
    )
    XCTAssertEqual(
      ChatOmiMark.frameSchedule(motion: .wave, reduceMotion: true),
      .staticResting
    )
    XCTAssertEqual(
      ChatOmiMark.frameSchedule(motion: .wave, reduceMotion: false),
      .animated(.wave)
    )
  }

  @MainActor
  func testCompletedMarkRenderDoesNotAdvanceAnimationModel() {
    let model = ChatMarkModel()
    let renderer = ImageRenderer(
      content: ChatOmiMark(motion: nil, size: 24, model: model)
        .frame(width: 48, height: 32)
    )
    renderer.scale = 1

    XCTAssertNotNil(renderer.cgImage)
    #if DEBUG
      XCTAssertEqual(model.debugAdvanceCount, 0)
    #endif
  }

  func testOnlyTheFinalAssistantMessageOwnsTheOmiMark() {
    let messages = [
      ChatMessage(id: "assistant-1", text: "First answer", sender: .ai),
      ChatMessage(id: "user-2", text: "Follow-up", sender: .user),
      ChatMessage(id: "assistant-2", text: "Final answer", sender: .ai),
    ]

    let markedIDs = messages.compactMap { message in
      message.id == ChatOmiMarkPlacement.finalAssistantMessageID(in: messages)
        ? message.id
        : nil
    }

    XCTAssertEqual(markedIDs, ["assistant-2"])
  }

  func testOmiMarkPlacementRequiresAnAssistantMessage() {
    let messages = [
      ChatMessage(id: "user-1", text: "Question", sender: .user),
      ChatMessage(id: "user-2", text: "Follow-up", sender: .user),
    ]

    XCTAssertNil(ChatOmiMarkPlacement.finalAssistantMessageID(in: []))
    XCTAssertNil(ChatOmiMarkPlacement.finalAssistantMessageID(in: messages))
  }

  func testOmiMarkReservesAVisibleRowForAnEmptyStreamingReply() {
    XCTAssertEqual(
      ChatOmiMarkPlacement.rowHeight(showsMark: true),
      ChatOmiMarkPlacement.reservedRowHeight
    )
    XCTAssertEqual(ChatOmiMarkPlacement.rowHeight(showsMark: false), 0)
  }

  func testIdleAndNonAssistantMessagesUseGatherMotion() {
    XCTAssertEqual(ChatWorkingStatus.motion(for: nil), .gather)
    XCTAssertEqual(
      ChatWorkingStatus.motion(for: ChatMessage(text: "hello", sender: .user)),
      .gather
    )
  }

  func testToolProgressHasOneExpandableGroupWithAllChildDetails() {
    let blocks: [ChatContentBlock] = [
      .toolCall(
        id: "search",
        name: "WebSearch",
        status: .completed,
        input: ToolCallInput(summary: "Omi", details: "query=Omi"),
        output: "Search result"
      ),
      .toolCall(
        id: "fetch",
        name: "WebFetch",
        status: .completed,
        input: ToolCallInput(summary: "omi.me", details: "url=https://omi.me"),
        output: "Page result"
      ),
    ]

    let visibleGroups = ContentBlockGroup.visibleChatGroups(blocks, isStreaming: true)

    XCTAssertEqual(visibleGroups.count, 1)
    guard let visibleGroup = visibleGroups.first,
      case .toolCalls(_, let childCalls) = visibleGroup
    else {
      return XCTFail("Expected one expandable tool-call pill")
    }
    XCTAssertEqual(childCalls.map(\.id), ["search", "fetch"])
    XCTAssertFalse(ToolCallsGroupExpansionPolicy.initiallyExpanded())
  }

  @MainActor
  func testCompletedBubbleReevaluatesWhenFinalOmiMarkOwnershipMoves() {
    let message = ChatMessage(id: "assistant", text: "Answer", sender: .ai)
    let marked = ChatBubble(
      message: message,
      app: nil,
      showsOmiMark: true,
      onRate: { _ in }
    )
    let unmarked = ChatBubble(
      message: message,
      app: nil,
      showsOmiMark: false,
      onRate: { _ in }
    )

    XCTAssertNotEqual(marked, unmarked)
  }

  func testLatestInFlightToolDrivesMarkMotion() {
    let message = ChatMessage(
      text: "",
      sender: .ai,
      contentBlocks: [
        .toolCall(id: "done", name: "Read", status: .completed),
        .toolCall(id: "fetch", name: "WebFetch", status: .running),
      ]
    )

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
