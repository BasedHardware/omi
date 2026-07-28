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
    // Names for iMessage-only 1:1 threads (which store phone numbers only) come from Contacts, so a
    // grant here is what lets those threads be labelled and deep-ingested by PeopleThreadIngest.
    // Fire-and-forget so the permission prompt NEVER blocks the export/graph/ingest pipeline — the
    // grant is picked up on the next sync. A denial is fine (WhatsApp names still apply).
    requestContactsAccessIfNeeded()
    await IMessageExporter.exportIfRequested(force: force)
    // WhatsApp shares the single Full Disk Access grant and the same `peopleIMessageExport` consent
    // flag, so opting in to on-device message mapping re-reads it too. Own throttle; off-main.
    await WhatsAppReader.exportIfRequested(force: force)
    await rebuildIfNeeded(uid: uid, force: force)
    // Write derived graph-structural relationship facts (who-knows-whom via shared groups/circles)
    // into the user's memory store. Self-gated on the same iMessage consent flag and its own
    // throttle; off-main; silent on any failure.
    await PeopleMemoryWriter.writeIfNeeded(uid: uid, force: force)
    // Route each substantial 1:1 thread through Omi's OWN conversation→memory pipeline so chat gains
    // a deep, searchable understanding of the relationship from the actual message content. This is
    // complementary to (not a duplicate of) the graph-structural facts above — it extracts content
    // facts no single thread's group membership captures. Same consent gate; own throttle; off-main;
    // silent on any failure.
    await PeopleThreadIngest.ingestIfNeeded(uid: uid, force: force)
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
  /// the write here means a burst of near-simultaneous triggers only admits the first. `minInterval`
  /// defaults to the graph-sync cadence but callers with tighter external budgets (e.g. the
  /// rate-limited thread ingest) pass a longer one so they self-throttle more conservatively.
  static func claimRun(
    _ key: DefaultsKey, force: Bool = false, now: Date = Date(), minInterval: TimeInterval = minSyncInterval
  ) -> Bool {
    let stored = UserDefaults.standard.double(forKey: key)  // 0.0 when never set
    let last = stored > 0 ? Date(timeIntervalSince1970: stored) : nil
    guard shouldRun(lastRun: last, now: now, force: force, minInterval: minInterval) else { return false }
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

    // Read every on-device connector export present, tag each with its channel, and merge them into
    // one root so identity resolution, edges, and communities are computed across all channels at
    // once (a person on both iMessage and WhatsApp resolves to a single node).
    let imessage = readExport(at: userDir.appendingPathComponent("imessage_export.json"))
    let whatsapp = readExport(at: userDir.appendingPathComponent("whatsapp_export.json"))
    guard imessage != nil || whatsapp != nil else {
      // No export produced yet (e.g. first run before FDA/export completes) — no-op.
      log("PeopleGraphBuilder: no readable imessage/whatsapp export in \(userDir.path); skipping")
      return
    }
    let root = mergedRoot(imessage: imessage, whatsapp: whatsapp)

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

    /// Direct construction used when merging multiple channel exports into one root.
    init(handles: [Handle], groups: [Group]) {
      self.handles = handles
      self.groups = groups
    }

    struct Handle: Decodable {
      let handle: String
      let phoneLast10: String?
      let contactName: String?
      let messageCount: Int
      let lastDate: String?
      /// Which connector this handle came from ("imessage" / "whatsapp"). Not part of the on-disk
      /// export shape — stamped in-memory at merge time — so it defaults to "imessage" for the
      /// iMessage export, which carries no channel field.
      var channel: String = "imessage"

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

      func withChannel(_ channel: String) -> Handle {
        var copy = self
        copy.channel = channel
        return copy
      }
    }

    struct Group: Decodable {
      let displayName: String
      let memberCount: Int?
      let members: [Member]
      /// Source connector for this group ("imessage" / "whatsapp"); stamped at merge time so edge
      /// `sources` and community `channel` carry honest provenance. Defaults to "imessage".
      var channel: String = "imessage"

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

      func withChannel(_ channel: String) -> Group {
        var copy = self
        copy.channel = channel
        return copy
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

  /// Combine the per-connector exports into one root, stamping each handle/group with its channel so
  /// every downstream computation (canonical people, edges, communities) runs once over all sources.
  /// Nil inputs are skipped; identity dedupe across channels then happens naturally in
  /// `buildCanonicalPeople` (same `phone_last10` ⇒ one person, regardless of channel).
  static func mergedRoot(imessage: ExportRoot?, whatsapp: ExportRoot?) -> ExportRoot {
    var handles: [ExportRoot.Handle] = []
    var groups: [ExportRoot.Group] = []
    if let im = imessage {
      handles += im.handles.map { $0.withChannel("imessage") }
      groups += im.groups.map { $0.withChannel("imessage") }
    }
    if let wa = whatsapp {
      handles += wa.handles.map { $0.withChannel("whatsapp") }
      groups += wa.groups.map { $0.withChannel("whatsapp") }
    }
    return ExportRoot(handles: handles, groups: groups)
  }

  // MARK: - Canonical people

  struct Canon {
    let id: String
    var name: String
    var messageCount: Int
    var identified: Bool
    var lastDate: String?
    /// Per-channel message counts ("imessage" / "whatsapp" → count). Drives the multi-channel
    /// breakdown in `createPeople`; a person seen on both channels gets one card with two channels.
    var messagesByChannel: [String: Int] = [:]
    /// Per-channel most-recent message date, used to pick the channel for `lastTouch`.
    var lastByChannel: [String: String] = [:]
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
    var phoneMsgCh: [String: [String: Int]] = [:]  // phone → channel → count
    var phoneLastCh: [String: [String: String]] = [:]  // phone → channel → newest ISO date
    var emailMsg: [String: Int] = [:]
    var emailSample: [String: String] = [:]
    var emailContactName: [String: String] = [:]
    var emailLast: [String: String] = [:]
    var emailMsgCh: [String: [String: Int]] = [:]
    var emailLastCh: [String: [String: String]] = [:]

    // Keep the newest ISO-8601 date. The exporter writes a fixed `.withInternetDateTime`
    // format, so lexicographic comparison equals chronological ordering.
    func keepNewer(_ store: inout [String: String], _ key: String, _ date: String?) {
      guard let d = nonEmpty(date) else { return }
      if let cur = store[key], cur >= d { return }
      store[key] = d
    }
    // Same newest-wins rule, but keyed per (identity, channel).
    func keepNewerChannel(_ store: inout [String: [String: String]], _ key: String, _ channel: String, _ date: String?)
    {
      guard let d = nonEmpty(date) else { return }
      if let cur = store[key]?[channel], cur >= d { return }
      store[key, default: [:]][channel] = d
    }

    for h in root.handles {
      let msgs = max(h.messageCount, 0)
      if let ph = phoneKey(explicit: h.phoneLast10, handle: h.handle) {
        phoneMsg[ph, default: 0] += msgs
        phoneMsgCh[ph, default: [:]][h.channel, default: 0] += msgs
        if phoneSample[ph] == nil { phoneSample[ph] = h.handle }
        if let cn = nonEmpty(h.contactName), phoneContactName[ph] == nil { phoneContactName[ph] = cn }
        keepNewer(&phoneLast, ph, h.lastDate)
        keepNewerChannel(&phoneLastCh, ph, h.channel, h.lastDate)
      } else {
        let key = h.handle.lowercased()
        guard !key.isEmpty else { continue }
        emailMsg[key, default: 0] += msgs
        emailMsgCh[key, default: [:]][h.channel, default: 0] += msgs
        if emailSample[key] == nil { emailSample[key] = h.handle }
        if let cn = nonEmpty(h.contactName), emailContactName[key] == nil { emailContactName[key] = cn }
        keepNewer(&emailLast, key, h.lastDate)
        keepNewerChannel(&emailLastCh, key, h.channel, h.lastDate)
      }
    }
    for g in root.groups {
      for m in g.members {
        if let ph = phoneKey(explicit: m.phoneLast10, handle: m.handle) {
          if phoneMsg[ph] == nil { phoneMsg[ph] = 0 }
          // Record the channel a group-only person appeared on, at zero direct messages, so their
          // card still shows the right channel dot.
          if phoneMsgCh[ph]?[g.channel] == nil { phoneMsgCh[ph, default: [:]][g.channel] = 0 }
          if phoneSample[ph] == nil { phoneSample[ph] = m.handle ?? ph }
        } else if let hh = m.handle?.lowercased(), !hh.isEmpty {
          if emailMsg[hh] == nil { emailMsg[hh] = 0 }
          if emailMsgCh[hh]?[g.channel] == nil { emailMsgCh[hh, default: [:]][g.channel] = 0 }
          if emailSample[hh] == nil { emailSample[hh] = m.handle ?? hh }
        }
      }
    }

    var people = People()

    func upsert(
      id: String, name: String, messages: Int, identified: Bool, lastDate: String?,
      byChannel: [String: Int], lastByChannel: [String: String]
    ) {
      if var existing = people.canonByID[id] {
        existing.messageCount += messages
        existing.identified = existing.identified || identified
        // Prefer a human-resolved name if we only had a fallback before.
        if identified, !existing.identified { existing.name = name }
        if let d = nonEmpty(lastDate), existing.lastDate.map({ $0 < d }) ?? true {
          existing.lastDate = d
        }
        for (ch, count) in byChannel { existing.messagesByChannel[ch, default: 0] += count }
        for (ch, d) in lastByChannel where existing.lastByChannel[ch].map({ $0 < d }) ?? true {
          existing.lastByChannel[ch] = d
        }
        people.canonByID[id] = existing
      } else {
        people.canonByID[id] = Canon(
          id: id, name: name, messageCount: messages, identified: identified, lastDate: nonEmpty(lastDate),
          messagesByChannel: byChannel, lastByChannel: lastByChannel)
      }
      people.idName[id] = people.canonByID[id]?.name ?? name
    }

    // Deterministic assignment order keeps ids/output stable across runs.
    for ph in phoneMsg.keys.sorted() {
      let resolved = contactsByPhone[ph] ?? phoneContactName[ph]
      let name = resolved ?? phoneSample[ph] ?? ph
      let id = slug(name)
      upsert(
        id: id, name: name, messages: phoneMsg[ph] ?? 0, identified: resolved != nil, lastDate: phoneLast[ph],
        byChannel: phoneMsgCh[ph] ?? [:], lastByChannel: phoneLastCh[ph] ?? [:])
      people.idByPhone[ph] = id
    }
    for hh in emailMsg.keys.sorted() {
      let resolved = emailContactName[hh]
      let name = resolved ?? emailSample[hh] ?? hh
      let id = slug(name)
      upsert(
        id: id, name: name, messages: emailMsg[hh] ?? 0, identified: resolved != nil, lastDate: emailLast[hh],
        byChannel: emailMsgCh[hh] ?? [:], lastByChannel: emailLastCh[hh] ?? [:])
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
    /// Number of graph-contributing groups per channel ("imessage" / "whatsapp"), surfaced in the
    /// social-graph stats so the UI can show which connectors fed the graph.
    var groupsUsedByChannel: [String: Int] = [:]
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
    var groupsUsedByChannel: [String: Int] = [:]

    // Each shared group of resolved size m contributes 1/(m-1) to every member pair.
    for g in root.groups {
      var ids = Set<String>()
      for m in g.members {
        if let id = people.memberID(handle: m.handle, phoneLast10: m.phoneLast10) { ids.insert(id) }
      }
      let members = ids.sorted()
      let m = members.count
      guard m >= 2, m <= maxGroup else { continue }
      groupsUsedByChannel[g.channel, default: 0] += 1
      let contrib = 1.0 / Double(m - 1)
      let label = g.displayName.trimmingCharacters(in: .whitespacesAndNewlines)
      let lower = label.lowercased()
      let generic = lower.isEmpty || lower == "(unnamed)" || lower == "(no name)" || label.hasPrefix("chat")
      for i in 0..<members.count {
        for j in (i + 1)..<members.count {
          let key = Pair(members[i], members[j])
          edgeW[key, default: 0] += contrib
          // Real provenance: an edge from a WhatsApp group is sourced "whatsapp"; a pair that
          // co-occurs on both channels carries both, corroborating the "knows" relationship.
          edgeSrc[key, default: []].insert(g.channel)
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
    graph.groupsUsedByChannel = groupsUsedByChannel

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
        "channel": g.channel,
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
        "groups_used": graph.groupsUsedByChannel,
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

  /// Human label for an on-device channel key (e.g. "whatsapp" → "WhatsApp").
  static func channelLabel(_ key: String) -> String {
    switch key {
    case "imessage": return "iMessage"
    case "whatsapp": return "WhatsApp"
    default: return key.prefix(1).uppercased() + key.dropFirst()
    }
  }

  /// Pure people-list creation (no IO): turns the canonical people plus derived graph/communities
  /// into the array of person dictionaries `PeoplePage`'s `PeopleIntelPerson` decodes. A person seen
  /// on more than one connector gets one card with a channel entry per connector (that is the
  /// multi-channel view); `closeness` is a proxy = total `message_count` across channels. Sorted by
  /// closeness desc (id as a stable tiebreak).
  static func createPeople(people: People, graph: Graph, communities: Communities) -> [[String: Any]] {
    people.canonByID.values
      .map { canon -> [String: Any] in
        let id = canon.id
        // One channel entry per connector this person was seen on, biggest first (stable by key).
        let byChannel =
          canon.messagesByChannel.isEmpty
          ? ["imessage": canon.messageCount] : canon.messagesByChannel
        let channels: [[String: Any]] =
          byChannel
          .sorted { $0.value != $1.value ? $0.value > $1.value : $0.key < $1.key }
          .map { key, count -> [String: Any] in
            var channel: [String: Any] = ["key": key, "label": channelLabel(key), "count": count]
            if let last = canon.lastByChannel[key] { channel["last"] = last }
            return channel
          }

        var person: [String: Any] = [
          "id": id,
          "name": canon.name,
          "closeness": Double(canon.messageCount),
          "channels": channels,
        ]
        // Only claim a contact name when we actually resolved a human (Contacts / export name).
        if canon.identified { person["contactName"] = canon.name }
        if let last = canon.lastDate {
          // Attribute the last touch to whichever channel carried that newest date.
          let lastChannel =
            canon.lastByChannel.first(where: { $0.value == last })?.key
            ?? channels.first?["key"] as? String ?? "imessage"
          person["lastTouch"] = ["channel": lastChannel, "date": last]
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
  /// Weak-signal review items and the user's saved corrections are folded in before writing, so
  /// the tab never silently asserts an uncertain identity/fact and user truth always wins.
  private static func createPeopleIntelligence(
    graph: Graph, communities: Communities, people: People, at url: URL
  ) {
    let persons = createPeople(people: people, graph: graph, communities: communities)
    let overrides = PeopleOverridesStore.load(directory: url.deletingLastPathComponent())
    let result = annotateAndReview(persons: persons, overrides: overrides)
    let finalPeople = result.people
    let multichannel = finalPeople.filter { (($0["channels"] as? [[String: Any]])?.count ?? 0) > 1 }
      .count
    let channelKeys = Set(
      finalPeople.flatMap {
        ($0["channels"] as? [[String: Any]] ?? []).compactMap { $0["key"] as? String }
      })
    let doc: [String: Any] = [
      "generated_at": isoNow(),
      "stats": [
        "people": finalPeople.count,
        "multichannel": multichannel,
        "channels": channelKeys.count,
      ],
      "people": finalPeople,
      "reviewQueue": result.reviewQueue,
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

    // Flag weak-signal identities/facts and fold the user's saved corrections in (user truth wins)
    // before persisting, so a backend-written card is never surfaced as certain when it isn't.
    let overrides = PeopleOverridesStore.load(directory: url.deletingLastPathComponent())
    let result = annotateAndReview(persons: persons, overrides: overrides)
    doc["people"] = result.people
    doc["reviewQueue"] = result.reviewQueue
    writeJSON(doc, to: url)
  }

  // MARK: - Human-in-the-loop review + user overrides

  /// Cap on low-confidence items surfaced at once, keeping the "Needs your confirmation" surface
  /// glanceable rather than an endless backlog.
  static let reviewQueueCap = 20
  /// Only the closest N people (the array is pre-sorted by closeness) are scanned for similar-name
  /// identity collisions, bounding the O(n²) pair scan on large lists.
  private static let similarNameScanLimit = 160

  /// Annotate weak-signal people with `needsConfirmation` / `confirmReason`, derive a capped
  /// `reviewQueue` of low-confidence items, then fold the user's saved decisions in so user truth
  /// always wins. Pure (no IO) and idempotent — safe to run on every write.
  ///
  /// Weak signals flagged today:
  ///   - a name that is edit-distance-close to another canonical person (e.g. Prisha / Pritha) —
  ///     surfaced as an `identity` question the user confirms, splits, or skips;
  ///   - a first-name-only identity that collides with another person's first name (ambiguous
  ///     "which one?") — surfaced as the same `identity` question;
  ///   - a `fact` carried by an identity-uncertain person — surfaced as a `fact` question the user
  ///     accepts, rejects (drops), or edits.
  static func annotateAndReview(
    persons: [[String: Any]], overrides: PeopleOverrides
  ) -> (people: [[String: Any]], reviewQueue: [[String: Any]]) {
    var people = persons
    var review: [[String: Any]] = []

    func id(_ p: [String: Any]) -> String { (p["id"] as? String) ?? "" }
    func name(_ p: [String: Any]) -> String { (p["name"] as? String) ?? "" }
    func pairKey(_ a: String, _ b: String) -> String { a < b ? "\(a)|\(b)" : "\(b)|\(a)" }

    // ---- 1. similar-name identity collisions (the Prisha / Pritha case) ----
    let scanCount = min(people.count, similarNameScanLimit)
    var flaggedPairs = Set<String>()
    if scanCount >= 2 {
      outer: for i in 0..<(scanCount - 1) {
        for j in (i + 1)..<scanCount {
          let na = norm(name(people[i]))
          let nb = norm(name(people[j]))
          guard !na.isEmpty, !nb.isEmpty, na != nb, na.first == nb.first else { continue }
          guard min(na.count, nb.count) >= 4 else { continue }
          let dist = editDistance(na, nb)
          guard dist >= 1, dist <= 2 else { continue }
          let a = id(people[i])
          let b = id(people[j])
          guard !a.isEmpty, !b.isEmpty, a != b else { continue }
          let key = pairKey(a, b)
          guard !flaggedPairs.contains(key) else { continue }
          flaggedPairs.insert(key)
          people[i]["needsConfirmation"] = true
          people[i]["confirmReason"] = "Name is very close to \(name(people[j])) — might be the same person"
          people[j]["needsConfirmation"] = true
          people[j]["confirmReason"] = "Name is very close to \(name(people[i])) — might be the same person"
          review.append([
            "id": "identity:\(key)",
            "name": name(people[i]),
            "kind": "identity",
            "question": "Are \(name(people[i])) and \(name(people[j])) the same person?",
            "options": ["Confirm", "Not the same", "Skip"],
            "a": a,
            "b": b,
          ])
          if review.count >= reviewQueueCap { break outer }
        }
      }
    }

    // ---- 2. first-name-only collisions (two identities that are just the same first name) ----
    // A single-token name is a weak identity; when two distinct people share the exact same one
    // (e.g. two "Alex" cards), ask which — rather than assuming they are the same or different.
    if review.count < reviewQueueCap {
      var byFirstNameOnly: [String: [Int]] = [:]
      for idx in 0..<min(people.count, similarNameScanLimit) {
        let n = norm(name(people[idx]))
        guard !n.isEmpty, !n.contains(" "), n.count >= 2 else { continue }  // single token only
        byFirstNameOnly[n, default: []].append(idx)
      }
      for firstName in byFirstNameOnly.keys.sorted() {
        guard review.count < reviewQueueCap, let indices = byFirstNameOnly[firstName], indices.count >= 2
        else { continue }
        // One question per colliding first name: pair the two closest (indices are closeness-sorted).
        let i = indices[0]
        let j = indices[1]
        let a = id(people[i])
        let b = id(people[j])
        guard !a.isEmpty, !b.isEmpty, a != b else { continue }
        let key = pairKey(a, b)
        guard !flaggedPairs.contains(key) else { continue }
        flaggedPairs.insert(key)
        for idx in indices {
          people[idx]["needsConfirmation"] = true
          people[idx]["confirmReason"] = "Matched on a first name only — may be more than one person"
        }
        review.append([
          "id": "identity:\(key)",
          "name": name(people[i]),
          "kind": "identity",
          "question": "You have two contacts named \(name(people[i])) — are they the same person?",
          "options": ["Confirm", "Not the same", "Skip"],
          "a": a,
          "b": b,
        ])
      }
    }

    // ---- 3. fact confirmation for identity-uncertain people that carry inferred facts ----
    if review.count < reviewQueueCap {
      for idx in people.indices {
        guard review.count < reviewQueueCap else { break }
        guard (people[idx]["needsConfirmation"] as? Bool) == true else { continue }
        guard let facts = people[idx]["facts"] as? [String],
          let fact = facts.first(where: { !$0.trimmingCharacters(in: .whitespaces).isEmpty })
        else { continue }
        let pid = id(people[idx])
        review.append([
          "id": "fact:\(pid)",
          "name": name(people[idx]),
          "kind": "fact",
          "question": "Is this right about \(name(people[idx]))? \u{201C}\(fact)\u{201D}",
          "options": ["Yes", "No", "Edit"],
          "personId": pid,
          "fact": fact,
        ])
      }
    }

    return applyOverrides(people: people, reviewQueue: review, overrides: overrides)
  }

  /// Fold the user's saved decisions onto derived people + review items. **User truth wins:**
  /// a confirmed-same identity merges the two cards, a confirmed-different / skipped / edited item
  /// never resurfaces, and a corrected fact replaces (or, when blank, drops) the inferred text.
  /// Pure and deterministic — no IO.
  static func applyOverrides(
    people: [[String: Any]], reviewQueue: [[String: Any]], overrides: PeopleOverrides
  ) -> (people: [[String: Any]], reviewQueue: [[String: Any]]) {
    var byIndex = people
    func indexOf(_ pid: String) -> Int? { byIndex.firstIndex { ($0["id"] as? String) == pid } }
    func pairKey(_ a: String, _ b: String) -> String { a < b ? "\(a)|\(b)" : "\(b)|\(a)" }

    var decidedPairs = Set<String>()

    // ---- identity decisions ----
    for decision in overrides.identity {
      let a = decision.a
      let b = decision.b
      guard !a.isEmpty, !b.isEmpty, a != b else { continue }
      decidedPairs.insert(pairKey(a, b))
      if decision.same {
        guard let ia = indexOf(a), let ib = indexOf(b) else {
          // One side already merged away transitively; just clear any survivor's flag.
          for pid in [a, b] { if let i = indexOf(pid) { clearConfirmation(&byIndex[i]) } }
          continue
        }
        let ca = (byIndex[ia]["closeness"] as? Double) ?? 0
        let cb = (byIndex[ib]["closeness"] as? Double) ?? 0
        let keep = ca >= cb ? ia : ib
        let drop = ca >= cb ? ib : ia
        byIndex[keep] = mergePersons(survivor: byIndex[keep], absorbed: byIndex[drop])
        clearConfirmation(&byIndex[keep])
        byIndex.remove(at: drop)
      } else {
        // Confirmed different: keep both, stop flagging/asking.
        for pid in [a, b] { if let i = indexOf(pid) { clearConfirmation(&byIndex[i]) } }
      }
    }

    // ---- fact edits (replace, or drop when the correction is blank) ----
    let unit = "\u{1F}"  // unit separator — never appears in a person id or fact
    var editedFactKeys = Set<String>()
    for edit in overrides.factEdits {
      editedFactKeys.insert("\(edit.id)\(unit)\(edit.original)")
      guard let i = indexOf(edit.id), var facts = byIndex[i]["facts"] as? [String] else { continue }
      let corrected = edit.corrected.trimmingCharacters(in: .whitespacesAndNewlines)
      if let fi = facts.firstIndex(of: edit.original) {
        if corrected.isEmpty {
          facts.remove(at: fi)
        } else {
          facts[fi] = corrected
        }
      } else if !corrected.isEmpty, !facts.contains(corrected) {
        facts.append(corrected)
      }
      byIndex[i]["facts"] = facts
    }

    // ---- filter the review queue: drop decided / edited / dismissed items ----
    let dismissed = Set(overrides.dismissed)
    let filtered = reviewQueue.filter { item in
      guard let itemId = item["id"] as? String else { return false }
      if dismissed.contains(itemId) { return false }
      let kind = item["kind"] as? String
      if kind == "identity", let a = item["a"] as? String, let b = item["b"] as? String,
        decidedPairs.contains(pairKey(a, b))
      {
        return false
      }
      if kind == "fact", let pid = item["personId"] as? String, let fact = item["fact"] as? String,
        editedFactKeys.contains("\(pid)\(unit)\(fact)")
      {
        return false
      }
      return true
    }

    return (byIndex, filtered)
  }

  private static func clearConfirmation(_ person: inout [String: Any]) {
    person["needsConfirmation"] = false
    person.removeValue(forKey: "confirmReason")
  }

  /// Merge an absorbed person into the survivor: keep the survivor's card, record the absorbed
  /// name/aliases as aliases, sum closeness, and union facts. Never loses the user-confirmed link.
  private static func mergePersons(survivor: [String: Any], absorbed: [String: Any]) -> [String: Any] {
    var out = survivor
    let survivorName = (out["name"] as? String) ?? ""
    var aliases = (out["aliases"] as? [String]) ?? []
    func addAlias(_ raw: String?) {
      guard let value = raw?.trimmingCharacters(in: .whitespacesAndNewlines), !value.isEmpty else {
        return
      }
      if value.caseInsensitiveCompare(survivorName) == .orderedSame { return }
      if !aliases.contains(where: { $0.caseInsensitiveCompare(value) == .orderedSame }) {
        aliases.append(value)
      }
    }
    addAlias(absorbed["name"] as? String)
    for alias in (absorbed["aliases"] as? [String]) ?? [] { addAlias(alias) }
    if !aliases.isEmpty { out["aliases"] = aliases }

    let combined = ((out["closeness"] as? Double) ?? 0) + ((absorbed["closeness"] as? Double) ?? 0)
    out["closeness"] = combined

    if let absorbedFacts = absorbed["facts"] as? [String], !absorbedFacts.isEmpty {
      var facts = (out["facts"] as? [String]) ?? []
      for fact in absorbedFacts where !facts.contains(fact) { facts.append(fact) }
      out["facts"] = facts
    }
    return out
  }

  /// Levenshtein edit distance (two-row DP). Used to detect names that are one or two edits apart
  /// (e.g. Prisha / Pritha) so a weak identity match asks instead of silently merging.
  static func editDistance(_ a: String, _ b: String) -> Int {
    let s = Array(a)
    let t = Array(b)
    if s.isEmpty { return t.count }
    if t.isEmpty { return s.count }
    var prev = Array(0...t.count)
    var curr = [Int](repeating: 0, count: t.count + 1)
    for i in 1...s.count {
      curr[0] = i
      for j in 1...t.count {
        let cost = s[i - 1] == t[j - 1] ? 0 : 1
        curr[j] = min(prev[j] + 1, curr[j - 1] + 1, prev[j - 1] + cost)
      }
      swap(&prev, &curr)
    }
    return prev[t.count]
  }

  /// Re-apply the user's saved corrections to the already-written `people_intelligence.json`
  /// without a full pipeline run. Lets a Confirm/Correct/Skip decision take effect immediately —
  /// even when there is no fresh iMessage export to trigger a rebuild. Guarded IO; a missing or
  /// unreadable file is a no-op.
  static func reapplyOverrides(uid: String?) {
    guard let dir = PeopleUserDirectory.resolve(uid: uid) else { return }
    let url = dir.appendingPathComponent("people_intelligence.json")
    guard let data = try? Data(contentsOf: url),
      let obj = try? JSONSerialization.jsonObject(with: data),
      var doc = obj as? [String: Any],
      let persons = doc["people"] as? [[String: Any]]
    else { return }
    let overrides = PeopleOverridesStore.load(directory: dir)
    let result = annotateAndReview(persons: persons, overrides: overrides)
    doc["people"] = result.people
    doc["reviewQueue"] = result.reviewQueue
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
  /// Shared with `PeopleThreadIngest` (which resolves counterpart names the same way).
  /// Request Contacts access once the user has opted into on-device message mapping, so iMessage-only
  /// 1:1 threads (phone numbers only) can be named and deep-ingested. Fire-and-forget: it prompts
  /// only when the status is undecided and never blocks the caller — the grant is applied on the next
  /// sync. A denial is a no-op (WhatsApp names and any existing grant still apply).
  static func requestContactsAccessIfNeeded() {
    guard UserDefaults.standard.bool(forKey: .peopleIMessageExport) else { return }
    guard CNContactStore.authorizationStatus(for: .contacts) == .notDetermined else { return }
    CNContactStore().requestAccess(for: .contacts) { _, _ in }
  }

  static func loadContactsByPhone() -> [String: String] {
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
