import CryptoKit
import Foundation

/// Turns the deterministic on-device People-Intelligence outputs into concise, grounded
/// relationship-fact memories, so the assistant's chat can answer "who is X / how do I know them /
/// who knows whom" questions — for every user, with no server-side graph.
///
/// Everything is derived from files this machine already wrote (nothing is inferred by an LLM):
///   - `people_intelligence.json` — per-person cards (name, channels, folded groups/circle)
///   - `people_social.json`       — the people-to-people edges, each carrying the real shared
///                                  group name(s) as `context`
///
/// Facts are submitted through the same authenticated memory client the rest of the app already
/// uses (`APIClient.shared.createMemory` → `POST /v3/memories`) under a neutral `interesting`
/// category — never `manual`. A local content-hash ledger (`people_memory_ledger.json`) means only
/// new or changed facts are ever submitted, and each run is volume-capped so it can never flood the
/// store.
///
/// Gated on the same `peopleIMessageExport` consent flag as the graph itself, plus its own sync
/// throttle. All work runs off the main thread; every IO / network failure is a silent no-op — this
/// is best-effort background enrichment and must never crash or block the People tab.
enum PeopleMemoryWriter {
  /// Hard cap on facts submitted per run, so a first run over a large graph trickles out rather than
  /// flooding the memory store. Remaining new facts are picked up on subsequent throttled runs.
  static let maxFactsPerRun = 40

  /// Provenance tag on every memory this writer creates (also aids debugging / auditing).
  static let memorySource = "people_intelligence"

  /// A single grounded relationship fact plus a stable subject key (for readability / debugging).
  struct Fact: Equatable {
    /// e.g. `person:alice` or `pair:alice|bob` — not sent to the server, only for reasoning/tests.
    let subject: String
    /// The memory content submitted verbatim.
    let text: String
    /// Content hash used for the dedupe ledger. Changed fact text yields a new hash, so a genuinely
    /// updated fact is re-submitted while an unchanged one never is.
    var hash: String { PeopleMemoryWriter.contentHash(text) }
  }

  // MARK: - Entry point (gated, throttled, off-main, silent)

  /// Called after the graph builds (from `PeopleGraphBuilder.syncIfNeeded`). Self-gates on the
  /// iMessage consent flag and its own throttle, prepares a capped/deduped fact batch off the main
  /// thread, submits it via the app's authenticated memory client, then records the submitted
  /// hashes. Any failure — no directory, unreadable files, not signed in, offline — is a no-op.
  static func writeIfNeeded(uid: String?, force: Bool = false) async {
    guard UserDefaults.standard.bool(forKey: .peopleIMessageExport) else { return }
    guard PeopleGraphBuilder.claimRun(.peopleMemoryLastWrite, force: force) else { return }

    // Resolve dir + read JSON + build the capped, deduped submission list off the main thread.
    let plan: SubmissionPlan? = await Task.detached(priority: .utility) {
      buildPlan(uid: uid)
    }.value
    guard let plan, !plan.facts.isEmpty else { return }

    // Submit sequentially via the app's authenticated memory client. Only successfully submitted
    // hashes are recorded, so a transient failure is simply retried on the next run.
    var submitted: Set<String> = []
    for fact in plan.facts {
      do {
        _ = try await APIClient.shared.createMemory(
          content: fact.text,
          category: .interesting,
          source: memorySource
        )
        submitted.insert(fact.hash)
      } catch {
        // Silent: not-signed-in / offline / server error. Unrecorded hashes retry next run.
      }
    }
    guard !submitted.isEmpty else { return }
    await Task.detached(priority: .utility) {
      appendLedger(directory: plan.directory, hashes: submitted)
    }.value
    log("PeopleMemoryWriter: submitted \(submitted.count) relationship-fact memories")
  }

  struct SubmissionPlan {
    let directory: URL
    let facts: [Fact]
  }

