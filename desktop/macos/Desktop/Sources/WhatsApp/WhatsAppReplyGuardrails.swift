import Foundation

enum WhatsAppReplyMode: String, CaseIterable, Identifiable, Sendable {
  case off
  case draft
  case auto

  var id: String { rawValue }

  var title: String {
    switch self {
    case .off:
      return "Off"
    case .draft:
      return "Draft"
    case .auto:
      return "Auto"
    }
  }
}

struct WhatsAppAuditEntry: Codable, Identifiable, Equatable, Sendable {
  let id: String
  let createdAt: Date
  let chatJid: String
  let senderJid: String
  let messageID: String?
  let text: String
  let outcome: String
  let reason: String?
}

@MainActor
final class WhatsAppReplySettings: ObservableObject {
  static let shared = WhatsAppReplySettings()

  @Published var mode: WhatsAppReplyMode {
    didSet { defaults.set(mode.rawValue, forKey: Keys.mode) }
  }
  @Published var killSwitchEnabled: Bool {
    didSet { defaults.set(killSwitchEnabled, forKey: Keys.killSwitchEnabled) }
  }
  @Published var allowlistedJids: Set<String> {
    didSet { defaults.set(Array(allowlistedJids).sorted(), forKey: Keys.allowlistedJids) }
  }
  @Published var rateLimitPerHour: Int {
    didSet { defaults.set(rateLimitPerHour, forKey: Keys.rateLimitPerHour) }
  }
  @Published var quietHoursEnabled: Bool {
    didSet { defaults.set(quietHoursEnabled, forKey: Keys.quietHoursEnabled) }
  }
  @Published var quietHoursStart: Int {
    didSet { defaults.set(quietHoursStart, forKey: Keys.quietHoursStart) }
  }
  @Published var quietHoursEnd: Int {
    didSet { defaults.set(quietHoursEnd, forKey: Keys.quietHoursEnd) }
  }
  @Published var toneMatchEnabled: Bool {
    didSet { defaults.set(toneMatchEnabled, forKey: Keys.toneMatchEnabled) }
  }

  private let defaults: UserDefaults
  private var autoSendHistory: [String: [Date]] = [:]
  private var sentClientMessageIDs = Set<String>()
  private var sentClientMessageIDOrder: [String] = []
  private let maxSentClientMessageIDs = 1_000

  private enum Keys {
    static let mode = "whatsapp.reply.mode"
    static let killSwitchEnabled = "whatsapp.reply.killSwitchEnabled"
    static let allowlistedJids = "whatsapp.reply.allowlistedJids"
    static let rateLimitPerHour = "whatsapp.reply.rateLimitPerHour"
    static let quietHoursEnabled = "whatsapp.reply.quietHoursEnabled"
    static let quietHoursStart = "whatsapp.reply.quietHoursStart"
    static let quietHoursEnd = "whatsapp.reply.quietHoursEnd"
    static let toneMatchEnabled = "whatsapp.reply.toneMatchEnabled"
  }

  init(defaults: UserDefaults = .standard) {
    self.defaults = defaults
    self.mode = WhatsAppReplyMode(rawValue: defaults.string(forKey: Keys.mode) ?? "") ?? .draft
    self.killSwitchEnabled = defaults.bool(forKey: Keys.killSwitchEnabled)
    self.allowlistedJids = Set(defaults.stringArray(forKey: Keys.allowlistedJids) ?? [])
    let storedRateLimit = defaults.integer(forKey: Keys.rateLimitPerHour)
    self.rateLimitPerHour = storedRateLimit > 0 ? storedRateLimit : 3
    let storedQuietStart = defaults.object(forKey: Keys.quietHoursStart) as? Int
    let storedQuietEnd = defaults.object(forKey: Keys.quietHoursEnd) as? Int
    self.quietHoursEnabled = defaults.bool(forKey: Keys.quietHoursEnabled)
    self.quietHoursStart = storedQuietStart ?? 22
    self.quietHoursEnd = storedQuietEnd ?? 7
    self.toneMatchEnabled = defaults.object(forKey: Keys.toneMatchEnabled) as? Bool ?? true
  }

  func addAllowlistedJid(_ jid: String) {
    let normalized = normalizeJid(jid)
    guard !normalized.isEmpty else { return }
    allowlistedJids.insert(normalized)
  }

  func removeAllowlistedJid(_ jid: String) {
    allowlistedJids.remove(normalizeJid(jid))
  }

  func canAttemptManualSend(clientMessageID: String?) -> WhatsAppSendDecision {
    if killSwitchEnabled {
      return .blocked("WhatsApp kill switch is enabled")
    }
    if let clientMessageID, !clientMessageID.isEmpty {
      guard !sentClientMessageIDs.contains(clientMessageID) else {
        return .duplicate
      }
      sentClientMessageIDs.insert(clientMessageID)
      sentClientMessageIDOrder.append(clientMessageID)
      pruneSentClientMessageIDs()
    }
    return .allowed
  }

  func preDraftDecision(for message: WAIncomingMessage) -> WhatsAppAutoDecision? {
    guard !killSwitchEnabled else {
      return .ignore(reason: "kill_switch")
    }
    guard mode != .off else {
      return .ignore(reason: "mode_off")
    }
    guard !message.fromMe, !message.isStatusOrBroadcast else {
      return .ignore(reason: "loop_prevention")
    }
    return nil
  }

