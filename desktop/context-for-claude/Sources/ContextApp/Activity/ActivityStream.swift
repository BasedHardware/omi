//
//  ActivityStream.swift — the list itself: one day, top to bottom.
//
//  It draws no chrome — no query field, no chips, no frame, no count line — because the surface
//  above owns all four. **What it owns is the reading order:** one merged reverse-chronological
//  stream grouped by day, with the conversation dominant and the frames it produced indented
//  beneath it, and an hour rail beside it running the same direction the list does.
//
//  A day can be **folded shut** from its own header. Folding is presentation and never a filter:
//  the rows stay composed, stay counted in `ActivityStore.matchCount`, and come back in the same
//  place. The one thing it moves is the hour rail — which tracks the topmost visible *row* and
//  therefore cannot see a folded day at all.
//
//  Brand: `Ink` semantics only, two rungs (glass) (INV-UI-1).
//

import Combine
import SwiftUI

// MARK: - Viewport

/// Which row is under the top of the list.
///
/// Deliberately a reference type held in `@State` rather than a `@StateObject`: the stream needs to
/// *own* it without *observing* it. Scrolling changes this several times a second, and a subscribed
/// parent would re-evaluate the whole list every time. Only the rail observes it, so only the rail
/// redraws.
@MainActor
final class ActivityViewport: ObservableObject {
    @Published private(set) var dayID: Date?
    @Published private(set) var hour: Int?

    func report(dayID: Date, hour: Int) {
        // Assign only on a real change: an identical publish is a redraw of the rail for nothing.
        if self.dayID != dayID { self.dayID = dayID }
        if self.hour != hour { self.hour = hour }
    }
}

/// What one row tells the viewport about itself. The row nearest the top of the list wins.
private struct ActivityRowAnchor: Equatable {
    let dayID: Date
    let hour: Int
    /// The row's bottom edge in the list's coordinate space. A row whose bottom is above the
    /// reading line has scrolled behind the sticky header; among the rest, the smallest bottom is
    /// the topmost visible row.
    let bottom: CGFloat
}

private struct ActivityTopRowKey: PreferenceKey {
    static let defaultValue: ActivityRowAnchor? = nil

    static func reduce(value: inout ActivityRowAnchor?, nextValue: () -> ActivityRowAnchor?) {
        guard let next = nextValue(), next.bottom > ActivityLayout.readingLine else { return }
        guard let current = value else {
            value = next
            return
        }
        if next.bottom < current.bottom { value = next }
    }
}

enum ActivityLayout {
    /// The line the list is read from: just under the sticky day header. A row whose bottom is
    /// above this is behind the header and is not what anybody is looking at.
    static let readingLine: CGFloat = ActivityMetrics.dayHeaderHeight + 4
    static let coordinateSpace = "context.activity"
    /// Between the lane's edge and the rows in it.
    static let lanePadding: CGFloat = 8
}

// MARK: - Stream

struct ActivityStream: View {
    @ObservedObject var store: ActivityStore
    /// Hands a frame to whatever owns the timeline. Defaulted so a preview can draw the list
    /// without a route to a window.
    var onOpenMoment: (ActivityMoment) -> Void = { _ in }
    /// Hands a conversation, a memory or a task to whatever pushes details. One closure for the
    /// three, because they leave this list by one route and arrive at one screen.
    var onOpen: (ActivityDetailSubject) -> Void = { _ in }

    @StateObject private var viewport = ActivityViewport()
    /// Which days are folded shut. Lives with the view rather than with the store because it is a
    /// reading position, not data: it is worth exactly as long as this list is on screen.
    @State private var collapse = ActivityDayCollapse()

    /// Whether there is a day for the rail to be about.
    ///
    /// A rail beside an empty list has no day to count, and its honest-looking "—" over "counting
    /// screen moments" then never resolves — on a Mac that has captured nothing it would sit there
    /// claiming to be counting for the rest of the session. While the first read is still running
    /// that claim is true, so the rail stays; once the read is done and there is still nothing, the
    /// list's own empty state is the whole answer and the rail is drawing a clock for no day.
    ///
    /// **And it is dropped whole when the chip has filtered its subject off the screen.** Every
    /// number on the rail is about screen capture — the headline counts screen moments, the bars are
    /// a histogram of them, the footer counts the day's conversations — so beside a soloed
    /// `Memories` it was describing, in detail, a day of things the list was excluding. Caught in the
    /// render harness: "counting screen moments / Today" and "2 conversations" standing next to four
    /// memories and nothing else. The narrow breakpoint already drops the rail rather than showing a
    /// worse version of it; this is the same rule for a different reason.
    private var describesADay: Bool {
        guard store.kind.showsLocalCapture else { return false }
        return !store.days.isEmpty || store.isPreparing
    }

