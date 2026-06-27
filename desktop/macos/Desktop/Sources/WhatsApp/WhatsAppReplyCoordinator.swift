import Combine
import Foundation

struct WAIncomingMessage: Equatable, Sendable {
  let id: String
  let chatJid: String
  let senderJid: String
  let senderName: String?
  let text: String
  let fromMe: Bool
  let isGroup: Bool
  let timestamp: Date?

  var displaySender: String {
    senderName?.isEmpty == false ? senderName! : senderJid
  }

  var isStatusOrBroadcast: Bool {
    chatJid.contains("status@broadcast") || senderJid.contains("status@broadcast")
      || chatJid.contains("broadcast") || senderJid.contains("broadcast")
  }

  init?(
    id: String?,
    chatJid: String?,
    senderJid: String?,
    senderName: String?,
    text: String?,
    fromMe: Bool,
    isGroup: Bool,
    timestamp: Date?
  ) {
    guard let chatJid = chatJid?.trimmingCharacters(in: .whitespacesAndNewlines), !chatJid.isEmpty,
      let senderJid = senderJid?.trimmingCharacters(in: .whitespacesAndNewlines), !senderJid.isEmpty,
      let text = text?.trimmingCharacters(in: .whitespacesAndNewlines), !text.isEmpty
    else {
      return nil
    }

    self.id = id?.trimmingCharacters(in: .whitespacesAndNewlines).nilIfEmpty
      ?? "\(chatJid):\(senderJid):\(text.hashValue)"
    self.chatJid = chatJid
    self.senderJid = senderJid
    self.senderName = senderName?.trimmingCharacters(in: .whitespacesAndNewlines).nilIfEmpty
    self.text = text
    self.fromMe = fromMe
    self.isGroup = isGroup || chatJid.contains("@g.us")
    self.timestamp = timestamp
  }

  init?(event: [String: Any]) {
    let message = WAIncomingMessage.messageObject(from: event)
    let chatJid =
      WAIncomingMessage.stringValue(message, keys: ["ChatJID", "chatJid", "chat_jid", "chat", "to", "from"])
      ?? WAIncomingMessage.stringValue(event, keys: ["ChatJID", "chatJid", "chat_jid", "chat", "to", "from"])
    let senderJid =
      WAIncomingMessage.stringValue(message, keys: ["SenderJID", "senderJid", "sender_jid", "sender", "participant", "from"])
      ?? WAIncomingMessage.stringValue(event, keys: ["SenderJID", "senderJid", "sender_jid", "sender", "participant", "from"])
      ?? chatJid
    let id =
      WAIncomingMessage.stringValue(message, keys: ["MsgID", "id", "messageId", "message_id", "clientMessageId"])
      ?? WAIncomingMessage.stringValue(event, keys: ["MsgID", "id", "messageId", "message_id"])
    let senderName =
      WAIncomingMessage.stringValue(message, keys: ["SenderName", "senderName", "sender_name", "pushName", "name", "ChatName"])
      ?? WAIncomingMessage.stringValue(event, keys: ["SenderName", "senderName", "sender_name", "pushName", "name", "ChatName"])
    let text =
      WAIncomingMessage.stringValue(message, keys: ["Text", "DisplayText", "text", "body", "message", "caption"])
      ?? WAIncomingMessage.stringValue(event, keys: ["Text", "DisplayText", "text", "body", "message", "caption"])
    let fromMe =
      WAIncomingMessage.boolValue(message, keys: ["FromMe", "fromMe", "from_me", "isFromMe"])
      ?? WAIncomingMessage.boolValue(event, keys: ["FromMe", "fromMe", "from_me", "isFromMe"])
      ?? false
    let isGroup =
      WAIncomingMessage.boolValue(message, keys: ["isGroup", "is_group", "group"])
      ?? WAIncomingMessage.boolValue(event, keys: ["isGroup", "is_group", "group"])
      ?? false
    let timestamp =
      WAIncomingMessage.dateValue(message, keys: ["Timestamp", "timestamp", "time", "createdAt"])
      ?? WAIncomingMessage.dateValue(event, keys: ["Timestamp", "timestamp", "time", "createdAt"])

    self.init(
      id: id,
      chatJid: chatJid,
      senderJid: senderJid,
      senderName: senderName,
      text: text,
      fromMe: fromMe,
      isGroup: isGroup,
      timestamp: timestamp
    )
  }

  private static func messageObject(from event: [String: Any]) -> [String: Any] {
    if let message = event["message"] as? [String: Any] {
      return message
    }
    if let data = event["data"] as? [String: Any] {
      if let message = data["message"] as? [String: Any] {
        return message
      }
      return data
    }
    return event
  }

  private static func stringValue(_ object: [String: Any], keys: [String]) -> String? {
    for key in keys {
      if let value = object[key] as? String, !value.isEmpty {
        return value
      }
      if let value = object[key] {
        let string = "\(value)"
        if !string.isEmpty {
          return string
        }
      }
    }
    return nil
  }

