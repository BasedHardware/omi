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
/// The people-intelligence engine deliberately never persists a phone number or email on a
/// person card (`PeopleGraphBuilder.createPeople` writes identity, channels and social fields
/// only), so a handle has to be recovered when the user asks to send something. Two sources,
/// in order:
///
///  1. **Contacts** — the phone/email map the graph builder already reads, inverted from
///     `phone → name` to `name → handles` and widened to email addresses.
///  2. **`imessage_export.json` / `whatsapp_export.json`** — the raw handles the exporter
///     persisted. This is what covers people who were never resolved to a contact card: their
///     person id *is* the slug of the raw handle.
///
/// Matching is on `slug(name)` — byte-identical to the slug that produced the person id — so a
/// contact card and a person card line up without any new identity concept.
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
      contacts: loadContacts(),
      exportFileURLs: exports
    )
  }

  /// Seam for tests: resolve against supplied contacts and export files only.
  nonisolated static func resolve(
    personID: String,
    contactName: String?,
    displayName: String,
    contacts: [ContactHandleRecord],
    exportFileURLs: [URL]
  ) -> PersonHandles {
    let keys = identityKeys(personID: personID, contactName: contactName, displayName: displayName)
    guard !keys.isEmpty else { return .none }

    var phones = DedupedHandles(normalize: phoneKey)
    var emails = DedupedHandles(normalize: { $0.lowercased() })

    // Contacts first: a real address-book card is the highest-quality handle we have.
    for contact in contacts where keys.contains(slug(contact.name)) {
      for phone in contact.phones { phones.insert(phone) }
      for email in contact.emails { emails.insert(email) }
    }

    // Then the raw export handles, resolved to a name exactly the way the graph builder does.
    let contactNameByPhone = phoneNameMap(contacts)
    for url in exportFileURLs {
      guard let root = PeopleGraphBuilder.readExport(at: url) else { continue }
      for handle in root.handles {
        let raw = handle.handle.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !raw.isEmpty else { continue }
        let resolvedName =
          contactNameByPhone[phoneKey(raw)] ?? nonEmpty(handle.contactName) ?? raw
        guard keys.contains(slug(resolvedName)) else { continue }
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
  /// (`PeopleGraphBuilder.requestContactsAccessIfNeeded()` owns the one-time request.)
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

  /// The slugs a person can legitimately be addressed by. The person id is already a slug, and
  /// both names are slugged so an export row or contact card matches the same way.
  private nonisolated static func identityKeys(
    personID: String, contactName: String?, displayName: String
  ) -> Set<String> {
    var keys: Set<String> = []
    for candidate in [personID, contactName, displayName] {
      guard let value = nonEmpty(candidate) else { continue }
      keys.insert(slug(value))
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

  /// Mirrors `PeopleGraphBuilder.slug` exactly — person ids are produced by that function, so
  /// any drift here silently stops matching.
  nonisolated static func slug(_ name: String) -> String {
    var out = ""
    var lastDash = false
    for ch in name.lowercased() {
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
