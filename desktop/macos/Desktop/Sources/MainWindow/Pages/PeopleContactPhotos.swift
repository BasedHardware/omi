import Contacts
import Foundation

/// Writes the local address book's contact thumbnails into the per-user `people_photos/` folder the
/// People UI already reads (`PeoplePhotos.photoPath(forID:)`, `PersonProfileAvatar`).
///
/// Every avatar surface was a read of a folder nothing ever wrote, so every person fell back to
/// initials even though macOS had their photo the whole time. The photo is fetched with the same
/// already-granted Contacts access the naming pass uses — no new permission, no network, nothing
/// leaves the machine — and only the small `thumbnailImageData` is read, never the full-size image.
///
/// All IO is guarded and runs on `PeopleGraphBuilder.build()`'s detached utility task (never the
/// main actor). A missing folder, unreadable contact, or failed write is a no-op, never a crash.
enum PeopleContactPhotos {
  /// Folder name under the per-user directory. Must match `PeoplePhotos.photosDirectory()`.
  static let directoryName = "people_photos"

  /// Outcome of storing one thumbnail. `unchanged` is the common case after the first run — the
  /// bytes are compared before writing so a re-run does not rewrite every photo.
  enum StoreResult: Equatable {
    case written(String)
    case unchanged(String)
    case skipped

    var path: String? {
      switch self {
      case .written(let path), .unchanged(let path): return path
      case .skipped: return nil
      }
    }
  }

  static func directory(in userDir: URL) -> URL {
    userDir.appendingPathComponent(directoryName, isDirectory: true)
  }

  /// File name for a person id, or `nil` when the id is not safe to put in a path.
  ///
  /// Person ids are `PeopleGraphBuilder.slug()` output (ASCII letters/digits/dashes), so an id
  /// carrying `/`, `..`, or anything else is rejected rather than rewritten: the reader builds its
  /// path from the **raw** id, so a sanitized-but-different name would simply never be found — and
  /// an id that escapes the folder must never be written at all.
  static func fileName(forID id: String) -> String? {
    guard !id.isEmpty, id.count <= 128 else { return nil }
    let safe = id.allSatisfy { char in
      (char.isASCII && (char.isLetter || char.isNumber)) || char == "-" || char == "_"
    }
    guard safe else { return nil }
    return "\(id).jpg"
  }

  /// Store one thumbnail for `id` under `<userDir>/people_photos/`. Skips the write when the file
  /// already holds exactly these bytes, so repeat runs are free.
  @discardableResult
  static func store(thumbnail data: Data, forID id: String, in userDir: URL) -> StoreResult {
    guard !data.isEmpty, let name = fileName(forID: id) else { return .skipped }
    let url = directory(in: userDir).appendingPathComponent(name)
    if let existing = try? Data(contentsOf: url), existing == data { return .unchanged(url.path) }
    do {
      try FileManager.default.createDirectory(
        at: url.deletingLastPathComponent(), withIntermediateDirectories: true)
      try data.write(to: url, options: .atomic)
      return .written(url.path)
    } catch {
      return .skipped
    }
  }

  // MARK: - Matching (pure, streaming, testable)

  /// What one pass over the address book actually did.
  ///
  /// A bare `[:]` cannot tell "Contacts refused us" apart from "your address book has no photos"
  /// apart from "we read the photos but no number matched anyone" — and that ambiguity is exactly
  /// what made a real production zero unattributable. Every field here is a count, never an
  /// identity.
  struct SyncStats: Equatable {
    /// Address-book entries that carried thumbnail bytes.
    var contactsWithPhoto = 0
    /// Entries whose photo was claimed by at least one person on the graph.
    var matchedContacts = 0
    var written = 0
    var unchanged = 0

    /// Entries that had a photo but whose numbers matched nobody the graph knows.
    var unmatchedContacts: Int { contactsWithPhoto - matchedContacts }
  }

  /// The match-and-store half of `syncFromContacts`, with `CNContactStore` factored out.
  ///
  /// The enumeration is the only part that needs a live address book; the part that actually
  /// decides *whether a photo lands* — normalizing a contact's phone number the same way
  /// `People.idByPhone` is keyed, and rejecting an id that is not a safe file name — is pure, so it
  /// is exercised directly by tests instead of being unreachable behind a TCC grant. Streaming
  /// (rather than taking `[Contact]`) so a large address book never holds every thumbnail in
  /// memory at once.
  struct Sink {
    /// `phone_last10 → person id`, exactly as `PeopleGraphBuilder.People.idByPhone` keys it.
    let idByPhone: [String: String]
    let userDir: URL
    private(set) var paths: [String: String] = [:]
    private(set) var stats = SyncStats()

