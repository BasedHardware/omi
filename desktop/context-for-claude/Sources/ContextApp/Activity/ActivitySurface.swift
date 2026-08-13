//
//  ActivitySurface.swift — the Activity view, as one thing a window can mount.
//
//  Two parts and nothing else: the kind switcher, and the stream under it. **The question is not
//  asked here** — the term and the time bounds belong to whatever hosts this, because they are the
//  same term and the same bounds every other surface in the window narrows on, and a second query
//  field would be a second answer to "what am I looking at". They arrive as inputs; the switcher is
//  the one control this surface owns, because the kind axis exists only here.
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
    /// Hands a conversation to whatever owns transcripts.
    var onOpenConversation: (ActivityConversation) -> Void = { _ in }

    @StateObject private var store: ActivityStore
    @State private var kind: ActivityKind = .everything

    init(
        store: @escaping () -> ContextStore?,
        query: String = "",
        since: Double? = nil,
        until: Double? = nil,
        onOpenMoment: @escaping (ActivityMoment) -> Void = { _ in },
        onOpenConversation: @escaping (ActivityConversation) -> Void = { _ in }
    ) {
        _store = StateObject(wrappedValue: ActivityStore(store: store))
        self.query = query
        self.since = since
        self.until = until
        self.onOpenMoment = onOpenMoment
        self.onOpenConversation = onOpenConversation
    }

    /// A surface with its answer already in it, for previews and the render harness. Takes no
    /// store, so nothing it draws can touch the user's database — the same bargain
    /// `SearchResultsModel`'s second initialiser makes.
    init(days: [ActivityDay], kind: ActivityKind = .everything) {
        _store = StateObject(wrappedValue: ActivityStore(days: days))
        _kind = State(initialValue: kind)
    }

    var body: some View {
        VStack(alignment: .leading, spacing: ActivitySurfaceLayout.switcherGap) {
            ActivityKindSwitcher(selection: kind, onSelect: { kind = $0 })
                .padding(.horizontal, ActivitySurfaceLayout.horizontalPadding)
            ActivityStream(
                store: store,
                onOpenMoment: onOpenMoment,
                onOpenConversation: onOpenConversation)
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

    private func apply() {
        store.apply(kind: kind, query: query, since: since, until: until)
    }
}

enum ActivitySurfaceLayout {
    static let horizontalPadding: CGFloat = 12
    static let topPadding: CGFloat = 12
    static let switcherGap: CGFloat = 10
}

// MARK: - The switcher

/// The one control this surface owns: which kind of thing the stream is showing.
///
/// Typed rather than an index into a string array — a control that reports "segment 1" is one
/// reordering away from showing screens when somebody asked for conversations. A capsule of
/// capsules, like every other selectable chip in this system: the selected pill is the only filled
/// thing, so the row ranks by weight rather than by colour.
struct ActivityKindSwitcher: View {
    let selection: ActivityKind
    let onSelect: (ActivityKind) -> Void

    var body: some View {
        HStack(spacing: 4) {
            ForEach(ActivityKind.chips) { kind in
                Button {
                    guard kind != selection else { return }
                    InkReduceMotion.perform(.easeOut(duration: InkMotion.checkbox)) {
                        onSelect(kind)
                    }
                } label: {
                    Text(kind.title)
                        .inkStyle(.rowCopy, color: kind == selection ? Ink.primary : Ink.secondary)
                        .lineLimit(1)
                        .fixedSize()
                        .padding(.horizontal, 14)
                        .padding(.vertical, 6)
                        .background(
                            Capsule(style: .continuous)
                                .fill(kind == selection ? Ink.rowFillHover : Color.clear)
                        )
                        .contentShape(Capsule(style: .continuous))
                }
                .buttonStyle(.plain)
                .accessibilityAddTraits(kind == selection ? .isSelected : [])
                .accessibilityIdentifier("activity-kind-\(kind.rawValue)")
            }
        }
        .padding(4)
        .background(Capsule(style: .continuous).fill(Ink.rowFill))
        .frame(maxWidth: .infinity, alignment: .leading)
        .accessibilityIdentifier("activity-kind-switcher")
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
