import CryptoKit
import Foundation

struct WhatsAppSyncedMessage: Identifiable, Equatable, Sendable {
  let id: String
  let chatJid: String
  let senderJid: String
  let senderName: String?
  let text: String
  let fromMe: Bool
  let timestamp: Date?
  let isGroup: Bool

  @MainActor
  var displaySender: String {
    WhatsAppContactResolver.shared.displayName(for: senderJid, fallback: senderName)
  }
}

@MainActor
final class WhatsAppMemoryImportService: ObservableObject {
  static let shared = WhatsAppMemoryImportService()

  @Published var syncWithBrainEnabled: Bool {
    didSet {
      defaults.set(syncWithBrainEnabled, forKey: Keys.syncWithBrainEnabled)
      if syncWithBrainEnabled {
        syncTask?.cancel()
        syncTask = nil
        scheduleSyncIfEnabled(delaySeconds: 0.5)
      }
    }
  }
  @Published private(set) var isSyncing = false
  @Published private(set) var lastStatus: String?
  @Published private(set) var lastError: String?
  @Published private(set) var lastSourceCount = 0
  @Published private(set) var lastMemoryCount = 0

  private let defaults = UserDefaults.standard
  private var syncTask: Task<Void, Never>?

  private enum Keys {
    static let syncWithBrainEnabled = "whatsapp.memoryImport.syncWithBrainEnabled"
    static let importedMessageIDs = "whatsapp.memoryImport.importedMessageIDs"
  }

  private init() {
    syncWithBrainEnabled = defaults.bool(forKey: Keys.syncWithBrainEnabled)
  }

  func scheduleSyncIfEnabled(delaySeconds: TimeInterval = 12) {
    guard syncWithBrainEnabled, syncTask == nil else { return }
    syncTask = Task { [weak self] in
      try? await Task.sleep(nanoseconds: UInt64(max(delaySeconds, 0) * 1_000_000_000))
      guard !Task.isCancelled, let self else { return }
      _ = await self.syncNow()
      self.syncTask = nil
    }
  }

  func enableAndSyncNow() async -> (sourceCount: Int, memories: Int)? {
    if !syncWithBrainEnabled {
      syncWithBrainEnabled = true
    }
    return await syncNow()
  }

  @discardableResult
  func retryAllMessages() async -> (sourceCount: Int, memories: Int)? {
    defaults.removeObject(forKey: Keys.importedMessageIDs)
    lastStatus = "Retrying all synced WhatsApp messages..."
    log("WhatsAppMemoryImportService: cleared imported message IDs for retry")
    return await syncNow()
  }

  @discardableResult
  func syncNow(limit: Int = 500) async -> (sourceCount: Int, memories: Int)? {
    log("WhatsAppMemoryImportService: sync requested enabled=\(syncWithBrainEnabled)")
    guard syncWithBrainEnabled else {
      lastStatus = "Turn on WhatsApp brain sync first."
      log("WhatsAppMemoryImportService: sync skipped because brain sync is disabled")
      return nil
    }
    guard !isSyncing else {
      lastStatus = "WhatsApp brain sync is already running."
      log("WhatsAppMemoryImportService: sync skipped because another sync is running")
      return nil
    }
    isSyncing = true
    lastError = nil
    lastStatus = "Reading synced WhatsApp messages..."
    defer { isSyncing = false }

    let messages = await readMessages(limit: limit)
      .filter { !$0.text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty }
      .sorted { lhs, rhs in
        (lhs.timestamp ?? .distantPast) < (rhs.timestamp ?? .distantPast)
      }
    lastSourceCount = messages.count
    log("WhatsAppMemoryImportService: read \(messages.count) WhatsApp messages for brain sync")
    guard !messages.isEmpty else {
      lastStatus = "No synced WhatsApp messages found yet. Keep WhatsApp connected until initial sync has messages, then try again."
      return (0, 0)
    }

    let importedIDs = Set(defaults.stringArray(forKey: Keys.importedMessageIDs) ?? [])
    let newMessages = messages.filter { !importedIDs.contains(dedupeKey(for: $0)) }
    guard !newMessages.isEmpty else {
      lastStatus = "WhatsApp brain sync is up to date."
      log("WhatsAppMemoryImportService: no new WhatsApp messages to import")
      return (messages.count, 0)
    }

    lastStatus = "Saving \(newMessages.count.formatted()) WhatsApp messages to Omi memory..."
    let rawImport = await saveAsMemories(messages: newMessages)
    let synthesis: (memories: Int, tasks: Int)
    if rawImport.saved > 0 {
      lastStatus = "Synthesizing WhatsApp memories and follow-ups..."
      synthesis = await synthesizeFromMessages(messages: Array(newMessages.suffix(180)))
    } else {
      synthesis = (0, 0)
    }
    let memoryCount = rawImport.saved + synthesis.memories
    lastMemoryCount = memoryCount

    let nextImportedIDs = importedIDs.union(rawImport.savedKeys)
    defaults.set(Array(nextImportedIDs).sorted(), forKey: Keys.importedMessageIDs)
    if rawImport.saved == 0 {
      lastStatus = "Read \(newMessages.count.formatted()) WhatsApp messages, but none were saved. They were not marked imported; try again after checking the error above."
    } else {
      lastStatus = "Synced \(newMessages.count.formatted()) WhatsApp messages and saved \(memoryCount.formatted()) memories."
    }
    return (newMessages.count, memoryCount)
  }