  func autoDecision(for message: WAIncomingMessage, draftText: String) -> WhatsAppAutoDecision {
    guard !killSwitchEnabled else {
      return .ignore(reason: "kill_switch")
    }
    guard mode != .off else {
      return .ignore(reason: "mode_off")
    }
    guard !message.fromMe, !message.isStatusOrBroadcast else {
      return .ignore(reason: "loop_prevention")
    }
    guard !message.isGroup else {
      return .draft(reason: "group_chat")
    }
    guard allowlistedJids.contains(normalizeJid(message.senderJid))
      || allowlistedJids.contains(normalizeJid(message.chatJid))
    else {
      return .draft(reason: "not_allowlisted")
    }
    if isQuietHoursActive() {
      return .draft(reason: "quiet_hours")
    }
    if containsSensitiveContent(message.text) || containsSensitiveContent(draftText) {
      return .draft(reason: "sensitive_content")
    }
    guard canAutoSend(to: message.senderJid) else {
      return .draft(reason: "rate_limited")
    }
    return .auto
  }

  func markAutoSent(to jid: String) {
    let normalized = normalizeJid(jid)
    var history = autoSendHistory[normalized, default: []]
    let cutoff = Date().addingTimeInterval(-3600)
    history = history.filter { $0 >= cutoff }
    history.append(Date())
    autoSendHistory[normalized] = history
  }

  func recentAuditEntries(limit: Int = 20) -> [WhatsAppAuditEntry] {
    let boundedLimit = max(1, min(limit, 200))
    let url = auditLogURL()
    guard let text = tailText(from: url, maxBytes: max(64 * 1024, boundedLimit * 4096)) else {
      return []
    }
    let decoder = JSONDecoder()
    decoder.dateDecodingStrategy = .iso8601
    return text.split(separator: "\n").suffix(boundedLimit).compactMap { line in
      guard let data = String(line).data(using: .utf8) else { return nil }
      return try? decoder.decode(WhatsAppAuditEntry.self, from: data)
    }
    .reversed()
  }

  func appendAuditEntry(_ entry: WhatsAppAuditEntry) {
    let url = auditLogURL()
    do {
      try FileManager.default.createDirectory(at: url.deletingLastPathComponent(), withIntermediateDirectories: true)
      let encoder = JSONEncoder()
      encoder.dateEncodingStrategy = .iso8601
      let data = try encoder.encode(entry)
      if !FileManager.default.fileExists(atPath: url.path) {
        FileManager.default.createFile(atPath: url.path, contents: nil)
      }
      let handle = try FileHandle(forWritingTo: url)
      defer { try? handle.close() }
      try handle.seekToEnd()
      try handle.write(contentsOf: data + Data("\n".utf8))
    } catch {
      log("WhatsAppReplySettings: failed to append audit entry: \(error.localizedDescription)")
    }
  }

  private func canAutoSend(to jid: String) -> Bool {
    let normalized = normalizeJid(jid)
    let cutoff = Date().addingTimeInterval(-3600)
    let history = autoSendHistory[normalized, default: []].filter { $0 >= cutoff }
    autoSendHistory[normalized] = history
    return history.count < max(rateLimitPerHour, 1)
  }

  private func pruneSentClientMessageIDs() {
    guard sentClientMessageIDOrder.count > maxSentClientMessageIDs else { return }
    let overflow = sentClientMessageIDOrder.count - maxSentClientMessageIDs
    let expired = sentClientMessageIDOrder.prefix(overflow)
    for id in expired {
      sentClientMessageIDs.remove(id)
    }
    sentClientMessageIDOrder.removeFirst(overflow)
  }

  private func tailText(from url: URL, maxBytes: Int) -> String? {
    guard let handle = try? FileHandle(forReadingFrom: url) else { return nil }
    defer { try? handle.close() }
    let size = (try? handle.seekToEnd()) ?? 0
    let offset = size > UInt64(maxBytes) ? size - UInt64(maxBytes) : 0
    try? handle.seek(toOffset: offset)
    var data = handle.readDataToEndOfFile()
    if offset > 0, let newline = data.firstIndex(of: UInt8(ascii: "\n")) {
      data = data[data.index(after: newline)...]
    }
    return String(data: data, encoding: .utf8)
  }

  func isQuietHoursActive(at date: Date = Date()) -> Bool {
    guard quietHoursEnabled else { return false }
    let hour = Calendar.current.component(.hour, from: date)
    let start = min(max(quietHoursStart, 0), 23)
    let end = min(max(quietHoursEnd, 0), 23)
    if start == end {
      return true
    }
    if start < end {
      return hour >= start && hour < end
    }
    return hour >= start || hour < end
  }

  func containsSensitiveContent(_ text: String) -> Bool {
    let lower = text.lowercased()
    let sensitiveTerms = [
      "bank", "rent", "payment", "pay", "money", "invoice", "legal", "lawyer", "court",
      "contract", "medical", "doctor", "hospital", "emergency", "sorry for your loss",
      "break up", "breakup", "love you", "hate", "angry", "suicide", "self harm",
    ]
    return sensitiveTerms.contains { lower.contains($0) }
  }

  private func auditLogURL() -> URL {
    URL(fileURLWithPath: WhatsAppService.defaultStoreDirectory())
      .appendingPathComponent("reply-audit.jsonl")
  }

  private func normalizeJid(_ jid: String) -> String {
    WhatsAppContactResolver.shared.canonicalJid(for: jid)
  }
}

enum WhatsAppSendDecision: Equatable, Sendable {
  case allowed
  case duplicate
  case blocked(String)
}

enum WhatsAppAutoDecision: Equatable, Sendable {
  case auto
  case draft(reason: String)
  case ignore(reason: String)
}

private func + (lhs: Data, rhs: Data) -> Data {
  var data = lhs
  data.append(rhs)
  return data
}
