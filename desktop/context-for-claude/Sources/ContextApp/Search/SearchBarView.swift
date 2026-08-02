import AppKit
import Combine
import SwiftUI

/// The prompt bar's contents: a mark, a field, and one line of truth underneath it.
///
/// The line under the field is the point of this view. Before you submit it says where the question
/// is going and whether that route actually exists on this Mac; after you submit it says what
/// happened, including when the honest answer is "I put it on your clipboard instead". There is no
/// results list, because there are no results here — the answer arrives in Claude.
struct SearchBarView: View {
    /// A question to start from, handed over by the timeline's "Search All" pill.
    let initialQuery: String
    let onDismiss: () -> Void

    @State private var query: String

    init(initialQuery: String = "", onDismiss: @escaping () -> Void) {
        self.initialQuery = initialQuery
        self.onDismiss = onDismiss
        _query = State(initialValue: initialQuery)
    }

    @State private var target = ClaudeRouter.preferredTarget
    @State private var outcome: Outcome?

    private enum Outcome: Equatable {
        case delivered(ClaudeRouter.Delivery)
        case failed(String)

        var sentence: String {
            switch self {
            case .delivered(let delivery):
                let truncation = delivery.wasTruncated
                    ? " I trimmed it to the \(ClaudeRouter.promptLimit) characters Claude accepts."
                    : ""
                return delivery.mechanism.note + truncation
            case .failed(let sentence):
                return sentence
            }
        }

        var isFailure: Bool {
            if case .failed = self { return true }
            return false
        }
    }

    private var availability: ClaudeRouter.Availability {
        ClaudeRouter.availability(of: target)
    }

    var body: some View {
        VStack(alignment: .leading, spacing: InkLayout.rhythm[5]) {
            field
            footer
        }
        .padding(.horizontal, 22)
        .padding(.vertical, 18)
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .top)
        .background(
            RoundedRectangle(cornerRadius: 18, style: .continuous)
                .fill(Ink.surface)
                .overlay(
                    RoundedRectangle(cornerRadius: 18, style: .continuous)
                        .strokeBorder(Ink.hairline, lineWidth: 1))
        )
        .onReceive(NotificationCenter.default.publisher(for: SearchBarWindow.refocusNotification)) { note in
            outcome = nil
            if let prefill = note.userInfo?[SearchBarWindow.prefillKey] as? String { query = prefill }
        }
    }

    // MARK: - Field

    private var field: some View {
        HStack(spacing: 12) {
            OmiMark(size: 20, color: Ink.primary)

            SearchField(text: $query, onSubmit: submit, onCancel: onDismiss)

            if !query.isEmpty {
                // A hint that is also the control. The reference only shows the keycap, but a bar whose
                // one action exists solely as a key press is unusable to anyone who cannot press it —
                // and it gives the gesture a target, which a hint alone does not.
                Button(action: submit) {
                    Text("↵").inkStyle(.statusLabel, color: Ink.tertiary)
                }
                .buttonStyle(.plain)
                .accessibilityLabel("Send to Claude")
                .help("Send to Claude")
                .transition(.opacity)
            }
        }
        .frame(height: 40)
    }

    // MARK: - Footer

    private var footer: some View {
        HStack(alignment: .firstTextBaseline, spacing: 10) {
            targetPill
            Text(outcome?.sentence ?? availability.detail)
                .inkStyle(.statusLabel, color: footerColour)
                .lineLimit(2)
                .fixedSize(horizontal: false, vertical: true)
            Spacer(minLength: 0)
            Text("esc")
                .inkStyle(.statusLabel, color: Ink.tertiary)
        }
    }

    private var footerColour: Color {
        if outcome?.isFailure == true { return Ink.errorRed }
        if outcome != nil { return Ink.secondary }
        return availability.isAvailable ? Ink.secondary : Ink.errorRed
    }

    /// The target, and a way to change it without leaving the bar. The accent is spent here because
    /// this is the one thing in the bar that is actionable and is not the field.
    private var targetPill: some View {
        Button {
            let next: ClaudeRouter.Target = target == .claudeApp ? .terminal : .claudeApp
            target = next
            ClaudeRouter.preferredTarget = next
            outcome = nil
        } label: {
            Text(target.title)
                .inkStyle(.statusLabel, color: Ink.accent)
                .padding(.horizontal, 8)
                .padding(.vertical, 3)
                .background(Capsule(style: .continuous).fill(Ink.rowFill))
        }
        .buttonStyle(.plain)
        .help("Switch where your question goes")
    }

    // MARK: - Submit

    private func submit() {
        // The shared chrome cue; it honours the system UI-sound setting itself.
        Sound.effect(.click)
        switch ClaudeRouter.route(query, to: target) {
        case .success(let delivery):
            outcome = .delivered(delivery)
            query = ""
            // Left open, showing what happened. Closing instantly would take the one sentence that
            // says whether the prompt was filled in or merely copied with it.
            DispatchQueue.main.asyncAfter(deadline: .now() + 1.6) { onDismiss() }
        case .failure(let error):
            outcome = .failed(error.sentence)
        }
    }
}


