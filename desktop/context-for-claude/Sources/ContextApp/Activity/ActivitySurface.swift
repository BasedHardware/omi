//
//  ActivitySurface.swift — the Activity view, as one thing a window can mount.
//
//  Three parts and nothing else: the header, the chips, and the stream under them. **The question is
//  not asked here** — the term and the time bounds belong to whatever hosts this, because they are
//  the same term and the same bounds every other surface in the window narrows on, and a second query
//  field would be a second answer to "what am I looking at". They arrive as inputs; the kind axis is
//  the one control this surface owns, because it exists only here.
//
//  **It has a second body.** A row on the spine opens a detail — a conversation with its transcript,
//  a memory or a task with the minute around it — and that detail is *pushed here*, over the header,
//  the chips and the stream, rather than into a window. See `ActivityDetailView` for why. The one
//  consequence for this file is that `body` switches on `detail` before it draws anything: the spine
//  and the detail are one surface with two states, never two surfaces racing to be on screen.
//
//  The header is `Filter` on the left and the corpus sentence on the right. **`Filter` discloses the
//  chips rather than a menu of time windows**, which is the one place this deliberately differs from
//  the reference it is drawn from: there the panel owns the time filter, and here the window already
//  does (`SearchTimeFilter`, one control, above this one). A second `Today / Last 7 days` menu inside
//  the panel would be two controls in one window answering "when" — so the disclosure narrows by
//  *kind*, which is the axis this surface is the only owner of, and the label says which kind is on
//  when the chips are folded away.
//
//  Brand: `Ink` semantics only, two rungs (glass) (INV-UI-1).
//

import ContextCore
import SwiftUI

struct ActivitySurface: View {
    /// What was typed, owned by the host. Trimmed and case-folded by the store.
    var query: String = ""
    /// The time window, as Unix epoch seconds — the same bounds the search surface uses, so the two
    /// narrow on one vocabulary.
    var since: Double?
    var until: Double?
    /// Hands a frame to whatever owns the timeline.
    var onOpenMoment: (ActivityMoment) -> Void = { _ in }

    @StateObject private var store: ActivityStore
    @StateObject private var detailModel: ActivityDetailModel
    @State private var kind: ActivityKind = .all
    /// Whether the chip row is disclosed. **Open by default**: the chips are the surface's one
    /// control, and a filter nobody can see is a filter nobody uses.
    @State private var showsChips = true
    /// The detail on top of the spine, or nil for the spine itself. See the note at the top of the
    /// file — this is the whole of the push.
    @State private var detail: ActivityDetailRequest?

    /// The surface over a store somebody else owns — which in the app is always `ActivitySpine`.
    ///
    /// **The store is handed in rather than built here, and that is the whole of the change that
    /// made re-opening the panel instant.** A `@StateObject` built in this initialiser lived exactly
    /// as long as this view did, and this view is rebuilt on every summoning of the search window
    /// and unmounted every time the panel switches to search results — so a hydrated corpus was
    /// discarded and re-paged from offset zero three different ordinary ways. See `ActivitySpine`.
    ///
    /// It stays a `@StateObject` for SwiftUI's benefit: the wrapped value is the shared instance, so
    /// the autoclosure returns the same object however many times the view is rebuilt, and the host
    /// rather than the view is what keeps it alive.
    init(
        spine: ActivityStore,
        conversations: ActivityConversationReading = ActivityConversationSource(),
        query: String = "",
        since: Double? = nil,
        until: Double? = nil,
        onOpenMoment: @escaping (ActivityMoment) -> Void = { _ in }
    ) {
        _store = StateObject(wrappedValue: spine)
        _detailModel = StateObject(wrappedValue: ActivityDetailModel(source: conversations))
        self.query = query
        self.since = since
        self.until = until
        self.onOpenMoment = onOpenMoment
    }

    /// The surface over a store of its own. Tests and previews that want a fresh spine per case;
    /// the app never takes this path, because a store per surface is what `ActivitySpine` exists to
    /// stop being true.
    init(
        store: @escaping () -> ContextStore?,
        account: ActivityAccountReading = ActivityAccountAbsent(),
        cache: ActivityAccountCache? = nil,
        conversations: ActivityConversationReading = ActivityConversationSource(),
        query: String = "",
        since: Double? = nil,
        until: Double? = nil,
        onOpenMoment: @escaping (ActivityMoment) -> Void = { _ in }
    ) {
        _store = StateObject(
            wrappedValue: ActivityStore(store: store, account: account, cache: cache))
        _detailModel = StateObject(wrappedValue: ActivityDetailModel(source: conversations))
        self.query = query
        self.since = since
        self.until = until
        self.onOpenMoment = onOpenMoment
    }

