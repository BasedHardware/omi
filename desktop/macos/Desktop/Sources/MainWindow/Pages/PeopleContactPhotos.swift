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

  /// One pass over the local Contacts store, writing a thumbnail for every resolved person that has
  /// one. Returns `person id → file path` for the caller to stamp onto the person cards.
  ///
  /// Only runs when access is **already** authorized (never prompts — `PeopleContactsAccess` owns
  /// that), and only when there is at least one phone→person mapping to match against. Logs counts
  /// only: no name, number, or path with a name in it is ever logged.
  static func syncFromContacts(idByPhone: [String: String], userDir: URL) -> [String: String] {
    guard CNContactStore.authorizationStatus(for: .contacts) == .authorized else { return [:] }
    guard !idByPhone.isEmpty else { return [:] }

    var paths: [String: String] = [:]
    var written = 0
    let keys: [CNKeyDescriptor] = [
      CNContactPhoneNumbersKey as CNKeyDescriptor,
      CNContactImageDataAvailableKey as CNKeyDescriptor,
      // Thumbnail, never CNContactImageDataKey: the full-size image is orders of magnitude larger
      // and the UI only ever renders a 28–96pt circle.
      CNContactThumbnailImageDataKey as CNKeyDescriptor,
    ]
    let request = CNContactFetchRequest(keysToFetch: keys)
    request.sortOrder = .none
    do {
      try CNContactStore().enumerateContacts(with: request) { contact, _ in
        guard contact.imageDataAvailable, let data = contact.thumbnailImageData, !data.isEmpty else {
          return
        }
        for phone in contact.phoneNumbers {
          guard let key = PeopleGraphBuilder.last10(phone.value.stringValue),
            let id = idByPhone[key], paths[id] == nil
          else { continue }
          switch store(thumbnail: data, forID: id, in: userDir) {
          case .written(let path):
            paths[id] = path
            written += 1
          case .unchanged(let path):
            paths[id] = path
          case .skipped:
            continue
          }
        }
      }
    } catch {
      log("PeopleContactPhotos: Contacts enumeration failed: \(error.localizedDescription)")
      return paths
    }
    log("PeopleContactPhotos: \(paths.count) people have a contact photo (\(written) written this run)")
    return paths
  }
}
