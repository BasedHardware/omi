import Foundation

struct WhatsAppContact: Codable, Equatable, Sendable {
  let jid: String
  var contactName: String?
  var whatsappName: String?
  var phoneNumber: String?
  var canonicalJid: String?

  var displayName: String {
    contactName?.nilIfEmpty
      ?? whatsappName?.nilIfEmpty
      ?? phoneNumber?.nilIfEmpty
      ?? jid
  }
}

enum WhatsAppContactResolutionError: LocalizedError {
  case emptyInput
  case ambiguous(String)
  case notFound(String)

  var errorDescription: String? {
    switch self {
    case .emptyInput:
      return "Enter a WhatsApp contact, phone number, or JID."
    case .ambiguous(let input):
      return "Multiple WhatsApp contacts matched '\(input)'. Use the phone number or exact JID."
    case .notFound(let input):
      return "Could not find a WhatsApp contact for '\(input)'."
    }
  }
}

@MainActor
final class WhatsAppContactResolver: ObservableObject {
  static let shared = WhatsAppContactResolver()

  @Published private(set) var contactsByJid: [String: WhatsAppContact] = [:]
  @Published private(set) var lastRefreshError: String?

  private let cacheFileName = "contacts-cache.json"
  private var refreshTask: Task<Void, Never>?

  private init(shouldLoadCache: Bool = true) {
    if shouldLoadCache {
      loadCache()
    }
  }

  #if DEBUG
  private var skipsPersistence = false

  internal init(testingContacts: [String: WhatsAppContact]) {
    self.contactsByJid = testingContacts
    self.skipsPersistence = true
  }

  internal func testing_collectContacts(from value: Any) -> [WhatsAppContact] {
    collectContacts(from: value)
  }

  internal func testing_contacts(fromJSON output: String) -> [WhatsAppContact] {
    contacts(from: output)
  }

  internal func testing_isJidLike(_ value: String) -> Bool {
    isJidLike(value)
  }

  internal func testing_jidFromPhone(_ value: String) -> String? {
    jidFromPhone(value)
  }

  internal func testing_stableCycleRepresentative(_ jids: [String]) -> String {
    stableCycleRepresentative(jids)
  }

  internal func testing_phoneNumber(from jid: String) -> String? {
    phoneNumber(from: jid)
  }
  #endif

  func displayName(for jid: String, fallback: String? = nil) -> String {
    let normalized = canonicalJid(for: jid)
    if let contact = contactsByJid[normalized] {
      return contact.displayName
    }
    if let fallback = fallback?.trimmingCharacters(in: .whitespacesAndNewlines), !fallback.isEmpty {
      return fallback
    }
    return phoneNumber(from: normalized) ?? jid
  }

  func detailLabel(for jid: String) -> String {
    let normalized = canonicalJid(for: jid)
    if normalized.contains("@lid") {
      return contactsByJid[normalized] == nil ? normalized : "WhatsApp linked contact"
    }
    if let phone = phoneNumber(from: normalized), phone != normalized {
      return "\(phone) - \(normalized)"
    }
    return normalized
  }

  func phoneDigits(for jid: String) -> String? {
    let normalized = canonicalJid(for: jid)
    guard !normalized.contains("@lid") else { return nil }
    let phone = contactsByJid[normalized]?.phoneNumber ?? phoneNumber(from: normalized)
    let digits = phone?.filter(\.isNumber) ?? ""
    return digits.count >= 7 ? digits : nil
  }

  func canonicalJid(for jid: String) -> String {
    var current = normalizeJid(jid)
    var path: [String] = []
    var visitedIndex: [String: Int] = [:]
    while let canonical = contactsByJid[current]?.canonicalJid?.nilIfEmpty.map(normalizeJid),
      canonical != current
    {
      if let cycleStart = visitedIndex[current] {
        return stableCycleRepresentative(Array(path[cycleStart...]))
      }
      if let cycleStart = visitedIndex[canonical] {
        return stableCycleRepresentative(Array(path[cycleStart...]) + [current])
      }
      visitedIndex[current] = path.count
      path.append(current)
      current = canonical
    }
    return current
  }

  func rememberAlias(jid: String, canonicalJid: String) {
    let normalized = normalizeJid(jid)
    let canonical = normalizeJid(canonicalJid)
    guard !normalized.isEmpty, !canonical.isEmpty, normalized != canonical else { return }
    guard !aliasChain(from: canonical, contains: normalized) else {
      log("WhatsAppContactResolver: skipped cyclic alias")
      return
    }
    var contact = contactsByJid[normalized] ?? WhatsAppContact(
      jid: normalized,
      contactName: nil,
      whatsappName: nil,
      phoneNumber: phoneNumber(from: normalized),
      canonicalJid: nil
    )
    contact.canonicalJid = canonical
    if let canonicalContact = contactsByJid[canonical] {
      contact.contactName = contact.contactName ?? canonicalContact.contactName
      contact.whatsappName = contact.whatsappName ?? canonicalContact.whatsappName
      contact.phoneNumber = canonicalContact.phoneNumber ?? contact.phoneNumber
    }
    contactsByJid[normalized] = contact
    saveCache()
  }

