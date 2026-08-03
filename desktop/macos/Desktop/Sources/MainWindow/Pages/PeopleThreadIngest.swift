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
  ///
  /// Kept small on purpose: `/v1/conversations/from-segments` is rate-limited (a budget shared with
  /// voice capture) and indexes each conversation via best-effort background work. A large burst both
  /// trips the rate limiter — those POSTs 429 and are silently dropped, never created — and floods the
  /// backend's post-processing so the conversations that *are* created never get vectorized, leaving
  /// them invisible to search and chat. `maxPeoplePerRun` × runs-per-hour must stay well under the
  /// endpoint budget; combined with `minIngestInterval` this holds the sustained rate there.
  static let maxPeoplePerRun = 6

  /// Minimum spacing between the ingest's *own* runs. The graph sync runs on a short (`minSyncInterval`,
  /// 5 min) cadence, but ingesting `maxPeoplePerRun` threads that often would exceed the from-segments
  /// rate budget, so the ingest self-throttles far more conservatively — its sustained submission rate
  /// stays well under the limit while a large backlog still trickles out across runs.
  static let minIngestInterval: TimeInterval = 30 * 60

  /// Gap between successive uploads within a single run. from-segments indexes each conversation with
  /// best-effort background work; submitting a batch back-to-back floods that work and the vectors are
  /// dropped (the conversation is created but never becomes searchable). Spacing the uploads keeps each
  /// one isolated enough to be accepted by the rate limiter and fully indexed — verified live: isolated
  /// uploads index reliably, a 40-wide burst indexed none.
  static let interSubmitDelayNanoseconds: UInt64 = 4_000_000_000

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

  /// Which on-device messaging store a thread comes from. The transcript build, redaction, dedupe and
  /// submission are provider-agnostic; only the message read differs per provider.
  enum Provider: String, Equatable {
    case imessage
    case whatsapp
  }

  /// A candidate 1:1 thread with a named contact, before message text is read.
  struct ThreadCandidate: Equatable {
    /// Stable per-person key. iMessage uses `phone_last10` (or the lowercased handle); WhatsApp
    /// prefixes with `wa:` so the same person's two channels ingest as two conversations rather than
    /// colliding on one dedupe window.
    let personKey: String
    /// Resolved human display name — used as the counterpart's speaker label.
    let contactName: String
    /// Provider-specific chat id: iMessage `chat_message_join` chat id, or WhatsApp `ZWACHATSESSION.Z_PK`.
    let chatId: Int64
    /// Count of readable (text) messages in the thread.
    let messageCount: Int
    /// ISO-8601 date of the newest readable message.
    let lastDate: String
    /// Source store; drives which reader `readThread` dispatches to.
    var provider: Provider = .imessage
  }

  /// A fully-prepared submission: the transcript segments plus the dedupe/idempotency keys.
  struct Submission {
    let windowKey: String
    /// The thread's stable per-person key, recorded in the ledger on success so the People engine
    /// can tell which people's history has really been ingested (`history_grounded`). The window
    /// key alone is a hash and cannot answer that.
    let personKey: String
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
    guard PeopleGraphBuilder.claimRun(.peopleThreadIngestLastRun, force: force, minInterval: minIngestInterval)
    else { return }

    let plan: SubmissionPlan? = await Task.detached(priority: .utility) {
      buildPlan(uid: uid)
    }.value
    guard let plan, !plan.submissions.isEmpty else { return }

    // Submit sequentially and *paced*. Only successfully-submitted window keys are recorded, so any
    // un-submitted thread is retried on a later throttled run. Pacing matters: a back-to-back burst
    // both trips the from-segments rate limiter and floods the backend's best-effort indexing, which
    // silently drops the conversations' vectors (created but unsearchable).
    var submitted: Set<String> = []
    var submittedPeople: Set<String> = []
    for (index, submission) in plan.submissions.enumerated() {
      if index > 0 {
        try? await Task.sleep(nanoseconds: interSubmitDelayNanoseconds)
      }
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
        submittedPeople.insert(submission.personKey)
      } catch {
        // Stop the run on the first failure — typically a 429 once the shared from-segments budget is
        // spent, or offline/auth. Un-submitted windows are NOT ledgered, so they retry on a later
        // throttled run once budget has freed, instead of hammering the rate limiter every run (which
        // previously produced a silent 429 storm and left threads permanently un-ingested).
        log("PeopleThreadIngest: stopped after \(submitted.count) submitted — \(error)")
        break
      }
    }
    guard !submitted.isEmpty else { return }
    let groundedPeople = submittedPeople
    await Task.detached(priority: .utility) {
      appendLedger(directory: plan.directory, keys: submitted, personKeys: groundedPeople)
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

    // Names come from the same data the graph used to name 1,800+ people: macOS Contacts when the
    // user has authorized it, plus WhatsApp's own `ZPARTNERNAME` and any iMessage contact names in
    // the on-device exports. This is what lets the deep ingest run WITHOUT a Contacts grant — iMessage
    // stores only phone numbers, so a Contacts-only lookup (the previous behavior) named nobody and
    // silently ingested nothing.
    let names = namesByPhone(directory: dir)
    let candidates = readThreadCandidates(namesByPhone: names) + readWhatsAppCandidates()
    guard !candidates.isEmpty else { return nil }

    let ledger = loadLedger(directory: dir)
    let selected = newCandidates(candidates, ledger: ledger, cap: maxPeoplePerRun)
    guard !selected.isEmpty else { return nil }

    var submissions: [Submission] = []
    for (candidate, windowKey) in selected {
      let messages = readThread(candidate, limit: maxMessagesPerThread)
      guard let built = buildTranscript(contactName: candidate.contactName, messages: messages) else {
        continue
      }
      submissions.append(
        Submission(
          windowKey: windowKey,
          personKey: candidate.personKey,
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

  // MARK: - Name resolution + provider candidates

  /// A `phone_last10 → display name` map reused from the exact sources the graph already resolved
  /// names from, so the deep ingest can label an iMessage thread (phone-only) without a Contacts
  /// grant. Order of preference: macOS Contacts (authoritative, when authorized), then WhatsApp's
  /// `ZPARTNERNAME` and any iMessage `contact_name`, read from the on-device export JSONs. Pure JSON +
  /// Contacts read; a missing/corrupt export just contributes nothing.
  static func namesByPhone(directory: URL, contacts: [String: String]? = nil) -> [String: String] {
    // `contacts` is injectable so the resolution is unit-testable without touching the real
    // Contacts store; production passes nil and reads macOS Contacts (empty unless authorized).
    var map = contacts ?? PeopleGraphBuilder.loadContactsByPhone()
    for file in ["whatsapp_export.json", "imessage_export.json"] {
      let url = directory.appendingPathComponent(file)
      guard let data = try? Data(contentsOf: url),
        let obj = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
        let handles = obj["handles"] as? [[String: Any]]
      else { continue }
      for handle in handles {
        guard let phone = handle["phone_last10"] as? String, !phone.isEmpty,
          let name = (handle["contact_name"] as? String)?.trimmingCharacters(in: .whitespacesAndNewlines),
          !name.isEmpty, PeopleMemoryWriter.isHumanName(name)
        else { continue }
        if map[phone] == nil { map[phone] = name }  // Contacts wins; else first export name.
      }
    }
    return map
  }

  /// Substantial 1:1 WhatsApp chats as ingest candidates, named by WhatsApp's own `ZPARTNERNAME`
  /// (`WhatsAppReader` reads the message text on demand). The `wa:` person-key prefix keeps a
  /// person's WhatsApp and iMessage threads as two distinct ingest windows. Empty when WhatsApp isn't
  /// installed / no Full Disk Access.
  static func readWhatsAppCandidates() -> [ThreadCandidate] {
    WhatsAppReader.readOneToOneThreads().compactMap { thread in
      guard PeopleMemoryWriter.isHumanName(thread.contactName) else { return nil }
      let personKey = "wa:" + (thread.phoneLast10 ?? String(thread.sessionPK))
      return ThreadCandidate(
        personKey: personKey, contactName: thread.contactName, chatId: thread.sessionPK,
        messageCount: thread.messageCount, lastDate: thread.lastDate, provider: .whatsapp)
    }
  }

  // MARK: - Messages DB reads (IO, provider-specific)

  /// Read the recent window for a candidate, dispatching to its provider's on-device reader. Both
  /// return chronological `RawMessage`s the provider-agnostic transcript build then redacts.
  static func readThread(_ candidate: ThreadCandidate, limit: Int) -> [RawMessage] {
    switch candidate.provider {
    case .imessage:
      return readIMessageThread(chatId: candidate.chatId, limit: limit)
    case .whatsapp:
      return WhatsAppReader.readThreadMessages(sessionPK: candidate.chatId, limit: limit)
        .map { RawMessage(fromMe: $0.fromMe, text: $0.text, date: $0.date) }
    }
  }

  /// Enumerate 1:1 iMessage chats with a resolvable name and their readable-message counts. Reads a
  /// throwaway read-only copy of `chat.db` (via `IMessageExporter.openReadOnlyCopy`) so it never
  /// touches the live database. A counterpart with no resolvable name (not in `namesByPhone`) is
  /// skipped so we never build a thread we can't label.
  static func readThreadCandidates(namesByPhone: [String: String]) -> [ThreadCandidate] {
    guard let dbQueue = openMessagesDB() else { return [] }
    let contactsByPhone = namesByPhone
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

  /// Read the most-recent `limit` readable messages of an iMessage chat, chronological.
  static func readIMessageThread(chatId: Int64, limit: Int) -> [RawMessage] {
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
    /// Per-person keys whose thread has been ingested at least once, in any window. Additive:
    /// a ledger written before this field existed decodes as nil, which reads as "nothing
    /// grounded" — the conservative direction, and it refills on the next successful run.
    var personKeys: [String]?
  }

  /// Set of already-ingested window keys. A missing / corrupt ledger reads as empty (worst case a
  /// window is re-ingested, which the backend de-dupes via `client_conversation_id`).
  static func loadLedger(directory: URL) -> Set<String> {
    Set(readLedger(directory: directory)?.keys ?? [])
  }

  /// People whose 1:1 thread has actually been submitted at least once. This is what makes
  /// `history_grounded` on a person card an honest claim rather than an assumption: the window
  /// keys are content hashes and cannot be traced back to a person.
  static func ingestedPersonKeys(directory: URL) -> Set<String> {
    Set(readLedger(directory: directory)?.personKeys ?? [])
  }

  private static func readLedger(directory: URL) -> Ledger? {
    let url = directory.appendingPathComponent(ledgerFileName)
    guard let data = try? Data(contentsOf: url) else { return nil }
    return try? JSONDecoder().decode(Ledger.self, from: data)
  }

  /// Merge newly-submitted window keys (and the people they belong to) into the on-disk ledger.
  /// Best-effort atomic write; a failure only means those windows are re-evaluated next run.
  static func appendLedger(directory: URL, keys: Set<String>, personKeys: Set<String> = []) {
    let merged = loadLedger(directory: directory).union(keys)
    let mergedPeople = ingestedPersonKeys(directory: directory).union(personKeys)
    let url = directory.appendingPathComponent(ledgerFileName)
    let ledger = Ledger(
      version: 1, keys: merged.sorted(), personKeys: mergedPeople.isEmpty ? nil : mergedPeople.sorted())
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
