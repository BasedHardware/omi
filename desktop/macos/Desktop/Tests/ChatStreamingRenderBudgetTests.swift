import AppKit
import SwiftUI
import XCTest

@testable import Omi_Computer

/// **How much work one streaming flush may do.**
///
/// The reported failure was the whole app going stuttery *while* an answer
/// streams and smooth again the moment it settles. The visible transcript is
/// correct throughout, so no assertion on what a row shows can catch the
/// regression; the guard has to be on the work the row does to show it. This
/// mounts the production transcript (`ChatMessagesView` in an `NSHostingView`,
/// through the shared gesture harness), streams a realistic long Markdown
/// answer into its last row in buffer-sized slices at the buffer's own
/// cadence, and reads `ChatStreamingRenderProbe` — the debug counters at the
/// parse, measure and text-storage sites — after every flush.
///
/// The counts are mechanism, not timing: a flush parses its Markdown once
/// (not once for AppKit and once more for a SwiftUI renderer that never
/// draws), edits the live text storage from the first changed character
/// (never replacing a whole answer to append a word), and answers its height
/// from the layout it already has (not from a throwaway TextKit stack that
/// lays the whole answer out again). Main-thread CPU per flush is measured and
/// printed alongside — evidence for the PR, deliberately not an assertion, so
/// a loaded CI host cannot fail a deterministic contract.
@MainActor
final class ChatStreamingRenderBudgetTests: XCTestCase {

  /// About two lines of prose per flush — `ChatStreamingReveal` lets through
  /// at most a paced slice, and a real answer arrives in bursts, so this is
  /// the steady-state chunk the transcript actually sees.
  private static let charactersPerFlush = 48
  private static let flushInterval: TimeInterval = 0.035

