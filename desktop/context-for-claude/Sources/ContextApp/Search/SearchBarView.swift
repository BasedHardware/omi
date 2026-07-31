import AppKit
import Combine
import ContextCore
import SwiftUI

/// The search surface: a prompt bar, a gap, and a panel of what you can filter by and what was
/// found.
///
/// **Two panels, not one.** The bar and the panel under it are separate floating objects with real
/// air between them (`SearchLayout.panelGap`), each cut to its own corner, each on its own glass,
/// each casting its own shadow. That separation is the design — it is what says "this is a place you
/// type" and "this is a place you look" without a label — and it is the one thing a refactor here
/// must not quietly undo by wrapping both in a single container.
///
/// The bar keeps everything it promised before: the typed question routes to Claude on Return, and
/// the one line of truth about where it went (including the honest "I put it on your clipboard
/// instead") still appears — it takes the keyboard hint's place rather than a row of its own, so the
/// bar stays a bar.
struct SearchBarView: View {
    /// A question to start from, handed over by the timeline's "Search All" pill.
    let initialQuery: String
    let onDismiss: () -> Void
    /// The surface's total height, whenever it changes. The window owns its own frame; this is how
    /// it learns the content grew a line.
    var onHeightChange: (CGFloat) -> Void = { _ in }

    @State private var query: String
    @StateObject private var results: SearchResultsModel

    init(
        initialQuery: String = "",
        store: ContextStore? = nil,
        onDismiss: @escaping () -> Void,
        onHeightChange: @escaping (CGFloat) -> Void = { _ in }
    ) {
        self.initialQuery = initialQuery
        self.onDismiss = onDismiss
        self.onHeightChange = onHeightChange
        _query = State(initialValue: initialQuery)
        _results = StateObject(wrappedValue: SearchResultsModel(store: store))
    }

