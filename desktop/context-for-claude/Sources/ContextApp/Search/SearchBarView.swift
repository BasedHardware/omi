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
/// **The bar answers for itself.** It used to be a delivery mechanism: whatever was typed went to
/// Claude on Return, and the panel underneath was only a filter for what had been captured. That is
/// a strange thing for a search bar to be — the app owns two full-text indexes over the user's own
/// machine, and the fastest possible answer to "what was that invoice site" was a round trip through
/// another application, a window switch, and a model call. Return now searches, the results are the
/// app's own, and they cover **both** halves of what it captures: the screens it saw and the
/// conversations it heard.
///
/// The one line under the field survives that change with a narrower job. It used to say where the
/// question had gone; there is nowhere for it to go now, so it appears only when the read itself
/// failed — which is the one state the panel's own empty copy cannot express, because "found
/// nothing" and "could not look" license opposite conclusions.
struct SearchBarView: View {
    /// A question to start from, handed over by the timeline's "Search All" pill.
    let initialQuery: String
    let onDismiss: () -> Void
    /// The surface's total height, whenever it changes. The window owns its own frame; this is how
    /// it learns the content grew a line.
    var onHeightChange: (CGFloat) -> Void = { _ in }
    /// **Where a result goes.** Activating a card hands the moment out here; the window turns it into
    /// `RewindWindow.present(store:at:)` and closes this surface.
    ///
    /// A closure rather than a call into `RewindWindow` from inside the view, for the reason every
    /// other window operation in this app is one: a view that opens windows cannot be rendered in a
    /// test or a preview without opening them.
    var onOpenMoment: (SearchMoment) -> Void = { _ in }

    @State private var query: String
    @StateObject private var results: SearchResultsModel

