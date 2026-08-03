import Combine
import Foundation
import GRDB

/// Per-person message history — the model the person profile page renders as a chat log.
///
/// Omi does **not** store message text. Everything here is read live, on demand, from the
/// on-device stores (`~/Library/Messages/chat.db` and WhatsApp's `ChatStorage.sqlite`) through a
/// disposable read-only snapshot, exactly the way `PeopleThreadIngest` and `WhatsAppReader` already
/// read them. Nothing is persisted, nothing is uploaded, and closing the model reaps the snapshot.
///
/// Three properties of this surface are load-bearing:
///
///  - **Consent-gated.** `DefaultsKey.peopleIMessageExport` (default false) is the same flag that
///    gates the exporters. When it is off the model publishes `.needsConsent` and performs *zero*
///    reads — the profile page must not silently widen on-device access.
///  - **Off-main by construction.** Every copy / SQLite read happens inside
///    `Task.detached(priority: .utility)` behind `PersonMessageHistoryStore`; the `@MainActor` model
///    only awaits values. Opening `chat.db` means copying a multi-hundred-megabyte database — it can
///    never touch the main actor.
///  - **Snapshot is opened once per model.** `PeopleThreadIngest`'s path copies `chat.db` twice per
///    thread (once to enumerate candidates, once to read messages). A chat log that pages backwards
///    would multiply that by every scroll, so the store caches the opened copies for its lifetime and
///    deletes them on `reset()` / `deinit`.
///
/// Unlike the ingest path, message text is **not** redacted here: redaction exists so text can leave
/// the machine, and this render never does. Message text is likewise never logged.

// MARK: - Rendered model

/// One message in a person's conversation with the user, ready to render.
struct PersonMessage: Identifiable, Equatable, Sendable {
  /// `"<channel>:<row id>"` — stable across reads, so overlapping pages de-duplicate.
  let id: String
  let text: String
  let isFromMe: Bool
  let date: Date
  /// `PersonMessage.imessageChannel` or `PersonMessage.whatsAppChannel`.
  let channel: String

  static let imessageChannel = "imessage"
  static let whatsAppChannel = "whatsapp"
}

/// What the profile page should show instead of (or alongside) the log.
///
/// `needsConsent` and `needsFullDiskAccess` are distinct on purpose: the first is a decision the user
/// has not made, the second is a system grant they have not given. Only the second is worth sending
/// someone to System Settings for.
enum PersonMessageHistoryState: Equatable, Sendable {
  /// Nothing requested yet.
  case idle
  /// A first page is in flight. Paging older messages keeps `.loaded` so the log does not blank.
  case loading
  /// A read completed. `messages` may still be empty when no thread matches this person.
  case loaded
  /// `peopleIMessageExport` is off; nothing was read.
  case needsConsent
  /// A messaging database exists but could not be copied — the Full Disk Access signature.
  case needsFullDiskAccess
  /// No messaging database on this Mac at all.
  case unavailable
  case failed(String)
}

// MARK: - Paging

/// How far back one channel has been walked.
///
/// `offset` counts **SQL rows consumed**, not messages kept: an iMessage row can carry an
/// `attributedBody` that decodes to nothing (an attachment-only message), and those rows are dropped
/// in Swift after the query. Advancing by kept-message count would silently re-read the dropped rows
/// forever and the log would stop paging.
struct PersonMessageCursor: Equatable, Sendable {
  var offset: Int = 0
  /// True once a page came back short — there is no older history on this channel.
  var exhausted: Bool = false

  /// Advance past the rows a page consumed. A short page means the channel ran out.
  mutating func advance(rowsScanned: Int, rowsRequested: Int) {
    offset += max(rowsScanned, 0)
    if rowsScanned < rowsRequested { exhausted = true }
  }

  /// Mark a channel that has no matching thread at all, so paging never asks it again.
  mutating func finish() {
    exhausted = true
  }
}

