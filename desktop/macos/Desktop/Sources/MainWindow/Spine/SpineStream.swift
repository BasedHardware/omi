//
//  SpineStream.swift — the results panel's body: one day, top to bottom.
//
//  This is what occupies `QueryResultsPanel`'s seam. It draws no chrome — no query field, no chips, no
//  frame, no count line — because the panel above owns all four. It reads one value down
//  (`QueryShellRequest`: the term, the type, the time window) and reports one number up
//  (`queryShellMatchCount`), which is the whole of its contract with the shell.
//
//  **What it owns is the reading order.** One merged reverse-chronological stream grouped by day, with
//  the conversation dominant and the memories and frames it produced indented beneath it — and an hour
//  rail beside it running the same direction the list does.
//
//  A day can be **folded shut** from its own header. Folding is presentation and never a filter: the
//  rows stay composed, stay counted in `queryShellMatchCount`, and come back in the same place. The
//  two things it does move are the hour rail — which tracks the topmost visible *row* and therefore
//  cannot see a folded day at all — and the load-more footer, which must not page the account away
//  behind a screen that is nothing but headers. Both are handled below.
//
//  **What it deliberately does not own is any page's job.** Opening a conversation hands it to
//  Conversations, which keeps search, filters, folders, starring, merge, edit, delete, refresh,
//  pagination and full-row selection (INV-NAV-1); the brain map hands off to the graph; a frame hands
//  off to Rewind. The one capability it hosts inline is the star, because a star is a single
//  authoritative write and a list you cannot star is a list you have to leave to use.
//
//  Brand: `Ink` semantics only, two rungs (glass) (INV-UI-1).
//

import AppKit
import Combine
import OmiTheme
import SwiftUI

// MARK: - Viewport

/// Which row is under the top of the list.
///
/// Deliberately a reference type held in `@State` rather than a `@StateObject`: the stream needs to
/// *own* it without *observing* it. Scrolling changes this several times a second, and a subscribed
/// parent would re-evaluate the whole list every time. Only the rail observes it, so only the rail
/// redraws — which is the same class of `@Published` churn a previous pass at this window was slow
/// because of.
@MainActor
final class SpineViewport: ObservableObject {
  @Published private(set) var dayID: Date?
  @Published private(set) var hour: Int?

  func report(dayID: Date, hour: Int) {
    // Assign only on a real change: an identical publish is a redraw of the rail for nothing.
    if self.dayID != dayID { self.dayID = dayID }
    if self.hour != hour { self.hour = hour }
  }
}

/// What one row tells the viewport about itself. The row nearest the top of the list wins.
private struct SpineRowAnchor: Equatable {
  let dayID: Date
  let hour: Int
  /// The row's bottom edge in the list's coordinate space. A row whose bottom is above the reading
  /// line has scrolled behind the sticky header; among the rest, the smallest bottom is the topmost
  /// visible row.
  let bottom: CGFloat
}

private struct SpineTopRowKey: PreferenceKey {
  static let defaultValue: SpineRowAnchor? = nil

  static func reduce(value: inout SpineRowAnchor?, nextValue: () -> SpineRowAnchor?) {
    guard let next = nextValue(), next.bottom > SpineLayout.readingLine else { return }
    guard let current = value else {
      value = next
      return
    }
    if next.bottom < current.bottom { value = next }
  }
}

enum SpineLayout {
  /// The line the list is read from: just under the sticky day header. A row whose bottom is above
  /// this is behind the header and is not what anybody is looking at.
  static let readingLine: CGFloat = SpineMetrics.dayHeaderHeight + 4
  static let coordinateSpace = "omi.spine"
  /// How tall the stream is allowed to get before it scrolls inside the panel. The panel is one of
  /// two objects on Home and must not grow until it swallows the gap under the query bar.
  static let maximumHeight: CGFloat = 470
  /// Below this the rail is dropped rather than squeezed: a rail narrower than its own hour labels
  /// is a column of stubs, and the spine is the part worth the width.
  static let railBreakpoint: CGFloat = 620
}

// MARK: - Stream

struct SpineStream: View {
  let request: QueryShellRequest
  @ObservedObject var appState: AppState
  @ObservedObject var memoriesViewModel: MemoriesViewModel

  /// Hands a conversation to the page that owns conversations.
  let onOpenConversation: (String) -> Void
  /// Hands the day's memories to the surface that owns the graph.
  let onOpenBrainMap: () -> Void
  /// Hands a frame to Rewind.
  let onOpenRewind: () -> Void

