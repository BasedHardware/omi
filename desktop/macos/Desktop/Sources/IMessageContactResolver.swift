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
  private var nameByPhone: [String: String] = [:]  // last-10-digits -> name
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
    let digits = h.filter { $0.isNumber }
    guard digits.count >= 7 else { return (nil, nil) }
    let key = String(digits.suffix(10))
    return (nameByPhone[key], imageByPhone[key])
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
          guard let num = row["num"] as? String else { continue }
          let digits = num.filter { $0.isNumber }
          guard digits.count >= 7 else { continue }
          let key = String(digits.suffix(10))
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
          guard let num = row["num"] as? String, let img = row["img"] as? Data, !img.isEmpty else { continue }
          let digits = num.filter { $0.isNumber }
          guard digits.count >= 7 else { continue }
          let key = String(digits.suffix(10))
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
