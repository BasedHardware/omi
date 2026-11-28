import Foundation
import OmiCore

/// The phone's contacts and message composer for tests: records what the app asked the system
/// for, answers with what the test set.
@MainActor
public final class FakeDeviceTools: DeviceToolPerforming {
    public var canSendMessages: Bool
    public var contactsAccess: ContactsAccess
    /// What the system prompt answers when asked.
    public var accessAfterPrompt: ContactsAccess = .granted
    public var contacts: [DeviceContact]
    /// What the composer's sheet ends with.
    public var composeOutcome: MessageComposeOutcome = .sent
    /// One entry per system interaction: `search:<query>`, `prompt`, `compose:<to>:<text>`.
    public private(set) var log: [String] = []

    public init(canSendMessages: Bool = true, contactsAccess: ContactsAccess = .granted, contacts: [DeviceContact] = FakeDeviceTools.anna) {
        self.canSendMessages = canSendMessages
        self.contactsAccess = contactsAccess
        self.contacts = contacts
    }

    public nonisolated static let anna: [DeviceContact] = [
        DeviceContact(
            id: "c-anna", name: "Anna Schmidt", phoneNumbers: [.init(label: "mobile", value: "+49 170 1234567")],
            emailAddresses: [.init(label: "work", value: "anna@example.com")], preferredHandle: "+49 170 1234567"
        ),
        DeviceContact(
            id: "c-annabel", name: "Annabel Lee", phoneNumbers: [.init(label: "home", value: "+1 415 555 0100")],
            emailAddresses: [], preferredHandle: "+1 415 555 0100"
        ),
    ]

    public func searchContacts(_ query: String, limit: Int) async -> [DeviceContact] {
        log.append("search:\(query)")
        return Array(contacts.filter { $0.name.localizedCaseInsensitiveContains(query) }.prefix(limit))
    }

    public func requestContactsAccess() async -> ContactsAccess {
        log.append("prompt")
        contactsAccess = accessAfterPrompt
        return contactsAccess
    }

    public func composeMessage(to recipients: [String], text: String, subject _: String?) async -> MessageComposeOutcome {
        log.append("compose:\(recipients.joined(separator: ",")):\(text)")
        return composeOutcome
    }
}