  func readMessages(limit: Int = 500) async -> [WhatsAppSyncedMessage] {
    let boundedLimit = max(1, min(limit, 2_000))
    var result = await runWacli(["messages", "export", "--limit", String(boundedLimit)])
    if result.exitCode != 0 {
      result = await runWacli(["messages", "list", "--limit", String(boundedLimit)])
    }
    guard result.exitCode == 0 else {
      lastError = result.output
      log("WhatsAppMemoryImportService: failed to read messages exit=\(result.exitCode) outputBytes=\(result.output.utf8.count)")
      return []
    }
    return parseMessages(from: result.output)
  }

  func saveAsMemories(messages: [WhatsAppSyncedMessage]) async -> (saved: Int, failed: Int, savedKeys: Set<String>) {
    guard !messages.isEmpty else { return (0, 0, []) }
    let chunkSize = APIClient.memoriesBatchMaxSize
    var saved = 0
    var failed = 0
    var savedKeys = Set<String>()
    var index = 0

    while index < messages.count {
      let end = min(index + chunkSize, messages.count)
      let chunk = Array(messages[index..<end])
      index = end
      let items = chunk.map { message in
        MemoryBatchItem(
          content: memoryContent(for: message),
          visibility: "private",
          tags: ["whatsapp", "message"],
          headline: "WhatsApp with \(chatDisplayName(for: message))"
        )
      }

      do {
        let response = try await APIClient.shared.createMemoriesBatch(items)
        saved += response.createdCount
        if response.createdCount > 0 {
          savedKeys.formUnion(chunk.map { dedupeKey(for: $0) })
        }
        if response.createdCount < chunk.count {
          failed += chunk.count - response.createdCount
        }
        log("WhatsAppMemoryImportService: saved WhatsApp memory batch \(response.createdCount)/\(chunk.count)")
      } catch {
        failed += chunk.count
        lastError = error.localizedDescription
        log("WhatsAppMemoryImportService: failed to save WhatsApp memory batch (\(chunk.count) items): \(error)")
      }
    }

    log("WhatsAppMemoryImportService: saved \(saved) WhatsApp messages as memories (\(failed) failed)")
    return (saved, failed, savedKeys)
  }

