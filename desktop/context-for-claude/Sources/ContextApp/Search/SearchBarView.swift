import AppKit
import Combine
import ContextCore
import SwiftUI

/// The search surface: a prompt bar, a gap, and a panel of what you can filter by and what was
/// found. **The content of the floating panel `SearchBarWindow` puts up.**
///
/// **Two panels, not one.** The bar and the panel under it are separate floating objects with real
/// air between them (`SearchLayout.panelGap`), each cut to its own corner, each on its own glass,
/// each casting its own shadow. That separation is the design — it is what says "this is a place you
/// type" and "this is a place you look" without a label — and it is the one thing a refactor here
/// must not quietly undo by wrapping both in a single container.
///
/// **It measures itself and the window follows.** The lower panel is content-sized — three empty
/// sections and a page of cards are 300 pt apart — so the surface reports its own height upwards
/// (`onHeightChange`) and the window resizes around its top edge. A Spotlight panel has no frame the
/// user owns, so there is nothing for the measurement to fight.
///
/// **Typing searches; Return asks.** This bar has flip-flopped on that once already, and the split is
/// what both halves of the argument were actually right about. Handing every keystroke to Claude made
/// the fastest possible answer to "what was that invoice site" a round trip through another
/// application, a window switch and a model call — when this app owns two full-text indexes over the
/// user's own machine. So typing narrows locally and instantly (`SearchResultsModel`), over **both**
/// halves of what is captured: the screens it saw and the conversations it heard. But a *question* —
/// "what was I supposed to send Priya" — is not a lookup, and this app cannot answer it. Return hands
/// it to whichever Claude `Settings → Agents → Claude target` names, through the same `ClaudeRouter`
/// the first-run tutorial uses. Nothing but what is in the field is ever sent, and an empty field
/// launches nothing at all.
///
/// The one line under the field says when that did not work. It carries two failures now — a read
/// that could not run, and a handoff that fell short of what the keycap promised — and nothing else:
/// a note after a *successful* search would be a status line reporting that the thing on screen is on
/// screen, and a note after a successful handoff would be describing a Claude the user is already
/// looking at. Success is visible; only failure needs saying.
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
    /// **The timeline, asked for by name rather than by picking a moment.** The bar's own way to the
    /// other window, and the reason the pill exists: a Spotlight panel that can only be left by
    /// activating a result is a panel a user with no result to activate is stuck on.
    ///
    /// A closure for the same reason `onOpenMoment` is one — see `RewindView.onSearch`, which is this
    /// same seam pointing the other way.
    var onOpenTimeline: () -> Void = {}
    /// Settings. The other half of what the timeline's header has always carried, and missing here
    /// for exactly as long as this surface was the one the app opened on.
    var onOpenSettings: () -> Void = {}
    /// Where a frame from the activity spine goes. A separate seam from `onOpenMoment` rather than a
    /// conversion into `SearchMoment`: that type carries a search hit's evidence — the matched
    /// snippet, the facet fields, the row it came from — and an activity tile has none of it. Making
    /// one from the other would mean inventing values a reader would later trust.
    var onOpenActivityMoment: (ActivityMoment) -> Void = { _ in }

    @State private var query: String
    @StateObject private var results: SearchResultsModel

    /// **Which body the panel is showing.**
    ///
    /// The surface has two: the activity surface, and the search results this file has always drawn.
    /// Stated as a value rather than as a boolean inside the `body` so a beat added later has to
    /// answer the question, and so the two cannot both be on screen.
    ///
    /// It opens on `.activity`, which is what the panel is for before a question is asked: what this
    /// Mac has been doing, in the order it happened. A question moves it to `.results` and clearing
    /// the field moves it back, so the two are one surface with a question in it rather than two
    /// places to remember.
    @State private var shownBody: LowerPanel = .activity

    /// Asked for, never held — see `ActivityStore.store` for why a surface cannot keep the store it
    /// found when it was built.
    private let store: () -> ContextStore?

    /// The two things the lower panel can be.
    enum LowerPanel: Equatable {
        /// What this Mac has been doing, `ActivitySurface` — see the mounting point in `body`.
        case activity
        /// The results of a search, and the filters that narrow them.
        case results
    }

    /// The Activity store the lower panel draws.
    ///
    /// **A stored seam and not an expression inside `body`**, because the expression was a way for a
    /// render harness to read the user's real memories. The preview initialiser below can only nil
    /// out the *search* store; the activity branch built its own live reader every time it drew, so
    /// an empty-query harness case rendered this person's saved memories into PNGs on disk. Held
    /// here, the harness is handed an inert store and the promise its header makes — that nothing of
    /// the user's is ever captured — is one the type system keeps.
    ///
    /// It is the *store* rather than the account reader behind it, because the store is the thing
    /// that has to outlive this view: see `ActivitySpine`. Passing a reader meant a store per panel,
    /// and a store per panel meant re-paging the whole account every time somebody opened the bar or
    /// typed into it. It has no default for the same reason it is not built here — a surface that
    /// can conjure its own spine is a surface that will, in some future call site nobody reviews.
    private let spine: ActivityStore

    init(
        initialQuery: String = "",
        store: @escaping () -> ContextStore? = { nil },
        spine: ActivityStore,
        onDismiss: @escaping () -> Void,
        onHeightChange: @escaping (CGFloat) -> Void = { _ in },
        onOpenMoment: @escaping (SearchMoment) -> Void = { _ in },
        onOpenActivityMoment: @escaping (ActivityMoment) -> Void = { _ in },
        onOpenTimeline: @escaping () -> Void = {},
        onOpenSettings: @escaping () -> Void = {}
    ) {
        self.initialQuery = initialQuery
        self.onDismiss = onDismiss
        self.onHeightChange = onHeightChange
        self.onOpenMoment = onOpenMoment
        self.onOpenActivityMoment = onOpenActivityMoment
        self.onOpenTimeline = onOpenTimeline
        self.onOpenSettings = onOpenSettings
        self.store = store
        self.spine = spine
        _query = State(initialValue: initialQuery)
        _results = StateObject(wrappedValue: SearchResultsModel(store: store))
        // A panel handed a question to start from is answering it, not showing the day.
        _shownBody = State(initialValue: initialQuery.isEmpty ? .activity : .results)
    }

    /// The already-answered form, for previews and the render harness. Nothing it draws can reach
    /// the user's database — including the account one, which is why `account` is the absent reader
    /// rather than the default.
    init(query: String, results: SearchResultsModel, onDismiss: @escaping () -> Void = {}) {
        self.initialQuery = query
        self.onDismiss = onDismiss
        self.store = { nil }
        // A store that is already its own answer: no capture database behind it and no account
        // reader, so the harness cannot reach the user's real memories through this branch however
        // it is driven. See `ActivityStore.holdsAFixedAnswer`.
        self.spine = ActivityStore(days: [])
        _query = State(initialValue: query)
        _results = StateObject(wrappedValue: results)
        _shownBody = State(initialValue: query.isEmpty ? .activity : .results)
    }

    /// What the last handoff could not do, or nil — the second of the two things the note line says.
    ///
    /// Held here rather than on `SearchResultsModel`, which is the reader of this Mac's indexes and
    /// has no business knowing another application exists. Cleared the moment the question changes:
    /// "I couldn't find Claude" standing over a question it was never told about is a sentence about
    /// nothing.
    @State private var handoffNote: String?

    /// The one line under the field, or nil when there is nothing to say and the keyboard hint has
    /// the space instead.
    ///
    /// Only ever a failure — of the read, or of the handoff. A note that appeared after every
    /// successful search would be a status line reporting that the thing on screen is on screen, and
    /// it would resize the window a line taller on every keystroke.
    ///
    /// The handoff leads, because it is the one the user just asked for: a Return that could not
    /// reach Claude is news, and a stale read failure underneath it is not.
    private var note: String? { handoffNote ?? results.loadError }

    /// When the panel is looking at, from the one control that decides it.
    ///
    /// Read off the results model rather than duplicated, because the time chips live in the filter
    /// block that the results body owns. Two copies of "which day" is the bug where the spine and the
    /// grid disagree about what "yesterday" meant.
    private var bounds: (since: Double?, until: Double?) {
        results.time.range(pickedDate: results.pickedDate)
    }

    var body: some View {
        VStack(alignment: .leading, spacing: SearchLayout.panelGap) {
            SearchGlassPanel { promptBar }
            lowerPanel
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
        .onAppear {
            results.ask(query)
            // A freshly mounted surface has no detail on it by definition, so anything still
            // holding the Escape route is a leftover from a panel that was dismissed while a detail
            // was open. Clearing it here is what keeps a stale hold from eating the *next* panel's
            // Escape — the one key that must never do nothing on a summoned overlay.
            ActivityDetailEscape.shared.release()
        }
        .onChange(of: query) { text in
            results.search(text)
            // A new question is not the one the handoff failed on.
            handoffNote = nil
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
            // keyboard back" signal, and a panel brought forward with nothing to ask must not wipe
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
    /// the two the panel is showing, and one place that switches on it, so the surface cannot end up
    /// drawing both or neither.
    @ViewBuilder
    private var lowerPanel: some View {
        switch shownBody {
        case .activity:
            SearchGlassPanel {
                // The time chips are the bar's, not the surface's: `SearchTimeFilter.range` already
                // returns exactly the bounds pair the activity store narrows on, so both bodies
                // answer "when" from one value and cannot disagree about which day it is.
                //
                // **The application's store, not one of this panel's own.** The branch this sits on
                // is unmounted the moment a question is typed and rebuilt when the field is cleared,
                // and the window around it is rebuilt on every summoning — so a store belonging to
                // this view is a corpus thrown away and re-paged several times a session. The
                // reader behind it is `ActivityLocalMemories(OmiActivityFeed())` exactly as it was;
                // what changed is who owns it. See `ActivitySpine`.
                ActivitySurface(
                    spine: spine,
                    query: query,
                    since: bounds.since,
                    until: bounds.until,
                    onOpenMoment: onOpenActivityMoment
                )
                // Stated, not measured, and the one place this surface sizes a body by hand. The
                // results grid hugs its content because a page of results is a finite thing; the
                // spine is a stream of everything this Mac has done, so it is longer than the panel
                // in every state that is not an empty install. Given the ceiling directly, it fills
                // the tallest panel this surface allows and scrolls inside it.
                .frame(
                    width: SearchLayout.panelWidth, height: SearchLayout.maximumResultsBodyHeight,
                    alignment: .topLeading)
            }
        case .results:
            SearchGlassPanel { SearchResultsView(model: results, onOpen: open) }
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
                    // Escape closes the panel — **unless the activity surface has a detail open, in
                    // which case it means "back to the spine" and the panel stays up.** The field
                    // editor's `cancelOperation:` is one of the two routes that sees Escape; the
                    // other is `SearchPanel.sendEvent`, which intercepts key code 53 before the
                    // responder chain runs and must ask the same question there for this to hold in
                    // practice. See `ActivityDetailEscape`.
                    onCancel: cancel,
                    onGridStep: { results.move($0) })
                Spacer(minLength: 12)
                if note == nil { keyboardHint }
                SearchBarExits(onOpenTimeline: onOpenTimeline, onOpenSettings: onOpenSettings)
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

    /// `↵  Ask Claude`, and it is also the control.
    ///
    /// The reference shows only the keycaps. A bar whose one action exists solely as a key press is
    /// unusable to anyone who cannot press it, so the hint is a button — same glyphs, same weight,
    /// with a target under them.
    ///
    /// It used to say `Search`, which was true of Return and is not any more. A keycap that names the
    /// wrong action is worse than no keycap: the panel is already full of results by the time anybody
    /// reads it, so `Search` would read as a refresh right up until it opened another application.
    /// The word names the one thing pressing the key does that the user cannot already see happening.
    private var keyboardHint: some View {
        Button(action: submit) {
            // Both halves on the same rung. The word used to sit a step below the keycap, which is
            // the right emphasis on paper and unavailable here: this bar is glass and glass carries
            // two rungs (see `Ink.tertiary`), so the choice is one rung or an invisible word. The
            // keycap still leads by shape.
            HStack(spacing: 6) {
                Text("↵").inkStyle(.statusLabel, color: Ink.secondary)
                Text("Ask Claude").inkStyle(.statusLabel, color: Ink.secondary)
            }
            .fixedSize()
        }
        .buttonStyle(.plain)
        .accessibilityLabel(Self.askActionName)
        .help(Self.askActionName)
    }

    /// What **typing** is called wherever it is named in words rather than in keycaps — the field's
    /// own label, and what the bar is.
    ///
    /// It names **both** halves on purpose. A user who has only ever seen this bar hand things to
    /// Claude has no reason to expect it to know what was said out loud, and the accessibility label
    /// is one of two places (the placeholder is the other) where that can be said in a sentence.
    ///
    /// It is deliberately not the *Return* key's name. Two actions live on this bar now and they do
    /// different things, so a screen reader has to be able to tell them apart: the field searches
    /// this Mac as you type, and the button beside it sends the question away.
    static let searchActionName = "Search this Mac's screens and conversations"

    /// What Return is called. The counterpart to the keycap, and the only place the destination is
    /// named in a sentence.
    static let askActionName = "Ask Claude this question"

    // MARK: - Submit

    /// **What Return means**, as a value.
    ///
    /// Three answers, decided in one pure place rather than in the middle of `submit`, because the
    /// one that matters is the one nobody thinks to try: Return on a bar with nothing typed into it.
    /// It must not launch anything — an empty question handed to another application is a window
    /// switch the user did not ask for — and "must not" is only checkable if the decision is
    /// something a test can call.
    enum ReturnKey: Equatable {
        /// A card is selected: open that moment. The selection exists for no other purpose, and a
        /// highlighted card that Return ignored would be a dead end the user walked into on purpose.
        case openTheSelection
        /// Nothing typed, so there is no question to hand anybody. `ask` and not `search`: `search`
        /// de-duplicates identical text, and capture is live, so re-asking is a real question with a
        /// possibly different answer. Nothing leaves this app.
        case readAgain
        /// A question, trimmed. It goes to Claude, and it is the only thing that does.
        case askClaude(String)
    }

    static func returnMeans(query: String, hasSelection: Bool) -> ReturnKey {
        guard !hasSelection else { return .openTheSelection }
        let question = query.trimmingCharacters(in: .whitespacesAndNewlines)
        return question.isEmpty ? .readAgain : .askClaude(question)
    }

    private func submit() {
        // The shared chrome cue; it honours the system UI-sound setting itself.
        Sound.effect(.click)
        switch Self.returnMeans(query: query, hasSelection: results.selectedMoment != nil) {
        case .openTheSelection:
            if let selected = results.selectedMoment { open(selected) }
        case .readAgain:
            results.ask(query)
        case .askClaude(let question):
            askClaude(question)
        }
    }

    /// Hand the question over, and say so only if it did not get there.
    ///
    /// **The panel dismisses on a real delivery**, for the same reason it dismisses when it opens a
    /// moment: the answer is now in another window, and a Spotlight panel floating over the
    /// application it just summoned is in the way of the thing it just did. It is also how the user
    /// can tell where the question went — Claude comes forward with it in the composer, which no note
    /// line could say better.
    ///
    /// Anything short of that keeps the panel up and puts the router's own sentence on the note line,
    /// because those are the states nothing else on screen would explain: no Claude on this Mac, no
    /// `claude` command, or a clipboard fallback that needs the user to paste. Dismissing on those
    /// would be the silent failure this whole path is supposed to be incapable of.
    private func askClaude(_ question: String) {
        let target = SettingsStore.shared.claudeTarget
        // Two events, deliberately, because they answer two questions: the control says a person
        // pressed Return meaning "ask Claude", and the handoff says whether it got there. A single
        // event could not separate "nobody uses this" from "it fails for everybody".
        //
        // **The question itself goes nowhere near either of them.** It is the one string in reach at
        // this call site and the schema has nowhere to put it, which is the point of the schema.
        ContextAnalytics.record(.controlUsed(.askClaude))
        switch ClaudeRouter.handOff(question, to: target) {
        case .arrived:
            ContextAnalytics.record(
                .claudeHandoff(target: Self.analyticsTarget(target), delivered: true))
            handoffNote = nil
            onDismiss()
        case .note(let sentence):
            // Not delivered, including the clipboard branch — that one reached Claude and filled
            // nothing in, so the user still has to paste, which is not the question arriving.
            ContextAnalytics.record(
                .claudeHandoff(target: Self.analyticsTarget(target), delivered: false))
            handoffNote = sentence
        }
    }

    /// The preference, in the analytics vocabulary. An exhaustive switch rather than a raw-value
    /// bridge, so a third target added to `ClaudeRouter.Target` is a compile error here rather than
    /// a silent absence from the series.
    private static func analyticsTarget(_ target: ClaudeRouter.Target) -> AnalyticsEvent.ClaudeTarget {
        switch target {
        case .claudeApp: return .claudeApp
        case .terminal: return .terminal
        }
    }

    /// **What Escape means**, in one place.
    ///
    /// A surface with two depths cannot have one answer to the key that leaves. The activity spine
    /// can have a detail pushed over it, and on a panel that dismisses itself the difference between
    /// "back" and "gone" is the difference between losing your place and losing the window. So the
    /// detail is offered the key first; only when nothing is holding it does Escape mean what it has
    /// always meant here.
    private func cancel() {
        guard !ActivityDetailEscape.shared.consume() else { return }
        onDismiss()
    }

    /// Hand a moment to whoever owns the windows.
    ///
    /// One function for both routes — the pointer's click and Return on a selection — so the two can
    /// never diverge into "clicking works and the keyboard does something subtly different".
    private func open(_ moment: SearchMoment) {
        onOpenMoment(moment)
    }
}

// MARK: - The two ways out of the panel

/// **The Timeline pill and the gear**, at the bar's trailing edge.
///
/// The regression they close: this surface had no route to either of the app's other windows. The
/// timeline could only be reached by activating a moment — so a user with no result to activate, and
/// anybody who wanted Settings at all, was on a surface with no way off it. `RewindView`'s header has
/// carried a "Search All" pill and a gear since it shipped, for exactly that reason; this is that pair
/// pointing the other way, drawn to the same metrics so the two surfaces read as one product.
///
/// A type of its own rather than two computed properties on `SearchBarView`, so a test can build the
/// pair, press it, and measure what it costs the bar — see `SearchLayout.trailingControlsWidth`, which
/// is the room the query chip gives up for it.
struct SearchBarExits: View {
    /// Opens the timeline. A closure rather than a call into `RewindWindow`, for the reason every
    /// other window operation in this app is one: a view that opens windows cannot be rendered in a
    /// test or a preview without opening them.
    var onOpenTimeline: () -> Void = {}
    var onOpenSettings: () -> Void = {}

    var body: some View {
        HStack(spacing: 8) {
            timelinePill
            gearButton
        }
        .fixedSize()
    }

    /// "Timeline", with its chord — `RewindView.searchPill`'s shape to the point: 10/5 padding, a
    /// capsule of `Ink.rowFill` inside `Ink.hairline`, and the shortcut in a keycap chip rather than
    /// in the label.
    ///
    /// The chord is `⌘T` and not a bare key, unlike the timeline's `/`: everything typed on this
    /// surface goes into a search field, so a shortcut without a modifier would fire in the middle of
    /// a question.
    private var timelinePill: some View {
        Button(action: onOpenTimeline) {
            HStack(spacing: 6) {
                Image(systemName: "clock.arrow.circlepath")
                    .font(.system(size: 11, weight: .semibold))
                Text("Timeline")
                    .font(.system(size: 12, weight: .medium))
                Text(Self.timelineShortcut)
                    .font(.system(size: 10, weight: .semibold, design: .monospaced))
                    .foregroundStyle(Ink.secondary)
                    .padding(.horizontal, 4)
                    .padding(.vertical, 1)
                    .background(
                        RoundedRectangle(cornerRadius: 3, style: .continuous)
                            .fill(Ink.wash))
            }
            .foregroundStyle(Ink.primary)
            .padding(.horizontal, 10)
            .padding(.vertical, 5)
            .background(
                Capsule(style: .continuous)
                    .fill(Ink.rowFill)
                    .overlay(Capsule(style: .continuous).strokeBorder(Ink.hairline, lineWidth: 1)))
        }
        .buttonStyle(.plain)
        .keyboardShortcut("t", modifiers: .command)
        .accessibilityLabel(Self.timelineActionName)
        .help(Self.timelineActionName)
    }

    /// `RewindView.gearButton`'s 26 pt disc, to the point of the glyph weight — two different gears on
    /// two surfaces of one app is the tell that nobody looked at them together.
    private var gearButton: some View {
        Button(action: onOpenSettings) {
            Image(systemName: "gearshape")
                .font(.system(size: 12, weight: .medium))
                .foregroundStyle(Ink.primary)
                .frame(width: 26, height: 26)
                .background(Circle().fill(Ink.rowFill))
        }
        .buttonStyle(.plain)
        .accessibilityLabel(Self.settingsActionName)
        .help(Self.settingsActionName)
    }

    /// What the pill's keycap prints, and the chord it really binds. One value, so the two cannot
    /// disagree — a hint that names a keystroke nothing listens for is worse than no hint.
    static let timelineShortcut = "⌘T"
    static let timelineActionName = "Open the timeline"
    static let settingsActionName = "Settings"
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
                            .strokeBorder(SearchInk.queryChipStroke, lineWidth: 1)
                    )
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
    /// The arrow keys reach the results from here for the same reason Return and Escape do: the
    /// field holds the first responder for the whole life of this surface, so a key press that never
    /// reaches the field's delegate never happens at all. The cards cannot take focus themselves —
    /// the panel is non-activating and full keyboard access is off by default — so this is not one
    /// way into the results, it is the only one.
    ///
    /// Returns whether the results took the key, which is what lets ← and → be shared: the field
    /// keeps them until a card is selected, and gets them back the moment one is not. See
    /// `SearchResultsModel.move`.
    var onGridStep: (SearchGridStep) -> Bool = { _ in false }

    /// The face the *placeholder* is set in — `SearchMetrics.queryFace`'s size and family at
    /// reading weight. See where it is applied for why the weight differs from the query's.
    static let placeholderFace: NSFont =
        InkFonts.role(size: SearchMetrics.queryFontSize, weight: .regular).metrics

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
        //
        // **The same size and the same family as the query, one weight lighter.** It used to be the
        // query's own semibold face, which on a bar that has no field well around it made an
        // untouched surface look like it already held a question — the prompt read as content, at
        // the loudest weight on the whole surface. The shipping Omi search field draws its
        // placeholder at reading weight and its query heavier, and that contrast is the whole of
        // how a field says "nothing typed yet" when the glass gives it no other edge to say it
        // with. Only the weight moves: the rung is the same, so the contrast this bar needs over a
        // dark wallpaper is untouched. Measured nowhere — `SearchMetrics.chipWidth` sizes the
        // *query* capsule, which never contains this string — so the two faces cannot disagree
        // about anything.
        field.placeholderAttributedString = NSAttributedString(
            string: SearchMetrics.placeholder,
            attributes: [
                .font: Self.placeholderFace, .foregroundColor: NSColor(Ink.secondary),
            ])
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

/// Takes focus the moment it joins a window, so the bar is typeable on the first open — **and takes
/// it back whenever the panel is summoned again.**
///
/// The async pass is the one that sticks: SwiftUI is still assembling the hierarchy when
/// `viewDidMoveToWindow` runs, and a first responder set inside that pass gets replaced.
///
/// The second half closes a gap between what `refocusNotification` promises and what anything did
/// about it. `SearchBarWindow` posts it on `didBecomeKey` and on a `present()` that found the panel
/// already up, documented as the way the field re-takes focus — but its only observer was the
/// prefill handler in `SearchBarView`, which returns immediately when there is no prefill. So focus
/// was taken exactly once per panel *construction*, and a panel re-summoned after focus had moved
/// off the field (to the filter block's date picker, to the Timeline pill) came forward untypeable.
/// The field is the thing that knows how to be focused, so it is the thing that listens.
final class FocusingTextField: NSTextField {
    private var refocus: NSObjectProtocol?

    override func viewDidMoveToWindow() {
        super.viewDidMoveToWindow()
        guard let window else {
            // Left the hierarchy: an observer outliving the field would be a strong reference to a
            // panel that has already closed.
            if let refocus { NotificationCenter.default.removeObserver(refocus) }
            refocus = nil
            return
        }
        takeFocus(in: window)
        guard refocus == nil else { return }
        refocus = NotificationCenter.default.addObserver(
            forName: SearchBarWindow.refocusNotification, object: nil, queue: .main
        ) { [weak self] _ in
            MainActor.assumeIsolated {
                guard let self, let window = self.window else { return }
                self.takeFocus(in: window)
            }
        }
    }

    deinit {
        if let refocus { NotificationCenter.default.removeObserver(refocus) }
    }

    /// Both passes, because only the second one sticks while SwiftUI is still assembling.
    private func takeFocus(in window: NSWindow) {
        window.makeFirstResponder(self)
        DispatchQueue.main.async { [weak self] in
            guard let self, self.window === window else { return }
            window.makeFirstResponder(self)
        }
    }
}
