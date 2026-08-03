import Foundation

/// Phase-2 of `desktop/macos/docs/people-intelligence-productization.md`: the **deterministic**
/// per-person fields the People tab renders, derived entirely from data the on-device engine
/// already holds in memory (`PeopleGraphBuilder.People` / `.Graph` / `.Communities`).
///
/// No model. No network. Every value here is a mechanical restatement of a signal that is already
/// on disk, which is what makes it safe to ship to every user:
///
///   - `affiliations`   — organizations, from email domains and recurring group-chat name tokens
///   - `relationship`   — a short reach/context label ("close · work")
///   - `community_meanings` — plain-English gloss for a group chat's inferred category
///   - `connections[].how` — how a "knows" edge was actually derived
///   - `history_grounded`  — whether `PeopleThreadIngest` really ingested that person's thread
///
/// The model-backed Phase-3 fields (`who` / `now` / `overall` / `facts` / `activities` /
/// `openThreads` / `connections[].type` / `network_insights`) are deliberately **not** produced
/// here. A deterministic stand-in for a narrative is a fabricated narrative, so those keys stay
/// absent and the profile renders its honest "Not much yet" state instead.
///
/// Conservatism is the operating rule throughout: when a signal is ambiguous this emits *nothing*
/// rather than a plausible-looking guess. A wrong employer on somebody's profile is a much worse
/// failure than a blank field.
enum PeopleIntelDerivation {

  // MARK: - Tunables (documented so a reader can audit every threshold)

  /// A group-chat name is only read as an organization when the chat has at least this many known
  /// members. Below it, the "group" is effectively a small thread and its name is not org evidence.
  static let minKnownMembersForOrgGroup = 3
  /// …and at most this many. Above it the chat is a broadcast community (a 591-member "Cold Email
  /// Club", a 247-member friends list): being in one says nothing about where you work. Mirrors
  /// `PeopleGraphBuilder.maxGroup`, which drops the same chats when it builds edges.
  static let maxKnownMembersForOrgGroup = 60
  /// Distinct group chats a token has to appear in before it is treated as an organization at all.
  /// Measured on a real 149-chat export: at three, the survivors were exactly the five real orgs;
  /// dropping to two additionally admitted `spring`, `sf`, `events`, `hires` and `vc` — season and
  /// role words that are not organizations.
  static let minChatsToEstablishOrg = 3
  /// Most affiliations shown per person. The profile header renders the first and the Overview tab
  /// the rest; beyond three this reads as a dump rather than an identity.
  static let maxAffiliationsPerPerson = 3
  /// Chats cited as evidence for one affiliation. An organization with 29 chats does not need 29
  /// lines of proof, and the profile renders `via` verbatim.
  static let maxEvidencePerAffiliation = 3
  /// Absolute message floors. Percentile rank alone is degenerate on a small graph (with three
  /// contacts the top 10% is one person), so a tier also has to clear a real volume of messages.
  static let closeMessageFloor = 50
  static let regularMessageFloor = 10
  /// Absolute bands, used when they are *kinder* than the percentile band, so a heavily-messaged
  /// person in a huge address book is still labelled honestly.
  static let closeMessageAbsolute = 300
  static let regularMessageAbsolute = 60

  // MARK: - Relationship label

  /// Short, deterministic relationship label per person id, e.g. `"close · work"`.
  ///
  /// Two segments, either of which may be absent:
  ///
  /// 1. **Reach tier** from how much you actually message them — `close` / `regular` /
  ///    `occasional`, or `group contact` for somebody who only ever appears inside your group
  ///    chats. The tier is the better of a percentile rank (top 10% / top 35% of everyone you
  ///    message) and an absolute band, and is floored so a "close" label always means real volume.
  ///    Being reachable on two connectors (iMessage *and* WhatsApp) promotes one tier — a person
  ///    you keep up with across two independent apps is genuinely closer than one channel shows.
  /// 2. **Context** from the dominant category of the group chats you share — `work`, `family`,
  ///    `household`, `friends`. Categories that describe an occasion rather than a relationship
  ///    (`trip / event`) and the categorizer's own unknown bucket (`social`) map to nothing.
  ///
  /// This is intentionally telegraphic. It must never read like a sentence a model wrote, because
  /// no model wrote it — it is a rank and a category, joined by a separator.
  static func relationshipLabels(
    people: PeopleGraphBuilder.People, communities: PeopleGraphBuilder.Communities
  ) -> [String: String] {
    let counts = people.canonByID.values.map(\.messageCount).filter { $0 > 0 }.sorted(by: >)
    // Score at (or above) which a person is inside the top X% of everyone you message.
    func floorAtPercentile(_ fraction: Double) -> Int? {
      guard !counts.isEmpty else { return nil }
      let rank = max(1, Int((Double(counts.count) * fraction).rounded(.up)))
      return counts[min(rank, counts.count) - 1]
    }
    let closeCut = floorAtPercentile(0.10)
    let regularCut = floorAtPercentile(0.35)

    var out: [String: String] = [:]
    for (id, canon) in people.canonByID {
      let groups = communities.groupsByPersonID[id] ?? []
      let context = dominantContext(groups: groups)
      let tier = reachTier(
        messages: canon.messageCount,
        channels: canon.messagesByChannel.keys.count,
        inAnyGroup: !groups.isEmpty,
        closeCut: closeCut,
        regularCut: regularCut)
      let label = [tier, context].compactMap { $0 }.joined(separator: " · ")
      if !label.isEmpty { out[id] = label }
    }
    return out
  }

