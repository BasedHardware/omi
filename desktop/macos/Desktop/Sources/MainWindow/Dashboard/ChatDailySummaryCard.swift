import OmiTheme
import SwiftUI

/// The daily summary, at the top of the Chat thread.
///
/// Mobile has rendered this for months; desktop shipped only the on/off setting, so the record the
/// backend generates every night had no reader here at all. It goes in Chat rather than on a page
/// of its own because Chat is the surface the app opens on, and the summary is a read the user
/// should meet without navigating to it.
///
/// **Chrome, not a message.** It is drawn above the transcript inside `ChatMessagesView`'s scroll
/// content: no turn is recorded, no synthetic row is appended, and the thread's one journal-owned
/// transcript is untouched (INV-CHAT-1). The follow-up chip prefills the composer through the
/// existing `MainChatNavigationRequestStore` seam and sends nothing — asking stays the user's move.
///
/// It shows only what the backend filled: no summary, no card; no highlights, no highlights
/// section. A quiet day, day 0, and a user who turned generation off all render nothing rather
/// than an empty frame. The generation toggle in Settings is about producing and delivering the
/// summary, not about hiding one that already exists.
struct ChatDailySummaryCard: View {
  private let coordinator: ChatDailySummaryCoordinator
  @ObservedObject private var store: HomeDailySummaryStore

  /// Injected so the label and the chip's wording are deterministic in tests.
  private let now: () -> Date

  @State private var isExpanded = false
  @State private var isHovering = false
  @State private var reportedSummaryID: String?

  init(coordinator: ChatDailySummaryCoordinator = .shared, now: @escaping () -> Date = Date.init) {
    self.coordinator = coordinator
    self._store = ObservedObject(wrappedValue: coordinator.store)
    self.now = now
  }

  var body: some View {
    Group {
      if let summary = store.latest {
        card(summary)
          .onAppear { reportShown(summary) }
          .onChange(of: summary.id) { _, _ in reportShown(summary) }
      }
    }
    .task { await coordinator.activate() }
    .omiAnimation(.easeOut(duration: 0.2), value: isExpanded)
  }

  // MARK: - Card

  private func card(_ summary: DailySummaryRecord) -> some View {
    VStack(alignment: .leading, spacing: OmiSpacing.md) {
      header(summary)

      if let stats = summary.stats {
        // The same row the Home hub uses, so the two surfaces cannot drift apart.
        HomeDailySummaryStatsRow(stats: stats)
      }

      if let overview = summary.overview, !overview.isEmpty {
        Text(overview)
          .scaledFont(size: OmiType.body)
          .foregroundStyle(HomePalette.secondary)
          .lineLimit(isExpanded ? nil : 2)
          .fixedSize(horizontal: false, vertical: true)
      }

      let learned = Self.memoriesLearned(in: summary)
      if !learned.isEmpty {
        // Keyed to the rows themselves, so tomorrow's card starts from tomorrow's memories rather
        // than inheriting a row model built for yesterday's.
        MemoryReviewSection(items: learned, source: .dailySummaryChat)
          .id(Self.reviewSectionIdentity(summaryID: summary.id, items: learned))
      }

      if isExpanded {
        expandedBody(summary)
      }

      followUpChip(summary)
    }
    .padding(.horizontal, OmiSpacing.lg)
    .padding(.vertical, OmiSpacing.md + 2)
    .frame(maxWidth: .infinity, alignment: .leading)
    .background(
      RoundedRectangle(cornerRadius: 13, style: .continuous)
        .fill(isHovering ? HomePalette.tileHover : Ink.rowFill)
    )
    .overlay(
      RoundedRectangle(cornerRadius: 13, style: .continuous)
        .stroke(isHovering ? Ink.hairline : Ink.separator, lineWidth: 1)
    )
    .contentShape(.rect(cornerRadius: 13))
    .onHover { isHovering = $0 }
    .accessibilityElement(children: .contain)
    .accessibilityIdentifier("chat-daily-summary")
  }