  /// Off-main preparation: resolve the user directory, read the deterministic outputs, generate
  /// facts, drop any already in the ledger, and cap the run. Guarded — a missing / corrupt file or
  /// an empty graph returns nil.
  static func buildPlan(uid: String?) -> SubmissionPlan? {
    guard let dir = PeopleUserDirectory.resolve(uid: uid) else { return nil }
    let people = readArray(dir.appendingPathComponent("people_intelligence.json"), key: "people")
    let social = readObject(dir.appendingPathComponent("people_social.json"))
    let edges = (social?["edges"] as? [[String: Any]]) ?? []
    let idName = (social?["id_name"] as? [String: String]) ?? [:]
    guard !people.isEmpty || !edges.isEmpty else { return nil }

    let facts = generateFacts(people: people, edges: edges, idName: idName)
    let ledger = loadLedger(directory: dir)
    let fresh = newFacts(facts, ledger: ledger, cap: maxFactsPerRun)
    guard !fresh.isEmpty else { return nil }
    return SubmissionPlan(directory: dir, facts: fresh)
  }

  // MARK: - Fact generation (pure, unit-testable)

  /// Generate grounded relationship facts from the deterministic per-person cards and the social
  /// edges. Per-person facts describe who someone is (community / circle) and how you reach them
  /// (channels); inter-person facts assert that two people know each other, citing the real shared
  /// group as evidence. Nothing is invented — every clause is backed by a field in the inputs.
  ///
  /// Identity-uncertain people (flagged `needsConfirmation` by the review pipeline) are never
  /// asserted about, and never used as an endpoint of a "they know each other" claim.
  static func generateFacts(
    people: [[String: Any]], edges: [[String: Any]], idName: [String: String]
  ) -> [Fact] {
    var facts: [Fact] = []

    var uncertain = Set<String>()
    for person in people where (person["needsConfirmation"] as? Bool) == true {
      if let id = nonEmpty(person["id"] as? String) { uncertain.insert(id) }
    }

    // ---- per-person (people_intelligence.json is pre-sorted by closeness desc) ----
    for person in people {
      guard let name = nonEmpty(person["name"] as? String), isHumanName(name) else { continue }
      if let id = person["id"] as? String, uncertain.contains(id) { continue }
      guard
        let role = roleClause(
          groups: person["groups"] as? [[String: Any]] ?? [],
          circle: person["circle"] as? [String: Any])
      else { continue }  // no community / relationship context → nothing grounded to say
      let subject = "person:\(nonEmpty(person["id"] as? String) ?? name)"
      let channels = channelClause(person["channels"] as? [[String: Any]] ?? [])
      let text =
        channels.isEmpty
        ? "\(name) — \(role)."
        : "\(name) — \(role); you know them via \(channels)."
      facts.append(Fact(subject: subject, text: text))
    }

    // ---- inter-person (people_social.json edges are pre-sorted by weight desc) ----
    for edge in edges {
      guard let a = nonEmpty(edge["a"] as? String), let b = nonEmpty(edge["b"] as? String), a != b
      else { continue }
      guard !uncertain.contains(a), !uncertain.contains(b) else { continue }
      let context = (edge["context"] as? [String]) ?? []
      guard let group = context.compactMap({ nonEmpty($0) }).first else { continue }  // need a real name
      guard let na = nonEmpty(idName[a]), isHumanName(na),
        let nb = nonEmpty(idName[b]), isHumanName(nb), na != nb
      else { continue }
      let subject = a < b ? "pair:\(a)|\(b)" : "pair:\(b)|\(a)"
      let text =
        "\(na) and \(nb) both belong to your \u{201C}\(group)\u{201D} group — they know each other."
      facts.append(Fact(subject: subject, text: text))
    }

    return facts
  }

  /// Filter to facts not already submitted (by content hash), de-dupe within the run, and cap.
  /// Pure and deterministic — the core of the "same fact never resubmitted" guarantee.
  static func newFacts(_ facts: [Fact], ledger: Set<String>, cap: Int) -> [Fact] {
    var seen = ledger
    var out: [Fact] = []
    for fact in facts {
      let hash = fact.hash
      guard !seen.contains(hash) else { continue }
      seen.insert(hash)
      out.append(fact)
      if out.count >= cap { break }
    }
    return out
  }

