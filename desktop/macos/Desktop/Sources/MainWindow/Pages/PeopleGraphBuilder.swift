import Contacts
import Foundation

/// On-device people-intelligence social-graph engine.
///
/// Productizes the reference Python pipeline (`build_edges.py` + `build_communities.py`)
/// as a native Swift engine so every user gets a "who-knows-whom" social graph without a
/// one-off script. Everything here is computed **locally**: it reads the per-user
/// `imessage_export.json` the existing `IMessageExporter` already writes, resolves people
/// on-device (Contacts framework when already authorized, otherwise the export's own
/// fields), and writes derived JSON back into the same user directory. Nothing leaves the
/// machine and nothing is sent over the network.
///
/// Outputs (all under `~/Library/Application Support/Omi/users/<uid>/`):
///   - `people_social.json`      — edges, circles, per-person connections, id→name map
///   - `people_communities.json` — named group chats → communities with inferred category
///   - `people_intelligence.json`— **non-destructively merged**: `connections` / `circle` /
///     `groups` folded onto matching person cards (all existing fields preserved)
///
/// Gated behind the `peopleGraphBuild` UserDefaults flag (**default true**) and run entirely
/// off the main thread. All IO is guarded — a missing/corrupt export or unreadable directory
/// is a no-op, never a crash.
enum PeopleGraphBuilder {
  // Tunables mirror build_edges.py exactly.
  private static let edgeMin = 0.30  // min aggregated weight to keep a "knows" edge
  private static let circleMin = 1.00  // stronger bar to form a CIRCLE (real multi-group overlap)
  private static let maxGroup = 60  // ignore groups bigger than this (broadcast lists)
  private static let topConn = 6  // connections shown per person

  /// Minimum spacing between two real pipeline runs. Continuous triggers (app becoming active, a
  /// new conversation, connector imports) fan in far more often than the underlying data changes,
  /// so a run inside this window is skipped unless the caller explicitly forces it.
  static let minSyncInterval: TimeInterval = 5 * 60

  /// Continuous-sync entry point. Re-exports the local iMessage aggregates (only if the user opted
  /// in) so newly received messages are picked up, then rebuilds the derived social graph — awaited
  /// in order so the graph always builds from the freshest export. Both steps self-throttle on their
  /// own timestamps, so calling this from many data-arrival seams is cheap. Pass `force: true` right
  /// after an explicit user action (e.g. enabling iMessage mapping) to bypass the throttle.
  static func syncIfNeeded(uid: String?, force: Bool = false) async {
    await IMessageExporter.exportIfRequested(force: force)
    await rebuildIfNeeded(uid: uid, force: force)
  }

  /// Entry point. Cheap flag + throttle check on the caller's thread, then all work (read + graph
  /// build + JSON writes) runs off the main thread, awaited so callers can sequence after it. Safe to
  /// call on every People-tab load and from frequent data-arrival triggers; runs at most once per
  /// `minSyncInterval` unless `force` is set.
  static func rebuildIfNeeded(uid: String?, force: Bool = false) async {
    let enabled = (UserDefaults.standard.object(forKey: .peopleGraphBuild) as? Bool) ?? true
    guard enabled else { return }
    guard claimRun(.peopleGraphLastRebuild, force: force) else { return }
    await Task.detached(priority: .utility) {
      build(uid: uid)
    }.value
  }

  // MARK: - Throttle

  /// Pure throttle decision (no IO — unit-testable): a run should proceed when it is forced, has
  /// never run before, or the last run was at least `minInterval` ago.
  static func shouldRun(
    lastRun: Date?, now: Date = Date(), force: Bool = false, minInterval: TimeInterval = minSyncInterval
  ) -> Bool {
    if force { return true }
    guard let lastRun else { return true }
    return now.timeIntervalSince(lastRun) >= minInterval
  }

  /// UserDefaults-backed check-and-mark for a throttle `key`. Returns `true` (and records `now` as
  /// the new run time) when a run should proceed; returns `false` to skip. Combining the check and
  /// the write here means a burst of near-simultaneous triggers only admits the first.
  static func claimRun(_ key: DefaultsKey, force: Bool = false, now: Date = Date()) -> Bool {
    let stored = UserDefaults.standard.double(forKey: key)  // 0.0 when never set
    let last = stored > 0 ? Date(timeIntervalSince1970: stored) : nil
    guard shouldRun(lastRun: last, now: now, force: force) else { return false }
    UserDefaults.standard.set(now.timeIntervalSince1970, forKey: key)
    return true
  }

