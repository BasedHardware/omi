import ContactsUI
import OmiComponents
import OmiDesign
import OmiService
import SwiftUI

/// Starting a call: type a number on the keypad or pick one from Contacts (the system picker, no
/// contacts permission and no list of our own). Flutter `phone_calls_page` (keypad + contacts tabs).
struct PhoneDialerScreen: View {
    @Environment(PhoneCallStore.self) private var phone
    @Environment(\.dismiss) private var dismiss
    @State private var number = ""
    @State private var contactName: String?
    @State private var picksContact = false
    @State private var isStarting = false
    @State private var failure: PhoneCallFailure?

    var body: some View {
        NavigationStack {
            VStack(spacing: DS.Spacing.lg) {
                display
                PhoneKeypad { key in
                    contactName = nil
                    number.append(key)
                } onLongZero: {
                    number.append("+")
                }
                callButton
            }
            .padding(DS.Spacing.gutter)
            .frame(maxHeight: .infinity, alignment: .bottom)
            .background(DS.Palette.background)
            .navigationTitle(L("nativePhoneNewCall"))
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) { Button(L("cancel")) { dismiss() } }
                ToolbarItem(placement: .primaryAction) {
                    Button { picksContact = true } label: { Label(L("phoneContactsTab"), systemImage: "person.crop.circle") }
                        .accessibilityIdentifier("phone.pickContact")
                }
            }
            .background(ContactPhonePicker(isPresented: $picksContact) { name, picked in
                contactName = name
                number = PhoneNumberFormat.stripped(picked)
            })
            .alert(failure.map(PhoneCallWording.failure) ?? "", isPresented: failureShown) { Button(L("ok")) {} }
        }
    }

    private var failureShown: Binding<Bool> {
        Binding(get: { failure != nil }, set: { if !$0 { failure = nil } })
    }

    private var display: some View {
        VStack(spacing: DS.Spacing.xs) {
            if let contactName {
                Text(contactName).font(DS.Typography.sectionTitle)
            }
            HStack {
                Text(number.isEmpty ? L("phoneEnterNumber") : number)
                    .font(.system(size: 34, weight: .medium, design: .rounded).monospacedDigit())
                    .foregroundStyle(number.isEmpty ? DS.Palette.inkTertiary : DS.Palette.ink)
                    .lineLimit(1)
                    .minimumScaleFactor(0.5)
                    .frame(maxWidth: .infinity)
                    .contextMenu {
                        Button(L("paste"), systemImage: "doc.on.clipboard") { paste() }
                    }
                    .accessibilityIdentifier("phone.dialed")
                if !number.isEmpty {
                    Button {
                        number.removeLast()
                        if number.isEmpty { contactName = nil }
                    } label: { Image(systemName: "delete.left").font(.title2) }
                        .buttonStyle(.plain)
                        .foregroundStyle(DS.Palette.inkSecondary)
                        .accessibilityLabel(L("delete"))
                }
            }
            if number.isEmpty {
                Button(L("paste"), systemImage: "doc.on.clipboard") { paste() }
                    .buttonStyle(.omiPillSubtle)
            }
        }
        .frame(minHeight: 96)
    }

    private var callButton: some View {
        Button {
            Task { await call() }
        } label: {
            Group {
                if isStarting { ProgressView().tint(.white) } else { Image(systemName: "phone.fill").font(.title) }
            }
            .frame(width: 76, height: 76)
            .background(DS.Palette.success, in: Circle())
            .foregroundStyle(.white)
        }
        .buttonStyle(.plain)
        .disabled(number.isEmpty || isStarting)
        .opacity(number.isEmpty ? 0.5 : 1)
        .accessibilityLabel(L("phoneCallButton"))
        .accessibilityIdentifier("phone.call")
    }

    private func call() async {
        isStarting = true
        defer { isStarting = false }
        if await phone.call(number, contactName: contactName) {
            dismiss()
        } else {
            failure = phone.failure ?? .server(nil)
        }
    }

    /// Only the characters a number can have (Flutter `_sanitizePastedNumber`).
    private func paste() {
        guard let text = UIPasteboard.general.string else { return }
        let kept = text.filter { $0.isNumber || $0 == "+" || $0 == "*" || $0 == "#" }
        guard !kept.isEmpty else { return }
        number = kept
        contactName = nil
    }
}