  func synthesizeFromMessages(messages: [WhatsAppSyncedMessage]) async -> (memories: Int, tasks: Int) {
    guard !messages.isEmpty else { return (0, 0) }

    let formatter = DateFormatter()
    formatter.dateFormat = "MMM d, HH:mm"
    let lines = messages.map { message in
      let date = message.timestamp.map { formatter.string(from: $0) } ?? "unknown date"
      let direction = message.fromMe ? "User" : message.displaySender
      let chatName = WhatsAppContactResolver.shared.displayName(for: message.chatJid, fallback: message.senderName)
      return "[\(date)] \(chatName) | \(direction): \(message.text.prefix(500))"
    }.joined(separator: "\n")

    let prompt = """
      Analyze these synced WhatsApp messages and extract useful Omi memories and follow-up tasks.

      WHATSAPP MESSAGES:
      \(lines)

      Respond ONLY with valid JSON:
      {
        "memories": [
          "The user ...",
          "The user's contact ... wants ..."
        ],
        "tasks": [
          {"description": "follow up with ...", "priority": "medium", "due_at": "2026-06-30T09:00:00Z"}
        ]
      }

      Rules:
      - Extract durable facts, relationship context, preferences, wants, important dates, wishes, commitments, and recurring topics.
      - Include facts that would help answer future personal questions or draft better WhatsApp replies.
      - Keep each memory as one clear factual sentence.
      - Create tasks only for clear follow-ups or commitments.
      - Do not invent facts not supported by the messages.
      """

    do {
      let bridge = AgentBridge(harnessMode: "piMono")
      try await bridge.start()
      defer { Task { await bridge.stop() } }

      let result = try await bridge.query(
        prompt: prompt,
        systemPrompt: "You extract Omi memories and tasks from WhatsApp history. Output strict JSON only.",
        surface: .service("whatsapp-memory-import"),
        model: ModelQoS.Claude.synthesis,
        onTextDelta: { @Sendable _ in },
        onToolCall: { @Sendable _, _, _ in "" },
        onToolActivity: { @Sendable _, _, _, _ in }
      )

      guard let parsed = parseJSONObject(from: result.text) else {
        log("WhatsAppMemoryImportService: failed to parse synthesis response: \(result.text.prefix(200))")
        return (0, 0)
      }
      let memoryStrings = parsed["memories"] as? [String] ?? []
      let taskDicts = parsed["tasks"] as? [[String: Any]] ?? []

      let memoriesSaved = await saveSynthesizedMemories(memoryStrings)

      var tasksSaved = 0
      for taskDict in taskDicts {
        guard let description = taskDict["description"] as? String, !description.isEmpty else { continue }
        let priority = taskDict["priority"] as? String ?? "medium"
        let dueAt = (taskDict["due_at"] as? String).flatMap { ISO8601DateFormatter().date(from: $0) }
        let task = await TasksStore.shared.createTask(
          description: description,
          dueAt: dueAt,
          priority: priority,
          tags: ["whatsapp"]
        )
        if task != nil {
          tasksSaved += 1
        }
      }
      return (memoriesSaved, tasksSaved)
    } catch {
      lastError = error.localizedDescription
      log("WhatsAppMemoryImportService: synthesis failed: \(error.localizedDescription)")
      return (0, 0)
    }
  }

  private func saveSynthesizedMemories(_ memories: [String]) async -> Int {
    let cleaned = memories
      .map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }
      .filter { !$0.isEmpty }
    guard !cleaned.isEmpty else { return 0 }

