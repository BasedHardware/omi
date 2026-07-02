import Foundation
import GRDB

/// Resolves an iMessage handle (phone/email) to a contact name and photo.
///
/// Reads the macOS AddressBook database directly (via Full Disk Access, which the
/// app already holds for reading Messages) instead of the Contacts framework —
/// the Contacts TCC prompt does not fire for self-signed dev builds, and reading
/// the DB works identically in production. Best-effort: unknown handles fall back
/// to the raw handle / initials.
actor IMessageContactResolver {
  static let shared = IMessageContactResolver()

  private var loaded = false
  private var nameByPhone: [String: String] = [:]  // normalized phone digits -> name
  private var imageByPhone: [String: Data] = [:]
  private var nameByEmail: [String: String] = [:]  // lowercased email -> name
  private var imageByEmail: [String: Data] = [:]

  func displayName(for handle: String) async -> String? {
    await ensureLoaded()
    return resolve(handle).name
  }

  func imageData(for handle: String) async -> Data? {
    await ensureLoaded()
    return resolve(handle).image
  }

  /// Reads the full macOS address book and returns one sync payload per contact
  /// record — the contact's display name plus every phone/email handle. Built from
  /// the same AddressBook DBs the resolver loads. Handles are raw (phone strings
  /// as-is, emails lowercased); the backend canonicalizes them. Records with no
  /// name AND no handles are skipped; handles are de-duped within a contact.
  /// Degrades to `[]` if the DB can't be opened.
  func allContacts() async -> [IMessageContactSyncPayload] {
    var payloads: [IMessageContactSyncPayload] = []
    for url in addressBookDatabaseURLs() {
      payloads.append(contentsOf: contacts(in: url))
    }
    return payloads
  }

  /// Force a reload on next lookup (e.g. after contacts change).
  func resetAuth() {
    loaded = false
    nameByPhone.removeAll()
    imageByPhone.removeAll()
    nameByEmail.removeAll()
    imageByEmail.removeAll()
  }

  // MARK: - lookup

  private func resolve(_ handle: String) -> (name: String?, image: Data?) {
    let h = handle.trimmingCharacters(in: .whitespacesAndNewlines)
    guard !h.isEmpty else { return (nil, nil) }
    if h.contains("@") {
      let key = h.lowercased()
      return (nameByEmail[key], imageByEmail[key])
    }
    guard let key = Self.normalizedPhoneKey(h) else { return (nil, nil) }
    return (nameByPhone[key], imageByPhone[key])
  }

  /// Normalizes a phone number to a lookup key by keeping the full digit string,
  /// only stripping a leading `1` from 11-digit US numbers. Matches
  /// `IMessageReaderService.prettyHandle` so distinct international numbers that
  /// share a 10-digit suffix (e.g. UK `+44 20 7946 0958` vs `020 7946 0958`) don't
  /// collapse to the same contact. Returns nil for numbers with fewer than 7 digits.
  static func normalizedPhoneKey(_ raw: String) -> String? {
    let digits = raw.filter { $0.isNumber }
    guard digits.count >= 7 else { return nil }
    if digits.count == 11 && digits.hasPrefix("1") { return String(digits.dropFirst()) }
    return digits
  }

  private func ensureLoaded() async {
    if loaded { return }
    loaded = true
    for url in addressBookDatabaseURLs() {
      loadDatabase(url)
    }
  }

  private func addressBookDatabaseURLs() -> [URL] {
    let fm = FileManager.default
    let base = fm.homeDirectoryForCurrentUser
      .appendingPathComponent("Library/Application Support/AddressBook", isDirectory: true)
    var urls: [URL] = []

    let top = base.appendingPathComponent("AddressBook-v22.abcddb", isDirectory: false)
    if fm.fileExists(atPath: top.path) { urls.append(top) }

    let sources = base.appendingPathComponent("Sources", isDirectory: true)
    if let items = try? fm.contentsOfDirectory(at: sources, includingPropertiesForKeys: nil) {
      for dir in items {
        let db = dir.appendingPathComponent("AddressBook-v22.abcddb", isDirectory: false)
        if fm.fileExists(atPath: db.path) { urls.append(db) }
      }
    }
    return urls
  }

  private func loadDatabase(_ url: URL) {
    var config = Configuration()
    config.readonly = true
    guard let queue = try? DatabaseQueue(path: url.path, configuration: config) else { return }

    try? queue.read { db in
      // Phone numbers -> name. Kept separate from image so a missing image column
      // never breaks name resolution.
      if let rows = try? Row.fetchAll(
        db,
        sql: """
            SELECT r.ZFIRSTNAME AS f, r.ZLASTNAME AS l, r.ZORGANIZATION AS org,
                   r.ZNICKNAME AS nick, p.ZFULLNUMBER AS num
            FROM ZABCDPHONENUMBER p JOIN ZABCDRECORD r ON p.ZOWNER = r.Z_PK
          """)
      {
        for row in rows {
          guard let num = row["num"] as? String, let key = Self.normalizedPhoneKey(num) else { continue }
          if nameByPhone[key] == nil, let name = Self.composeName(row) { nameByPhone[key] = name }
        }
      }

      // Emails -> name.
      if let rows = try? Row.fetchAll(
        db,
        sql: """
            SELECT r.ZFIRSTNAME AS f, r.ZLASTNAME AS l, r.ZORGANIZATION AS org,
                   r.ZNICKNAME AS nick, e.ZADDRESS AS addr
            FROM ZABCDEMAILADDRESS e JOIN ZABCDRECORD r ON e.ZOWNER = r.Z_PK
          """)
      {
        for row in rows {
          guard let addr = (row["addr"] as? String)?.lowercased() else { continue }
          if nameByEmail[addr] == nil, let name = Self.composeName(row) { nameByEmail[addr] = name }
        }
      }

      // Photos (optional — column may not exist on all macOS versions).
      if let rows = try? Row.fetchAll(
        db,
        sql: """
            SELECT p.ZFULLNUMBER AS num, r.ZTHUMBNAILIMAGEDATA AS img
            FROM ZABCDPHONENUMBER p JOIN ZABCDRECORD r ON p.ZOWNER = r.Z_PK
            WHERE r.ZTHUMBNAILIMAGEDATA IS NOT NULL
          """)
      {
        for row in rows {
          guard let num = row["num"] as? String, let img = row["img"] as? Data, !img.isEmpty,
            let key = Self.normalizedPhoneKey(num)
          else { continue }
          if imageByPhone[key] == nil { imageByPhone[key] = img }
        }
      }
      if let rows = try? Row.fetchAll(
        db,
        sql: """
            SELECT e.ZADDRESS AS addr, r.ZTHUMBNAILIMAGEDATA AS img
            FROM ZABCDEMAILADDRESS e JOIN ZABCDRECORD r ON e.ZOWNER = r.Z_PK
            WHERE r.ZTHUMBNAILIMAGEDATA IS NOT NULL
          """)
      {
        for row in rows {
          guard let addr = (row["addr"] as? String)?.lowercased(), let img = row["img"] as? Data, !img.isEmpty
          else { continue }
          if imageByEmail[addr] == nil { imageByEmail[addr] = img }
        }
      }
    }
  }

  /// Reads one AddressBook DB and returns a sync payload per record, grouping each
  /// record's phone numbers and email addresses (joined via `ZOWNER = Z_PK`) under
  /// its composed display name. Records are keyed by `Z_PK`, which is unique within
  /// a single DB file. Returns `[]` if the DB can't be opened.
  private func contacts(in url: URL) -> [IMessageContactSyncPayload] {
    var config = Configuration()
    config.readonly = true
    guard let queue = try? DatabaseQueue(path: url.path, configuration: config) else { return [] }

    var nameByPK: [Int64: String] = [:]
    var handlesByPK: [Int64: [String]] = [:]
    var seenByPK: [Int64: Set<String>] = [:]

    // Appends a handle to a record, de-duping (case-insensitively) within the record.
    func add(_ handle: String, to pk: Int64) {
      let h = handle.trimmingCharacters(in: .whitespacesAndNewlines)
      guard !h.isEmpty else { return }
      let key = h.lowercased()
      var seen = seenByPK[pk] ?? []
      guard !seen.contains(key) else { return }
      seen.insert(key)
      seenByPK[pk] = seen
      handlesByPK[pk, default: []].append(h)
    }

    try? queue.read { db in
      if let rows = try? Row.fetchAll(
        db,
        sql: """
            SELECT r.Z_PK AS pk, r.ZFIRSTNAME AS f, r.ZLASTNAME AS l, r.ZORGANIZATION AS org,
                   r.ZNICKNAME AS nick, p.ZFULLNUMBER AS num
            FROM ZABCDPHONENUMBER p JOIN ZABCDRECORD r ON p.ZOWNER = r.Z_PK
          """)
      {
        for row in rows {
          guard let pk = row["pk"] as? Int64 else { continue }
          if nameByPK[pk] == nil, let name = Self.composeName(row) { nameByPK[pk] = name }
          if let num = row["num"] as? String { add(num, to: pk) }
        }
      }

      if let rows = try? Row.fetchAll(
        db,
        sql: """
            SELECT r.Z_PK AS pk, r.ZFIRSTNAME AS f, r.ZLASTNAME AS l, r.ZORGANIZATION AS org,
                   r.ZNICKNAME AS nick, e.ZADDRESS AS addr
            FROM ZABCDEMAILADDRESS e JOIN ZABCDRECORD r ON e.ZOWNER = r.Z_PK
          """)
      {
        for row in rows {
          guard let pk = row["pk"] as? Int64 else { continue }
          if nameByPK[pk] == nil, let name = Self.composeName(row) { nameByPK[pk] = name }
          if let addr = (row["addr"] as? String)?.lowercased() { add(addr, to: pk) }
        }
      }
    }

    var payloads: [IMessageContactSyncPayload] = []
    for pk in Set(nameByPK.keys).union(handlesByPK.keys) {
      let name = nameByPK[pk]
      let handles = handlesByPK[pk] ?? []
      guard name != nil || !handles.isEmpty else { continue }
      payloads.append(IMessageContactSyncPayload(name: name ?? "", handles: handles))
    }
    return payloads
  }

  private static func composeName(_ row: Row) -> String? {
    let first = (row["f"] as? String) ?? ""
    let last = (row["l"] as? String) ?? ""
    let full = "\(first) \(last)".trimmingCharacters(in: .whitespaces)
    if !full.isEmpty { return full }
    if let nick = row["nick"] as? String, !nick.isEmpty { return nick }
    if let org = row["org"] as? String, !org.isEmpty { return org }
    return nil
  }
}
