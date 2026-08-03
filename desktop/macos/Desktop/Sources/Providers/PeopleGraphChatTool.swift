import Foundation

// MARK: - People-graph chat tools
//
// `get_person` / `search_people` answer person questions from the on-device
// people graph. Both run entirely locally: the desktop agent loop executes tools
// by calling back into Swift, so no backend is involved and nothing is uploaded.
//
// Output budget: results are relayed through
// `agent/src/runtime/relay-tool-result.ts`, which JSON-wraps the text and drops
// anything over 8 KiB. Every list here is capped and every long field clipped, and
// the assembled text is then hard-bounded by `PeopleGraphOutputBudget` so a person
// with an unusually dense profile degrades to fewer sections instead of vanishing.

/// Accumulates lines under a hard byte budget. Sections are added in priority
/// order; once the budget is reached later sections are dropped and the result
/// says so rather than silently losing detail.
struct PeopleGraphOutputBudget {
  /// Leaves ~2 KiB of the relay's 8 KiB for the JSON envelope and escaping.
  static let defaultBytes = 6 * 1024

  private static let overflowNote = "(more detail omitted to stay inside the tool output budget)"

  private let limit: Int
  private var lines: [String] = []
  private var usedBytes = 0
  private var dropped = false

  init(bytes: Int = PeopleGraphOutputBudget.defaultBytes) {
    // Reserve room for the overflow note so admitting it can never overflow.
    limit = max(0, bytes - (Self.overflowNote.utf8.count + 1))
  }

  /// Appends a line if it fits; otherwise marks the output as truncated.
  mutating func add(_ line: String) {
    guard !line.isEmpty else { return }
    let cost = line.utf8.count + 1
    guard usedBytes + cost <= limit else {
      dropped = true
      return
    }
    lines.append(line)
    usedBytes += cost
  }

  mutating func add(section title: String, items: [String]) {
    guard !items.isEmpty else { return }
    add(title)
    for item in items { add("- \(item)") }
  }

  func rendered() -> String {
    var out = lines
    if dropped { out.append(Self.overflowNote) }
    return out.joined(separator: "\n")
  }

  var didDrop: Bool { dropped }
}

/// Clipping + date helpers shared by both tools. Pure so tests can pin `now`.
enum PeopleGraphChatFormat {
  /// Character-based clip with an ellipsis; the byte budget is enforced separately.
  nonisolated static func clip(_ raw: String, _ maxCharacters: Int) -> String {
    let trimmed = raw.trimmingCharacters(in: .whitespacesAndNewlines)
      .replacingOccurrences(of: "\n", with: " ")
    guard trimmed.count > maxCharacters, maxCharacters > 1 else { return trimmed }
    return String(trimmed.prefix(maxCharacters - 1)) + "…"
  }

  /// Compact, deterministic recency ("3d ago", "5mo ago"). Deliberately not
  /// `RelativeDateTimeFormatter`: tests need a fixed `now` and stable wording.
  nonisolated static func age(of raw: String?, now: Date) -> String? {
    guard let date = PeopleDateFormat.date(from: raw) else { return nil }
    let seconds = now.timeIntervalSince(date)
    if seconds < 0 { return "just now" }
    let days = Int(seconds / 86_400)
    if days < 1 { return "today" }
    if days == 1 { return "1d ago" }
    if days < 60 { return "\(days)d ago" }
    let months = days / 30
    if months < 24 { return "\(months)mo ago" }
    return "\(days / 365)y ago"
  }

  nonisolated static func day(_ raw: String?) -> String? {
    guard let raw, raw.count >= 10 else { return nil }
    return String(raw.prefix(10))
  }
}

