import OmiTheme
import SwiftUI

/// The day's recap, whole: the headline, the overview, the stats, and every section with its
/// conversation links and its actions — a full-page destination, not a sheet and not a banner.
///
/// It is hosted by the Chat-first shell on the glass page lane like the other full pages, opened
/// from the two surfaces that show a recap (the Chat transcript's in-history row and the Activity
/// day). The route carries identity only (`DailyRecapRouteRef`), so this page re-reads the record:
/// shared store first, then the API by id. A relaunch onto the persisted route re-fetches, and a
/// record that has since disappeared degrades to an honest "gone" state instead of stale text.
struct DailyRecapPage: View {
  private let ref: DailyRecapRouteRef
  @ObservedObject private var navigation: ChatFirstShellNavigation

  @State private var current: DailySummaryRecord?
  @State private var isFetching = false
  @State private var failedToLoad = false
  @State private var isRegenerating = false
  @State private var regenerateError: String?
  @State private var isOpeningLink = false
  @State private var failedLinkID: String?

  init(ref: DailyRecapRouteRef, navigation: ChatFirstShellNavigation) {
    self.ref = ref
    self.navigation = navigation
  }

  var body: some View {
    VStack(spacing: 0) {
      topBar
      Divider()
        .overlay(Ink.separator)
      if let current {
        pageBody(current)
      } else if failedToLoad {
        unavailable
      } else {
        loading
      }
    }
    .accessibilityIdentifier("daily-recap-page")
    .task { await loadIfEmpty() }
  }

  // MARK: - Top bar

  private var topBar: some View {
    HStack(spacing: OmiSpacing.md) {
      Button {
        navigation.closeDailyRecap()
      } label: {
        Image(systemName: "chevron.left")
          .scaledFont(size: OmiType.body, weight: .semibold)
          .foregroundStyle(Ink.primary)
          .frame(width: 24, height: 24)
          .contentShape(Rectangle())
      }
      .buttonStyle(.plain)
      .accessibilityLabel(Text("Back"))
      .accessibilityIdentifier("daily-recap-back")
      .help("Back")

      Text("Daily recap")
        .scaledFont(size: OmiType.micro, weight: .semibold)
        .foregroundStyle(Ink.secondary)
        .tracking(0.6)
        .textCase(.uppercase)

      Spacer(minLength: OmiSpacing.md)

      // Single-line by construction: one line of text that never wraps. A wrapped
      // action pill reads as two controls.
      Button {
        askAboutThisDay()
      } label: {
        Label("Ask about this day", systemImage: "text.bubble")
          .lineLimit(1)
          .fixedSize(horizontal: true, vertical: false)
      }
      .buttonStyle(OmiButtonStyle(.primary, size: .compact))
      .accessibilityIdentifier("daily-recap-ask")

      if !isSynthesizedID {
        Button {
          Task { await regenerate() }
        } label: {
          Label(isRegenerating ? "Regenerating…" : "Regenerate", systemImage: "arrow.clockwise")
            .lineLimit(1)
            .fixedSize(horizontal: true, vertical: false)
        }
        .buttonStyle(OmiButtonStyle(.secondary, size: .compact))
        .disabled(isRegenerating)
        .accessibilityIdentifier("daily-recap-regenerate")
      }
    }
    .padding(.horizontal, OmiSpacing.lg)
    .padding(.vertical, OmiSpacing.sm + 2)
  }

  // MARK: - Body