// MARK: - The field

/// An AppKit text field, not a SwiftUI `TextField`.
///
/// Three SwiftUI mechanisms were tried in the real app and none of them works inside a borderless
/// non-activating panel: `@FocusState` never gave the field focus, `.onSubmit` never fired on Return,
/// and Escape reached the field (it dropped focus) without any observer of ours seeing it — including
/// an `NSEvent.addLocalMonitorForEvents` monitor and an `NSPanel.sendEvent` override.
///
/// `NSTextField` reports both keys through `control(_:textView:doCommandBy:)`, which is the documented
/// path and the one that actually runs, and it can be made first responder directly. Everything about
/// how it looks still comes from `Ink` — the same face, size and colour roles the SwiftUI version had.
private struct SearchField: NSViewRepresentable {
    @Binding var text: String
    let onSubmit: () -> Void
    let onCancel: () -> Void

    private static let placeholder = "Ask Claude about your day…"

    func makeNSView(context: Context) -> FocusingTextField {
        // The same role the SwiftUI field used, resolved to the AppKit font it is made of.
        let face = InkFonts.role(size: InkType.stepHeadline.size, weight: .semiBold).metrics
        let field = FocusingTextField()
        field.delegate = context.coordinator
        field.isBordered = false
        field.drawsBackground = false
        field.focusRingType = .none
        field.font = face
        field.textColor = Ink.nsPrimary
        field.lineBreakMode = .byTruncatingTail
        // The placeholder carries the role too, or it renders in the system body font beside a 25 pt
        // field and the bar looks like two different components.
        field.placeholderAttributedString = NSAttributedString(
            string: Self.placeholder,
            attributes: [.font: face, .foregroundColor: NSColor.tertiaryLabelColor])
        // Both Return paths, because AppKit picks between them depending on whether the field editor
        // is active: a live editor reports `insertNewline:` through the delegate, an inactive one fires
        // the cell's target/action instead. Wiring only one leaves Return dead half the time.
        field.target = context.coordinator
        field.action = #selector(Coordinator.submitFromField(_:))
        field.usesSingleLineMode = true
        field.setAccessibilityLabel("Ask Claude")
        field.stringValue = text
        return field
    }

    func updateNSView(_ field: FocusingTextField, context: Context) {
        context.coordinator.text = $text
        context.coordinator.onSubmit = onSubmit
        context.coordinator.onCancel = onCancel
        // Only when it really differs: assigning `stringValue` moves the insertion point to the end,
        // which would fight the user on every keystroke.
        if field.stringValue != text { field.stringValue = text }
    }

    func makeCoordinator() -> Coordinator {
        Coordinator(text: $text, onSubmit: onSubmit, onCancel: onCancel)
    }

    final class Coordinator: NSObject, NSTextFieldDelegate {
        var text: Binding<String>
        var onSubmit: () -> Void
        var onCancel: () -> Void

        init(text: Binding<String>, onSubmit: @escaping () -> Void, onCancel: @escaping () -> Void) {
            self.text = text
            self.onSubmit = onSubmit
            self.onCancel = onCancel
        }

        @objc func submitFromField(_ sender: NSTextField) {
            text.wrappedValue = sender.stringValue
            onSubmit()
        }

        func controlTextDidChange(_ notification: Notification) {
            guard let field = notification.object as? NSTextField else { return }
            text.wrappedValue = field.stringValue
        }

        func control(_ control: NSControl, textView: NSTextView, doCommandBy command: Selector) -> Bool {
            switch command {
            case #selector(NSResponder.insertNewline(_:)):
                onSubmit()
                return true
            case #selector(NSResponder.cancelOperation(_:)):
                onCancel()
                return true
            default:
                return false
            }
        }
    }
}

/// Takes focus the moment it joins a window, so the bar is typeable on the first open.
///
/// The async pass is the one that sticks: SwiftUI is still assembling the hierarchy when
/// `viewDidMoveToWindow` runs, and a first responder set inside that pass gets replaced.
final class FocusingTextField: NSTextField {
    override func viewDidMoveToWindow() {
        super.viewDidMoveToWindow()
        guard let window else { return }
        window.makeFirstResponder(self)
        DispatchQueue.main.async { [weak self] in
            guard let self, self.window === window else { return }
            window.makeFirstResponder(self)
        }
    }
}
