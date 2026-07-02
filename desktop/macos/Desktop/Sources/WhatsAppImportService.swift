import Foundation

// MARK: - Parsed models

struct WhatsAppParsedMessage: Sendable {
  let senderName: String?
  let text: String
  let date: Date
}

enum WhatsAppImportError: LocalizedError {
  case unrecognizedFormat

  var errorDescription: String? {
    switch self {
    case .unrecognizedFormat:
      return "No messages found. Export from WhatsApp with a chat → More → Export chat → "
        + "Without media, then pick the .txt file."
    }
  }
}

private let whatsAppHeaderPattern =
  #"^[\u200E\u200F\uFEFF]*\[?(\d{1,4})[./\-](\d{1,2})[./\-](\d{1,4})(?:,[ \u00A0\u202F]*|[ \u00A0\u202F]+)(\d{1,2}):(\d{2})(?::(\d{2}))?[ \u00A0\u202F]*(?:([AaPp])\.?[ \u00A0\u202F]?[Mm]\.?)?\]?[ \u00A0\u202F]*(?:[-–—][ \u00A0\u202F]+)?(.*)$"#

private struct WhatsAppRawHeader {
  let a: Int
  let b: Int
  let c: Int
  let hour: Int
  let minute: Int
  let second: Int
  let isPM: Bool?
  let rest: String
}

private enum WhatsAppLine {
  case header(WhatsAppRawHeader)
  case continuation(String)
}

private enum WhatsAppDateOrder {
  case dayFirst, monthFirst, yearFirst
}