  private func pageBody(_ record: DailySummaryRecord) -> some View {
    ScrollView {
      VStack(alignment: .leading, spacing: OmiSpacing.lg) {
        header(record)
        overview(record)
        if let stats = record.stats {
          statsRow(stats)
        }
        highlightsSection(record)
        tasksSection(record)
        unresolvedQuestionsSection(record)
        decisionsSection(record)
        memoriesLearnedSection(record)
        learningsSection(record)
        if let failedLinkID {
          Text("Couldn't open that conversation.")
            .scaledFont(size: OmiType.caption)
            .foregroundStyle(Ink.errorRed)
            .accessibilityIdentifier("daily-recap-open-failed")
            // The id is only a change key; the message never shows it.
            .id(failedLinkID)
        }
        if let regenerateError {
          Text(regenerateError)
            .scaledFont(size: OmiType.caption)
            .foregroundStyle(Ink.errorRed)
        }
      }
      .padding(.horizontal, OmiSpacing.xl)
      .padding(.vertical, OmiSpacing.lg)
      // Generous, readable column: the recap is prose with rows, not a dashboard.
      .frame(maxWidth: 720, alignment: .leading)
      .frame(maxWidth: .infinity, alignment: .top)
    }
    .omiAnimation(.easeOut(duration: 0.2), value: record.id)
  }

  private func header(_ record: DailySummaryRecord) -> some View {
    VStack(alignment: .leading, spacing: OmiSpacing.xs) {
      Text(ChatDailySummaryPresentation.pageDateLabel(for: record.date, now: Date()) ?? "")
        .scaledFont(size: OmiType.micro, weight: .semibold)
        .foregroundStyle(HomePalette.muted)
        .tracking(0.6)
      HStack(alignment: .firstTextBaseline, spacing: OmiSpacing.sm + 2) {
        Text(nonEmpty(record.dayEmoji) ?? "📅")
          .scaledFont(size: OmiType.title)
        Text(nonEmpty(record.headline) ?? "Your day in review")
          .scaledFont(size: OmiType.heading, weight: .semibold)
          .foregroundStyle(HomePalette.ink)
          .lineLimit(3)
          .fixedSize(horizontal: false, vertical: true)
      }
    }
  }

  private func overview(_ record: DailySummaryRecord) -> some View {
    Text(nonEmpty(record.overview) ?? "")
      .scaledFont(size: OmiType.body)
      .foregroundStyle(HomePalette.secondary)
      .fixedSize(horizontal: false, vertical: true)
      .frame(maxWidth: .infinity, alignment: .leading)
  }

  /// One row of chips, each hugging its content on a single line: icon, bold
  /// value, label ("4h 33m watching"). A fixed slot was tried and was the bug:
  /// short labels left dead space inside their capsule while the row's tail
  /// clipped past the column edge. Content-sized chips keep every label whole
  /// and the row scrolls only when the window is genuinely too narrow.
  private func statsRow(_ stats: DailySummaryRecord.Stats) -> some View {
    let chips = HomeDailySummaryStatsRow.chips(for: stats)
    return Group {
      if !chips.isEmpty {
        ScrollView(.horizontal, showsIndicators: false) {
          HStack(spacing: OmiSpacing.xs) {
            ForEach(chips) { chip in
              statChip(chip)
            }
          }
          .padding(.vertical, 1)
        }
        .accessibilityIdentifier("daily-recap-stats")
      }
    }
  }

  private func statChip(_ chip: HomeDailySummaryStatsRow.Chip) -> some View {
    HStack(spacing: OmiSpacing.xxs) {
      Image(systemName: chip.symbol)
        .scaledFont(size: OmiType.micro, weight: .semibold)
        .foregroundStyle(HomePalette.muted)
      Text(chip.value)
        .scaledFont(size: OmiType.caption, weight: .bold)
        .monospacedDigit()
        .foregroundStyle(HomePalette.ink)
      Text(chip.label)
        .scaledFont(size: OmiType.caption)
        .foregroundStyle(HomePalette.secondary)
    }
    .lineLimit(1)
    .fixedSize()
    .padding(.horizontal, OmiSpacing.xxs + 2)
    .padding(.vertical, OmiSpacing.xxs + 2)
    .background(Capsule().fill(Ink.rowFill))
    .accessibilityElement(children: .combine)
    .accessibilityLabel("\(chip.value) \(chip.label)")
  }

