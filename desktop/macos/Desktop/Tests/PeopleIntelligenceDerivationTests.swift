import XCTest

@testable import Omi_Computer

/// Exercises the deterministic Phase-2 enrichment (`PeopleIntelDerivation`) that turns the
/// on-device graph into the per-person fields the People list and profile actually render:
/// `affiliations`, `relationship`, `community_meanings`, `connections[].how` and
/// `history_grounded`.
///
/// Everything runs through the real pipeline (`readExport` → `buildCanonicalPeople` → `buildGraph`
/// → `buildCommunities` → `createPeople`) from one synthetic export, so a rule that only works on
/// hand-built structs cannot pass. Hermetic: a temp directory, no network, no Contacts, no
/// live services.
final class PeopleIntelligenceDerivationTests: XCTestCase {

  // MARK: - Fixture

  /// A small but deliberately varied address book:
  ///
  ///   - Alice / Bob      — both on `@acme.com`, both in two Acme chats
  ///   - Carol            — consumer mailbox (`gmail.com`), only in the Zenith chats
  ///   - Dana             — **phone only**; in the Acme chats, the Zenith chats and a family chat
  ///   - Erin             — a personal domain that restates her own name (vanity)
  ///   - Grace / Harry    — appear ONLY inside the family group chat, never messaged directly
  ///   - Ivan             — a consumer mailbox with zero messages and no group at all
  ///   - Nia / Owen / Pia — **phone only**, and every group they are in is a false-positive trap
  ///   - Rex / Quinn / Sam— **phone only**, in exactly one chat Acme owns
  ///
  /// The group chats are the real subject of this fixture. They cover every branch that matters:
  ///
  ///   - **Acme** — four chats bear the token, so the organization is established. Alice and Bob
  ///     also hold the matching email domain; Dana, Rex, Quinn and Sam hold no email at all, which
  ///     is what makes this a phone-only test.
  ///   - **`"Northwind >< Acme"`** — a two-party chat. Nia, Owen and Pia are in exactly this one
  ///     Acme chat, so they are the counterparty and must get nothing.
  ///   - **Zenith** — two chats, one short of the bar. Must produce nothing.
  ///   - **Vertex** — one chat. Must produce nothing.
  ///   - **`"meat gang"`** — the documented trap: the categorizer files it under work because of
  ///     two loose keywords. One chat, so it must never become an employer.
  ///   - **Crib ×3** — recurrence and overlap both satisfied, but the chats are a household.
  ///   - **`"Nia …"` ×3** — recurrence and overlap both satisfied, but the token is a contact.
  private func syntheticExport() throws -> PeopleGraphBuilder.ExportRoot {
    let json = """
      {
        "handles": [
          { "handle": "alice@acme.com", "contact_name": "Alice Chen", "message_count": 400,
            "last_date": "2026-07-01T10:00:00Z" },
          { "handle": "bob@acme.com", "contact_name": "Bob Ruiz", "message_count": 120,
            "last_date": "2026-06-01T10:00:00Z" },
          { "handle": "carol@gmail.com", "contact_name": "Carol Diaz", "message_count": 90,
            "last_date": "2026-06-02T10:00:00Z" },
          { "handle": "+15551234567", "phone_last10": "5551234567", "contact_name": "Dana Kim",
            "message_count": 30, "last_date": "2026-05-01T10:00:00Z" },
          { "handle": "erin@erinlovelace.com", "contact_name": "Erin Lovelace", "message_count": 12,
            "last_date": "2026-04-01T10:00:00Z" },
          { "handle": "ivan@gmail.com", "contact_name": "Ivan Petrov", "message_count": 0 },
          { "handle": "+15550110001", "phone_last10": "5550110001", "contact_name": "Nia Kaur",
            "message_count": 0 },
          { "handle": "+15550110002", "phone_last10": "5550110002", "contact_name": "Owen Diaz",
            "message_count": 0 },
          { "handle": "+15550110003", "phone_last10": "5550110003", "contact_name": "Pia Roy",
            "message_count": 0 },
          { "handle": "+15550110004", "phone_last10": "5550110004", "contact_name": "Rex Bloom",
            "message_count": 0 },
          { "handle": "+15550110005", "phone_last10": "5550110005", "contact_name": "Quinn Vega",
            "message_count": 0 },
          { "handle": "+15550110006", "phone_last10": "5550110006", "contact_name": "Sam Iyer",
            "message_count": 0 }
        ],
        "groups": [
          { "display_name": "Acme Interns", "member_count": 3, "members": [
              { "handle": "alice@acme.com" }, { "handle": "bob@acme.com" },
              { "phone_last10": "5551234567" } ] },
          { "display_name": "Acme Startup 2024", "member_count": 6, "members": [
              { "handle": "alice@acme.com" }, { "handle": "bob@acme.com" },
              { "phone_last10": "5551234567" } ] },
          { "display_name": "Acme Ops", "member_count": 3, "members": [
              { "phone_last10": "5550110004" }, { "phone_last10": "5550110005" },
              { "phone_last10": "5550110006" } ] },
          { "display_name": "Northwind >< Acme", "member_count": 3, "members": [
              { "phone_last10": "5550110001" }, { "phone_last10": "5550110002" },
              { "phone_last10": "5550110003" } ] },
          { "display_name": "Zenith Interns", "member_count": 3, "members": [
              { "handle": "carol@gmail.com" }, { "phone_last10": "5551234567" },
              { "handle": "erin@erinlovelace.com" } ] },
          { "display_name": "Zenith Startup Chat", "member_count": 3, "members": [
              { "handle": "carol@gmail.com" }, { "phone_last10": "5551234567" },
              { "handle": "erin@erinlovelace.com" } ] },
          { "display_name": "Vertex Interns", "member_count": 3, "members": [
              { "handle": "carol@gmail.com" }, { "phone_last10": "5551234567" },
              { "handle": "erin@erinlovelace.com" } ] },
          { "display_name": "meat gang", "member_count": 3, "members": [
              { "phone_last10": "5550110001" }, { "phone_last10": "5550110002" },
              { "phone_last10": "5550110003" } ] },
          { "display_name": "Crib Chat", "member_count": 3, "members": [
              { "phone_last10": "5550110001" }, { "phone_last10": "5550110002" },
              { "phone_last10": "5550110003" } ] },
          { "display_name": "Crib Rules", "member_count": 3, "members": [
              { "phone_last10": "5550110001" }, { "phone_last10": "5550110002" },
              { "phone_last10": "5550110003" } ] },
          { "display_name": "Crib Nights", "member_count": 3, "members": [
              { "phone_last10": "5550110001" }, { "phone_last10": "5550110002" },
              { "phone_last10": "5550110003" } ] },
          { "display_name": "Nia Sync", "member_count": 3, "members": [
              { "phone_last10": "5550110001" }, { "phone_last10": "5550110002" },
              { "phone_last10": "5550110003" } ] },
          { "display_name": "Nia Standup", "member_count": 3, "members": [
              { "phone_last10": "5550110001" }, { "phone_last10": "5550110002" },
              { "phone_last10": "5550110003" } ] },
          { "display_name": "Nia Ops", "member_count": 3, "members": [
              { "phone_last10": "5550110001" }, { "phone_last10": "5550110002" },
              { "phone_last10": "5550110003" } ] },
          { "display_name": "Kim Family", "member_count": 3, "members": [
              { "phone_last10": "5551234567" }, { "phone_last10": "5550002222" },
              { "phone_last10": "5550003333" } ] },
          { "display_name": "Brunch Plans", "member_count": 3, "members": [
              { "handle": "alice@acme.com" }, { "handle": "carol@gmail.com" },
              { "phone_last10": "5551234567" } ] }
        ]
      }
      """
    let dir = FileManager.default.temporaryDirectory
      .appendingPathComponent("PeopleIntelDerivationTests-\(UUID().uuidString)", isDirectory: true)
    try FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
    defer { try? FileManager.default.removeItem(at: dir) }
    let url = dir.appendingPathComponent("imessage_export.json")
    try XCTUnwrap(json.data(using: .utf8)).write(to: url)
    return try XCTUnwrap(PeopleGraphBuilder.readExport(at: url), "synthetic export must decode")
  }

