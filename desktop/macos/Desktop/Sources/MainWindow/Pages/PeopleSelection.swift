import Foundation

// MARK: - Who becomes a person
//
// `PeopleGraphBuilder.buildCanonicalPeople` deliberately turns **every identity in the export** into
// a node: direct correspondents, group members, and the opaque platform tokens that large group
// member lists are full of. That is correct for a *graph* — an edge needs both endpoints — and wrong
// for a *directory*. A real cold start on one machine produced 1,825 nodes, 988 of which were
// unbridged WhatsApp `@lid` tokens pulled out of four broadcast lists (591 / 275 / 247 / 204
// members) and 1,398 of which had never exchanged a single message. Shipping that array to the
// People tab is a graph dump, not "the people you know".
//
// This file is the missing stage between "every node in the graph" and "the People tab". It is a
// pure function over `(People, Graph, Communities)` — no IO, no Contacts, no clock — so the rule can
// be asserted directly, and every node it removes carries a stated reason the UI can show the user.
//
// The rule, in one sentence: **a person is someone you can address, and either someone you have
// actually talked with or someone you can name who shares a real group with you.**

/// Where a person's display name came from, strongest first.
///
/// The distinction that matters is *asserted* vs *derived*: Contacts, a connector's own contact
/// name, and a name this machine resolved on an earlier run were all told to us by a source. A name
/// pulled out of an email address's local part is a reading of the address itself. Both are enough
/// to put a human label on a card; only the asserted ones may claim `contactName`.
enum PersonNameSource: Int, Comparable, Sendable {
  /// No name at all — the raw phone number / handle is the only label available.
  case handle = 0
  /// Derived from the address, e.g. `dana.wu@example.com` → "Dana Wu". A reading, not an assertion.
  case emailLocalPart = 1
  /// A human name this machine already resolved for this identity key on an earlier run
  /// (`people_identity.json`). Survives Contacts access being revoked or a connector going quiet.
  case durable = 2
  /// The connector's own name for the person (WhatsApp's `ZPARTNERNAME`).
  case exportContact = 3
  /// The macOS address book.
  case addressBook = 4

  /// True when anything better than the raw handle named this person.
  var isNamed: Bool { self != .handle }

  /// True when a *source* asserted this name, rather than it being read off the address. Only these
  /// may be surfaced as a `contactName`.
  var isAsserted: Bool { self >= .durable }

  static func < (lhs: PersonNameSource, rhs: PersonNameSource) -> Bool { lhs.rawValue < rhs.rawValue }
}

/// The naming cascade, exhausted **before** a node is ever dropped for being unnamed.
///
/// Only 147 of the 1,825 nodes in the measured cold start carried a name, because
/// `IMessageExporter.ExportHandle` has no name field at all — iMessage names come from Contacts or
/// from nowhere. That makes "unnamed" a very common state and therefore a dangerous drop signal
/// unless every source that exists has been tried first. Nothing here invents a name: each rung is
/// a real source, and a node with no rung left stays unnamed.
enum PeopleNaming {
  /// True when `name` reads as a human label rather than a phone number, an address, or a token.
  ///
  /// Deliberately strict about the two shapes the pipeline actually produces as fallbacks: a raw
  /// phone handle (`+1 (555) 123-4567`) and a raw JID/address (`10005616@lid`,
  /// `urn:biz:6e67a89b-…`). Both are already the *default* label, so accepting either here would
  /// make "named" meaningless.
  static func isHumanShaped(_ name: String?) -> Bool {
    guard let trimmed = name?.trimmingCharacters(in: .whitespacesAndNewlines), !trimmed.isEmpty
    else { return false }
    if trimmed.contains("@") { return false }
    if trimmed.lowercased().hasPrefix("urn:") { return false }
    // At least one letter, and no more digits than letters — "+1 555 123 4567" and "725" are not
    // names, "Sruti's Mom" and "Aryaveer UMN" are.
    let letters = trimmed.filter(\.isLetter).count
    let digits = trimmed.filter(\.isNumber).count
    return letters > 0 && letters > digits
  }

  /// A human name read out of an email identity key's local part, or nil when the local part is not
  /// name-shaped. `dana.wu@example.com` → "Dana Wu"; `r8809kwstey@example.cn` → nil.
  ///
  /// A local part containing digits is rejected outright: mixed alphanumerics are handles and
  /// throwaway addresses, and a wrong name is worse than no name.
  static func fromEmailLocalPart(_ key: String) -> String? {
    let lowered = key.lowercased()
    guard let at = lowered.firstIndex(of: "@"), !lowered.hasSuffix("@lid") else { return nil }
    let local = String(lowered[lowered.startIndex..<at])
    let tokens = local.split(whereSeparator: { $0 == "." || $0 == "_" || $0 == "-" || $0 == "+" })
      .map(String.init)
    guard !tokens.isEmpty, tokens.allSatisfy({ $0.allSatisfy(\.isLetter) }) else { return nil }
    guard tokens.contains(where: { $0.count >= 3 }) else { return nil }
    let name = tokens.map { $0.prefix(1).uppercased() + $0.dropFirst() }.joined(separator: " ")
    return isHumanShaped(name) ? name : nil
  }