/// Both channels' cursors. They advance independently — a person may have ten years of iMessage and
/// three months of WhatsApp, and the merged log must keep paging until *both* run dry.
struct PersonMessageCursors: Equatable, Sendable {
  var imessage = PersonMessageCursor()
  var whatsApp = PersonMessageCursor()

  var hasMore: Bool { !imessage.exhausted || !whatsApp.exhausted }
}

/// One page request: who, and how far back each channel already is.
struct PersonMessagePageRequest: Equatable, Sendable {
  let personID: String
  let contactName: String?
  let displayName: String
  let cursors: PersonMessageCursors
  let pageSize: Int
}

/// The result of one page read. Non-`page` cases are terminal for this model instance's session.
enum PersonMessagePageOutcome: Equatable, Sendable {
  case page(messages: [PersonMessage], cursors: PersonMessageCursors)
  case needsFullDiskAccess
  case unavailable
  case failed(String)
}

/// The seam the model reads through. Production uses `PersonMessageHistoryStore`; tests substitute a
/// stub so "consent off performs zero reads" is a behavioral assertion rather than code inspection.
protocol PersonMessageHistorySource: Sendable {
  func page(_ request: PersonMessagePageRequest) async -> PersonMessagePageOutcome
  /// Release the cached snapshot and delete its temp copies. Re-opening on a later `page` is fine.
  func close() async
}

// MARK: - Thread matching (pure)

/// A thread that might belong to a person, before any message text is read.
struct PersonThreadRef: Equatable, Sendable {
  /// iMessage `chat.ROWID`, or WhatsApp `ZWACHATSESSION.Z_PK`.
  let chatID: Int64
  let channel: String
  /// The counterpart's resolved name, or nil when the store could not name them.
  let contactName: String?
}

/// The pure half of the reader: person↔thread identity, page merging, and the SQL-free helpers the
/// tests drive. Kept separate from the IO so the matching rules are unit-testable without a database.
enum PersonMessageMatching {
  /// The people-graph identity for a name, or nil when the name carries no identity.
  ///
  /// `PeopleGraphBuilder.slug` — the single authority for person ids — maps an empty or
  /// non-ASCII-only name to the literal `"person"`. Treating that as a match key would fuse every
  /// unnamed thread onto whichever person happens to slug to `"person"`, so a name with no ASCII
  /// letter or digit is rejected outright rather than slugged.
  static func identity(for name: String?) -> String? {
    guard let name else { return nil }
    let trimmed = name.trimmingCharacters(in: .whitespacesAndNewlines)
    guard trimmed.contains(where: { $0.isASCII && ($0.isLetter || $0.isNumber) }) else { return nil }
    return PeopleGraphBuilder.slug(trimmed)
  }

  /// Every identity a thread may match this person on: the person id itself (already a slug), plus
  /// the slugs of their contact name and display name. `contactName` is optional because the people
  /// file does not carry one for every person — the display name alone still matches.
  static func matchKeys(personID: String, contactName: String?, displayName: String) -> Set<String> {
    var keys: Set<String> = []
    let trimmedID = personID.trimmingCharacters(in: .whitespacesAndNewlines)
    if !trimmedID.isEmpty { keys.insert(trimmedID) }
    if let contact = identity(for: contactName) { keys.insert(contact) }
    if let display = identity(for: displayName) { keys.insert(display) }
    return keys
  }

  /// Whether a candidate thread belongs to the person described by `keys`. A thread whose
  /// counterpart could not be named never matches — an unnamed thread is not evidence of anyone.
  static func matches(_ candidate: PersonThreadRef, keys: Set<String>) -> Bool {
    guard let key = identity(for: candidate.contactName) else { return false }
    return keys.contains(key)
  }

  /// Merge per-channel pages into one chronological log: de-duplicated by id, oldest first, with a
  /// deterministic tiebreak so two messages sharing a timestamp never reorder between reads.
  static func merge(_ groups: [[PersonMessage]]) -> [PersonMessage] {
    var seen = Set<String>()
    var out: [PersonMessage] = []
    for group in groups {
      for message in group where !seen.contains(message.id) {
        seen.insert(message.id)
        out.append(message)
      }
    }
    out.sort { $0.date != $1.date ? $0.date < $1.date : $0.id < $1.id }
    return out
  }
}

