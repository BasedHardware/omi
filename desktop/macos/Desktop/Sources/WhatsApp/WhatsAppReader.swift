import Foundation

@MainActor
enum WhatsAppReader {
  static func listChats(limit: Int = 50) async -> [MessageThread] {
    let boundedLimit = max(1, min(limit, 200))
    let raw = await runWacliJSON(["chats", "list", "--limit", String(boundedLimit)])
    return parseChats(raw)
  }

  static func listMessages(chatJid: String, limit: Int = 100) async -> [MessageItem] {
    let boundedLimit = max(1, min(limit, 300))
    let raw = await runWacliJSON([
      "messages", "list",
      "--chat", chatJid,
      "--limit", String(boundedLimit),
    ])
    return parseMessages(raw)
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
      return nil
    }
    guard let json = try? JSONSerialization.jsonObject(with: data) else {
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

  private static func parseChats(_ data: Any?) -> [MessageThread] {
    collectChats(from: data as Any)
      .reduce(into: [String: MessageThread]()) { partial, thread in
        partial[thread.id] = thread
      }
      .values
      .sorted {
        ($0.lastActivity ?? .distantPast) > ($1.lastActivity ?? .distantPast)
      }
  }

  private static func collectChats(from value: Any) -> [MessageThread] {
    if let array = value as? [Any] {
      return array.flatMap { collectChats(from: $0) }
    }
    guard let object = value as? [String: Any] else { return [] }

    var threads = object.values.flatMap { collectChats(from: $0) }
    guard let jid = stringValue(object, keys: ["jid", "JID", "chatJid", "ChatJID", "chat_jid", "id", "ID", "chat"]),
      jid.contains("@")
    else {
      return threads
    }

    let isGroup = (boolValue(object, keys: ["isGroup", "is_group", "group", "IsGroup"]) ?? false) || jid.contains("@g.us")
    let rawTitle = stringValue(object, keys: [
      "title", "Title", "name", "Name", "contactName", "ContactName", "pushName", "PushName",
      "displayName", "DisplayName", "chatName", "ChatName",
    ])
    if !isGroup {
      WhatsAppContactResolver.shared.remember(jid: jid, contactName: rawTitle)
    }
    let title = displayTitle(for: jid, rawTitle: rawTitle, isGroup: isGroup)
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

  private static func parseMessages(_ data: Any?) -> [MessageItem] {
    collectMessages(from: data as Any)
      .reduce(into: [String: MessageItem]()) { partial, message in
        partial[message.id] = message
      }
      .values
      .sorted {
        ($0.timestamp ?? .distantPast) < ($1.timestamp ?? .distantPast)
      }
  }

  private static func collectMessages(from value: Any) -> [MessageItem] {
    if let array = value as? [Any] {
      return array.flatMap { collectMessages(from: $0) }
    }
    guard let object = value as? [String: Any] else { return [] }

    var messages = object.values.flatMap { collectMessages(from: $0) }
    guard let text = stringValue(object, keys: ["text", "body", "message", "caption", "Text", "DisplayText"]),
      !text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
    else {
      return messages
    }

    let senderJid = stringValue(object, keys: ["senderJid", "SenderJID", "sender_jid", "sender", "participant", "from"])
    let timestamp = dateValue(object, keys: [
      "timestamp", "Timestamp", "time", "createdAt", "CreatedAt", "messageTimestamp", "message_timestamp",
    ])
    let id = stringValue(object, keys: ["id", "ID", "messageId", "message_id", "MsgID"])
      ?? "\(senderJid ?? "unknown"):\(Int(timestamp?.timeIntervalSince1970 ?? 0)):\(text.hashValue)"
    let senderName = stringValue(object, keys: ["senderName", "SenderName", "pushName", "PushName", "name", "Name"])
      ?? senderJid.map { WhatsAppContactResolver.shared.displayName(for: $0) }

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

  private static func displayTitle(for jid: String, rawTitle: String?, isGroup: Bool) -> String {
    let cleanedTitle = rawTitle?.trimmingCharacters(in: .whitespacesAndNewlines)
    let fallback = isGroup ? "WhatsApp Group" : nil
    let resolved = WhatsAppContactResolver.shared.displayName(for: jid, fallback: cleanedTitle ?? fallback)
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
    let lowercased = value.lowercased()
    return lowercased.contains("@s.whatsapp.net") || lowercased.contains("@g.us")
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