  @StateObject private var store = SpineStore()
  @State private var viewport = SpineViewport()
  /// Which days are folded shut. Lives with the view rather than with the store because it is a
  /// reading position, not data: it is worth exactly as long as this list is on screen.
  @State private var collapse = SpineDayCollapse()

  var body: some View {
    GeometryReader { proxy in
      HStack(spacing: 0) {
        if proxy.size.width >= SpineLayout.railBreakpoint {
          SpineRailColumn(store: store, viewport: viewport, collapse: collapse)
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
    .frame(height: SpineLayout.maximumHeight)
    .queryShellMatchCount(store.matchCount)
    .task {
      if appState.conversations.isEmpty { await appState.loadConversations() }
      await memoriesViewModel.loadMemoriesIfNeeded()
      ingest()
    }
    .onReceive(appState.$conversations) { _ in ingest() }
    .onReceive(memoriesViewModel.$streamMemories) { _ in ingest() }
    .onChange(of: request) { _, newValue in store.apply(request: newValue) }
  }

  private func ingest() {
    store.ingest(conversations: appState.conversations, memories: memoriesViewModel.streamMemories)
    store.apply(request: request)
  }

  // MARK: The list

  private var stream: some View {
    ScrollView {
      LazyVStack(alignment: .leading, spacing: 0, pinnedViews: [.sectionHeaders]) {
        ForEach(store.days) { day in
          Section {
            // Folding is presentation, never a filter: the rows are still composed, still counted by
            // `queryShellMatchCount`, and still in the same chronological place when they come back.
            if !collapse.contains(day.id) {
              ForEach(day.rows) { row in
                SpineRowView(
                  row: row,
                  showsIndent: store.kind == .everything,
                  onOpenConversation: { onOpenConversation($0.id) },
                  onToggleStar: toggleStar,
                  onOpenMoment: { _ in onOpenRewind() },
                  onOpenBrainMap: onOpenBrainMap
                )
                .background(anchor(for: row, in: day))
              }
            }
          } header: {
            SpineDayHeader(
              day: day,
              isCollapsed: collapse.contains(day.id),
              onToggle: { toggleCollapse(day) }
            )
          }
        }
        footer
      }
      .padding(.horizontal, OmiSpacing.sm)
      .padding(.bottom, OmiSpacing.md)
    }
    .coordinateSpace(name: SpineLayout.coordinateSpace)
    .onPreferenceChange(SpineTopRowKey.self) { anchor in
      guard let anchor else { return }
      Task { @MainActor in viewport.report(dayID: anchor.dayID, hour: anchor.hour) }
    }
    .glassScrollFade(top: 6, bottom: 18)
  }

  /// A layout-neutral reporter behind each row. A `GeometryReader` in a `background` never affects
  /// layout, and inside a `LazyVStack` only the rows that exist report — a dozen or so, not a
  /// thousand.
  private func anchor(for row: SpineRow, in day: SpineDay) -> some View {
    GeometryReader { proxy in
      Color.clear.preference(
        key: SpineTopRowKey.self,
        value: SpineRowAnchor(
          dayID: day.id,
          hour: Calendar.current.component(.hour, from: row.anchor),
          bottom: proxy.frame(in: .named(SpineLayout.coordinateSpace)).maxY
        )
      )
    }
  }

  /// The end of the loaded stream. Only offered when there is genuinely another page behind it and
  /// nothing is narrowing the view — paging deeper to satisfy a filter would fetch the account one
  /// page at a time to answer a question the server already answers.
  ///
  /// It also withdraws while every loaded day is folded shut. The footer loads a page the *moment it
  /// appears*, and a spine of nothing but headers puts it on screen immediately — which would page
  /// the account away behind a surface with nothing on it to have reached the end of.
  @ViewBuilder
  private var footer: some View {
    if appState.canLoadMoreConversations, !request.isFiltering,
      !collapse.containsEvery(store.days.map(\.id))
    {
      SpineLoadMoreFooter(isLoading: appState.isLoadingConversations) {
        await appState.loadMoreConversations()
      }
    }
  }

  /// Folds one day shut, or opens it again.
  ///
  /// Animated through the gate rather than with a raw `withAnimation`, so Reduce Motion gets the
  /// instant version instead of a list of hundreds of rows sliding away.
  private func toggleCollapse(_ day: SpineDay) {
    OmiMotion.withGated(.easeOut(duration: InkMotion.stepTransition)) { collapse.toggle(day.id) }
  }

  private func toggleStar(_ conversation: ServerConversation) {
    OmiUISound.play(.commit)
    Task {
      await appState.setConversationStarred(conversation.id, starred: !conversation.starred)
    }
  }

  // MARK: Empty

  /// Never an illustration and never a shrug — and it keeps the shell's other key in view, because
  /// "nothing matched" is exactly when asking is the better move.
  private var emptyState: some View {
    VStack(alignment: .leading, spacing: 6) {
      Text(store.isPreparing ? "Reading your day…" : emptyHeadline)
        .scaledFont(size: OmiType.body, weight: .medium)
        .foregroundStyle(Ink.primary)
      if !store.isPreparing {
        Text(emptyDetail)
          .scaledFont(size: OmiType.caption, weight: .regular)
          .foregroundStyle(Ink.secondary)
      }
    }
    .frame(maxWidth: .infinity, alignment: .leading)
    .padding(.vertical, OmiSpacing.lg)
    .padding(.horizontal, OmiSpacing.sm)
    .accessibilityIdentifier("query-shell-empty")
  }

  private var emptyHeadline: String {
    request.term.isEmpty
      ? "Nothing captured in this window yet." : "Nothing captured matches “\(request.text)”."
  }

  private var emptyDetail: String {
    guard request.term.isEmpty else { return "Press ⌘⏎ to ask Omi instead." }
    switch store.kind {
    case .everything: return "Conversations, memories and screen moments appear here as they happen."
    case .conversations: return "Conversations appear here once Omi has heard one."
    case .memories: return "Memories appear here as Omi learns things worth keeping."
    case .screen: return "Screen moments appear here while screen capture is on."
    }
  }
}

// MARK: - Rail column

/// The rail, in its own view so a scroll redraws twenty-four bars rather than the whole spine.
private struct SpineRailColumn: View {
  @ObservedObject var store: SpineStore
  @ObservedObject var viewport: SpineViewport
  let collapse: SpineDayCollapse

  /// The day the rail describes.
  ///
  /// Normally the one the list reported, which comes from the topmost visible *row*. **A folded day
  /// has no rows**, so it can never be reported again — but it can still be the last thing reported
  /// before it was folded, and a rail describing a day whose rows are all hidden is a rail pointing
  /// at nothing. So a reported day that has since folded is dropped in favour of the first day still
  /// open, and only when every day is folded does it fall back to the newest one.
  private var dayID: Date? {
    if let reported = viewport.dayID, !collapse.contains(reported) { return reported }
    return store.days.first { !collapse.contains($0.id) }?.id ?? store.days.first?.id
  }

  private var day: SpineDay? { store.days.first { $0.id == dayID } }

  /// The hour marker belongs to the day the list actually reported. Carrying it onto a day chosen by
  /// the fallback above would light up an hour on a rail for a day nobody is reading.
  private var currentHour: Int? {
    guard let dayID, dayID == viewport.dayID else { return nil }
    return viewport.hour
  }

  var body: some View {
    SpineHourRail(
      density: dayID.map(store.density(for:)) ?? Array(repeating: 0, count: 24),
      currentHour: currentHour,
      momentCount: dayID.map(store.momentCount(for:)) ?? 0,
      dayTitle: day?.title ?? "",
      conversationCount: day?.conversationCount ?? 0
    )
  }
}

// MARK: - Day header

/// The one place in this system where uppercase and positive tracking are justified: a header pinned
/// over moving content has to read as chrome rather than as the first line of the day.
///
/// It is also the day's **disclosure**. The whole band is the target rather than the chevron alone —
/// an 11 pt glyph is a small thing to hit repeatedly, and nothing in this header is selectable text,
/// so there is nothing for a click to be taking away. The chevron on the trailing edge is what says
/// the band is a control at all; the count beside the title is what makes a folded day still worth
/// having on screen.
struct SpineDayHeader: View {
  let day: SpineDay
  let isCollapsed: Bool
  let onToggle: () -> Void

  @State private var isHovering = false

  var body: some View {
    Button(action: onToggle) {
      HStack(spacing: 10) {
        HStack(alignment: .firstTextBaseline, spacing: 10) {
          Text(day.title.uppercased())
            .font(.system(size: 11, weight: .semibold))
            .tracking(1.0)
            .foregroundStyle(Ink.primary)
          Text(day.subtitle)
            .scaledFont(size: OmiType.caption, weight: .regular)
            .foregroundStyle(Ink.secondary)
            .lineLimit(1)
        }
        Spacer(minLength: OmiSpacing.sm)
        SpineDayDisclosure(isCollapsed: isCollapsed, isHighlighted: isHovering)
      }
      .padding(.horizontal, 12)
      .frame(height: SpineMetrics.dayHeaderHeight, alignment: .leading)
      .frame(maxWidth: .infinity, alignment: .leading)
      .contentShape(Rectangle())
    }
    .buttonStyle(.plain)
    .onHover { hovering in
      isHovering = hovering
      if hovering { NSCursor.pointingHand.push() } else { NSCursor.pop() }
    }
    .accessibilityElement(children: .combine)
    .accessibilityAddTraits(.isButton)
    .accessibilityLabel(Text(isCollapsed ? "Expand \(day.title)" : "Collapse \(day.title)"))
    .accessibilityValue(Text(day.subtitle))
    .help(isCollapsed ? "Show this day" : "Hide this day")
    // Pinned headers have rows sliding under them, so the header has to occlude — and **a wash
    // cannot occlude.** The first attempt painted `Ink.surface` at 0.9, which on the light-pinned
    // panel is a hard white slab running edge to edge: it read as paint laid over the glass rather
    // than as chrome belonging to it, which is the same class of bug as any literal that only looks
    // right against one ground.
    //
    // A material is the vocabulary for exactly this — it occludes by frosting what is behind it, so
    // the header stays made of the same glass the panel is. Bounded by a continuous corner and
    // `Ink.separator` rather than bled to the edges, so it reads as a band belonging to the lane
    // instead of a slab laid across it.
    .background(
      RoundedRectangle(cornerRadius: 10, style: .continuous).fill(.regularMaterial)
    )
    .overlay(
      RoundedRectangle(cornerRadius: 10, style: .continuous)
        .strokeBorder(Ink.separator, lineWidth: 1)
    )
    .padding(.bottom, 4)
  }
}

/// The chevron on the header's trailing edge: down for an open day, turned a quarter for a folded one.
///
/// It **turns** rather than swapping glyph, because the rotation is the thing that says the two states
/// are the same control. Weight rather than colour on hover, like everything else here — and the
/// rotation animates through the gate so Reduce Motion gets the state and not the spin.
private struct SpineDayDisclosure: View {
  let isCollapsed: Bool
  let isHighlighted: Bool

  var body: some View {
    Image(systemName: "chevron.down")
      .font(.system(size: 11, weight: .semibold))
      .foregroundStyle(isHighlighted ? Ink.primary : Ink.secondary)
      .rotationEffect(.degrees(isCollapsed ? -90 : 0))
      // Sized inside the header's own band, so a target big enough to hit without aiming never makes
      // the header taller than the scroll reader's `dayHeaderHeight` says it is.
      .frame(width: 24, height: 24)
      .animation(InkReduceMotion.animation(.easeOut(duration: InkMotion.stepTransition)), value: isCollapsed)
      .accessibilityHidden(true)
  }
}

// MARK: - Load more

/// Both a button and an automatic trigger: the button is what a keyboard reaches and what automation
/// presses, scrolling to the end is what a pointer does, and both call the one guarded loader — so a
/// page is never fetched twice.
struct SpineLoadMoreFooter: View {
  let isLoading: Bool
  let load: () async -> Void

  @State private var hasRequested = false

  var body: some View {
    Button {
      Task { await load() }
    } label: {
      HStack(spacing: 8) {
        if isLoading { ProgressView().controlSize(.small) }
        Text(isLoading ? "Loading earlier days…" : "Load earlier days")
          .scaledFont(size: OmiType.caption, weight: .regular)
          .foregroundStyle(Ink.secondary)
      }
      .frame(maxWidth: .infinity)
      .padding(.vertical, 14)
      .contentShape(Rectangle())
    }
    .buttonStyle(.plain)
    .disabled(isLoading)
    .accessibilityIdentifier("spine-load-more")
    .onAppear {
      guard !hasRequested else { return }
      hasRequested = true
      Task { await load() }
    }
    .onDisappear { hasRequested = false }
  }
}