// MARK: - On-device snapshot (IO, never on the main actor)

/// The opened read-only copies plus the name map, cached for one store's lifetime.
///
/// `DatabaseQueue` is `@unchecked Sendable` in GRDB and is safe to read from any thread, so this
/// whole value crosses into `Task.detached` without copying a database again.
struct PersonMessageSnapshot: Sendable {
  let imessage: DatabaseQueue?
  let whatsApp: DatabaseQueue?
  /// `phone_last10 → display name`, resolved the same way the deep ingest resolves it.
  let namesByPhone: [String: String]
  /// A database file exists but its snapshot copy failed — the Full Disk Access signature.
  let blockedByPermission: Bool

  var hasAnyStore: Bool { imessage != nil || whatsApp != nil }
}

/// The IO half of the reader. Every function here is `nonisolated static` and is only ever called
/// from inside `Task.detached(priority: .utility)`.
enum PersonMessageReader {
  /// Open a disposable read-only copy of each installed messaging store under `root`.
  ///
  /// `IMessageExporter.openReadOnlyCopy` is reused for both databases so neither live store is ever
  /// touched, locked, or mutated. A store that is not installed is simply absent; a store that is
  /// present but cannot be copied sets `blockedByPermission`.
  nonisolated static func openSnapshot(root: URL, uid: String?) -> PersonMessageSnapshot {
    let fileManager = FileManager.default
    var blocked = false

    let chatDB = fileManager.homeDirectoryForCurrentUser
      .appendingPathComponent("Library/Messages/chat.db")
    var imessage: DatabaseQueue?
    if fileManager.fileExists(atPath: chatDB.path) {
      do {
        imessage = try IMessageExporter.openReadOnlyCopy(
          of: chatDB, into: root.appendingPathComponent("imessage", isDirectory: true))
      } catch {
        // The file is there and we still cannot copy it: that is the missing-grant shape, not a
        // corrupt database. Never log the path or the error body — this is a private store.
        blocked = true
      }
    }

    let whatsAppDB = WhatsAppReader.groupContainer.appendingPathComponent("ChatStorage.sqlite")
    var whatsApp: DatabaseQueue?
    if fileManager.fileExists(atPath: whatsAppDB.path) {
      do {
        whatsApp = try IMessageExporter.openReadOnlyCopy(
          of: whatsAppDB, into: root.appendingPathComponent("whatsapp", isDirectory: true))
      } catch {
        blocked = true
      }
    }

    // iMessage stores phone numbers only, so a thread is unnamed — and therefore unmatchable —
    // without this map. WhatsApp carries `ZPARTNERNAME` and needs no lookup.
    let names = imessage == nil ? [:] : namesByPhone(uid: uid)
    return PersonMessageSnapshot(
      imessage: imessage, whatsApp: whatsApp, namesByPhone: names, blockedByPermission: blocked)
  }

  /// The same name resolution the deep ingest uses: macOS Contacts when authorized, else the
  /// on-device export JSONs. Falls back to Contacts alone when no user directory exists yet.
  nonisolated static func namesByPhone(uid: String?) -> [String: String] {
    guard let directory = PeopleUserDirectory.resolve(uid: uid) else {
      return PeopleGraphBuilder.loadContactsByPhone()
    }
    return PeopleThreadIngest.namesByPhone(directory: directory)
  }

  // MARK: Candidate threads