  // MARK: - Orchestration

  private static func build(uid: String?) {
    let effectiveUID = uid ?? UserDefaults.standard.string(forKey: .authUserId)
    guard let userDir = resolveUserDir(uid: effectiveUID) else {
      log("PeopleGraphBuilder: no user directory resolved; skipping")
      return
    }

    let exportURL = userDir.appendingPathComponent("imessage_export.json")
    guard let root = readExport(at: exportURL) else {
      // Export not produced yet (e.g. first run before FDA/export completes) — no-op.
      log("PeopleGraphBuilder: no readable imessage_export.json at \(exportURL.path); skipping")
      return
    }

    let contactsByPhone = loadContactsByPhone()

    // ---- 1. canonical people (dedupe by phone_last10, prefer a human name) ----
    let people = buildCanonicalPeople(root: root, contactsByPhone: contactsByPhone)

    // ---- 2. edges (size-normalized), circles, per-person connections ----
    let graph = buildGraph(root: root, people: people)

    // ---- 3. communities (named group chats → category) ----
    let communities = buildCommunities(root: root, people: people)

    // ---- 4. write outputs + create-or-merge ----
    writeSocial(graph: graph, to: userDir.appendingPathComponent("people_social.json"))
    writeCommunities(communities, to: userDir.appendingPathComponent("people_communities.json"))
    let peopleURL = userDir.appendingPathComponent("people_intelligence.json")
    if hasExistingPeople(at: peopleURL) {
      // A backend-written people file already exists: fold graph fields onto it, non-destructively.
      mergeIntoPeopleIntelligence(
        graph: graph, communities: communities, people: people, at: peopleURL)
    } else {
      // Fresh, backend-less user (file missing or its `people` array empty): CREATE the People
      // list from the on-device canonical people so the tab is populated with no backend at all.
      createPeopleIntelligence(
        graph: graph, communities: communities, people: people, at: peopleURL)
    }

    log(
      "PeopleGraphBuilder: \(people.canonByID.count) people, \(graph.edges.count) edges, "
        + "\(graph.circles.count) circles, \(communities.list.count) communities")
  }

  // MARK: - Input decoding (lenient)

  struct ExportRoot: Decodable {
    let handles: [Handle]
    let groups: [Group]

    enum CodingKeys: String, CodingKey { case handles, groups }

    init(from decoder: Decoder) throws {
      let c = try decoder.container(keyedBy: CodingKeys.self)
      handles = (try? c.decode([Handle].self, forKey: .handles)) ?? []
      groups = (try? c.decode([Group].self, forKey: .groups)) ?? []
    }

    struct Handle: Decodable {
      let handle: String
      let phoneLast10: String?
      let contactName: String?
      let messageCount: Int
      let lastDate: String?

      enum CodingKeys: String, CodingKey {
        case handle
        case phoneLast10 = "phone_last10"
        case contactName = "contact_name"
        case messageCount = "message_count"
        case lastDate = "last_date"
      }

      init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        handle = (try? c.decode(String.self, forKey: .handle)) ?? ""
        phoneLast10 = try? c.decodeIfPresent(String.self, forKey: .phoneLast10)
        contactName = try? c.decodeIfPresent(String.self, forKey: .contactName)
        messageCount = (try? c.decode(Int.self, forKey: .messageCount)) ?? 0
        lastDate = try? c.decodeIfPresent(String.self, forKey: .lastDate)
      }
    }

    struct Group: Decodable {
      let displayName: String
      let memberCount: Int?
      let members: [Member]

      enum CodingKeys: String, CodingKey {
        case displayName = "display_name"
        case memberCount = "member_count"
        case members
      }

