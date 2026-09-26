import XCTest

@testable import Omi_Computer

/// What one journal echo costs on the main thread as the transcript grows.
///
/// Every coalesced streaming write refreshes the journal and projects the
/// echo through `projectJournalTurns`, which runs whole-transcript work
/// (canonical sort, citation inheritance, citation-identifier diff) before it
/// can decide that nothing visible changed. This pins that cost as a
/// function of transcript length so it is measured rather than guessed.
@MainActor
final class ChatJournalProjectionCostTests: XCTestCase {

  func testStreamingEchoProjectionCostAcrossTranscriptSizes() throws {
    for rows in [50, 300, 800] {
      let provider = ChatProvider()
      let surface = provider.mainChatSurfaceReference()
      provider.messages = Self.transcript(rows: rows)
      let live = try XCTUnwrap(provider.messages.last)
      let liveID = live.id
      let liveText = live.text
      let echo = try Self.makeTurn(
        surface: surface, turnID: liveID, status: .streaming,
        content: String(liveText.prefix(liveText.count / 2)),
        contentBlocks: [["type": "text", "id": "\(liveID):text", "text": String(liveText.prefix(liveText.count / 2))]],
        turnSeq: rows + 1)
      // Warm once, then time.
      provider.projectJournalTurns([echo])
      let iterations = 10
      let start = ContinuousClock.now
      for _ in 0..<iterations {
        provider.projectJournalTurns([echo])
      }
      let elapsed = ContinuousClock.now - start
      let perCallMs =
        Double(elapsed.components.attoseconds) / 1e15 / Double(iterations)
        + Double(elapsed.components.seconds) * 1000 / Double(iterations)
      // Attribute the pass: the canonical sort and the citation inheritance
      // are the two whole-transcript steps a no-op echo still runs.
      var sorted = provider.messages
      let sortStart = ContinuousClock.now
      for _ in 0..<iterations {
        sorted = provider.messages
        sorted.sort {
          if $0.createdAt == $1.createdAt { return $0.id < $1.id }
          return $0.createdAt < $1.createdAt
        }
      }
      let sortMs = Self.milliseconds(ContinuousClock.now - sortStart) / Double(iterations)
      var inherited = provider.messages
      let inheritStart = ContinuousClock.now
      for _ in 0..<iterations {
        inherited = provider.messages
        ChatProvider.inheritCitationsAcrossTurns(&inherited)
      }
      let inheritMs = Self.milliseconds(ContinuousClock.now - inheritStart) / Double(iterations)
      print(
        "PROJECTION_COST rows=\(rows) per_echo_ms=\(String(format: "%.2f", perCallMs)) "
          + "sort_ms=\(String(format: "%.2f", sortMs)) inherit_ms=\(String(format: "%.2f", inheritMs))")
      XCTAssertEqual(provider.messages.last?.text, liveText, "the echo behind the live row must not move the text back")
    }
  }

  private static func milliseconds(_ duration: Duration) -> Double {
    Double(duration.components.seconds) * 1000 + Double(duration.components.attoseconds) / 1e15
  }

  private static func transcript(rows: Int) -> [ChatMessage] {
    let base = Date(timeIntervalSince1970: 1_700_000_000)
    var messages: [ChatMessage] = []
    let prose = String(repeating: "A sentence about what was discussed, with a marker [1] and another [2]. ", count: 6)
    for index in 0..<rows {
      let createdAt = base.addingTimeInterval(TimeInterval(index))
      if index % 2 == 0 {
        messages.append(
          ChatMessage(id: "user-\(index)", text: "Question \(index)?", createdAt: createdAt, sender: .user))
      } else {
        let id = "assistant-\(index)"
        let isLast = index == rows - 1
        messages.append(
          ChatMessage(
            id: id,
            text: prose,
            createdAt: createdAt,
            sender: .ai,
            isStreaming: isLast,
            contentBlocks: [
              .text(id: "\(id):text", text: prose),
              .citation(
                id: "\(id):c1",
                reference: ChatCitationReference(
                  ordinal: 1, kind: .conversation, sourceID: "conv-\(index)", title: "Conversation \(index)")),
              .citation(
                id: "\(id):c2",
                reference: ChatCitationReference(
                  ordinal: 2, kind: .memory, sourceID: "mem-\(index)", title: "Memory \(index)")),
            ],
            turnOwner: .mainChat,
            journalStatus: isLast ? .streaming : .completed))
      }
    }
    return messages
  }

  private static func makeTurn(
    surface: AgentSurfaceReference,
    turnID: String,
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
        "role": "assistant",
        "surfaceKind": surface.surfaceKind,
        "externalRefKind": surface.externalRefKind,
        "externalRefId": surface.externalRefId,
        "content": content,
        "origin": "test",
        "status": status.rawValue,
        "contentBlocks": contentBlocks,
        "resources": [],
        "metadataJson": "{}",
        "createdAtMs": 1_700_000_000_000 + Int64(turnSeq) * 1000,
        "updatedAtMs": 1_700_000_000_000 + Int64(turnSeq) * 1000,
      ]))
  }
}