  func remember(jid: String, contactName: String? = nil, whatsappName: String? = nil) {
    let normalized = normalizeJid(jid)
    guard !normalized.isEmpty else { return }
    var contact = contactsByJid[normalized] ?? WhatsAppContact(
      jid: normalized,
      contactName: nil,
      whatsappName: nil,
      phoneNumber: phoneNumber(from: normalized),
      canonicalJid: nil
    )
    contact.contactName = contactName?.nilIfEmpty ?? contact.contactName
    contact.whatsappName = whatsappName?.nilIfEmpty ?? contact.whatsappName
    contact.phoneNumber = contact.phoneNumber ?? phoneNumber(from: normalized)
    contactsByJid[normalized] = contact
    saveCache()
  }

  func scheduleRefresh(importSystemContacts: Bool = true) {
    guard refreshTask == nil else { return }
    refreshTask = Task { [weak self] in
      try? await Task.sleep(nanoseconds: 2_000_000_000)
      guard let self else { return }
      await self.refresh(importSystemContacts: importSystemContacts)
      self.refreshTask = nil
    }
  }

  func refresh(importSystemContacts: Bool = true) async {
    lastRefreshError = nil

    if importSystemContacts {
      let importResult = await runWacli(["contacts", "import-system"], readOnly: false)
      if importResult.exitCode != 0 {
        lastRefreshError = importResult.output
        log("WhatsAppContactResolver: contacts import-system failed exit=\(importResult.exitCode) outputBytes=\(importResult.output.utf8.count)")
      }
    }
    let refreshResult = await runWacli(["contacts", "refresh"], readOnly: false)
    if refreshResult.exitCode != 0 {
      lastRefreshError = [lastRefreshError, refreshResult.output].compactMap(\.self).joined(separator: "\n")
      log("WhatsAppContactResolver: contacts refresh failed exit=\(refreshResult.exitCode) outputBytes=\(refreshResult.output.utf8.count)")
    }

    let chats = await runWacli(["chats", "list", "--limit", "200"], readOnly: true)
    if chats.exitCode == 0 {
      mergeContacts(from: chats.output)
    } else {
      lastRefreshError = [lastRefreshError, chats.output].compactMap(\.self).joined(separator: "\n")
    }
  }

  func resolveRecipient(_ input: String) async throws -> String {
    let trimmed = input.trimmingCharacters(in: .whitespacesAndNewlines)
    guard !trimmed.isEmpty else { throw WhatsAppContactResolutionError.emptyInput }
    if trimmed.contains("@"), isJidLike(trimmed) {
      return canonicalJid(for: trimmed)
    }
    if let jid = jidFromPhone(trimmed) {
      return jid
    }

    let lower = trimmed.lowercased()
    let localMatches = contactsByJid.values.filter { contact in
      [contact.contactName, contact.whatsappName, contact.phoneNumber, contact.jid]
        .compactMap { $0?.lowercased() }
        .contains { $0 == lower || $0.contains(lower) }
    }
    if localMatches.count == 1 {
      return localMatches[0].jid
    }
    if localMatches.count > 1 {
      throw WhatsAppContactResolutionError.ambiguous(trimmed)
    }

    let contactSearch = await runWacli(["contacts", "search", trimmed], readOnly: true)
    if contactSearch.exitCode == 0 {
      let matches = contacts(from: contactSearch.output)
      merge(matches)
      if matches.count == 1 {
        return matches[0].jid
      }
      if matches.count > 1 {
        throw WhatsAppContactResolutionError.ambiguous(trimmed)
      }
    }

    let chatSearch = await runWacli(["chats", "list", "--query", trimmed, "--limit", "10"], readOnly: true)
    if chatSearch.exitCode == 0 {
      let matches = contacts(from: chatSearch.output)
      merge(matches)
      if matches.count == 1 {
        return matches[0].jid
      }
      if matches.count > 1 {
        throw WhatsAppContactResolutionError.ambiguous(trimmed)
      }
    }

    throw WhatsAppContactResolutionError.notFound(trimmed)
  }

  private func mergeContacts(from output: String) {
    merge(contacts(from: output))
  }

  private func merge(_ contacts: [WhatsAppContact]) {
    guard !contacts.isEmpty else { return }
    for contact in contacts {
      var existing = contactsByJid[contact.jid] ?? contact
      existing.contactName = contact.contactName?.nilIfEmpty ?? existing.contactName
      existing.whatsappName = contact.whatsappName?.nilIfEmpty ?? existing.whatsappName
      existing.phoneNumber = contact.phoneNumber?.nilIfEmpty ?? existing.phoneNumber
      existing.canonicalJid = contact.canonicalJid?.nilIfEmpty ?? existing.canonicalJid
      contactsByJid[contact.jid] = existing
    }
    saveCache()
  }

