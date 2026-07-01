import Foundation

/// Orchestrates an iMessage sync: read new messages, group them into threads,
/// resolve contact names, push to the backend, and advance the cursor only after
/// a successful push (so a failed upload is retried next time).
actor IMessageSyncCoordinator {
  static let shared = IMessageSyncCoordinator()

  struct SyncOutcome: Sendable {
    let messagesIngested: Int
    let peopleUpserted: Int
    let conversationsCreated: Int
  }

  func sync(backfillDays: Int = 90) async throws -> SyncOutcome {
    let (records, maxROWID) = try await IMessageReaderService.shared.readNewMessages(
      backfillDays: backfillDays)
    guard !records.isEmpty else {
      return SyncOutcome(messagesIngested: 0, peopleUpserted: 0, conversationsCreated: 0)
    }

    var byChat: [String: [IMessageRecord]] = [:]
    for record in records {
      byChat[record.chatGUID, default: []].append(record)
    }

    let iso = ISO8601DateFormatter()
    iso.formatOptions = [.withInternetDateTime, .withFractionalSeconds]

    var threads: [IMessageThreadPayload] = []
    for (chatGUID, recs) in byChat {
      // Group chats use a ";+;" GUID or a "chat…" identifier; 1:1 use ";-;".
      let isGroup =
        chatGUID.contains(";+;") || (recs.first?.chatIdentifier?.hasPrefix("chat") ?? false)

      var displayName: String? = recs.first?.chatDisplayName
      if !isGroup {
        let handle = recs.compactMap { $0.isFromMe ? nil : $0.handle }.first
        if let handle {
          displayName =
            await IMessageContactResolver.shared.displayName(for: handle)
            ?? recs.first?.chatDisplayName ?? handle
        }
      }

      let messages = recs.map { r in
        IMessageMessagePayload(
          guid: r.guid,
          text: r.text,
          isFromMe: r.isFromMe,
          timestamp: iso.string(from: r.date),
          handle: r.isFromMe ? nil : r.handle
        )
      }

      threads.append(
        IMessageThreadPayload(
          chatGUID: chatGUID,
          chatIdentifier: recs.first?.chatIdentifier,
          displayName: displayName,
          isGroup: isGroup,
          messages: messages
        ))
    }

    let response = try await APIClient.shared.imessageIngest(threads: threads, lastRowID: maxROWID)
    await IMessageReaderService.shared.setLastProcessedROWID(maxROWID)

    return SyncOutcome(
      messagesIngested: response.messagesIngested,
      peopleUpserted: response.peopleUpserted,
      conversationsCreated: response.conversationsCreated
    )
  }
}
