import XCTest

@testable import Omi_Computer

/// Exercises the relationship-fact memory writer's pure core: grounded fact generation from the
/// real pipeline outputs, the content-hash dedupe ("same fact never resubmitted"), the per-run
/// volume cap, the human-name guard, and the on-disk ledger round-trip. No network, no main thread.
final class PeopleMemoryWriterTests: XCTestCase {

  /// Two named 1:1 contacts (Alice, Bob) plus one 3-person named group whose third member (Carol)
  /// is phone-only and unresolved — so she stays a bare "+1555…" handle and must be filtered out of
  /// every fact. Mirrors the shape the exporter writes.
  private func buildPipelineInputs() throws -> (
    people: [[String: Any]], edges: [[String: Any]], idName: [String: String]
  ) {
    let dir = FileManager.default.temporaryDirectory
      .appendingPathComponent("PeopleMemoryWriterTests-\(UUID().uuidString)", isDirectory: true)
    try FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
    defer { try? FileManager.default.removeItem(at: dir) }
    let url = dir.appendingPathComponent("imessage_export.json")

    let json = """
      {
        "generated_at": "2026-07-25T10:00:00Z",
        "total_messages": 150,
        "handles": [
          { "handle": "+15551234567", "phone_last10": "5551234567", "contact_name": "Alice",
            "message_count": 100, "last_date": "2026-07-01T10:00:00Z" },
          { "handle": "+15559876543", "phone_last10": "5559876543", "contact_name": "Bob",
            "message_count": 50, "last_date": "2026-06-01T10:00:00Z" }
        ],
        "groups": [
          {
            "display_name": "Tahoe Trip 2024",
            "member_count": 3,
            "members": [
              { "phone_last10": "5551234567" },
              { "phone_last10": "5559876543" },
              { "handle": "+15550001111", "phone_last10": "5550001111" }
            ]
          }
        ]
      }
      """
    try XCTUnwrap(json.data(using: .utf8)).write(to: url)

    guard let root = PeopleGraphBuilder.readExport(at: url) else {
      throw XCTSkip("readExport returned nil for the synthetic export")
    }
    let people = PeopleGraphBuilder.buildCanonicalPeople(root: root, contactsByPhone: [:])
    let graph = PeopleGraphBuilder.buildGraph(root: root, people: people)
    let communities = PeopleGraphBuilder.buildCommunities(root: root, people: people)
    let persons = PeopleGraphBuilder.createPeople(people: people, graph: graph, communities: communities)
    // Match the people_social.json edge shape the writer reads from disk.
    let edges = graph.edges.map { ["a": $0.a, "b": $0.b, "context": $0.context] as [String: Any] }
    return (persons, edges, graph.idName)
  }

  // MARK: - Fact generation

  func testGeneratesGroundedPerPersonAndInterPersonFacts() throws {
    let inputs = try buildPipelineInputs()
    let facts = PeopleMemoryWriter.generateFacts(
      people: inputs.people, edges: inputs.edges, idName: inputs.idName)

    // Alice + Bob per-person, Alice–Bob inter-person = 3. Carol (bare "+1555…") is filtered
    // everywhere, so her per-person fact and both of her edges are dropped.
    XCTAssertEqual(facts.count, 3, "two named people + one named pair, unresolved handle filtered")

    let texts = facts.map { $0.text }
    XCTAssertTrue(
      texts.contains {
        $0.contains("Alice") && $0.contains("Tahoe Trip 2024") && $0.contains("you know them via iMessage")
      },
      "per-person fact must name the person, cite the real group, and state the channel")

    let interPerson = try XCTUnwrap(
      texts.first { $0.contains("both belong to your") }, "an inter-person fact must exist")
    XCTAssertTrue(
      interPerson.contains("Alice") && interPerson.contains("Bob")
        && interPerson.contains("Tahoe Trip 2024") && interPerson.contains("they know each other"),
      "inter-person fact must name both people, cite the shared group, and assert they know each other")

    XCTAssertFalse(
      texts.contains { $0.contains("+1555") || $0.contains("5550001111") },
      "an unresolved phone handle must never appear in a fact")
  }

