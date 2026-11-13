import OmiComponents
import OmiCore
import OmiDesign
import OmiService
import SwiftUI
#if canImport(MessageUI) && canImport(ContactsUI)
    import Contacts
    import ContactsUI
    import MessageUI
#endif

/// "Share via SMS" (Flutter `share_to_contacts_sheet`): pick contacts' numbers, then Messages
/// opens with "Here's what we just discussed: <link>" to them. Omi never sends anything; the
/// user sends from the composer. The link needs the conversation shared, so a private one is
/// shared first and goes back to private when the message is not sent.
struct ShareBySMS: ViewModifier {
    @Binding var isActive: Bool
    let conversation: Conversation
    let onNotice: (String) -> Void
    @Environment(ConversationsStore.self) private var conversations
    @State private var message: SMSDraft?

    func body(content: Content) -> some View {
        #if canImport(MessageUI) && canImport(ContactsUI)
            content
                .sheet(isPresented: $isActive) {
                    ContactNumberPicker { numbers in
                        isActive = false
                        if !numbers.isEmpty { Task { await compose(to: numbers) } }
                    }
                    .ignoresSafeArea()
                }
                .sheet(item: $message) { draft in
                    MessageComposer(draft: draft) { sent in
                        message = nil
                        if !sent, draft.madeShared { Task { await conversations.setVisibility(draft.conversationID, .private) } }
                    }
                    .ignoresSafeArea()
                }
        #else
            content
        #endif
    }

    private func compose(to numbers: [String]) async {
        let id = conversation.id
        let wasPrivate = conversation.visibility == .private
        if wasPrivate, await !(conversations.setVisibility(id, .shared)) {
            return onNotice(L("failedToPrepareConversationForSharing"))
        }
        #if canImport(MessageUI)
            guard MFMessageComposeViewController.canSendText() else {
                if wasPrivate { await conversations.setVisibility(id, .private) }
                return onNotice(L("couldNotOpenSmsApp"))
            }
        #endif
        // After the contact picker has gone, so the composer is not dropped mid-dismissal.
        try? await Task.sleep(for: .milliseconds(500))
        message = SMSDraft(
            conversationID: id, recipients: numbers,
            body: L("heresWhatWeDiscussed", Conversation.shareURL(id: id).absoluteString), madeShared: wasPrivate
        )
    }
}

/// A message waiting in the composer.
struct SMSDraft: Identifiable {
    let id = UUID()
    let conversationID: String
    let recipients: [String]
    let body: String
    /// The conversation was private and was shared for this message.
    let madeShared: Bool
}

#if canImport(MessageUI) && canImport(ContactsUI)
    /// The system contact picker, phone numbers only, several at once (no Contacts permission:
    /// the picker runs outside the app).
    struct ContactNumberPicker: UIViewControllerRepresentable {
        let onPick: ([String]) -> Void

        func makeCoordinator() -> Coordinator {
            Coordinator(onPick: onPick)
        }

        func makeUIViewController(context: Context) -> CNContactPickerViewController {
            let picker = CNContactPickerViewController()
            picker.delegate = context.coordinator
            picker.displayedPropertyKeys = [CNContactPhoneNumbersKey]
            picker.predicateForEnablingContact = NSPredicate(format: "phoneNumbers.@count > 0")
            picker.predicateForSelectionOfProperty = NSPredicate(format: "key == 'phoneNumbers'")
            return picker
        }

        func updateUIViewController(_: CNContactPickerViewController, context _: Context) {}

        final class Coordinator: NSObject, CNContactPickerDelegate {
            let onPick: ([String]) -> Void

            init(onPick: @escaping ([String]) -> Void) {
                self.onPick = onPick
            }

            func contactPicker(_: CNContactPickerViewController, didSelect contactProperties: [CNContactProperty]) {
                onPick(contactProperties.compactMap { ($0.value as? CNPhoneNumber)?.stringValue })
            }

            func contactPickerDidCancel(_: CNContactPickerViewController) {
                onPick([])
            }
        }
    }

    /// Messages' composer with the recipients and text filled in; `onFinish(true)` when sent.
    struct MessageComposer: UIViewControllerRepresentable {
        let draft: SMSDraft
        let onFinish: (Bool) -> Void

        func makeCoordinator() -> Coordinator {
            Coordinator(onFinish: onFinish)
        }

        func makeUIViewController(context: Context) -> MFMessageComposeViewController {
            let composer = MFMessageComposeViewController()
            composer.recipients = draft.recipients
            composer.body = draft.body
            composer.messageComposeDelegate = context.coordinator
            return composer
        }

        func updateUIViewController(_: MFMessageComposeViewController, context _: Context) {}

        final class Coordinator: NSObject, MFMessageComposeViewControllerDelegate {
            let onFinish: (Bool) -> Void

            init(onFinish: @escaping (Bool) -> Void) {
                self.onFinish = onFinish
            }

            func messageComposeViewController(_: MFMessageComposeViewController, didFinishWith result: MessageComposeResult) {
                onFinish(result == .sent)
            }
        }
    }
#endif
