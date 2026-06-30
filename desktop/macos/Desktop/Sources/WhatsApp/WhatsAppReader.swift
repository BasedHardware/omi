import CryptoKit
import Foundation

enum WhatsAppReader {
  private static let iso8601DateStyle = Date.ISO8601FormatStyle()
  private static let iso8601FractionalDateStyle = Date.ISO8601FormatStyle(includingFractionalSeconds: true)

  static func listChats(limit: Int = 50) async -> [MessageThread] {
    let boundedLimit = max(1, min(limit, 200))
    let raw = await runWacliJSON(["chats", "list", "--limit", String(boundedLimit)])
    return await parseChats(raw)
  }

  static func listMessages(chatJid: String, limit: Int = 100) async -> [MessageItem] {
    let boundedLimit = max(1, min(limit, 300))
    let raw = await runWacliJSON([
      "messages", "list",
      "--chat", chatJid,
      "--limit", String(boundedLimit),
    ])
    return await parseMessages(raw)
  }

  static func backfillRecentMessages(chatJid: String, count: Int = 50) async {
    let boundedCount = max(1, min(count, 100))
    _ = await runWacli([
      "history", "backfill",
      "--chat", chatJid,
      "--requests", "1",
      "--count", String(boundedCount),
    ], readOnly: false)
  }

  private static func runWacliJSON(_ arguments: [String]) async -> Any? {
    let result = await runWacli(arguments, readOnly: true)
    guard result.exitCode == 0, let data = result.output.data(using: .utf8) else {
      log("WhatsAppReader: wacli failed exit=\(result.exitCode) outputBytes=\(result.output.utf8.count)")
      return nil
    }
    guard let json = try? JSONSerialization.jsonObject(with: data) else {
      log("WhatsAppReader: failed to parse wacli JSON command=\(redactedCommandLabel(arguments)) outputBytes=\(result.output.utf8.count)")
      return nil
    }
    if let envelope = json as? [String: Any], envelope.keys.contains("data") {
      return envelope["data"]
    }
    return json
  }

  private static func runWacli(_ arguments: [String], readOnly: Bool) async -> (output: String, exitCode: Int32) {
    guard let binary = WhatsAppService.findWacliBinary() else {
      return ("wacli not installed", 127)
    }

    let storeDir = WhatsAppService.defaultStoreDirectory()
    return await Task.detached(priority: .utility) {
      do {
        try FileManager.default.createDirectory(atPath: storeDir, withIntermediateDirectories: true)

        let process = Process()
        process.executableURL = URL(fileURLWithPath: binary)
        process.arguments = ["--store", storeDir, "--json"] + (readOnly ? ["--read-only"] : []) + arguments

        var env = ProcessInfo.processInfo.environment
        let binaryDir = (binary as NSString).deletingLastPathComponent
        let existingPath = env["PATH"] ?? "/usr/bin:/bin"
        if !existingPath.components(separatedBy: ":").contains(binaryDir) {
          env["PATH"] = "\(binaryDir):\(existingPath)"
        }
        if readOnly {
          env["WACLI_READONLY"] = "1"
        }
        process.environment = env

        let outputPipe = Pipe()
        process.standardOutput = outputPipe
        process.standardError = outputPipe
        try process.run()
        let data = outputPipe.fileHandleForReading.readDataToEndOfFile()
        process.waitUntilExit()
        let output = String(data: data, encoding: .utf8)?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        return (output, process.terminationStatus)
      } catch {
        return ("\(error)", 1)
      }
    }.value
  }

  private static func parseChats(_ data: Any?) async -> [MessageThread] {
    let collected = await collectChats(from: data as Any)
    return collected
      .reduce(into: [String: MessageThread]()) { partial, thread in
        partial[thread.id] = thread
      }
      .values
      .sorted {
        ($0.lastActivity ?? .distantPast) > ($1.lastActivity ?? .distantPast)
      }
  }