  // MARK: - Clause builders

  /// e.g. `in your “AV Founders” group (work / venture) and 2 others`, a circle fallback, or nil
  /// when the person has no community / relationship context to describe.
  private static func roleClause(groups: [[String: Any]], circle: [String: Any]?) -> String? {
    if let first = groups.first, let gname = nonEmpty(first["name"] as? String) {
      var clause = "in your \u{201C}\(gname)\u{201D} group"
      if let category = nonEmpty(first["category"] as? String) { clause += " (\(category))" }
      let others = groups.count - 1
      if others > 0 { clause += " and \(others) other\(others == 1 ? "" : "s")" }
      return clause
    }
    if let circle, let label = nonEmpty(circle["label"] as? String) {
      return "part of your \(label) circle"
    }
    return nil
  }

  /// Distinct channel labels joined for the "you know them via …" clause (e.g. "iMessage").
  private static func channelClause(_ channels: [[String: Any]]) -> String {
    var labels: [String] = []
    for channel in channels {
      guard let label = nonEmpty(channel["label"] as? String) ?? nonEmpty(channel["key"] as? String)
      else { continue }
      if !labels.contains(label) { labels.append(label) }
    }
    return labels.joined(separator: " / ")
  }

  // MARK: - Ledger IO (guarded)

  static let ledgerFileName = "people_memory_ledger.json"

  private struct Ledger: Codable {
    var version: Int
    var hashes: [String]
  }

  /// Set of already-submitted fact hashes. A missing / corrupt ledger reads as empty (so nothing is
  /// lost — worst case a memory is created twice, which the backend de-dupes on content).
  static func loadLedger(directory: URL) -> Set<String> {
    let url = directory.appendingPathComponent(ledgerFileName)
    guard let data = try? Data(contentsOf: url),
      let ledger = try? JSONDecoder().decode(Ledger.self, from: data)
    else { return [] }
    return Set(ledger.hashes)
  }

  /// Merge newly-submitted hashes into the on-disk ledger. Best-effort atomic write; a failure only
  /// means those facts are re-evaluated next run.
  static func appendLedger(directory: URL, hashes: Set<String>) {
    let merged = loadLedger(directory: directory).union(hashes)
    let url = directory.appendingPathComponent(ledgerFileName)
    let ledger = Ledger(version: 1, hashes: merged.sorted())
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

  /// Lowercase hex SHA-256 of the fact text — the ledger's dedupe key.
  static func contentHash(_ text: String) -> String {
    SHA256.hash(data: Data(text.utf8)).map { String(format: "%02x", $0) }.joined()
  }

  /// True when a name looks like a person — not a bare phone number, email handle, or empty string —
  /// so a fact never asserts "you know 4155551234".
  static func isHumanName(_ name: String) -> Bool {
    let trimmed = name.trimmingCharacters(in: .whitespacesAndNewlines)
    guard !trimmed.isEmpty else { return false }
    if trimmed.contains("@") { return false }
    if trimmed.hasPrefix("+") { return false }
    return trimmed.contains { $0.isLetter }
  }

  private static func nonEmpty(_ value: String?) -> String? {
    guard let trimmed = value?.trimmingCharacters(in: .whitespacesAndNewlines), !trimmed.isEmpty
    else { return nil }
    return trimmed
  }

  private static func readObject(_ url: URL) -> [String: Any]? {
    guard let data = try? Data(contentsOf: url),
      let obj = try? JSONSerialization.jsonObject(with: data),
      let dict = obj as? [String: Any]
    else { return nil }
    return dict
  }

  private static func readArray(_ url: URL, key: String) -> [[String: Any]] {
    guard let dict = readObject(url), let arr = dict[key] as? [[String: Any]] else { return [] }
    return arr
  }
}