  func testHumanNameGuardRejectsHandlesAndBlanks() {
    XCTAssertTrue(PeopleMemoryWriter.isHumanName("Alice"))
    XCTAssertTrue(PeopleMemoryWriter.isHumanName("Mary Jane"))
    XCTAssertFalse(PeopleMemoryWriter.isHumanName("+15550001111"), "bare phone handle is not a name")
    XCTAssertFalse(PeopleMemoryWriter.isHumanName("foo@bar.com"), "email handle is not a name")
    XCTAssertFalse(PeopleMemoryWriter.isHumanName("   "), "blank is not a name")
  }

  // MARK: - Dedupe + cap

  func testSameFactNotResubmittedButChangedFactIs() throws {
    let inputs = try buildPipelineInputs()
    let facts = PeopleMemoryWriter.generateFacts(
      people: inputs.people, edges: inputs.edges, idName: inputs.idName)
    XCTAssertFalse(facts.isEmpty, "precondition: facts were generated")

    // First run against an empty ledger submits everything.
    let firstRun = PeopleMemoryWriter.newFacts(facts, ledger: [], cap: PeopleMemoryWriter.maxFactsPerRun)
    XCTAssertEqual(firstRun.count, facts.count, "an empty ledger admits every generated fact")

    // Record those hashes; an identical second run submits nothing.
    let ledger = Set(firstRun.map { $0.hash })
    let secondRun = PeopleMemoryWriter.newFacts(facts, ledger: ledger, cap: PeopleMemoryWriter.maxFactsPerRun)
    XCTAssertTrue(secondRun.isEmpty, "already-submitted facts must never be resubmitted")

    // A genuinely changed fact (new text → new hash) is admitted again.
    let changed = PeopleMemoryWriter.Fact(subject: "person:alice", text: "Alice — updated role.")
    let thirdRun = PeopleMemoryWriter.newFacts([changed], ledger: ledger, cap: PeopleMemoryWriter.maxFactsPerRun)
    XCTAssertEqual(thirdRun, [changed], "a changed fact hashes differently and is submitted")
  }

  func testVolumeCapBoundsFactsPerRun() throws {
    let inputs = try buildPipelineInputs()
    let facts = PeopleMemoryWriter.generateFacts(
      people: inputs.people, edges: inputs.edges, idName: inputs.idName)
    XCTAssertGreaterThanOrEqual(facts.count, 2, "precondition: at least two facts to cap")

    let capped = PeopleMemoryWriter.newFacts(facts, ledger: [], cap: 1)
    XCTAssertEqual(capped.count, 1, "the per-run cap bounds how many facts are submitted at once")
  }

  // MARK: - Ledger IO

  func testLedgerRoundTripMergesHashes() throws {
    let dir = FileManager.default.temporaryDirectory
      .appendingPathComponent("PeopleMemoryLedgerTests-\(UUID().uuidString)", isDirectory: true)
    try FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
    defer { try? FileManager.default.removeItem(at: dir) }

    XCTAssertTrue(PeopleMemoryWriter.loadLedger(directory: dir).isEmpty, "no ledger yet reads empty")

    PeopleMemoryWriter.appendLedger(directory: dir, hashes: ["aaa", "bbb"])
    XCTAssertEqual(PeopleMemoryWriter.loadLedger(directory: dir), ["aaa", "bbb"])

    // A second append unions rather than replaces.
    PeopleMemoryWriter.appendLedger(directory: dir, hashes: ["bbb", "ccc"])
    XCTAssertEqual(PeopleMemoryWriter.loadLedger(directory: dir), ["aaa", "bbb", "ccc"])

    let ledgerURL = dir.appendingPathComponent(PeopleMemoryWriter.ledgerFileName)
    XCTAssertTrue(
      FileManager.default.fileExists(atPath: ledgerURL.path),
      "the ledger is persisted at people_memory_ledger.json")
  }

  // MARK: - Wire contract