  /// The human name a previous run on this machine recorded for this identity key, if it recorded
  /// one. `PeopleIdentityLinks` stores whatever the display name was at the time, which for an
  /// unnamed person is their phone number — so the shape check is what makes this a name source
  /// rather than an echo.
  static func durableName(forKey key: String, links: PeopleIdentityLinks) -> String? {
    guard let stored = links.byKey[key]?.name, stored != key, isHumanShaped(stored) else { return nil }
    return stored
  }

  /// Resolve one identity key's display name by exhausting every source, strongest first.
  ///
  /// `fallback` is the raw handle sample the pipeline uses today (a phone number, an address). It is
  /// still returned as the label — a card has to say *something* — but it is reported as
  /// `.handle`, which is what the selection stage reads as "we could not name this node".
  static func resolve(
    key: String, addressBook: String?, exportContact: String?, links: PeopleIdentityLinks,
    fallback: String
  ) -> (name: String, source: PersonNameSource) {
    if let book = addressBook, isHumanShaped(book) { return (trim(book), .addressBook) }
    if let export = exportContact, isHumanShaped(export) { return (trim(export), .exportContact) }
    if let durable = durableName(forKey: key, links: links) { return (trim(durable), .durable) }
    if let derived = fromEmailLocalPart(key) { return (derived, .emailLocalPart) }
    return (fallback, .handle)
  }

  private static func trim(_ value: String) -> String {
    value.trimmingCharacters(in: .whitespacesAndNewlines)
  }
}

/// Decides which canonical nodes become people, and records why each of the rest did not.
///
/// Pure by construction: everything it needs is already computed by the graph pipeline, so the whole
/// rule can be asserted over synthetic `(People, Graph, Communities)` values with no export, no
/// files and no address book.
enum PeopleSelection {

  /// Why a node did not become a person. One reason per node — the first bar it failed — so the
  /// explanation shown to the user is the actual cause and not a summary of several.
  enum DropReason: String, Sendable, CaseIterable {
    /// The node's only identity is a platform-internal token (an unbridged WhatsApp `@lid`). There
    /// is no phone number and no address: it cannot be named, cannot be messaged, and will never
    /// become nameable. 988 of the 1,825 measured cold-start nodes were exactly this.
    case unaddressable
    /// Never corresponded, and every group shared with the user is larger than the graph's group
    /// ceiling. Being row 412 of a 591-member broadcast list is not a relationship.
    case broadcastListOnly
    /// Never corresponded and shares no usable group at all — an address the export knows about
    /// with nothing behind it. Kept distinct from `broadcastListOnly` so the reason shown to the
    /// user is the one that is actually true of them.
    case noSignal
    /// Shares a real (small) group but has never exchanged a message and could not be named by any
    /// source. The card would be a bare phone number with no thread behind it.
    case groupOnlyUnnamed
    /// Messages exist but the exchange was one-directional — they wrote and were never answered, or
    /// were written to and never replied — and no source could name them. This is the shape of
    /// delivery notices, verification codes and marketing blasts.
    case oneWayUnnamed

    /// Short human explanation, shown where the UI accounts for who is missing.
    var explanation: String {
      switch self {
      case .unaddressable: return "no phone number or address to identify them by"
      case .broadcastListOnly: return "only seen inside large broadcast groups"
      case .noSignal: return "no messages and no shared group"
      case .groupOnlyUnnamed: return "in a shared group, but never messaged and unnamed"
      case .oneWayUnnamed: return "one-way messages only, and unnamed"
      }
    }
  }

  /// One node that did not become a person, with the reason and enough context to explain it.
  struct Drop: Sendable, Equatable {
    let id: String
    let name: String
    let reason: DropReason
    /// A group this node appeared in, when one is known — what makes the drop concrete rather than
    /// a category ("only seen in Cold Email Club").
    let detail: String?
  }

  /// The complete partition of the candidate nodes. `featured.count + drops.count` is always the
  /// number of canonical nodes that went in: no node is silently lost, and none is counted twice.
  struct Outcome: Sendable {
    /// Ids that become people, in the graph's own id order (stable across runs).
    let featured: [String]
    let drops: [Drop]

    var featuredIDs: Set<String> { Set(featured) }
    var candidateCount: Int { featured.count + drops.count }

    /// Drop counts keyed by `DropReason.rawValue`, for the stats block and the UI's accounting.
    var countsByReason: [String: Int] {
      var counts: [String: Int] = [:]
      for drop in drops { counts[drop.reason.rawValue, default: 0] += 1 }
      return counts
    }

    static let empty = Outcome(featured: [], drops: [])
  }