enum PeopleGraphChatTool {
  // Per-section caps. Chosen against the real reference graph (181 people, max 6
  // connections / 8 groups / 7 facts per person) so the worst realistic person
  // renders well under `PeopleGraphOutputBudget.defaultBytes`.
  private static let maxChannels = 4
  private static let maxFacts = 5
  private static let maxOpenThreads = 4
  private static let maxActivities = 2
  private static let maxGroups = 5
  private static let maxAffiliations = 5
  private static let maxConnections = 6
  private static let maxSuggestions = 5
  private static let maxAmbiguous = 8

  // MARK: - Tool entry points

  /// `get_person`. Reads `name` (required), then does all file IO off the main actor.
  @MainActor
  static func getPerson(_ arguments: [String: Any]) async -> String {
    let raw = (arguments["name"] as? String)?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
    guard !raw.isEmpty else { return "Error: name is required" }
    let uid = peopleGraphUID()
    return await Task.detached(priority: .utility) {
      personResult(name: raw, uid: uid, now: Date())
    }.value
  }

  /// `search_people`. All filters optional; with none it lists the closest people.
  @MainActor
  static func searchPeople(_ arguments: [String: Any]) async -> String {
    let request = PeopleGraphSearchRequest(
      text: arguments["query"] as? String,
      affiliation: arguments["affiliation"] as? String,
      group: arguments["group"] as? String,
      quietForDays: intArgument(arguments["quiet_for_days"]),
      limit: intArgument(arguments["limit"]) ?? PeopleGraphSearchRequest.defaultLimit)
    let uid = peopleGraphUID()
    return await Task.detached(priority: .utility) {
      searchResult(request: request, uid: uid, now: Date())
    }.value
  }

  /// The people surfaces (People tab, graph builder, overrides store) all resolve
  /// the graph directory from `authUserId`; this reads the same key so chat can
  /// never answer from a different account's graph than the tab shows.
  @MainActor
  private static func peopleGraphUID() -> String? {
    UserDefaults.standard.string(forKey: .authUserId)
  }

  /// Tool arguments arrive as JSON, where an integer may decode as `Int`, `Double`,
  /// or a numeric `String` depending on the provider.
  nonisolated static func intArgument(_ value: Any?) -> Int? {
    if let int = value as? Int { return int }
    if let double = value as? Double { return Int(double) }
    if let string = value as? String { return Int(string.trimmingCharacters(in: .whitespaces)) }
    return nil
  }

  // MARK: - Results (nonisolated: safe to run off the main actor)

  nonisolated static func personResult(name: String, uid: String?, now: Date) -> String {
    switch PeopleGraphSnapshotLoader.load(uid: uid) {
    case .missing:
      return graphMissingMessage
    case .unreadable(let reason):
      return "PEOPLE GRAPH UNREADABLE — \(reason). Nothing about this person could be read."
    case .loaded(let snapshot):
      return renderPerson(name: name, snapshot: snapshot, now: now)
    }
  }

  nonisolated static func searchResult(
    request: PeopleGraphSearchRequest, uid: String?, now: Date
  ) -> String {
    switch PeopleGraphSnapshotLoader.load(uid: uid) {
    case .missing:
      return graphMissingMessage
    case .unreadable(let reason):
      return "PEOPLE GRAPH UNREADABLE — \(reason). No people could be listed."
    case .loaded(let snapshot):
      return renderSearch(request: request, snapshot: snapshot, now: now)
    }
  }

  /// Distinct from "person not found": there is no graph at all to look in.
  nonisolated static var graphMissingMessage: String {
    """
    PEOPLE GRAPH NOT BUILT — there is no people_intelligence.json on this Mac, so \
    nothing is known about anyone yet. Omi builds this graph on-device from the \
    People tab (iMessage/WhatsApp/voice). Tell the user to open the People tab to \
    build it. Do not answer the person question from other sources as if it came \
    from the people graph.
    """
  }

  // MARK: - Rendering

