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
      WAIncomingMessage.stringValue(message, keys: ["ChatJID", "Chat", "chatJid", "chat_jid", "chat", "to", "from"])
      ?? WAIncomingMessage.stringValue(event, keys: ["ChatJID", "Chat", "chatJid", "chat_jid", "chat", "to", "from"])
    let senderJid =
      WAIncomingMessage.stringValue(message, keys: ["SenderJID", "senderJid", "sender_jid", "sender", "participant", "from"])
      ?? WAIncomingMessage.stringValue(event, keys: ["SenderJID", "senderJid", "sender_jid", "sender", "participant", "from"])
      ?? chatJid
    let id =
      WAIncomingMessage.stringValue(message, keys: ["MsgID", "ID", "id", "messageId", "message_id", "clientMessageId"])
      ?? WAIncomingMessage.stringValue(event, keys: ["MsgID", "ID", "id", "messageId", "message_id"])
    let senderName =
      WAIncomingMessage.stringValue(message, keys: ["SenderName", "PushName", "senderName", "sender_name", "pushName", "name", "ChatName"])
      ?? WAIncomingMessage.stringValue(event, keys: ["SenderName", "PushName", "senderName", "sender_name", "pushName", "name", "ChatName"])
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

  @MainActor
  func withCanonicalJids() -> WAIncomingMessage {
    WAIncomingMessage(
      id: id,
      chatJid: WhatsAppContactResolver.shared.canonicalJid(for: chatJid),
      senderJid: WhatsAppContactResolver.shared.canonicalJid(for: senderJid),
      senderName: senderName,
      text: text,
      fromMe: fromMe,
      isGroup: isGroup,
      timestamp: timestamp
    ) ?? self
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
      if let nested = object[key] as? [String: Any],
        let value = jidString(from: nested) ?? stringValue(nested, keys: ["JID", "jid", "ID", "id", "Raw", "raw"]),
        !value.isEmpty
      {
        return value
      }
      if let value = object[key] {
        if let number = value as? NSNumber {
          return number.stringValue
        }
        if String(describing: type(of: value)).contains("Dictionary") {
          continue
        }
        let string = "\(value)"
        if !string.isEmpty {
          return string
        }
      }
    }
    return nil
  }

  private static func jidString(from object: [String: Any]) -> String? {
    if let jid = object["JID"] as? String, !jid.isEmpty {
      return jid
    }
    if let jid = object["jid"] as? String, !jid.isEmpty {
      return jid
    }
    let user = (object["User"] as? String) ?? (object["user"] as? String)
    let server = (object["Server"] as? String) ?? (object["server"] as? String)
    if let user, !user.isEmpty, let server, !server.isEmpty {
      return "\(user)@\(server)"
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
    - Use WhatsApp thread/search tools for chat-specific history.
    - Use Omi memory and conversation tools for personal facts, prior events, relationships, and commitments.
    - Use check_calendar_availability before answering whether the user is free at a specific time.
    - If you are unsure, draft a reply that says the user will check and get back.
    - This draft path is read-only: you cannot send WhatsApp messages or mutate tasks/memories/calendar. Only draft the reply text.
    - For this autonomous inbound flow, return only the reply text. No explanations.
    """

  private let bridge = AgentBridge(harnessMode: "piMono")
  @Published private(set) var pendingDrafts: [WhatsAppDraft] = []
  @Published private(set) var lastDraftFailure: String?
  private var processedMessageIDs = Set<String>()
  private var processedMessageIDOrder: [String] = []
  private var queuedMessageIDs = Set<String>()
  private var processingChatJids = Set<String>()
  private var queuedMessagesByChatJid: [String: [WAIncomingMessage]] = [:]
  private var latestDrafts: [String: WhatsAppDraft] = [:]
  private var latestDraftMessageIDOrder: [String] = []
  private let maxProcessedMessageIDs = 1_000
  private let maxLatestDrafts = 500

  private init() {}

  nonisolated static func visibleReplyText(from rawText: String) -> String {
    let trimmed = rawText.trimmingCharacters(in: .whitespacesAndNewlines)
    guard !trimmed.isEmpty else { return trimmed }

    let paragraphs = trimmed
      .components(separatedBy: "\n\n")
      .map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }
      .filter { !$0.isEmpty }
    if paragraphs.count > 1, paragraphs.dropLast().contains(where: isExplanationParagraph) {
      return stripReplyLabel(from: paragraphs.last ?? trimmed)
    }

    let lines = trimmed.components(separatedBy: .newlines)
    let replyLines = lines
      .map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }
      .filter { !$0.isEmpty && !isExplanationParagraph($0) }
    if !replyLines.isEmpty, replyLines.count < lines.count {
      return stripReplyLabel(from: replyLines.joined(separator: "\n"))
    }

    return stripReplyLabel(from: trimmed)
  }

  func handle(_ message: WAIncomingMessage) async {
    guard shouldProcess(message), !queuedMessageIDs.contains(message.id) else { return }
    queuedMessageIDs.insert(message.id)
    queuedMessagesByChatJid[message.chatJid, default: []].append(message)

    guard !processingChatJids.contains(message.chatJid) else { return }
    await processQueuedMessages(for: message.chatJid)
  }

  private func processQueuedMessages(for chatJid: String) async {
    processingChatJids.insert(chatJid)
    defer { processingChatJids.remove(chatJid) }

    while var queue = queuedMessagesByChatJid[chatJid], !queue.isEmpty {
      let message = queue.removeFirst()
      queuedMessagesByChatJid[chatJid] = queue
      queuedMessageIDs.remove(message.id)
      await process(message)
    }

    queuedMessagesByChatJid[chatJid] = nil
  }

  private func process(_ message: WAIncomingMessage) async {
    guard shouldProcess(message) else { return }
    WhatsAppContactResolver.shared.remember(
      jid: message.senderJid,
      contactName: message.senderName,
      whatsappName: message.senderName
    )
    WhatsAppContactResolver.shared.remember(jid: message.chatJid, whatsappName: message.senderName)

    if let preDraftDecision = WhatsAppReplySettings.shared.preDraftDecision(for: message) {
      if case .ignore(let reason) = preDraftDecision {
        appendAuditMessage(for: message, outcome: "ignored", reason: reason)
        markProcessed(message.id)
        log("WhatsAppReplyCoordinator: ignored message \(message.id) before drafting, reason=\(reason)")
        return
      }
    }

    do {
      let draft = try await draftReply(for: message)
      await routeDraft(draft, for: message)
      markProcessed(message.id)
    } catch {
      let reason = error.localizedDescription
      let sender = WhatsAppContactResolver.shared.displayName(for: message.senderJid, fallback: message.senderName)
      lastDraftFailure = "Could not draft a WhatsApp reply for \(sender): \(reason)"
      appendAuditMessage(for: message, outcome: "draft_failed", reason: reason)
      log("WhatsAppReplyCoordinator: failed to draft reply for \(redactedJidLabel(message.chatJid)): \(reason)")
    }
  }

  func latestDraft(for messageID: String) -> WhatsAppDraft? {
    latestDrafts[messageID]
  }

  func approveDraft(id: String, editedText: String? = nil) async -> String {
    guard let draft = pendingDrafts.first(where: { $0.id == id }) else {
      return "Error: WhatsApp draft not found"
    }
    let text = Self.visibleReplyText(
      from: editedText?.trimmingCharacters(in: .whitespacesAndNewlines).nilIfEmpty ?? draft.text
    )
    let routedDraft = draft.withCanonicalJids()
    let result = await ChatToolExecutor.execute(ToolCall(
      name: "wa_send_message",
      arguments: [
        "to": routedDraft.chatJid,
        "message": text,
        "client_message_id": "draft:\(routedDraft.messageID)",
      ],
      thoughtSignature: nil
    ))
    removePendingDraft(id: id)
    appendAudit(for: routedDraft.withText(text), outcome: "draft_sent", reason: result)
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
    let routedDraft = draft.withCanonicalJids()
    WhatsAppReplySettings.shared.addAllowlistedJid(routedDraft.senderJid)
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
    let draft = draft.withText(Self.visibleReplyText(from: draft.text)).withCanonicalJids()
    let message = message.withCanonicalJids()
    let decision = WhatsAppReplySettings.shared.autoDecision(for: message, draftText: draft.text)
    switch decision {
    case .ignore(let reason):
      appendAudit(for: draft, outcome: "ignored", reason: reason)
      log("WhatsAppReplyCoordinator: ignored message \(message.id), reason=\(reason)")

    case .draft(let reason):
      enqueueDraft(draft)
      appendAudit(for: draft, outcome: "drafted", reason: reason)
      log("WhatsAppReplyCoordinator: drafted reply for \(redactedJidLabel(message.chatJid)), reason=\(reason), draftBytes=\(draft.text.utf8.count)")

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
      log("WhatsAppReplyCoordinator: auto-sent reply for \(redactedJidLabel(message.chatJid)), resultBytes=\(result.utf8.count)")
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

  private func appendAuditMessage(for message: WAIncomingMessage, outcome: String, reason: String?) {
    WhatsAppReplySettings.shared.appendAuditEntry(WhatsAppAuditEntry(
      id: UUID().uuidString,
      createdAt: Date(),
      chatJid: message.chatJid,
      senderJid: message.senderJid,
      messageID: message.id,
      text: message.text,
      outcome: outcome,
      reason: reason
    ))
  }

  private func enqueueDraft(_ draft: WhatsAppDraft) {
    lastDraftFailure = nil
    if latestDrafts[draft.messageID] == nil {
      latestDraftMessageIDOrder.append(draft.messageID)
    }
    latestDrafts[draft.messageID] = draft
    pruneLatestDrafts()
    pendingDrafts.removeAll { $0.messageID == draft.messageID }
    pendingDrafts.insert(draft, at: 0)
    showDraftNotification(draft)
  }

  private func removePendingDraft(id: String) {
    pendingDrafts.removeAll { $0.id == id }
  }

  private func markProcessed(_ messageID: String) {
    guard processedMessageIDs.insert(messageID).inserted else { return }
    processedMessageIDOrder.append(messageID)
    guard processedMessageIDOrder.count > maxProcessedMessageIDs else { return }
    let overflow = processedMessageIDOrder.count - maxProcessedMessageIDs
    for expired in processedMessageIDOrder.prefix(overflow) {
      processedMessageIDs.remove(expired)
    }
    processedMessageIDOrder.removeFirst(overflow)
  }

  private func pruneLatestDrafts() {
    guard latestDraftMessageIDOrder.count > maxLatestDrafts else { return }
    let overflow = latestDraftMessageIDOrder.count - maxLatestDrafts
    for expired in latestDraftMessageIDOrder.prefix(overflow) {
      latestDrafts.removeValue(forKey: expired)
    }
    latestDraftMessageIDOrder.removeFirst(overflow)
  }

  private func showDraftNotification(_ draft: WhatsAppDraft) {
    let sender = WhatsAppContactResolver.shared.displayName(for: draft.senderJid, fallback: draft.senderName)
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
        detail: "Open Messages to send, edit, dismiss, or always auto-reply to this sender."
      )
    )
  }

  private func draftReply(for message: WAIncomingMessage) async throws -> WhatsAppDraft {
    let prompt = await buildPrompt(for: message)
    let senderName = WhatsAppContactResolver.shared.displayName(for: message.senderJid, fallback: message.senderName)
    let result = try await bridge.query(
      prompt: prompt,
      systemPrompt: "\(Self.systemPrompt)\n\n\(WhatsAppToneProfile.shared.styleGuide())",
      surface: AgentSurfaceReference(
        surfaceKind: "whatsapp",
        externalRefKind: "message",
        externalRefId: message.id
      ),
      mode: "ask",
      onTextDelta: { _ in },
      onToolCall: { _, name, input in
        let toolCall = ToolCall(name: name, arguments: input, thoughtSignature: nil)
        // Draft generation is read-only by construction — wa_send_message and
        // other write tools are denied even if the model requests them.
        return await ChatToolExecutor.execute(toolCall, mode: .draftReadOnly)
      },
      onToolActivity: { name, status, _, _ in
        log("WhatsAppReplyCoordinator: tool \(name) \(status)")
      },
      onThinkingDelta: { _ in },
      onToolResultDisplay: { _, _, _ in }
    )

    let replyText = Self.visibleReplyText(from: result.text)
    return WhatsAppDraft(
      id: UUID().uuidString,
      messageID: message.id,
      chatJid: message.chatJid,
      senderJid: message.senderJid,
      senderName: senderName,
      incomingText: message.text,
      text: replyText,
      createdAt: Date(),
      mode: "draft"
    )
  }

  private func buildPrompt(for message: WAIncomingMessage) async -> String {
    let recentThreadContext = await recentThreadContext(for: message)
    let senderDisplayName = WhatsAppContactResolver.shared.displayName(for: message.senderJid, fallback: message.senderName)
    let chatDisplayName = WhatsAppContactResolver.shared.displayName(for: message.chatJid, fallback: message.senderName)
    return """
    Recent WhatsApp thread context (last 6 synced messages, oldest to newest):
    \(recentThreadContext)

    Incoming WhatsApp message:
    Sender: \(senderDisplayName)
    Sender JID: \(message.senderJid)
    Chat: \(chatDisplayName)
    Chat JID: \(message.chatJid)
    Chat type: \(message.isGroup ? "group" : "direct")
    Message ID: \(message.id)
    Text: \(message.text)

    Use the recent thread context above first.
    Only call wa_read_thread if the reply needs older messages, more context, or exact prior details not visible above.
    Use Omi memory/conversation/task search tools if the message asks about personal facts, plans, availability, or commitments.
    Check calendar availability before answering scheduling questions like whether the user is free at a specific time.
    Do not send messages or mutate tasks/memories/calendar while drafting.
    Draft the best reply as the user. Return exactly the WhatsApp message body and nothing else.
    Do not include reasoning, context summaries, labels, or explanations.
    """
  }

  private func redactedJidLabel(_ jid: String) -> String {
    let normalized = jid.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
    let parts = normalized.split(separator: "@", maxSplits: 1, omittingEmptySubsequences: false)
    let server = parts.count == 2 ? String(parts[1]) : "unknown"
    let kind: String
    if server == "g.us" || normalized.contains("@g.us") {
      kind = "group"
    } else if server == "lid" || normalized.contains("@lid") {
      kind = "lid"
    } else {
      kind = "user"
    }
    return "\(kind)@\(server)#\(String(normalized.hashValue, radix: 16))"
  }

  private func recentThreadContext(for message: WAIncomingMessage) async -> String {
    let result = await ChatToolExecutor.execute(ToolCall(
      name: "wa_read_thread",
      arguments: [
        "chat_jid": message.chatJid,
        "limit": 6,
        "ascending": true,
      ],
      thoughtSignature: nil
    ))

    if result.hasPrefix("Error:") {
      log("WhatsAppReplyCoordinator: failed to read recent thread context: \(result.prefix(200))")
      return "Unavailable: \(result)"
    }
    return result.isEmpty ? "[]" : result
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

  @MainActor
  func withCanonicalJids() -> WhatsAppDraft {
    WhatsAppDraft(
      id: id,
      messageID: messageID,
      chatJid: WhatsAppContactResolver.shared.canonicalJid(for: chatJid),
      senderJid: WhatsAppContactResolver.shared.canonicalJid(for: senderJid),
      senderName: senderName,
      incomingText: incomingText,
      text: text,
      createdAt: createdAt,
      mode: mode
    )
  }
}

private func isExplanationParagraph(_ value: String) -> Bool {
  let lower = value.lowercased()
  return lower.hasPrefix("no clear context")
    || lower.hasPrefix("context:")
    || lower.hasPrefix("reason:")
    || lower.hasPrefix("reasoning:")
    || lower.hasPrefix("explanation:")
    || lower.contains("i'll draft")
    || lower.contains("i’ll draft")
    || lower.contains("likely a reply")
    || lower.contains("reply to a prior conversation")
    || lower.contains("based on the context")
}

private func stripReplyLabel(from value: String) -> String {
  let trimmed = value.trimmingCharacters(in: .whitespacesAndNewlines)
  for prefix in ["Reply:", "Draft reply:", "Message:", "WhatsApp reply:"] {
    if trimmed.lowercased().hasPrefix(prefix.lowercased()) {
      return String(trimmed.dropFirst(prefix.count)).trimmingCharacters(in: .whitespacesAndNewlines)
    }
  }
  return trimmed
}

private extension String {
  var nilIfEmpty: String? {
    isEmpty ? nil : self
  }
}