  private struct Pipeline {
    let people: PeopleGraphBuilder.People
    let graph: PeopleGraphBuilder.Graph
    let communities: PeopleGraphBuilder.Communities
  }

  private func runPipeline() throws -> Pipeline {
    let root = try syntheticExport()
    let people = PeopleGraphBuilder.buildCanonicalPeople(root: root, contactsByPhone: [:])
    return Pipeline(
      people: people,
      graph: PeopleGraphBuilder.buildGraph(root: root, people: people),
      communities: PeopleGraphBuilder.buildCommunities(root: root, people: people))
  }

  private func affiliation(_ orgs: [PeopleIntelDerivation.Affiliation], named name: String)
    -> PeopleIntelDerivation.Affiliation?
  {
    orgs.first { $0.name == name }
  }

  // MARK: - Affiliations

  /// Organizations are only claimed when a second, independent signal agrees. This is the whole
  /// point of the rule: an unbacked guess about where somebody works is worse than a blank field.
  func testAffiliationsRequireCorroboration() throws {
    let p = try runPipeline()
    let orgs = PeopleIntelDerivation.affiliations(people: p.people, communities: p.communities)

    // --- corporate email domain shared by two contacts, and named by the chats they share.
    let alice = try XCTUnwrap(orgs["alice-chen"], "Alice must get an affiliation")
    let acme = try XCTUnwrap(affiliation(alice, named: "Acme"), "the @acme.com domain names Acme")
    XCTAssertEqual(acme.kind, "company", "a non-academic corporate domain is a company")
    XCTAssertEqual(
      acme.confidence, 0.85, accuracy: 0.0001,
      "email domain AND matching work chat name are independent signals, so they merge stronger")
    XCTAssertTrue(
      acme.via.contains("email: @acme.com"), "the evidence must name the domain it came from")
    XCTAssertTrue(
      acme.via.contains("group chat: Acme Interns"),
      "the evidence must name the group chat it came from")

    // --- chat-name-only organization: no email anywhere on this person.
    let dana = try XCTUnwrap(orgs["dana-kim"], "Dana is in two of the organization's chats")
    let danaAcme = try XCTUnwrap(affiliation(dana, named: "Acme"))
    XCTAssertEqual(danaAcme.kind, "organization", "Dana has no Acme email — only the chats name it")
    XCTAssertEqual(
      danaAcme.confidence, 0.7, accuracy: 0.0001,
      "chat names alone score below a first-party email at the same organization")
    XCTAssertFalse(
      danaAcme.via.contains(where: { $0.hasPrefix("email:") }),
      "Dana's evidence must not cite an email address she does not have")

    // --- THE CONSERVATIVE CASES. Each of these clears some of the bar and must still yield
    // nothing, because the whole rule is that one signal on its own is never enough.
    for (personID, list) in orgs {
      XCTAssertNil(
        affiliation(list, named: "Vertex"),
        "\(personID): a single un-corroborated group-chat name must never invent an organization")
      XCTAssertNil(
        affiliation(list, named: "Zenith"),
        "\(personID): two chats is one short of establishing an organization")
      for trap in ["Meat", "Meat Gang", "Gang", "Crib", "Nia"] {
        XCTAssertNil(
          affiliation(list, named: trap),
          "\(personID): '\(trap)' must never be read as an organization")
      }
    }

    // --- consumer mailbox is not an employer.
    let carol = orgs["carol-diaz"] ?? []
    XCTAssertNil(affiliation(carol, named: "Gmail"), "a gmail.com address says nothing about work")
    XCTAssertTrue(carol.isEmpty, "Carol has no corroborated signal of any kind")

    // --- a domain that just restates the person's own name is a personal site, not an org.
    let erin = orgs["erin-lovelace"] ?? []
    XCTAssertNil(
      affiliation(erin, named: "Erinlovelace"), "a vanity domain must not become an employer")

    // --- nobody with no signal at all gets an entry.
    XCTAssertNil(orgs["ivan-petrov"], "a consumer mailbox and no groups yields no affiliation")
  }