  private func contacts(from output: String) -> [WhatsAppContact] {
    guard let data = output.data(using: .utf8),
      let json = try? JSONSerialization.jsonObject(with: data)
    else {
      return []
    }
    return collectContacts(from: json)
  }

  private func collectContacts(from value: Any) -> [WhatsAppContact] {
    if let array = value as? [Any] {
      return array.flatMap { collectContacts(from: $0) }
    }
    guard let object = value as? [String: Any] else { return [] }

    var contacts = object.values.flatMap { collectContacts(from: $0) }
    if let jid = jidValue(object, keys: ["jid", "JID", "chatJid", "ChatJID", "id", "ID", "chat", "raw"]) {
      let normalized = normalizeJid(jid)
      if isJidLike(normalized) {
        contacts.append(WhatsAppContact(
          jid: normalized,
          contactName: stringValue(object, keys: ["contactName", "contact_name", "fullName", "full_name", "name", "Name"]),
          whatsappName: stringValue(object, keys: ["pushName", "PushName", "whatsappName", "displayName", "DisplayName", "chatName", "ChatName"]),
          phoneNumber: stringValue(object, keys: ["phone", "phoneNumber", "number"]) ?? phoneNumber(from: normalized),
          canonicalJid: nil
        ))
      }
    }
    return contacts
  }

  private func stringValue(_ object: [String: Any], keys: [String]) -> String? {
    for key in keys {
      if let value = object[key] as? String, !value.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
        return value
      }
    }
    return nil
  }

  private func jidValue(_ object: [String: Any], keys: [String]) -> String? {
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

  private func loadCache() {
    let url = cacheURL()
    guard let data = try? Data(contentsOf: url),
      let decoded = try? JSONDecoder().decode([String: WhatsAppContact].self, from: data)
    else {
      return
    }
    contactsByJid = decoded
  }

  private func saveCache() {
    #if DEBUG
    if skipsPersistence { return }
    #endif
    let url = cacheURL()
    do {
      try FileManager.default.createDirectory(at: url.deletingLastPathComponent(), withIntermediateDirectories: true)
      let data = try JSONEncoder().encode(contactsByJid)
      try data.write(to: url, options: .atomic)
    } catch {
      log("WhatsAppContactResolver: failed to save cache: \(error.localizedDescription)")
    }
  }

  private func cacheURL() -> URL {
    URL(fileURLWithPath: WhatsAppService.defaultStoreDirectory()).appendingPathComponent(cacheFileName)
  }

  private func normalizeJid(_ jid: String) -> String {
    jid.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
  }

  private func isJidLike(_ value: String) -> Bool {
    let normalized = normalizeJid(value)
    let parts = normalized.split(separator: "@", omittingEmptySubsequences: false)
    guard parts.count == 2, parts.allSatisfy({ !$0.isEmpty }) else { return false }
    guard normalized.rangeOfCharacter(from: .whitespacesAndNewlines) == nil else { return false }
    return isKnownWhatsAppServer(String(parts[1]))
  }

  private func isKnownWhatsAppServer(_ server: String) -> Bool {
    switch server {
    case "s.whatsapp.net", "c.us", "g.us", "lid", "broadcast", "newsletter":
      return true
    default:
      return false
    }
  }

  private func aliasChain(from start: String, contains target: String) -> Bool {
    var current = start
    var visited: Set<String> = []
    while !current.isEmpty, visited.insert(current).inserted {
      if current == target {
        return true
      }
      guard let canonical = contactsByJid[current]?.canonicalJid?.nilIfEmpty.map(normalizeJid),
        canonical != current
      else {
        return false
      }
      current = canonical
    }
    return false
  }

  private func stableCycleRepresentative(_ jids: [String]) -> String {
    jids.min() ?? ""
  }

  private func jidFromPhone(_ value: String) -> String? {
    let digits = value.filter(\.isNumber)
    guard digits.count >= 7 else { return nil }
    return "\(digits)@s.whatsapp.net"
  }

  private func phoneNumber(from jid: String) -> String? {
    guard !jid.lowercased().contains("@lid") else { return nil }
    let user = jid.split(separator: "@", maxSplits: 1).first.map(String.init) ?? jid
    let digits = user.filter(\.isNumber)
    guard digits.count >= 7 else { return nil }
    return "+\(digits)"
  }

  private func runWacli(_ arguments: [String], readOnly: Bool) async -> (output: String, exitCode: Int32) {
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
        if readOnly {
          env["WACLI_READONLY"] = "1"
        }
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

private extension String {
  var nilIfEmpty: String? {
    isEmpty ? nil : self
  }
}