  private static func boolValue(_ object: [String: Any], keys: [String]) -> Bool? {
    for key in keys {
      if let value = object[key] as? Bool {
        return value
      }
      if let value = object[key] as? String {
        switch value.lowercased() {
        case "true", "1", "yes":
          return true
        case "false", "0", "no":
          return false
        default:
          continue
        }
      }
    }
    return nil
  }

  private static func dateValue(_ object: [String: Any], keys: [String]) -> Date? {
    for key in keys {
      if let seconds = object[key] as? TimeInterval {
        return Date(timeIntervalSince1970: seconds > 10_000_000_000 ? seconds / 1000 : seconds)
      }
      if let string = object[key] as? String {
        if let date = ISO8601DateFormatter().date(from: string) {
          return date
        }
        if let seconds = TimeInterval(string) {
          return Date(timeIntervalSince1970: seconds > 10_000_000_000 ? seconds / 1000 : seconds)
        }
      }
    }
    return nil
  }
}

@MainActor
final class WhatsAppReplyCoordinator: ObservableObject {
  static let shared = WhatsAppReplyCoordinator()

  static let systemPrompt = """
    You draft WhatsApp replies on behalf of the Omi user.

    Rules:
    - Draft as the user, in first person, with a natural WhatsApp tone.
    - Be brief unless the incoming message clearly needs detail.
    - Ground personal facts in tools and context. Never invent facts.
    - If you are unsure, draft a reply that says the user will check and get back.
    - Do not send messages yourself unless explicitly asked through wa_send_message.
    - For this autonomous inbound flow, return only the reply text. No explanations.
    """

  private let bridge = AgentBridge(harnessMode: "piMono")
  @Published private(set) var pendingDrafts: [WhatsAppDraft] = []
  private var processedMessageIDs = Set<String>()
  private var latestDrafts: [String: WhatsAppDraft] = [:]

  private init() {}

  func handle(_ message: WAIncomingMessage) async {
    guard shouldProcess(message) else { return }
    processedMessageIDs.insert(message.id)

    do {
      let draft = try await draftReply(for: message)
      await routeDraft(draft, for: message)
    } catch {
      log("WhatsAppReplyCoordinator: failed to draft reply for \(message.chatJid): \(error.localizedDescription)")
    }
  }

  func latestDraft(for messageID: String) -> WhatsAppDraft? {
    latestDrafts[messageID]
  }

  func approveDraft(id: String, editedText: String? = nil) async -> String {
    guard let draft = pendingDrafts.first(where: { $0.id == id }) else {
      return "Error: WhatsApp draft not found"
    }
    let text = editedText?.trimmingCharacters(in: .whitespacesAndNewlines).nilIfEmpty ?? draft.text
    let result = await ChatToolExecutor.execute(ToolCall(
      name: "wa_send_message",
      arguments: [
        "to": draft.chatJid,
        "message": text,
        "client_message_id": "draft:\(draft.messageID)",
      ],
      thoughtSignature: nil
    ))
    removePendingDraft(id: id)
    appendAudit(for: draft.withText(text), outcome: "draft_sent", reason: result)
    return result
  }

  func dismissDraft(id: String) {
    guard let draft = pendingDrafts.first(where: { $0.id == id }) else { return }
    removePendingDraft(id: id)
    appendAudit(for: draft, outcome: "dismissed", reason: nil)
  }

  func alwaysAutoReplyAndApproveDraft(id: String) async -> String {
    guard let draft = pendingDrafts.first(where: { $0.id == id }) else {
      return "Error: WhatsApp draft not found"
    }
    WhatsAppReplySettings.shared.addAllowlistedJid(draft.senderJid)
    return await approveDraft(id: id)
  }

  private func shouldProcess(_ message: WAIncomingMessage) -> Bool {
    guard WhatsAppReplySettings.shared.mode != .off else { return false }
    guard !WhatsAppReplySettings.shared.killSwitchEnabled else { return false }
    guard !message.fromMe else { return false }
    guard !message.isStatusOrBroadcast else { return false }
    guard !processedMessageIDs.contains(message.id) else { return false }
    return true
  }

  private func routeDraft(_ draft: WhatsAppDraft, for message: WAIncomingMessage) async {
    let decision = WhatsAppReplySettings.shared.autoDecision(for: message, draftText: draft.text)
    switch decision {
    case .ignore(let reason):
      appendAudit(for: draft, outcome: "ignored", reason: reason)
      log("WhatsAppReplyCoordinator: ignored message \(message.id), reason=\(reason)")

    case .draft(let reason):
      enqueueDraft(draft)
      appendAudit(for: draft, outcome: "drafted", reason: reason)
      log("WhatsAppReplyCoordinator: drafted reply for \(message.chatJid), reason=\(reason): \(draft.text.prefix(160))")

    case .auto:
      let result = await ChatToolExecutor.execute(ToolCall(
        name: "wa_send_message",
        arguments: [
          "to": message.chatJid,
          "message": draft.text,
          "client_message_id": "auto:\(message.id)",
        ],
        thoughtSignature: nil
      ))
      WhatsAppReplySettings.shared.markAutoSent(to: message.senderJid)
      appendAudit(for: draft, outcome: "auto_sent", reason: result)
      log("WhatsAppReplyCoordinator: auto-sent reply for \(message.chatJid): \(result.prefix(200))")
    }
  }