  /// The regression this whole rule exists for: a **phone-only** address book with realistic chat
  /// names must still produce affiliations. The email-corroborated version of this rule shipped a
  /// cold run with `affiliations` on 0 of 1,825 people, because real message exports carry phone
  /// handles and essentially no email — so every assertion below deliberately uses a person who has
  /// no email address at all.
  func testAffiliationsAreDerivedFromPhoneOnlyData() throws {
    let p = try runPipeline()
    let orgs = PeopleIntelDerivation.affiliations(people: p.people, communities: p.communities)

    // Dana holds no email. Four chats bear "Acme"; she is in two of them.
    let dana = try XCTUnwrap(orgs["dana-kim"], "a phone-only contact must still get an affiliation")
    XCTAssertTrue(
      p.people.idByEmail.values.allSatisfy { $0 != "dana-kim" }, "Dana must have no email handle")
    let danaAcme = try XCTUnwrap(affiliation(dana, named: "Acme"))
    XCTAssertEqual(danaAcme.confidence, 0.7, accuracy: 0.0001, "in two of the organization's chats")

    // Rex is in exactly one chat, but it is a chat Acme *owns* — named after it, no second party.
    let rex = try XCTUnwrap(orgs["rex-bloom"], "one chat the organization owns is real evidence")
    let rexAcme = try XCTUnwrap(affiliation(rex, named: "Acme"))
    XCTAssertEqual(
      rexAcme.confidence, 0.55, accuracy: 0.0001, "the weakest evidence we still accept")
    XCTAssertEqual(rexAcme.via, ["group chat: Acme Ops"], "the owning chat is the evidence")
    XCTAssertEqual(rexAcme.kind, "organization", "no email said 'company', so we do not either")

    // THE COUNTERPARTY CASE. Nia, Owen and Pia are in exactly one Acme chat and it names a second
    // party, so they are as likely to be Northwind as Acme. Guessing here would put a stranger's
    // employer on a real person's profile.
    for personID in ["nia-kaur", "owen-diaz", "pia-roy"] {
      XCTAssertNil(
        affiliation(orgs[personID] ?? [], named: "Acme"),
        "\(personID): one two-party chat does not say which of the two parties they are on")
      XCTAssertNil(
        affiliation(orgs[personID] ?? [], named: "Northwind"),
        "\(personID): Northwind is named by one chat and is not established at all")
    }
  }

