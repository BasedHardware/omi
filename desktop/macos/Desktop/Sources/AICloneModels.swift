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