  private func header(_ summary: DailySummaryRecord) -> some View {
    HStack(alignment: .firstTextBaseline, spacing: OmiSpacing.sm) {
      Text(nonEmpty(summary.dayEmoji) ?? "📅")
        .scaledFont(size: OmiType.subheading)
      VStack(alignment: .leading, spacing: 2) {
        if let label = ChatDailySummaryPresentation.dateLabel(for: summary.date, now: now()) {
          Text(label)
            .scaledFont(size: OmiType.micro, weight: .semibold)
            .foregroundStyle(HomePalette.muted)
            .tracking(0.6)
            .accessibilityIdentifier("chat-daily-summary-date")
        }
        Text(nonEmpty(summary.headline) ?? "Your day in review")
          .scaledFont(size: OmiType.subheading, weight: .semibold)
          .foregroundStyle(HomePalette.ink)
          .lineLimit(isExpanded ? nil : 2)
          .fixedSize(horizontal: false, vertical: true)
      }
      Spacer(minLength: OmiSpacing.sm)
      if hasExpandableDetail(summary) {
        Button(isExpanded ? "Less" : "More") {
          isExpanded.toggle()
          if isExpanded { AnalyticsManager.shared.trackDailySummary(.expanded) }
        }
        .buttonStyle(.plain)
        .scaledFont(size: OmiType.caption, weight: .medium)
        .foregroundStyle(HomePalette.secondary)
        .accessibilityIdentifier("chat-daily-summary-toggle")
      }
    }
  }

  @ViewBuilder
  private func expandedBody(_ summary: DailySummaryRecord) -> some View {
    let highlights = Self.highlights(in: summary)
    if !highlights.isEmpty {
      section("Highlights") {
        ForEach(Array(highlights.prefix(3).enumerated()), id: \.offset) { _, highlight in
          HStack(alignment: .firstTextBaseline, spacing: OmiSpacing.sm) {
            Text(nonEmpty(highlight.emoji) ?? "•")
              .scaledFont(size: OmiType.caption)
            VStack(alignment: .leading, spacing: 1) {
              if let topic = highlight.topic, !topic.isEmpty {
                Text(topic)
                  .scaledFont(size: OmiType.body, weight: .medium)
                  .foregroundStyle(HomePalette.ink)
              }
              Text(highlight.summary ?? "")
                .scaledFont(size: OmiType.body)
                .foregroundStyle(HomePalette.secondary)
                .fixedSize(horizontal: false, vertical: true)
            }
          }
        }
      }
    }

    let items = Self.actionItems(in: summary)
    if !items.isEmpty {
      section("Action items") {
        ForEach(Array(items.prefix(5).enumerated()), id: \.offset) { _, item in
          HStack(alignment: .firstTextBaseline, spacing: OmiSpacing.sm) {
            Image(systemName: item.completed == true ? "checkmark.circle.fill" : "circle")
              .scaledFont(size: OmiType.caption, weight: .medium)
              .foregroundStyle(item.completed == true ? HomePalette.green : HomePalette.muted)
            Text(item.description ?? "")
              .scaledFont(size: OmiType.body)
              .foregroundStyle(HomePalette.ink)
              .strikethrough(item.completed == true, color: HomePalette.muted)
              .fixedSize(horizontal: false, vertical: true)
          }
        }
      }
    }
  }

  @ViewBuilder
  private func section<Content: View>(
    _ title: String, @ViewBuilder content: () -> Content
  ) -> some View {
    VStack(alignment: .leading, spacing: OmiSpacing.xs) {
      Text(title)
        .scaledFont(size: OmiType.micro, weight: .semibold)
        .foregroundStyle(HomePalette.muted)
        .tracking(0.6)
      content()
    }
  }