/// The 12-key pad (letters under the digits); a long press on 0 types `+`.
struct PhoneKeypad: View {
    let onKey: (String) -> Void
    var onLongZero: (() -> Void)?

    private static let keys: [(String, String)] = [
        ("1", ""), ("2", "ABC"), ("3", "DEF"), ("4", "GHI"), ("5", "JKL"), ("6", "MNO"),
        ("7", "PQRS"), ("8", "TUV"), ("9", "WXYZ"), ("*", ""), ("0", "+"), ("#", ""),
    ]

    var body: some View {
        Grid(horizontalSpacing: DS.Spacing.xl, verticalSpacing: DS.Spacing.md) {
            ForEach(0 ..< 4, id: \.self) { row in
                GridRow {
                    ForEach(0 ..< 3, id: \.self) { column in
                        key(Self.keys[row * 3 + column])
                    }
                }
            }
        }
    }

    private func key(_ key: (digit: String, letters: String)) -> some View {
        Button {
            DSHaptics.selection()
            onKey(key.digit)
        } label: {
            VStack(spacing: 0) {
                Text(key.digit).font(.system(size: 30, weight: .regular, design: .rounded))
                Text(key.letters).font(.system(size: 9, weight: .semibold)).tracking(1.5).opacity(key.letters.isEmpty ? 0 : 1)
            }
            .frame(width: 72, height: 72)
            .background(DS.Palette.fill, in: Circle())
            .foregroundStyle(DS.Palette.ink)
        }
        .buttonStyle(.plain)
        .simultaneousGesture(LongPressGesture().onEnded { _ in
            if key.digit == "0", let onLongZero { onLongZero() }
        })
        .accessibilityLabel(key.digit)
    }
}

/// Presents `CNContactPickerViewController` limited to phone numbers; picking one hands back the
/// contact's name and that number. The picker runs out of process: no contacts permission needed.
struct ContactPhonePicker: UIViewControllerRepresentable {
    @Binding var isPresented: Bool
    let onPick: (String?, String) -> Void

    func makeUIViewController(context _: Context) -> UIViewController {
        UIViewController()
    }

    func updateUIViewController(_ host: UIViewController, context: Context) {
        guard isPresented, host.presentedViewController == nil else { return }
        let picker = CNContactPickerViewController()
        picker.displayedPropertyKeys = [CNContactPhoneNumbersKey]
        picker.predicateForEnablingContact = NSPredicate(format: "phoneNumbers.@count > 0")
        picker.predicateForSelectionOfProperty = NSPredicate(format: "key == 'phoneNumbers'")
        picker.delegate = context.coordinator
        context.coordinator.parent = self
        DispatchQueue.main.async { host.present(picker, animated: true) }
    }

    func makeCoordinator() -> Coordinator {
        Coordinator(parent: self)
    }

    @MainActor
    final class Coordinator: NSObject, @preconcurrency CNContactPickerDelegate {
        var parent: ContactPhonePicker

        init(parent: ContactPhonePicker) {
            self.parent = parent
        }

        func contactPicker(_: CNContactPickerViewController, didSelect property: CNContactProperty) {
            if let phone = property.value as? CNPhoneNumber {
                let name = CNContactFormatter.string(from: property.contact, style: .fullName)
                parent.onPick(name?.isEmpty == false ? name : nil, phone.stringValue)
            }
            parent.isPresented = false
        }

        func contactPickerDidCancel(_: CNContactPickerViewController) {
            parent.isPresented = false
        }
    }
}