  private static func reachTier(
    messages: Int, channels: Int, inAnyGroup: Bool, closeCut: Int?, regularCut: Int?
  ) -> String? {
    guard messages > 0 else {
      // No direct message ever exchanged: they exist because you share a group chat. Say exactly
      // that instead of implying a level of contact that never happened.
      return inAnyGroup ? "group contact" : nil
    }
    var rank = 0  // 0 = occasional, 1 = regular, 2 = close
    if let regularCut, messages >= regularCut { rank = 1 }
    if let closeCut, messages >= closeCut { rank = 2 }
    if messages >= regularMessageAbsolute { rank = max(rank, 1) }
    if messages >= closeMessageAbsolute { rank = max(rank, 2) }
    if channels >= 2 { rank = min(rank + 1, 2) }
    if rank == 2, messages < closeMessageFloor { rank = 1 }
    if rank == 1, messages < regularMessageFloor { rank = 0 }
    switch rank {
    case 2: return "close"
    case 1: return "regular"
    default: return "occasional"
    }
  }

  /// Category → relationship word. `trip / event` describes an occasion, not a relationship, and
  /// `social` is the categorizer's fallback for "we could not tell" — both map to nothing rather
  /// than asserting a category we did not actually infer.
  private static func contextWord(forCategory category: String) -> String? {
    switch category {
    case "work / venture": return "work"
    case "family": return "family"
    case "household": return "household"
    case "friends / social": return "friends"
    default: return nil
    }
  }

  /// Fixed precedence so ties resolve identically on every run.
  private static let contextPriority = ["work", "family", "household", "friends"]

  private static func dominantContext(groups: [[String: Any]]) -> String? {
    var tally: [String: Int] = [:]
    for group in groups {
      guard let category = group["category"] as? String,
        let word = contextWord(forCategory: category)
      else { continue }
      tally[word, default: 0] += 1
    }
    guard !tally.isEmpty else { return nil }
    return tally.max { lhs, rhs in
      if lhs.value != rhs.value { return lhs.value < rhs.value }
      let li = contextPriority.firstIndex(of: lhs.key) ?? contextPriority.count
      let ri = contextPriority.firstIndex(of: rhs.key) ?? contextPriority.count
      return li > ri
    }?.key
  }

  // MARK: - Affiliations

  /// One inferred organization plus the evidence that produced it.
  struct Affiliation: Equatable, Sendable {
    let name: String
    /// Matches the `type` key `PersonAffiliation` decodes: `company`, `school`, `organization`.
    let kind: String
    let confidence: Double
    /// Human-readable evidence, e.g. `"group chat: Acme Team"` / `"email: @acme.com"`.
    let via: [String]

    var json: [String: Any] {
      ["name": name, "type": kind, "confidence": confidence, "via": via]
    }
  }

  /// One organization the graph's own chat names establish, plus the chats that established it.
  struct Organization: Equatable, Sendable {
    /// Comparison key (`orgKey`), e.g. `"breakout"`.
    let key: String
    /// The spelling to show, taken from how the user actually types it: `"BreakOut"`.
    let display: String
    /// Every qualifying chat whose name bears this token, sorted.
    let chats: [String]
    /// The subset of `chats` the organization *owns* — the chat is named after it (`"GLO OPS"`),
    /// rather than merely mentioning it alongside another party (`"Compass >< GLO"`).
    let ownChats: Set<String>
  }