  /// The establish step, pinned on its own: which words this graph's chat names make organizations,
  /// and — more importantly — which ones they do not.
  func testOrganizationsAreEstablishedOnlyByCorroboratedRecurrence() throws {
    let p = try runPipeline()
    let index = PeopleIntelDerivation.organizations(people: p.people, communities: p.communities)

    XCTAssertEqual(
      Set(index.organizations.keys), ["acme"],
      "exactly one token in this address book clears recurrence + overlap + category + shape")
    let acme = try XCTUnwrap(index.organizations["acme"])
    XCTAssertEqual(acme.display, "Acme", "the spelling the user actually types")
    XCTAssertEqual(
      acme.chats,
      ["Acme Interns", "Acme Ops", "Acme Startup 2024", "Northwind >< Acme"],
      "every chat bearing the token counts toward establishing it")
    XCTAssertEqual(
      acme.ownChats, ["Acme Interns", "Acme Ops", "Acme Startup 2024"],
      "a two-party chat is evidence the organization exists, never evidence of who works there")
  }

  /// Each filter, isolated: the fixture gives every one of these tokens enough recurrence and
  /// enough membership overlap to be established, and each is stopped by exactly one rule.
  func testIdentityWordsRejectEachClassOfNonOrganization() {
    let names: Set<String> = ["nia", "kaur", "dana", "kim"]
    func words(_ name: String) -> [String] {
      PeopleIntelDerivation.identityWords(inGroupName: name, excludingNames: names)
    }
    XCTAssertEqual(words("Acme Interns"), ["Acme"], "role words are decoration")
    XCTAssertEqual(words("🚀 Acme eng standup"), ["Acme"], "so are emoji")
    XCTAssertEqual(words("OpenAI Team"), ["OpenAI"], "the user's own capitalization is preserved")
    XCTAssertEqual(words("AV S26"), ["AV"], "an acronym survives; a cohort code does not")
    XCTAssertEqual(
      words("Spring '25 Dilly"), ["Dilly"], "a season and a year are both cohort codes")
    XCTAssertEqual(words("the team chat"), [], "an all-generic name names no organization")
    XCTAssertEqual(words("meat gang"), ["meat"], "'gang' is generic; 'meat' survives to be counted")
    XCTAssertEqual(
      words("Nia Sync"), [],
      "a contact's own name is the single most recurrent token in real chat names")
    XCTAssertEqual(words("🎉🎉🎉"), [], "emoji alone name nothing")
    XCTAssertEqual(words("2024 2025"), [], "digits carry no organization identity")
    XCTAssertEqual(
      words("AI Startup Founders"), [], "industry and role words say what, never which")
  }

