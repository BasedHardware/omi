import Foundation

// MARK: - Parsed models

struct TelegramParsedMessage: Sendable {
  let senderName: String?
  let senderID: String?
  let text: String
  let date: Date
}

struct TelegramSender: Sendable, Identifiable {
  let senderID: String?
  let name: String?
  let messageCount: Int
  var id: String { senderID ?? name ?? "unknown" }
}

struct TelegramParsedChat: Sendable {
  let id: Int64
  let name: String?
  let type: String
  var isPersonalChat: Bool { type == "personal_chat" }
  let messages: [TelegramParsedMessage]
  let senders: [TelegramSender]
}

enum TelegramImportError: LocalizedError {
  case unrecognizedFormat

  var errorDescription: String? {
    switch self {
    case .unrecognizedFormat:
      return "This file doesn't look like a Telegram export. In Telegram Desktop use "
        + "Settings → Advanced → Export Telegram Data with format set to JSON, then pick result.json."
    }
  }
}

private enum TelegramRawTextPiece: Decodable {
  case plain(String)
  case entity(String)

  private enum CodingKeys: String, CodingKey { case text }

  init(from decoder: Decoder) throws {
    if let single = try? decoder.singleValueContainer(), let s = try? single.decode(String.self) {
      self = .plain(s)
      return
    }
    let object = try decoder.container(keyedBy: CodingKeys.self)
    self = .entity((try? object.decode(String.self, forKey: .text)) ?? "")
  }

  var text: String {
    switch self {
    case .plain(let s), .entity(let s): return s
    }
  }
}

private enum TelegramRawText: Decodable {
  case plain(String)
  case rich([TelegramRawTextPiece])

  init(from decoder: Decoder) throws {
    let container = try decoder.singleValueContainer()
    if let s = try? container.decode(String.self) {
      self = .plain(s)
    } else if let pieces = try? container.decode([TelegramRawTextPiece].self) {
      self = .rich(pieces)
    } else {
      self = .plain("")
    }
  }

  var flattened: String {
    switch self {
    case .plain(let s): return s
    case .rich(let pieces): return pieces.map(\.text).joined()
    }
  }
}

private struct TelegramRawMessage: Decodable {
  let type: String?
  let date: String?
  let dateUnixtime: String?
  let from: String?
  let fromID: String?
  let text: TelegramRawText?

  private enum CodingKeys: String, CodingKey {
    case type, date, from, text
    case dateUnixtime = "date_unixtime"
    case fromID = "from_id"
  }

  init(from decoder: Decoder) throws {
    let c = try decoder.container(keyedBy: CodingKeys.self)
    type = try? c.decode(String.self, forKey: .type)
    date = try? c.decode(String.self, forKey: .date)
    if let s = try? c.decode(String.self, forKey: .dateUnixtime) {
      dateUnixtime = s
    } else if let n = try? c.decode(Int64.self, forKey: .dateUnixtime) {
      dateUnixtime = String(n)
    } else {
      dateUnixtime = nil
    }
    from = try? c.decode(String.self, forKey: .from)
    if let s = try? c.decode(String.self, forKey: .fromID) {
      fromID = s
    } else if let n = try? c.decode(Int64.self, forKey: .fromID) {
      fromID = String(n)
    } else {
      fromID = nil
    }
    text = try? c.decode(TelegramRawText.self, forKey: .text)
  }
}

private struct TelegramRawChat: Decodable {
  let id: Int64?
  let name: String?
  let type: String?
  let messages: [TelegramRawMessage]?
}

private struct TelegramRawChatList: Decodable {
  let list: [TelegramRawChat]?
}

private struct TelegramRawExport: Decodable {
  let chats: TelegramRawChatList?
  let leftChats: TelegramRawChatList?

  private enum CodingKeys: String, CodingKey {
    case chats
    case leftChats = "left_chats"
  }
}