func parseWhatsAppExport(text: String) -> [WhatsAppParsedMessage] {
  guard let regex = try? NSRegularExpression(pattern: whatsAppHeaderPattern) else { return [] }

  var calendar = Calendar(identifier: .gregorian)
  calendar.timeZone = .current

  func stripMarks(_ s: String) -> String {
    s.replacingOccurrences(of: "\u{200E}", with: "")
      .replacingOccurrences(of: "\u{200F}", with: "")
      .trimmingCharacters(in: .whitespaces)
  }

  func capture(_ index: Int, _ match: NSTextCheckingResult, in line: String) -> String? {
    let nsRange = match.range(at: index)
    guard nsRange.location != NSNotFound, let range = Range(nsRange, in: line) else { return nil }
    return String(line[range])
  }

  // Pass 1: classify every line as a message header or a continuation.
  let rawLines = text.replacingOccurrences(of: "\r\n", with: "\n")
    .components(separatedBy: "\n")

  var lines: [WhatsAppLine] = []
  var headers: [WhatsAppRawHeader] = []
  for line in rawLines {
    let fullRange = NSRange(line.startIndex..., in: line)
    if let match = regex.firstMatch(in: line, range: fullRange),
      let aText = capture(1, match, in: line), let a = Int(aText),
      let bText = capture(2, match, in: line), let b = Int(bText),
      let cText = capture(3, match, in: line), let c = Int(cText),
      let hourText = capture(4, match, in: line), let hour = Int(hourText),
      let minuteText = capture(5, match, in: line), let minute = Int(minuteText)
    {
      let second = capture(6, match, in: line).flatMap(Int.init) ?? 0
      let isPM = capture(7, match, in: line).map { $0.lowercased() == "p" }
      let rest = capture(8, match, in: line) ?? ""
      let header = WhatsAppRawHeader(
        a: a, b: b, c: c, hour: hour, minute: minute, second: second, isPM: isPM, rest: rest)
      lines.append(.header(header))
      headers.append(header)
    } else {
      lines.append(.continuation(line))
    }
  }

  guard !headers.isEmpty else { return [] }

  func date(from header: WhatsAppRawHeader, order: WhatsAppDateOrder) -> Date? {
    let day: Int, month: Int, year: Int
    switch order {
    case .dayFirst: (day, month, year) = (header.a, header.b, header.c)
    case .monthFirst: (month, day, year) = (header.a, header.b, header.c)
    case .yearFirst: (year, month, day) = (header.a, header.b, header.c)
    }
    guard (1...12).contains(month), (1...31).contains(day) else { return nil }

    var hour = header.hour
    if let isPM = header.isPM {
      if isPM && hour < 12 { hour += 12 }
      if !isPM && hour == 12 { hour = 0 }
    }
    guard (0...23).contains(hour), (0...59).contains(header.minute) else { return nil }

    var components = DateComponents()
    components.year = year < 100 ? year + 2000 : year
    components.month = month
    components.day = day
    components.hour = hour
    components.minute = header.minute
    components.second = header.second
    return calendar.date(from: components)
  }

  // Pass 2: pick the day/month order.
  let order: WhatsAppDateOrder
  if headers.contains(where: { $0.a >= 1000 }) {
    order = .yearFirst
  } else {
    let maxA = headers.map(\.a).max() ?? 0
    let maxB = headers.map(\.b).max() ?? 0
    if maxA > 12 && maxB <= 12 {
      order = .dayFirst
    } else if maxB > 12 && maxA <= 12 {
      order = .monthFirst
    } else {
      func inversions(_ candidate: WhatsAppDateOrder) -> Int {
        var count = 0
        var previous: Date?
        for header in headers {
          guard let d = date(from: header, order: candidate) else {
            count += 1
            continue
          }
          if let p = previous, d < p { count += 1 }
          previous = d
        }
        return count
      }
      order = inversions(.dayFirst) <= inversions(.monthFirst) ? .dayFirst : .monthFirst
    }
  }

  func splitSender(_ rest: String) -> (sender: String?, body: String) {
    guard let range = rest.range(of: ": ") else { return (nil, rest) }
    let sender = String(rest[..<range.lowerBound])
    let body = String(rest[range.upperBound...])
    return (sender.isEmpty ? nil : sender, body)
  }

  // Pass 3: build messages, appending continuation lines to the previous message.
  var messages: [WhatsAppParsedMessage] = []
  var current: (sender: String?, text: String, date: Date)?

  func flush() {
    guard let finished = current else { return }
    let text = finished.text.trimmingCharacters(in: .whitespacesAndNewlines)
    if !text.isEmpty || finished.sender != nil {
      messages.append(
        WhatsAppParsedMessage(senderName: finished.sender, text: text, date: finished.date))
    }
    current = nil
  }

  for line in lines {
    switch line {
    case .header(let header):
      flush()
      guard let messageDate = date(from: header, order: order) else { continue }
      let (sender, body) = splitSender(stripMarks(header.rest))
      current = (sender.map(stripMarks), stripMarks(body), messageDate)
    case .continuation(let raw):
      guard current != nil else { continue }
      current?.text += "\n" + stripMarks(raw)
    }
  }
  flush()

  return messages
}

func whatsAppSenders(in messages: [WhatsAppParsedMessage]) -> [(name: String, messageCount: Int)] {
  var counts: [String: Int] = [:]
  var order: [String] = []
  for message in messages {
    guard let sender = message.senderName else { continue }
    if counts[sender] == nil { order.append(sender) }
    counts[sender, default: 0] += 1
  }
  return
    order
    .map { (name: $0, messageCount: counts[$0] ?? 0) }
    .sorted { $0.messageCount > $1.messageCount }
}

func isWhatsAppMediaPlaceholder(_ text: String) -> Bool {
  let trimmed = text.trimmingCharacters(in: .whitespacesAndNewlines)
  if trimmed.hasPrefix("<") && trimmed.hasSuffix(">") { return true }
  let lowered = trimmed.lowercased()
  let omittedKinds = [
    "image omitted", "video omitted", "audio omitted", "sticker omitted",
    "gif omitted", "document omitted", "contact card omitted",
  ]
  if omittedKinds.contains(lowered) { return true }
  if lowered == "null" { return true }
  if lowered.hasPrefix("<attached:") { return true }
  return false
}

// MARK: - Sender picker option

struct WhatsAppSenderOption: Sendable, Identifiable {
  let name: String
  let messageCount: Int
  /// True when this name appears in every imported chat — a strong "this is you" signal.
  let appearsInEveryChat: Bool
  var id: String { name }
}

// MARK: - Reader