    /// A surface with its answer already in it, for previews and the render harness. Takes no store
    /// and no account, so nothing it draws can touch the user's database or the network — the same
    /// bargain `SearchResultsModel`'s second initialiser makes.
    init(
        days: [ActivityDay],
        kind: ActivityKind = .all,
        accountReachable: Bool = true,
        corpusSettled: Bool = true,
        detail: ActivityDetailRequest? = nil,
        detailState: ActivityDetailModel.State = .reading
    ) {
        _store = StateObject(
            wrappedValue: ActivityStore(
                days: days, accountReachable: accountReachable, corpusSettled: corpusSettled))
        // The state-carrying model, never the reading one: the store-less surface promises that
        // nothing it draws can reach the network, and a detail that started a read on appear would
        // break that promise from inside a preview.
        _detailModel = StateObject(wrappedValue: ActivityDetailModel(state: detailState))
        _kind = State(initialValue: kind)
        _detail = State(initialValue: detail)
    }

    var body: some View {
        Group {
            if let detail {
                ActivityDetailView(
                    request: detail, model: detailModel, onBack: dismissDetail, onOpen: show)
            } else {
                spine
            }
        }
        // Held for as long as a detail is on screen and released the moment it is not, so Escape
        // can find the way back — see `ActivityDetailEscape` for why it cannot simply be a key
        // handler in this view.
        .onDisappear { ActivityDetailEscape.shared.release() }
    }

    private var spine: some View {
        VStack(alignment: .leading, spacing: ActivitySurfaceLayout.headerGap) {
            ActivityPanelHeader(
                kind: kind,
                isDisclosed: showsChips,
                countSentence: countSentence,
                onToggle: toggleChips
            )
            .padding(.horizontal, ActivitySurfaceLayout.horizontalPadding)
            if showsChips {
                ActivityKindChips(selection: kind, onSelect: { kind = $0 })
                    .padding(.horizontal, ActivitySurfaceLayout.horizontalPadding)
            }
            // Only when a column on screen is standing in for the account, and never for a reason
            // the reader has to go looking for. See `ActivityAccountLocalNote` — a locally-read
            // memory column is the one degraded state this surface has that is otherwise completely
            // invisible.
            if let local = localNote {
                ActivityAccountLocalStrip(note: local)
                    .padding(.horizontal, ActivitySurfaceLayout.horizontalPadding)
            }
            ActivityStream(
                store: store,
                onOpenMoment: onOpenMoment,
                onOpen: { show(ActivityDetailRequest.make($0, in: store.days)) })
        }
        .padding(.top, ActivitySurfaceLayout.topPadding)
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
        // One place the question reaches the store, so the chip, the term and the window can never
        // be applied in three different orders and leave the list answering two of the three.
        .onAppear { apply() }
        .onChange(of: kind) { _, _ in apply() }
        .onChange(of: query) { _, _ in apply() }
        .onChange(of: since) { _, _ in apply() }
        .onChange(of: until) { _, _ in apply() }
        .accessibilityIdentifier("activity-surface")
    }

    /// The corner sentence. Resolved from the store's own counts rather than recomputed here: a
    /// second count of the same data by different code is the standard way a search surface starts
    /// lying about itself.
    private var countSentence: String {
        guard let total = store.corpusTotal else {
            // A count that finished and found nothing is an answer, not a count still running.
            return store.corpusSettled ? ActivityCount.nothingYet : ActivityCount.counting
        }
        return ActivityCount.sentence(
            matching: store.matchCount, total: total, isFiltering: store.isFiltering,
            isSettled: store.corpusSettled,
            // **The scope narrows when the account is silent.** The empty copy that would otherwise
            // say so is only reachable on a *completely* empty stream, which on any Mac with screen
            // capture on never happens — so this line was the only thing on screen, and it was
            // claiming to count "everything Omi has kept" over half of it.
            scope: ActivityCount.scope(accountUnreachable: store.accountUnreachableReason))
    }

    /// The caveat over the stream, or nil when nothing on it is standing in for the account.
    private var localNote: ActivityAccountLocalNote? {
        ActivityAccountLocalNote.resolve(
            locallySourced: store.accountLocallySourced,
            answered: store.accountAnswered,
            kind: kind,
            reason: store.accountUnreachableReason)
    }

    private func toggleChips() {
        InkReduceMotion.perform(.easeOut(duration: InkMotion.stepTransition)) {
            showsChips.toggle()
        }
    }

    private func apply() {
        store.apply(kind: kind, query: query, since: since, until: until)
    }