  private static func collectChats(from value: Any) async -> [MessageThread] {
    if let array = value as? [Any] {
      var collected: [MessageThread] = []
      for item in array {
        collected.append(contentsOf: await collectChats(from: item))
      }
      return collected
    }
    guard let object = value as? [String: Any] else { return [] }

    var threads: [MessageThread] = []
    for nested in nestedCollectionValues(object, keys: ["data", "chats", "items", "results", "conversations"]) {
      threads.append(contentsOf: await collectChats(from: nested))
    }
    guard let jid = stringValue(object, keys: ["jid", "JID", "chatJid", "ChatJID", "chat_jid", "id", "ID", "chat"]),
      isJidLike(jid)
    else {
      return threads
    }

    let isGroup = (boolValue(object, keys: ["isGroup", "is_group", "group", "IsGroup"]) ?? false) || jid.contains("@g.us")
    let rawTitle = stringValue(object, keys: [
      "title", "Title", "name", "Name", "contactName", "ContactName", "pushName", "PushName",
      "displayName", "DisplayName", "chatName", "ChatName",
    ])
    if !isGroup {
      await WhatsAppContactResolver.shared.remember(jid: jid, contactName: rawTitle)
    }
    let title = await displayTitle(for: jid, rawTitle: rawTitle, isGroup: isGroup)
    let subtitle = subtitle(for: jid, object: object, isGroup: isGroup)
    let preview = stringValue(object, keys: [
      "lastMessagePreview", "last_message_preview", "lastMessageText", "last_message_text",
      "lastText", "last_message", "text", "body", "message", "Message", "DisplayText", "displayText",
    ]) ?? nestedStringValue(object, parentKeys: ["lastMessage", "LastMessage", "last_message"], childKeys: [
      "text", "body", "message", "caption", "Text", "DisplayText",
    ])
    let lastActivity = dateValue(object, keys: [
      "lastActivity", "last_activity", "lastMessageAt", "last_message_at", "lastMessageTs", "last_message_ts",
      "last_message_timestamp", "timestamp", "Timestamp", "updatedAt",
    ]) ?? nestedDateValue(object, parentKeys: ["lastMessage", "LastMessage", "last_message"], childKeys: [
      "timestamp", "Timestamp", "time", "createdAt", "CreatedAt", "last_message_ts",
    ])
    let unreadCount = intValue(object, keys: ["unreadCount", "unread_count", "unread", "UnreadCount"]) ?? 0

    threads.append(MessageThread(
      id: jid,
      providerId: "whatsapp",
      title: title,
      subtitle: subtitle,
      lastMessagePreview: preview,
      lastActivity: lastActivity,
      unreadCount: max(0, unreadCount),
      isGroup: isGroup,
      hasPendingDraft: false
    ))
    return threads
  }

  private static func parseMessages(_ data: Any?) async -> [MessageItem] {
    let collected = await collectMessages(from: data as Any)
    return collected
      .reduce(into: [String: MessageItem]()) { partial, message in
        partial[message.id] = message
      }
      .values
      .sorted {
        ($0.timestamp ?? .distantPast) < ($1.timestamp ?? .distantPast)
      }
  }

  private static func collectMessages(from value: Any) async -> [MessageItem] {
    if let array = value as? [Any] {
      var collected: [MessageItem] = []
      for item in array {
        collected.append(contentsOf: await collectMessages(from: item))
      }
      return collected
    }
    guard let object = value as? [String: Any] else { return [] }

    var messages: [MessageItem] = []
    for nested in nestedCollectionValues(object, keys: ["data", "messages", "items", "results"]) {
      messages.append(contentsOf: await collectMessages(from: nested))
    }
    let rawText = stringValue(object, keys: ["text", "body", "message", "caption", "Text"])
    let displayText = stringValue(object, keys: ["DisplayText", "displayText"])
    guard let text = rawText ?? displayText,
      !text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
    else {
      return messages
    }
    if isPlaceholderMessage(rawText: rawText, displayText: displayText, object: object) {
      return messages
    }

    let senderJid = stringValue(object, keys: ["senderJid", "SenderJID", "sender_jid", "sender", "participant", "from"])
    let timestamp = dateValue(object, keys: [
      "timestamp", "Timestamp", "time", "createdAt", "CreatedAt", "messageTimestamp", "message_timestamp",
    ])
    let id = stringValue(object, keys: ["id", "ID", "messageId", "message_id", "MsgID"])
      ?? stableFallbackMessageID(senderJid: senderJid, timestamp: timestamp, text: text)
    let senderName: String?
    if let value = stringValue(object, keys: ["senderName", "SenderName", "pushName", "PushName", "name", "Name"]) {
      senderName = value
    } else if let senderJid {
      senderName = await WhatsAppContactResolver.shared.displayName(for: senderJid)
    } else {
      senderName = nil
    }

    messages.append(MessageItem(
      id: id,
      text: text,
      isFromMe: boolValue(object, keys: ["fromMe", "from_me", "isFromMe", "FromMe"]) ?? false,
      senderName: senderName,
      timestamp: timestamp
    ))
    return messages
  }

  private static func nestedStringValue(_ object: [String: Any], parentKeys: [String], childKeys: [String]) -> String? {
    for parentKey in parentKeys {
      if let nested = object[parentKey] as? [String: Any], let value = stringValue(nested, keys: childKeys) {
        return value
      }
    }
    return nil
  }

  private static func nestedDateValue(_ object: [String: Any], parentKeys: [String], childKeys: [String]) -> Date? {
    for parentKey in parentKeys {
      if let nested = object[parentKey] as? [String: Any], let value = dateValue(nested, keys: childKeys) {
        return value
      }
    }
    return nil
  }

  private static func nestedCollectionValues(_ object: [String: Any], keys: [String]) -> [Any] {
    keys.compactMap { object[$0] }
  }

  private static func isPlaceholderMessage(rawText: String?, displayText: String?, object: [String: Any]) -> Bool {
    guard rawText?.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty != false else { return false }
    guard displayText?.trimmingCharacters(in: .whitespacesAndNewlines).lowercased() == "(message)" else { return false }
    let mediaKeys = ["MediaType", "mediaType", "MediaCaption", "mediaCaption", "Filename", "filename", "MimeType", "mimeType", "DirectPath", "directPath"]
    return mediaKeys.allSatisfy { key in
      guard let value = object[key] as? String else { return true }
      return value.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
    }
  }

