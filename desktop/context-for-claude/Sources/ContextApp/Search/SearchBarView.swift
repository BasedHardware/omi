import AppKit
import Combine
import ContextCore
import SwiftUI

/// The search surface: a prompt bar, a gap, and a panel of what you can filter by and what was
/// found. **The content of the app's main window.**
///
/// **Two panels, not one.** The bar and the panel under it are separate objects with real air
/// between them (`SearchLayout.panelGap`), each cut to its own corner. That separation is the design
/// — it is what says "this is a place you type" and "this is a place you look" without a label — and
/// it is the one thing a refactor here must not quietly undo by wrapping both in a single container.
/// It survived the move into a titled window: what changed is that the panels are raised regions on
/// the window's own glass rather than two pieces of glass over the desktop (see `SearchGlassPanel`).
///
/// **It measures the window rather than the window measuring it.** As a floating panel this view
/// reported its natural height upwards and the window resized itself to match on every keystroke,
/// which is exactly the wrong direction for a frame the user owns — one drag of the corner would be
/// undone by the next character typed. The geometry reader here is that arrow reversed: the window is
/// whatever the user made it, and the width the grid reflows to and the room the results body gets
/// are both functions of it (`SearchLayout.panelWidth(inWindowOfWidth:)`,
/// `SearchLayout.availableResultsBodyHeight(inWindowOfHeight:showingNote:)`).
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
    /// **Where a result goes.** Activating a card hands the moment out here; the window turns it into
    /// `RewindWindow.present(store:at:)`.
    ///
    /// A closure rather than a call into `RewindWindow` from inside the view, for the reason every
    /// other window operation in this app is one: a view that opens windows cannot be rendered in a
    /// test or a preview without opening them.
    var onOpenMoment: (SearchMoment) -> Void = { _ in }
    /// Where a frame from the activity spine goes. A separate seam from `onOpenMoment` rather than a
    /// conversion into `SearchMoment`: that type carries a search hit's evidence — the matched
    /// snippet, the facet fields, the row it came from — and an activity tile has none of it. Making
    /// one from the other would mean inventing values a reader would later trust.
    var onOpenActivityMoment: (ActivityMoment) -> Void = { _ in }

    @State private var query: String
    @StateObject private var results: SearchResultsModel

    /// **Which body the window is showing.**
    ///
    /// The main window has two: the activity surface, and the search results this file has always
    /// drawn. Stated as a value rather than as a boolean inside the `body` so a beat added later has
    /// to answer the question, and so the two cannot both be on screen.
    ///
    /// It opens on `.activity`, which is the point of the window: what this Mac has been doing, in
    /// the order it happened. A question moves it to `.results` and clearing the field moves it back,
    /// so the two are one surface with a question in it rather than two places to remember.
    @State private var shownBody: LowerPanel = .activity

    /// Asked for, never held — see `ActivityStore.store` for why a window built at launch cannot keep
    /// the store it found there.
    private let store: () -> ContextStore?

    /// The two things the main window's lower panel can be.
    enum LowerPanel: Equatable {
        /// What this Mac has been doing, `ActivitySurface` — see the mounting point in `body`.
        case activity
        /// The results of a search, and the filters that narrow them.
        case results
    }

    init(
        initialQuery: String = "",
        store: @escaping () -> ContextStore? = { nil },
        onOpenMoment: @escaping (SearchMoment) -> Void = { _ in },
        onOpenActivityMoment: @escaping (ActivityMoment) -> Void = { _ in }
    ) {
        self.initialQuery = initialQuery
        self.onOpenMoment = onOpenMoment
        self.onOpenActivityMoment = onOpenActivityMoment
        self.store = store
        _query = State(initialValue: initialQuery)
        _results = StateObject(wrappedValue: SearchResultsModel(store: store))
        // A window handed a question to start from is answering it, not showing the day.
        _shownBody = State(initialValue: initialQuery.isEmpty ? .activity : .results)
    }

    /// The already-answered form, for previews and the render harness. Nothing it draws can reach
    /// the user's database.
    init(query: String, results: SearchResultsModel) {
        self.initialQuery = query
        self.store = { nil }
        _query = State(initialValue: query)
        _results = StateObject(wrappedValue: results)
        _shownBody = State(initialValue: query.isEmpty ? .activity : .results)
    }

    /// The one line under the field, or nil when there is nothing to say and the keyboard hint has
    /// the space instead.
    ///
    /// Only ever a failure now. A note that appears after every successful search would be a status
    /// line reporting that the thing on screen is on screen, and it would resize the window a line
    /// taller on every keystroke.
    private var note: String? { results.loadError }

    /// When the window is looking at, from the one control that decides it.
    ///
    /// Read off the results model rather than duplicated, because the time chips live in the filter
    /// block that the results body owns. Two copies of "which day" is the bug where the spine and the
    /// grid disagree about what "yesterday" meant.
    private var bounds: (since: Double?, until: Double?) {
        results.time.range(pickedDate: results.pickedDate)
    }

    var body: some View {
        GeometryReader { proxy in
            let panelWidth = SearchLayout.panelWidth(inWindowOfWidth: proxy.size.width)
            VStack(alignment: .leading, spacing: SearchLayout.panelGap) {
                SearchGlassPanel { promptBar(panelWidth: panelWidth) }
                lowerPanel(
                    panelWidth: panelWidth,
                    availableBodyHeight: SearchLayout.availableResultsBodyHeight(
                        inWindowOfHeight: proxy.size.height, showingNote: note != nil))
                // The two panels add up to exactly the window's height by construction
                // (`SearchLayout.windowChrome` plus the body's share of what is left), so this only
                // ever absorbs a point of rounding. It is here so that if they ever do not, the
                // leftover is bare glass at the bottom rather than a stretched panel.
                Spacer(minLength: 0)
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .top)
            .padding(.horizontal, SearchLayout.windowInset)
            .padding(.bottom, SearchLayout.windowInset)
            // The band the traffic lights sit in. The glass runs under the title bar; the field the
            // user is typing into may not.
            .padding(.top, SearchLayout.titleBarInset)
        }
        // `ask`, not `search`: the window opens empty, and `search` treats "still empty" as nothing
        // to do, so the panel used to open having never read anything at all.
        .onAppear { results.ask(query) }
        .onChange(of: query) { text in
            results.search(text)
            // The question decides which body answers it. An emptied field is not a search for
            // nothing — it is the absence of a question, which is the day.
            let asked = !text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
            let wanted: LowerPanel = asked ? .results : .activity
            guard wanted != shownBody else { return }
            InkReduceMotion.perform(.easeOut(duration: InkMotion.press)) { shownBody = wanted }
        }
        .onReceive(NotificationCenter.default.publisher(for: SearchBarWindow.refocusNotification)) { note in
            guard let prefill = note.userInfo?[SearchBarWindow.prefillKey] as? String else { return }
            // Only a prefill that really arrived. The notification is also the plain "take the
            // keyboard back" signal, and a window brought forward with nothing to ask must not wipe
            // the question already in the field.
            query = prefill
            // A prefill is a new question from somewhere else in the app, and the panel de-duplicates
            // identical text — so a second press of the same pill would otherwise show a stale answer
            // over a live capture.
            results.ask(prefill)
        }
    }

    // MARK: - The lower panel, and where Activity mounts

    /// The lower of the two panels.
    ///
    /// **`ActivitySurface` mounts on the `.activity` branch.** It is owned elsewhere and is not this
    /// file's to invent. What lives here is only the seam: one value (`shownBody`) deciding which of
    /// the two the window is showing, and one place that switches on it, so the surface cannot end up
    /// drawing both or neither.
    @ViewBuilder
    private func lowerPanel(panelWidth: CGFloat, availableBodyHeight: CGFloat) -> some View {
        switch shownBody {
        case .activity:
            SearchGlassPanel {
                // The time chips are the window's, not the surface's: `SearchTimeFilter.range`
                // already returns exactly the bounds pair the activity store narrows on, so both
                // bodies answer "when" from one value and cannot disagree about which day it is.
                ActivitySurface(
                    store: store,
                    query: query,
                    since: bounds.since,
                    until: bounds.until,
                    onOpenMoment: onOpenActivityMoment)
                .frame(width: panelWidth, height: availableBodyHeight, alignment: .topLeading)
            }
        case .results:
            SearchGlassPanel {
                SearchResultsView(
                    model: results,
                    onOpen: open,
                    panelWidth: panelWidth,
                    availableBodyHeight: availableBodyHeight)
            }
        }
    }

    // MARK: - The bar

    private func promptBar(panelWidth: CGFloat) -> some View {
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
                    available: SearchLayout.queryFieldWidth(panelWidth: panelWidth),
                    onSubmit: submit,
                    // **Escape clears the question; it does not close the window.** On a summoned
                    // panel those were the same gesture. On the app's main window they are not: a
                    // window that vanishes when you press Escape in its search field is a window you
                    // cannot use a search field in. Clearing puts the surface back to its resting
                    // state — the newest captures, nothing typed — which is what Escape means in
                    // every other search field on this platform.
                    onCancel: clear,
                    onGridStep: { results.move($0) })
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
        .frame(maxWidth: .infinity, alignment: .leading)
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
            // Both halves on the same rung. The word used to sit a step below the keycap, which is
            // the right emphasis on paper and unavailable here: this bar is glass and glass carries
            // two rungs (see `Ink.tertiary`), so the choice is one rung or an invisible word. The
            // keycap still leads by shape.
            HStack(spacing: 6) {
                Text("↵").inkStyle(.statusLabel, color: Ink.secondary)
                Text("Search").inkStyle(.statusLabel, color: Ink.secondary)
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

    /// Back to the resting state: no question, no selection, the newest captures.
    ///
    /// `ask` and not `search`, for the same reason `submit` uses it — with the field already emptied
    /// by the binding, `search("")` would find nothing to do and leave the previous answer on screen.
    private func clear() {
        results.clearSelection()
        query = ""
        results.ask("")
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
    /// The four arrow keys, as a move on the results grid. See `SearchResultsModel.move`.
    var onGridStep: (SearchGridStep) -> Bool = { _ in false }

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
                    onGridStep: onGridStep)
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
/// Three SwiftUI mechanisms were tried in the real app and none of them worked: `@FocusState` never
/// gave the field focus, `.onSubmit` never fired on Return, and Escape reached the field (it dropped
/// focus) without any observer of ours seeing it — including an `NSEvent.addLocalMonitorForEvents`
/// monitor and an `NSWindow.sendEvent` override.
///
/// **That measurement was taken on the borderless non-activating panel this surface used to be, and
/// it is not a reason to go back and try again.** `control(_:textView:doCommandBy:)` is the
/// documented path for both keys and the one that actually runs, and — the part that matters more
/// than the focus story — the arrow-key routing below is the only keyboard path into the results at
/// all. The cards cannot take focus themselves, so ripping this out for a `TextField` would take the
/// grid's navigation with it. Everything about how it looks still comes from `Ink`.
private struct SearchField: NSViewRepresentable {
    @Binding var text: String
    let onSubmit: () -> Void
    let onCancel: () -> Void
    /// The arrow keys reach the results from here for the same reason Return and Escape do: the
    /// field holds the first responder for as long as the user is typing, so a key press that never
    /// reaches the field's delegate never happens at all. The cards cannot take focus themselves —
    /// full keyboard access is off by default — so this is not one way into the results, it is the
    /// only one.
    ///
    /// Returns whether the results took the key, which is what lets ← and → be shared: the field
    /// keeps them until a card is selected, and gets them back the moment one is not. See
    /// `SearchResultsModel.move`.
    var onGridStep: (SearchGridStep) -> Bool = { _ in false }

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
        // query and the bar looks like two different components. `secondary` and not the fainter
        // rung a placeholder usually gets: this bar is glass, and a placeholder is the *only* thing
        // on an untouched bar — a rung that vanishes over a dark wallpaper leaves an empty capsule
        // with no idea what to type into it. See `Ink.tertiary` for the two-rung rule.
        field.placeholderAttributedString = NSAttributedString(
            string: SearchMetrics.placeholder,
            attributes: [.font: face, .foregroundColor: NSColor(Ink.secondary)])
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
        context.coordinator.onGridStep = onGridStep
        // Only when it really differs: assigning `stringValue` moves the insertion point to the end,
        // which would fight the user on every keystroke.
        if field.stringValue != text { field.stringValue = text }
    }

    func makeCoordinator() -> Coordinator {
        Coordinator(
            text: $text, onSubmit: onSubmit, onCancel: onCancel, onGridStep: onGridStep)
    }

    final class Coordinator: NSObject, NSTextFieldDelegate {
        var text: Binding<String>
        var onSubmit: () -> Void
        var onCancel: () -> Void
        var onGridStep: (SearchGridStep) -> Bool

        init(
            text: Binding<String>,
            onSubmit: @escaping () -> Void,
            onCancel: @escaping () -> Void,
            onGridStep: @escaping (SearchGridStep) -> Bool = { _ in false }
        ) {
            self.text = text
            self.onSubmit = onSubmit
            self.onCancel = onCancel
            self.onGridStep = onGridStep
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
                return onGridStep(.down)
            case #selector(NSResponder.moveUp(_:)):
                return onGridStep(.up)
            // …and ← / → are the opposite case: they are the *field's* by default, because moving
            // the insertion point through a query is what a person does with them all day. They are
            // only borrowed while a card is selected, and the borrow is announced by the return
            // value rather than by a flag this file would have to keep in step — `false` here means
            // the results declined, and AppKit hands the key straight back to the field editor.
            case #selector(NSResponder.moveLeft(_:)):
                return onGridStep(.left)
            case #selector(NSResponder.moveRight(_:)):
                return onGridStep(.right)
            default:
                return false
            }
        }
    }
}

