import Contacts
import Foundation

/// Resolves people to messaging handles from the local Contacts store.
///
/// This exists so `send_message` receives a handle the user can recognize on the
/// approval card rather than the agent guessing a phone number.
struct ContactRecord: Identifiable, Sendable {
  let id: String
  let displayName: String
  let organization: String
  let phoneNumbers: [ContactHandle]
  let emailAddresses: [ContactHandle]

  /// The handle to offer `send_message` first: a mobile number when one exists,
  /// then any other number, then email.
  var preferredMessagingHandle: String? {
    if let mobile = phoneNumbers.first(where: { $0.isMobile }) {
      return mobile.value
    }
    return phoneNumbers.first?.value ?? emailAddresses.first?.value
  }
}

struct ContactHandle: Sendable {
  /// Localized, for the approval card the user reads.
  let label: String
  /// The `CNLabelPhoneNumber*` constant, for the code that has to choose.
  let rawLabel: String
  let value: String

  /// Matched on the constant, never on the localized text. `localizedString(forLabel:)`
  /// returns the user's language — "Mobile" only on an English Mac — so a
  /// substring test for "mobile" failed everywhere else and the preferred handle
  /// silently fell through to whatever number came first, often a home or work
  /// line. The tool contract promises a mobile number; sending to the landline
  /// instead is a wrong-recipient bug, not a cosmetic one.
  var isMobile: Bool {
    rawLabel == CNLabelPhoneNumberMobile || rawLabel == CNLabelPhoneNumberiPhone
  }
}

enum ContactsReaderError: LocalizedError {
  case authorizationDenied
  case authorizationRestricted
  case lookupFailed(reason: String)

  var errorDescription: String? {
    switch self {
    case .authorizationDenied:
      return
        "Omi needs Contacts permission to resolve names to phone numbers. Grant it in System Settings > Privacy & Security > Contacts."
    case .authorizationRestricted:
      return "Contacts access is restricted on this Mac by policy."
    case .lookupFailed(let reason):
      return "Contacts lookup failed: \(reason)"
    }
  }

  var reasonCode: String {
    switch self {
    case .authorizationDenied: return "authorization_denied"
    case .authorizationRestricted: return "authorization_restricted"
    case .lookupFailed: return "lookup_failed"
    }
  }

  var requiredPermission: String? {
    switch self {
    case .authorizationDenied: return "contacts"
    case .authorizationRestricted, .lookupFailed: return nil
    }
  }
}

enum ContactsReaderService {
  static func authorizationStatus() -> CNAuthorizationStatus {
    CNContactStore.authorizationStatus(for: .contacts)
  }

  static func requestAccess() async -> Bool {
    return await ChatToolExecutor.awaitCancellablePermissionRequest { completion in
      let store = CNContactStore()
      store.requestAccess(for: .contacts) { granted, _ in
        completion(granted)
      }
    } ?? false
  }

  static func search(query: String, limit: Int) throws -> [ContactRecord] {
    switch authorizationStatus() {
    case .denied: throw ContactsReaderError.authorizationDenied
    case .restricted: throw ContactsReaderError.authorizationRestricted
    default: break
    }

    let bounded = max(1, min(limit, 50))
    let trimmed = query.trimmingCharacters(in: .whitespacesAndNewlines)
    guard !trimmed.isEmpty else { return [] }

    let store = CNContactStore()
    let keys: [CNKeyDescriptor] = [
      CNContactFormatter.descriptorForRequiredKeys(for: .fullName),
      CNContactOrganizationNameKey as CNKeyDescriptor,
      CNContactPhoneNumbersKey as CNKeyDescriptor,
      CNContactEmailAddressesKey as CNKeyDescriptor,
    ]

    do {
      let matches = try store.unifiedContacts(
        matching: CNContact.predicateForContacts(matchingName: trimmed),
        keysToFetch: keys)
      return matches.prefix(bounded).map { contact in
        ContactRecord(
          id: contact.identifier,
          displayName: CNContactFormatter.string(from: contact, style: .fullName) ?? "",
          organization: contact.organizationName,
          phoneNumbers: contact.phoneNumbers.map { entry in
            ContactHandle(
              label: entry.label.map { CNLabeledValue<NSString>.localizedString(forLabel: $0) } ?? "",
              rawLabel: entry.label ?? "",
              value: entry.value.stringValue)
          },
          emailAddresses: contact.emailAddresses.map { entry in
            ContactHandle(
              label: entry.label.map { CNLabeledValue<NSString>.localizedString(forLabel: $0) } ?? "",
              rawLabel: entry.label ?? "",
              value: entry.value as String)
          })
      }
    } catch {
      throw ContactsReaderError.lookupFailed(reason: error.localizedDescription)
    }
  }
}