  nonisolated static func renderPerson(
    name: String, snapshot: PeopleGraphSnapshot, now: Date,
    budgetBytes: Int = PeopleGraphOutputBudget.defaultBytes
  ) -> String {
    guard !snapshot.isEmpty else {
      return
        "PEOPLE GRAPH EMPTY — the graph exists\(builtSuffix(snapshot)) but contains 0 people, so nothing is known about \"\(PeopleGraphChatFormat.clip(name, 60))\"."
    }

    let hits = PeopleNameMatcher.matches(query: name, in: snapshot.people)
    guard let person = hits.first else {
      return renderNotFound(name: name, snapshot: snapshot)
    }
    if hits.count > 1 {
      return renderAmbiguous(name: name, hits: hits, snapshot: snapshot, now: now)
    }

    let extras = snapshot.extras(for: person.id)
    var out = PeopleGraphOutputBudget(bytes: budgetBytes)
    out.add(headline(person, extras))
    out.add(identityLine(person))
    if let contact = lastContactLine(person, now: now) { out.add(contact) }
    if let channels = channelsLine(person, now: now) { out.add(channels) }
    if !person.who.isEmpty { out.add("Who they are: \(PeopleGraphChatFormat.clip(person.who, 240))") }
    if !person.now.isEmpty { out.add("Where things stand: \(PeopleGraphChatFormat.clip(person.now, 240))") }
    if !person.overall.isEmpty {
      out.add("Summary: \(PeopleGraphChatFormat.clip(person.overall, 340))")
    }
    out.add(
      section: "Facts:",
      items: person.facts.prefix(maxFacts).map { PeopleGraphChatFormat.clip($0, 160) })
    out.add(
      section: "Open threads:",
      items: person.openThreads.prefix(maxOpenThreads).map { PeopleGraphChatFormat.clip($0, 150) })
    out.add(section: "Shared groups:", items: groupItems(extras, snapshot: snapshot))
    out.add(section: "Affiliations:", items: affiliationItems(extras))
    out.add(section: "Knows (from shared groups and messaging):", items: connectionItems(person, extras))
    if let circle = person.circle, !circle.label.isEmpty {
      out.add("Circle: \(PeopleGraphChatFormat.clip(circle.label, 90)) (\(circle.size) people)")
    }
    out.add(
      section: "Recent activity:",
      items: person.activities.prefix(maxActivities).map { PeopleGraphChatFormat.clip($0, 130) })
    if person.needsConfirmation == true {
      let reason = person.confirmReason.map { PeopleGraphChatFormat.clip($0, 120) } ?? "weak identity signal"
      out.add("Unconfirmed identity: \(reason). Say so before asserting these details.")
    }
    out.add("Source: on-device people graph\(builtSuffix(snapshot)).")
    return out.rendered()
  }

  nonisolated static func renderSearch(
    request: PeopleGraphSearchRequest, snapshot: PeopleGraphSnapshot, now: Date,
    budgetBytes: Int = PeopleGraphOutputBudget.defaultBytes
  ) -> String {
    guard !snapshot.isEmpty else {
      return "PEOPLE GRAPH EMPTY — the graph exists\(builtSuffix(snapshot)) but contains 0 people."
    }
    let result = PeopleGraphSearch.run(request, snapshot: snapshot, now: now)
    let criteria = describe(request)
    guard !result.people.isEmpty else {
      return
        "NO PEOPLE MATCH \(criteria) — the graph has \(result.totalPeople) people and none match. The graph itself is fine\(builtSuffix(snapshot))."
    }

    var out = PeopleGraphOutputBudget(bytes: budgetBytes)
    out.add(
      "PEOPLE MATCHING \(criteria) — showing \(result.people.count) of \(result.totalMatched) matched (\(result.totalPeople) people in the graph\(builtSuffix(snapshot)))"
    )
    for (index, person) in result.people.enumerated() {
      out.add("\(index + 1). \(summaryLine(person, snapshot: snapshot, now: now))")
    }
    out.add("Call get_person with a full name from this list for the detail on any of them.")
    return out.rendered()
  }

