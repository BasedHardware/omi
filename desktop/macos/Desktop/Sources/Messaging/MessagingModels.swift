import Foundation

struct MessageThread: Identifiable, Equatable, Sendable {
  let id: String
  let providerId: String
  let title: String
  let subtitle: String?
  let lastMessagePreview: String?
  let lastActivity: Date?
  let unreadCount: Int
  let isGroup: Bool
  let hasPendingDraft: Bool
}

struct MessageItem: Identifiable, Equatable, Sendable {
  let id: String
  let text: String
  let isFromMe: Bool
  let senderName: String?
  let timestamp: Date?
}

struct PendingDraftItem: Identifiable, Equatable, Sendable {
  let id: String
  let threadId: String
  let text: String
  let incomingText: String
  let createdAt: Date
}

enum MessageSendResult: Sendable {
  case sent
  case failed(String)
}