  /// `Organization`s keyed by `orgKey`, plus the per-chat membership used to derive them.
  struct OrganizationIndex: Sendable {
    var organizations: [String: Organization] = [:]
    var membersByChat: [String: Set<String>] = [:]
  }

  /// Names that describe a home, a family or an occasion rather than an organization. A token whose
  /// chats are mostly these is a place or a trip ("Crib", "Tahoe"), never an employer.
  private static let personalCategories: Set<String> = ["family", "household", "trip / event"]

  /// Punctuation people use to name a chat that spans two parties: `"Compass >< GLO"`.
  private static let bridgeMarkers = ["><", "<>", "<->", "|"]

  /// The organizations this graph's group-chat names actually establish.
  ///
  /// **The problem this solves.** Affiliation used to require an email domain to corroborate a
  /// group name. Real message exports carry phone handles and almost no email, so on a 1,825-person
  /// export the email leg fired for one person and the whole feature produced zero affiliations.
  /// Corroboration therefore has to come from the chat names themselves — but a *single* work-ish
  /// chat name is not evidence, because the categorizer keys off loose words (`gang`, `class`,
  /// `meat`, `sage`), and `"meat gang"` must never become an employer called "Meat Gang".
  ///
  /// **The rule.** A word is an organization only when four independent things agree:
  ///
  ///  1. **Recurrence** — it appears in at least `minChatsToEstablishOrg` (3) distinct group-chat
  ///     names. One chat is a name; three chats is a thing people organize around. `"meat"` appears
  ///     in exactly one chat on the measured export, so the trap word never clears this on its own.
  ///  2. **Membership overlap** — at least one person is in two of those chats, so they are one
  ///     cluster rather than three unrelated groups that happen to share a word.
  ///  3. **Category agreement** — the chats are not mostly `family` / `household` / `trip / event`.
  ///     This is what stops `"Crib"` (three household chats) from becoming an organization.
  ///  4. **Token shape** — the word is not a generic group word (`team`, `gang`, `class`, `ops`), not
  ///     a date or cohort code (anything containing a digit: `S26`, `F25`, `2024`), and **not the
  ///     name of anybody in the graph**. That last one matters most: on the measured export the
  ///     single most recurrent token was the user's own first name (17 chats), and several contacts'
  ///     first names recurred too. An organization is not a person you know.
  ///
  /// The cost of (4) is that a real org sharing a contact's name is dropped. That is the correct
  /// direction: a missing affiliation is a blank field, a wrong one is a lie about somebody's job.
  static func organizations(
    people: PeopleGraphBuilder.People, communities: PeopleGraphBuilder.Communities
  ) -> OrganizationIndex {
    let nameTokens = personNameTokens(people)

    var index = OrganizationIndex()
    var categoryByChat: [String: String] = [:]
    var wordsByChat: [String: [String]] = [:]
    for community in communities.list {
      guard
        let name = (community["name"] as? String)?
          .trimmingCharacters(in: .whitespacesAndNewlines), !name.isEmpty,
        let members = community["known_members"] as? [[String: Any]],
        (minKnownMembersForOrgGroup...maxKnownMembersForOrgGroup).contains(members.count)
      else { continue }
      index.membersByChat[name, default: []].formUnion(members.compactMap { $0["id"] as? String })
      // `list` is ordered by known-membership descending, so the first sighting of a name is its
      // richest one; a same-named chat on the other connector must not overwrite it.
      if categoryByChat[name] == nil {
        categoryByChat[name] = (community["category"] as? String) ?? "social"
        wordsByChat[name] = identityWords(inGroupName: name, excludingNames: nameTokens)
      }
    }

    var chatsByToken: [String: Set<String>] = [:]
    var spellingsByToken: [String: [String: Int]] = [:]
    for (name, words) in wordsByChat {
      var seen: Set<String> = []
      for word in words {
        let key = orgKey(word)
        guard !key.isEmpty, seen.insert(key).inserted else { continue }
        chatsByToken[key, default: []].insert(name)
        spellingsByToken[key, default: [:]][word, default: 0] += 1
      }
    }

    for (key, chats) in chatsByToken where chats.count >= minChatsToEstablishOrg {
      let personal = chats.filter { personalCategories.contains(categoryByChat[$0] ?? "") }.count
      guard personal * 2 <= chats.count else { continue }
      var appearances: [String: Int] = [:]
      for chat in chats {
        for id in index.membersByChat[chat] ?? [] { appearances[id, default: 0] += 1 }
      }
      guard appearances.values.contains(where: { $0 >= 2 }) else { continue }
      guard let display = dominantSpelling(spellingsByToken[key] ?? [:]) else { continue }
      index.organizations[key] = Organization(
        key: key, display: display, chats: chats.sorted(), ownChats: [])
    }

    // Second pass: which chats each organization *owns*. Needs the full establish set, because a
    // chat naming two established organizations is a chat between them and belongs to neither.
    let established = index.organizations
    for (key, org) in established {
      let owned = org.chats.filter { chat in
        guard !bridgeMarkers.contains(where: { chat.contains($0) }) else { return false }
        let words = wordsByChat[chat] ?? []
        let named = Set(words.map(orgKey).filter { established[$0] != nil })
        guard named.count < 2 else { return false }
        // "GLO OPS" / "AV Tech Team": the organization leads, the rest is the sub-team. When it
        // trails other identity words ("Roundtable VC 👑 GLO") the chat names a second party the
        // graph has not established, so its members are not necessarily this organization's.
        return orgKey(words.first ?? "") == key
      }
      index.organizations[key] = Organization(
        key: org.key, display: org.display, chats: org.chats, ownChats: Set(owned))
    }
    return index
  }

