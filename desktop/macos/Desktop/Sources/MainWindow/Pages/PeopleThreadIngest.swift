import Contacts
import CryptoKit
import Foundation
import GRDB

/// Routes each known contact's substantial 1:1 messaging thread through Omi's OWN
/// conversation→memory pipeline so the assistant gains a deep, *searchable* understanding of your
/// relationships — for every user, with no server-side graph.
///
/// Unlike `PeopleMemoryWriter` (which submits terse, graph-derived relationship *facts* to
/// `POST /v3/memories`), this ingester submits the real conversation *content* as a bounded
/// transcript through `POST /v1/conversations/from-segments` — the exact Firebase-authed path the
/// desktop app already uses to upload on-device (Parakeet) transcriptions. That endpoint runs the
/// full `process_conversation` engine on the backend (entity/pronoun resolution, relationship-fact
/// extraction, and — crucially — the *vectorized* `new_memories_extractor` memories that chat
/// semantic-search actually reads). Reusing it gives deep understanding + searchability + per-user
/// enrichment for free, and works regardless of a user's memory cohort (canonical or legacy).
///
/// The two writers are **complementary, not duplicative**: `PeopleMemoryWriter` asserts
/// graph-structural "who-knows-whom" facts (shared groups / circles) that no single 1:1 thread
/// contains, while this ingester extracts content facts ("Alice is planning a Tahoe trip", "Bob
/// just started at Acme") from the messages themselves. Neither writes the other's facts.
///
/// Everything runs on-device and is bounded:
///   - Only **1:1** chats with a **contact you have named** (resolved via the local Contacts store,
///     authorized-only — never prompts) and a **substantial** number of readable messages.
///   - Only the **last N** messages per thread, with phone numbers / emails / OTP-style codes
///     **redacted** before anything leaves the machine.
///   - A per-run **people cap** so a first pass over a big message history trickles out.
///   - A local **ledger** (`people_thread_ingest_ledger.json`) keyed by a per-thread *window key*
///     so the same window is never resubmitted; `client_conversation_id` also gives the backend
///     server-side idempotency.
///
/// Gated behind the same `peopleIMessageExport` consent flag as the graph, plus its own sync
/// throttle. All work runs off the main thread via `Task.detached(.utility)`; every IO / network
/// failure is a silent no-op — this is best-effort background enrichment and must never crash or
/// block the People tab.
///
/// The message-reading layer (`readThreads`) is the only iMessage-specific part; the transcript
/// build, redaction, dedupe/bound, and submission are provider-agnostic so a future WhatsApp
/// adapter only needs to produce `[RawMessage]` per person.
enum PeopleThreadIngest {
  /// Max people (threads) submitted per run, so a first pass over a large message history trickles
  /// out rather than flooding the conversation list / backend. Remaining threads are picked up on
  /// subsequent throttled runs.
  static let maxPeoplePerRun = 12

  /// Only the most-recent messages of a thread are turned into a transcript (bounds token cost and
  /// stays well under the backend's 500-segment ceiling).
  static let maxMessagesPerThread = 40

  /// A thread must have at least this many readable (text) messages to be considered "substantial"
  /// — below this there isn't enough signal to ground a relationship memory.
  static let minThreadMessages = 25

  /// After redaction / empty-drop, a transcript must still have at least this many segments to be
  /// worth submitting.
  static let minSegmentsToSubmit = 6

  /// Message-count bucket used in the window key: a thread only re-ingests once it crosses a bucket
  /// boundary (or sees activity on a new day). Keeps a chatty thread from re-submitting on every
  /// single new message while still refreshing understanding as the relationship evolves.
  static let windowMessageBucket = 20

  /// Conversation source for the upload. `phone` (the from-segments default) is processed by the
  /// backend immediately for ALL plans, so memories are extracted and vectorized right away. We
  /// deliberately do NOT use `desktop`, which triggers the free-tier "lazy processing" deferral
  /// (memories only extracted when the conversation is first opened) — that would defeat
  /// searchability for the majority of users.
  static let conversationSource = "phone"

  static let ledgerFileName = "people_thread_ingest_ledger.json"

  // MARK: - Provider-agnostic value types

  /// One message in a thread. `fromMe` distinguishes the user from the counterpart; `date` is an
  /// ISO-8601 timestamp (used only for the conversation's `started_at`, never redacted).
  struct RawMessage: Equatable {
    let fromMe: Bool
    let text: String
    let date: String
  }