  @ViewBuilder
  private func highlightsSection(_ record: DailySummaryRecord) -> some View {
    let highlights = ChatDailySummaryPresentation.highlights(in: record)
    if !highlights.isEmpty {
      section("Highlights") {
        ForEach(Array(highlights.enumerated()), id: \.offset) { _, highlight in
          RecapRow(
            leading: nonEmpty(highlight.emoji) ?? "•",
            title: highlight.topic,
            detail: highlight.summary ?? "",
            conversationID: highlight.conversationIds?.first,
            onOpen: openConversation(_:))
        }
      }
    }
  }

  @ViewBuilder
  private func tasksSection(_ record: DailySummaryRecord) -> some View {
    let items = ChatDailySummaryPresentation.actionItems(in: record)
    if !items.isEmpty {
      let completed = items.filter { $0.completed == true }
      // Open work first, like mobile: what is still to do is the reason the reader looks.
      let ordered = completed.count < items.count ? items.filter { $0.completed != true } + completed : items
      section("Tasks", accessory: "\(completed.count)/\(items.count)") {
        ForEach(Array(ordered.enumerated()), id: \.offset) { _, item in
          RecapTaskRow(item: item, conversationID: item.sourceConversationId, onOpen: openConversation(_:))
        }
      }
    }
  }

  @ViewBuilder
  private func unresolvedQuestionsSection(_ record: DailySummaryRecord) -> some View {
    let questions = (record.unresolvedQuestions ?? []).filter { !($0.question ?? "").isEmpty }
    if !questions.isEmpty {
      section("Unresolved questions") {
        ForEach(Array(questions.enumerated()), id: \.offset) { _, question in
          RecapRow(
            detail: question.question ?? "",
            conversationID: question.conversationId,
            onOpen: openConversation(_:))
        }
      }
    }
  }

  @ViewBuilder
  private func decisionsSection(_ record: DailySummaryRecord) -> some View {
    let decisions = (record.decisionsMade ?? []).filter { !($0.decision ?? "").isEmpty }
    if !decisions.isEmpty {
      section("Decisions") {
        ForEach(Array(decisions.enumerated()), id: \.offset) { _, decision in
          RecapRow(
            detail: decision.decision ?? "",
            conversationID: decision.conversationId,
            onOpen: openConversation(_:))
        }
      }
    }
  }

  /// The same review rows the Activity day composes, keyed so a regeneration
  /// rebuilds the section's store instead of showing the replaced rows.
  @ViewBuilder
  private func memoriesLearnedSection(_ record: DailySummaryRecord) -> some View {
    let learned = ChatDailySummaryPresentation.memoriesLearned(in: record)
    if !learned.isEmpty {
      MemoryReviewSection(items: learned, source: .dailySummaryDetail)
        .id(ChatDailySummaryPresentation.reviewSectionIdentity(summaryID: record.id, items: learned))
    }
  }

  @ViewBuilder
  private func learningsSection(_ record: DailySummaryRecord) -> some View {
    let nuggets = (record.knowledgeNuggets ?? []).filter { !($0.insight ?? "").isEmpty }
    if !nuggets.isEmpty {
      section("Things I learned today") {
        ForEach(Array(nuggets.enumerated()), id: \.offset) { _, nugget in
          RecapRow(
            detail: nugget.insight ?? "",
            conversationID: nugget.conversationId,
            onOpen: openConversation(_:))
        }
      }
    }
  }

  @ViewBuilder
  private func section(
    _ title: String, accessory: String? = nil, @ViewBuilder content: () -> some View
  ) -> some View {
    VStack(alignment: .leading, spacing: OmiSpacing.xs) {
      HStack(spacing: OmiSpacing.sm) {
        Text(title)
          .scaledFont(size: OmiType.micro, weight: .semibold)
          .foregroundStyle(HomePalette.muted)
          .tracking(0.6)
        if let accessory {
          Text(accessory)
            .scaledFont(size: OmiType.micro, weight: .medium)
            .monospacedDigit()
            .foregroundStyle(HomePalette.muted)
        }
      }
      content()
    }
  }

