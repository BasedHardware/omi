import Foundation

/// Platform-agnostic message shape consumed by the AI Clone persona/backtest pipeline.
/// Concrete readers (iMessage, Telegram, …) map their own types into this.
struct ImportedMessage: Sendable {
  let isFromMe: Bool
  let text: String
  let date: Date
}

/// Platform-agnostic contact shape. `platform` identifies the source (e.g. "imessage",
/// "telegram") so downstream features can label or branch without knowing the reader type.
struct ImportedContact: Sendable {
  let id: String
  let displayName: String
  let messageCount: Int
  let platform: String
}

/// Loads a contact's message history (newest-first) from whichever reader owns its
/// platform. Shared by the AI Clone page and the app-level send coordinator, which needs
/// history for retrieval indexing and rolling reply context without the page open.
enum AICloneMessageLoader {
  static func loadMessages(
    for contact: ImportedContact, limit: Int = 500
  ) async throws -> [ImportedMessage] {
    switch contact.platform {
    case "telegram":
      return await TelegramImportService.shared.messages(for: contact.id, limit: limit)
    case "whatsapp":
      return await WhatsAppImportService.shared.messages(for: contact.id, limit: limit)
    default:
      let imContact = IMessageContact(
        id: contact.id, displayName: contact.displayName, messageCount: contact.messageCount)
      return try await IMessageReaderService.shared.messages(for: imContact, limit: limit)
        .map { $0.asImportedMessage() }
    }
  }
}