  /// A candidate 1:1 thread with a named contact, before message text is read.
  struct ThreadCandidate: Equatable {
    /// Stable per-person key (phone_last10 when available, else the lowercased handle).
    let personKey: String
    /// Resolved human display name (from Contacts) — used as the counterpart's speaker label.
    let contactName: String
    /// Underlying Messages chat row id, used to read the recent window.
    let chatId: Int64
    /// Count of readable (text) messages in the thread.
    let messageCount: Int
    /// ISO-8601 date of the newest readable message.
    let lastDate: String
  }

  /// A fully-prepared submission: the transcript segments plus the dedupe/idempotency keys.
  struct Submission {
    let windowKey: String
    let clientConversationId: String
    let startedAt: String?
    let segments: [APIClient.UploadSegment]
  }

  struct SubmissionPlan {
    let directory: URL
    let submissions: [Submission]
  }

  // MARK: - Entry point (gated, throttled, off-main, silent)

  /// Called after the graph builds (from `PeopleGraphBuilder.syncIfNeeded`). Self-gates on the
  /// iMessage consent flag and its own throttle, prepares a capped/deduped batch of thread
  /// transcripts off the main thread, submits each through the app's authenticated conversation
  /// client, then records the submitted window keys. Any failure — no Messages DB, no Full Disk
  /// Access, not signed in, offline — is a no-op.
  static func ingestIfNeeded(uid: String?, force: Bool = false) async {
    guard UserDefaults.standard.bool(forKey: .peopleIMessageExport) else { return }
    guard PeopleGraphBuilder.claimRun(.peopleThreadIngestLastRun, force: force) else { return }

    let plan: SubmissionPlan? = await Task.detached(priority: .utility) {
      buildPlan(uid: uid)
    }.value
    guard let plan, !plan.submissions.isEmpty else { return }

    // Submit sequentially. Only successfully-submitted window keys are recorded, so a transient
    // failure is simply retried on the next run.
    var submitted: Set<String> = []
    for submission in plan.submissions {
      do {
        let request = APIClient.CreateConversationFromSegmentsRequest(
          transcript_segments: submission.segments,
          source: conversationSource,
          started_at: submission.startedAt,
          finished_at: nil,  // backend computes from segment durations
          language: "en",
          client_conversation_id: submission.clientConversationId
        )
        _ = try await APIClient.shared.createConversationFromSegments(request)
        submitted.insert(submission.windowKey)
      } catch {
        // Silent: not-signed-in / offline / rate-limited / server error. Retried next run.
      }
    }
    guard !submitted.isEmpty else { return }
    await Task.detached(priority: .utility) {
      appendLedger(directory: plan.directory, keys: submitted)
    }.value
    log("PeopleThreadIngest: submitted \(submitted.count) thread transcript(s) for relationship understanding")
  }

  // MARK: - Off-main plan build (IO)

  /// Resolve the user directory, read substantial 1:1 threads from the Messages DB, resolve
  /// counterpart names via Contacts, dedupe/cap against the ledger, then read each selected
  /// thread's recent window and build a redacted transcript. Guarded — no DB / no access / empty
  /// returns nil.
  static func buildPlan(uid: String?) -> SubmissionPlan? {
    guard let dir = PeopleUserDirectory.resolve(uid: uid) else { return nil }

    let candidates = readThreadCandidates()
    guard !candidates.isEmpty else { return nil }

    let ledger = loadLedger(directory: dir)
    let selected = newCandidates(candidates, ledger: ledger, cap: maxPeoplePerRun)
    guard !selected.isEmpty else { return nil }

    var submissions: [Submission] = []
    for (candidate, windowKey) in selected {
      let messages = readThread(chatId: candidate.chatId, limit: maxMessagesPerThread)
      guard let built = buildTranscript(contactName: candidate.contactName, messages: messages) else {
        continue
      }
      submissions.append(
        Submission(
          windowKey: windowKey,
          clientConversationId: clientConversationId(personKey: candidate.personKey, windowKey: windowKey),
          startedAt: built.startedAt,
          segments: built.segments
        )
      )
    }
    guard !submissions.isEmpty else { return nil }
    return SubmissionPlan(directory: dir, submissions: submissions)
  }

  // MARK: - Candidate selection (pure)

