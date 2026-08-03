import Contacts
import Foundation

/// The addressable handles for one person, in the order a composer should prefer them.
struct PersonHandles: Equatable, Sendable {
  let phones: [String]
  let emails: [String]

  var isEmpty: Bool { phones.isEmpty && emails.isEmpty }
  var preferredPhone: String? { phones.first }

  /// Recipients for a Messages composer: phone numbers first (iMessage/SMS), emails after
  /// (a valid iMessage address too, and the only option for email-only contacts).
  var recipients: [String] { phones + emails }

  static let none = PersonHandles(phones: [], emails: [])
}

/// One address-book card, flattened to the fields that matter for addressing. Keeping the
/// Contacts framework behind this type is what lets the matching rules be tested without a
/// live address book.
struct ContactHandleRecord: Equatable, Sendable {
  let name: String
  let phones: [String]
  let emails: [String]

  init(name: String, phones: [String] = [], emails: [String] = []) {
    self.name = name
    self.phones = phones
    self.emails = emails
  }
}

/// Resolves "how do I actually message this person" at send time.
///
/// A person card now carries the identity keys the graph resolved it by (`handles`:
/// `phone_last10` / lowercased handle — see `PersonIdentityKeys`), so the primary match is on
/// **identity**, not on a display name. What still has to be recovered here is the *dialable*
/// form of those keys — a bare last-10 is an identity, not a recipient — from two local sources:
///
///  1. **Contacts** — the phone/email map the graph builder already reads, inverted from
///     `phone → name` to `identity → handles` and widened to email addresses.
///  2. **`imessage_export.json` / `whatsapp_export.json`** — the raw handles the exporter
///     persisted. This is what covers people who were never resolved to a contact card.
///
/// Name-slug matching remains only as the fallback for a card written before handles were
/// persisted; it is the path that breaks the moment the user renames a contact, which is why it is
/// no longer the primary. The slug itself is `PeopleGraphBuilder.slug` — never a second copy,
/// because any drift between two copies silently stops matching.
///
/// Everything stays local: no network, and nothing is logged about who was resolved.
enum PersonHandleResolver {

  /// Resolve a person's handles from the local Contacts store and the on-device exports.
  ///
  /// Never call this on the main actor: it enumerates the address book and decodes a
  /// multi-hundred-KB export. A denied or undetermined Contacts grant is not an error — it
  /// just means the Contacts source contributes nothing.
  nonisolated static func resolve(
    personID: String,
    contactName: String?,
    displayName: String,
    identityKeys: PersonIdentityKeys = .none,
    uid: String? = nil
  ) -> PersonHandles {
    let userDir = PeopleUserDirectory.resolve(uid: uid)
    let exports = ["imessage_export.json", "whatsapp_export.json"].compactMap {
      userDir?.appendingPathComponent($0)
    }
    return resolve(
      personID: personID,
      contactName: contactName,
      displayName: displayName,
      identityKeys: identityKeys,
      contacts: loadContacts(),
      exportFileURLs: exports
    )
  }

  /// Seam for tests: resolve against supplied contacts and export files only.
  nonisolated static func resolve(
    personID: String,
    contactName: String?,
    displayName: String,
    identityKeys: PersonIdentityKeys = .none,
    contacts: [ContactHandleRecord],
    exportFileURLs: [URL]
  ) -> PersonHandles {
    // The card's persisted identity keys, normalized the same way handles are keyed everywhere.
    let identity = Set(identityKeys.all.map { $0.contains("@") ? $0.lowercased() : phoneKey($0) })
    // Fallback for cards written before identity keys were persisted: re-derive from the name.
    let nameKeys =
      identity.isEmpty
      ? nameSlugs(personID: personID, contactName: contactName, displayName: displayName) : []
    guard !identity.isEmpty || !nameKeys.isEmpty else { return .none }

    var phones = DedupedHandles(normalize: phoneKey)
    var emails = DedupedHandles(normalize: { $0.lowercased() })

    /// True when a handle-like string is one of this person's identity keys.
    func isIdentity(_ raw: String) -> Bool {
      identity.contains(raw.contains("@") ? raw.lowercased() : phoneKey(raw))
    }

    // Contacts first: a real address-book card is the highest-quality handle we have. Matched by
    // identity key when the card has one, so renaming the contact changes nothing.
    for contact in contacts {
      let matched =
        identity.isEmpty
        ? nameKeys.contains(PeopleGraphBuilder.slug(contact.name))
        : contact.phones.contains(where: isIdentity) || contact.emails.contains(where: isIdentity)
      guard matched else { continue }
      for phone in contact.phones { phones.insert(phone) }
      for email in contact.emails { emails.insert(email) }
    }

    // Then the raw export handles — the dialable form of an identity key, and the only source for
    // someone who was never resolved to a contact card.
    let contactNameByPhone = phoneNameMap(contacts)
    for url in exportFileURLs {
      guard let root = PeopleGraphBuilder.readExport(at: url) else { continue }
      for handle in root.handles {
        let raw = handle.handle.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !raw.isEmpty else { continue }
        if identity.isEmpty {
          let resolvedName = contactNameByPhone[phoneKey(raw)] ?? nonEmpty(handle.contactName) ?? raw
          guard nameKeys.contains(PeopleGraphBuilder.slug(resolvedName)) else { continue }
        } else {
          guard isIdentity(nonEmpty(handle.phoneLast10) ?? raw) || isIdentity(raw) else { continue }
        }
        if raw.contains("@") {
          emails.insert(raw)
        } else {
          phones.insert(raw)
        }
      }
    }

    return PersonHandles(phones: phones.values, emails: emails.values)
  }