/// Session-scoped reader over one or more imported WhatsApp "Export Chat" .txt files.
/// One file == one chat. Mirrors `IMessageReaderService`'s actor + `shared` +
/// `ImportedContact`/`ImportedMessage` conversion shape so `AIClonePage` can treat all
/// platforms uniformly.
actor WhatsAppImportService {
  static let shared = WhatsAppImportService()

  private var chatsByID: [String: [WhatsAppParsedMessage]] = [:]
  private var displayNamesByID: [String: String] = [:]
  private var chatOrder: [String] = []
  private var selfName: String? =
    UserDefaults.standard.string(forKey: "aiCloneWhatsAppSelfName")

  /// Import one or more exported .txt files (one chat per file). Returns sender options
  /// needing disambiguation, or `[]` once self is already known.
  func importFiles(at urls: [URL]) throws -> [WhatsAppSenderOption] {
    var anyProduced = false
    for url in urls {
      let text = try String(contentsOf: url, encoding: .utf8)
      let messages = parseWhatsAppExport(text: text)
      guard !messages.isEmpty else { continue }
      anyProduced = true
      let id = "whatsapp:\(url.lastPathComponent)"
      if chatsByID[id] == nil { chatOrder.append(id) }
      chatsByID[id] = messages
      displayNamesByID[id] = Self.displayName(forFileName: url.lastPathComponent, messages: messages)
    }
    guard anyProduced else { throw WhatsAppImportError.unrecognizedFormat }
    guard selfName == nil else { return [] }
    return currentSenderOptions()
  }

  func setSelfName(_ name: String) {
    selfName = name
    UserDefaults.standard.set(name, forKey: "aiCloneWhatsAppSelfName")
  }

  /// True once the user's own sender name is known (picked from the import options).
  func hasSelfIdentity() -> Bool { selfName != nil }

  /// Aggregated sender candidates across all imported chats, most-active-first. Used
  /// both for the initial disambiguation prompt and the "Change" affordance.
  func currentSenderOptions() -> [WhatsAppSenderOption] {
    var counts: [String: Int] = [:]
    var chatsContaining: [String: Set<String>] = [:]
    for (chatID, messages) in chatsByID {
      for entry in whatsAppSenders(in: messages) {
        counts[entry.name, default: 0] += entry.messageCount
        chatsContaining[entry.name, default: []].insert(chatID)
      }
    }
    return counts.keys
      .sorted { (counts[$0] ?? 0) > (counts[$1] ?? 0) }
      .map { name in
        WhatsAppSenderOption(
          name: name, messageCount: counts[name] ?? 0,
          appearsInEveryChat: chatsContaining[name]?.count == chatsByID.count)
      }
  }

  func topContacts(limit: Int) -> [ImportedContact] {
    chatOrder
      .compactMap { id -> ImportedContact? in
        guard let messages = chatsByID[id] else { return nil }
        return ImportedContact(
          id: id, displayName: displayNamesByID[id] ?? id,
          messageCount: messages.count, platform: "whatsapp")
      }
      .sorted { $0.messageCount > $1.messageCount }
      .prefix(limit)
      .map { $0 }
  }

  func messages(for contactID: String, limit: Int = 500) -> [ImportedMessage] {
    guard let raw = chatsByID[contactID] else { return [] }
    let selfName = selfName
    return
      raw
      .filter { $0.senderName != nil && !isWhatsAppMediaPlaceholder($0.text) }
      .suffix(limit)
      .map { ImportedMessage(isFromMe: $0.senderName == selfName, text: $0.text, date: $0.date) }
  }

  /// `WhatsApp Chat with X.txt` → `X`. Falls back to the most frequent non-system sender
  /// (e.g. for `_chat.txt`, the generic name inside an exported zip).
  private static func displayName(forFileName fileName: String, messages: [WhatsAppParsedMessage])
    -> String
  {
    let base = (fileName as NSString).deletingPathExtension
    let prefix = "WhatsApp Chat with "
    if base.hasPrefix(prefix) {
      return String(base.dropFirst(prefix.count))
    }
    return whatsAppSenders(in: messages).first?.name ?? base
  }
}