/// Takes the keyboard when the window is **asked for**, and once when it is first built.
///
/// The old rule was "grab first responder every time this view joins a window, twice, the second time
/// asynchronously". That was written for a panel that was rebuilt from nothing on every ⌘⌘⇧, where
/// the only moment the field could be given focus was the moment it appeared — and the async pass was
/// needed because SwiftUI is still assembling the hierarchy when `viewDidMoveToWindow` runs, so a
/// first responder set inside that pass gets replaced.
///
/// Neither reason survives a persistent window, and the rule actively misbehaves in one: a view that
/// claims the first responder unconditionally whenever it is re-attached takes the keyboard away from
/// whatever else the window contains. So the grab is once, on the way in, and after that it happens
/// only when something says the window has been asked for — `SearchBarWindow.refocusNotification`,
/// posted by `present()` and on `didBecomeKey`.
///
/// Selecting the existing text is part of the same statement: a user who summons this window with a
/// question already in it means to replace it, exactly as ⌘-Space does.
final class FocusingTextField: NSTextField {
    private var hasTakenTheKeyboard = false
    private var refocusObserver: NSObjectProtocol?

    override func viewDidMoveToWindow() {
        super.viewDidMoveToWindow()
        guard let window else {
            // Torn down here rather than in `deinit`: this is the one place that is guaranteed to be
            // on the main actor, and an observer left behind would outlive the field it points at.
            if let refocusObserver {
                NotificationCenter.default.removeObserver(refocusObserver)
                self.refocusObserver = nil
            }
            return
        }

        if refocusObserver == nil {
            refocusObserver = NotificationCenter.default.addObserver(
                forName: SearchBarWindow.refocusNotification, object: nil, queue: .main
            ) { [weak self] _ in
                MainActor.assumeIsolated { self?.takeTheKeyboard() }
            }
        }

        guard !hasTakenTheKeyboard else { return }
        hasTakenTheKeyboard = true
        window.makeFirstResponder(self)
        DispatchQueue.main.async { [weak self] in
            guard let self, self.window === window else { return }
            window.makeFirstResponder(self)
        }
    }

    /// First responder, with whatever is already typed selected.
    private func takeTheKeyboard() {
        guard let window, window.isVisible else { return }
        window.makeFirstResponder(self)
        currentEditor()?.selectAll(nil)
    }
}
