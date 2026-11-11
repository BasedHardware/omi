import OmiTheme
import SwiftUI

/// What the day's recap slot shows. The recap is chrome for the day, not a `SpineRow`, so it
/// cannot inflate `memoryCount` / `matchCount` / `subtitle`.
enum SpineDayRecapContent: Equatable {
  case recap(DailySummaryRecord)
  case emptyGenerate
  case hidden

  /// A stored recap belongs to the day, not to the query, so it survives any filter. The
  /// *generate* affordance does not: `SpineDay.conversationCount` is recomputed from the
  /// filtered rows, so under a soloed kind or a typed query it reports the matches, not the
  /// day. Offering "Generate recap" off that number would claim a day was recorded-but-unsummarized
  /// on the strength of a count that cannot say so — the same reason `SpineHourRail` drops its
  /// conversation footer while filtering.
  static func resolve(
    recap: DailySummaryRecord?,
    conversationCount: Int,
    isFiltering: Bool,
    dayID: Date,
    now: Date,
    calendar: Calendar,
    summaryHour: Int
  ) -> SpineDayRecapContent {
    if let recap { return .recap(recap) }
    guard !isFiltering else { return .hidden }
    guard conversationCount > 0 else { return .hidden }
    if calendar.isDate(dayID, inSameDayAs: now) {
      let hour = calendar.component(.hour, from: now)
      if hour < summaryHour { return .hidden }
    }
    return .emptyGenerate
  }
}

extension SpineDayRecapContent {
  /// True for `.recap` — the only content that attaches to the header's card.
  /// The generate affordance stays its own small surface.
  var attachesToHeaderCard: Bool {
    if case .recap = self { return true }
    return false
  }
}

/// Recap chrome drawn inside a day's `Section` content, before its rows, so it folds and unfolds
/// with the day.
///
/// A stored recap renders as a **pill: title and summary, nothing else.** The stat chips, the
/// "Ask about this day" / "Regenerate" buttons, and the highlight chips are gone from the list on
/// purpose — the day header is the recap's toggle (thin when the day is folded, title + summary
/// when it is open), and the full experience with badges and actions is `DailyRecapPage`, which
/// clicking the pill opens as a sheet. The generate affordance for a day with *no* recap stays:
/// it is not recap chrome, it is the one way to make the recap exist.
struct SpineDayRecapRow: View {
  let content: SpineDayRecapContent
  let dateKey: String

  @State private var isWorking = false
  @State private var errorMessage: String?

  /// Opens the dedicated recap page for the day's record.
  var onOpenRecap: (DailySummaryRecord) -> Void = { _ in }

  var body: some View {
    switch content {
    case .hidden:
      EmptyView()
    case .emptyGenerate:
      emptyState
    case .recap(let record):
      recapPill(record)
    }
  }

  private var emptyState: some View {
    VStack(alignment: .leading, spacing: OmiSpacing.xs) {
      HStack(spacing: OmiSpacing.sm) {
        Text(isWorking ? "Generating recap…" : "No recap for this day")
          .scaledFont(size: OmiType.caption, weight: .regular)
          .foregroundStyle(Ink.secondary)
        Spacer(minLength: OmiSpacing.sm)
        if isWorking {
          ProgressView().controlSize(.small)
        } else {
          Button("Generate recap") { Task { await runGenerate() } }
            .buttonStyle(OmiButtonStyle(.secondary, size: .compact))
            .accessibilityIdentifier("spine-day-recap-generate")
        }
      }
      if let errorMessage {
        Text(errorMessage)
          .scaledFont(size: OmiType.micro, weight: .regular)
          .foregroundStyle(Ink.secondary)
      }
    }
    .padding(.top, SpineMetrics.attachedGap)
    .padding(.bottom, OmiSpacing.xs)
    .accessibilityIdentifier("spine-day-recap-empty")
  }

  private func recapPill(_ record: DailySummaryRecord) -> some View {
    Button {
      onOpenRecap(record)
    } label: {
      VStack(alignment: .leading, spacing: OmiSpacing.xxs) {
        // The day header directly above already shows the recap's emoji and is
        // the fold control: no second emoji, no second arrow. The body's whole
        // surface opens the page (pointer + tooltip say so).
        Text(nonEmpty(record.headline) ?? "Your day in review")
          .scaledFont(size: OmiType.caption, weight: .semibold)
          .foregroundStyle(Ink.primary)
          .lineLimit(1)
          .truncationMode(.tail)
        if let overview = nonEmpty(record.overview) {
          Text(overview)
            .scaledFont(size: OmiType.caption, weight: .regular)
            .foregroundStyle(Ink.secondary)
            .lineLimit(2)
            .fixedSize(horizontal: false, vertical: true)
        }
      }
      .padding(.horizontal, 12)
      .padding(.top, OmiSpacing.xxs)
      .padding(.bottom, OmiSpacing.sm)
      .frame(maxWidth: .infinity, alignment: .leading)
      .contentShape(Rectangle())
    }
    .buttonStyle(.plain)
    // **The day card's body, not a second surface.** Same material as the
    // header above, square where they meet, rounded where the card ends, and
    // the hairline only on the edges that are actually outer — so header and
    // recap read as one continuous card.
    .background(
      UnevenRoundedRectangle(
        bottomLeadingRadius: 10, bottomTrailingRadius: 10, style: .continuous
      )
      .fill(.regularMaterial)
    )
    .overlay(
      ZStack(alignment: .bottom) {
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
          bottomLeadingRadius: 10, bottomTrailingRadius: 10, style: .continuous))
    )
    .accessibilityIdentifier("spine-day-recap")
    .accessibilityLabel(Text("Open the daily recap"))
    .help("Open the full recap for this day")
  }

  private func runGenerate() async {
    isWorking = true
    errorMessage = nil
    defer { isWorking = false }
    let store = ChatDailySummaryCoordinator.shared.store
    // INV-AUTH-1: capture the fence before the request, not after — the answer belongs to the
    // owner who asked for it.
    guard let isOwnerStillCurrent = store.captureOwnerFence() else { return }
    do {
      let record = try await APIClient.shared.createDailySummary(date: dateKey)
      store.upsert(record, isOwnerStillCurrent: isOwnerStillCurrent)
    } catch {
      // The transport logs only the request line, so without this the local log cannot tell a
      // server decline from a dead network — which is exactly the question a "couldn't
      // generate" report raises.
      log("SpineDayRecapRow: generate failed for \(dateKey): \(error)")
      errorMessage = ChatDailySummaryPresentation.generationFailureMessage(
        for: error, fallback: "Couldn't generate this recap.")
    }
  }

  private func nonEmpty(_ value: String?) -> String? {
    guard let value, !value.isEmpty else { return nil }
    return value
  }
}
