import Combine
import XCTest

@testable import Omi_Computer

/// The journal side of a streaming flush.
///
/// Every ~35 ms flush of a streamed answer schedules a journal write of the
/// whole row. Two things about that used to scale with the answer instead of
/// with the flush: the writes were queued one per flush behind whatever the
/// kernel was still doing (unbounded when a round trip outlasts a flush), and
/// every completed write echoed the row back through `projectJournalTurns`,
/// which republished the whole transcript — with the echo's *older* text, so
/// the visible answer stepped back a few words on every write and forward
/// again on the next flush. These pin the coalescing and the echo handling.
@MainActor
final class ChatStreamingJournalCoalescingTests: XCTestCase {

  // MARK: - Coalescing

  func testStreamingWritesCoalesceToTheNewestWhileOneIsInFlight() async {
    let coordinator = ChatJournalWriteCoordinator()
    let messageID = "assistant-streaming"
    let gate = Gate()
    let executed = Executed()

    XCTAssertTrue(
      coordinator.schedule(messageID: messageID, coalescing: true) {
        await gate.wait()
        executed.append(0)
      })
    await gate.untilWaiting()
    // Fifty more flushes arrive while the first write is still on the wire.
    for snapshot in 1...50 {
      XCTAssertTrue(
        coordinator.schedule(messageID: messageID, coalescing: true) {
          executed.append(snapshot)
        })
    }
    gate.open()
    _ = await coordinator.beginTerminalization(messageID: messageID)

    XCTAssertEqual(
      executed.values, [0, 50],
      "the in-flight write finishes, then only the newest waiting snapshot is written — "
        + "never one per flush")
  }

  func testDurableWritesKeepTheirPlaceBehindACoalescedStreamingWrite() async {
    let coordinator = ChatJournalWriteCoordinator()
    let messageID = "assistant-streaming"
    let gate = Gate()
    let executed = Executed()

    coordinator.schedule(messageID: messageID, coalescing: true) {
      await gate.wait()
      executed.append(0)
    }
    await gate.untilWaiting()
    coordinator.schedule(messageID: messageID, coalescing: true) { executed.append(1) }
    coordinator.schedule(messageID: messageID, supersededByTerminalization: false) { executed.append(100) }
    coordinator.schedule(messageID: messageID, coalescing: true) { executed.append(2) }
    coordinator.schedule(messageID: messageID, coalescing: true) { executed.append(3) }
    gate.open()
    _ = await coordinator.beginTerminalization(messageID: messageID)

    XCTAssertEqual(
      executed.values, [0, 1, 100, 3],
      "a durable write runs after the streaming snapshot queued before it and before the one after; "
        + "streaming snapshots queued together still coalesce to the newest")
  }

  func testCancelAllDropsAWaitingCoalescedWrite() async {
    let coordinator = ChatJournalWriteCoordinator()
    let messageID = "assistant-streaming"
    let gate = Gate()
    let executed = Executed()

    coordinator.schedule(messageID: messageID, coalescing: true) {
      await gate.wait()
      executed.append(0)
    }
    await gate.untilWaiting()
    coordinator.schedule(messageID: messageID, coalescing: true) { executed.append(1) }
    coordinator.cancelAll()
    gate.open()
    // Nothing is awaited by design after cancellation; give the run loop a turn.
    await Task.yield()
    await Task.yield()

    XCTAssertFalse(executed.values.contains(1), "an auth change must not let a stale snapshot land afterwards")
  }

  // MARK: - Echo handling

  func testAStreamingEchoBehindTheLiveRowNeitherMovesTheTextBackNorRepublishes() throws {
    let provider = ChatProvider()
    let surface = provider.mainChatSurfaceReference()
    let turnID = "assistant-turn-1"
    let liveText = "The answer so far, with more words than the journal has seen."
    let createdAt = Date(timeIntervalSince1970: 1_700_000_000)
    provider.messages = [
      ChatMessage(id: "user-turn-1", text: "Question?", createdAt: createdAt, sender: .user),
      ChatMessage(
        id: turnID,
        text: liveText,
        createdAt: createdAt,
        sender: .ai,
        isStreaming: true,
        contentBlocks: [.text(id: "\(turnID):text", text: liveText)],
        turnOwner: .mainChat,
        journalStatus: .streaming),
    ]
    var publishes = 0
    let subscription = provider.$messages.dropFirst().sink { _ in publishes += 1 }
    defer { subscription.cancel() }

    let echoText = "The answer so far,"
    provider.projectJournalTurns([
      try Self.makeTurn(
        surface: surface,
        turnID: turnID,
        role: "assistant",
        status: .streaming,
        content: echoText,
        contentBlocks: [["type": "text", "id": "\(turnID):text", "text": echoText]],
        turnSeq: 7)
    ])

    XCTAssertEqual(provider.messages[1].text, liveText, "the live row is ahead of its own echo and keeps its text")
    XCTAssertEqual(publishes, 0, "an echo that changes nothing visible must not republish the transcript")
  }