    /// The already-answered form, for previews and the render harness. Nothing it draws can reach
    /// the user's database.
    init(query: String, results: SearchResultsModel, onDismiss: @escaping () -> Void = {}) {
        self.initialQuery = query
        self.onDismiss = onDismiss
        _query = State(initialValue: query)
        _results = StateObject(wrappedValue: results)
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

    /// The one line under the field, or nil when there is nothing to say and the keyboard hint has
    /// the space instead.
    private var note: String? {
        if let outcome { return outcome.sentence }
        if !availability.isAvailable { return availability.detail }
        return nil
    }

    private var noteColour: Color {
        if outcome?.isFailure == true || !availability.isAvailable { return Ink.errorRed }
        return Ink.secondary
    }

    var body: some View {
        VStack(alignment: .leading, spacing: SearchLayout.panelGap) {
            SearchGlassPanel { promptBar }
            SearchGlassPanel { SearchResultsView(model: results) }
        }
        // The clear margin the shadows fall off into. Without it the window clips them and the
        // panels look stamped onto the desktop rather than floating over it.
        .padding(SearchLayout.shadowMargin)
        .frame(width: SearchLayout.surfaceWidth, alignment: .top)
        .background(SearchHeightReader(key: SearchSurfaceHeightKey.self))
        // Measured, not predicted. The second panel is content-sized — three empty sections and a
        // page of cards are 300 pt apart — so the window has to take the height the view arrived at
        // rather than one this file guessed.
        .onPreferenceChange(SearchSurfaceHeightKey.self) { height in
            guard height > 0 else { return }
            onHeightChange(height)
        }
        // `start`, not `search`: the bar opens empty, and `search` treats "still empty" as nothing to
        // do, so the panel used to open having never read anything at all.
        .onAppear { results.start(query) }
        .onChange(of: query) { text in
            outcome = nil
            results.search(text)
        }
        .onReceive(NotificationCenter.default.publisher(for: SearchBarWindow.refocusNotification)) { note in
            outcome = nil
            if let prefill = note.userInfo?[SearchBarWindow.prefillKey] as? String { query = prefill }
        }
    }

    // MARK: - The bar

    private var promptBar: some View {
        VStack(alignment: .leading, spacing: 0) {
            HStack(spacing: 12) {
                SearchTargetGlyph(size: SearchLayout.glyphSize)
                SearchQueryField(
                    query: $query,
                    available: SearchLayout.queryFieldWidth,
                    onSubmit: submit,
                    onCancel: onDismiss)
                Spacer(minLength: 12)
                if note == nil { keyboardHint }
            }
            .frame(height: SearchLayout.barHeight)

            if let note {
                Text(note)
                    .inkStyle(.statusLabel, color: noteColour)
                    .lineLimit(2)
                    .fixedSize(horizontal: false, vertical: true)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .padding(.bottom, SearchLayout.panelPaddingVertical - 4)
                    .padding(.leading, SearchLayout.glyphSize + 12)
                    .transition(.opacity)
            }
        }
        .padding(.horizontal, SearchLayout.panelPaddingHorizontal)
        .frame(width: SearchLayout.panelWidth, alignment: .leading)
        .animation(InkReduceMotion.animation(.easeOut(duration: InkMotion.settle)), value: note)
    }

    /// `⌘ ↵  Run on Claude Code`, and it is also the control.
    ///
    /// The reference shows only the keycaps. A bar whose one action exists solely as a key press is
    /// unusable to anyone who cannot press it, so the hint is a button — same glyphs, same weight,
    /// with a target under them.
    private var keyboardHint: some View {
        Button(action: submit) {
            HStack(spacing: 6) {
                Text("⌘ ↵").inkStyle(.statusLabel, color: Ink.secondary)
                Text("Run on \(destinationName)").inkStyle(.statusLabel, color: Ink.tertiary)
            }
            .fixedSize()
        }
        .buttonStyle(.plain)
        .accessibilityLabel("Send to \(destinationName)")
        .help("Send to \(destinationName)")
    }

    /// What the hint calls where the question is going.
    ///
    /// Not `Target.title`, which is the name of the *application* and is what the old target picker
    /// needed. The prompt is delivered to `claude://code/new`, so the surface it lands on is Claude
    /// Code — and a hint that names the app while the delivery note says "Opened a Claude Code tab"
    /// is two answers to one question.
    private var destinationName: String {
        target == .claudeApp ? "Claude Code" : target.title
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

// MARK: - The glyph

/// The small coloured mark at the bar's leading edge: the icon of whatever app actually answers
/// `claude://` on this Mac, or the app's own mark when nothing does.
///
/// A real icon rather than a drawn glyph because it is the one place the bar says *where the
/// question is going*, and an app's icon says that faster than its name. Resolved through
/// LaunchServices, so a hit is never the wrong app — and a miss falls back to the Omi mark rather
/// than to a generic document.
struct SearchTargetGlyph: View {
    var size: CGFloat = 22

    @State private var icon: NSImage?

    var body: some View {
        Group {
            if let icon {
                Image(nsImage: icon).resizable().aspectRatio(contentMode: .fit)
            } else {
                OmiMark(size: size, color: Ink.primary)
            }
        }
        .frame(width: size, height: size)
        .accessibilityHidden(true)
        .task {
            guard let url = ClaudeRouter.Probe.live().handlerForClaudeScheme() else { return }
            icon = NSWorkspace.shared.icon(forFile: url.path)
        }
    }
}

// MARK: - The field

/// The query, drawn as the reference draws it: a tinted capsule around what has been typed, with the
/// live insertion point sitting after it.
///
/// The capsule is sized from the text rather than filling the bar (`SearchMetrics.chipWidth`), which
/// is what makes it read as a *chip* — a fixed-width tinted box would be a text field with a
/// background. With nothing typed there is no chip at all, only the placeholder and the cursor,
/// which is the state the reference shows at rest.
private struct SearchQueryField: View {
    @Binding var query: String
    /// Width available to the chip before it has to stop growing.
    let available: CGFloat
    let onSubmit: () -> Void
    let onCancel: () -> Void

    private var isTyped: Bool { !query.isEmpty }

    var body: some View {
        ZStack(alignment: .leading) {
            if isTyped {
                Capsule(style: .continuous)
                    .fill(SearchInk.queryChipFill)
                    .overlay(
                        Capsule(style: .continuous)
                            .strokeBorder(SearchInk.queryChipStroke, lineWidth: 1))
                    .frame(
                        width: SearchMetrics.chipWidth(for: query, available: available),
                        height: SearchMetrics.queryLineHeight)
            }
            HStack(spacing: 6) {
                if isTyped {
                    Image(systemName: "magnifyingglass")
                        .font(.system(size: 11, weight: .semibold))
                        .foregroundStyle(SearchInk.queryChipGlyph)
                        .accessibilityHidden(true)
                }
                SearchField(text: $query, onSubmit: onSubmit, onCancel: onCancel)
            }
            .padding(.leading, isTyped ? SearchMetrics.chipPaddingHorizontal : 0)
        }
        // The field's line box, with room over the ascenders. A row shorter than the face it is set
        // in clips the top of the placeholder, which is exactly what a 27 pt query in a 34 pt row did.
        .frame(height: SearchMetrics.queryLineHeight)
        .animation(InkReduceMotion.animation(.easeOut(duration: InkMotion.press)), value: isTyped)
    }
}

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

    func makeNSView(context: Context) -> FocusingTextField {
        // The same role the chip is measured with, resolved to the AppKit font it is made of. The
        // two must be the same face or the capsule and the text it wraps disagree about how wide the
        // query is.
        let face = SearchMetrics.queryFace
        let field = FocusingTextField()
        field.delegate = context.coordinator
        field.isBordered = false
        field.drawsBackground = false
        field.focusRingType = .none
        field.font = face
        field.textColor = Ink.nsPrimary
        field.lineBreakMode = .byTruncatingTail
        // The placeholder carries the role too, or it renders in the system body font beside the
        // query and the bar looks like two different components.
        field.placeholderAttributedString = NSAttributedString(
            string: SearchMetrics.placeholder,
            attributes: [.font: face, .foregroundColor: NSColor(Ink.tertiary)])
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
