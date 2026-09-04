import OmiTheme
import SwiftUI

/// The daily recap, as Chat shows it: a thin clickable bar pinned above the transcript.
///
/// The pill is a doorway, not the experience. It carries the day emoji, the headline, and at most
/// two lines of overview — no stat chips, no buttons, no review rows, no Hide/More — because the
/// full record, its badges, and its actions live on `DailyRecapPage`, which clicking opens. The
/// previous in-place card expanded over the thread, which both occluded the newest messages and
/// made the transcript's top inset chase a height that only ever grew.
///
/// **Chrome, not a message.** It stays pinned to the top of the messages viewport as an overlay,
/// not a transcript row: no turn is recorded, no synthetic row is appended, and the thread's one
/// journal-owned transcript is untouched (INV-CHAT-1). Admission above the thread remains
/// `ChatMessagesView`'s decision (INV-CHAT-2) — this view only renders what it is told is
/// admitted, and only from the one shared daily-summary store.
struct ChatDailyRecapPill: View {
  private let coordinator: ChatDailySummaryCoordinator
  @ObservedObject private var store: HomeDailySummaryStore

  /// Injected so the staleness label is deterministic in tests.
  private let now: () -> Date

  @State private var presentedRecord: DailySummaryRecord?
  @State private var reportedSummaryID: String?

  init(
    coordinator: ChatDailySummaryCoordinator = .shared,
    now: @escaping () -> Date = Date.init
  ) {
    self.coordinator = coordinator
    self._store = ObservedObject(wrappedValue: coordinator.store)
    self.now = now
  }

  var body: some View {
    Group {
      if let summary = store.latest {
        pill(summary)
          .onAppear { reportShown(summary) }
          .onChange(of: summary.id) { _, _ in reportShown(summary) }
      }
    }
    .task { await coordinator.activate() }
  }

  private func pill(_ summary: DailySummaryRecord) -> some View {
    let stale = ChatDailySummaryPresentation.isStale(summary.date, now: now())
    let headline = nonEmpty(summary.headline) ?? "Your day in review"
    // Stale still shows the headline; the age rides in front of it so the bar never becomes a
    // warning that hides which day it is about.
    let line =
      stale
      ? "\(ChatDailySummaryPresentation.staleLabel(for: summary.date, now: now())) · \(headline)"
      : headline
    return Button {
      presentedRecord = summary
      AnalyticsManager.shared.trackDailySummary(.expanded)
    } label: {
      VStack(alignment: .leading, spacing: OmiSpacing.xxs) {
        HStack(spacing: OmiSpacing.sm) {
          Text(nonEmpty(summary.dayEmoji) ?? "📅")
            .scaledFont(size: OmiType.caption)
          Text(line)
            .scaledFont(size: OmiType.caption, weight: .medium)
            .foregroundStyle(stale ? HomePalette.muted : HomePalette.ink)
            .lineLimit(1)
            .truncationMode(.tail)
          Spacer(minLength: OmiSpacing.sm)
          Image(systemName: "chevron.right")
            .scaledFont(size: OmiType.micro, weight: .semibold)
            .foregroundStyle(HomePalette.muted)
        }
        if let overview = nonEmpty(summary.overview) {
          // Bounded here on purpose: the pill may cost the thread at most two lines, whatever the
          // backend wrote. The whole record is one click away.
          Text(overview)
            .scaledFont(size: OmiType.caption)
            .foregroundStyle(HomePalette.secondary)
            .lineLimit(2)
            .fixedSize(horizontal: false, vertical: true)
            .multilineTextAlignment(.leading)
        }
      }
      .padding(.horizontal, OmiSpacing.md)
      .padding(.vertical, OmiSpacing.xs + 1)
      .frame(maxWidth: .infinity, alignment: .leading)
      .background(.regularMaterial, in: RoundedRectangle(cornerRadius: 10, style: .continuous))
      .overlay(
        RoundedRectangle(cornerRadius: 10, style: .continuous)
          .stroke(Ink.separator, lineWidth: 1)
      )
      .contentShape(.rect(cornerRadius: 10))
    }
    .buttonStyle(.plain)
    .accessibilityIdentifier("chat-daily-recap-pill")
    .accessibilityLabel(Text("Open the daily recap"))
    .sheet(item: $presentedRecord) { record in
      DailyRecapPage(
        record: record,
        onOpenConversation: {
          ChatFirstShellNavigation.shared.open(conversation: $0)
        })
    }
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
}
