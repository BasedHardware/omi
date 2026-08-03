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
    // The prompt is raised here and **awaited before the naming pass**: fire-and-forget meant a
    // first run always beat the user's answer and labelled every iMessage person by phone number,
    // which then cost them every derived fact and every ingested thread. It is started in parallel
    // so it overlaps the (slow) message exports instead of serializing in front of them, and it
    // gives up after a bounded wait so an unanswered prompt can never stall the pipeline — a late
    // "Allow" re-runs the naming pass by itself. A denial is fine and terminal (WhatsApp names
    // still apply) and is surfaced to the UI instead of silently listing phone numbers.
    async let contactsAccess = PeopleContactsAccess.prepareForNaming(uid: uid)
    await IMessageExporter.exportIfRequested(force: force)
    // WhatsApp shares the single Full Disk Access grant and the same `peopleIMessageExport` consent
    // flag, so opting in to on-device message mapping re-reads it too. Own throttle; off-main.
    await WhatsAppReader.exportIfRequested(force: force)
    _ = await contactsAccess
    await rebuildIfNeeded(uid: uid, force: force)
    // Bind each on-device person card to the backend `Person` record segments and memories are
    // keyed by. Runs BEFORE the thread ingest so a uuid resolved now is stamped onto the segments
    // that ingest uploads moments later — which is what lets the backend attribute a 1:1 thread's
    // memories to that person instead of leaving the subject unknown. Own throttle; off-main.
    await PeopleIdentityBridge.resolveIfNeeded(uid: uid, force: force)
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

    // The durable `identity key → person id` table. Loaded BEFORE people are built so an id this
    // machine already assigned survives the contact being renamed, and re-saved after so newly
    // seen identities are anchored from now on.
    let links = PeopleIdentityStore.load(directory: userDir)

    // ---- 1. canonical people (dedupe by phone_last10, prefer a human name) ----
    let people = buildCanonicalPeople(root: root, contactsByPhone: contactsByPhone, links: links)
    // Only names a *source* asserted are durable. Recording every display name would write phone
    // numbers into the store as "names", and would launder a name merely read off an email address
    // into an asserted one on the next run — at which point the card would claim a `contactName`
    // nobody ever gave us.
    PeopleIdentityStore.record(
      identityKeys: people.identityKeysByID(), names: people.assertedNamesByID(), directory: userDir)

    // ---- 2. edges (size-normalized), circles, per-person connections ----
    let graph = buildGraph(root: root, people: people)

    // ---- 3. communities (named group chats → category) ----
    let communities = buildCommunities(root: root, people: people)

    // ---- 4. contact photos (already-granted Contacts only, thumbnails, unchanged ones skipped) ----
    let photoPaths = PeopleContactPhotos.syncFromContacts(idByPhone: people.idByPhone, userDir: userDir)

    // ---- 5. write outputs + create-or-merge ----
    writeSocial(graph: graph, to: userDir.appendingPathComponent("people_social.json"))
    writeCommunities(communities, to: userDir.appendingPathComponent("people_communities.json"))
    let peopleURL = userDir.appendingPathComponent("people_intelligence.json")
    // Which people's message history the deep ingest has actually submitted — the only honest
    // source for `history_grounded`.
    let ingestedPersonKeys = PeopleThreadIngest.ingestedPersonKeys(directory: userDir)
    if hasExistingPeople(at: peopleURL) {
      // A backend-written people file already exists: fold graph fields onto it, non-destructively.
      mergeIntoPeopleIntelligence(
        graph: graph, communities: communities, people: people,
        ingestedPersonKeys: ingestedPersonKeys, photoPaths: photoPaths, links: links, at: peopleURL)
    } else {
      // Fresh, backend-less user (file missing or its `people` array empty): CREATE the People
      // list from the on-device canonical people so the tab is populated with no backend at all.
      createPeopleIntelligence(
        graph: graph, communities: communities, people: people,
        ingestedPersonKeys: ingestedPersonKeys, photoPaths: photoPaths, links: links, at: peopleURL)
    }

    let selection = PeopleSelection.select(people: people, graph: graph, communities: communities)
    log(
      "PeopleGraphBuilder: \(selection.featured.count) people featured of \(selection.candidateCount) "
        + "candidates (dropped \(selection.countsByReason)), \(graph.edges.count) edges, "
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
      /// Messages **we** sent this person, and messages they sent us. `IMessageExporter` attributes
      /// an outbound 1:1 message to the chat's single participant and skips outbound group messages,
      /// so `sent > 0` is proof a one-to-one thread exists and the pair together prove the exchange
      /// was two-way. Absent for connectors that do not report direction (WhatsApp), which is why
      /// they are optional rather than zero — "unknown" and "none" must not read the same.
      let sent: Int?
      let received: Int?
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
        case sent
        case received
        case lastDate = "last_date"
      }

      init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        handle = (try? c.decode(String.self, forKey: .handle)) ?? ""
        phoneLast10 = try? c.decodeIfPresent(String.self, forKey: .phoneLast10)
        contactName = try? c.decodeIfPresent(String.self, forKey: .contactName)
        messageCount = (try? c.decode(Int.self, forKey: .messageCount)) ?? 0
        sent = try? c.decodeIfPresent(Int.self, forKey: .sent)
        received = try? c.decodeIfPresent(Int.self, forKey: .received)
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
    /// Which source produced `name`. `identified` says "a source asserted this"; this says *which*,
    /// and distinguishes "we read a name off the address" from "we have no name at all" — the
    /// difference between a card the selection stage can keep and one it drops.
    var nameSource: PersonNameSource = .handle
    /// Messages we sent them / they sent us, summed across connectors that report direction. Nil
    /// when no connector reported any, so "we never replied" is never inferred from silence.
    var sentCount: Int?
    var receivedCount: Int?
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

  /// Resolve every identity in the export(s) to a canonical person.
  ///
  /// `links` is the durable `identity key → person id` table (`people_identity.json`). It is what
  /// decouples a person's id from their display name: without it `slug(name)` *is* the identity,
  /// so renaming a contact mints a new person and silently detaches their saved override
  /// decisions, their `person:<id>` memory tags and their contact photo. Defaulting it to `.empty`
  /// reproduces the name-only behavior exactly, which is also what a first run sees.
  static func buildCanonicalPeople(
    root: ExportRoot, contactsByPhone: [String: String], links: PeopleIdentityLinks = .empty
  ) -> People {
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
    // Directional counts, summed only over connectors that actually report them, so an identity
    // seen only on a direction-less connector stays nil rather than looking like a silent contact.
    var direction: [String: (sent: Int, received: Int)] = [:]

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

    /// Fold one handle's reported direction into the identity's running totals.
    func addDirection(_ key: String, _ handle: ExportRoot.Handle) {
      guard handle.sent != nil || handle.received != nil else { return }
      var current = direction[key] ?? (sent: 0, received: 0)
      current.sent += max(handle.sent ?? 0, 0)
      current.received += max(handle.received ?? 0, 0)
      direction[key] = current
    }

    for h in root.handles {
      let msgs = max(h.messageCount, 0)
      if let ph = phoneKey(explicit: h.phoneLast10, handle: h.handle) {
        addDirection(ph, h)
        phoneMsg[ph, default: 0] += msgs
        phoneMsgCh[ph, default: [:]][h.channel, default: 0] += msgs
        if phoneSample[ph] == nil { phoneSample[ph] = h.handle }
        if let cn = nonEmpty(h.contactName), phoneContactName[ph] == nil { phoneContactName[ph] = cn }
        keepNewer(&phoneLast, ph, h.lastDate)
        keepNewerChannel(&phoneLastCh, ph, h.channel, h.lastDate)
      } else {
        let key = h.handle.lowercased()
        guard !key.isEmpty else { continue }
        addDirection(key, h)
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
      id: String, key: String, name: String, source: PersonNameSource, messages: Int, lastDate: String?,
      byChannel: [String: Int], lastByChannel: [String: String]
    ) {
      if var existing = people.canonByID[id] {
        existing.messageCount += messages
        // The strongest naming source across every identity key that resolved to this person wins.
        // (This used to read `identified = identified || new` and only *then* test `!identified`,
        // which is never true — so a WhatsApp name could never replace an iMessage phone-number
        // fallback on the same person.)
        if source > existing.nameSource {
          existing.nameSource = source
          existing.name = name
        }
        existing.identified = existing.nameSource.isAsserted
        if let d = nonEmpty(lastDate), existing.lastDate.map({ $0 < d }) ?? true {
          existing.lastDate = d
        }
        for (ch, count) in byChannel { existing.messagesByChannel[ch, default: 0] += count }
        for (ch, d) in lastByChannel where existing.lastByChannel[ch].map({ $0 < d }) ?? true {
          existing.lastByChannel[ch] = d
        }
        if let dir = direction[key] {
          existing.sentCount = (existing.sentCount ?? 0) + dir.sent
          existing.receivedCount = (existing.receivedCount ?? 0) + dir.received
        }
        people.canonByID[id] = existing
      } else {
        let dir = direction[key]
        people.canonByID[id] = Canon(
          id: id, name: name, messageCount: messages, identified: source.isAsserted,
          lastDate: nonEmpty(lastDate), messagesByChannel: byChannel, lastByChannel: lastByChannel,
          nameSource: source, sentCount: dir?.sent, receivedCount: dir?.received)
      }
      people.idName[id] = people.canonByID[id]?.name ?? name
    }

    // Resolve every identity key's display name first, then let the durable link table decide the
    // id. A freshly-slugged name is only the *default* identity — an id this machine already
    // assigned to the same phone/handle always wins, so a rename cannot mint a second person.
    //
    // Every naming source is exhausted here — address book, the connector's own name, a name this
    // machine resolved on an earlier run, then the address itself — because "unnamed" is the
    // strongest drop signal the selection stage has, and it must only fire after everything that
    // could have named this person has been tried.
    var namedByKey: [String: (name: String, source: PersonNameSource)] = [:]
    for ph in phoneMsg.keys.sorted() {
      namedByKey[ph] = PeopleNaming.resolve(
        key: ph, addressBook: contactsByPhone[ph], exportContact: phoneContactName[ph], links: links,
        fallback: phoneSample[ph] ?? ph)
    }
    for hh in emailMsg.keys.sorted() {
      namedByKey[hh] = PeopleNaming.resolve(
        key: hh, addressBook: nil, exportContact: emailContactName[hh], links: links,
        fallback: emailSample[hh] ?? hh)
    }
    let idByKey = PeopleIdentityLinks.stableIDs(
      nameIDByKey: namedByKey.mapValues { slug($0.name) }, links: links)

    // Deterministic assignment order keeps ids/output stable across runs.
    for ph in phoneMsg.keys.sorted() {
      let resolved = namedByKey[ph] ?? (name: ph, source: .handle)
      let id = idByKey[ph] ?? slug(resolved.name)
      upsert(
        id: id, key: ph, name: resolved.name, source: resolved.source, messages: phoneMsg[ph] ?? 0,
        lastDate: phoneLast[ph], byChannel: phoneMsgCh[ph] ?? [:], lastByChannel: phoneLastCh[ph] ?? [:])
      people.idByPhone[ph] = id
    }
    for hh in emailMsg.keys.sorted() {
      let resolved = namedByKey[hh] ?? (name: hh, source: .handle)
      let id = idByKey[hh] ?? slug(resolved.name)
      upsert(
        id: id, key: hh, name: resolved.name, source: resolved.source, messages: emailMsg[hh] ?? 0,
        lastDate: emailLast[hh], byChannel: emailMsgCh[hh] ?? [:], lastByChannel: emailLastCh[hh] ?? [:])
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
    /// Per person, how many groups they share with the user that the graph accepts as a group —
    /// 2…`maxGroup` resolved members. This is the one definition of "a real group" in the pipeline;
    /// the selection stage reads it so "shares a group with you" cannot come to mean something
    /// different there than it does for edges.
    var sharedGroupCountByID: [String: Int] = [:]
    /// The mirror image: groups too large to be relationships (a 591-member broadcast list). Kept
    /// so a dropped node can be explained as "only ever in broadcast groups" rather than "unknown".
    var broadcastGroupCountByID: [String: Int] = [:]
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
    var sharedGroupCountByID: [String: Int] = [:]
    var broadcastGroupCountByID: [String: Int] = [:]

    // Each shared group of resolved size m contributes 1/(m-1) to every member pair.
    for g in root.groups {
      var ids = Set<String>()
      for m in g.members {
        if let id = people.memberID(handle: m.handle, phoneLast10: m.phoneLast10) { ids.insert(id) }
      }
      let members = ids.sorted()
      let m = members.count
      // Record which side of the group ceiling every membership fell on before the edge guard drops
      // the oversized ones — that split is exactly what tells a shared group from a broadcast list.
      if m >= 2 {
        for id in members {
          if m <= maxGroup {
            sharedGroupCountByID[id, default: 0] += 1
          } else {
            broadcastGroupCountByID[id, default: 0] += 1
          }
        }
      }
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
    graph.sharedGroupCountByID = sharedGroupCountByID
    graph.broadcastGroupCountByID = broadcastGroupCountByID

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
        let sources = (edgeSrc[key].map { Array($0).sorted() }) ?? []
        let context = topLabels(edgeCtx[key] ?? [:], 4)
        var connection: [String: Any] = [
          "id": b,
          "name": people.name(b),
          "weight": round2(w),
          "sources": sources,
          "context": context,
        ]
        // Deterministic plain-English derivation of the edge (Phase 2). The model-backed
        // `type`/`confidence` on a connection stay absent — those are Phase 3.
        connection["how"] = PeopleIntelDerivation.connectionHow(context: context, sources: sources)
        return connection
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
  ///
  /// `ingestedPersonKeys` comes from `PeopleThreadIngest`'s ledger and is the only input that is
  /// not derived from the export itself; it decides `history_grounded`. Defaulting it to empty
  /// keeps the function callable (and testable) with graph inputs alone — an empty set simply
  /// means nobody's thread has been ingested yet.
  ///
  /// `photoPaths` is `person id -> on-device contact-photo path` from `PeopleContactPhotos`. It
  /// defaults to empty so graph-only callers (and tests) stay unchanged; an absent entry simply
  /// means that person has no contact photo, and the avatar falls back to initials.
  ///
  /// Every card also carries the identity the pipeline resolved it by:
  ///   - `handles` — the `phone_last10` / handle keys from `People.idByPhone` / `idByEmail`. These
  ///     already exist; writing them down is what lets anything downstream address this person
  ///     without re-slugging their display name.
  ///   - `personUUID` — the backend `Person` this identity is bridged to, from `links`
  ///     (`PeopleIdentityBridge` resolves it; the graph never blocks on the network to get one).
  /// `selection` decides which canonical nodes become cards at all (see `PeopleSelection`). Passing
  /// nil computes it from the same three inputs, so a caller can never accidentally get the
  /// unfiltered node dump: there is no "no selection" mode. Callers that already computed the
  /// outcome (to write its counts into `stats`) pass it in rather than paying for it twice.
  static func createPeople(
    people: People, graph: Graph, communities: Communities, ingestedPersonKeys: Set<String> = [],
    photoPaths: [String: String] = [:], links: PeopleIdentityLinks = .empty,
    selection: PeopleSelection.Outcome? = nil
  ) -> [[String: Any]] {
    let featured =
      (selection ?? PeopleSelection.select(people: people, graph: graph, communities: communities))
      .featuredIDs
    let identityKeys = people.identityKeysByID()
    // Deterministic Phase-2 enrichment, computed once for the whole list (the relationship tier is
    // a rank across everyone, so it cannot be computed per person in isolation).
    let relationships = PeopleIntelDerivation.relationshipLabels(people: people, communities: communities)
    let affiliations = PeopleIntelDerivation.affiliations(people: people, communities: communities)
    let grounded = PeopleIntelDerivation.historyGroundedIDs(
      people: people, ingestedPersonKeys: ingestedPersonKeys)

    return
      people.canonByID.values
      .filter { featured.contains($0.id) }
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
        // The identity keys this person was actually resolved by, and the backend Person they are
        // bridged to. Both are omitted rather than blanked when absent.
        let keys = identityKeys[id] ?? .none
        if !keys.isEmpty { person["handles"] = keys.json }
        if let uuid = links.personUUID(forPersonID: id) { person["personUUID"] = uuid }
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
        // The contact photo this run wrote, if any. The People UI reads the same folder by id, so
        // this is a shortcut, not a second source of truth.
        if let photo = photoPaths[id] { person["photoPath"] = photo }
        // Deterministic Phase-2 fields. Each is omitted rather than blanked when there is no
        // honest value, so "absent" always means "we could not tell" and never "we said no".
        if let relationship = relationships[id] { person["relationship"] = relationship }
        if let orgs = affiliations[id], !orgs.isEmpty {
          person["affiliations"] = orgs.map(\.json)
        }
        if grounded.contains(id) { person["history_grounded"] = true }
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
    graph: Graph, communities: Communities, people: People, ingestedPersonKeys: Set<String>,
    photoPaths: [String: String], links: PeopleIdentityLinks, at url: URL
  ) {
    let selection = PeopleSelection.select(people: people, graph: graph, communities: communities)
    let persons = createPeople(
      people: people, graph: graph, communities: communities, ingestedPersonKeys: ingestedPersonKeys,
      photoPaths: photoPaths, links: links, selection: selection)
    let overrides = PeopleOverridesStore.load(directory: url.deletingLastPathComponent())
    let result = annotateAndReview(persons: persons, overrides: overrides)
    let doc: [String: Any] = [
      "generated_at": isoNow(),
      "stats": statsBlock(finalPeople: result.people, selection: selection),
      "people": result.people,
      "reviewQueue": result.reviewQueue,
      // Plain-English gloss per shared group chat, rendered under "Shared groups" on a profile.
      "community_meanings": PeopleIntelDerivation.communityMeanings(communities),
    ]
    writeJSON(doc, to: url)
  }

  /// The file's `stats` block. `featured` / `dropped` are the two halves of the selection stage and
  /// always sum to the number of canonical nodes it judged — that is what lets the UI say "you know
  /// 315 people" instead of quietly hiding 1,510 of them. `people` can be *below* `featured` when
  /// the user has confirmed two cards are the same person, which merges them after selection.
  static func statsBlock(
    finalPeople: [[String: Any]], selection: PeopleSelection.Outcome
  ) -> [String: Any] {
    let multichannel = finalPeople.filter { (($0["channels"] as? [[String: Any]])?.count ?? 0) > 1 }
      .count
    let channelKeys = Set(
      finalPeople.flatMap {
        ($0["channels"] as? [[String: Any]] ?? []).compactMap { $0["key"] as? String }
      })
    return [
      "people": finalPeople.count,
      "multichannel": multichannel,
      "channels": channelKeys.count,
      "featured": selection.featured.count,
      "dropped": selection.drops.count,
      "dropped_reasons": selection.countsByReason,
    ]
  }

  /// Non-destructively fold `connections` / `circle` / `groups` onto the matching person in an
  /// existing `people_intelligence.json`. Uses `JSONSerialization` (not a rigid Codable model)
  /// so every field the backend wrote is preserved untouched. Internal (not private) so the
  /// non-destructive contract is covered by a real test against a real file rather than by review.
  /// People are matched by id equality
  /// first, then by normalized name / contactName / alias.
  ///
  /// Selection binds this path in both directions:
  ///   - a node the selection stage **dropped** is never written into the file, so a person hidden
  ///     on the create path cannot reappear through the merge path;
  ///   - a card already in the file is **never removed**, whatever this run decided. A person the
  ///     user has seen (and possibly corrected, tagged or bridged) does not silently vanish because
  ///     an export went quiet.
  /// Newly selected people with no matching card are appended, which is what lets the list grow
  /// after the first run — before this, only the create path ever added anyone, and it runs once.
  static func mergeIntoPeopleIntelligence(
    graph: Graph, communities: Communities, people: People, ingestedPersonKeys: Set<String>,
    photoPaths: [String: String] = [:], links: PeopleIdentityLinks = .empty, at url: URL
  ) {
    guard let data = try? Data(contentsOf: url),
      let obj = try? JSONSerialization.jsonObject(with: data),
      var doc = obj as? [String: Any],
      var persons = doc["people"] as? [[String: Any]]
    else { return }

    let selection = PeopleSelection.select(people: people, graph: graph, communities: communities)
    var unmatchedFeatured = selection.featuredIDs
    let identityKeys = people.identityKeysByID()
    let relationships = PeopleIntelDerivation.relationshipLabels(people: people, communities: communities)
    let affiliations = PeopleIntelDerivation.affiliations(people: people, communities: communities)
    let grounded = PeopleIntelDerivation.historyGroundedIDs(
      people: people, ingestedPersonKeys: ingestedPersonKeys)

    var nameToID: [String: String] = [:]
    for id in people.canonByID.keys.sorted() {
      guard let name = people.canonByID[id]?.name else { continue }
      let k = norm(name)
      if nameToID[k] == nil { nameToID[k] = id }
    }

    for i in persons.indices {
      var p = persons[i]
      var matched: String?
      // An id this run actually resolved is an exact identity match, whether or not the graph
      // produced edges for them — otherwise a card with no shared groups could only ever be
      // matched by its display name, which is the failure this change exists to remove.
      if let pid = p["id"] as? String,
        people.canonByID[pid] != nil || graph.connectionsByID[pid] != nil
          || graph.circleChipByID[pid] != nil || communities.groupsByPersonID[pid] != nil
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
        unmatchedFeatured.remove(id)
        if let conns = graph.connectionsByID[id] { p["connections"] = conns }
        if let chip = graph.circleChipByID[id] { p["circle"] = chip }
        if let gs = communities.groupsByPersonID[id] { p["groups"] = gs }
        // Deterministic Phase-2 fields FILL IN, they do not overwrite: a richer value already on
        // the card (a model-written relationship, a curated affiliation list) always wins over a
        // rank-and-category restatement. `history_grounded` only ever goes false → true.
        if (p["relationship"] as? String)?.trimmingCharacters(in: .whitespaces).isEmpty ?? true,
          let relationship = relationships[id]
        {
          p["relationship"] = relationship
        }
        if (p["affiliations"] as? [[String: Any]])?.isEmpty ?? true, let orgs = affiliations[id],
          !orgs.isEmpty
        {
          p["affiliations"] = orgs.map(\.json)
        }
        if grounded.contains(id) { p["history_grounded"] = true }
        // Same fill-in rule for the avatar: a photo the backend already provided always wins.
        if p["photoPath"] as? String == nil, let photo = photoPaths[id] { p["photoPath"] = photo }
        // Identity keys UNION rather than replace — gaining a WhatsApp handle must add a key, not
        // discard the iMessage one a previous run recorded. `personUUID` is fill-in only: a card
        // already bridged to a backend Person is never repointed at a second one.
        let resolvedKeys = identityKeys[id] ?? .none
        if !resolvedKeys.isEmpty {
          let merged = PersonIdentityKeys.from(json: p["handles"]).union(resolvedKeys)
          p["handles"] = merged.json
        }
        if (p["personUUID"] as? String)?.isEmpty ?? true, let uuid = links.personUUID(forPersonID: id) {
          p["personUUID"] = uuid
        }
      }
      persons[i] = p
    }

    // Append the people this run selected that no existing card accounts for. Built by the same
    // `createPeople` the create path uses, then filtered to the unmatched ids — so an appended card
    // is identical in shape to a created one, and a dropped node can never be among them.
    if !unmatchedFeatured.isEmpty {
      let fresh = createPeople(
        people: people, graph: graph, communities: communities, ingestedPersonKeys: ingestedPersonKeys,
        photoPaths: photoPaths, links: links, selection: selection)
      persons += fresh.filter { unmatchedFeatured.contains(($0["id"] as? String) ?? "") }
    }

    // Same fill-in rule for the file-level group glossary: an existing meaning is never replaced.
    var meanings = (doc["community_meanings"] as? [String: String]) ?? [:]
    for (name, meaning) in PeopleIntelDerivation.communityMeanings(communities)
    where (meanings[name]?.isEmpty ?? true) {
      meanings[name] = meaning
    }
    if !meanings.isEmpty { doc["community_meanings"] = meanings }

    // Flag weak-signal identities/facts and fold the user's saved corrections in (user truth wins)
    // before persisting, so a backend-written card is never surfaced as certain when it isn't.
    let overrides = PeopleOverridesStore.load(directory: url.deletingLastPathComponent())
    let result = annotateAndReview(persons: persons, overrides: overrides)
    doc["people"] = result.people
    doc["reviewQueue"] = result.reviewQueue
    // The merge path used to leave `stats` exactly as it found it, so a file seeded once kept
    // reporting that first run's counts forever. Recomputed here for the same reason it is written
    // on the create path: the header must describe the list the user is looking at.
    doc["stats"] = statsBlock(finalPeople: result.people, selection: selection)
    writeJSON(doc, to: url)
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

  /// The user allowed Contacts *after* a run had already labelled iMessage people by phone number
  /// (`PeopleContactsAccess.prepareForNaming` stopped waiting). Re-runs only the naming-dependent
  /// stages, forced past their throttles, so the names, facts and photos appear without waiting for
  /// the next sync window. The message exports are deliberately not re-run — the on-disk export is
  /// already current — and the rate-limited thread ingest keeps its own throttle. This never
  /// prompts, so it cannot loop.
  static func renameAfterContactsGrant(uid: String?) async {
    await rebuildIfNeeded(uid: uid, force: true)
    // Names only just became resolvable, so cards that had nothing but a phone number now carry a
    // human name and can finally be bridged to a backend Person.
    await PeopleIdentityBridge.resolveIfNeeded(uid: uid, force: true)
    await PeopleMemoryWriter.writeIfNeeded(uid: uid, force: true)
    await PeopleThreadIngest.ingestIfNeeded(uid: uid, force: false)
  }

  /// Builds a `phone_last10 → display name` map from the local Contacts store, but **only** when
  /// access is already granted. Status is checked explicitly so this never triggers a TCC prompt —
  /// `PeopleContactsAccess` owns the one prompt. Shared with `PeopleThreadIngest` (which resolves
  /// counterpart names the same way).
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
  /// Internal (not private) so `PeopleContactPhotos` keys contact phone numbers exactly the way
  /// `People.idByPhone` is keyed — two normalizers would silently drop photos.
  static func last10(_ s: String?) -> String? {
    guard let s, !s.contains("@") else { return nil }
    let digits = s.filter { $0.isNumber }
    guard digits.count >= 10 else { return nil }
    return String(digits.suffix(10))
  }

  /// Internal (not private) because `PeopleReviewAnnotation` matches names with the same rule; two
  /// normalizers would silently split people the merge path is meant to join.
  static func norm(_ s: String?) -> String {
    let lowered = (s ?? "").lowercased()
    return lowered.split(whereSeparator: { $0.isWhitespace }).joined(separator: " ")
  }

  static func slug(_ n: String) -> String {
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