      init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        displayName = (try? c.decode(String.self, forKey: .displayName)) ?? ""
        memberCount = try? c.decodeIfPresent(Int.self, forKey: .memberCount)
        members = (try? c.decode([Member].self, forKey: .members)) ?? []
      }
    }

    struct Member: Decodable {
      let handle: String?
      let phoneLast10: String?

      enum CodingKeys: String, CodingKey {
        case handle
        case phoneLast10 = "phone_last10"
      }

      init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        handle = try? c.decodeIfPresent(String.self, forKey: .handle)
        phoneLast10 = try? c.decodeIfPresent(String.self, forKey: .phoneLast10)
      }
    }
  }

  static func readExport(at url: URL) -> ExportRoot? {
    guard let data = try? Data(contentsOf: url) else { return nil }
    return try? JSONDecoder().decode(ExportRoot.self, from: data)
  }

  // MARK: - Canonical people

  struct Canon {
    let id: String
    var name: String
    var messageCount: Int
    var identified: Bool
    var lastDate: String?
  }

  /// Resolved people plus the lookup maps used to turn a group member (handle / phone) into a
  /// canonical person id. Mirrors the Python `person_for_phone` / `person_for_name` resolvers,
  /// but sourced from what is actually available on-device.
  struct People {
    var canonByID: [String: Canon] = [:]
    var idByPhone: [String: String] = [:]
    var idByEmail: [String: String] = [:]
    var idName: [String: String] = [:]

    func name(_ id: String) -> String { idName[id] ?? id }
    func closeness(_ id: String) -> Int { canonByID[id]?.messageCount ?? 0 }

    /// Resolve a group member to a canonical person id (phone first, then email handle).
    func memberID(handle: String?, phoneLast10: String?) -> String? {
      if let ph = phoneKey(explicit: phoneLast10, handle: handle), let id = idByPhone[ph] { return id }
      if let hh = handle?.lowercased(), !hh.isEmpty, let id = idByEmail[hh] { return id }
      return nil
    }
  }

  static func buildCanonicalPeople(root: ExportRoot, contactsByPhone: [String: String])
    -> People
  {
    // Gather every distinct identity (phone_last10, or email/handle when no phone) from both
    // the direct handles and every group member, so people who only ever appear in a group
    // still become nodes.
    var phoneMsg: [String: Int] = [:]
    var phoneSample: [String: String] = [:]  // representative handle string for a fallback name
    var phoneContactName: [String: String] = [:]  // name carried by the export itself (if any)
    var phoneLast: [String: String] = [:]  // most-recent message ISO date per phone
    var emailMsg: [String: Int] = [:]
    var emailSample: [String: String] = [:]
    var emailContactName: [String: String] = [:]
    var emailLast: [String: String] = [:]

    // Keep the newest ISO-8601 date. The exporter writes a fixed `.withInternetDateTime`
    // format, so lexicographic comparison equals chronological ordering.
    func keepNewer(_ store: inout [String: String], _ key: String, _ date: String?) {
      guard let d = nonEmpty(date) else { return }
      if let cur = store[key], cur >= d { return }
      store[key] = d
    }

    for h in root.handles {
      if let ph = phoneKey(explicit: h.phoneLast10, handle: h.handle) {
        phoneMsg[ph, default: 0] += max(h.messageCount, 0)
        if phoneSample[ph] == nil { phoneSample[ph] = h.handle }
        if let cn = nonEmpty(h.contactName), phoneContactName[ph] == nil { phoneContactName[ph] = cn }
        keepNewer(&phoneLast, ph, h.lastDate)
      } else {
        let key = h.handle.lowercased()
        guard !key.isEmpty else { continue }
        emailMsg[key, default: 0] += max(h.messageCount, 0)
        if emailSample[key] == nil { emailSample[key] = h.handle }
        if let cn = nonEmpty(h.contactName), emailContactName[key] == nil { emailContactName[key] = cn }
        keepNewer(&emailLast, key, h.lastDate)
      }
    }
    for g in root.groups {
      for m in g.members {
        if let ph = phoneKey(explicit: m.phoneLast10, handle: m.handle) {
          if phoneMsg[ph] == nil { phoneMsg[ph] = 0 }
          if phoneSample[ph] == nil { phoneSample[ph] = m.handle ?? ph }
        } else if let hh = m.handle?.lowercased(), !hh.isEmpty {
          if emailMsg[hh] == nil { emailMsg[hh] = 0 }
          if emailSample[hh] == nil { emailSample[hh] = m.handle ?? hh }
        }
      }
    }

    var people = People()

    func upsert(id: String, name: String, messages: Int, identified: Bool, lastDate: String?) {
      if var existing = people.canonByID[id] {
        existing.messageCount += messages
        existing.identified = existing.identified || identified
        // Prefer a human-resolved name if we only had a fallback before.
        if identified, !existing.identified { existing.name = name }
        if let d = nonEmpty(lastDate), existing.lastDate.map({ $0 < d }) ?? true {
          existing.lastDate = d
        }
        people.canonByID[id] = existing
      } else {
        people.canonByID[id] = Canon(
          id: id, name: name, messageCount: messages, identified: identified, lastDate: nonEmpty(lastDate))
      }
      people.idName[id] = people.canonByID[id]?.name ?? name
    }

    // Deterministic assignment order keeps ids/output stable across runs.
    for ph in phoneMsg.keys.sorted() {
      let resolved = contactsByPhone[ph] ?? phoneContactName[ph]
      let name = resolved ?? phoneSample[ph] ?? ph
      let id = slug(name)
      upsert(id: id, name: name, messages: phoneMsg[ph] ?? 0, identified: resolved != nil, lastDate: phoneLast[ph])
      people.idByPhone[ph] = id
    }
    for hh in emailMsg.keys.sorted() {
      let resolved = emailContactName[hh]
      let name = resolved ?? emailSample[hh] ?? hh
      let id = slug(name)
      upsert(id: id, name: name, messages: emailMsg[hh] ?? 0, identified: resolved != nil, lastDate: emailLast[hh])
      people.idByEmail[hh] = id
    }

    return people
  }

  // MARK: - Graph (edges + circles + connections)

  struct EdgeRec {
    let a: String
    let b: String
    let weight: Double
    let sources: [String]
    let context: [String]
  }

  struct Graph {
    var edges: [EdgeRec] = []
    var circles: [[String: Any]] = []  // {id,label,size,members:[{id,name}]}
    var circleChipByID: [String: [String: Any]] = [:]  // person id → {id,label,size}
    var connectionsByID: [String: [[String: Any]]] = [:]  // person id → [{id,name,weight,sources,context}]
    var idName: [String: String] = [:]
    var peopleInGraph = 0
    var groupsUsed = 0
  }

  /// Unordered pair key (a <= b) for edge aggregation.
  private struct Pair: Hashable {
    let a: String
    let b: String
    init(_ x: String, _ y: String) {
      if x <= y {
        a = x
        b = y
      } else {
        a = y
        b = x
      }
    }
  }

  static func buildGraph(root: ExportRoot, people: People) -> Graph {
    var edgeW: [Pair: Double] = [:]
    var edgeSrc: [Pair: Set<String>] = [:]
    var edgeCtx: [Pair: [String: Int]] = [:]
    var groupsUsed = 0

    // Each shared group of resolved size m contributes 1/(m-1) to every member pair.
    for g in root.groups {
      var ids = Set<String>()
      for m in g.members {
        if let id = people.memberID(handle: m.handle, phoneLast10: m.phoneLast10) { ids.insert(id) }
      }
      let members = ids.sorted()
      let m = members.count
      guard m >= 2, m <= maxGroup else { continue }
      groupsUsed += 1
      let contrib = 1.0 / Double(m - 1)
      let label = g.displayName.trimmingCharacters(in: .whitespacesAndNewlines)
      let lower = label.lowercased()
      let generic = lower.isEmpty || lower == "(unnamed)" || lower == "(no name)" || label.hasPrefix("chat")
      for i in 0..<members.count {
        for j in (i + 1)..<members.count {
          let key = Pair(members[i], members[j])
          edgeW[key, default: 0] += contrib
          edgeSrc[key, default: []].insert("imessage")
          if !generic { edgeCtx[key, default: [:]][label, default: 0] += 1 }
        }
      }
    }

    // ---- keep strong edges ----
    var edges: [EdgeRec] = edgeW.compactMap { key, w in
      guard w >= edgeMin else { return nil }
      return EdgeRec(
        a: key.a, b: key.b, weight: round3(w),
        sources: (edgeSrc[key].map { Array($0).sorted() }) ?? [],
        context: topLabels(edgeCtx[key] ?? [:], 4))
    }
    edges.sort {
      if $0.weight != $1.weight { return $0.weight > $1.weight }
      if $0.a != $1.a { return $0.a < $1.a }
      return $0.b < $1.b
    }

    // ---- adjacency ----
    var adj: [String: [String: Double]] = [:]
    for e in edges {
      adj[e.a, default: [:]][e.b] = e.weight
      adj[e.b, default: [:]][e.a] = e.weight
    }

    // ---- circles = connected components over STRONG edges only ----
    var cadj: [String: Set<String>] = [:]
    for e in edges where e.weight >= circleMin {
      cadj[e.a, default: []].insert(e.b)
      cadj[e.b, default: []].insert(e.a)
    }
    var visited = Set<String>()
    var comps: [[String]] = []
    for node in cadj.keys.sorted() {
      if visited.contains(node) { continue }
      var stack = [node]
      var comp: [String] = []
      while let x = stack.popLast() {
        if visited.contains(x) { continue }
        visited.insert(x)
        comp.append(x)
        for nb in (cadj[x] ?? []).sorted() where !visited.contains(nb) { stack.append(nb) }
      }
      if comp.count >= 2 { comps.append(comp) }
    }
    comps.sort {
      if $0.count != $1.count { return $0.count > $1.count }
      return ($0.min() ?? "") < ($1.min() ?? "")
    }

    var graph = Graph()
    graph.edges = edges
    graph.idName = people.idName
    graph.peopleInGraph = adj.count
    graph.groupsUsed = groupsUsed

    // circles + per-person circle chip (label = most-central members by closeness)
    for (i, comp) in comps.enumerated() {
      let ordered = comp.sorted {
        let ca = people.closeness($0)
        let cb = people.closeness($1)
        return ca != cb ? ca > cb : $0 < $1
      }
      let label = ordered.prefix(2).map { people.name($0) }.joined(separator: " · ")
      let members = ordered.map { ["id": $0, "name": people.name($0)] as [String: Any] }
      graph.circles.append(["id": i, "label": label, "size": comp.count, "members": members])
      let chip: [String: Any] = ["id": i, "label": label, "size": comp.count]
      for id in comp { graph.circleChipByID[id] = chip }
    }

    // per-person connections (top co-members by weight)
    for (node, nbrs) in adj {
      let top = nbrs.sorted { $0.value != $1.value ? $0.value > $1.value : $0.key < $1.key }
        .prefix(topConn)
      graph.connectionsByID[node] = top.map { b, w in
        let key = Pair(node, b)
        return [
          "id": b,
          "name": people.name(b),
          "weight": round2(w),
          "sources": (edgeSrc[key].map { Array($0).sorted() }) ?? [],
          "context": topLabels(edgeCtx[key] ?? [:], 4),
        ]
      }
    }

    return graph
  }

  // MARK: - Communities (named group chats → category)

  struct Communities {
    var list: [[String: Any]] = []  // {name,channel,category,size_total,known_members:[{id,name}]}
    var byCategory: [String: Int] = [:]
    var groupsByPersonID: [String: [[String: Any]]] = [:]  // person id → [{name,category}]
  }

  // Inferred category from the group name — ported verbatim from build_communities.py.
  private static let categories: [(String, [String])] = [
    (
      "work / venture",
      [
        "av ", " av", "pnp", "board", "analyst", "mvp", " vc", "vc ", "yc", "founder house",
        "gang", "class", "cohort", "dilly", "directors", "meat", "mofarm", "sage", "0-1",
        "startup", "intern",
      ]
    ),
    ("household", ["ave", " st", "apt", "house", "crib", "roommate", "725", "flat", "dorm"]),
    (
      "trip / event",
      ["tahoe", "yosemite", "trip", "sunday", "retreat", "vegas", "cabo", "beach", "ski", "camp"]
    ),
    ("family", ["family", " fam", "fam ", "bhai", "cousin", "mom", "dad", "parents", "ghar", "home"]),
    (
      "friends / social",
      ["friend", "cool ppl", " ppl", "squad", "crew", "boys", "girls", "besties", "gc", "group"]
    ),
  ]

  static func categorize(_ name: String) -> String {
    let n = norm(name)
    for (cat, kws) in categories where kws.contains(where: { n.contains($0) }) { return cat }
    return "social"
  }

  static func buildCommunities(root: ExportRoot, people: People) -> Communities {
    var result = Communities()

    for g in root.groups {
      let name = g.displayName.trimmingCharacters(in: .whitespacesAndNewlines)
      let lower = name.lowercased()
      if name.isEmpty || lower == "(unnamed)" || lower == "(no name)" || name.hasPrefix("chat") {
        continue
      }
      var seen = Set<String>()
      var known: [[String: Any]] = []
      for m in g.members {
        if let id = people.memberID(handle: m.handle, phoneLast10: m.phoneLast10), !seen.contains(id) {
          seen.insert(id)
          known.append(["id": id, "name": people.name(id)])
        }
      }
      guard known.count >= 2 else { continue }
      result.list.append([
        "name": name,
        "channel": "imessage",
        "category": categorize(name),
        "size_total": g.memberCount ?? g.members.count,
        "known_members": known,
      ])
    }

    // largest known-membership first (matches the Python ordering)
    result.list.sort {
      (($0["known_members"] as? [Any])?.count ?? 0) > (($1["known_members"] as? [Any])?.count ?? 0)
    }

    for c in result.list {
      let cat = c["category"] as? String ?? "social"
      result.byCategory[cat, default: 0] += 1
      guard let name = c["name"] as? String, let members = c["known_members"] as? [[String: Any]]
      else { continue }
      for m in members {
        guard let id = m["id"] as? String else { continue }
        var list = result.groupsByPersonID[id] ?? []
        if !list.contains(where: { ($0["name"] as? String) == name }) {
          list.append(["name": name, "category": cat])
        }
        result.groupsByPersonID[id] = list
      }
    }
    // unique by name, cap 8 per person
    for (id, list) in result.groupsByPersonID where list.count > 8 {
      result.groupsByPersonID[id] = Array(list.prefix(8))
    }

    return result
  }

  // MARK: - Output

  private static func writeSocial(graph: Graph, to url: URL) {
    let social: [String: Any] = [
      "generated_at": isoNow(),
      "stats": [
        "edges": graph.edges.count,
        "circles": graph.circles.count,
        "people_in_graph": graph.peopleInGraph,
        "groups_used": ["imessage": graph.groupsUsed],
      ],
      "edges": graph.edges.map {
        ["a": $0.a, "b": $0.b, "weight": $0.weight, "sources": $0.sources, "context": $0.context]
          as [String: Any]
      },
      "circles": graph.circles,
      "connections": graph.connectionsByID,
      "id_name": graph.idName,
    ]
    writeJSON(social, to: url)
  }

  private static func writeCommunities(_ communities: Communities, to url: URL) {
    let out: [String: Any] = [
      "generated_at": isoNow(),
      "count": communities.list.count,
      "by_category": communities.byCategory,
      "communities": communities.list,
    ]
    writeJSON(out, to: url)
  }

  /// True only when `people_intelligence.json` already exists AND decodes to a non-empty `people`
  /// array — i.e. a backend actually wrote person cards. A missing file or an empty `people` array
  /// is treated as "no people yet" so the on-device engine creates the list instead of merging
  /// onto nothing.
  private static func hasExistingPeople(at url: URL) -> Bool {
    guard let data = try? Data(contentsOf: url),
      let obj = try? JSONSerialization.jsonObject(with: data),
      let doc = obj as? [String: Any],
      let persons = doc["people"] as? [[String: Any]]
    else { return false }
    return !persons.isEmpty
  }

  /// Pure people-list creation (no IO): turns the canonical people plus derived graph/communities
  /// into the array of person dictionaries `PeoplePage`'s `PeopleIntelPerson` decodes. Everyone is
  /// a single on-device iMessage channel today; `closeness` is a proxy = total iMessage
  /// `message_count`. Sorted by closeness desc (id as a stable tiebreak).
  static func createPeople(people: People, graph: Graph, communities: Communities) -> [[String: Any]] {
    people.canonByID.values
      .map { canon -> [String: Any] in
        let id = canon.id
        var channel: [String: Any] = [
          "key": "imessage",
          "label": "iMessage",
          "count": canon.messageCount,
        ]
        if let last = canon.lastDate { channel["last"] = last }

        var person: [String: Any] = [
          "id": id,
          "name": canon.name,
          "closeness": Double(canon.messageCount),
          "channels": [channel],
        ]
        // Only claim a contact name when we actually resolved a human (Contacts / export name).
        if canon.identified { person["contactName"] = canon.name }
        if let last = canon.lastDate {
          person["lastTouch"] = ["channel": "imessage", "date": last]
        }
        // Graph-derived social fields (same shape the merge path folds onto backend cards).
        if let conns = graph.connectionsByID[id] { person["connections"] = conns }
        if let chip = graph.circleChipByID[id] { person["circle"] = chip }
        if let gs = communities.groupsByPersonID[id] { person["groups"] = gs }
        return person
      }
      .sorted { a, b in
        let ca = (a["closeness"] as? Double) ?? 0
        let cb = (b["closeness"] as? Double) ?? 0
        if ca != cb { return ca > cb }
        return ((a["id"] as? String) ?? "") < ((b["id"] as? String) ?? "")
      }
  }

  /// Fresh-user create path: writes a complete `people_intelligence.json` from on-device people,
  /// including top-level `stats` and `generated_at`. Only called when no backend file exists.
  private static func createPeopleIntelligence(
    graph: Graph, communities: Communities, people: People, at url: URL
  ) {
    let persons = createPeople(people: people, graph: graph, communities: communities)
    let multichannel = persons.filter { (($0["channels"] as? [[String: Any]])?.count ?? 0) > 1 }.count
    let channelKeys = Set(
      persons.flatMap { ($0["channels"] as? [[String: Any]] ?? []).compactMap { $0["key"] as? String } })
    let doc: [String: Any] = [
      "generated_at": isoNow(),
      "stats": [
        "people": persons.count,
        "multichannel": multichannel,
        "channels": channelKeys.count,
      ],
      "people": persons,
    ]
    writeJSON(doc, to: url)
  }

  /// Non-destructively fold `connections` / `circle` / `groups` onto the matching person in an
  /// existing `people_intelligence.json`. Uses `JSONSerialization` (not a rigid Codable model)
  /// so every field the backend wrote is preserved untouched. People are matched by id equality
  /// first, then by normalized name / contactName / alias.
  private static func mergeIntoPeopleIntelligence(
    graph: Graph, communities: Communities, people: People, at url: URL
  ) {
    guard let data = try? Data(contentsOf: url),
      let obj = try? JSONSerialization.jsonObject(with: data),
      var doc = obj as? [String: Any],
      var persons = doc["people"] as? [[String: Any]]
    else { return }

    var nameToID: [String: String] = [:]
    for id in people.canonByID.keys.sorted() {
      guard let name = people.canonByID[id]?.name else { continue }
      let k = norm(name)
      if nameToID[k] == nil { nameToID[k] = id }
    }

    for i in persons.indices {
      var p = persons[i]
      var matched: String?
      if let pid = p["id"] as? String,
        graph.connectionsByID[pid] != nil || graph.circleChipByID[pid] != nil
          || communities.groupsByPersonID[pid] != nil
      {
        matched = pid
      }
      if matched == nil {
        var candidates: [String] = []
        if let n = p["name"] as? String { candidates.append(n) }
        if let cn = p["contactName"] as? String { candidates.append(cn) }
        if let aliases = p["aliases"] as? [String] { candidates.append(contentsOf: aliases) }
        for cand in candidates where nameToID[norm(cand)] != nil {
          matched = nameToID[norm(cand)]
          break
        }
      }
      if let id = matched {
        if let conns = graph.connectionsByID[id] { p["connections"] = conns }
        if let chip = graph.circleChipByID[id] { p["circle"] = chip }
        if let gs = communities.groupsByPersonID[id] { p["groups"] = gs }
      }
      persons[i] = p
    }

    doc["people"] = persons
    writeJSON(doc, to: url)
  }

  private static func writeJSON(_ obj: Any, to url: URL) {
    guard JSONSerialization.isValidJSONObject(obj) else {
      log("PeopleGraphBuilder: refusing to write invalid JSON to \(url.lastPathComponent)")
      return
    }
    do {
      let data = try JSONSerialization.data(withJSONObject: obj, options: [.prettyPrinted, .sortedKeys])
      try FileManager.default.createDirectory(
        at: url.deletingLastPathComponent(), withIntermediateDirectories: true)
      try data.write(to: url, options: .atomic)
    } catch {
      log("PeopleGraphBuilder: write failed for \(url.lastPathComponent): \(error)")
    }
  }

  // MARK: - Contacts (only when already authorized — never prompts)

  /// Builds a `phone_last10 → display name` map from the local Contacts store, but **only** when
  /// access is already granted. Status is checked explicitly so this never triggers a TCC prompt.
  private static func loadContactsByPhone() -> [String: String] {
    guard CNContactStore.authorizationStatus(for: .contacts) == .authorized else { return [:] }
    var map: [String: String] = [:]
    let store = CNContactStore()
    let keys: [CNKeyDescriptor] = [
      CNContactGivenNameKey as CNKeyDescriptor,
      CNContactFamilyNameKey as CNKeyDescriptor,
      CNContactOrganizationNameKey as CNKeyDescriptor,
      CNContactPhoneNumbersKey as CNKeyDescriptor,
    ]
    let request = CNContactFetchRequest(keysToFetch: keys)
    do {
      try store.enumerateContacts(with: request) { contact, _ in
        let name = contactDisplayName(contact)
        guard !name.isEmpty else { return }
        for phone in contact.phoneNumbers {
          if let ph = last10(phone.value.stringValue), map[ph] == nil { map[ph] = name }
        }
      }
    } catch {
      log("PeopleGraphBuilder: Contacts enumeration failed: \(error)")
    }
    return map
  }

  private static func contactDisplayName(_ contact: CNContact) -> String {
    let full = "\(contact.givenName) \(contact.familyName)".trimmingCharacters(in: .whitespaces)
    if !full.isEmpty { return full }
    return contact.organizationName.trimmingCharacters(in: .whitespaces)
  }

  // MARK: - Directory resolution (mirrors PeopleViewModel / IMessageExporter)

  private static func resolveUserDir(uid: String?) -> URL? {
    let fm = FileManager.default
    guard let support = fm.urls(for: .applicationSupportDirectory, in: .userDomainMask).first
    else { return nil }
    let usersDir = support.appendingPathComponent("Omi/users", isDirectory: true)

    if let uid, !uid.isEmpty {
      let dir = usersDir.appendingPathComponent(uid, isDirectory: true)
      if fm.fileExists(atPath: dir.appendingPathComponent("imessage_export.json").path) { return dir }
      if fm.fileExists(atPath: dir.path) { return dir }
    }
    guard
      let entries = try? fm.contentsOfDirectory(
        at: usersDir, includingPropertiesForKeys: nil, options: [.skipsHiddenFiles])
    else { return nil }
    for e in entries
    where fm.fileExists(atPath: e.appendingPathComponent("imessage_export.json").path) { return e }
    for e in entries
    where fm.fileExists(atPath: e.appendingPathComponent("people_intelligence.json").path) { return e }
    return nil
  }

  // MARK: - Small helpers (mirror the Python norm/last10/slug)

  private static func nonEmpty(_ s: String?) -> String? {
    guard let t = s?.trimmingCharacters(in: .whitespacesAndNewlines), !t.isEmpty else { return nil }
    return t
  }

  private static func phoneKey(explicit: String?, handle: String?) -> String? {
    if let e = explicit, !e.isEmpty { return e }
    return last10(handle)
  }

  /// Last 10 digits of a phone-like string (stable cross-format key), or nil for emails / short
  /// codes with fewer than 10 digits — same rule the exporter uses for `phone_last10`.
  private static func last10(_ s: String?) -> String? {
    guard let s, !s.contains("@") else { return nil }
    let digits = s.filter { $0.isNumber }
    guard digits.count >= 10 else { return nil }
    return String(digits.suffix(10))
  }

  private static func norm(_ s: String?) -> String {
    let lowered = (s ?? "").lowercased()
    return lowered.split(whereSeparator: { $0.isWhitespace }).joined(separator: " ")
  }

  private static func slug(_ n: String) -> String {
    var out = ""
    var lastDash = false
    for ch in n.lowercased() {
      if ch.isASCII && (ch.isLetter || ch.isNumber) {
        out.append(ch)
        lastDash = false
      } else if !lastDash {
        out.append("-")
        lastDash = true
      }
    }
    let trimmed = out.trimmingCharacters(in: CharacterSet(charactersIn: "-"))
    return trimmed.isEmpty ? "person" : trimmed
  }

  private static func topLabels(_ counts: [String: Int], _ n: Int) -> [String] {
    counts.sorted { $0.value != $1.value ? $0.value > $1.value : $0.key < $1.key }
      .prefix(n).map { $0.key }
  }

  private static func round2(_ v: Double) -> Double { (v * 100).rounded() / 100 }
  private static func round3(_ v: Double) -> Double { (v * 1000).rounded() / 1000 }

  private static func isoNow() -> String {
    let f = ISO8601DateFormatter()
    f.formatOptions = [.withInternetDateTime]
    return f.string(from: Date())
  }
}