  /// A single-holder corporate domain is real but weaker evidence than one several contacts share,
  /// and an academic domain is a school rather than a company.
  func testAffiliationConfidenceAndKindFromDomainAlone() throws {
    var people = PeopleGraphBuilder.People()
    people.canonByID["jo-park"] = PeopleGraphBuilder.Canon(
      id: "jo-park", name: "Jo Park", messageCount: 40, identified: true, lastDate: nil)
    people.canonByID["sam-lee"] = PeopleGraphBuilder.Canon(
      id: "sam-lee", name: "Sam Lee", messageCount: 20, identified: true, lastDate: nil)
    people.idName = ["jo-park": "Jo Park", "sam-lee": "Sam Lee"]
    people.idByEmail = ["jo@vertexrobotics.io": "jo-park", "sam@stanford.edu": "sam-lee"]

    let orgs = PeopleIntelDerivation.affiliations(
      people: people, communities: PeopleGraphBuilder.Communities())

    let jo = try XCTUnwrap(orgs["jo-park"]?.first)
    XCTAssertEqual(jo.name, "Vertexrobotics", "the registrable label names the company")
    XCTAssertEqual(jo.kind, "company")
    XCTAssertEqual(
      jo.confidence, 0.5, accuracy: 0.0001,
      "a domain only one contact holds stays low-confidence — it could be a personal domain")

    let sam = try XCTUnwrap(orgs["sam-lee"]?.first)
    XCTAssertEqual(sam.name, "Stanford")
    XCTAssertEqual(sam.kind, "school", "a .edu domain is a school, not a company")
  }

  /// An uncorroborated domain also has to look like a brand. Both of these were real senders in a
  /// real 1,825-person address book, and both became companies on somebody's profile.
  func testUncorroboratedSpamDomainsDoNotBecomeCompanies() throws {
    var people = PeopleGraphBuilder.People()
    people.canonByID["spam-one"] = PeopleGraphBuilder.Canon(
      id: "spam-one", name: "Spam One", messageCount: 2, identified: false, lastDate: nil)
    people.canonByID["real-one"] = PeopleGraphBuilder.Canon(
      id: "real-one", name: "Matt R", messageCount: 40, identified: true, lastDate: nil)
    people.idName = ["spam-one": "Spam One", "real-one": "Matt R"]
    people.idByEmail = [
      "jaystr8@marketing.yxzvwggct.com": "spam-one", "matt@molinar.ai": "real-one",
    ]

    let orgs = PeopleIntelDerivation.affiliations(
      people: people, communities: PeopleGraphBuilder.Communities())
    XCTAssertNil(orgs["spam-one"], "a machine-generated hostname is not an employer")
    XCTAssertEqual(
      orgs["real-one"]?.first?.name, "Molinar",
      "a pronounceable single-holder domain is still the person telling you where they work")

    XCTAssertTrue(PeopleIntelDerivation.isMachineGenerated("yxzvwggct"))
    XCTAssertTrue(PeopleIntelDerivation.isMachineGenerated("xrbru"))
    for brand in ["molinar", "stanford", "acme", "openai", "vertexrobotics", "breakout"] {
      XCTAssertFalse(
        PeopleIntelDerivation.isMachineGenerated(brand), "\(brand) is a name people say out loud")
    }
  }

  // MARK: - Relationship label

  /// The label is a rank plus a category, and must read as such. Each assertion below pins one
  /// signal combination.
  func testRelationshipLabelsAcrossSignalCombinations() throws {
    let p = try runPipeline()
    let labels = PeopleIntelDerivation.relationshipLabels(
      people: p.people, communities: p.communities)

    XCTAssertEqual(
      labels["alice-chen"], "close · work",
      "the most-messaged contact, whose shared chats are work-category")
    XCTAssertEqual(
      labels["bob-ruiz"], "regular · work", "a mid-volume contact is regular, not close")
    XCTAssertEqual(
      labels["dana-kim"], "occasional · work",
      "30 messages is real but light; work still dominates her group categories")
    XCTAssertEqual(
      labels["5550002222"], "group contact · family",
      "someone who only appears inside a group chat is never described as messaged")
    XCTAssertNil(
      labels["ivan-petrov"],
      "no messages and no shared group means no honest label at all — not a filler one")

    for (personID, label) in labels {
      XCTAssertFalse(
        label.contains("."), "\(personID): the label is a tag, not a model-written sentence")
      XCTAssertLessThanOrEqual(label.count, 32, "\(personID): the list subtitle must stay short")
    }
  }