  nonisolated static func renderNotFound(
    name: String, snapshot: PeopleGraphSnapshot
  ) -> String {
    let query = PeopleGraphChatFormat.clip(name, 60)
    let suggestions = PeopleNameMatcher.suggestions(
      query: name, in: snapshot.people, limit: maxSuggestions)
    var message =
      "NO PERSON NAMED \"\(query)\" — the people graph has \(snapshot.people.count) people\(builtSuffix(snapshot)) and none of them match that name."
    if !suggestions.isEmpty {
      message += " Similar names in the graph: \(suggestions.joined(separator: ", "))."
    }
    message +=
      " The graph is present and readable — this is a miss, not a missing graph. Do not invent details for this person."
    return message
  }

  nonisolated static func renderAmbiguous(
    name: String, hits: [PeopleIntelPerson], snapshot: PeopleGraphSnapshot, now: Date
  ) -> String {
    var out = PeopleGraphOutputBudget()
    out.add(
      "AMBIGUOUS — \(hits.count) people match \"\(PeopleGraphChatFormat.clip(name, 60))\" equally well. Ask the user which one, or call get_person again with a full name. Never merge them."
    )
    for person in hits.prefix(maxAmbiguous) {
      out.add("- \(summaryLine(person, snapshot: snapshot, now: now))")
    }
    return out.rendered()
  }

  // MARK: - Line builders

  private nonisolated static func headline(
    _ person: PeopleIntelPerson, _ extras: PersonProfileExtras
  ) -> String {
    var parts: [String] = []
    if !person.relationship.isEmpty { parts.append(person.relationship) }
    if let role = extras.role, !role.isEmpty { parts.append(PeopleGraphChatFormat.clip(role, 90)) }
    if let subtitle = person.linkedin?.subtitle, !subtitle.isEmpty, extras.role == nil {
      parts.append(PeopleGraphChatFormat.clip(subtitle, 90))
    }
    let suffix = parts.isEmpty ? "" : " — \(parts.joined(separator: " · "))"
    return "\(person.name)\(suffix)"
  }

  private nonisolated static func identityLine(_ person: PeopleIntelPerson) -> String {
    var parts = ["id=\(person.id)"]
    if let contactName = person.contactName, !contactName.isEmpty,
      contactName.caseInsensitiveCompare(person.name) != .orderedSame
    {
      parts.append("in Contacts as \(contactName)")
    }
    let aliases = person.aliases.filter {
      !$0.isEmpty && $0.caseInsensitiveCompare(person.name) != .orderedSame
    }
    if !aliases.isEmpty {
      parts.append("also called \(aliases.prefix(4).joined(separator: ", "))")
    }
    return parts.joined(separator: " · ")
  }

  private nonisolated static func lastContactLine(
    _ person: PeopleIntelPerson, now: Date
  ) -> String? {
    guard let touch = person.lastTouch, !touch.date.isEmpty else {
      return "Last contact: none recorded"
    }
    let age = PeopleGraphChatFormat.age(of: touch.date, now: now) ?? "unknown"
    let day = PeopleGraphChatFormat.day(touch.date).map { " on \($0)" } ?? ""
    let channel = touch.channel.isEmpty ? "" : " over \(touch.channel)"
    return "Last contact: \(age)\(channel)\(day)"
  }

  private nonisolated static func channelsLine(
    _ person: PeopleIntelPerson, now: Date
  ) -> String? {
    guard !person.channels.isEmpty else { return nil }
    let parts = person.channels.prefix(maxChannels).map { channel -> String in
      let age = PeopleGraphChatFormat.age(of: channel.last, now: now).map { ", last \($0)" } ?? ""
      return "\(channel.label) \(channel.count) msgs\(age)"
    }
    return "Channels: \(parts.joined(separator: " · "))"
  }