    init(
        initialQuery: String = "",
        store: ContextStore? = nil,
        onDismiss: @escaping () -> Void,
        onHeightChange: @escaping (CGFloat) -> Void = { _ in },
        onOpenMoment: @escaping (SearchMoment) -> Void = { _ in }
    ) {
        self.initialQuery = initialQuery
        self.onDismiss = onDismiss
        self.onHeightChange = onHeightChange
        self.onOpenMoment = onOpenMoment
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

    /// The one line under the field, or nil when there is nothing to say and the keyboard hint has
    /// the space instead.
    ///
    /// Only ever a failure now. A note that appears after every successful search would be a status
    /// line reporting that the thing on screen is on screen, and it would resize the window a line
    /// taller on every keystroke.
    private var note: String? { results.loadError }

    var body: some View {
        VStack(alignment: .leading, spacing: SearchLayout.panelGap) {
            SearchGlassPanel { promptBar }
            SearchGlassPanel { SearchResultsView(model: results, onOpen: open) }
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
        // `ask`, not `search`: the bar opens empty, and `search` treats "still empty" as nothing to
        // do, so the panel used to open having never read anything at all.
        .onAppear { results.ask(query) }
        .onChange(of: query) { text in
            results.search(text)
        }
        .onReceive(NotificationCenter.default.publisher(for: SearchBarWindow.refocusNotification)) { note in
            if let prefill = note.userInfo?[SearchBarWindow.prefillKey] as? String { query = prefill }
        }
    }

    // MARK: - The bar

    private var promptBar: some View {
        VStack(alignment: .leading, spacing: 0) {
            HStack(spacing: 12) {
                // The app's own mark, not the icon of whatever answers `claude://`. The glyph at the
                // leading edge says who is about to answer, and the honest answer is now this app.
                // Not a second magnifier either — the query chip already carries one, and two
                // magnifiers 30 pt apart read as a rendering fault rather than as a search bar.
                OmiMark(size: SearchLayout.glyphSize, color: Ink.primary)
                    .frame(width: SearchLayout.glyphSize, height: SearchLayout.glyphSize)
                    .accessibilityHidden(true)
                SearchQueryField(
                    query: $query,
                    available: SearchLayout.queryFieldWidth,
                    onSubmit: submit,
                    onCancel: onDismiss,
                    onMoveSelection: { results.moveSelection($0) })
                Spacer(minLength: 12)
                if note == nil { keyboardHint }
            }
            .frame(height: SearchLayout.barHeight)

            if let note {
                Text(note)
                    // Always the failure colour, because a note is now always a failure.
                    .inkStyle(.statusLabel, color: Ink.errorRed)
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

    /// `↵  Search`, and it is also the control.
    ///
    /// The reference shows only the keycaps. A bar whose one action exists solely as a key press is
    /// unusable to anyone who cannot press it, so the hint is a button — same glyphs, same weight,
    /// with a target under them.
    ///
    /// It says `Search` and not `Search again` even though the panel is already showing an answer by
    /// the time anyone can read it. "Again" would be accurate and useless: the hint's job on an
    /// untouched bar is to say what this thing *is*, and a search bar whose keycap advertises a
    /// refresh reads as a bar that has not searched yet.
    private var keyboardHint: some View {
        Button(action: submit) {
            HStack(spacing: 6) {
                Text("↵").inkStyle(.statusLabel, color: Ink.secondary)
                Text("Search").inkStyle(.statusLabel, color: Ink.tertiary)
            }
            .fixedSize()
        }
        .buttonStyle(.plain)
        .accessibilityLabel(Self.searchActionName)
        .help(Self.searchActionName)
    }

    /// What the action is called wherever it is named in words rather than in keycaps.
    ///
    /// It names **both** halves on purpose. A user who has only ever seen this bar hand things to
    /// Claude has no reason to expect it to know what was said out loud, and the accessibility label
    /// is one of two places (the placeholder is the other) where that can be said in a sentence.
    static let searchActionName = "Search this Mac's screens and conversations"

    // MARK: - Submit

    private func submit() {
        // The shared chrome cue; it honours the system UI-sound setting itself.
        Sound.effect(.click)
        // **Return means whichever thing the keyboard is currently on.** With a card selected it
        // opens that moment — the selection exists for no other purpose, and a highlighted card that
        // Return ignored would be a dead end the user walked into on purpose.
        if let selected = results.selectedMoment {
            open(selected)
            return
        }
        // Otherwise `ask`, not `search`: `search` de-duplicates identical text, and by the time
        // Return is pressed the text is always identical — every keystroke already searched. Return
        // means "ask again", and capture is live, so asking again is a real question with a possibly
        // different answer. Nothing is cleared and nothing is dismissed: the results are the point,
        // and a bar that emptied itself on Return would throw away the query that produced them.
        results.ask(query)
    }

    /// Hand a moment to whoever owns the windows.
    ///
    /// One function for both routes — the pointer's click and Return on a selection — so the two can
    /// never diverge into "clicking works and the keyboard does something subtly different".
    private func open(_ moment: SearchMoment) {
        onOpenMoment(moment)
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
    /// ↓ and ↑, as a step through the results. See `SearchResultsModel.moveSelection`.
    var onMoveSelection: (Int) -> Void = { _ in }

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
                SearchField(
                    text: $query, onSubmit: onSubmit, onCancel: onCancel,
                    onMoveSelection: onMoveSelection)
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
    /// ↓ and ↑ reach the results from here for the same reason Return and Escape do: the field holds
    /// the first responder for the whole life of this surface, so a key press that never reaches the
    /// field's delegate never happens at all. The cards cannot take focus themselves — the panel is
    /// non-activating and full keyboard access is off by default — so this is not one way into the
    /// results, it is the only one.
    var onMoveSelection: (Int) -> Void = { _ in }

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
        field.setAccessibilityLabel(SearchBarView.searchActionName)
        field.stringValue = text
        return field
    }

    func updateNSView(_ field: FocusingTextField, context: Context) {
        context.coordinator.text = $text
        context.coordinator.onSubmit = onSubmit
        context.coordinator.onCancel = onCancel
        context.coordinator.onMoveSelection = onMoveSelection
        // Only when it really differs: assigning `stringValue` moves the insertion point to the end,
        // which would fight the user on every keystroke.
        if field.stringValue != text { field.stringValue = text }
    }

    func makeCoordinator() -> Coordinator {
        Coordinator(
            text: $text, onSubmit: onSubmit, onCancel: onCancel, onMoveSelection: onMoveSelection)
    }

    final class Coordinator: NSObject, NSTextFieldDelegate {
        var text: Binding<String>
        var onSubmit: () -> Void
        var onCancel: () -> Void
        var onMoveSelection: (Int) -> Void

        init(
            text: Binding<String>,
            onSubmit: @escaping () -> Void,
            onCancel: @escaping () -> Void,
            onMoveSelection: @escaping (Int) -> Void = { _ in }
        ) {
            self.text = text
            self.onSubmit = onSubmit
            self.onCancel = onCancel
            self.onMoveSelection = onMoveSelection
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
            // Consumed (`true`) rather than passed on: a single-line field's own answer to ↓ is to
            // move the insertion point to the end of the line, which is a no-op the user cannot see
            // — so letting it through would look exactly like the key doing nothing.
            case #selector(NSResponder.moveDown(_:)):
                onMoveSelection(1)
                return true
            case #selector(NSResponder.moveUp(_:)):
                onMoveSelection(-1)
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
