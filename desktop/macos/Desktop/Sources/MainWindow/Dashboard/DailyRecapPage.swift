import OmiTheme
import SwiftUI

/// The day's recap, whole: date and headline, the overview, the stats, and every section with its
/// conversation links and its actions.
///
/// This is the one surface where recap badges and buttons live. The Chat pill and the Activity day
/// are doorways — title and summary only, by design — and both present this page as a sheet. A
/// sheet rather than a `ChatFirstRoute`: route values persist across launches and are gated to
/// primary destinations, while a recap is a transient read over whichever surface produced it, not
/// a place the shell should restore into. Mobile's `daily_summary_detail_page.dart` is the
/// reference; macOS deliberately gets no recap *list* page.
struct DailyRecapPage: View {
  /// The record on screen. Regeneration replaces it in place; the shared store is updated first so
  /// the surface that opened this sheet re-renders from the same data.
  @State private var current: DailySummaryRecord
  /// Hands a validated conversation to the surface that opened the page. The Chat shell passes its
  /// typed deep link (`ChatFirstShellNavigation.open(conversation:)`); the Activity spine passes
  /// the same `onOpenConversation` its rows use, so a recap link can never open a second detail
  /// owner beside the hub's own.
  private let onOpenConversation: (ServerConversation) -> Void
  @Environment(\.dismiss) private var dismiss

  @State private var isRegenerating = false
  @State private var regenerateError: String?
  @State private var isOpeningLink = false
  @State private var failedLinkID: String?

  init(record: DailySummaryRecord, onOpenConversation: @escaping (ServerConversation) -> Void) {
    self._current = State(initialValue: record)
    self.onOpenConversation = onOpenConversation
  }

  var body: some View {
    VStack(spacing: 0) {
      headerBar
      Divider()
        .overlay(Ink.separator)
      ScrollView {
        VStack(alignment: .leading, spacing: OmiSpacing.lg) {
          overview
          if let stats = current.stats {
            HomeDailySummaryStatsRow(stats: stats)
          }
          highlightsSection
          tasksSection
          unresolvedQuestionsSection
          decisionsSection
          memoriesLearnedSection
          learningsSection
          if let failedLinkID {
            Text("Couldn't open that conversation.")
              .scaledFont(size: OmiType.caption)
              .foregroundStyle(Ink.errorRed)
              .accessibilityIdentifier("daily-recap-open-failed")
              // The id is only a change key; the message never shows it.
              .id(failedLinkID)
          }
        }
        .padding(OmiSpacing.lg)
        .frame(maxWidth: .infinity, alignment: .leading)
      }
    }
    .frame(minWidth: 480, idealWidth: 560, minHeight: 440, idealHeight: 600)
    .omiAnimation(.easeOut(duration: 0.2), value: current.id)
    .accessibilityIdentifier("daily-recap-page")
  }

  // MARK: - Header

  private var headerBar: some View {
    HStack(alignment: .top, spacing: OmiSpacing.md) {
      VStack(alignment: .leading, spacing: 2) {
        if let label = ChatDailySummaryPresentation.dateLabel(for: current.date, now: Date()) {
          Text(label)
            .scaledFont(size: OmiType.micro, weight: .semibold)
            .foregroundStyle(HomePalette.muted)
            .tracking(0.6)
        }
        HStack(alignment: .firstTextBaseline, spacing: OmiSpacing.sm) {
          Text(nonEmpty(current.dayEmoji) ?? "📅")
            .scaledFont(size: OmiType.title)
          Text(nonEmpty(current.headline) ?? "Your day in review")
            .scaledFont(size: OmiType.heading, weight: .semibold)
            .foregroundStyle(HomePalette.ink)
            .fixedSize(horizontal: false, vertical: true)
        }
      }
      Spacer(minLength: OmiSpacing.md)
      VStack(alignment: .trailing, spacing: OmiSpacing.xs) {
        Button("Done") { dismiss() }
          .buttonStyle(OmiButtonStyle(.secondary, size: .compact))
          .accessibilityIdentifier("daily-recap-done")
        HStack(spacing: OmiSpacing.xs) {
          Button {
            askAboutThisDay()
          } label: {
            Label("Ask about this day", systemImage: "text.bubble")
          }
          .buttonStyle(OmiButtonStyle(.secondary, size: .compact))
          .accessibilityIdentifier("daily-recap-ask")
          // A record the backend served without an id gets a synthesized `date:<day>` identity
          // (see `DailySummaryRecord.init(from:)`); posting that to `/{summary_id}/regenerate`
          // is a guaranteed 404, so the action is only offered for a real server id.
          if !current.id.hasPrefix("date:") {
            Button {
              Task { await regenerate() }
            } label: {
              Label(isRegenerating ? "Regenerating…" : "Regenerate", systemImage: "arrow.clockwise")
            }
            .buttonStyle(OmiButtonStyle(.secondary, size: .compact))
            .disabled(isRegenerating)
            .accessibilityIdentifier("daily-recap-regenerate")
          }
        }
        if let regenerateError {
          Text(regenerateError)
            .scaledFont(size: OmiType.micro)
            .foregroundStyle(Ink.errorRed)
        }
      }
    }
    .padding(.horizontal, OmiSpacing.lg)
    .padding(.vertical, OmiSpacing.md)
  }