  private func followUpChip(_ summary: DailySummaryRecord) -> some View {
    let question = ChatDailySummaryPresentation.followUpQuestion(for: summary.date, now: now())
    return Button {
      Self.requestFollowUp(question)
    } label: {
      HStack(spacing: OmiSpacing.xxs) {
        Image(systemName: "text.bubble")
          .scaledFont(size: OmiType.micro, weight: .semibold)
        Text(question)
          .scaledFont(size: OmiType.caption, weight: .medium)
      }
      .foregroundStyle(HomePalette.secondary)
      .padding(.horizontal, OmiSpacing.sm + 1)
      .padding(.vertical, OmiSpacing.xxs + 1)
      .background(Capsule().fill(Ink.rowFill))
      .overlay(Capsule().stroke(Ink.separator, lineWidth: 1))
    }
    .buttonStyle(.plain)
    .accessibilityIdentifier("chat-daily-summary-follow-up")
  }

  // MARK: - Helpers

  /// What the chip does, separated from the chip so it is testable: place the question in the
  /// composer and stop. It never sends — the user reads the summary, then decides whether to ask.
  /// `MainChatNavigationRequestStore` is the one prefill seam both shells' composers consume; a
  /// second path would race the first for the draft.
  @MainActor
  static func requestFollowUp(_ question: String) {
    MainChatNavigationRequestStore.shared.request(draft: question)
    AnalyticsManager.shared.trackDailySummary(.followUpTapped)
  }

  private func reportShown(_ summary: DailySummaryRecord) {
    guard reportedSummaryID != summary.id else { return }
    reportedSummaryID = summary.id
    AnalyticsManager.shared.trackDailySummary(.shown)
  }

  private func nonEmpty(_ value: String?) -> String? {
    guard let value, !value.isEmpty else { return nil }
    return value
  }

  private func hasExpandableDetail(_ summary: DailySummaryRecord) -> Bool {
    !Self.highlights(in: summary).isEmpty || !Self.actionItems(in: summary).isEmpty
      || (summary.overview ?? "").count > 160
  }

  /// Pure so the "render only what is there" rule is testable without a view: an empty section is
  /// never drawn, and a record with nothing to expand never offers "More".
  nonisolated static func highlights(in summary: DailySummaryRecord) -> [DailySummaryRecord.Highlight] {
    (summary.highlights ?? []).filter { !($0.summary ?? "").isEmpty }
  }

  nonisolated static func actionItems(in summary: DailySummaryRecord) -> [DailySummaryRecord.ActionItem] {
    (summary.actionItems ?? []).filter { !($0.description ?? "").isEmpty }
  }

  /// The review rows, and only from `memories_learned`.
  ///
  /// Deliberately never falls back to `knowledge_nuggets`: a nugget is LLM prose with no memory
  /// behind it, so a ✓ on one would mutate nothing and a ✗ would teach extraction nothing. A day
  /// with no qualifying memory shows no section, which is the honest empty state.
  nonisolated static func memoriesLearned(in summary: DailySummaryRecord) -> [MemoryReviewItem] {
    summary.memoriesLearned
      .filter {
        // Trimmed, not merely non-empty: a blank-but-present id would render a row whose ✓ / ✗ /
        // Fix address no memory at all.
        !$0.memoryID.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
          && !$0.content.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
      }
      .prefix(MemoryReviewSection.maxRows)
      .map(MemoryReviewItem.init)
  }

  /// Identity for the review section.
  ///
  /// The section holds one `MemoryReviewCardStore`, and the store captures its rows at init. A
  /// summary regenerated for the same day keeps its id, so keying on the id alone kept the old
  /// store alive: new memories never appeared and corrected ones kept the text the record no
  /// longer contained. Folding the rows in rebuilds the section exactly when they change.
  nonisolated static func reviewSectionIdentity(
    summaryID: String, items: [MemoryReviewItem]
  ) -> String {
    let rows = items.map { "\($0.memoryID)\u{1F}\($0.content)" }.joined(separator: "\u{1E}")
    return "memory-review-\(summaryID)\u{1E}\(rows)"
  }
}