  /// Regression: relationship facts were submitted with `source: "people_intelligence"` only, and
  /// `source` is not a field on the backend `Memory` model (`backend/models/memories.py`) — Pydantic
  /// dropped it, so every fact ever written was untagged and unfindable by provenance. `tags` *is* a
  /// persisted field (`MemoryDB.from_memory` copies `memory.tags` verbatim), so the durable
  /// provenance rides there. Asserted on the real serialized request body, not on a helper's return
  /// value: drop `tags:` from the `createMemory` call and this fails.
  func testSubmittedRequestBodyCarriesDurablePersonTags() async throws {
    PeopleMemoryWriteCapture.reset()
    setenv("OMI_PYTHON_API_URL", "http://people-memory-contract-test:9002", 1)
    defer {
      unsetenv("OMI_PYTHON_API_URL")
      PeopleMemoryWriteCapture.reset()
    }

    let configuration = URLSessionConfiguration.ephemeral
    configuration.protocolClasses = [PeopleMemoryWriteCapture.self]
    let client = APIClient(session: URLSession(configuration: configuration))
    await client.setTestAuthHeader("Bearer test-token")

    let fact = PeopleMemoryWriter.Fact(
      subject: "person:alice", text: "Alice \u{2014} in your \u{201C}Tahoe\u{201D} group.")
    let submitted = await PeopleMemoryWriter.submit(facts: [fact], client: client)
    XCTAssertEqual(submitted, [fact.hash], "a 2xx write records the fact's hash")

    let request = try XCTUnwrap(PeopleMemoryWriteCapture.request)
    XCTAssertEqual(request.httpMethod, "POST")
    XCTAssertEqual(request.url?.path, "/v3/memories")

    let body = try XCTUnwrap(PeopleMemoryWriteCapture.body)
    let json = try XCTUnwrap(JSONSerialization.jsonObject(with: body) as? [String: Any])
    let tags = try XCTUnwrap(json["tags"] as? [String], "tags must reach the wire")
    XCTAssertTrue(
      tags.contains("person:alice"),
      "the write must carry person:<id> so the profile page can find it back: \(tags)")
    XCTAssertTrue(
      tags.contains(PeopleMemoryWriter.memorySource),
      "and the cohort tag so every relationship fact stays enumerable: \(tags)")
    XCTAssertEqual(json["content"] as? String, fact.text)
    XCTAssertEqual(json["category"] as? String, "interesting")
  }

  /// A "they know each other" fact belongs on *both* profiles, so it carries both person tags.
  func testPairFactTagsBothEndpoints() {
    let tags = PeopleMemoryWriter.tags(forSubject: "pair:alice|bob")
    XCTAssertEqual(
      Set(tags), ["people_intelligence", "person:alice", "person:bob"],
      "a pair fact must be findable from either person's profile")
  }
}

/// Captures the serialized `POST /v3/memories` request the writer actually sends.
private final class PeopleMemoryWriteCapture: URLProtocol, @unchecked Sendable {
  private static let lock = NSLock()
  private nonisolated(unsafe) static var _request: URLRequest?
  private nonisolated(unsafe) static var _body: Data?

  static var request: URLRequest? {
    lock.lock()
    defer { lock.unlock() }
    return _request
  }

  static var body: Data? {
    lock.lock()
    defer { lock.unlock() }
    return _body
  }

  static func reset() {
    lock.lock()
    _request = nil
    _body = nil
    lock.unlock()
  }

  override class func canInit(with request: URLRequest) -> Bool { true }
  override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }

  override func startLoading() {
    let captured = Self.bodyData(from: request)
    Self.lock.lock()
    Self._request = request
    Self._body = captured
    Self.lock.unlock()

    let response = HTTPURLResponse(
      url: request.url!,
      statusCode: 200,
      httpVersion: nil,
      headerFields: ["Content-Type": "application/json"]
    )!
    client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
    client?.urlProtocol(
      self, didLoad: Data("{\"id\":\"memory-1\",\"content\":\"Alice\"}".utf8))
    client?.urlProtocolDidFinishLoading(self)
  }

  override func stopLoading() {}

  private static func bodyData(from request: URLRequest) -> Data? {
    if let body = request.httpBody { return body }
    guard let stream = request.httpBodyStream else { return nil }
    stream.open()
    defer { stream.close() }
    var body = Data()
    let buffer = UnsafeMutablePointer<UInt8>.allocate(capacity: 4_096)
    defer { buffer.deallocate() }
    while stream.hasBytesAvailable {
      let readCount = stream.read(buffer, maxLength: 4_096)
      if readCount > 0 { body.append(buffer, count: readCount) } else { break }
    }
    return body
  }
}
