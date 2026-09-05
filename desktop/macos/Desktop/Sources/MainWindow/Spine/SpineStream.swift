//
//  SpineStream.swift — the results panel's body: one day, top to bottom.
//
//  This is what occupies `QueryResultsPanel`'s seam. It draws no chrome — no query field, no chips, no
//  frame, no count line — because the panel above owns all four. It reads one value down
//  (`QueryShellRequest`: the term, the type, the time window) and reports one number up
//  (`queryShellMatchCount`), which is the whole of its contract with the shell.
//
//  **What it owns is the reading order.** One merged reverse-chronological stream grouped by day, with
//  the conversation dominant and the memories and frames it produced attached beneath it — and an hour
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
  /// Below this the rail is dropped rather than squeezed: a rail narrower than its own hour labels
  /// is a column of stubs, and the spine is the part worth the width.
  static let railBreakpoint: CGFloat = 620
}

// MARK: - Stream

struct SpineStream: View {
  let request: QueryShellRequest
  @ObservedObject var appState: AppState
  @ObservedObject var memoriesViewModel: MemoriesViewModel
  @ObservedObject var tasksStore: TasksStore
  var searchSurface: SearchSurface

  /// Hands a conversation to the page that owns conversations. The whole record, not its id: the
  /// row already holds it, and handing over an id forced the receiver to look it back up against a
  /// list that may not have loaded yet.
  let onOpenConversation: (ServerConversation) -> Void
  /// Hands a memory to the page that owns memories.
  let onOpenMemory: (SpineMemory) -> Void
  /// Hands the day's memories to the surface that owns the graph.
  let onOpenBrainMap: () -> Void
  /// Hands a frame to Rewind.
  let onOpenRewind: () -> Void

  @StateObject private var store = SpineStore()
  /// Pages the rest of the account in behind the first paint. See `SpineHydration`.
  @StateObject private var hydrator = SpineHydrator()
  @ObservedObject private var dailySummaries = ChatDailySummaryCoordinator.shared.store
  @State private var viewport = SpineViewport()
  /// Which days are folded shut. Lives with the view rather than with the store because it is a
  /// reading position, not data: it is worth exactly as long as this list is on screen.
  @State private var collapse = SpineDayCollapse()