  /// Every named 1:1 iMessage chat, as match candidates. Group chats are excluded — a person's
  /// profile shows their conversation with the user, not every room they share.
  nonisolated static func imessageThreads(
    _ dbQueue: DatabaseQueue, namesByPhone: [String: String]
  ) -> [PersonThreadRef] {
    (try? dbQueue.read { db -> [PersonThreadRef] in
      var handlesByChat: [Int64: [String]] = [:]
      let cursor = try Row.fetchCursor(
        db,
        sql: """
            SELECT chj.chat_id AS cid, h.id AS handle
            FROM chat_handle_join chj JOIN handle h ON h.ROWID = chj.handle_id
          """)
      while let row = try cursor.next() {
        guard let handle = (row["handle"] as? String)?.trimmingCharacters(in: .whitespaces),
          !handle.isEmpty
        else { continue }
        let cid = int64(row, "cid")
        if !(handlesByChat[cid]?.contains(handle) ?? false) {
          handlesByChat[cid, default: []].append(handle)
        }
      }
      return handlesByChat.compactMap { cid, handles -> PersonThreadRef? in
        guard handles.count == 1, let handle = handles.first else { return nil }
        guard let phone = phoneLast10(handle), let name = namesByPhone[phone] else { return nil }
        return PersonThreadRef(chatID: cid, channel: PersonMessage.imessageChannel, contactName: name)
      }
    }) ?? []
  }

  /// Every named 1:1 WhatsApp chat, as match candidates. Mirrors `WhatsAppReader.readOneToOneThreads`
  /// but runs on the store's cached snapshot instead of copying `ChatStorage.sqlite` again.
  nonisolated static func whatsAppThreads(_ dbQueue: DatabaseQueue) -> [PersonThreadRef] {
    (try? dbQueue.read { db -> [PersonThreadRef] in
      var out: [PersonThreadRef] = []
      let cursor = try Row.fetchCursor(
        db, sql: "SELECT Z_PK AS pk, ZCONTACTJID AS jid, ZPARTNERNAME AS name FROM ZWACHATSESSION")
      while let row = try cursor.next() {
        let jid = (row["jid"] as? String)?.trimmingCharacters(in: .whitespaces) ?? ""
        guard WhatsAppReader.isRealContactJID(jid), !jid.lowercased().hasSuffix("@g.us") else {
          continue
        }
        let name = (row["name"] as? String)?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        guard !name.isEmpty else { continue }
        out.append(
          PersonThreadRef(
            chatID: int64(row, "pk"), channel: PersonMessage.whatsAppChannel, contactName: name))
      }
      return out
    }) ?? []
  }

  // MARK: Page reads

  /// One channel's page: what survived decoding, and how many SQL rows it consumed.
  struct ChannelPage: Equatable, Sendable {
    let messages: [PersonMessage]
    let rowsScanned: Int
  }

  /// Read one page of iMessage history, newest-first from `offset`, returned chronologically.
  ///
  /// `chatIDs` are `chat.ROWID` values this reader just read out of the same database, so they are
  /// interpolated as integer literals — SQLite has no array binding and the values are not user input.
  nonisolated static func imessagePage(
    _ dbQueue: DatabaseQueue, chatIDs: [Int64], limit: Int, offset: Int
  ) throws -> ChannelPage {
    guard !chatIDs.isEmpty, limit > 0 else { return ChannelPage(messages: [], rowsScanned: 0) }
    let idList = chatIDs.map(String.init).joined(separator: ",")
    return try dbQueue.read { db -> ChannelPage in
      var messages: [PersonMessage] = []
      var rowsScanned = 0
      // Both body columns: on modern macOS `m.text` is usually NULL and the string lives in the
      // `attributedBody` typedstream, which only `IMessageText.body` can decode.
      let cursor = try Row.fetchCursor(
        db,
        sql: """
            SELECT m.ROWID AS mid, m.text AS text, m.attributedBody AS attributed_body,
                   m.is_from_me AS from_me, m.date AS date
            FROM message m JOIN chat_message_join cmj ON cmj.message_id = m.ROWID
            WHERE cmj.chat_id IN (\(idList))
              AND (m.associated_message_type = 0 OR m.associated_message_type IS NULL)
              AND ((m.text IS NOT NULL AND length(trim(m.text)) > 0) OR m.attributedBody IS NOT NULL)
            ORDER BY m.date DESC
            LIMIT ? OFFSET ?
          """,
        arguments: [limit, offset])
      while let row = try cursor.next() {
        rowsScanned += 1
        guard
          let body = IMessageText.body(
            text: row["text"] as? String, attributedBody: row["attributed_body"] as? Data),
          !body.trimmingCharacters(in: .whitespaces).isEmpty
        else { continue }
        messages.append(
          PersonMessage(
            id: "\(PersonMessage.imessageChannel):\(int64(row, "mid"))",
            text: body,
            isFromMe: int64(row, "from_me") == 1,
            date: appleDate(nanosecondsOrSeconds: int64(row, "date")),
            channel: PersonMessage.imessageChannel))
      }
      return ChannelPage(messages: messages.reversed(), rowsScanned: rowsScanned)
    }
  }