  /// Keep substantial threads not already ingested for their current window, de-dupe within the run,
  /// and cap. Returns each surviving candidate paired with its window key (recorded on success).
  /// Pure and deterministic — the core of the "same window never resubmitted" guarantee.
  static func newCandidates(
    _ candidates: [ThreadCandidate], ledger: Set<String>, cap: Int
  ) -> [(ThreadCandidate, String)] {
    // Most-active threads first so the per-run cap spends its budget on the strongest signal.
    let ordered = candidates.sorted {
      $0.messageCount != $1.messageCount ? $0.messageCount > $1.messageCount : $0.personKey < $1.personKey
    }
    var seen = ledger
    var out: [(ThreadCandidate, String)] = []
    for candidate in ordered {
      guard candidate.messageCount >= minThreadMessages else { continue }
      guard PeopleMemoryWriter.isHumanName(candidate.contactName) else { continue }
      let key = windowKey(
        personKey: candidate.personKey, messageCount: candidate.messageCount, lastDate: candidate.lastDate)
      guard !seen.contains(key) else { continue }
      seen.insert(key)
      out.append((candidate, key))
      if out.count >= cap { break }
    }
    return out
  }

  /// Stable dedupe key for a thread's current "window". Combines the person, the message-count
  /// bucket, and the day of the newest message so a thread re-ingests when it grows by a bucket or
  /// sees activity on a new day, but not on every single new message.
  static func windowKey(personKey: String, messageCount: Int, lastDate: String) -> String {
    let bucket = messageCount / max(windowMessageBucket, 1)
    let day = String(lastDate.prefix(10))  // YYYY-MM-DD from an ISO-8601 timestamp
    return contentHash("\(personKey)|\(bucket)|\(day)")
  }

  /// Stable, backend-safe (`client_session_id`) id for a window, so a retry of the same window
  /// returns the same conversation instead of creating a duplicate. Bounded well under 200 chars.
  static func clientConversationId(personKey: String, windowKey: String) -> String {
    "people_thread_" + contentHash("\(personKey)|\(windowKey)")
  }

  // MARK: - Transcript build (pure)

  struct BuiltTranscript {
    let segments: [APIClient.UploadSegment]
    let startedAt: String?
  }

  /// Turn a chronological list of messages into redacted transcript segments labelled "Me" / the
  /// contact's name, with synthetic monotonic timings the backend accepts. Bounds to the last
  /// `maxMessagesPerThread`, drops messages that are empty after redaction, and returns nil when
  /// fewer than `minSegmentsToSubmit` survive (not enough to ground a memory). Pure and
  /// unit-testable — no IO.
  static func buildTranscript(contactName: String, messages: [RawMessage]) -> BuiltTranscript? {
    let window = messages.suffix(maxMessagesPerThread)
    var segments: [APIClient.UploadSegment] = []
    var startedAt: String?
    var slot = 0
    for message in window {
      let cleaned = redact(message.text).trimmingCharacters(in: .whitespacesAndNewlines)
      guard !cleaned.isEmpty else { continue }
      if startedAt == nil, !message.date.isEmpty { startedAt = message.date }
      segments.append(
        APIClient.UploadSegment(
          text: cleaned,
          speaker: message.fromMe ? "SPEAKER_00" : contactName,
          speaker_id: message.fromMe ? 0 : 1,
          is_user: message.fromMe,
          person_id: nil,
          start: Double(slot),
          end: Double(slot) + 0.9
        )
      )
      slot += 1
    }
    guard segments.count >= minSegmentsToSubmit else { return nil }
    return BuiltTranscript(segments: segments, startedAt: startedAt)
  }

  // MARK: - Redaction (pure)

