import Foundation

/// Phase-2 of `desktop/macos/docs/people-intelligence-productization.md`: the **deterministic**
/// per-person fields the People tab renders, derived entirely from data the on-device engine
/// already holds in memory (`PeopleGraphBuilder.People` / `.Graph` / `.Communities`).
///
/// No model. No network. Every value here is a mechanical restatement of a signal that is already
/// on disk, which is what makes it safe to ship to every user:
///
///   - `affiliations`   — organizations, from email domains and work-category group-chat names
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
  /// Most affiliations shown per person. The profile header renders the first and the Overview tab
  /// the rest; beyond three this reads as a dump rather than an identity.
  static let maxAffiliationsPerPerson = 3
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

  /// Organizations per person id, from two independent deterministic signals.
  ///
  /// **Email domain (direct).** A non-consumer domain on a handle you actually exchange messages
  /// with is the person telling you where they are. `stanford.edu` → school, everything else →
  /// company. A domain nobody else shares scores lower (0.5) than one two or more of your contacts
  /// share (0.8), because the second holder is what distinguishes a real org from a personal
  /// domain. A domain that merely echoes the person's own name is dropped outright as a vanity
  /// domain.
  ///
  /// **Work group-chat name (indirect, always corroborated).** A single work-category group chat is
  /// a weak signal — this categorizer keys off loose words like "gang" and "class" — so a group name
  /// alone never creates an organization. It is emitted only when a second, independent signal
  /// agrees: the same organization token appears in two different group chats the person is in
  /// (0.55), or somebody in that very chat has an email at the matching domain (0.7). When both the
  /// email and the group name point at the same organization the two merge into one entry at 0.85.
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

    // ---- 2. work group-chat organization candidates ----
    // person id -> org key -> group names that produced it.
    var groupOrgs: [String: [String: Set<String>]] = [:]
    // org key -> true when somebody inside that chat also has the matching email domain.
    var groupOrgDomainBacked: [String: Set<String>] = [:]  // person id -> org keys
    for community in communities.list {
      guard (community["category"] as? String) == "work / venture",
        let name = community["name"] as? String,
        let members = community["known_members"] as? [[String: Any]],
        members.count >= minKnownMembersForOrgGroup,
        let token = organizationToken(fromGroupName: name)
      else { continue }
      let key = orgKey(token)
      guard !key.isEmpty else { continue }
      let memberIDs = members.compactMap { $0["id"] as? String }
      // Independent corroboration: somebody actually in this chat has an email at the matching
      // domain, so the chat name is not the only thing claiming the organization exists.
      let domainBacked = memberIDs.contains { memberID in
        (domainsByPerson[memberID] ?? []).contains { domain in
          orgKey(registrableLabel(domain) ?? "") == key
        }
      }
      for memberID in memberIDs {
        groupOrgs[memberID, default: [:]][key, default: []].insert(name)
        if domainBacked { groupOrgDomainBacked[memberID, default: []].insert(key) }
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
        byKey[key] = Affiliation(
          name: displayName(fromDomainLabel: label),
          kind: isAcademic(domain) ? "school" : "company",
          confidence: shared ? 0.8 : 0.5,
          via: ["email: @\(domain)"])
      }

      for (key, groupNames) in groupOrgs[personID] ?? [:] {
        let domainBacked = groupOrgDomainBacked[personID]?.contains(key) ?? false
        let multiGroup = groupNames.count >= 2
        // No corroboration → no organization. A lone work-ish chat name is not evidence.
        guard domainBacked || multiGroup || byKey[key] != nil else { continue }
        let evidence = groupNames.sorted().map { "group chat: \($0)" }
        if let existing = byKey[key] {
          // The email and the group name agree — independent signals, so the entry gets stronger.
          byKey[key] = Affiliation(
            name: existing.name, kind: existing.kind,
            confidence: max(existing.confidence, 0.85),
            via: existing.via + evidence)
        } else {
          guard let display = groupNames.sorted().compactMap({ organizationToken(fromGroupName: $0) }).first
          else { continue }
          byKey[key] = Affiliation(
            name: display, kind: "organization",
            confidence: domainBacked ? 0.7 : 0.55,
            via: evidence)
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
  /// Groups in the categorizer's `social` fallback bucket get **no** entry: that bucket means "we
  /// could not tell", and glossing it as "a social group chat" would report a categorization that
  /// never happened.
  static func communityMeanings(_ communities: PeopleGraphBuilder.Communities) -> [String: String] {
    var out: [String: String] = [:]
    for community in communities.list {
      guard let name = community["name"] as? String, !name.isEmpty,
        let category = community["category"] as? String,
        let phrase = categoryPhrase(category)
      else { continue }
      let known = (community["known_members"] as? [[String: Any]])?.count ?? 0
      guard known > 0 else { continue }
      let total = (community["size_total"] as? Int) ?? known
      let channel = PeopleGraphBuilder.channelLabel((community["channel"] as? String) ?? "imessage")
      let membership =
        total > known
        ? "\(known) of its \(total) members are people you know"
        : "\(known) \(known == 1 ? "person" : "people") you know"
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

  /// Words that carry no organization identity on their own. A group name made only of these
  /// yields no token at all.
  private static let genericGroupWords: Set<String> = [
    "a", "all", "analyst", "analysts", "and", "band", "board", "boys", "chat", "chats", "class",
    "club", "co", "cohort", "corp", "crew", "daily", "design", "directors", "eng", "engineering",
    "fam", "family", "folks", "for", "founders", "founding", "friends", "gang", "gc", "general",
    "girls", "group", "groups", "hq", "inc", "intern", "interns", "internship", "llc", "ltd",
    "main", "misc", "of", "office", "ops", "people", "ppl", "product", "random", "room", "rooms",
    "sales", "squad", "standup", "startup", "startups", "stuff", "sync", "team", "teams", "the",
    "things", "thread", "weekly", "with", "work",
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
  private static func isVanityDomain(_ label: String, forName name: String) -> Bool {
    let key = orgKey(label)
    guard !key.isEmpty else { return true }
    let tokens = name.lowercased().split(whereSeparator: { !$0.isLetter }).map(String.init)
    for token in tokens where token.count >= 4 {
      if key.contains(token) { return true }
    }
    // "alicesmith.com" vs "Alice Smith": the whole name, spaces removed.
    let joined = tokens.joined()
    return joined.count >= 6 && key == joined
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

  /// The organization token inside a group-chat name: `"Acme Team 🚀"` → `"Acme"`. Returns nil when
  /// nothing identity-bearing survives (all-generic names, pure years, single letters, emoji-only).
  static func organizationToken(fromGroupName raw: String) -> String? {
    let scrubbed = String(
      raw.unicodeScalars.map { scalar -> Character in
        CharacterSet.alphanumerics.contains(scalar) || scalar == "-" || scalar == "&"
          ? Character(scalar) : " "
      })
    let words = scrubbed.split(separator: " ").map(String.init).filter { word in
      guard word.count >= 2, word.contains(where: { $0.isLetter }) else { return false }
      return !genericGroupWords.contains(word.lowercased())
    }
    // One to three identity-bearing words. Longer than that is a sentence, not an org name.
    guard (1...3).contains(words.count) else { return nil }
    let name = words.map(capitalizedWord).joined(separator: " ")
    return name.count >= 3 ? name : nil
  }
}