  private nonisolated static func groupItems(
    _ extras: PersonProfileExtras, snapshot: PeopleGraphSnapshot
  ) -> [String] {
    extras.groups.prefix(maxGroups).map { group in
      var line = PeopleGraphChatFormat.clip(group.name, 70)
      if !group.category.isEmpty { line += " (\(group.category))" }
      if let meaning = snapshot.meaning(forGroup: group.name), !meaning.isEmpty {
        line += " — \(PeopleGraphChatFormat.clip(meaning, 110))"
      }
      return line
    }
  }

  private nonisolated static func affiliationItems(_ extras: PersonProfileExtras) -> [String] {
    extras.affiliations.prefix(maxAffiliations).map { affiliation in
      var line = PeopleGraphChatFormat.clip(affiliation.name, 60)
      if !affiliation.kind.isEmpty { line += " (\(affiliation.kind))" }
      if let via = affiliation.via.first, !via.isEmpty {
        line += " — evidence: \(PeopleGraphChatFormat.clip(via, 70))"
      }
      return line
    }
  }

  /// The "who they know" edges, each carrying the `how`/`context` that explains it.
  private nonisolated static func connectionItems(
    _ person: PeopleIntelPerson, _ extras: PersonProfileExtras
  ) -> [String] {
    (person.connections ?? []).prefix(maxConnections).map { connection in
      let detail = extras.connectionDetails[connection.id]
      var line = connection.name.isEmpty ? connection.id : connection.name
      if let how = detail?.how, !how.isEmpty {
        line += " — \(PeopleGraphChatFormat.clip(how, 120))"
      } else if let kind = detail?.kind, !kind.isEmpty {
        line += " — \(kind)"
      }
      let context = detail?.context ?? connection.sources
      let shared = context.filter { !$0.isEmpty }.prefix(2)
      if !shared.isEmpty {
        line += " [via \(shared.map { PeopleGraphChatFormat.clip($0, 40) }.joined(separator: ", "))]"
      }
      return line
    }
  }

  private nonisolated static func summaryLine(
    _ person: PeopleIntelPerson, snapshot: PeopleGraphSnapshot, now: Date
  ) -> String {
    let extras = snapshot.extras(for: person.id)
    var parts: [String] = []
    if !person.relationship.isEmpty { parts.append(person.relationship) }
    if let role = extras.role, !role.isEmpty { parts.append(PeopleGraphChatFormat.clip(role, 60)) }
    if !person.channels.isEmpty {
      parts.append(person.channels.prefix(3).map { $0.label }.joined(separator: "/"))
    }
    let touch = person.lastTouch?.date ?? person.channels.compactMap { $0.last }.max()
    parts.append("last \(PeopleGraphChatFormat.age(of: touch, now: now) ?? "never")")
    let connectionCount = person.connections?.count ?? 0
    if connectionCount > 0 { parts.append("knows \(connectionCount)") }
    return "\(person.name) — \(parts.joined(separator: " · "))"
  }

  private nonisolated static func describe(_ request: PeopleGraphSearchRequest) -> String {
    var parts: [String] = []
    if let text = request.text { parts.append("\"\(PeopleGraphChatFormat.clip(text, 60))\"") }
    if let affiliation = request.affiliation {
      parts.append("affiliation \"\(PeopleGraphChatFormat.clip(affiliation, 60))\"")
    }
    if let group = request.group {
      parts.append("group \"\(PeopleGraphChatFormat.clip(group, 60))\"")
    }
    if let quiet = request.quietForDays { parts.append("no contact in \(quiet)+ days") }
    return parts.isEmpty ? "everyone (closest first)" : parts.joined(separator: " + ")
  }

  private nonisolated static func builtSuffix(_ snapshot: PeopleGraphSnapshot) -> String {
    guard let day = PeopleGraphChatFormat.day(snapshot.generatedAt) else { return "" }
    return ", built \(day)"
  }
}