  /// Being reachable on two connectors is independent corroboration of closeness, and the absolute
  /// message floors stop a tiny address book from calling a five-message contact "close".
  func testRelationshipTierUsesChannelMixAndAbsoluteFloors() {
    func people(_ entries: [(String, Int, [String: Int])]) -> PeopleGraphBuilder.People {
      var out = PeopleGraphBuilder.People()
      for (id, messages, channels) in entries {
        out.canonByID[id] = PeopleGraphBuilder.Canon(
          id: id, name: id, messageCount: messages, identified: true, lastDate: nil,
          messagesByChannel: channels)
        out.idName[id] = id
      }
      return out
    }
    let empty = PeopleGraphBuilder.Communities()

    // Same rank, same volume, both well below the top of the address book — the only difference
    // is being reachable on a second app.
    let mixed = PeopleIntelDerivation.relationshipLabels(
      people: people([
        ("heaviest", 500, ["imessage": 500]),
        ("one-app", 80, ["imessage": 80]),
        ("two-apps", 80, ["imessage": 40, "whatsapp": 40]),
      ]), communities: empty)
    XCTAssertEqual(mixed["heaviest"], "close", "the top of the address book anchors the ranking")
    XCTAssertEqual(mixed["one-app"], "regular")
    XCTAssertEqual(
      mixed["two-apps"], "close",
      "keeping up across two independent messaging apps promotes exactly one tier")

    // Top of a three-person address book, but only five messages: rank alone must not say "close".
    let tiny = PeopleIntelDerivation.relationshipLabels(
      people: people([
        ("top", 5, ["imessage": 5]), ("mid", 3, ["imessage": 3]), ("low", 1, ["imessage": 1]),
      ]), communities: empty)
    XCTAssertEqual(
      tiny["top"], "occasional",
      "the absolute floor stops a degenerate percentile from claiming a close relationship")
  }

  // MARK: - Community meanings

  func testCommunityMeaningsExplainEveryGroupWithoutInventingACategory() throws {
    let p = try runPipeline()
    let meanings = PeopleIntelDerivation.communityMeanings(p.communities)

    XCTAssertEqual(
      meanings["Acme Interns"], "A work group chat on iMessage — 3 people you know.",
      "a fully-known chat states how many of your people are in it")
    XCTAssertEqual(
      meanings["Acme Startup 2024"],
      "A work group chat on iMessage — 3 of its 6 members are people you know.",
      "a partly-known chat is explicit that you only know some of it")
    XCTAssertEqual(meanings["Kim Family"], "A family group chat on iMessage — 3 people you know.")

    // The categorizer's `social` bucket means "we could not tell". Requiring a category meant three
    // quarters of a real user's groups rendered as a bare name with nothing under them, so the
    // connector and the membership — facts about every chat — are stated either way.
    let brunch = try XCTUnwrap(
      meanings["Brunch Plans"], "an unclassified group still gets the facts we do have")
    XCTAssertEqual(brunch, "A group chat on iMessage — 3 people you know.")
    XCTAssertFalse(
      brunch.lowercased().contains("social"),
      "the fallback bucket must never be reported as a category we inferred")

    XCTAssertEqual(
      meanings.count, p.communities.list.count,
      "every named group with a known member gets an explanation")
  }

  // MARK: - connections[].how

