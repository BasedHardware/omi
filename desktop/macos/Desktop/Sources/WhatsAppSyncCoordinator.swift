import Foundation

/// Orchestrates a WhatsApp sync: read new messages, group them into threads,
/// resolve contact names, push to the backend, and advance the client-side `Z_PK`
/// cursor only after a successful push (so a failed upload is retried next time).
actor WhatsAppSyncCoordinator {
  static let shared = WhatsAppSyncCoordinator()

  struct SyncOutcome: Sendable {
    let messagesIngested: Int
    let peopleUpserted: Int
    let conversationsCreated: Int
  }

  func sync(backfillDays: Int = 90) async throws -> SyncOutcome {
    let (records, maxZPK) = try await WhatsAppReaderService.shared.readNewMessages(
      backfillDays: backfillDays)
    guard !records.isEmpty else {
      return SyncOutcome(messagesIngested: 0, peopleUpserted: 0, conversationsCreated: 0)
    }

    var byChat: [String: [WhatsAppRecord]] = [:]
    for record in records {
      byChat[record.chatID, default: []].append(record)
    }

    var threads: [WhatsAppThreadPayload] = []
    for (chatID, recs) in byChat {
      let isGroup = recs.first?.isGroup ?? chatID.hasSuffix("@g.us")

      var displayName: String? = recs.first?.chatDisplayName
      if !isGroup {
        // Resolve the 1:1 counterparty's Contacts name from the first inbound handle.
        if let handle = recs.compactMap({ $0.isFromMe ? nil : $0.handle }).first {
          displayName =
            await IMessageContactResolver.shared.displayName(for: handle)
            ?? recs.first?.chatDisplayName ?? handle
        }
      }

      let messages = recs.map { r in
        WhatsAppMessagePayload(
          messageId: r.messageId,
          text: r.text,
          isFromMe: r.isFromMe,
          timestamp: r.date,
          handle: r.isFromMe ? nil : r.handle
        )
      }

      threads.append(
        WhatsAppThreadPayload(
          chatID: chatID,
          displayName: displayName,
          isGroup: isGroup,
          messages: messages
        ))
    }

    let response = try await APIClient.shared.whatsappIngest(threads: threads)
    // Advance the client-side cursor only after a successful push.
    await WhatsAppReaderService.shared.setLastProcessedZPK(maxZPK)

    return SyncOutcome(
      messagesIngested: response.messagesIngested,
      peopleUpserted: response.peopleUpserted,
      conversationsCreated: response.conversationsCreated
    )
  }
}