  /// Every letter-token of every name in the graph, for the "an organization is not a person you
  /// know" filter. An email used as a display name contributes its local part only — the domain of
  /// `matt@molinar.ai` is the company, not the person.
  private static func personNameTokens(_ people: PeopleGraphBuilder.People) -> Set<String> {
    var out: Set<String> = []
    for name in people.idName.values {
      let local = name.split(separator: "@", omittingEmptySubsequences: false).first.map(String.init) ?? name
      for token in local.lowercased().split(whereSeparator: { !$0.isLetter }) where token.count >= 3 {
        out.insert(String(token))
      }
    }
    return out
  }

  /// Most-used spelling, ties broken lexicographically so a rebuild never renames an organization.
  private static func dominantSpelling(_ counts: [String: Int]) -> String? {
    counts.max { lhs, rhs in
      lhs.value != rhs.value ? lhs.value < rhs.value : lhs.key > rhs.key
    }?.key
  }

  /// Organizations per person id, from two independent deterministic signals.
  ///
  /// **Email domain (direct).** A non-consumer domain on a handle you actually exchange messages
  /// with is the person telling you where they are. `stanford.edu` → school, everything else →
  /// company. A domain nobody else shares scores lower (0.5) than one two or more of your contacts
  /// share (0.8), because the second holder is what distinguishes a real org from a personal
  /// domain. A domain that merely echoes the person's own name is dropped outright as a vanity
  /// domain.
  ///
  /// **Recurring chat-name organization (indirect, always corroborated).** `organizations(…)` first
  /// establishes that an organization exists at all, from recurrence + membership overlap + category
  /// agreement + token shape. Attaching a *person* to it then needs its own evidence, because the
  /// single biggest false-positive class is the two-party chat: `"Compass >< GLO"` contains Compass
  /// people and GLO people, and calling everybody in it a GLO employee is exactly the wrong answer.
  /// So a person is affiliated only when:
  ///
  ///   - they are in **two or more** chats bearing the organization (0.7, or 0.8 at three or more) —
  ///     across two-party chats the counterparty changes every time and only the organization's own
  ///     people recur; or
  ///   - they are in a chat the organization **owns** — named after it, no second party (0.55).
  ///
  /// When the email and the chat names agree the two merge into one entry at 0.85.
  static func affiliations(
    people: PeopleGraphBuilder.People, communities: PeopleGraphBuilder.Communities
  ) -> [String: [Affiliation]] {
    // ---- 1. email-domain organizations ----
    var domainHolders: [String: Set<String>] = [:]  // domain -> person ids
    var domainsByPerson: [String: Set<String>] = [:]
    for (handle, personID) in people.idByEmail {
      guard let domain = mailDomain(handle), !consumerMailDomains.contains(domain) else { continue }
      guard let label = registrableLabel(domain), !isVanityDomain(label, forName: people.name(personID))
      else { continue }
      domainHolders[domain, default: []].insert(personID)
      domainsByPerson[personID, default: []].insert(domain)
    }
    // organization key -> the domain that produced it, for cross-checking group names.
    var domainByOrgKey: [String: String] = [:]
    var orgKeyHolders: [String: Set<String>] = [:]
    for (domain, holders) in domainHolders {
      guard let label = registrableLabel(domain) else { continue }
      let key = orgKey(label)
      guard !key.isEmpty else { continue }
      if domainByOrgKey[key] == nil { domainByOrgKey[key] = domain }
      orgKeyHolders[key, default: []].formUnion(holders)
    }

    // ---- 2. recurring organization tokens across group-chat names ----
    let index = organizations(people: people, communities: communities)
    // person id -> org key -> (confidence, cited chats)
    var groupOrgs: [String: [String: (confidence: Double, chats: [String])]] = [:]
    for (key, org) in index.organizations {
      var chatsByMember: [String: [String]] = [:]
      for chat in org.chats {
        for id in index.membersByChat[chat] ?? [] { chatsByMember[id, default: []].append(chat) }
      }
      for (memberID, chats) in chatsByMember {
        let owned = chats.filter { org.ownChats.contains($0) }
        let confidence: Double
        var cited: [String]
        if chats.count >= 2 {
          confidence = chats.count >= 3 ? 0.8 : 0.7
          // Chats the organization owns are the clearest evidence, so cite those first.
          cited = owned.sorted() + chats.filter { !org.ownChats.contains($0) }.sorted()
        } else if !owned.isEmpty {
          confidence = 0.55
          cited = owned.sorted()
        } else {
          // In exactly one chat, and that chat names a second party too — no affiliation.
          continue
        }
        cited = Array(cited.prefix(maxEvidencePerAffiliation))
        groupOrgs[memberID, default: [:]][key] = (confidence, cited)
      }
    }

    // ---- 3. merge per person ----
    var out: [String: [Affiliation]] = [:]
    let allPersonIDs = Set(domainsByPerson.keys).union(groupOrgs.keys)
    for personID in allPersonIDs {
      var byKey: [String: Affiliation] = [:]

      for domain in (domainsByPerson[personID] ?? []).sorted() {
        guard let label = registrableLabel(domain) else { continue }
        let key = orgKey(label)
        guard !key.isEmpty else { continue }
        let shared = (orgKeyHolders[key]?.count ?? 1) >= 2
        // A domain only one contact holds has no corroboration at all, so it also has to *look*
        // like a brand. Two of the three non-consumer domains in a real 1,825-person address book
        // were spam senders with machine-generated hostnames; without this they became companies
        // named "Xrbru" and "Yxzvwggct" on somebody's profile.
        guard shared || !isMachineGenerated(label) else { continue }
        byKey[key] = Affiliation(
          name: displayName(fromDomainLabel: label),
          kind: isAcademic(domain) ? "school" : "company",
          confidence: shared ? 0.8 : 0.5,
          via: ["email: @\(domain)"])
      }

      for (key, evidence) in groupOrgs[personID] ?? [:] {
        let cited = evidence.chats.map { "group chat: \($0)" }
        if let existing = byKey[key] {
          // The email and the chat names agree — independent signals, so the entry gets stronger.
          byKey[key] = Affiliation(
            name: existing.name, kind: existing.kind,
            confidence: max(existing.confidence, 0.85),
            via: existing.via + cited)
        } else {
          guard let display = index.organizations[key]?.display else { continue }
          byKey[key] = Affiliation(
            name: display, kind: "organization", confidence: evidence.confidence, via: cited)
        }
      }

      let sorted = byKey.values.sorted {
        $0.confidence != $1.confidence ? $0.confidence > $1.confidence : $0.name < $1.name
      }
      if !sorted.isEmpty { out[personID] = Array(sorted.prefix(maxAffiliationsPerPerson)) }
    }
    return out
  }