    // MARK: - Pushing a detail, and coming back

    /// The one place a detail is pushed — from the spine, and from inside another detail when a
    /// memory offers the conversation that was running at the time.
    ///
    /// The read is started here rather than inside the detail view's `task`, so that opening the
    /// *same* conversation twice does not re-run a network call the model already answered, and so
    /// a memory that carries no read at all never starts one.
    private func show(_ request: ActivityDetailRequest) {
        guard request != detail else { return }
        InkReduceMotion.perform(.easeOut(duration: InkMotion.press)) { detail = request }
        ActivityDetailEscape.shared.hold { dismissDetail() }
        if case .conversation(let conversation) = request.subject {
            detailModel.read(conversation)
        }
    }

    private func dismissDetail() {
        ActivityDetailEscape.shared.release()
        InkReduceMotion.perform(.easeOut(duration: InkMotion.press)) { detail = nil }
    }
}

enum ActivitySurfaceLayout {
    static let horizontalPadding: CGFloat = 12
    static let topPadding: CGFloat = 12
    /// Between the header row, the chips, and the stream.
    static let headerGap: CGFloat = 10
    /// Between two chips.
    static let chipSpacing: CGFloat = 6
    /// Inside a chip, either side of its label.
    static let chipHorizontalPadding: CGFloat = 12
    /// The header control's lift over a type chip, so `Filter` reads as the row's own control rather
    /// than as a sixth chip that wandered up a line.
    static let headerControlLift: CGFloat = 2
    /// Between the glyph, the word and the chevron inside the `Filter` control.
    static let filterSpacing: CGFloat = 6
    /// The chevron. A step under the label, because it is punctuation on a control rather than a
    /// second thing to read.
    static let filterChevronSize: CGFloat = 9

    /// **Whether `Filter` wears a pill.**
    ///
    /// It used to, always — and a pill was precisely the wrong thing to give it. The five things
    /// directly underneath are pills, so a sixth one a line above them said `Filter` was another
    /// kind you could solo rather than the control that reveals them. The shipping Omi Activity page
    /// draws this row's leading control bare for that reason, and this surface is the same row.
    ///
    /// The pill comes back for the only two states where it is doing work: a **soloed kind**, where
    /// the fill is the one thing on the row saying the list is being narrowed at all, and **hover**,
    /// which is now the control's only affordance — bare type with no feedback under the pointer is
    /// a control nobody discovers.
    ///
    /// A value rather than a condition inside the `body` for the reason everything else in this
    /// enum is one: "the resting row has no pill on it" is then a claim a test can hold instead of a
    /// thing somebody has to re-notice in a screenshot.
    nonisolated static func filterControlIsFilled(kind: ActivityKind, isHovering: Bool) -> Bool {
        kind != .all || isHovering
    }
}

// MARK: - The header

/// `Filter` on the left, what is being counted on the right.
///
/// The chevron **turns** rather than swapping glyph, for the reason the day header's does: the
/// rotation is the thing that says the two states are one control.
struct ActivityPanelHeader: View {
    let kind: ActivityKind
    let isDisclosed: Bool
    let countSentence: String
    let onToggle: () -> Void

    @State private var isHovering = false

    /// A folded row still has to say what is on. `All` is the absence of a filter, so the control
    /// keeps its own name there and takes the kind's only when one is actually soloed.
    private var title: String { kind == .all ? "Filter" : kind.title }

    var body: some View {
        HStack(alignment: .center, spacing: ActivitySurfaceLayout.chipSpacing) {
            Button(action: onToggle) {
                HStack(spacing: ActivitySurfaceLayout.filterSpacing) {
                    Image(systemName: "line.3.horizontal.decrease")
                        .inkStyle(.statusLabel)
                    Text(title)
                        .inkStyle(.statusLabel)
                        .lineLimit(1)
                        .fixedSize()
                    Image(systemName: "chevron.right")
                        .font(
                            .system(
                                size: ActivitySurfaceLayout.filterChevronSize, weight: .semibold)
                        )
                        .rotationEffect(.degrees(isDisclosed ? 90 : 0))
                        .animation(
                            InkReduceMotion.animation(
                                .easeOut(duration: InkMotion.stepTransition)),
                            value: isDisclosed)
                }
                .foregroundStyle(Ink.primary)
                .padding(.horizontal, ActivitySurfaceLayout.chipHorizontalPadding)
                .frame(height: SearchLayout.chipHeight + ActivitySurfaceLayout.headerControlLift)
                // Bare at rest — see `ActivitySurfaceLayout.filterControlIsFilled`. The height is
                // unconditional so the row does not change shape when the pill arrives.
                .activityChip(
                    isSelected: kind != .all,
                    isHovering: isHovering,
                    isFilled: ActivitySurfaceLayout.filterControlIsFilled(
                        kind: kind, isHovering: isHovering))
            }
            .buttonStyle(.plain)
            .onHover { isHovering = $0 }
            .help(isDisclosed ? "Hide the type filter" : "Show the type filter")
            .accessibilityLabel(Text("Filter"))
            .accessibilityValue(Text(kind.title))
            .accessibilityIdentifier("activity-filter")

            Spacer(minLength: 8)

            // Monospaced digits so a number climbing under the reader — which is exactly what it does
            // while the day walk runs — does not shuffle the whole sentence sideways each time.
            Text(countSentence)
                .inkStyle(.statusLabel, color: Ink.secondary)
                .monospacedDigit()
                .lineLimit(1)
                .accessibilityIdentifier("activity-count")
        }
    }
}