func parseTelegramExport(jsonData: Data) throws -> [TelegramParsedChat] {
  let decoder = JSONDecoder()

  var rawChats: [TelegramRawChat] = []
  if let export = try? decoder.decode(TelegramRawExport.self, from: jsonData),
    export.chats?.list != nil || export.leftChats?.list != nil
  {
    rawChats = (export.chats?.list ?? []) + (export.leftChats?.list ?? [])
  } else if let single = try? decoder.decode(TelegramRawChat.self, from: jsonData),
    single.messages != nil
  {
    rawChats = [single]
  } else {
    throw TelegramImportError.unrecognizedFormat
  }

  let isoFormatter = DateFormatter()
  isoFormatter.locale = Locale(identifier: "en_US_POSIX")
  isoFormatter.dateFormat = "yyyy-MM-dd'T'HH:mm:ss"
  isoFormatter.timeZone = .current

  func resolveDate(_ message: TelegramRawMessage) -> Date? {
    if let unix = message.dateUnixtime, let seconds = TimeInterval(unix) {
      return Date(timeIntervalSince1970: seconds)
    }
    if let iso = message.date {
      return isoFormatter.date(from: iso)
    }
    return nil
  }

  return rawChats.compactMap { raw -> TelegramParsedChat? in
    guard let id = raw.id, let type = raw.type else { return nil }

    var messages: [TelegramParsedMessage] = []
    var senderOrder: [String] = []
    var senderInfo: [String: (id: String?, name: String?, count: Int)] = [:]

    for rawMessage in raw.messages ?? [] {
      guard (rawMessage.type ?? "message") == "message" else { continue }
      let text = rawMessage.text?.flattened
        .trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
      guard !text.isEmpty else { continue }
      guard let date = resolveDate(rawMessage) else { continue }

      messages.append(
        TelegramParsedMessage(
          senderName: rawMessage.from, senderID: rawMessage.fromID, text: text, date: date))

      let key = rawMessage.fromID ?? rawMessage.from ?? "unknown"
      if var existing = senderInfo[key] {
        existing.count += 1
        if existing.name == nil { existing.name = rawMessage.from }
        senderInfo[key] = existing
      } else {
        senderOrder.append(key)
        senderInfo[key] = (id: rawMessage.fromID, name: rawMessage.from, count: 1)
      }
    }

    guard !messages.isEmpty else { return nil }

    let senders =
      senderOrder
      .compactMap { key -> TelegramSender? in
        guard let info = senderInfo[key] else { return nil }
        return TelegramSender(senderID: info.id, name: info.name, messageCount: info.count)
      }
      .sorted { $0.messageCount > $1.messageCount }

    return TelegramParsedChat(
      id: id, name: raw.name, type: type, messages: messages, senders: senders)
  }
}

func telegramSelfUserID(jsonData: Data) -> String? {
  struct PersonalInfoEnvelope: Decodable {
    struct PersonalInfo: Decodable {
      let userID: Int64?
      private enum CodingKeys: String, CodingKey { case userID = "user_id" }
    }
    let personalInformation: PersonalInfo?
    private enum CodingKeys: String, CodingKey {
      case personalInformation = "personal_information"
    }
  }
  guard
    let envelope = try? JSONDecoder().decode(PersonalInfoEnvelope.self, from: jsonData),
    let userID = envelope.personalInformation?.userID
  else { return nil }
  return "user\(userID)"
}

// MARK: - Reader

/// Session-scoped reader over one imported Telegram Desktop JSON export. Mirrors
/// `IMessageReaderService`'s actor + `shared` + `ImportedContact`/`ImportedMessage`
/// conversion shape so `AIClonePage` can treat all platforms uniformly.
actor TelegramImportService {
  static let shared = TelegramImportService()

  private var chats: [TelegramParsedChat] = []
  private var selfID: String? =
    UserDefaults.standard.string(forKey: "aiCloneTelegramSelfID")

  /// Load a `result.json` (or a directory containing one). Returns senders needing
  /// disambiguation, or `[]` if self was auto-detected from `personal_information`.
  func importExport(at url: URL) throws -> [TelegramSender] {
    let resolvedURL = url.hasDirectoryPath ? url.appendingPathComponent("result.json") : url
    let data = try Data(contentsOf: resolvedURL)
    chats = try parseTelegramExport(jsonData: data)
    if let auto = telegramSelfUserID(jsonData: data) { setSelfID(auto) }
    if selfID != nil { return [] }
    return currentSenders()
  }

  func setSelfID(_ id: String) {
    selfID = id
    UserDefaults.standard.set(id, forKey: "aiCloneTelegramSelfID")
  }

  /// True once the user's own sender identity is known (auto-detected or picked).
  func hasSelfIdentity() -> Bool { selfID != nil }

  /// Aggregated senders across all imported personal chats, most-active-first. Used
  /// both for the initial disambiguation prompt and the "Change" affordance.
  func currentSenders() -> [TelegramSender] {
    var merged: [String: TelegramSender] = [:]
    for chat in chats where chat.isPersonalChat {
      for s in chat.senders {
        guard s.senderID != nil else { continue }
        let key = s.id
        merged[key] = TelegramSender(
          senderID: s.senderID, name: s.name ?? merged[key]?.name,
          messageCount: (merged[key]?.messageCount ?? 0) + s.messageCount)
      }
    }
    return merged.values.sorted { $0.messageCount > $1.messageCount }
  }

  func topContacts(limit: Int) -> [ImportedContact] {
    chats.filter(\.isPersonalChat)
      .sorted { $0.messages.count > $1.messages.count }
      .prefix(limit)
      .map {
        ImportedContact(
          id: "telegram:\($0.id)",
          displayName: $0.name ?? $0.senders.first?.name ?? "Unknown",
          messageCount: $0.messages.count, platform: "telegram")
      }
  }

  func messages(for contactID: String, limit: Int = 500) -> [ImportedMessage] {
    guard let chat = chats.first(where: { "telegram:\($0.id)" == contactID }) else { return [] }
    return chat.messages.suffix(limit).map {
      ImportedMessage(
        isFromMe: $0.senderID != nil && $0.senderID == selfID, text: $0.text, date: $0.date)
    }
  }
}