  // MARK: - Community meanings

  /// Plain-English gloss per group-chat name, for the `community_meanings` map the profile page
  /// renders under each shared group. Purely a restatement of the categorizer's own output plus
  /// membership counts — the group's inferred kind, the connector it lives on, and how much of it
  /// you actually know.
  ///
  /// The categorizer's `social` bucket is its "we could not tell" fallback, and on a real 149-chat
  /// export it swallowed 111 of them — so requiring a category meant three quarters of the user's
  /// groups rendered as a bare name with nothing under it. The fix is to stop conflating the two
  /// claims: the **category** is asserted only when the categorizer actually made one, while the
  /// **connector and membership** are facts about every chat and are always stated. An unclassified
  /// group reads "A group chat on WhatsApp — 4 people you know." — which reports no categorization
  /// that never happened, and still tells the reader something they did not know.
  static func communityMeanings(_ communities: PeopleGraphBuilder.Communities) -> [String: String] {
    var out: [String: String] = [:]
    for community in communities.list {
      guard let name = community["name"] as? String, !name.isEmpty else { continue }
      let known = (community["known_members"] as? [[String: Any]])?.count ?? 0
      guard known > 0 else { continue }
      // `list` is ordered by known-membership descending, so the first entry for a name is the
      // richest; a same-named chat on the other connector must not overwrite it with a smaller one.
      guard out[name] == nil else { continue }
      let total = (community["size_total"] as? Int) ?? known
      let channel = PeopleGraphBuilder.channelLabel((community["channel"] as? String) ?? "imessage")
      let membership =
        total > known
        ? "\(known) of its \(total) members are people you know"
        : "\(known) \(known == 1 ? "person" : "people") you know"
      let phrase = categoryPhrase((community["category"] as? String) ?? "") ?? "A group chat"
      out[name] = "\(phrase) on \(channel) — \(membership)."
    }
    return out
  }