  func testConnectionHowDescribesTheEdgeItActuallyHas() {
    XCTAssertEqual(
      PeopleIntelDerivation.connectionHow(context: ["Acme Interns"], sources: ["imessage"]),
      "Both in Acme Interns")
    XCTAssertEqual(
      PeopleIntelDerivation.connectionHow(
        context: ["Acme Interns", "Brunch Plans"], sources: ["imessage", "whatsapp"]),
      "Both in Acme Interns and Brunch Plans, on iMessage and WhatsApp",
      "co-occurring on two connectors is real corroboration and worth naming")
    XCTAssertEqual(
      PeopleIntelDerivation.connectionHow(context: ["A", "B", "C", "D"], sources: ["imessage"]),
      "Both in A, B, and other shared group chats",
      "the context list is capped upstream, so an exact remainder count would be a lie")

    // An edge with no named context came from a group nobody named — say exactly that.
    XCTAssertEqual(
      PeopleIntelDerivation.connectionHow(context: [], sources: ["imessage"]),
      "In an unnamed shared iMessage group chat")
    XCTAssertEqual(
      PeopleIntelDerivation.connectionHow(context: [], sources: ["imessage", "whatsapp"]),
      "In an unnamed shared group chat, on iMessage and WhatsApp")

    // Every edge in this engine comes from group co-membership; there is no 1:1 co-occurrence
    // signal on device, so the prototype's "frequent 1:1 messaging" phrasing must never appear.
    for context in [[], ["Acme Interns"], ["A", "B"]] {
      let how = PeopleIntelDerivation.connectionHow(context: context, sources: ["imessage"])
      XCTAssertFalse(how.lowercased().contains("1:1"), "no edge here is derived from 1:1 messaging")
      XCTAssertTrue(how.lowercased().contains("group chat") || how.hasPrefix("Both in "))
    }
  }

  func testGraphConnectionsCarryTheirDerivation() throws {
    let p = try runPipeline()
    let danaConnections = try XCTUnwrap(p.graph.connectionsByID["dana-kim"])
    let toAlice = try XCTUnwrap(danaConnections.first { ($0["id"] as? String) == "alice-chen" })
    let how = try XCTUnwrap(toAlice["how"] as? String, "every connection must carry a derivation")
    XCTAssertTrue(
      how.contains("Acme Interns") || how.contains("Acme Startup 2024")
        || how.contains("Brunch Plans"),
      "the derivation must name a group they are really both in, got: \(how)")
    XCTAssertNil(toAlice["type"], "relationship typing is model-backed (Phase 3) and stays absent")
  }

  // MARK: - history_grounded

  /// The ledger's window keys are content hashes and cannot be traced back to a person, so the
  /// ingest records the person keys it actually submitted. `history_grounded` reads only that.
  func testHistoryGroundedReflectsTheIngestLedger() throws {
    let dir = FileManager.default.temporaryDirectory
      .appendingPathComponent("PeopleIntelLedger-\(UUID().uuidString)", isDirectory: true)
    try FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
    defer { try? FileManager.default.removeItem(at: dir) }

    XCTAssertTrue(
      PeopleThreadIngest.ingestedPersonKeys(directory: dir).isEmpty, "no ledger reads as nothing")

    // A ledger written before the person-key set existed must not claim anything is grounded.
    let legacy = #"{"version":1,"keys":["w1","w2"]}"#
    try XCTUnwrap(legacy.data(using: .utf8))
      .write(to: dir.appendingPathComponent(PeopleThreadIngest.ledgerFileName))
    XCTAssertEqual(
      PeopleThreadIngest.loadLedger(directory: dir), ["w1", "w2"], "legacy dedupe still works")
    XCTAssertTrue(
      PeopleThreadIngest.ingestedPersonKeys(directory: dir).isEmpty,
      "an unmigrated ledger grounds nobody rather than guessing")

    PeopleThreadIngest.appendLedger(directory: dir, keys: ["w3"], personKeys: ["5551234567"])
    XCTAssertEqual(PeopleThreadIngest.loadLedger(directory: dir), ["w1", "w2", "w3"])
    XCTAssertEqual(PeopleThreadIngest.ingestedPersonKeys(directory: dir), ["5551234567"])

    let p = try runPipeline()
    XCTAssertEqual(
      PeopleIntelDerivation.historyGroundedIDs(
        people: p.people, ingestedPersonKeys: PeopleThreadIngest.ingestedPersonKeys(directory: dir)),
      ["dana-kim"], "the phone identity in the ledger resolves to exactly that canonical person")
    XCTAssertEqual(
      PeopleIntelDerivation.historyGroundedIDs(
        people: p.people, ingestedPersonKeys: ["wa:5551234567"]),
      ["dana-kim"], "the WhatsApp-prefixed key grounds the same person")
    XCTAssertTrue(
      PeopleIntelDerivation.historyGroundedIDs(people: p.people, ingestedPersonKeys: ["9998887777"])
        .isEmpty, "an unknown key grounds nobody")
  }

  // MARK: - Created people cards