  func testAStreamingFlushParsesOnceAndEditsTheTailOnly() throws {
    // The working mark animates only outside Reduce Motion, and the mark's
    // frames are the very thing the idle budget measures. Pin the environment
    // so the host machine's accessibility settings (a CI image can ship with
    // Reduce Motion on) cannot silently take the mark's static branch and fail
    // this precondition for a reason the code under test never chose.
    let harness = try ChatTranscriptGestureHarnessTests.Harness(
      messageCount: 20,
      pinReduceMotion: false)
    defer { harness.tearDown() }
    // Real history, not uniform prose: settled answers carry the blocks a real
    // turn leaves behind — a tool call with its output and the answer text —
    // because the per-row derivations the transcript runs on every body pass
    // are only expensive on rows that have them. A uniform fixture hid the
    // single largest cost sampled in the live app.
    harness.model.messages = Self.richHistory(count: 20)
    harness.settleInitialPlacement()

    let answer = Self.longMarkdownAnswer
    let chunks = Self.chunks(of: answer, size: Self.charactersPerFlush)
    XCTAssertGreaterThan(chunks.count, 100, "the fixture must be long enough to stream in many flushes")

    harness.beginStreamingAssistantMessage()
    harness.pump(0.1)
    ChatStreamingRenderProbe.reset()

    var flushCPUMilliseconds: [Double] = []
    var perFlushSnapshots: [[ChatStreamingRenderProbe.Counter: Int]] = []
    var previous = ChatStreamingRenderProbe.snapshot()
    for chunk in chunks {
      let cpuBefore = Self.mainThreadCPUNanoseconds()
      harness.appendStreamingText(chunk)
      harness.pump(Self.flushInterval)
      let cpuAfter = Self.mainThreadCPUNanoseconds()
      flushCPUMilliseconds.append(Double(cpuAfter - cpuBefore) / 1_000_000)
      let now = ChatStreamingRenderProbe.snapshot()
      perFlushSnapshots.append(Self.delta(from: previous, to: now))
      previous = now
    }

    let totals = ChatStreamingRenderProbe.snapshot()
    let flushes = chunks.count

    // Control: the same cadence with nothing arriving. Whatever the main thread
    // spends here — the live-edge pinner, the working mark's frames — is the
    // floor a flush is measured above, not part of the flush.
    var idleCPUMilliseconds: [Double] = []
    let beforeIdle = ChatStreamingRenderProbe.snapshot()
    for _ in 0..<20 {
      let cpuBefore = Self.mainThreadCPUNanoseconds()
      harness.pump(Self.flushInterval)
      idleCPUMilliseconds.append(Double(Self.mainThreadCPUNanoseconds() - cpuBefore) / 1_000_000)
    }
    let idle = Self.delta(from: beforeIdle, to: ChatStreamingRenderProbe.snapshot())
    let idleSorted = idleCPUMilliseconds.sorted()
    let sorted = flushCPUMilliseconds.sorted()
    let p50 = sorted[sorted.count / 2]
    let p95 = sorted[Int(Double(sorted.count - 1) * 0.95)]
    let maximum = sorted.last ?? 0
    let total = flushCPUMilliseconds.reduce(0, +)
    let report =
      "STREAM_RENDER_BUDGET flushes=\(flushes) chars=\(answer.count) "
      + "cpu_ms p50=\(String(format: "%.2f", p50)) p95=\(String(format: "%.2f", p95)) "
      + "max=\(String(format: "%.2f", maximum)) total=\(String(format: "%.1f", total)) "
      + "idle_cpu_ms p50=\(String(format: "%.2f", idleSorted[idleSorted.count / 2])) "
      + "max=\(String(format: "%.2f", idleSorted.last ?? 0)) "
      + "appKitParses=\(totals[.appKitProseBuild] ?? 0) "
      + "swiftUIParses=\(totals[.swiftUIProseBuild] ?? 0) "
      + "documentParses=\(totals[.documentParse] ?? 0) "
      + "throwawayMeasures=\(totals[.throwawayHeightMeasure] ?? 0) "
      + "liveHeightReads=\(totals[.liveHeightRead] ?? 0) "
      + "storageReplacements=\(totals[.storageReplacement] ?? 0) "
      + "storageIncrementalEdits=\(totals[.storageIncrementalEdit] ?? 0) "
      + "transcriptBodies=\(totals[.transcriptBodyEvaluation] ?? 0) "
      + "bubbleBodies=\(totals[.bubbleBodyEvaluation] ?? 0) "
      + "idle markFrames=\(idle[.markFrame] ?? 0) proseSizeQueries=\(idle[.proseSizeQuery] ?? 0) "
      + "markFramesTotal=\(totals[.markFrame] ?? 0) "
      + "hostReduceMotion=\(NSWorkspace.shared.accessibilityDisplayShouldReduceMotion)"
    print(report)

    // 0. A streaming row that receives nothing lays nothing out. The working
    //    mark keeps animating beside it, and its frames must not re-lay out
    //    the transcript: as a SwiftUI timeline every frame was a full
    //    hosting-view layout pass, which alone kept the main thread busy for
    //    the whole answer.
    XCTAssertGreaterThan(
      idle[.markFrame] ?? 0, 0,
      "precondition: the working mark animates while the row streams")
    XCTAssertLessThanOrEqual(
      idle[.proseSizeQuery] ?? 0, 2,
      "the working mark's frames must not lay the transcript out again "
        + "(\(idle[.proseSizeQuery] ?? 0) prose size queries over \(idle[.markFrame] ?? 0) frames)")

    // The row must actually have re-rendered per flush for any of the
    // budgets below to mean anything.
    XCTAssertGreaterThanOrEqual(
      totals[.appKitProseBuild] ?? 0, flushes,
      "every flush must reach the AppKit prose renderer (precondition for the budgets)")

    // 1. One Markdown parse per flush. The SwiftUI renderer's parse is for
    //    rows the AppKit path does not draw; the live transcript draws every
    //    prose block through `ChatSelectableProse`, so its parse is pure waste
    //    here — and it used to run on every flush, then be discarded.
    XCTAssertEqual(
      totals[.swiftUIProseBuild] ?? 0, 0,
      "the AppKit prose path must not also run the SwiftUI Markdown parse it never renders")

    // 2. The live text storage is edited from the first changed character;
    //    the whole answer is replaced at most once, when the row is created.
    XCTAssertLessThanOrEqual(
      totals[.storageReplacement] ?? 0, 1,
      "a streaming flush must edit the text storage's tail, not replace the whole answer")
    // Slightly under the flush count: two flushes landing in one run-loop
    // turn are one edit, which is coalescing, not replacement.
    XCTAssertGreaterThanOrEqual(
      totals[.storageIncrementalEdit] ?? 0, flushes * 9 / 10,
      "each flush after the first must land as an incremental storage edit")

    // 3. Once the column has a width, a flush measures its height from the
    //    layout the live view already did for the edit — never by laying the
    //    whole answer out again in a throwaway stack. A handful is allowed
    //    for the row's first placement and any width the layout proposes
    //    before it settles.
    let throwaway = totals[.throwawayHeightMeasure] ?? 0
    XCTAssertLessThanOrEqual(
      throwaway, 8,
      "a streaming flush must not lay the whole answer out in a throwaway TextKit stack "
        + "(\(throwaway) throwaway measures over \(flushes) flushes)")
    XCTAssertGreaterThanOrEqual(
      totals[.liveHeightRead] ?? 0, flushes / 2,
      "the streaming row's height must come from its live layout")
  }