  var body: some View {
    GeometryReader { proxy in
      HStack(spacing: 0) {
        if proxy.size.width >= SpineLayout.railBreakpoint {
          SpineRailColumn(
            store: store, viewport: viewport, collapse: collapse, request: request)
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
    // **The panel says how tall this is.** A flat 470 here was taller than the page the panel had at
    // the shell's own default window size, so the list ran off the bottom edge and the last row was
    // cut through the middle of its text — outside the scroll view, so unreachable by scrolling.
    // `QueryShellLayout.panelBodyHeight` is the one place that number is decided now.
    .frame(maxWidth: .infinity, maxHeight: .infinity)
    .queryShellMatchCount(store.matchCount)
    // The corner's count is a fraction of the corpus, so it has to know whether the corpus is done
    // arriving. Same source as the foot of the spine, so the two can never disagree about it.
    .queryShellCorpusSettled(hydrator.state == .whole)
    // First paint is the first page of each store and nothing else. Only once that is composed and
    // on screen does hydration start walking the rest of the account in behind it.
    .task {
      if appState.conversations.isEmpty { await appState.loadConversations() }
      await memoriesViewModel.loadMemoriesIfNeeded()
      await tasksStore.loadTasksIfNeeded()
      ingest()
      hydrator.start(conversations: conversationPages, memories: memoryPages)
      await ChatDailySummaryCoordinator.shared.activate()
    }
    .onDisappear { hydrator.stop() }
    .onReceive(appState.$conversations) { _ in ingest() }
    .onReceive(memoriesViewModel.$streamMemories) { _ in ingest() }
    .onReceive(tasksStore.$incompleteTasks) { _ in ingest() }
    .onChange(of: request) { _, newValue in
      store.apply(request: newValue)
      commitSearchAnalytics(newValue)
    }
  }

  private func ingest() {
    store.ingest(
      conversations: appState.conversations,
      memories: memoriesViewModel.streamMemories,
      tasks: tasksStore.incompleteTasks
    )
    store.apply(request: request)
    commitSearchAnalytics(request)
    // A store that was hydrated and has since been truncated under us reopens its cursor; this is
    // where the spine notices and goes back for the rest.
    hydrator.resume()
  }

  private func commitSearchAnalytics(_ request: QueryShellRequest) {
    SearchAnalytics.scheduleQueryEntered(surface: searchSurface, query: request.text) {
      store.matchCount
    }
  }

  private var searchIsActive: Bool {
    DebouncedSearchCoordinator.isActive(request.text)
  }

  private func openConversationFromSearch(_ conversation: ServerConversation) {
    SearchAnalytics.resultOpened(surface: searchSurface, searchIsActive: searchIsActive)
    onOpenConversation(conversation)
  }

  private func openMemoryFromSearch(_ memory: SpineMemory) {
    SearchAnalytics.resultOpened(surface: searchSurface, searchIsActive: searchIsActive)
    onOpenMemory(memory)
  }

  private func openRewindFromSearch() {
    SearchAnalytics.resultOpened(surface: searchSurface, searchIsActive: searchIsActive)
    onOpenRewind()
  }

  /// The two paged stores, as the hydrator sees them. Neither is owned here — the spine reads the
  /// same `loadMore` a scroll would have called, so there is no second cursor and no second cache.
  private var conversationPages: SpinePageSource {
    SpinePageSource(
      hasMore: { appState.canLoadMoreConversations },
      loadedCount: { appState.conversations.count },
      total: { appState.totalConversationsCount },
      loadMore: { await appState.loadMoreConversations() }
    )
  }

  private var memoryPages: SpinePageSource {
    SpinePageSource(
      hasMore: { memoriesViewModel.hasMoreMemories },
      loadedCount: { memoriesViewModel.memories.count },
      loadMore: { await memoriesViewModel.loadMore() }
    )
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
              recapSlot(for: day)
              ForEach(day.rows) { row in
                SpineRowView(
                  row: row,
                  showsIndent: store.kind == .everything,
                  onOpenConversation: openConversationFromSearch,
                  onOpenMemory: openMemoryFromSearch,
                  onToggleTask: { task in Task { await tasksStore.toggleTask(task) } },
                  onToggleStar: toggleStar,
                  // Clicking a moment used to discard the moment and navigate to the Rewind
                  // page — the one thing the user did not ask for, since what they clicked was a
                  // specific frame they wanted to read. Quick Look shows that frame at full
                  // resolution, in place, and arrows along the rest of the strip.
                  onOpenMoment: { moment, strip in
                    ScreenFrameQuickLook.shared.present(
                      strip.map { QuickLookFrame(screenshot: $0.screenshot) },
                      startingAt: String(moment.id))
                  },
                  onShowAllMoments: openRewindFromSearch,
                  onOpenBrainMap: onOpenBrainMap
                )
                .background(anchor(for: row, in: day))
              }
            }
          } header: {
            SpineDayHeader(
              day: day,
              isCollapsed: collapse.contains(day.id),
              onToggle: { toggleCollapse(day) },
              recapEmoji: recap(for: day)?.dayEmoji,
              // The stored recap is the card's own body: when the day is open and
              // a recap is attached, the header is the card's top half, not a
              // second floating surface above it.
              attachesRecapBody:
                !collapse.contains(day.id) && recapContent(for: day).attachesToHeaderCard
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
    .glassScrollFade(bottom: 18)
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

  /// What the end of the loaded stream is allowed to say.
  ///
  /// **It says the same thing under a filter as without one, which is the whole change.** The
  /// footer used to withdraw entirely while anything was narrowing the view, on the reasoning that
  /// paging deeper to satisfy a filter fetches the account one page at a time to answer a question
  /// the server should answer. The reasoning was sound and the consequence was a lie: filtering to
  /// Memories showed whatever happened to be loaded, with nothing on screen admitting there was
  /// more. The account is now paged in whether or not a filter is on, so the honest report is the
  /// same either way — filling, partial, or nothing at all.
  @ViewBuilder
  private var footer: some View {
    switch foot {
    case .nothing:
      EmptyView()
    case .note(let text):
      SpineCorpusNote(text: text)
    case .loadMore:
      // Hydration is not running and pages remain: it was abandoned, or the surface has only just
      // opened. Either way the manual door has to be there — and unlike the old footer it does not
      // fetch itself the instant it appears, so a spine of nothing but folded headers cannot page
      // the account away behind a screen with nothing on it to have reached the end of.
      SpineLoadMoreFooter { hydrator.retry() }
    }
  }

  private var foot: SpineFoot {
    SpineFoot.resolve(
      corpus: hydrator.state,
      canLoadMore: appState.canLoadMoreConversations || memoriesViewModel.hasMoreMemories
    )
  }

  /// Recap chrome for the day: not a `SpineRow`, so counts and the collapsed subtitle stay honest.
  @ViewBuilder
  private func recapSlot(for day: SpineDay) -> some View {
    let dateKey = SpineDayDateKey.string(from: day.id, calendar: store.calendar) ?? ""
    let content = recapContent(for: day)
    if content != .hidden {
      SpineDayRecapRow(
        content: content,
        dateKey: dateKey,
        onOpenRecap: { record in
          ChatFirstShellNavigation.shared.openDailyRecap(
            DailyRecapRouteRef(recordID: record.id, date: record.date ?? ""))
        }
      )
    }
  }

  /// What the day's recap slot shows, resolved once so the header's attached-card
  /// shape and the slot's content can never disagree.
  private func recapContent(for day: SpineDay) -> SpineDayRecapContent {
    SpineDayRecapContent.resolve(
      recap: recap(for: day),
      conversationCount: day.conversationCount,
      isFiltering: request.isFiltering,
      dayID: day.id,
      now: Date(),
      calendar: store.calendar,
      summaryHour: dailySummaries.summaryHour
    )
  }

  private func recap(for day: SpineDay) -> DailySummaryRecord? {
    guard let key = SpineDayDateKey.string(from: day.id, calendar: store.calendar) else { return nil }
    return dailySummaries.byDate[key]
  }

  /// Folds one day shut, or opens it again.
  ///
  /// Animated through the gate rather than with a raw `withAnimation`, so Reduce Motion gets the
  /// instant version instead of a list of hundreds of rows sliding away.
  private func toggleCollapse(_ day: SpineDay) {
    OmiMotion.withGated(.easeOut(duration: InkMotion.stepTransition)) { collapse.toggle(day.id) }
  }

  private func toggleStar(_ conversation: ServerConversation) {
    Task {
      await appState.setConversationStarred(conversation.id, starred: !conversation.starred)
    }
  }

  // MARK: Empty

  /// Never an illustration and never a shrug — and it keeps the shell's other key in view, because
  /// "nothing matched" is exactly when asking is the better move.
  ///
  /// **It is also the second place a filter could lie, and the worse one.** A filter narrow enough
  /// to match nothing in the pages loaded so far empties the list entirely, which takes the footer
  /// off screen with it — so the surface answered "nothing matches" while pages that might match
  /// were still arriving. The copy is resolved from the same `SpineFoot` the footer is, and the foot
  /// is rendered here too, so the two can never disagree about whether the corpus is complete.
  private var emptyState: some View {
    VStack(alignment: .center, spacing: 6) {
      Text(copy.headline)
        .scaledFont(size: OmiType.body, weight: .medium)
        .foregroundStyle(Ink.primary)
        .multilineTextAlignment(.center)
      if let detail = copy.detail {
        Text(detail)
          .scaledFont(size: OmiType.caption, weight: .regular)
          .foregroundStyle(Ink.secondary)
          .multilineTextAlignment(.center)
      }
      footer
    }
    .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .center)
    .padding(.vertical, OmiSpacing.lg)
    .padding(.horizontal, OmiSpacing.sm)
    .accessibilityIdentifier("query-shell-empty")
  }

  private var copy: SpineEmptyCopy {
    SpineEmptyCopy.resolve(
      isPreparing: store.isPreparing, request: request, kind: store.kind, foot: foot)
  }
}

// MARK: - What an empty spine is allowed to say

/// The two lines an empty spine shows, resolved from state rather than assembled in a `body`.
///
/// The rule worth stating: **"nothing matched" is a claim about the corpus, and it may only be made
/// once the corpus is whole.** While pages are still arriving, an empty result is an unfinished
/// answer, and saying so is the difference between a search surface you can trust and one that
/// quietly under-reports the account.
struct SpineEmptyCopy: Equatable, Sendable {
  let headline: String
  /// `nil` while the first day is still being read — there is nothing useful to add to "reading".
  let detail: String?

  static func resolve(
    isPreparing: Bool, request: QueryShellRequest, kind: SpineKind, foot: SpineFoot
  ) -> SpineEmptyCopy {
    guard !isPreparing else {
      return SpineEmptyCopy(headline: "Reading your day…", detail: nil)
    }
    // Still filling: the list being empty says nothing about the account yet.
    if case .note(let progress) = foot {
      return SpineEmptyCopy(headline: "Nothing here yet — still loading.", detail: progress)
    }
    let headline =
      request.term.isEmpty
      ? "Nothing captured in this window yet." : "Nothing captured matches “\(request.text)”."
    // Pages remain and nothing is fetching them: an empty list is a partial answer, and the button
    // below is how it stops being one.
    if foot == .loadMore {
      return SpineEmptyCopy(
        headline: headline, detail: "Some of your history isn’t loaded yet.")
    }
    guard request.term.isEmpty else {
      return SpineEmptyCopy(headline: headline, detail: "Press ⌘⏎ to ask Omi instead.")
    }
    return SpineEmptyCopy(headline: headline, detail: emptyKindDetail(kind))
  }

  private static func emptyKindDetail(_ kind: SpineKind) -> String {
    switch kind {
    case .everything: return "Conversations, memories, tasks and screen moments appear here as they happen."
    case .conversations: return "Conversations appear here once Omi has heard one."
    case .memories: return "Memories appear here as Omi learns things worth keeping."
    case .tasks: return "Tasks you add or Omi extracts appear here."
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
  let request: QueryShellRequest

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

  /// The rail remains a timeline navigator while the list narrows. Its capture histogram and
  /// screen-moment total therefore describe the complete day, not just the matching rows. Say so in
  /// the scope line; otherwise a search for a memory can make "1,204 screen moments" look like a
  /// result count for the memory search.
  private var railDayTitle: String {
    guard request.isFiltering, let title = day?.title, !title.isEmpty else {
      return day?.title ?? ""
    }
    return "\(title) · full day"
  }

  var body: some View {
    SpineHourRail(
      density: dayID.map(store.density(for:)) ?? Array(repeating: 0, count: 24),
      currentHour: currentHour,
      momentCount: dayID.flatMap(store.momentCount(for:)),
      dayTitle: railDayTitle,
      // Filtered results no longer carry the complete day's conversation count. The footer is
      // supplementary context, so omit it rather than pairing a full-day rail with a filtered noun.
      conversationCount: request.isFiltering ? 0 : (day?.conversationCount ?? 0)
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
  var recapEmoji: String? = nil
  /// True when the open day's recap body renders directly beneath this header.
  /// The header is then the card's **top half**: rounded at the top, square at
  /// the bottom, no gap — one continuous card with its body, never two floating
  /// surfaces.
  var attachesRecapBody: Bool = false

  @State private var isHovering = false

  var body: some View {
    Button(action: onToggle) {
      HStack(spacing: 10) {
        HStack(alignment: .firstTextBaseline, spacing: 10) {
          if let recapEmoji, !recapEmoji.isEmpty {
            Text(recapEmoji)
              .font(.system(size: 11))
              .frame(height: 11, alignment: .center)
              .accessibilityHidden(true)
          }
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
    .accessibilityIdentifier("spine-day-header")
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
    // the header stays made of the same glass the panel is. The card silhouette follows the body:
    // with an attached recap the header is rounded at the top and square at the bottom, and the
    // hairline runs only around the outer edges that are actually outer — no line across the seam,
    // because the header and its body are one card.
    .background(
      cardShape.fill(.regularMaterial)
    )
    .overlay(cardEdges)
    .padding(.bottom, attachesRecapBody ? 0 : 4)
  }

  private var cardShape: some Shape {
    if attachesRecapBody {
      return AnyShape(
        UnevenRoundedRectangle(
          topLeadingRadius: 10, topTrailingRadius: 10, style: .continuous))
    }
    return AnyShape(RoundedRectangle(cornerRadius: 10, style: .continuous))
  }

  /// The card's outer hairline. Attached, the bottom edge is the body's — only
  /// the top and sides are this header's to draw.
  @ViewBuilder
  private var cardEdges: some View {
    if attachesRecapBody {
      ZStack(alignment: .top) {
        VStack {
          HStack {
            Rectangle().fill(Ink.separator).frame(width: 1)
            Spacer(minLength: 0)
            Rectangle().fill(Ink.separator).frame(width: 1)
          }
          Spacer(minLength: 0)
        }
        Rectangle().fill(Ink.separator).frame(height: 1)
      }
      .clipShape(
        UnevenRoundedRectangle(
          topLeadingRadius: 10, topTrailingRadius: 10, style: .continuous))
    } else {
      RoundedRectangle(cornerRadius: 10, style: .continuous)
        .strokeBorder(Ink.separator, lineWidth: 1)
    }
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

/// The manual door to the next page, for the case where the background fill is not running.
///
/// It no longer fetches itself the moment it appears. That trigger was how the spine paged at all,
/// and it made the footer's mere presence a side effect — a folded spine, or a short filtered one,
/// would put it on screen and page the account away behind a surface with nothing on it. Now that
/// hydration owns the paging, the footer is only ever a button, which is also the only shape a
/// keyboard and automation can reach reliably.
struct SpineLoadMoreFooter: View {
  let load: () -> Void

  var body: some View {
    Button(action: load) {
      HStack(spacing: 8) {
        Image(systemName: "clock.arrow.circlepath")
          .accessibilityHidden(true)
        Text("Load earlier days")
      }
    }
    .buttonStyle(OmiButtonStyle(.secondary, size: .compact))
    .frame(maxWidth: .infinity)
    .padding(.top, OmiSpacing.sm)
    .padding(.bottom, OmiSpacing.md)
    .help("Retry loading the rest of your history")
    .accessibilityIdentifier("spine-load-more")
  }
}

/// One quiet line at the foot of the spine saying how much of the account is in it.
///
/// Two rungs of type on glass, so this is `Ink.secondary` and never a third rung (INV-UI-1).
struct SpineCorpusNote: View {
  let text: String

  var body: some View {
    HStack(spacing: 8) {
      ProgressView().controlSize(.small)
      Text(text)
        .scaledFont(size: OmiType.caption, weight: .regular)
        .foregroundStyle(Ink.secondary)
    }
    .frame(maxWidth: .infinity)
    .padding(.vertical, 14)
    .accessibilityIdentifier("spine-corpus-note")
  }
}