    var saved = 0
    var index = 0
    while index < cleaned.count {
      let end = min(index + APIClient.memoriesBatchMaxSize, cleaned.count)
      let chunk = Array(cleaned[index..<end]).map { memory in
        MemoryBatchItem(
          content: memory,
          visibility: "private",
          tags: ["whatsapp", "profile"],
          headline: "WhatsApp Insight"
        )
      }
      index = end
      do {
        let response = try await APIClient.shared.createMemoriesBatch(chunk)
        saved += response.createdCount
      } catch {
        lastError = error.localizedDescription
        log("WhatsAppMemoryImportService: failed to save synthesized memory batch (\(chunk.count) items): \(error)")
      }
    }
    return saved
  }

  private func memoryContent(for message: WhatsAppSyncedMessage) -> String {
    let dateStr = message.timestamp?.formatted(date: .abbreviated, time: .shortened) ?? "unknown date"
    let direction = message.fromMe ? "sent by the user" : "from \(message.displaySender)"
    return "WhatsApp message in \(chatDisplayName(for: message)) on \(dateStr) \(direction): \(message.text)"
  }

  private func chatDisplayName(for message: WhatsAppSyncedMessage) -> String {
    WhatsAppContactResolver.shared.displayName(for: message.chatJid, fallback: message.senderName)
  }

  func parseMessages(from output: String) -> [WhatsAppSyncedMessage] {
    guard let data = output.data(using: .utf8),
      let json = try? JSONSerialization.jsonObject(with: data)
    else {
      return []
    }
    return collectMessages(from: json, path: "root")
  }

  private func collectMessages(from value: Any, path: String) -> [WhatsAppSyncedMessage] {
    if let array = value as? [Any] {
      return array.enumerated().flatMap { index, item in
        collectMessages(from: item, path: "\(path).\(index)")
      }
    }
    guard let object = value as? [String: Any] else { return [] }
    var messages = object.keys.sorted().flatMap { key in
      collectMessages(from: object[key] as Any, path: "\(path).\(key)")
    }

    let chatJid = stringValue(object, keys: ["chatJid", "ChatJID", "chat_jid", "chat", "to", "from"])
    let senderJid = stringValue(object, keys: ["senderJid", "SenderJID", "sender_jid", "sender", "participant", "from"]) ?? chatJid
    let text = stringValue(object, keys: ["text", "body", "message", "caption", "Text", "DisplayText"])
    if let chatJid, let senderJid, let text, !text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
      let timestamp = dateValue(object, keys: ["timestamp", "Timestamp", "time", "createdAt"])
      let id = stringValue(object, keys: ["id", "ID", "messageId", "message_id", "MsgID"])
        ?? stableFallbackMessageID(chatJid: chatJid, senderJid: senderJid, timestamp: timestamp, text: text, sourcePosition: path)
      messages.append(WhatsAppSyncedMessage(
        id: id,
        chatJid: chatJid,
        senderJid: senderJid,
        senderName: stringValue(object, keys: ["senderName", "SenderName", "pushName", "PushName", "name", "chatName", "ChatName"]),
        text: text,
        fromMe: boolValue(object, keys: ["fromMe", "from_me", "isFromMe", "FromMe"]) ?? false,
        timestamp: timestamp,
        isGroup: (boolValue(object, keys: ["isGroup", "is_group", "group"]) ?? false) || chatJid.contains("@g.us")
      ))
    }
    return messages
  }

  private func parseJSONObject(from text: String) -> [String: Any]? {
    var responseText = text
    if let jsonStart = responseText.range(of: "```json") {
      responseText = String(responseText[jsonStart.upperBound...])
      if let jsonEnd = responseText.range(of: "```") {
        responseText = String(responseText[..<jsonEnd.lowerBound])
      }
    } else if let fenceStart = responseText.range(of: "```") {
      responseText = String(responseText[fenceStart.upperBound...])
      if let fenceEnd = responseText.range(of: "```") {
        responseText = String(responseText[..<fenceEnd.lowerBound])
      }
    }
    if let braceStart = responseText.firstIndex(of: "{") {
      responseText = String(responseText[braceStart...])
    }
    responseText = responseText.trimmingCharacters(in: .whitespacesAndNewlines)
    guard let data = responseText.data(using: .utf8) else { return nil }
    return try? JSONSerialization.jsonObject(with: data) as? [String: Any]
  }

  nonisolated func dedupeKey(for message: WhatsAppSyncedMessage) -> String {
    "\(message.chatJid)|\(message.senderJid)|\(message.id)|\(Int(message.timestamp?.timeIntervalSince1970 ?? 0))"
  }

  nonisolated func stableFallbackMessageID(
    chatJid: String,
    senderJid: String,
    timestamp: Date?,
    text: String,
    sourcePosition: String
  ) -> String {
    let timestampPart = timestamp.map { String(Int($0.timeIntervalSince1970)) } ?? "position:\(sourcePosition)"
    let source = "\(chatJid):\(senderJid):\(timestampPart):\(text)"
    let digest = SHA256.hash(data: Data(source.utf8))
    return digest.map { String(format: "%02x", $0) }.joined()
  }

  private func stringValue(_ object: [String: Any], keys: [String]) -> String? {
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

  private func boolValue(_ object: [String: Any], keys: [String]) -> Bool? {
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

  private func dateValue(_ object: [String: Any], keys: [String]) -> Date? {
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

  private func runWacli(_ arguments: [String]) async -> (output: String, exitCode: Int32) {
    guard let binary = WhatsAppService.findWacliBinary() else {
      return ("wacli not installed", 127)
    }
    let storeDir = WhatsAppService.defaultStoreDirectory()
    return await Task.detached(priority: .utility) {
      do {
        try FileManager.default.createDirectory(atPath: storeDir, withIntermediateDirectories: true)
        let process = Process()
        process.executableURL = URL(fileURLWithPath: binary)
        process.arguments = ["--store", storeDir, "--json", "--read-only"] + arguments
        var env = ProcessInfo.processInfo.environment
        env["WACLI_READONLY"] = "1"
        let binaryDir = (binary as NSString).deletingLastPathComponent
        let existingPath = env["PATH"] ?? "/usr/bin:/bin"
        if !existingPath.components(separatedBy: ":").contains(binaryDir) {
          env["PATH"] = "\(binaryDir):\(existingPath)"
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
}