  /// Read one page of WhatsApp history, newest-first from `offset`, returned chronologically.
  /// `sessionPKs` are `ZWACHATSESSION.Z_PK` values read from this same database — see `imessagePage`.
  nonisolated static func whatsAppPage(
    _ dbQueue: DatabaseQueue, sessionPKs: [Int64], limit: Int, offset: Int
  ) throws -> ChannelPage {
    guard !sessionPKs.isEmpty, limit > 0 else { return ChannelPage(messages: [], rowsScanned: 0) }
    let idList = sessionPKs.map(String.init).joined(separator: ",")
    return try dbQueue.read { db -> ChannelPage in
      var messages: [PersonMessage] = []
      var rowsScanned = 0
      let cursor = try Row.fetchCursor(
        db,
        sql: """
            SELECT Z_PK AS mid, ZTEXT AS text, ZISFROMME AS from_me, ZMESSAGEDATE AS date
            FROM ZWAMESSAGE
            WHERE ZCHATSESSION IN (\(idList))
              AND ZTEXT IS NOT NULL AND length(trim(ZTEXT)) > 0
            ORDER BY ZMESSAGEDATE DESC
            LIMIT ? OFFSET ?
          """,
        arguments: [limit, offset])
      while let row = try cursor.next() {
        rowsScanned += 1
        guard let text = (row["text"] as? String)?.trimmingCharacters(in: .whitespacesAndNewlines),
          !text.isEmpty
        else { continue }
        messages.append(
          PersonMessage(
            id: "\(PersonMessage.whatsAppChannel):\(int64(row, "mid"))",
            text: text,
            isFromMe: int64(row, "from_me") == 1,
            date: Date(timeIntervalSinceReferenceDate: coreDataSeconds(row["date"])),
            channel: PersonMessage.whatsAppChannel))
      }
      return ChannelPage(messages: messages.reversed(), rowsScanned: rowsScanned)
    }
  }

  /// Read one merged page across both channels and advance each channel's cursor.
  nonisolated static func page(
    _ request: PersonMessagePageRequest, snapshot: PersonMessageSnapshot
  ) -> PersonMessagePageOutcome {
    guard snapshot.hasAnyStore else {
      return snapshot.blockedByPermission ? .needsFullDiskAccess : .unavailable
    }
    let keys = PersonMessageMatching.matchKeys(
      personID: request.personID, contactName: request.contactName,
      displayName: request.displayName)
    var cursors = request.cursors
    var groups: [[PersonMessage]] = []

    do {
      if let dbQueue = snapshot.imessage, !cursors.imessage.exhausted {
        let ids = imessageThreads(dbQueue, namesByPhone: snapshot.namesByPhone)
          .filter { PersonMessageMatching.matches($0, keys: keys) }
          .map(\.chatID)
        if ids.isEmpty {
          cursors.imessage.finish()
        } else {
          let page = try imessagePage(
            dbQueue, chatIDs: ids, limit: request.pageSize, offset: cursors.imessage.offset)
          groups.append(page.messages)
          cursors.imessage.advance(rowsScanned: page.rowsScanned, rowsRequested: request.pageSize)
        }
      } else {
        cursors.imessage.finish()
      }

      if let dbQueue = snapshot.whatsApp, !cursors.whatsApp.exhausted {
        let ids = whatsAppThreads(dbQueue)
          .filter { PersonMessageMatching.matches($0, keys: keys) }
          .map(\.chatID)
        if ids.isEmpty {
          cursors.whatsApp.finish()
        } else {
          let page = try whatsAppPage(
            dbQueue, sessionPKs: ids, limit: request.pageSize, offset: cursors.whatsApp.offset)
          groups.append(page.messages)
          cursors.whatsApp.advance(rowsScanned: page.rowsScanned, rowsRequested: request.pageSize)
        }
      } else {
        cursors.whatsApp.finish()
      }
    } catch {
      // Never interpolate rows or text into a user-facing string — only the database error itself.
      return .failed("Couldn't read messages: \(error.localizedDescription)")
    }

    return .page(messages: PersonMessageMatching.merge(groups), cursors: cursors)
  }

