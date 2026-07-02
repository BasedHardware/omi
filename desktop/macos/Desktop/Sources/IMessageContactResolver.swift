import Contacts
import Foundation

/// Resolves an iMessage handle (phone/email) to a contact name and photo.
///
/// Uses Apple's Contacts framework (`CNContactStore`) so the OS shows a scoped
/// Contacts permission prompt (`NSContactsUsageDescription`) instead of reading the
/// AddressBook SQLite database directly. Best-effort: if access is denied/restricted,
/// or a handle has no matching contact, resolution degrades to nil and callers fall
/// back to the raw handle / initials.
///
/// Note: on self-signed local dev builds the Contacts TCC prompt may not fire, in
/// which case lookups simply return nil; production signed/notarized builds get the
/// prompt and full resolution.
actor IMessageContactResolver {
  static let shared = IMessageContactResolver()

  private let store = CNContactStore()

  // Cached authorization state so we only prompt / check once per session.
  private var authChecked = false
  private var authorized = false

  // Per-handle resolved cache (name/image), including negative results, to avoid
  // repeated store queries for the same handle.
  private var cache: [String: (name: String?, image: Data?)] = [:]

  // Contacts has no email predicate, so email resolution enumerates the store once
  // and builds an index lazily. Keyed by lowercased email address.
  private var emailIndexBuilt = false
  private var nameByEmail: [String: String] = [:]
  private var imageByEmail: [String: Data] = [:]

  private static let keysToFetch: [CNKeyDescriptor] = [
    CNContactGivenNameKey as CNKeyDescriptor,
    CNContactFamilyNameKey as CNKeyDescriptor,
    CNContactNicknameKey as CNKeyDescriptor,
    CNContactOrganizationNameKey as CNKeyDescriptor,
    CNContactPhoneNumbersKey as CNKeyDescriptor,
    CNContactEmailAddressesKey as CNKeyDescriptor,
    CNContactThumbnailImageDataKey as CNKeyDescriptor,
  ]

  func displayName(for handle: String) async -> String? {
    await resolve(handle).name
  }

  func imageData(for handle: String) async -> Data? {
    await resolve(handle).image
  }

  /// Enumerates every unified contact and returns a sync payload per contact for
  /// upload to the backend. Handles are the raw phone `stringValue`s plus lowercased
  /// emails — the backend canonicalizes them. Contacts with no usable name AND no
  /// handles are skipped. Degrades to `[]` if Contacts access isn't granted.
  func allContacts() async -> [IMessageContactSyncPayload] {
    guard await ensureAuthorized() else { return [] }
    let request = CNContactFetchRequest(keysToFetch: Self.keysToFetch)
    request.sortOrder = .none
    var payloads: [IMessageContactSyncPayload] = []
    let ok = (try? store.enumerateContacts(with: request) { contact, _ in
      var handles: [String] = []
      for phone in contact.phoneNumbers {
        let value = phone.value.stringValue.trimmingCharacters(in: .whitespacesAndNewlines)
        if !value.isEmpty { handles.append(value) }
      }
      for email in contact.emailAddresses {
        let addr = (email.value as String).lowercased().trimmingCharacters(in: .whitespacesAndNewlines)
        if !addr.isEmpty { handles.append(addr) }
      }
      let name = Self.composeName(contact)
      // Skip contacts we can't key on at all (no name and no handles).
      guard name != nil || !handles.isEmpty else { return }
      payloads.append(IMessageContactSyncPayload(name: name ?? "", handles: handles))
    }) != nil
    return ok ? payloads : []
  }

  /// Force a re-check on next lookup (e.g. after contacts or authorization change).
  func resetAuth() {
    authChecked = false
    authorized = false
    cache.removeAll()
    emailIndexBuilt = false
    nameByEmail.removeAll()
    imageByEmail.removeAll()
  }

  // MARK: - lookup

  private func resolve(_ handle: String) async -> (name: String?, image: Data?) {
    let h = handle.trimmingCharacters(in: .whitespacesAndNewlines)
    guard !h.isEmpty else { return (nil, nil) }
    if let cached = cache[h] { return cached }
    // Don't cache while unauthorized — access may be granted later this session.
    guard await ensureAuthorized() else { return (nil, nil) }

    let result = h.contains("@") ? resolveEmail(h) : resolvePhone(h)
    cache[h] = result
    return result
  }

  /// Resolves a phone handle via a Contacts predicate, then verifies the match by
  /// normalized digits so international numbers sharing a suffix don't collide.
  private func resolvePhone(_ handle: String) -> (name: String?, image: Data?) {
    guard let wantKey = Self.normalizedPhoneKey(handle) else { return (nil, nil) }
    let predicate = CNContact.predicateForContacts(matching: CNPhoneNumber(stringValue: handle))
    guard let matches = try? store.unifiedContacts(matching: predicate, keysToFetch: Self.keysToFetch) else {
      return (nil, nil)
    }
    // Require an exact normalized-digit match (predicate matching is looser and can
    // match on a shared suffix); if none match, treat the handle as unknown.
    guard
      let contact = matches.first(where: { contact in
        contact.phoneNumbers.contains { Self.normalizedPhoneKey($0.value.stringValue) == wantKey }
      })
    else { return (nil, nil) }
    return (Self.composeName(contact), Self.imageData(from: contact))
  }

  private func resolveEmail(_ handle: String) -> (name: String?, image: Data?) {
    buildEmailIndexIfNeeded()
    let key = handle.lowercased()
    return (nameByEmail[key], imageByEmail[key])
  }

  private func buildEmailIndexIfNeeded() {
    if emailIndexBuilt { return }
    let request = CNContactFetchRequest(keysToFetch: Self.keysToFetch)
    request.sortOrder = .none
    do {
      try store.enumerateContacts(with: request) { contact, _ in
        guard !contact.emailAddresses.isEmpty else { return }
        let name = Self.composeName(contact)
        let image = Self.imageData(from: contact)
        for email in contact.emailAddresses {
          let addr = (email.value as String).lowercased()
          guard !addr.isEmpty else { continue }
          if let name, nameByEmail[addr] == nil { nameByEmail[addr] = name }
          if let image, imageByEmail[addr] == nil { imageByEmail[addr] = image }
        }
      }
      // Mark built only after a successful enumeration, so a transient store
      // failure doesn't permanently disable email resolution for the session.
      emailIndexBuilt = true
    } catch {
      NSLog("IMessageContactResolver: contact enumeration failed, will retry: \(error.localizedDescription)")
    }
  }

  // MARK: - authorization

  private func ensureAuthorized() async -> Bool {
    if authChecked { return authorized }
    switch CNContactStore.authorizationStatus(for: .contacts) {
    case .authorized:
      authorized = true
    case .notDetermined:
      authorized = (try? await store.requestAccess(for: .contacts)) ?? false
    default:  // .denied, .restricted (and any future non-granting states)
      authorized = false
    }
    authChecked = true
    return authorized
  }

  // MARK: - helpers

  /// Normalizes a phone number to a lookup key by keeping the full digit string,
  /// only stripping a leading `1` from 11-digit US numbers. Matches
  /// `IMessageReaderService.prettyHandle` so distinct international numbers that
  /// share a 10-digit suffix (e.g. UK `+44 20 7946 0958` vs `020 7946 0958`) don't
  /// collapse to the same contact. Returns nil for numbers with fewer than 7 digits.
  static func normalizedPhoneKey(_ raw: String) -> String? {
    let digits = raw.filter { $0.isNumber }
    guard digits.count >= 7 else { return nil }
    if digits.count == 11 && digits.hasPrefix("1") { return String(digits.dropFirst()) }
    return digits
  }

  private static func composeName(_ contact: CNContact) -> String? {
    let full = "\(contact.givenName) \(contact.familyName)".trimmingCharacters(in: .whitespaces)
    if !full.isEmpty { return full }
    if !contact.nickname.isEmpty { return contact.nickname }
    if !contact.organizationName.isEmpty { return contact.organizationName }
    return nil
  }

  private static func imageData(from contact: CNContact) -> Data? {
    guard let data = contact.thumbnailImageData, !data.isEmpty else { return nil }
    return data
  }
}