  /// Apply the rule to every canonical node.
  ///
  /// Three bars, in order; the first one a node fails is its stated reason.
  ///
  /// 1. **Can we address them?** At least one identity key that is a phone number or a real email
  ///    address. A node known only by an opaque token fails.
  /// 2. **Is there any evidence of a relationship?** Either messages exist, or they share at least
  ///    one group the graph itself accepts as a group (2…`maxGroup` resolved members — the same
  ///    ceiling the edge builder uses, so "real group" means one thing in this codebase).
  /// 3. **Can we say who they are?** Either a name from any source, or a two-way exchange, which
  ///    makes the thread itself the identity: you wrote to them and they wrote back, so the card is
  ///    actionable even while it reads as a phone number. When a connector does not report message
  ///    direction the exchange is not *known* to be one-way, so this bar passes on correspondence
  ///    alone — the reason only fires on evidence we actually have.
  ///
  /// The bias is toward dropping. A person wrongly hidden reappears the moment they are named or
  /// answered; 1,825 rows never become usable.
  static func select(
    people: PeopleGraphBuilder.People, graph: PeopleGraphBuilder.Graph,
    communities: PeopleGraphBuilder.Communities
  ) -> Outcome {
    var featured: [String] = []
    var drops: [Drop] = []
    // Inverted once for the whole run: per-person key lookup would make a 1,800-node address book
    // quadratic for no gain.
    let identityKeys = people.identityKeysByID()

    for id in people.canonByID.keys.sorted() {
      guard let canon = people.canonByID[id] else { continue }
      let keys = (identityKeys[id] ?? .none).all
      let detail = firstGroupName(forID: id, communities: communities)

      func drop(_ reason: DropReason) {
        drops.append(Drop(id: id, name: canon.name, reason: reason, detail: detail))
      }

      // 1. addressable?
      guard keys.contains(where: isAddressable) else {
        drop(.unaddressable)
        continue
      }

      // 2. any evidence of a relationship?
      let corresponded = canon.messageCount > 0
      let sharesRealGroup = (graph.sharedGroupCountByID[id] ?? 0) > 0
      guard corresponded || sharesRealGroup else {
        drop((graph.broadcastGroupCountByID[id] ?? 0) > 0 ? .broadcastListOnly : .noSignal)
        continue
      }

      // 3. can we say who they are?
      if canon.nameSource.isNamed {
        featured.append(id)
        continue
      }
      guard corresponded else {
        drop(.groupOnlyUnnamed)
        continue
      }
      guard isTwoWay(canon) else {
        drop(.oneWayUnnamed)
        continue
      }
      featured.append(id)
    }

    return Outcome(featured: featured, drops: drops)
  }

  /// Names safe to persist as this identity's durable name: only the ones a source asserted.
  /// A phone-number fallback is not a name, and a name read off an email address must not come back
  /// on the next run as though the address book had given it.
  static func assertedNames(in people: PeopleGraphBuilder.People) -> [String: String] {
    var out: [String: String] = [:]
    for (id, canon) in people.canonByID where canon.nameSource.isAsserted { out[id] = canon.name }
    return out
  }

  /// Turn a `dropped_reasons` map into the sentence the People tab shows under its stat line —
  /// biggest reason first, capped so the header stays a header. Nil when nothing was dropped.
  static func summarize(droppedReasons: [String: Int]) -> String? {
    guard !droppedReasons.isEmpty else { return nil }
    return
      droppedReasons
      .sorted { $0.value != $1.value ? $0.value > $1.value : $0.key < $1.key }
      .prefix(3)
      .map { "\($0.value.formatted()) \(DropReason(rawValue: $0.key)?.explanation ?? $0.key)" }
      .joined(separator: " · ")
  }

  /// An identity key we could put in front of a human: a phone key (the pipeline's `phone_last10`)
  /// or a real email address. Everything else — an unbridged `@lid`, a bare service token — is a
  /// platform internal.
  static func isAddressable(_ key: String) -> Bool {
    if key.contains("@") { return !key.lowercased().hasSuffix("@lid") }
    return key.count >= 10 && key.allSatisfy(\.isNumber)
  }

  /// True unless the connector reported message direction *and* reported it as one-directional.
  /// Absent direction data is not evidence of a broadcast, so it passes.
  private static func isTwoWay(_ canon: PeopleGraphBuilder.Canon) -> Bool {
    guard let sent = canon.sentCount, let received = canon.receivedCount else { return true }
    return sent > 0 && received > 0
  }

  private static func firstGroupName(
    forID id: String, communities: PeopleGraphBuilder.Communities
  ) -> String? {
    guard let entry = communities.groupsByPersonID[id]?.first else { return nil }
    return entry["name"] as? String
  }
}

extension PeopleGraphBuilder.People {
  /// The companion of `namesByID()` for the durable identity store: only names a source asserted.
  /// See `PeopleSelection.assertedNames` for why the unfiltered map must not be persisted.
  func assertedNamesByID() -> [String: String] { PeopleSelection.assertedNames(in: self) }
}