  private static func displayTitle(for jid: String, rawTitle: String?, isGroup: Bool) async -> String {
    let cleanedTitle = rawTitle?.trimmingCharacters(in: .whitespacesAndNewlines)
    let fallback = isGroup ? "WhatsApp Group" : nil
    let resolved = await WhatsAppContactResolver.shared.displayName(for: jid, fallback: cleanedTitle ?? fallback)
    if isJidLike(resolved) {
      return phoneNumber(from: jid) ?? (isGroup ? "WhatsApp Group" : jid)
    }
    return resolved
  }

  private static func subtitle(for jid: String, object: [String: Any], isGroup: Bool) -> String? {
    if isGroup {
      return "Group"
    }
    return stringValue(object, keys: ["phone", "phoneNumber", "number", "Number"])
      ?? phoneNumber(from: jid)
  }

  private static func isJidLike(_ value: String) -> Bool {
    let trimmed = value.trimmingCharacters(in: .whitespacesAndNewlines)
    let parts = trimmed.split(separator: "@", omittingEmptySubsequences: false)
    guard parts.count == 2, parts.allSatisfy({ !$0.isEmpty }) else { return false }
    guard trimmed.rangeOfCharacter(from: .whitespacesAndNewlines) == nil else { return false }
    return isKnownWhatsAppServer(String(parts[1]).lowercased())
  }

  private static func isKnownWhatsAppServer(_ server: String) -> Bool {
    switch server {
    case "s.whatsapp.net", "c.us", "g.us", "lid", "broadcast", "newsletter":
      return true
    default:
      return false
    }
  }

  private static func phoneNumber(from jid: String) -> String? {
    let user = jid.split(separator: "@", maxSplits: 1).first.map(String.init) ?? jid
    let digits = user.filter(\.isNumber)
    guard digits.count >= 7 else { return nil }
    return "+\(digits)"
  }

  private static func stringValue(_ object: [String: Any], keys: [String]) -> String? {
    for key in keys {
      if let value = object[key] as? String, !value.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
        return value
      }
      if let nested = object[key] as? [String: Any] {
        if let jid = stringValue(nested, keys: ["jid", "JID", "raw", "Raw"]), !jid.isEmpty {
          return jid
        }
        let user = (nested["User"] as? String) ?? (nested["user"] as? String)
        let server = (nested["Server"] as? String) ?? (nested["server"] as? String)
        if let user, let server, !user.isEmpty, !server.isEmpty {
          return "\(user)@\(server)"
        }
      }
    }
    return nil
  }

  private static func intValue(_ object: [String: Any], keys: [String]) -> Int? {
    for key in keys {
      if let value = object[key] as? Int {
        return value
      }
      if let value = object[key] as? Double {
        return Int(value)
      }
      if let value = object[key] as? String, let parsed = Int(value) {
        return parsed
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
        if let date = parseISO8601Date(string) {
          return date
        }
        if let seconds = TimeInterval(string) {
          return Date(timeIntervalSince1970: seconds > 10_000_000_000 ? seconds / 1000 : seconds)
        }
      }
    }
    return nil
  }

  private static func parseISO8601Date(_ value: String) -> Date? {
    if let date = try? iso8601FractionalDateStyle.parse(value) {
      return date
    }
    return try? iso8601DateStyle.parse(value)
  }

  private static func stableFallbackMessageID(senderJid: String?, timestamp: Date?, text: String) -> String {
    let source = "\(senderJid ?? "unknown"):\(Int(timestamp?.timeIntervalSince1970 ?? 0)):\(text)"
    let digest = SHA256.hash(data: Data(source.utf8))
    return digest.map { String(format: "%02x", $0) }.joined()
  }

  private static func redactedCommandLabel(_ arguments: [String]) -> String {
    arguments.prefix(2).joined(separator: " ")
  }
}

#if DEBUG
extension WhatsAppReader {
  static func testingUnwrapJSONEnvelope(_ json: Any) -> Any? {
    if let envelope = json as? [String: Any], envelope.keys.contains("data") {
      return envelope["data"]
    }
    return json
  }

  static func testingParseChats(from data: Any?) async -> [MessageThread] {
    await parseChats(data)
  }

  static func testingParseMessages(from data: Any?) async -> [MessageItem] {
    await parseMessages(data)
  }

  static func testingIsPlaceholderMessage(
    rawText: String?,
    displayText: String?,
    object: [String: Any]
  ) -> Bool {
    isPlaceholderMessage(rawText: rawText, displayText: displayText, object: object)
  }

  static func testingStableFallbackMessageID(
    senderJid: String?,
    timestamp: Date?,
    text: String
  ) -> String {
    stableFallbackMessageID(senderJid: senderJid, timestamp: timestamp, text: text)
  }

  static func testingDisplayTitle(for jid: String, rawTitle: String?, isGroup: Bool) async -> String {
    await displayTitle(for: jid, rawTitle: rawTitle, isGroup: isGroup)
  }
}
#endif
