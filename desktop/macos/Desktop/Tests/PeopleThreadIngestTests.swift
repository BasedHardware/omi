import XCTest

@testable import Omi_Computer

/// Exercises the thread-ingester's pure core: PII redaction, transcript building (Me/contact
/// labels, monotonic timings, last-N bound, empty-drop, minimum-segments gate), the window-key
/// dedupe ("same window never resubmitted"), substantial-thread + per-run-cap selection, stable
/// idempotency ids, and the on-disk ledger round-trip. No network, no Messages DB, no main thread.
final class PeopleThreadIngestTests: XCTestCase {

  // MARK: - Redaction

  func testRedactionRemovesPhonesEmailsAndCodes() {
    let input = "text me at +1 (415) 555-1234 or alice@example.com — the code is 483920"
    let out = PeopleThreadIngest.redact(input)
    XCTAssertFalse(out.contains("415"), "phone digits must be redacted")
    XCTAssertFalse(out.contains("555-1234"), "phone must be redacted")
    XCTAssertFalse(out.contains("alice@example.com"), "email must be redacted")
    XCTAssertFalse(out.contains("483920"), "OTP-style code must be redacted")
    XCTAssertTrue(out.contains("[phone]"), "phone placeholder present")
    XCTAssertTrue(out.contains("[email]"), "email placeholder present")
    XCTAssertTrue(out.contains("[code]"), "code placeholder present")
  }

  func testRedactionLeavesOrdinaryTextIntact() {
    let input = "See you at 7 for dinner, bringing 2 friends"
    XCTAssertEqual(
      PeopleThreadIngest.redact(input), input,
      "short standalone numbers (times, small counts) are not codes and stay put")
  }

  // MARK: - Transcript build

  private func messages(count: Int, contactText: String = "hi") -> [PeopleThreadIngest.RawMessage] {
    (0..<count).map { i in
      PeopleThreadIngest.RawMessage(
        fromMe: i % 2 == 0,
        text: i % 2 == 0 ? "me msg \(i)" : "\(contactText) \(i)",
        date: String(format: "2026-07-%02dT10:00:00Z", (i % 27) + 1))
    }
  }

  func testBuildTranscriptLabelsSpeakersAndOrdersTimings() throws {
    let msgs = messages(count: 8)
    let built = try XCTUnwrap(PeopleThreadIngest.buildTranscript(contactName: "Alice", messages: msgs))

    XCTAssertEqual(built.segments.count, 8)
    XCTAssertEqual(built.startedAt, msgs.first?.date, "started_at is the first kept message's date")

    // Me segments are the user; contact segments carry the contact's name and are not the user.
    for (i, seg) in built.segments.enumerated() {
      if i % 2 == 0 {
        XCTAssertTrue(seg.is_user, "even indices are 'Me'")
        XCTAssertEqual(seg.speaker, "SPEAKER_00")
      } else {
        XCTAssertFalse(seg.is_user, "odd indices are the contact")
        XCTAssertEqual(seg.speaker, "Alice", "contact segments use the resolved name as speaker")
      }
    }

    // Timings are strictly increasing and non-overlapping (backend requires end > start >= 0).
    for (i, seg) in built.segments.enumerated() {
      XCTAssertGreaterThanOrEqual(seg.start, 0)
      XCTAssertGreaterThan(seg.end, seg.start)
      if i > 0 { XCTAssertGreaterThan(seg.start, built.segments[i - 1].start) }
    }
  }

  func testBuildTranscriptBoundsToLastNAndRedacts() throws {
    // More than the cap, and every contact line contains a phone number to prove redaction ran.
    let msgs = (0..<(PeopleThreadIngest.maxMessagesPerThread + 15)).map { i in
      PeopleThreadIngest.RawMessage(
        fromMe: i % 2 == 0, text: i % 2 == 0 ? "ok \(i)" : "call +14155559999 now", date: "2026-07-01T10:00:00Z")
    }
    let built = try XCTUnwrap(PeopleThreadIngest.buildTranscript(contactName: "Bob", messages: msgs))
    XCTAssertEqual(built.segments.count, PeopleThreadIngest.maxMessagesPerThread, "bounded to the last N")
    XCTAssertFalse(
      built.segments.contains { $0.text.contains("4155559999") }, "phone numbers must be redacted out")
  }

  func testBuildTranscriptDropsEmptyAndReturnsNilBelowMinimum() {
    // Only 3 non-empty messages (below minSegmentsToSubmit) mixed with blanks → nil.
    let msgs: [PeopleThreadIngest.RawMessage] = [
      .init(fromMe: true, text: "hey", date: "2026-07-01T10:00:00Z"),
      .init(fromMe: false, text: "   ", date: "2026-07-01T10:01:00Z"),
      .init(fromMe: true, text: "you around?", date: "2026-07-01T10:02:00Z"),
      .init(fromMe: false, text: "yes", date: "2026-07-01T10:03:00Z"),
    ]
    XCTAssertNil(
      PeopleThreadIngest.buildTranscript(contactName: "Al", messages: msgs),
      "below the minimum-segments bar returns nil (blank line dropped, only 3 real → < 6)")
  }