  // MARK: Small helpers

  nonisolated static func int64(_ row: Row, _ column: String) -> Int64 {
    (row[column] as? Int64) ?? Int64(row[column] as? Int ?? 0)
  }

  /// `message.date` is nanoseconds since the 2001 reference date on modern macOS; legacy databases
  /// store seconds. Mirrors `IMessageExporter`.
  nonisolated static func appleDate(nanosecondsOrSeconds raw: Int64) -> Date {
    let seconds = raw > 1_000_000_000_000 ? Double(raw) / 1_000_000_000.0 : Double(raw)
    return Date(timeIntervalSinceReferenceDate: seconds)
  }

  /// WhatsApp `TIMESTAMP` columns are Core Data reference-date seconds, occasionally stored as Int.
  nonisolated static func coreDataSeconds(_ value: DatabaseValueConvertible?) -> Double {
    if let double = value as? Double { return double }
    if let int = value as? Int64 { return Double(int) }
    if let int = value as? Int { return Double(int) }
    return 0
  }

  /// Last 10 digits of a phone handle (a stable cross-format key), or nil for emails / short codes.
  nonisolated static func phoneLast10(_ handle: String) -> String? {
    if handle.contains("@") { return nil }
    let digits = handle.filter { $0.isNumber }
    guard digits.count >= 10 else { return nil }
    return String(digits.suffix(10))
  }
}

// MARK: - Store (owns the cached snapshot)

/// Owns one set of disposable database copies for the lifetime of one model.
///
/// An actor rather than a plain type so the cache cannot be raced by a scroll that fires two pages at
/// once, and so the snapshot is never reachable from the main actor. Every blocking operation still
/// runs inside `Task.detached(priority: .utility)`; the actor only holds the result.
actor PersonMessageHistoryStore: PersonMessageHistorySource {
  /// Per-instance temp root. `nonisolated let` so `deinit` can reap it without isolation hops.
  private nonisolated let root: URL
  private var snapshot: PersonMessageSnapshot?

  init() {
    root = FileManager.default.temporaryDirectory
      .appendingPathComponent("omi-person-history-\(UUID().uuidString)", isDirectory: true)
  }

  deinit {
    // A model dropped without `reset()` must not leave a copy of the user's message database on disk.
    let root = self.root
    Task.detached(priority: .utility) { try? FileManager.default.removeItem(at: root) }
  }

  func page(_ request: PersonMessagePageRequest) async -> PersonMessagePageOutcome {
    let snapshot = await currentSnapshot()
    guard snapshot.hasAnyStore else {
      return snapshot.blockedByPermission ? .needsFullDiskAccess : .unavailable
    }
    return await Task.detached(priority: .utility) {
      PersonMessageReader.page(request, snapshot: snapshot)
    }.value
  }

  func close() async {
    snapshot = nil
    let root = self.root
    await Task.detached(priority: .utility) {
      try? FileManager.default.removeItem(at: root)
    }.value
  }

  /// The cached snapshot, opening it once on first use. Re-opens after `close()` under a fresh copy.
  private func currentSnapshot() async -> PersonMessageSnapshot {
    if let snapshot { return snapshot }
    let root = self.root
    let opened = await Task.detached(priority: .utility) {
      // Reading the uid off the main actor is safe — `UserDefaults` is thread-safe — and keeps the
      // whole open path (copy + Contacts + JSON) off it.
      let uid = UserDefaults.standard.string(forKey: .authUserId)
      return PersonMessageReader.openSnapshot(root: root, uid: uid)
    }.value
    snapshot = opened
    return opened
  }
}

