import Foundation
import GRDB

/// Resolves iMessage handles (phone numbers / emails) to the real contact names in the
/// user's macOS Contacts, by reading the local AddressBook SQLite stores directly.
///
/// chat.db stores only handles, not names — names live in the Contacts database. The app is
/// sandboxed, so `CNContactStore` would need a separate Contacts entitlement *and* a fresh
/// permission prompt. But the AI Clone feature already requires Full Disk Access (to read
/// chat.db), and that same access can read the AddressBook stores — so name resolution needs
/// no extra permission. If the stores can't be read (no FDA, no Contacts), lookups return nil
/// and callers fall back to the raw handle.
actor ContactNameResolver {
  static let shared = ContactNameResolver()

  /// last-10-digits → name, for phone-number handles.
  private var phoneToName: [String: String]?
  /// lowercased email → name, for email handles.
  private var emailToName: [String: String]?

  private init() {}

  /// Drop the cached maps so the next lookup rebuilds from the current AddressBook (e.g. after
  /// the user grants Full Disk Access or edits a contact).
  func invalidate() {
    phoneToName = nil
    emailToName = nil
  }

  /// Resolve one handle to a display name, or nil if unknown / unreadable.
  func name(for handle: String) async -> String? {
    await ensureLoaded()
    return lookup(handle)
  }

  /// Batch-resolve handles → names. Only handles with a match appear in the result.
  func resolveAll(_ handles: [String]) async -> [String: String] {
    await ensureLoaded()
    var out: [String: String] = [:]
    for handle in handles {
      if let name = lookup(handle) { out[handle] = name }
    }
    return out
  }

  // MARK: - Lookup

  private func lookup(_ handle: String) -> String? {
    let trimmed = handle.trimmingCharacters(in: .whitespaces)
    guard !trimmed.isEmpty else { return nil }
    if trimmed.contains("@") {
      return emailToName?[trimmed.lowercased()]
    }
    if let key = Self.phoneKey(trimmed) {
      return phoneToName?[key]
    }
    return nil
  }

  /// Last 10 digits of a phone number — a country-code-tolerant match key. Returns nil if the
  /// value has too few digits to be a phone number (e.g. a short code we won't match reliably).
  private static func phoneKey(_ raw: String) -> String? {
    let digits = raw.filter { $0.isNumber }
    guard digits.count >= 10 else { return nil }
    return String(digits.suffix(10))
  }

  /// Format a record's name: "First Last", falling back to first-only, nickname, then company.
  private static func formatName(first: String?, last: String?, nickname: String?, org: String?)
    -> String?
  {
    let f = (first ?? "").trimmingCharacters(in: .whitespaces)
    let l = (last ?? "").trimmingCharacters(in: .whitespaces)
    let full = [f, l].filter { !$0.isEmpty }.joined(separator: " ")
    if !full.isEmpty { return full }
    if let nick = nickname?.trimmingCharacters(in: .whitespaces), !nick.isEmpty { return nick }
    if let company = org?.trimmingCharacters(in: .whitespaces), !company.isEmpty { return company }
    return nil
  }

  // MARK: - Load

  private func ensureLoaded() async {
    guard phoneToName == nil || emailToName == nil else { return }
    var phones: [String: String] = [:]
    var emails: [String: String] = [:]

    for dbURL in Self.addressBookDatabaseURLs() {
      do {
        var config = Configuration()
        config.readonly = true
        let queue = try DatabaseQueue(path: dbURL.path, configuration: config)
        let (dbPhones, dbEmails) = try await queue.read { db in
          (Self.fetchPhones(db), Self.fetchEmails(db))
        }
        // First non-empty name for a key wins — don't let a later, sparser store overwrite it.
        for (key, name) in dbPhones where phones[key] == nil { phones[key] = name }
        for (key, name) in dbEmails where emails[key] == nil { emails[key] = name }
      } catch {
        // Unreadable store (no FDA, locked, or schema mismatch) — skip it, keep any others.
        log("ContactNameResolver: could not read \(dbURL.lastPathComponent): \(error)")
      }
    }

    phoneToName = phones
    emailToName = emails
    log(
      "ContactNameResolver: loaded \(phones.count) phone + \(emails.count) email contact names")
  }

  /// Fetch phone-key → name pairs from one AddressBook store (keeps the first name per key).
  private static func fetchPhones(_ db: Database) -> [(String, String)] {
    let rows =
      (try? Row.fetchAll(
        db,
        sql: """
            SELECT r.ZFIRSTNAME AS first, r.ZLASTNAME AS last, r.ZNICKNAME AS nick,
                   r.ZORGANIZATION AS org, p.ZFULLNUMBER AS number
            FROM ZABCDPHONENUMBER p
            JOIN ZABCDRECORD r ON r.Z_PK = p.ZOWNER
            WHERE p.ZFULLNUMBER IS NOT NULL
          """)) ?? []
    var out: [(String, String)] = []
    var seen = Set<String>()
    for row in rows {
      guard let number = row["number"] as? String, let key = phoneKey(number) else { continue }
      guard !seen.contains(key) else { continue }
      if let name = formatName(
        first: row["first"], last: row["last"], nickname: row["nick"], org: row["org"])
      {
        seen.insert(key)
        out.append((key, name))
      }
    }
    return out
  }

  /// Fetch email → name pairs from one AddressBook store (keeps the first name per address).
  private static func fetchEmails(_ db: Database) -> [(String, String)] {
    let rows =
      (try? Row.fetchAll(
        db,
        sql: """
            SELECT r.ZFIRSTNAME AS first, r.ZLASTNAME AS last, r.ZNICKNAME AS nick,
                   r.ZORGANIZATION AS org, e.ZADDRESS AS address
            FROM ZABCDEMAILADDRESS e
            JOIN ZABCDRECORD r ON r.Z_PK = e.ZOWNER
            WHERE e.ZADDRESS IS NOT NULL
          """)) ?? []
    var out: [(String, String)] = []
    var seen = Set<String>()
    for row in rows {
      guard let address = row["address"] as? String else { continue }
      let key = address.lowercased().trimmingCharacters(in: .whitespaces)
      guard !key.isEmpty, !seen.contains(key) else { continue }
      if let name = formatName(
        first: row["first"], last: row["last"], nickname: row["nick"], org: row["org"])
      {
        seen.insert(key)
        out.append((key, name))
      }
    }
    return out
  }

  /// Every `AddressBook-v22.abcddb` store: the top-level local store plus each iCloud/exchange
  /// source under `Sources/<uuid>/`. Reading all of them covers contacts from every account.
  private static func addressBookDatabaseURLs() -> [URL] {
    let base = FileManager.default.homeDirectoryForCurrentUser
      .appendingPathComponent("Library/Application Support/AddressBook", isDirectory: true)
    var urls: [URL] = []

    let topLevel = base.appendingPathComponent("AddressBook-v22.abcddb", isDirectory: false)
    if FileManager.default.fileExists(atPath: topLevel.path) { urls.append(topLevel) }

    let sources = base.appendingPathComponent("Sources", isDirectory: true)
    if let entries = try? FileManager.default.contentsOfDirectory(
      at: sources, includingPropertiesForKeys: nil)
    {
      for entry in entries {
        let candidate = entry.appendingPathComponent("AddressBook-v22.abcddb", isDirectory: false)
        if FileManager.default.fileExists(atPath: candidate.path) { urls.append(candidate) }
      }
    }
    return urls
  }
}