  private func appendAudit(for draft: WhatsAppDraft, outcome: String, reason: String?) {
    WhatsAppReplySettings.shared.appendAuditEntry(WhatsAppAuditEntry(
      id: UUID().uuidString,
      createdAt: Date(),
      chatJid: draft.chatJid,
      senderJid: draft.senderJid,
      messageID: draft.messageID,
      text: draft.text,
      outcome: outcome,
      reason: reason
    ))
  }

  private func enqueueDraft(_ draft: WhatsAppDraft) {
    latestDrafts[draft.messageID] = draft
    pendingDrafts.removeAll { $0.messageID == draft.messageID }
    pendingDrafts.insert(draft, at: 0)
    showDraftNotification(draft)
  }

  private func removePendingDraft(id: String) {
    pendingDrafts.removeAll { $0.id == id }
  }

  private func showDraftNotification(_ draft: WhatsAppDraft) {
    let sender = draft.senderName?.nilIfEmpty ?? draft.senderJid
    FloatingControlBarManager.shared.showNotification(
      title: "WhatsApp draft for \(sender)",
      message: draft.text,
      assistantId: "whatsapp",
      sound: .default,
      context: FloatingBarNotificationContext(
        sourceTitle: "WhatsApp",
        assistantId: "whatsapp",
        sourceApp: "WhatsApp",
        windowTitle: nil,
        contextSummary: "Incoming: \(draft.incomingText)",
        currentActivity: nil,
        reasoning: "Omi drafted a WhatsApp reply for approval.",
        detail: "Open Settings -> WhatsApp to send, edit, dismiss, or always auto-reply to this sender."
      )
    )
  }

  private func draftReply(for message: WAIncomingMessage) async throws -> WhatsAppDraft {
    let prompt = buildPrompt(for: message)
    let result = try await bridge.query(
      prompt: prompt,
      systemPrompt: "\(Self.systemPrompt)\n\n\(WhatsAppToneProfile.shared.styleGuide())",
      sessionKey: "whatsapp-reply-\(message.chatJid)",
      surfaceKind: "whatsapp",
      externalRefKind: "message",
      externalRefId: message.id,
      legacyClientScope: "whatsapp",
      mode: "ask",
      onTextDelta: { _ in },
      onToolCall: { _, name, input in
        let toolCall = ToolCall(name: name, arguments: input, thoughtSignature: nil)
        return await ChatToolExecutor.execute(toolCall)
      },
      onToolActivity: { name, status, _, _ in
        log("WhatsAppReplyCoordinator: tool \(name) \(status)")
      },
      onThinkingDelta: { _ in },
      onToolResultDisplay: { _, name, output in
        log("WhatsAppReplyCoordinator: tool result \(name): \(output.prefix(200))")
      }
    )

    return WhatsAppDraft(
      id: UUID().uuidString,
      messageID: message.id,
      chatJid: message.chatJid,
      senderJid: message.senderJid,
      senderName: message.senderName,
      incomingText: message.text,
      text: result.text.trimmingCharacters(in: .whitespacesAndNewlines),
      createdAt: Date(),
      mode: "draft"
    )
  }

  private func buildPrompt(for message: WAIncomingMessage) -> String {
    """
    Incoming WhatsApp message:
    Sender: \(message.displaySender)
    Sender JID: \(message.senderJid)
    Chat JID: \(message.chatJid)
    Chat type: \(message.isGroup ? "group" : "direct")
    Message ID: \(message.id)
    Text: \(message.text)

    First read recent thread context with wa_read_thread for this chat when useful.
    Use Omi memory/conversation/task tools if the message asks about personal facts, plans, availability, or commitments.
    Draft the best reply as the user. Return only the reply text.
    """
  }
}

struct WhatsAppDraft: Identifiable, Equatable, Sendable {
  let id: String
  let messageID: String
  let chatJid: String
  let senderJid: String
  let senderName: String?
  let incomingText: String
  let text: String
  let createdAt: Date
  let mode: String

  func withText(_ newText: String) -> WhatsAppDraft {
    WhatsAppDraft(
      id: id,
      messageID: messageID,
      chatJid: chatJid,
      senderJid: senderJid,
      senderName: senderName,
      incomingText: incomingText,
      text: newText,
      createdAt: createdAt,
      mode: mode
    )
  }
}

private extension String {
  var nilIfEmpty: String? {
    isEmpty ? nil : self
  }
}