    init(idByPhone: [String: String], userDir: URL) {
      self.idByPhone = idByPhone
      self.userDir = userDir
    }

    /// Offer one address-book entry. `phoneNumbers` are raw, in whatever format the user typed
    /// them — they are normalized here with the *same* `last10` the graph keys people by, because
    /// two normalizers would silently drop every photo whose number is stored in a different
    /// format from the one the messaging export reported.
    mutating func offer(phoneNumbers: [String], thumbnail: Data) {
      guard !thumbnail.isEmpty else { return }
      stats.contactsWithPhoto += 1
      var claimed = false
      for phone in phoneNumbers {
        guard let key = PeopleGraphBuilder.last10(phone), let id = idByPhone[key], paths[id] == nil
        else { continue }
        switch PeopleContactPhotos.store(thumbnail: thumbnail, forID: id, in: userDir) {
        case .written(let path):
          paths[id] = path
          stats.written += 1
          claimed = true
        case .unchanged(let path):
          paths[id] = path
          stats.unchanged += 1
          claimed = true
        case .skipped:
          continue
        }
      }
      if claimed { stats.matchedContacts += 1 }
    }
  }

  // MARK: - One pass over the address book

  /// One pass over the local Contacts store, writing a thumbnail for every resolved person that has
  /// one. Returns `person id → file path` for the caller to stamp onto the person cards.
  ///
  /// Only runs when access is **already** authorized (never prompts — `PeopleContactsAccess` owns
  /// that), and only when there is at least one phone→person mapping to match against. Both of
  /// those, and the outcome itself, are logged as **counts and an authorization state only**: no
  /// name, number, or path containing a name ever reaches the log.
  static func syncFromContacts(idByPhone: [String: String], userDir: URL) -> [String: String] {
    let status = CNContactStore.authorizationStatus(for: .contacts)
    guard status == .authorized else {
      // Says which of the five ways a zero can happen actually happened. Previously this returned
      // silently, so "no photos" and "Contacts said no" were the same observation.
      log("PeopleContactPhotos: read nothing — Contacts authorization is \(label(status)), not authorized")
      return [:]
    }
    guard !idByPhone.isEmpty else {
      log("PeopleContactPhotos: read nothing — the graph resolved no phone identity to match against")
      return [:]
    }

    var sink = Sink(idByPhone: idByPhone, userDir: userDir)
    let keys: [CNKeyDescriptor] = [
      CNContactPhoneNumbersKey as CNKeyDescriptor,
      CNContactImageDataAvailableKey as CNKeyDescriptor,
      // Thumbnail, never CNContactImageDataKey: the full-size image is orders of magnitude larger
      // and the UI only ever renders a 28–96pt circle.
      CNContactThumbnailImageDataKey as CNKeyDescriptor,
    ]
    let request = CNContactFetchRequest(keysToFetch: keys)
    request.sortOrder = .none
    // The store must outlive the enumeration it is driving; a temporary in the `try` expression
    // leaves that to the optimizer.
    let store = CNContactStore()
    do {
      try store.enumerateContacts(with: request) { contact, _ in
        guard contact.imageDataAvailable, let data = contact.thumbnailImageData else { return }
        sink.offer(phoneNumbers: contact.phoneNumbers.map { $0.value.stringValue }, thumbnail: data)
      }
    } catch {
      log("PeopleContactPhotos: Contacts enumeration failed: \(error.localizedDescription)")
      return sink.paths
    }
    withExtendedLifetime(store) {}
    let stats = sink.stats
    log(
      "PeopleContactPhotos: \(stats.contactsWithPhoto) contact(s) with a photo, "
        + "\(sink.paths.count) matched a person (\(stats.written) written, \(stats.unchanged) unchanged), "
        + "\(stats.unmatchedContacts) matched nobody")
    return sink.paths
  }

  /// Authorization state as a word, for the log. Deliberately not `String(describing:)` — a raw
  /// enum case number tells a reader nothing about what to do next.
  private static func label(_ status: CNAuthorizationStatus) -> String {
    switch status {
    case .notDetermined: return "not yet requested"
    case .restricted: return "restricted by policy"
    case .denied: return "denied"
    case .authorized: return "authorized"
    @unknown default: return "an unhandled state"
    }
  }
}