  // MARK: - Window key + idempotency id

  func testWindowKeyStableWithinBucketAndDayButChangesAcross() {
    let base = PeopleThreadIngest.windowKey(personKey: "5551234567", messageCount: 40, lastDate: "2026-07-10T09:00:00Z")

    // Same bucket (40 and 45 both in bucket 40/20=2) and same day → identical key.
    XCTAssertEqual(
      base,
      PeopleThreadIngest.windowKey(personKey: "5551234567", messageCount: 45, lastDate: "2026-07-10T23:00:00Z"),
      "a few more messages on the same day do not re-trigger ingestion")

    // Crossing a message bucket → different key.
    XCTAssertNotEqual(
      base,
      PeopleThreadIngest.windowKey(personKey: "5551234567", messageCount: 61, lastDate: "2026-07-10T09:00:00Z"),
      "crossing a message-count bucket re-triggers ingestion")

    // A new day of activity → different key.
    XCTAssertNotEqual(
      base,
      PeopleThreadIngest.windowKey(personKey: "5551234567", messageCount: 40, lastDate: "2026-07-11T09:00:00Z"),
      "activity on a new day re-triggers ingestion")

    // Different person → different key.
    XCTAssertNotEqual(
      base,
      PeopleThreadIngest.windowKey(personKey: "5559999999", messageCount: 40, lastDate: "2026-07-10T09:00:00Z"))
  }

  func testClientConversationIdStableAndBounded() {
    let key = PeopleThreadIngest.windowKey(personKey: "p", messageCount: 30, lastDate: "2026-07-10T09:00:00Z")
    let a = PeopleThreadIngest.clientConversationId(personKey: "p", windowKey: key)
    let b = PeopleThreadIngest.clientConversationId(personKey: "p", windowKey: key)
    XCTAssertEqual(a, b, "same person+window yields the same idempotency id (server-side dedupe)")
    XCTAssertTrue(a.hasPrefix("people_thread_"))
    XCTAssertLessThanOrEqual(a.count, 200, "must fit the backend client_session_id limit")
  }

  // MARK: - Candidate selection (substantial / dedupe / cap)

  private func candidate(_ key: String, name: String = "Alice", count: Int, last: String = "2026-07-10T09:00:00Z")
    -> PeopleThreadIngest.ThreadCandidate
  {
    .init(personKey: key, contactName: name, chatId: 1, messageCount: count, lastDate: last)
  }

  func testNewCandidatesKeepsSubstantialDropsLedgeredNamelessAndCaps() {
    let substantialA = candidate("a", name: "Alice", count: 80)
    let substantialB = candidate("b", name: "Bob", count: 60)
    let tooSmall = candidate("c", name: "Carl", count: PeopleThreadIngest.minThreadMessages - 1)
    let nameless = candidate("d", name: "+15550001111", count: 100)  // unresolved handle as name

    let selected = PeopleThreadIngest.newCandidates(
      [tooSmall, substantialB, nameless, substantialA], ledger: [], cap: 10)

    let keys = selected.map { $0.0.personKey }
    XCTAssertEqual(keys, ["a", "b"], "only substantial, human-named threads, most-active first")
    XCTAssertFalse(keys.contains("c"), "below the substantial bar is dropped")
    XCTAssertFalse(keys.contains("d"), "a bare-phone 'name' is not a human name and is dropped")

    // Ledgering A's current window excludes it next time; B remains.
    let ledger: Set<String> = [
      PeopleThreadIngest.windowKey(
        personKey: "a", messageCount: 80, lastDate: "2026-07-10T09:00:00Z")
    ]
    let second = PeopleThreadIngest.newCandidates([substantialA, substantialB], ledger: ledger, cap: 10)
    XCTAssertEqual(second.map { $0.0.personKey }, ["b"], "an already-ingested window is not resubmitted")

    // Per-run cap bounds the batch.
    let capped = PeopleThreadIngest.newCandidates([substantialA, substantialB], ledger: [], cap: 1)
    XCTAssertEqual(capped.count, 1, "the per-run cap bounds how many threads are submitted at once")
  }

  /// Regression guard for the ingest "burst" bug. `/v1/conversations/from-segments` is rate-limited
  /// (a budget shared with voice capture) and indexes each conversation via best-effort background
  /// work. A wide per-run batch trips the limiter — most POSTs 429 and are silently dropped, never
  /// created — and floods the indexing so the conversations that *are* created never vectorize and
  /// stay invisible to search and chat. Verified live: an isolated upload indexes reliably; a 40-wide
  /// burst indexed none. The per-run batch must therefore stay small, and `newCandidates` must
  /// actually enforce that cap over a large qualifying set.
  func testPerRunBatchIsBoundedSoTheRateLimitedEndpointIsNotFlooded() {
    XCTAssertLessThanOrEqual(
      PeopleThreadIngest.maxPeoplePerRun, 10,
      "a run must submit only a small batch; a wide burst is 429-dropped by the rate limiter and floods indexing")

    let many = (0..<100).map { candidate("p\($0)", name: "Person \($0)", count: 100 - ($0 % 5)) }
    let selected = PeopleThreadIngest.newCandidates(
      many, ledger: [], cap: PeopleThreadIngest.maxPeoplePerRun)
    XCTAssertEqual(
      selected.count, PeopleThreadIngest.maxPeoplePerRun,
      "newCandidates must cap the batch at maxPeoplePerRun even when far more threads qualify")
  }