  private var overview: some View {
    Text(nonEmpty(current.overview) ?? "")
      .scaledFont(size: OmiType.body)
      .foregroundStyle(HomePalette.secondary)
      .fixedSize(horizontal: false, vertical: true)
      .frame(maxWidth: .infinity, alignment: .leading)
  }

  // MARK: - Sections

  @ViewBuilder
  private var highlightsSection: some View {
    let highlights = ChatDailySummaryPresentation.highlights(in: current)
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
  private var tasksSection: some View {
    let items = ChatDailySummaryPresentation.actionItems(in: current)
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
  private var unresolvedQuestionsSection: some View {
    let questions = (current.unresolvedQuestions ?? []).filter { !($0.question ?? "").isEmpty }
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
  private var decisionsSection: some View {
    let decisions = (current.decisionsMade ?? []).filter { !($0.decision ?? "").isEmpty }
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

  /// The same review rows the Chat surface used to compose, keyed so a regeneration rebuilds the
  /// section's store instead of showing the replaced rows.
  @ViewBuilder
  private var memoriesLearnedSection: some View {
    let learned = ChatDailySummaryPresentation.memoriesLearned(in: current)
    if !learned.isEmpty {
      MemoryReviewSection(items: learned, source: .dailySummaryDetail)
        .id(ChatDailySummaryPresentation.reviewSectionIdentity(summaryID: current.id, items: learned))
    }
  }

  @ViewBuilder
  private var learningsSection: some View {
    let nuggets = (current.knowledgeNuggets ?? []).filter { !($0.insight ?? "").isEmpty }
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

  // MARK: - Actions

  private func askAboutThisDay() {
    let question = ChatDailySummaryPresentation.followUpQuestion(for: current.date, now: Date())
    ChatDailySummaryPresentation.requestFollowUp(question)
    // The question is in the composer behind this sheet; dismissing is what makes that visible.
    dismiss()
  }

  /// Re-runs generation server-side and replaces the record in place, through the same owner fence
  /// every other recap writer uses (INV-AUTH-1).
  private func regenerate() async {
    guard !isRegenerating else { return }
    isRegenerating = true
    regenerateError = nil
    defer { isRegenerating = false }
    let store = ChatDailySummaryCoordinator.shared.store
    guard let isOwnerStillCurrent = store.captureOwnerFence() else { return }
    do {
      let updated = try await APIClient.shared.regenerateDailySummary(id: current.id)
      store.upsert(updated, isOwnerStillCurrent: isOwnerStillCurrent)
      current = updated
    } catch {
      regenerateError = "Couldn't regenerate this recap."
    }
  }

  /// One fetch, one validation, then the surface's own opener. The sheet dismisses only on
  /// success, so a dead id leaves the recap on screen with the failure said in one line.
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
        dismiss()
        onOpenConversation(valid)
      } catch {
        failedLinkID = id
      }
    }
  }

  private func nonEmpty(_ value: String?) -> String? {
    guard let value, !value.isEmpty else { return nil }
    return value
  }
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
    let content = HStack(alignment: .firstTextBaseline, spacing: OmiSpacing.sm) {
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
    let content = HStack(alignment: .firstTextBaseline, spacing: OmiSpacing.sm) {
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