  private var loading: some View {
    VStack(spacing: OmiSpacing.md) {
      ProgressView().controlSize(.small)
      Text("Opening the recap…")
        .scaledFont(size: OmiType.caption)
        .foregroundStyle(Ink.secondary)
    }
    .frame(maxWidth: .infinity, maxHeight: .infinity)
  }

  /// The route outlived its record — deleted, another account's, or an id the
  /// backend no longer knows. Says so instead of showing a stale or empty page.
  private var unavailable: some View {
    VStack(spacing: OmiSpacing.sm) {
      Text("This recap isn't available.")
        .scaledFont(size: OmiType.subheading, weight: .medium)
        .foregroundStyle(Ink.primary)
      Text("It may have been removed, or it belongs to a different account.")
        .scaledFont(size: OmiType.caption)
        .foregroundStyle(Ink.secondary)
    }
    .frame(maxWidth: .infinity, maxHeight: .infinity)
    .multilineTextAlignment(.center)
    .padding(OmiSpacing.lg)
    .accessibilityIdentifier("daily-recap-unavailable")
  }

  // MARK: - Data

  /// Store first (instant, no network), then the wire by id. Either may be
  /// stale on a relaunch; a miss on both is the unavailable state, never a
  /// blank page and never yesterday's text.
  private func loadIfEmpty() async {
    guard current == nil else { return }
    let store = ChatDailySummaryCoordinator.shared.store
    if let record = store.latest, record.id == ref.recordID {
      current = record
      return
    }
    if let dateKey = nonEmpty(ref.date), let record = store.byDate[dateKey], record.id == ref.recordID {
      current = record
      return
    }
    guard !isFetching else { return }
    isFetching = true
    defer { isFetching = false }
    do {
      current = try await APIClient.shared.getDailySummary(id: ref.recordID)
    } catch {
      failedToLoad = true
    }
  }

  // MARK: - Actions

  private func askAboutThisDay() {
    guard let record = current else { return }
    let question = ChatDailySummaryPresentation.followUpQuestion(for: record.date, now: Date())
    ChatDailySummaryPresentation.requestFollowUp(question)
    // The question is in the composer of the surface that opened the recap;
    // going back is what makes that visible.
    navigation.closeDailyRecap()
  }

  /// Re-runs generation server-side and replaces the record in place, through the same owner fence
  /// every other recap writer uses (INV-AUTH-1).
  private func regenerate() async {
    guard !isRegenerating, let record = current else { return }
    isRegenerating = true
    regenerateError = nil
    defer { isRegenerating = false }
    let store = ChatDailySummaryCoordinator.shared.store
    guard let isOwnerStillCurrent = store.captureOwnerFence() else { return }
    do {
      let updated = try await APIClient.shared.regenerateDailySummary(id: record.id)
      store.upsert(updated, isOwnerStillCurrent: isOwnerStillCurrent)
      current = updated
    } catch {
      log("DailyRecapPage: regenerate failed for \(record.id): \(error)")
      regenerateError = ChatDailySummaryPresentation.generationFailureMessage(
        for: error, fallback: "Couldn't regenerate this recap.")
    }
  }

  /// One fetch, one validation, then the shared navigation owner's typed
  /// conversation deep link. A dead id is said in one line, not a dead click.
  private func openConversation(_ id: String?) {
    guard let id, !id.isEmpty else { return }
    guard !isOpeningLink else { return }
    isOpeningLink = true
    failedLinkID = nil
    Task { @MainActor in
      defer { isOpeningLink = false }
      do {
        let conversation = try await APIClient.shared.getConversation(id: id)
        guard
          let valid = ChatFirstConversationLinkPolicy.validatedConversation(
            conversation, requestedID: id)
        else {
          throw URLError(.cannotParseResponse)
        }
        navigation.open(conversation: valid)
      } catch {
        failedLinkID = id
      }
    }
  }