// MARK: - The chips

/// The one axis this surface owns: which kind of thing the stream is showing.
///
/// Typed rather than an index into a string array — a control that reports "segment 1" is one
/// reordering away from showing screens when somebody asked for conversations. **A row of separate
/// pills, not a capsule of capsules**: the segmented form said these five were alternatives inside
/// one control, which is the wrong claim on a surface whose default is the merged view.
struct ActivityKindChips: View {
    let selection: ActivityKind
    let onSelect: (ActivityKind) -> Void

    var body: some View {
        HStack(spacing: ActivitySurfaceLayout.chipSpacing) {
            ForEach(ActivityKind.chips) { kind in
                ActivityTypeChip(
                    kind: kind,
                    isSelected: kind == selection,
                    action: {
                        guard kind != selection else { return }
                        InkReduceMotion.perform(.easeOut(duration: InkMotion.checkbox)) {
                            onSelect(kind)
                        }
                    })
            }
            Spacer(minLength: 0)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .accessibilityIdentifier("activity-kind-chips")
    }
}

private struct ActivityTypeChip: View {
    let kind: ActivityKind
    let isSelected: Bool
    let action: () -> Void

    @State private var isHovering = false

    var body: some View {
        Button(action: action) {
            Text(kind.title)
                .inkStyle(.statusLabel, color: isSelected ? Ink.primary : Ink.secondary)
                .lineLimit(1)
                .fixedSize()
                .padding(.horizontal, ActivitySurfaceLayout.chipHorizontalPadding)
                .frame(height: SearchLayout.chipHeight)
                .activityChip(isSelected: isSelected, isHovering: isHovering)
        }
        .buttonStyle(.plain)
        .onHover { isHovering = $0 }
        .animation(InkReduceMotion.animation(.easeOut(duration: InkMotion.press)), value: isSelected)
        .accessibilityAddTraits(isSelected ? .isSelected : [])
        .accessibilityIdentifier("activity-kind-\(kind.rawValue)")
    }
}

extension View {
    /// The pill every control in this header wears.
    ///
    /// It borrows `SearchInk`'s chip fills rather than declaring a second set, because this panel
    /// sits directly under the search bar's own chips in the same window: one product cannot have two
    /// opinions about what a chip looks like six points apart. The selected one is the only *filled*
    /// thing, so the row ranks by weight rather than by colour (INV-UI-1).
    ///
    /// Reachable from the detail screen for exactly that reason: its way back is a chip, and a
    /// second definition of the pill would be the second opinion this comment exists to prevent.
    /// - Parameter isFilled: whether the pill is drawn at all. Only the header's `Filter` control
    ///   ever passes `false`: a control that discloses the chips must not look like one of them.
    ///   The hit shape is the capsule either way, so a bare control is exactly as easy to press as a
    ///   filled one — the pill is what is missing, never the target.
    func activityChip(isSelected: Bool, isHovering: Bool, isFilled: Bool = true) -> some View {
        let fill: Color =
            isSelected
            ? SearchInk.chipFillSelected : (isHovering ? SearchInk.chipFillHover : SearchInk.chipFill)
        return
            background(
                Group {
                    if isFilled {
                        Capsule(style: .continuous).fill(fill)
                            .overlay(
                                Capsule(style: .continuous)
                                    .strokeBorder(SearchInk.chipStroke, lineWidth: 1))
                    }
                }
            )
            .contentShape(Capsule(style: .continuous))
    }
}

// MARK: - Previews

#if DEBUG
    #Preview("Activity") {
        ActivitySurface(days: [])
            .frame(width: 860, height: 560)
            .background(Ink.surface)
    }
#endif
