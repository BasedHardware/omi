import Contacts
import MessageUI
import OmiCore
import OmiService
import UIKit

/// The phone's side of Omi's device tools (backend `utils/device_tools.py`): contacts lookups
/// and the system message composer. iOS cannot send a message silently, so the composer is the
/// approval: the user sends (or not) in the system sheet, and only after tapping "Send" on
/// "Omi asks" opened it.
@MainActor
final class DeviceToolsPerformer: NSObject, DeviceToolPerforming {
    private var composeContinuation: CheckedContinuation<MessageComposeOutcome, Never>?

    /// Runs end with a notification when the app is away; Omi can ask mid-run (a message to send,
    /// which contact), and nothing happens without the user's tap.
    static func wire(agent: AgentStore, chat: ChatStore, log: DebugLog) {
        agent.onRunEnded = { task, finished in AgentNotifications.runEnded(task, finished: finished) }
        let performer = DeviceToolsPerformer()
        agent.deviceTools = performer
        agent.log = log
        chat.deviceTools = performer
    }

    var canSendMessages: Bool {
        MFMessageComposeViewController.canSendText()
    }

    var contactsAccess: ContactsAccess {
        Self.access(CNContactStore.authorizationStatus(for: .contacts))
    }

    func requestContactsAccess() async -> ContactsAccess {
        _ = try? await CNContactStore().requestAccess(for: .contacts)
        return contactsAccess
    }

    func searchContacts(_ query: String, limit: Int) async -> [DeviceContact] {
        guard contactsAccess.isUsable else { return [] }
        return await Task.detached(priority: .userInitiated) { Self.lookUp(query, limit: limit) }.value
    }

    func composeMessage(to recipients: [String], text: String, subject: String?) async -> MessageComposeOutcome {
        guard MFMessageComposeViewController.canSendText() else { return .unavailable }
        guard composeContinuation == nil, let presenter = Self.topViewController() else { return .failed }
        let composer = MFMessageComposeViewController()
        composer.messageComposeDelegate = self
        composer.recipients = recipients
        composer.body = text
        if let subject, !subject.isEmpty, MFMessageComposeViewController.canSendSubject() { composer.subject = subject }
        return await withCheckedContinuation { continuation in
            composeContinuation = continuation
            presenter.present(composer, animated: true)
        }
    }

    private nonisolated static func lookUp(_ query: String, limit: Int) -> [DeviceContact] {
        let keys: [any CNKeyDescriptor] = [
            CNContactFormatter.descriptorForRequiredKeys(for: .fullName),
            CNContactPhoneNumbersKey as any CNKeyDescriptor,
            CNContactEmailAddressesKey as any CNKeyDescriptor,
        ]
        let matches = (try? CNContactStore().unifiedContacts(
            matching: CNContact.predicateForContacts(matchingName: query),
            keysToFetch: keys
        )) ?? []
        return matches.prefix(max(1, min(limit, 50))).map { contact in
            let phones = contact.phoneNumbers.map { entry in
                DeviceContact.Handle(
                    label: entry.label.map { CNLabeledValue<NSString>.localizedString(forLabel: $0) } ?? "",
                    value: entry.value.stringValue
                )
            }
            let emails = contact.emailAddresses.map { entry in
                DeviceContact.Handle(
                    label: entry.label.map { CNLabeledValue<NSString>.localizedString(forLabel: $0) } ?? "",
                    value: entry.value as String
                )
            }
            // The mobile number by its constant, not its localized label (which is the user's language).
            let mobile = contact.phoneNumbers.first { $0.label == CNLabelPhoneNumberMobile || $0.label == CNLabelPhoneNumberiPhone }
            let preferred = mobile?.value.stringValue ?? phones.first?.value ?? emails.first?.value ?? ""
            return DeviceContact(
                id: contact.identifier, name: CNContactFormatter.string(from: contact, style: .fullName) ?? "",
                phoneNumbers: phones, emailAddresses: emails, preferredHandle: preferred
            )
        }
    }

    private static func access(_ status: CNAuthorizationStatus) -> ContactsAccess {
        switch status {
        case .authorized: .granted
        case .limited: .limited
        case .notDetermined: .notDetermined
        case .restricted: .restricted
        default: .denied
        }
    }

    private static func topViewController() -> UIViewController? {
        let scene = UIApplication.shared.connectedScenes.compactMap { $0 as? UIWindowScene }
            .first { $0.activationState == .foregroundActive }
        var top = scene?.windows.first(where: \.isKeyWindow)?.rootViewController
        while let presented = top?.presentedViewController {
            top = presented
        }
        return top
    }
}

extension DeviceToolsPerformer: MFMessageComposeViewControllerDelegate {
    nonisolated func messageComposeViewController(_ controller: MFMessageComposeViewController,
                                                  didFinishWith result: MessageComposeResult)
    {
        let outcome: MessageComposeOutcome = switch result {
        case .sent: .sent
        case .cancelled: .cancelled
        default: .failed
        }
        MainActor.assumeIsolated {
            controller.dismiss(animated: true)
            composeContinuation?.resume(returning: outcome)
            composeContinuation = nil
        }
    }
}