// MARK: - Model

/// Who a load is for. Compared as a whole so a page that lands after the profile page moved on is
/// discarded instead of appearing under the wrong person.
private struct PersonMessageIdentity: Equatable, Sendable {
  let personID: String
  let contactName: String?
  let displayName: String
}

/// The observable per-person chat log the profile page binds to.
@MainActor
final class PersonMessageHistoryModel: ObservableObject {
  /// Oldest → newest, ready to render top-to-bottom.
  @Published private(set) var messages: [PersonMessage] = []
  @Published private(set) var state: PersonMessageHistoryState = .idle
  @Published private(set) var canLoadMore = false

  /// Messages per page, per channel. Sized to fill a first screen of a chat log in one read.
  static let pageSize = 50

  private let source: PersonMessageHistorySource
  private let consentGranted: @Sendable () -> Bool
  private var identity: PersonMessageIdentity?
  private var cursors = PersonMessageCursors()
  private var isLoading = false
  /// Bumped by every `load` / `reset`, so an in-flight page that belongs to a superseded request
  /// cannot write back over newer state.
  private var generation = 0

  init(
    source: PersonMessageHistorySource = PersonMessageHistoryStore(),
    consentGranted: @escaping @Sendable () -> Bool = {
      UserDefaults.standard.bool(forKey: .peopleIMessageExport)
    }
  ) {
    self.source = source
    self.consentGranted = consentGranted
  }

  /// Load the most recent page for a person. Publishes `.needsConsent` and reads nothing when
  /// on-device message access has not been opted into.
  func load(personID: String, contactName: String?, displayName: String) async {
    let identity = PersonMessageIdentity(
      personID: personID, contactName: contactName, displayName: displayName)
    generation += 1
    let token = generation
    self.identity = identity
    messages = []
    cursors = PersonMessageCursors()
    canLoadMore = false

    guard consentGranted() else {
      state = .needsConsent
      return
    }
    state = .loading
    await fetch(identity: identity, cursors: cursors, token: token)
  }

  /// Page one screen further back through history. No-op once both channels are exhausted.
  func loadMore() async {
    guard !isLoading, canLoadMore, let identity else { return }
    guard consentGranted() else {
      state = .needsConsent
      canLoadMore = false
      return
    }
    await fetch(identity: identity, cursors: cursors, token: generation)
  }

  /// Drop everything and release the cached database copies. Safe to call from `onDisappear`.
  func reset() {
    generation += 1
    identity = nil
    messages = []
    cursors = PersonMessageCursors()
    canLoadMore = false
    state = .idle
    isLoading = false
    let source = self.source
    Task.detached(priority: .utility) { await source.close() }
  }

  private func fetch(
    identity: PersonMessageIdentity, cursors: PersonMessageCursors, token: Int
  ) async {
    isLoading = true
    let outcome = await source.page(
      PersonMessagePageRequest(
        personID: identity.personID, contactName: identity.contactName,
        displayName: identity.displayName, cursors: cursors, pageSize: Self.pageSize))
    // A newer load (or a reset) owns the published state now — leave `isLoading` to its owner.
    guard token == generation else { return }
    isLoading = false

    switch outcome {
    case .page(let newMessages, let newCursors):
      self.cursors = newCursors
      messages = PersonMessageMatching.merge([messages, newMessages])
      canLoadMore = newCursors.hasMore
      state = .loaded
    case .needsFullDiskAccess:
      canLoadMore = false
      state = .needsFullDiskAccess
    case .unavailable:
      canLoadMore = false
      state = .unavailable
    case .failed(let message):
      canLoadMore = false
      state = .failed(message)
    }
  }
}