  func testCreatedPeopleCarryTheDeterministicFieldsAndNothingModelBacked() throws {
    let p = try runPipeline()
    let persons = PeopleGraphBuilder.createPeople(
      people: p.people, graph: p.graph, communities: p.communities,
      ingestedPersonKeys: ["5551234567"])

    func card(_ id: String) throws -> [String: Any] {
      try XCTUnwrap(persons.first { ($0["id"] as? String) == id }, "missing card for \(id)")
    }

    let alice = try card("alice-chen")
    XCTAssertEqual(alice["relationship"] as? String, "close · work")
    XCTAssertEqual(
      ((alice["affiliations"] as? [[String: Any]])?.first?["name"] as? String), "Acme",
      "the affiliation is written in the shape PersonAffiliation decodes")
    XCTAssertEqual(
      ((alice["affiliations"] as? [[String: Any]])?.first?["type"] as? String), "company",
      "the decoder reads `type`, not `kind`")
    XCTAssertNil(
      alice["history_grounded"], "Alice's thread was never ingested, so the claim is not made")

    let dana = try card("dana-kim")
    XCTAssertEqual(
      dana["history_grounded"] as? Bool, true, "Dana's thread is in the ledger")

    // Phase 3 is model-backed. Emitting deterministic stand-ins would be dishonest, so these keys
    // must stay absent on every card the on-device engine writes.
    for person in persons {
      for absent in ["who", "now", "overall", "facts", "activities", "openThreads", "role"] {
        XCTAssertNil(
          person[absent],
          "\(person["id"] as? String ?? "?"): `\(absent)` needs a model and must not be faked")
      }
    }
  }

  // MARK: - Merge path

  /// A card that already carries richer values (a model-written relationship, a curated
  /// affiliation list, a hand-written group gloss) must survive a rebuild untouched; a card
  /// missing them gets the deterministic fill-in.
  func testMergePreservesRicherValuesAndFillsBlanks() throws {
    let p = try runPipeline()
    let dir = FileManager.default.temporaryDirectory
      .appendingPathComponent("PeopleIntelMerge-\(UUID().uuidString)", isDirectory: true)
    try FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
    defer { try? FileManager.default.removeItem(at: dir) }
    let url = dir.appendingPathComponent("people_intelligence.json")

    let existing: [String: Any] = [
      "people": [
        [
          "id": "alice-chen", "name": "Alice Chen",
          "relationship": "college roommate, now my cofounder",
          "affiliations": [["name": "Curated Co", "type": "company", "confidence": 1.0, "via": []]],
        ] as [String: Any],
        ["id": "bob-ruiz", "name": "Bob Ruiz", "relationship": ""] as [String: Any],
      ],
      "community_meanings": ["Acme Interns": "where we plan the intern cohort"],
    ]
    try JSONSerialization.data(withJSONObject: existing).write(to: url)

    PeopleGraphBuilder.mergeIntoPeopleIntelligence(
      graph: p.graph, communities: p.communities, people: p.people, ingestedPersonKeys: [], at: url)

    let merged = try XCTUnwrap(
      try JSONSerialization.jsonObject(with: Data(contentsOf: url)) as? [String: Any])
    let people = try XCTUnwrap(merged["people"] as? [[String: Any]])
    let alice = try XCTUnwrap(people.first { ($0["id"] as? String) == "alice-chen" })
    let bob = try XCTUnwrap(people.first { ($0["id"] as? String) == "bob-ruiz" })

    XCTAssertEqual(
      alice["relationship"] as? String, "college roommate, now my cofounder",
      "a richer existing relationship must never be overwritten by a rank-and-category tag")
    XCTAssertEqual(
      (alice["affiliations"] as? [[String: Any]])?.first?["name"] as? String, "Curated Co",
      "a curated affiliation list must never be replaced by the inferred one")
    XCTAssertEqual(
      bob["relationship"] as? String, "regular · work",
      "an empty relationship is filled in, which is what un-blanks the People list subtitle")

    let meanings = try XCTUnwrap(merged["community_meanings"] as? [String: String])
    XCTAssertEqual(
      meanings["Acme Interns"], "where we plan the intern cohort",
      "an existing gloss wins over the generated one")
    XCTAssertEqual(
      meanings["Kim Family"], "A family group chat on iMessage — 3 people you know.",
      "groups with no gloss yet still get one")
  }
}
