import XCTest

@testable import Omi_Computer

/// The wire delivers an answer in bursts; the transcript should show it as a
/// flow. These pin the pacing that turns one into the other.
final class ChatStreamingRevealTests: XCTestCase {
  func testASmallBacklogDrainsOverAFewFlushes() {
    XCTAssertEqual(ChatStreamingReveal.characters(pending: 100), 20)
    XCTAssertEqual(ChatStreamingReveal.characters(pending: 10), ChatStreamingReveal.minimumPerFlush)
    XCTAssertEqual(ChatStreamingReveal.characters(pending: 3), 3, "never more than is pending")
    XCTAssertEqual(ChatStreamingReveal.characters(pending: 0), 0)
  }

  func testALargeBacklogCatchesUpToTheLagCap() {
    let revealed = ChatStreamingReveal.characters(pending: 2000)
    XCTAssertEqual(2000 - revealed, ChatStreamingReveal.maximumLag, "a paragraph from a tool lands almost at once")
  }

  private func makeMessages() -> [ChatMessage] {
    [ChatMessage(id: "m", text: "", sender: .ai, isStreaming: true)]
  }

  func testAPacedFlushRevealsASliceAndKeepsTheRestQueued() {
    let buffer = ChatStreamingBuffer(flushInterval: 10)
    var messages = makeMessages()
    buffer.appendText(messageId: "m", text: String(repeating: "a", count: 100), scheduleFlush: {})

    XCTAssertTrue(buffer.flushPaced(messages: &messages), "most of the burst is still waiting")
    XCTAssertEqual(messages[0].text.count, 20)
    XCTAssertEqual(buffer.pendingTextCount, 80)

    XCTAssertTrue(buffer.flushPaced(messages: &messages))
    XCTAssertEqual(messages[0].text.count, 36, "each flush takes a fifth of what remains")

    buffer.flush(messages: &messages)
    XCTAssertEqual(messages[0].text.count, 100)
    XCTAssertFalse(buffer.flushPaced(messages: &messages), "nothing left once drained")
  }

  func testThinkingStaysBehindTheTextItFollows() {
    let buffer = ChatStreamingBuffer(flushInterval: 10)
    var messages = makeMessages()
    buffer.appendText(messageId: "m", text: String(repeating: "a", count: 100), scheduleFlush: {})
    buffer.appendThinking(messageId: "m", text: "thought", scheduleFlush: {})
    buffer.appendText(messageId: "m", text: String(repeating: "b", count: 10), scheduleFlush: {})

    XCTAssertTrue(buffer.flushPaced(messages: &messages))
    XCTAssertEqual(messages[0].contentBlocks.count, 1, "the thinking block waits for the text ahead of it")
    XCTAssertEqual(messages[0].text, String(repeating: "a", count: 22))

    buffer.flush(messages: &messages)
    XCTAssertEqual(messages[0].contentBlocks.count, 3)
    XCTAssertEqual(messages[0].text, String(repeating: "a", count: 100) + String(repeating: "b", count: 10))
  }

  func testAPacedFlushCutsOnCharacterBoundaries() {
    let buffer = ChatStreamingBuffer(flushInterval: 10)
    var messages = makeMessages()
    // Family emoji are one Character of several scalars; a cut must not split one.
    let text = String(repeating: "👨‍👩‍👧", count: 30)
    buffer.appendText(messageId: "m", text: text, scheduleFlush: {})

    _ = buffer.flushPaced(messages: &messages)
    XCTAssertEqual(messages[0].text, String(repeating: "👨‍👩‍👧", count: 6))
    buffer.flush(messages: &messages)
    XCTAssertEqual(messages[0].text, text)
  }