    var body: some View {
        GeometryReader { proxy in
            HStack(spacing: 0) {
                if proxy.size.width >= ActivityHourRail.breakpoint, describesADay {
                    ActivityRailColumn(store: store, viewport: viewport, collapse: collapse)
                    Rectangle().fill(Ink.separator).frame(width: 1)
                }
                Group {
                    if store.days.isEmpty {
                        emptyState
                    } else {
                        stream
                    }
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity)
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .task { store.start() }
    }

    // MARK: The list

    private var stream: some View {
        ScrollView {
            LazyVStack(alignment: .leading, spacing: 0, pinnedViews: [.sectionHeaders]) {
                ForEach(store.days) { day in
                    Section {
                        // Folding is presentation, never a filter: the rows are still composed,
                        // still counted, and still in the same chronological place when they come
                        // back.
                        if !collapse.contains(day.id) {
                            ForEach(day.rows) { row in
                                ActivityRowView(
                                    row: row,
                                    showsIndent: store.kind == .all,
                                    loader: store.loader,
                                    onOpenMoment: onOpenMoment,
                                    onOpen: onOpen
                                )
                                .background(anchor(for: row, in: day))
                            }
                        }
                    } header: {
                        ActivityDayHeader(
                            day: day,
                            isCollapsed: collapse.contains(day.id),
                            onToggle: { toggleCollapse(day) }
                        )
                    }
                }
            }
            .padding(.horizontal, ActivityLayout.lanePadding)
            .padding(.bottom, ActivityMetrics.rowGap)
        }
        .coordinateSpace(name: ActivityLayout.coordinateSpace)
        .onPreferenceChange(ActivityTopRowKey.self) { anchor in
            guard let anchor else { return }
            Task { @MainActor in viewport.report(dayID: anchor.dayID, hour: anchor.hour) }
        }
    }

    /// A layout-neutral reporter behind each row. A `GeometryReader` in a `background` never affects
    /// layout, and inside a `LazyVStack` only the rows that exist report — a dozen or so, not a
    /// thousand.
    private func anchor(for row: ActivityRow, in day: ActivityDay) -> some View {
        GeometryReader { proxy in
            Color.clear.preference(
                key: ActivityTopRowKey.self,
                value: ActivityRowAnchor(
                    dayID: day.id,
                    hour: Calendar.current.component(.hour, from: row.anchor),
                    bottom: proxy.frame(in: .named(ActivityLayout.coordinateSpace)).maxY
                )
            )
        }
    }

    /// Folds one day shut, or opens it again. Animated through the gate rather than with a raw
    /// `withAnimation`, so Reduce Motion gets the instant version instead of hundreds of rows
    /// sliding away.
    private func toggleCollapse(_ day: ActivityDay) {
        InkReduceMotion.perform(.easeOut(duration: InkMotion.stepTransition)) {
            collapse.toggle(day.id)
        }
    }

    // MARK: Empty

    /// Never an illustration and never a shrug — and never a claim the store is not entitled to
    /// make. See `ActivityEmptyCopy`.
    private var emptyState: some View {
        VStack(alignment: .center, spacing: 6) {
            Text(copy.headline)
                .inkStyle(.rowCopy, color: Ink.primary)
                .multilineTextAlignment(.center)
            if let detail = copy.detail {
                Text(detail)
                    .inkStyle(.statusLabel, color: Ink.secondary)
                    .multilineTextAlignment(.center)
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .center)
        .padding(24)
        .accessibilityIdentifier("activity-empty")
    }

    private var copy: ActivityEmptyCopy {
        ActivityEmptyCopy.resolve(
            isPreparing: store.isPreparing,
            readFailure: store.readFailure,
            capture: store.capture,
            query: store.currentQuery,
            kind: store.kind,
            accountReachable: store.accountReachable,
            accountUnreachableReason: store.accountUnreachableReason)
    }
}

// MARK: - What an empty stream is allowed to say

/// The two lines an empty stream shows, resolved from state rather than assembled in a `body`.
///
/// The rule worth stating: **"nothing was captured" is a claim about the machine, and it may only
/// be made once something has actually been read.** A read that is still running, one that threw,
/// and an account that never answered are none of them an empty answer — and saying so is the
/// difference between a surface you can trust and one that quietly under-reports the day.
///
/// **An unreachable account is the newest of those and the easiest to get wrong**, because it is the
/// one that renders as a perfectly ordinary empty list. Three of the five things this surface shows
/// live in the account, so a signed-out Mac soloed to `Memories` has nothing to draw — and
/// "Nothing captured in this window yet" there is a claim about the user's life made from a failed
/// network read.
///
/// **And "unreachable" is itself several different things to the person reading it.** A key the
/// account rejected is a thing they can fix in one action; being signed out is not a fault at all;
/// Airgap Mode is a switch they turned on themselves and can turn off. Telling all three "I couldn't
/// reach your Omi account" is true and useless — it hands someone a dead end where they had a next
/// step. So each names the state and the action, and none of them ever implies the account is empty.
struct ActivityEmptyCopy: Equatable, Sendable {
    let headline: String
    /// `nil` while the first day is still being read — there is nothing useful to add to "reading".
    let detail: String?

    /// The sentence an unreachable state ends on **while the local half is on screen**: the local
    /// half is still real, and the missing half is named, so an empty list is never mistaken for an
    /// empty life.
    ///
    /// It may only be said when it is true. Under a soloed `Memories`, `Tasks` or `Conversations`
    /// chip the local half is *excluded by the filter the user is looking at*, so promising that
    /// screen moments show up here is a sentence the surface immediately contradicts — see
    /// `stillShowing(under:)`.
    private static let localHalfStillShows =
        "Screen moments from this Mac still show up here. Conversations, memories and tasks come "
        + "from your account."

    /// What the reader is told about the half this filter is *not* showing.
    private static func stillShowing(under kind: ActivityKind) -> String {
        guard kind.showsLocalCapture else {
            return "\(kind.title) come from your Omi account, so this list stays empty until it answers."
        }
        return localHalfStillShows
    }

    /// - Parameters:
    ///   - capture: whether this Mac's own database could be asked at all. Reported before the
    ///     account, because a machine that could not be asked outranks an account that answered —
    ///     see `ActivityCaptureAvailability`.
    ///   - kind: which chip is lit, and therefore **which sources are even in scope**. The account's
    ///     silence is not an explanation for an empty `Rewind`, and this Mac's capture is not an
    ///     explanation for an empty `Memories`.
    static func resolve(
        isPreparing: Bool,
        readFailure: String?,
        capture: ActivityCaptureAvailability = .open,
        query: String,
        kind: ActivityKind,
        accountReachable: Bool,
        accountUnreachableReason: ActivityAccountUnreachableReason? = nil
    ) -> ActivityEmptyCopy {
        // The local half's two failures, and only while the local half is one of the things being
        // asked for. Both outrank everything below them: a surface that could not look must never
        // report what it found.
        if kind.showsLocalCapture {
            if let readFailure {
                return ActivityEmptyCopy(
                    headline: "Couldn't read this Mac's capture.", detail: readFailure)
            }
            switch capture {
            case .opening:
                return ActivityEmptyCopy(
                    headline: "This Mac's capture isn't open yet.",
                    detail: openingDetail(kind))
            case .unavailable:
                return ActivityEmptyCopy(
                    headline: "This Mac's capture didn't open.",
                    detail:
                        "This is not an empty history — none of it could be read. Close this panel "
                        + "and open it again to look once more.")
            case .open:
                break
            }
        }
        guard !isPreparing else {
            return ActivityEmptyCopy(headline: "Reading your day…", detail: nil)
        }
        guard query.isEmpty else {
            return ActivityEmptyCopy(
                headline: "Nothing captured matches “\(query)”.",
                detail: "Try a different word, or widen the time window.")
        }
        // **Only when the account is a source of what is being shown.** Soloed to `Rewind`, nothing
        // on screen comes from the account, and blaming it for a day with no screen capture is a
        // confident wrong answer about the wrong machine.
        guard accountReachable || !kind.showsAccount else {
            return unreachable(accountUnreachableReason, kind: kind)
        }
        return ActivityEmptyCopy(
            headline: "Nothing captured in this window yet.", detail: emptyKindDetail(kind))
    }

    /// The second line while the database is still being opened. **Future tense, deliberately**: at
    /// this instant there is nothing local on screen, so a sentence claiming screen moments "still
    /// show up here" is a promise the surface is in the middle of breaking.
    private static func openingDetail(_ kind: ActivityKind) -> String {
        guard kind.showsAccount else { return "Screen moments appear here as soon as it opens." }
        return "Screen moments appear here as soon as it opens. Conversations, memories and tasks "
            + "come from your account."
    }

    private static func unreachable(
        _ reason: ActivityAccountUnreachableReason?, kind: ActivityKind
    ) -> ActivityEmptyCopy {
        let stillShowing = stillShowing(under: kind)
        switch reason {
        case .airgapped:
            return ActivityEmptyCopy(
                headline: "Airgap Mode is on, so your Omi account isn't being read.",
                detail: stillShowing + " Turn Airgap Mode off in Settings to bring them back.")
        case .signedOut:
            return ActivityEmptyCopy(
                headline: "Sign in to Omi to see your account here.",
                detail: stillShowing)
        // The one unreachable reason that repairs itself: nothing is wrong with the key or this Mac,
        // the account is asking us to wait, and `ActivityStore.scheduleAccountReread` is already
        // waiting. So it says so — and says nothing about signing in or reconnecting, which would
        // send someone to fix a thing that is not broken.
        case .rateLimited:
            return ActivityEmptyCopy(
                headline: "Your Omi account is rate-limiting this Mac, so it isn't answering yet.",
                detail: "Nothing is wrong with your account — I'll ask again shortly. " + stillShowing)
        // One sentence for both, because they are one thing to the reader: this Mac cannot open an
        // account that is there. Which of the two it was — a key the account refused, or one that
        // was never minted — changes nothing they can do about it.
        case .keyRejected, .keyUnavailable:
            return ActivityEmptyCopy(
                headline: "Omi couldn't authenticate this Mac, so your account can't be read.",
                detail:
                    "This is not an empty account. Sign out and back in to Omi from the menu bar to "
                    + "reconnect it. " + stillShowing)
        case .noAnswer, .none:
            return ActivityEmptyCopy(
                headline: "I couldn't reach your Omi account.", detail: stillShowing)
        }
    }

    private static func emptyKindDetail(_ kind: ActivityKind) -> String {
        switch kind {
        case .all: return "Conversations, memories, tasks and screen moments appear here as they happen."
        case .conversations: return "Conversations appear here once this Mac has heard one."
        case .memories: return "Memories appear here as Omi learns something worth keeping."
        case .tasks: return "Tasks appear here as Omi hears you commit to something."
        case .rewind: return "Screen moments appear here while screen capture is on."
        }
    }
}

// MARK: - Rail column

/// The rail, in its own view so a scroll redraws twenty-four bars rather than the whole list.
private struct ActivityRailColumn: View {
    @ObservedObject var store: ActivityStore
    @ObservedObject var viewport: ActivityViewport
    let collapse: ActivityDayCollapse

    /// The day the rail describes.
    ///
    /// Normally the one the list reported, which comes from the topmost visible *row*. **A folded
    /// day has no rows**, so it can never be reported again — but it can still be the last thing
    /// reported before it was folded, and a rail describing a day whose rows are all hidden is a
    /// rail pointing at nothing. So a reported day that has since folded is dropped in favour of
    /// the first day still open, and only when every day is folded does it fall back to the newest.
    private var dayID: Date? {
        if let reported = viewport.dayID, !collapse.contains(reported) { return reported }
        return store.days.first { !collapse.contains($0.id) }?.id ?? store.days.first?.id
    }

    private var day: ActivityDay? { store.days.first { $0.id == dayID } }

    /// The hour marker belongs to the day the list actually reported. Carrying it onto a day chosen
    /// by the fallback above would light up an hour on a rail for a day nobody is reading.
    private var currentHour: Int? {
        guard let dayID, dayID == viewport.dayID else { return nil }
        return viewport.hour
    }

    var body: some View {
        ActivityHourRail(
            density: dayID.map(store.density(for:)) ?? Array(repeating: 0, count: 24),
            currentHour: currentHour,
            momentCount: dayID.flatMap(store.momentCount(for:)),
            dayTitle: day?.title ?? "",
            conversationCount: day?.conversationCount ?? 0
        )
    }
}