  /// Redact phone numbers, emails, and OTP-style numeric codes from message text before it leaves
  /// the machine. Deliberately over-redacts numbers (privacy-first): emails → `[email]`,
  /// phone-like sequences → `[phone]`, standalone 6–8 digit codes → `[code]`. Guarded — a regex
  /// build failure just returns the input unchanged (still on-device only at this point).
  static func redact(_ text: String) -> String {
    var out = text
    // Order matters: emails first (they contain digits), then phones (long digit runs), then the
    // shorter standalone codes left over.
    out = replace(out, pattern: #"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"#, with: "[email]")
    out = replace(out, pattern: #"\+?\d[\d\s\-().]{6,}\d"#, with: "[phone]")
    out = replace(out, pattern: #"\b\d{6,8}\b"#, with: "[code]")
    return out
  }

  private static func replace(_ text: String, pattern: String, with replacement: String) -> String {
    guard let regex = try? NSRegularExpression(pattern: pattern) else { return text }
    let range = NSRange(text.startIndex..., in: text)
    return regex.stringByReplacingMatches(in: text, range: range, withTemplate: replacement)
  }

  // MARK: - Messages DB reads (IO, iMessage-specific)

  /// Enumerate 1:1 chats with a named contact and their readable-message counts. Reads a throwaway
  /// read-only copy of `chat.db` (via `IMessageExporter.openReadOnlyCopy`) so it never touches the
  /// live database. Contacts are resolved authorized-only (never prompts); an unnamed counterpart
  /// (bare phone / email) is skipped so we never build a thread we can't label.
  static func readThreadCandidates() -> [ThreadCandidate] {
    guard let dbQueue = openMessagesDB() else { return [] }
    let contactsByPhone = PeopleGraphBuilder.loadContactsByPhone()
    let iso = ISO8601DateFormatter()
    iso.formatOptions = [.withInternetDateTime]

    return
      (try? dbQueue.read { db -> [ThreadCandidate] in
        // 1:1 chats = exactly one participant handle.
        var handlesByChat: [Int64: [String]] = [:]
        let partCursor = try Row.fetchCursor(
          db,
          sql: """
              SELECT chj.chat_id AS cid, h.id AS handle
              FROM chat_handle_join chj JOIN handle h ON h.ROWID = chj.handle_id
            """)
        while let row = try partCursor.next() {
          guard let handle = (row["handle"] as? String)?.trimmingCharacters(in: .whitespaces), !handle.isEmpty
          else { continue }
          let cid = intValue(row, "cid")
          if !(handlesByChat[cid]?.contains(handle) ?? false) { handlesByChat[cid, default: []].append(handle) }
        }
        let oneToOne = handlesByChat.filter { $0.value.count == 1 }

        // Readable-message counts + newest date per chat.
        var counts: [Int64: Int] = [:]
        var newest: [Int64: Int64] = [:]
        // Count messages that carry a body in EITHER column. On modern macOS `m.text` is usually
        // NULL and the string lives in `attributedBody`, so a text-only count wildly undercounts a
        // thread (and can push a real relationship below `minThreadMessages`). Counting rows with a
        // non-empty `text` OR a present `attributedBody` restores a realistic per-thread total; the
        // exact body is decoded later by `readThread` via `IMessageText.body`.
        let aggCursor = try Row.fetchCursor(
          db,
          sql: """
              SELECT cmj.chat_id AS cid, COUNT(*) AS cnt, MAX(m.date) AS maxdate
              FROM message m JOIN chat_message_join cmj ON cmj.message_id = m.ROWID
              WHERE (m.associated_message_type = 0 OR m.associated_message_type IS NULL)
                AND ((m.text IS NOT NULL AND length(trim(m.text)) > 0) OR m.attributedBody IS NOT NULL)
              GROUP BY cmj.chat_id
            """)
        while let row = try aggCursor.next() {
          let cid = intValue(row, "cid")
          counts[cid] = Int(intValue(row, "cnt"))
          newest[cid] = intValue(row, "maxdate")
        }

        var candidates: [ThreadCandidate] = []
        for (cid, handles) in oneToOne {
          guard let handle = handles.first, let count = counts[cid], count > 0 else { continue }
          let phone = phoneLast10(handle)
          let personKey = phone ?? handle.lowercased()
          guard let phone, let name = contactsByPhone[phone], PeopleMemoryWriter.isHumanName(name) else {
            continue  // only named contacts (skips bare phones / emails we can't label)
          }
          let lastISO = newest[cid].map { isoString(appleTime: $0, iso: iso) } ?? ""
          candidates.append(
            ThreadCandidate(
              personKey: personKey, contactName: name, chatId: cid, messageCount: count, lastDate: lastISO))
        }
        return candidates
      }) ?? []
  }

  /// Read the most-recent `limit` readable messages of a chat, returned in chronological order.
  static func readThread(chatId: Int64, limit: Int) -> [RawMessage] {
    guard let dbQueue = openMessagesDB() else { return [] }
    let iso = ISO8601DateFormatter()
    iso.formatOptions = [.withInternetDateTime]

    let recentDesc: [RawMessage] =
      (try? dbQueue.read { db -> [RawMessage] in
        var out: [RawMessage] = []
        // Select both body columns. On modern macOS `m.text` is usually NULL and the message string
        // lives only in the `attributedBody` typedstream BLOB, so the old text-only filter captured
        // almost nothing recent. Include any row that has EITHER, then resolve the body in Swift via
        // `IMessageText.body` (rows that decode to nothing — e.g. attachment-only — are dropped).
        let cursor = try Row.fetchCursor(
          db,
          sql: """
              SELECT m.text AS text, m.attributedBody AS attributed_body, m.is_from_me AS from_me, m.date AS date
              FROM message m JOIN chat_message_join cmj ON cmj.message_id = m.ROWID
              WHERE cmj.chat_id = ?
                AND (m.associated_message_type = 0 OR m.associated_message_type IS NULL)
                AND ((m.text IS NOT NULL AND length(trim(m.text)) > 0) OR m.attributedBody IS NOT NULL)
              ORDER BY m.date DESC
              LIMIT ?
            """,
          arguments: [chatId, limit])
        while let row = try cursor.next() {
          guard
            let text = IMessageText.body(
              text: row["text"] as? String, attributedBody: row["attributed_body"] as? Data),
            !text.trimmingCharacters(in: .whitespaces).isEmpty
          else { continue }
          out.append(
            RawMessage(
              fromMe: intValue(row, "from_me") == 1,
              text: text,
              date: isoString(appleTime: intValue(row, "date"), iso: iso)))
        }
        return out
      }) ?? []
    return recentDesc.reversed()  // chronological for the transcript
  }

  /// Open a throwaway read-only copy of the live Messages database. The caller owns nothing to
  /// clean up beyond process temp; the copy is discarded when the temp dir is reaped by the OS.
  private static func openMessagesDB() -> DatabaseQueue? {
    let chatDB = FileManager.default.homeDirectoryForCurrentUser
      .appendingPathComponent("Library/Messages/chat.db")
    guard FileManager.default.fileExists(atPath: chatDB.path) else { return nil }
    let tempDir = FileManager.default.temporaryDirectory
      .appendingPathComponent("omi-thread-ingest-\(UUID().uuidString)", isDirectory: true)
    return try? IMessageExporter.openReadOnlyCopy(of: chatDB, into: tempDir)
  }

  // MARK: - Ledger IO (guarded)

  private struct Ledger: Codable {
    var version: Int
    var keys: [String]
  }

  /// Set of already-ingested window keys. A missing / corrupt ledger reads as empty (worst case a
  /// window is re-ingested, which the backend de-dupes via `client_conversation_id`).
  static func loadLedger(directory: URL) -> Set<String> {
    let url = directory.appendingPathComponent(ledgerFileName)
    guard let data = try? Data(contentsOf: url),
      let ledger = try? JSONDecoder().decode(Ledger.self, from: data)
    else { return [] }
    return Set(ledger.keys)
  }

  /// Merge newly-submitted window keys into the on-disk ledger. Best-effort atomic write; a failure
  /// only means those windows are re-evaluated next run.
  static func appendLedger(directory: URL, keys: Set<String>) {
    let merged = loadLedger(directory: directory).union(keys)
    let url = directory.appendingPathComponent(ledgerFileName)
    let ledger = Ledger(version: 1, keys: merged.sorted())
    do {
      let encoder = JSONEncoder()
      encoder.outputFormatting = [.prettyPrinted, .sortedKeys]
      let data = try encoder.encode(ledger)
      try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
      try data.write(to: url, options: .atomic)
    } catch {
      // Best-effort persistence; see loadLedger note. Non-fatal.
    }
  }

  // MARK: - Small helpers

  /// Lowercase hex SHA-256 — the ledger's dedupe key and the idempotency-id builder.
  static func contentHash(_ text: String) -> String {
    SHA256.hash(data: Data(text.utf8)).map { String(format: "%02x", $0) }.joined()
  }

  private static func intValue(_ row: Row, _ column: String) -> Int64 {
    (row[column] as? Int64) ?? Int64(row[column] as? Int ?? 0)
  }

  /// `message.date` is nanoseconds since the 2001 reference date on modern macOS; legacy databases
  /// store seconds. Convert either to an ISO-8601 string. Mirrors `IMessageExporter`.
  private static func isoString(appleTime raw: Int64, iso: ISO8601DateFormatter) -> String {
    let seconds = raw > 1_000_000_000_000 ? Double(raw) / 1_000_000_000.0 : Double(raw)
    return iso.string(from: Date(timeIntervalSinceReferenceDate: seconds))
  }

  /// Last 10 digits of a phone handle (a stable cross-format key), or nil for emails / short codes.
  private static func phoneLast10(_ handle: String) -> String? {
    if handle.contains("@") { return nil }
    let digits = handle.filter { $0.isNumber }
    guard digits.count >= 10 else { return nil }
    return String(digits.suffix(10))
  }
}