  // MARK: - Ledger IO

  func testLedgerRoundTripMergesKeys() throws {
    let dir = FileManager.default.temporaryDirectory
      .appendingPathComponent("PeopleThreadIngestLedgerTests-\(UUID().uuidString)", isDirectory: true)
    try FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
    defer { try? FileManager.default.removeItem(at: dir) }

    XCTAssertTrue(PeopleThreadIngest.loadLedger(directory: dir).isEmpty, "no ledger yet reads empty")

    PeopleThreadIngest.appendLedger(directory: dir, keys: ["w1", "w2"])
    XCTAssertEqual(PeopleThreadIngest.loadLedger(directory: dir), ["w1", "w2"])

    PeopleThreadIngest.appendLedger(directory: dir, keys: ["w2", "w3"])
    XCTAssertEqual(PeopleThreadIngest.loadLedger(directory: dir), ["w1", "w2", "w3"], "append unions, not replaces")

    let ledgerURL = dir.appendingPathComponent(PeopleThreadIngest.ledgerFileName)
    XCTAssertTrue(
      FileManager.default.fileExists(atPath: ledgerURL.path),
      "the ledger is persisted at people_thread_ingest_ledger.json")
  }

  // MARK: - Name resolution (the deep-ingest gate)

  /// Regression: the ingest used to resolve names ONLY from macOS Contacts, which iMessage-only
  /// bundles can never obtain — so `namesByPhone` returned nothing and every thread was silently
  /// skipped (zero conversations reached the backend). It must now resolve names from the on-device
  /// export JSONs (WhatsApp's `contact_name` / any iMessage `contact_name`) with no Contacts grant.
  func testNamesByPhoneResolvesFromExportsWithoutContacts() throws {
    let dir = FileManager.default.temporaryDirectory
      .appendingPathComponent("PeopleThreadIngestNamesTests-\(UUID().uuidString)", isDirectory: true)
    try FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
    defer { try? FileManager.default.removeItem(at: dir) }

    let whatsapp = """
      {"generated_at":"2026-07-28","total_messages":10,"handles":[
        {"handle":"+917746099000","phone_last10":"7746099000","contact_name":"Aryaveer UMN","message_count":328,"is_group":false},
        {"handle":"+15551230000","phone_last10":"5551230000","contact_name":"","message_count":5,"is_group":false}
      ],"groups":[]}
      """
    let imessage = """
      {"generated_at":"2026-07-28","total_messages":10,"handles":[
        {"handle":"+16516210269","phone_last10":"6516210269","contact_name":"Maya Iyer","message_count":900,"is_group":false},
        {"handle":"+19998887777","phone_last10":"9998887777","message_count":40,"is_group":false}
      ],"groups":[]}
      """
    try whatsapp.write(to: dir.appendingPathComponent("whatsapp_export.json"), atomically: true, encoding: .utf8)
    try imessage.write(to: dir.appendingPathComponent("imessage_export.json"), atomically: true, encoding: .utf8)

    // Inject an empty Contacts map so the test is hermetic (no real address-book dependency) and
    // proves the export-only resolution path that a no-Contacts-grant bundle actually uses.
    let map = PeopleThreadIngest.namesByPhone(directory: dir, contacts: [:])
    XCTAssertEqual(
      map["7746099000"], "Aryaveer UMN", "WhatsApp contact_name resolves the counterpart name with no Contacts grant")
    XCTAssertEqual(map["6516210269"], "Maya Iyer", "iMessage contact_name (when present) also resolves")
    XCTAssertNil(map["5551230000"], "an empty contact_name is not a usable label")
    XCTAssertNil(map["9998887777"], "a phone with no contact_name is left unresolved (thread stays skipped)")

    // When macOS Contacts IS authorized, its name is authoritative and wins over the export.
    let withContacts = PeopleThreadIngest.namesByPhone(
      directory: dir, contacts: ["7746099000": "Aryaveer Singh"])
    XCTAssertEqual(withContacts["7746099000"], "Aryaveer Singh", "Contacts name wins over the WhatsApp export name")
  }

  /// A WhatsApp candidate must key its window on a `wa:`-prefixed person id so the same person's
  /// WhatsApp and iMessage threads ingest as two distinct conversations instead of colliding.
  func testWhatsAppAndIMessageWindowsForOnePersonDoNotCollide() {
    let phone = "7746099000"
    let imessageKey = PeopleThreadIngest.windowKey(personKey: phone, messageCount: 40, lastDate: "2026-07-28T00:00:00Z")
    let whatsappKey = PeopleThreadIngest.windowKey(
      personKey: "wa:" + phone, messageCount: 40, lastDate: "2026-07-28T00:00:00Z")
    XCTAssertNotEqual(imessageKey, whatsappKey, "same person, two channels → two independent ingest windows")
  }
}