  func testTheRemainderReArmsItsOwnFlush() {
    let buffer = ChatStreamingBuffer(flushInterval: 0.01)
    var messages = makeMessages()
    let rearmed = expectation(description: "a paced flush that leaves text behind schedules the next")
    buffer.appendText(messageId: "m", text: String(repeating: "a", count: 100), scheduleFlush: {})

    XCTAssertTrue(buffer.flushPaced(messages: &messages))
    buffer.scheduleFlush { rearmed.fulfill() }

    wait(for: [rearmed], timeout: 1)
  }

  /// A flush whose render work eats into its interval must not drag every
  /// later beat back. Beats anchor to the beat before them, so the reveal's
  /// period stays `flushInterval` while a flush still fits inside one — late
  /// in a long answer is exactly when a completion-anchored cadence slows the
  /// reveal down and the stream starts to stutter.
  ///
  /// Driven against `nextBeatDeadline` with simulated work instead of a real
  /// `Thread.sleep`: the property is the scheduling math, and a sleep's actual
  /// duration is whatever the host scheduler feels like — on a loaded CI
  /// runner the sleep itself overshot the beat budget and the test failed on
  /// machines whose streaming was fine.
  func testBeatsHoldTheirPeriodWhenFlushWorkEatsIntoTheInterval() {
    let interval = UInt64(0.08 * 1_000_000_000)
    // Work that occupies three quarters of the interval, the way a growing
    // transcript render does late in an answer.
    let work = UInt64(0.06 * 1_000_000_000)

    var scheduledBeat: UInt64? = nil
    var fireAt: UInt64? = nil
    var now: UInt64 = 1_000_000_000
    var periods: [UInt64] = []
    for _ in 0..<20 {
      let deadline = ChatStreamingBuffer.nextBeatDeadline(
        scheduledBeat: scheduledBeat, now: now, interval: interval)
      if let previous = fireAt {
        periods.append(deadline - previous)
      }
      fireAt = deadline
      scheduledBeat = deadline
      now = deadline &+ work  // the flush's render work runs past its start
    }

    XCTAssertEqual(periods.count, 19, "precondition: a long beat chain")
    // Anchored beats hold the grid exactly. A completion-anchored cadence
    // would run every beat at interval + work (140 ms here) — the stutter
    // this scheduling exists to prevent.
    XCTAssertTrue(
      periods.allSatisfy { $0 == interval },
      "beats left the \(String(format: "%.0f", Double(interval) / 1e6)) ms grid: "
        + periods.map { String(format: "%.0f", Double($0) / 1e6) }.joined(separator: ", "))
  }

  /// A beat whose work overran its interval resynchronizes — it fires at once
  /// and the grid restarts from there — instead of compounding the overrun.
  func testAnOverrunningBeatResynchronizesToNow() {
    let interval = UInt64(0.08 * 1_000_000_000)
    // Work that overshoots the interval by half again.
    let work = UInt64(0.12 * 1_000_000_000)

    var scheduledBeat: UInt64? = nil
    var now: UInt64 = 1_000_000_000
    var firstResyncPeriod: UInt64? = nil
    var periodsAfterResync: [UInt64] = []
    for _ in 0..<10 {
      let deadline = ChatStreamingBuffer.nextBeatDeadline(
        scheduledBeat: scheduledBeat, now: now, interval: interval)
      if let previous = scheduledBeat {
        let period = deadline - previous
        if firstResyncPeriod == nil {
          firstResyncPeriod = period
        } else {
          periodsAfterResync.append(period)
        }
      }
      scheduledBeat = deadline
      now = deadline &+ work
    }

    // The first re-arm after the overrun fires at the overrun's end (period ==
    // work, not work + interval); from there work still overruns, so every
    // period is exactly the work duration — the grid never accumulates debt.
    XCTAssertEqual(firstResyncPeriod, work)
    XCTAssertTrue(
      periodsAfterResync.allSatisfy { $0 == work },
      "overrunning beats compounded: "
        + periodsAfterResync.map { String(format: "%.0f", Double($0) / 1e6) }.joined(separator: ", "))
  }
}