  func testATerminalReplayStillReplacesTheStreamingRow() throws {
    let provider = ChatProvider()
    let surface = provider.mainChatSurfaceReference()
    let turnID = "assistant-turn-2"
    provider.messages = [
      ChatMessage(
        id: turnID,
        text: "Streaming text that is longer than the final answer will be.",
        sender: .ai,
        isStreaming: true,
        journalStatus: .streaming)
    ]
    var publishes = 0
    let subscription = provider.$messages.dropFirst().sink { _ in publishes += 1 }
    defer { subscription.cancel() }

    provider.projectJournalTurns([
      try Self.makeTurn(
        surface: surface,
        turnID: turnID,
        role: "assistant",
        status: .completed,
        content: "Final.",
        contentBlocks: [["type": "text", "id": "\(turnID):terminal", "text": "Final."]],
        turnSeq: 8)
    ])

    XCTAssertEqual(provider.messages[0].text, "Final.", "the journal's terminal row is the durable authority")
    XCTAssertFalse(provider.messages[0].isStreaming)
    XCTAssertEqual(publishes, 1)
  }

  // MARK: - Plumbing

  private static func makeTurn(
    surface: AgentSurfaceReference,
    turnID: String,
    role: String,
    status: KernelJournalTurnStatus,
    content: String,
    contentBlocks: [[String: Any]],
    turnSeq: Int
  ) throws -> KernelJournalTurn {
    try XCTUnwrap(
      KernelJournalTurn(dictionary: [
        "conversationId": "conversation-1",
        "turnId": turnID,
        "turnSeq": turnSeq,
        "conversationGeneration": 1,
        "generationBaseTurnSeq": 0,
        "producerId": "producer:\(turnID)",
        "payloadHash": "sha256:\(turnID):\(turnSeq)",
        "role": role,
        "surfaceKind": surface.surfaceKind,
        "externalRefKind": surface.externalRefKind,
        "externalRefId": surface.externalRefId,
        "content": content,
        "origin": "test",
        "status": status.rawValue,
        "contentBlocks": contentBlocks,
        "resources": [],
        "metadataJson": "{}",
        "createdAtMs": 1_700_000_000_000,
        "updatedAtMs": 1_700_000_000_000 + turnSeq,
      ]))
  }

  /// A one-shot gate the in-flight write waits on, so the test controls how
  /// long "the kernel" takes.
  private final class Gate: @unchecked Sendable {
    private var continuation: CheckedContinuation<Void, Never>?
    private var isOpen = false
    private let lock = NSLock()

    func wait() async {
      await withCheckedContinuation { (continuation: CheckedContinuation<Void, Never>) in
        lock.lock()
        if isOpen {
          lock.unlock()
          continuation.resume()
          return
        }
        self.continuation = continuation
        lock.unlock()
      }
    }

    /// Yields until the first write is actually parked on the gate, so the
    /// writes scheduled afterwards are behind one that is genuinely in flight.
    func untilWaiting() async {
      while !isWaitingOrOpen {
        await Task.yield()
      }
    }

    private var isWaitingOrOpen: Bool {
      lock.lock()
      defer { lock.unlock() }
      return continuation != nil || isOpen
    }

    func open() {
      lock.lock()
      isOpen = true
      let waiting = continuation
      continuation = nil
      lock.unlock()
      waiting?.resume()
    }
  }

  private final class Executed: @unchecked Sendable {
    private let lock = NSLock()
    private var storage: [Int] = []
    var values: [Int] {
      lock.lock()
      defer { lock.unlock() }
      return storage
    }
    func append(_ value: Int) {
      lock.lock()
      storage.append(value)
      lock.unlock()
    }
  }
}