  private static func categoryPhrase(_ category: String) -> String? {
    switch category {
    case "work / venture": return "A work group chat"
    case "household": return "A household group chat"
    case "trip / event": return "A trip or event group chat"
    case "family": return "A family group chat"
    case "friends / social": return "A friends group chat"
    default: return nil  // "social" is the unknown bucket — say nothing.
    }
  }

  // MARK: - Connection derivation ("how")

  /// Plain-English derivation for a "knows" edge, from the shared-group context and channel
  /// provenance `buildGraph` already computed.
  ///
  /// Every edge in this engine comes from **shared group membership** — there is no 1:1
  /// co-occurrence signal on device — so the text always says so. Notably it never claims
  /// "frequent 1:1 messaging, no shared group chat" (the phrasing in the out-of-tree prototype's
  /// files): that sentence describes a signal this pipeline does not compute, so emitting it would
  /// be a fabrication. An edge with no named context came from a group chat nobody named, and is
  /// described as exactly that.
  ///
  /// The connector is named only when the pair co-occurs on **two** connectors, which is real
  /// corroboration; naming it for a single connector is noise.
  static func connectionHow(context: [String], sources: [String]) -> String {
    let named = context.map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }.filter { !$0.isEmpty }
    let channels = sources.filter { !$0.isEmpty }.map(PeopleGraphBuilder.channelLabel)
    let suffix = channels.count >= 2 ? ", on \(joinList(channels))" : ""
    switch named.count {
    case 0:
      // A single connector reads better inline than as a trailing clause.
      let single = channels.count == 1 ? "\(channels[0]) " : ""
      return "In an unnamed shared \(single)group chat\(suffix)"
    case 1:
      return "Both in \(named[0])\(suffix)"
    case 2:
      return "Both in \(named[0]) and \(named[1])\(suffix)"
    default:
      return "Both in \(named[0]), \(named[1]), and other shared group chats\(suffix)"
    }
  }

  private static func joinList(_ items: [String]) -> String {
    switch items.count {
    case 0: return ""
    case 1: return items[0]
    case 2: return "\(items[0]) and \(items[1])"
    default: return items.dropLast().joined(separator: ", ") + ", and " + (items.last ?? "")
    }
  }

  // MARK: - history_grounded

  /// Person ids whose 1:1 thread `PeopleThreadIngest` has actually submitted at least once.
  ///
  /// The ingest keys its ledger by a stable per-person key (`phone_last10`, or `wa:` + that for
  /// WhatsApp), so a canonical person is "grounded" when any phone identity resolving to them
  /// appears in the ledger's ingested set. A ledger written before that set existed contributes
  /// nothing, which reads as "not grounded" — the conservative direction.
  static func historyGroundedIDs(
    people: PeopleGraphBuilder.People, ingestedPersonKeys: Set<String>
  ) -> Set<String> {
    guard !ingestedPersonKeys.isEmpty else { return [] }
    var out: Set<String> = []
    for (phone, personID) in people.idByPhone
    where ingestedPersonKeys.contains(phone) || ingestedPersonKeys.contains("wa:" + phone) {
      out.insert(personID)
    }
    return out
  }

  // MARK: - Organization-name helpers

  /// Free/consumer mailbox providers. An address here says nothing about where somebody works.
  private static let consumerMailDomains: Set<String> = [
    "aol.com", "att.net", "bellsouth.net", "btinternet.com", "comcast.net", "cox.net",
    "duck.com", "email.com", "fastmail.com", "free.fr", "gmail.com", "gmx.com", "gmx.de",
    "gmx.net", "googlemail.com", "hey.com", "hotmail.co.uk", "hotmail.com", "hotmail.fr",
    "icloud.com", "inbox.com", "live.co.uk", "live.com", "mac.com", "mail.com", "mail.ru",
    "me.com", "msn.com", "naver.com", "outlook.com", "pm.me", "posteo.de", "proton.me",
    "protonmail.com", "qq.com", "rediffmail.com", "rocketmail.com", "sbcglobal.net",
    "tutanota.com", "verizon.net", "web.de", "yahoo.co.in", "yahoo.co.uk", "yahoo.com",
    "yandex.com", "yandex.ru", "ymail.com", "zoho.com", "163.com", "126.com",
  ]

  /// Two-label public suffixes that must be skipped when picking the registrable label, so
  /// `acme.co.uk` yields "acme" and not "co".
  private static let compoundSuffixes: Set<String> = [
    "ac.at", "ac.in", "ac.jp", "ac.kr", "ac.nz", "ac.uk", "co.id", "co.il", "co.in", "co.jp",
    "co.kr", "co.nz", "co.uk", "co.za", "com.au", "com.br", "com.cn", "com.mx", "com.sg",
    "com.tr", "edu.au", "edu.cn", "edu.in", "edu.sg", "gov.uk", "net.au", "org.uk",
  ]

  /// Words that carry no organization identity on their own, so a chat name made only of these
  /// names no organization. Three kinds, and every one of them was observed misfiring on real data:
  ///
  ///   - **group words** — `team`, `gang`, `class`, `crew`, `squad`, `board`, `ops`
  ///   - **season and cohort words** — `spring`, `summer`, `fall`, `winter` (numeric cohort codes
  ///     like `S26` / `F25` / `2024` are dropped separately, by the digit rule in `identityWords`)
  ///   - **industry and role words** — `ai`, `tech`, `dev`, `labs`, `vc`, `startup`, `founder`.
  ///     `ai` recurred across five unrelated chats on the measured export; it describes what a
  ///     company does, never which company.
  private static let genericGroupWords: Set<String> = [
    "a", "ai", "all", "analyst", "analysts", "and", "app", "autumn", "band", "board", "boys", "chat",
    "chats", "class", "club", "co", "cohort", "corp", "crew", "daily", "design", "dev", "directors",
    "eng", "engineering", "fall", "fam", "family", "folks", "for", "founder", "founders", "founding",
    "friends", "gang", "gc", "general", "girls", "group", "groups", "hq", "house", "inc", "intern",
    "interns", "internship", "labs", "llc", "ltd", "main", "misc", "of", "office", "ops", "people",
    "ppl", "product", "random", "room", "rooms", "sales", "spring", "squad", "standup", "startup",
    "startups", "stuff", "summer", "summit", "sync", "team", "teams", "tech", "the", "things",
    "thread", "vc", "weekly", "winter", "with", "work",
  ]

  private static func mailDomain(_ handle: String) -> String? {
    let parts = handle.lowercased().split(separator: "@", omittingEmptySubsequences: false)
    guard parts.count == 2 else { return nil }
    let domain = parts[1].trimmingCharacters(in: .whitespaces)
    guard domain.contains("."), !domain.hasPrefix("."), !domain.hasSuffix(".") else { return nil }
    return domain
  }

  private static func isAcademic(_ domain: String) -> Bool {
    domain.hasSuffix(".edu") || compoundSuffixes.contains(where: { domain.hasSuffix("." + $0) && $0.hasPrefix("ac.") })
      || domain.hasSuffix(".ac") || domain.hasSuffix(".edu.in") || domain.hasSuffix(".edu.au")
  }

  /// The organization-bearing label of a domain: `mail.acme.co.uk` → `acme`.
  static func registrableLabel(_ domain: String) -> String? {
    guard !domain.isEmpty else { return nil }
    var labels = domain.lowercased().split(separator: ".").map(String.init)
    guard labels.count >= 2 else { return nil }
    let lastTwo = labels.suffix(2).joined(separator: ".")
    labels.removeLast(compoundSuffixes.contains(lastTwo) ? 2 : 1)
    guard let label = labels.last, label.count >= 3, label.contains(where: { $0.isLetter }) else {
      return nil
    }
    return label
  }

  /// A domain that merely restates the person's own name is a personal site, not an employer.
  ///
  /// The comparison is against the person's *name*, so when the display name is itself the handle
  /// (`"matt@molinar.ai"` — what an unnamed email contact falls back to) only the local part counts.
  /// Comparing the whole string made every such contact look like their own vanity domain, which on
  /// the measured export dropped the one real corporate domain in the entire address book.
  private static func isVanityDomain(_ label: String, forName name: String) -> Bool {
    let key = orgKey(label)
    guard !key.isEmpty else { return true }
    let local = name.split(separator: "@", omittingEmptySubsequences: false).first.map(String.init) ?? name
    let tokens = local.lowercased().split(whereSeparator: { !$0.isLetter }).map(String.init)
    for token in tokens where token.count >= 4 {
      if key.contains(token) { return true }
    }
    // "alicesmith.com" vs "Alice Smith": the whole name, spaces removed.
    let joined = tokens.joined()
    return joined.count >= 6 && key == joined
  }

  /// A label a human would never type as a brand: `xrbru`, `yxzvwggct`. A name meant to be said out
  /// loud does not run four consonants together, and a randomly generated spam hostname routinely
  /// does. Applied **only** to a domain no second contact shares — a domain two of your contacts
  /// both use is corroborated by that fact whatever it looks like, so a real acronym company keeps
  /// working.
  static func isMachineGenerated(_ label: String) -> Bool {
    let vowels: Set<Character> = ["a", "e", "i", "o", "u", "y"]
    var run = 0
    for character in label.lowercased() where character.isLetter {
      run = vowels.contains(character) ? 0 : run + 1
      if run > 3 { return true }
    }
    return false
  }

  /// Comparison key: lowercase, letters and digits only.
  static func orgKey(_ raw: String) -> String {
    String(raw.lowercased().unicodeScalars.filter { CharacterSet.alphanumerics.contains($0) }.map(Character.init))
  }

  private static func displayName(fromDomainLabel label: String) -> String {
    label.split(separator: "-").map(capitalizedWord).joined(separator: " ")
  }

  /// Preserve a word the user already capitalized (e.g. "OpenAI"); otherwise upcase the first
  /// letter. Never re-cases an existing capital, so a real brand keeps its shape.
  private static func capitalizedWord<S: StringProtocol>(_ word: S) -> String {
    let text = String(word)
    guard let first = text.first else { return text }
    if text.contains(where: { $0.isUppercase }) { return text }
    return first.uppercased() + text.dropFirst()
  }

  /// The identity-bearing words of a group-chat name, in order, in the spelling the user typed:
  /// `"🚀 Acme eng standup"` → `["Acme"]`, `"AV S26"` → `["AV"]`, `"the team chat"` → `[]`.
  ///
  /// Each of the four filters removes a class of word that cannot name an organization:
  ///
  ///   - **no letter** — emoji, pure numbers.
  ///   - **any digit** — a cohort, season or date code (`S26`, `F25`, `2024`, `0-1`). A real
  ///     organization's name does not carry the term it ran in.
  ///   - **generic** — `genericGroupWords`: group, season, industry and role words.
  ///   - **a name in the graph** — `excludingNames`. Chat names are full of the people in them, and
  ///     on real data a contact's first name recurs far more often than any employer does.
  ///
  /// Two-letter words survive only when the user typed them as an acronym (`AV`, `YC`); otherwise
  /// three characters is the floor.
  static func identityWords(inGroupName raw: String, excludingNames nameTokens: Set<String>)
    -> [String]
  {
    let scrubbed = String(
      raw.unicodeScalars.map { scalar -> Character in
        CharacterSet.alphanumerics.contains(scalar) || scalar == "-" || scalar == "&"
          ? Character(scalar) : " "
      })
    return scrubbed.split(separator: " ").map(String.init).filter { word in
      guard word.contains(where: { $0.isLetter }), !word.contains(where: { $0.isNumber }) else {
        return false
      }
      let key = orgKey(word)
      guard key.count >= (word == word.uppercased() ? 2 : 3) else { return false }
      return !genericGroupWords.contains(key) && !nameTokens.contains(key)
    }
  }
}