  private var isSynthesizedID: Bool {
    ref.recordID.hasPrefix("date:")
  }

  private func nonEmpty(_ value: String?) -> String? {
    guard let value, !value.isEmpty else { return nil }
    return value
  }

  /// Six chips at a width that holds the longest label ("8h 5m listening",
  /// "13 conversations") on one line; the row scrolls in a narrower lane
  /// rather than folding a label mid-word.
}

// MARK: - Rows

/// One recap row: optional leading mark, optional title, one detail line, and a chevron only when
/// the row actually deep-links. The whole row is the target when it links, and nothing else —
/// rows that carry no conversation id are text, not dead buttons.
private struct RecapRow: View {
  var leading: String? = nil
  var title: String? = nil
  let detail: String
  let conversationID: String?
  let onOpen: (String?) -> Void

  var body: some View {
    row
  }

  @ViewBuilder
  private var row: some View {
    let content =
      HStack(alignment: .firstTextBaseline, spacing: OmiSpacing.sm) {
        if let leading {
          Text(leading)
            .scaledFont(size: OmiType.caption)
        }
        VStack(alignment: .leading, spacing: 1) {
          if let title, !title.isEmpty {
            Text(title)
              .scaledFont(size: OmiType.body, weight: .medium)
              .foregroundStyle(HomePalette.ink)
          }
          Text(detail)
            .scaledFont(size: OmiType.body)
            .foregroundStyle(HomePalette.secondary)
            .fixedSize(horizontal: false, vertical: true)
        }
        Spacer(minLength: OmiSpacing.sm)
        if conversationID != nil {
          Image(systemName: "chevron.right")
            .scaledFont(size: OmiType.micro, weight: .semibold)
            .foregroundStyle(HomePalette.muted)
        }
      }
      .padding(.horizontal, OmiSpacing.sm + 1)
      .padding(.vertical, OmiSpacing.xs)
      .frame(maxWidth: .infinity, alignment: .leading)
      .contentShape(Rectangle())

    if let conversationID {
      Button {
        onOpen(conversationID)
      } label: {
        content
      }
      .buttonStyle(.plain)
      .accessibilityIdentifier("daily-recap-conversation-link")
    } else {
      content
    }
  }
}

/// The task row: the completion circle is the point, and a completed task reads as done.
private struct RecapTaskRow: View {
  let item: DailySummaryRecord.ActionItem
  let conversationID: String?
  let onOpen: (String?) -> Void

  var body: some View {
    let content =
      HStack(alignment: .firstTextBaseline, spacing: OmiSpacing.sm) {
        Image(systemName: item.completed == true ? "checkmark.circle.fill" : "circle")
          .scaledFont(size: OmiType.caption, weight: .medium)
          .foregroundStyle(item.completed == true ? HomePalette.green : HomePalette.muted)
        Text(item.description ?? "")
          .scaledFont(size: OmiType.body)
          .foregroundStyle(item.completed == true ? HomePalette.muted : HomePalette.ink)
          .strikethrough(item.completed == true, color: HomePalette.muted)
          .fixedSize(horizontal: false, vertical: true)
        Spacer(minLength: OmiSpacing.sm)
        if conversationID != nil {
          Image(systemName: "chevron.right")
            .scaledFont(size: OmiType.micro, weight: .semibold)
            .foregroundStyle(HomePalette.muted)
        }
      }
      .padding(.horizontal, OmiSpacing.sm + 1)
      .padding(.vertical, OmiSpacing.xs)
      .frame(maxWidth: .infinity, alignment: .leading)
      .contentShape(Rectangle())

    if let conversationID {
      Button {
        onOpen(conversationID)
      } label: {
        content
      }
      .buttonStyle(.plain)
      .accessibilityIdentifier("daily-recap-conversation-link")
    } else {
      content
    }
  }
}