  // MARK: - Fixture

  /// A realistic long answer: headings, emphasis, inline code, bullets, a
  /// numbered list, a short fenced block and prose — the shapes a model
  /// actually produces, so every renderer branch on the flush path is paid.
  static let longMarkdownAnswer: String = {
    var parts: [String] = []
    parts.append("## What changed and why it matters\n")
    for paragraph in 0..<6 {
      parts.append(
        "Paragraph \(paragraph + 1): the transcript keeps **every row eagerly mounted** so the "
          + "document height stays stable while you scroll, and each streamed slice lands as one "
          + "`flushPaced` beat. A reader sees a steady flow rather than a lurch, which is the whole "
          + "point of pacing the reveal ~ roughly two lines at a time (see `ChatStreamingReveal`).\n")
    }
    parts.append("### Checklist\n")
    for item in 0..<14 {
      parts.append(
        "- Item \(item + 1): verify the *first impossible transition* before adding a policy, and "
          + "record the `sequence`, the owner, and the native geometry it produced.")
    }
    parts.append("\n### Steps\n")
    for step in 0..<8 {
      parts.append(
        "\(step + 1). Mount the production view in an `NSHostingView`, drive the real boundary, "
          + "and assert both the authoritative state and the rendered outcome.")
    }
    parts.append("\n```swift\nlet height = ChatSelectableProseText.height(of: attributed, fittingWidth: 640)\n```\n")
    for paragraph in 0..<6 {
      parts.append(
        "Closing paragraph \(paragraph + 1): none of this changes what the reader sees — the answer "
          + "is identical either way — it changes how much the main thread does to show it, which "
          + "is exactly why the guard has to count work rather than compare pixels.\n")
    }
    return parts.joined(separator: "\n")
  }()

  /// Alternating user questions and settled assistant turns whose blocks look
  /// like a real tool-using answer: one completed tool call with a few
  /// kilobytes of output, then the answer as a text block.
  static func richHistory(count: Int) -> [ChatMessage] {
    let toolOutput = (0..<40).map { index in
      "{\"id\":\"item-\(index)\",\"title\":\"Result \(index) from the tool\",\"detail\":\""
        + String(repeating: "x", count: 40)
        + "\"}"
    }.joined(separator: ",")
    return (0..<count).map { index in
      let createdAt = Date(timeIntervalSince1970: 1_700_000_000 + Double(index))
      if index.isMultiple(of: 2) {
        return ChatMessage(
          id: "user-\(index)",
          text: "Reader question number \(index) about the desktop transcript.",
          createdAt: createdAt,
          sender: .user)
      }
      let answer = String(
        repeating: "Assistant answer \(index) with **enough prose** to make the row tall, and `code`. ", count: 6)
      return ChatMessage(
        id: "assistant-\(index)",
        text: answer,
        createdAt: createdAt,
        sender: .ai,
        contentBlocks: [
          .toolCall(
            id: "tool-\(index)", name: "search_memories", status: .completed,
            toolUseId: "call-\(index)", input: nil, output: "[\(toolOutput)]"),
          .text(id: "assistant-\(index):terminal", text: answer),
        ])
    }
  }

  static func chunks(of text: String, size: Int) -> [String] {
    var result: [String] = []
    var index = text.startIndex
    while index < text.endIndex {
      let end = text.index(index, offsetBy: size, limitedBy: text.endIndex) ?? text.endIndex
      result.append(String(text[index..<end]))
      index = end
    }
    return result
  }

  private static func delta(
    from before: [ChatStreamingRenderProbe.Counter: Int],
    to after: [ChatStreamingRenderProbe.Counter: Int]
  ) -> [ChatStreamingRenderProbe.Counter: Int] {
    var result: [ChatStreamingRenderProbe.Counter: Int] = [:]
    for counter in ChatStreamingRenderProbe.Counter.allCases {
      result[counter] = (after[counter] ?? 0) - (before[counter] ?? 0)
    }
    return result
  }

  /// CPU time this thread has consumed, so a run-loop pump that mostly sleeps
  /// is measured by what it did rather than how long it waited.
  private static func mainThreadCPUNanoseconds() -> UInt64 {
    clock_gettime_nsec_np(CLOCK_THREAD_CPUTIME_ID)
  }
}