  // MARK: - Contacts

  /// Reads the address book, but only when access is already granted — this never prompts.
  /// (`PeopleContactsAccess.prepareForNaming()` owns the one-time request.)
  private nonisolated static func loadContacts() -> [ContactHandleRecord] {
    guard CNContactStore.authorizationStatus(for: .contacts) == .authorized else { return [] }
    let keys: [CNKeyDescriptor] = [
      CNContactGivenNameKey as CNKeyDescriptor,
      CNContactFamilyNameKey as CNKeyDescriptor,
      CNContactOrganizationNameKey as CNKeyDescriptor,
      CNContactPhoneNumbersKey as CNKeyDescriptor,
      CNContactEmailAddressesKey as CNKeyDescriptor,
    ]
    var records: [ContactHandleRecord] = []
    do {
      try CNContactStore().enumerateContacts(with: CNContactFetchRequest(keysToFetch: keys)) {
        contact, _ in
        let name = displayName(of: contact)
        guard !name.isEmpty else { return }
        records.append(
          ContactHandleRecord(
            name: name,
            phones: contact.phoneNumbers.map { $0.value.stringValue },
            emails: contact.emailAddresses.map { $0.value as String }
          ))
      }
    } catch {
      // A revoked grant or an unreadable store means "no contact handles", never a throw.
      log("PersonHandleResolver: Contacts enumeration unavailable")
      return records
    }
    return records
  }

  /// Same rule as `PeopleGraphBuilder.contactDisplayName`: full name, else organization.
  private nonisolated static func displayName(of contact: CNContact) -> String {
    let full = "\(contact.givenName) \(contact.familyName)".trimmingCharacters(in: .whitespaces)
    if !full.isEmpty { return full }
    return contact.organizationName.trimmingCharacters(in: .whitespaces)
  }

  // MARK: - Matching helpers

  /// Legacy fallback only: the slugs a card with no persisted identity keys can be addressed by.
  /// This is the path a contact rename silently breaks — `slug(name)` changes, so the card stops
  /// matching its own handles — which is precisely why a card that carries `handles` never uses it.
  private nonisolated static func nameSlugs(
    personID: String, contactName: String?, displayName: String
  ) -> Set<String> {
    var keys: Set<String> = []
    for candidate in [personID, contactName, displayName] {
      guard let value = nonEmpty(candidate) else { continue }
      keys.insert(PeopleGraphBuilder.slug(value))
    }
    return keys
  }

  private nonisolated static func phoneNameMap(_ contacts: [ContactHandleRecord]) -> [String: String] {
    var map: [String: String] = [:]
    for contact in contacts where !contact.name.isEmpty {
      for phone in contact.phones {
        let key = phoneKey(phone)
        if map[key] == nil { map[key] = contact.name }
      }
    }
    return map
  }

  /// Stable identity for a phone-like string: its last 10 digits when it has that many (the
  /// same `phone_last10` key the exporter writes), otherwise the raw lowercased value so short
  /// codes and email-shaped handles still dedupe against themselves.
  private nonisolated static func phoneKey(_ value: String) -> String {
    let digits = value.filter { $0.isNumber }
    guard digits.count >= 10 else { return value.lowercased() }
    return String(digits.suffix(10))
  }

  private nonisolated static func nonEmpty(_ value: String?) -> String? {
    guard let trimmed = value?.trimmingCharacters(in: .whitespacesAndNewlines), !trimmed.isEmpty
    else { return nil }
    return trimmed
  }

  /// Order-preserving dedupe keyed on a normalized form, so "+1 (555) 010-1234" and
  /// "+15550101234" collapse to one recipient while keeping the first formatting seen.
  private struct DedupedHandles {
    private let normalize: (String) -> String
    private var seen: Set<String> = []
    private(set) var values: [String] = []

    init(normalize: @escaping (String) -> String) {
      self.normalize = normalize
    }

    mutating func insert(_ raw: String) {
      let trimmed = raw.trimmingCharacters(in: .whitespacesAndNewlines)
      guard !trimmed.isEmpty else { return }
      let key = normalize(trimmed)
      guard seen.insert(key).inserted else { return }
      values.append(trimmed)
    }
  }
}
