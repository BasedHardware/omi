import Contacts
import Foundation

/// Resolves an iMessage handle (phone/email) to a contact display name via the
/// Contacts framework. Best-effort and cached: if Contacts access is denied or a
/// handle has no match, callers fall back to the raw handle.
///
/// Requires `NSContactsUsageDescription` in Info.plist.
actor IMessageContactResolver {
  static let shared = IMessageContactResolver()

  private let store = CNContactStore()
  private var cache: [String: String] = [:]  // handle -> resolved name ("" = looked up, no match)
  private var authChecked = false
  private var authorized = false

  /// Returns the display name for a handle, or nil if unknown / not permitted.
  func displayName(for handle: String) async -> String? {
    let key = handle.trimmingCharacters(in: .whitespacesAndNewlines)
    guard !key.isEmpty else { return nil }
    if let cached = cache[key] { return cached.isEmpty ? nil : cached }
    guard await ensureAccess() else { return nil }

    let name = lookup(handle: key)
    cache[key] = name ?? ""
    return name
  }

  private func ensureAccess() async -> Bool {
    if authChecked { return authorized }
    let status = CNContactStore.authorizationStatus(for: .contacts)
    switch status {
    case .authorized:
      authChecked = true
      authorized = true
    case .denied, .restricted:
      authChecked = true
      authorized = false
    default:
      let granted = await withCheckedContinuation { (cont: CheckedContinuation<Bool, Never>) in
        store.requestAccess(for: .contacts) { ok, _ in cont.resume(returning: ok) }
      }
      authChecked = true
      authorized = granted
    }
    return authorized
  }

  private func lookup(handle: String) -> String? {
    var keys: [CNKeyDescriptor] = [
      CNContactNicknameKey as CNKeyDescriptor,
      CNContactOrganizationNameKey as CNKeyDescriptor,
    ]
    keys.append(CNContactFormatter.descriptorForRequiredKeys(for: .fullName))

    let predicate: NSPredicate
    if handle.contains("@") {
      predicate = CNContact.predicateForContacts(matchingEmailAddress: handle)
    } else {
      predicate = CNContact.predicateForContacts(matching: CNPhoneNumber(stringValue: handle))
    }

    do {
      let matches = try store.unifiedContacts(matching: predicate, keysToFetch: keys)
      guard let contact = matches.first else { return nil }
      if let full = CNContactFormatter.string(from: contact, style: .fullName),
        !full.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
      {
        return full
      }
      if !contact.nickname.isEmpty { return contact.nickname }
      if !contact.organizationName.isEmpty { return contact.organizationName }
      return nil
    } catch {
      return nil
    }
  }
}
