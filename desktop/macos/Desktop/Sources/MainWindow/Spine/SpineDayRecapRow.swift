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

/// Recap (or the generate affordance) drawn inside a day's `Section` content, before its rows,
/// so it folds and unfolds with the day.
struct SpineDayRecapRow: View {
  let content: SpineDayRecapContent
  let dateKey: String
  let now: Date
  let calendar: Calendar

  @State private var isWorking = false
  @State private var errorMessage: String?

  var body: some View {
    switch content {
    case .hidden:
      EmptyView()
    case .emptyGenerate:
      emptyState
    case .recap(let record):
      recapCard(record)
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

  private func recapCard(_ record: DailySummaryRecord) -> some View {
    VStack(alignment: .leading, spacing: OmiSpacing.sm) {
      Text(nonEmpty(record.headline) ?? "Your day in review")
        .inkStyle(.rowCopy, color: Ink.primary)
        .fixedSize(horizontal: false, vertical: true)
      if let overview = nonEmpty(record.overview) {
        Text(overview)
          .inkStyle(.statusLabel, color: Ink.secondary)
          .fixedSize(horizontal: false, vertical: true)
      }
      highlightChips(in: record)
      HStack(spacing: OmiSpacing.sm) {
        Button("Ask about this day") {
          let question = ChatDailySummaryPresentation.followUpQuestion(
            for: record.date, now: now, calendar: calendar)
          ChatDailySummaryCard.requestFollowUp(question)
        }
        .buttonStyle(OmiButtonStyle(.secondary, size: .compact))
        // A record the backend served without an `id` gets a synthesized `date:<day>` identity
        // (see `DailySummaryRecord.init(from:)`); posting that to `/{summary_id}/regenerate`
        // is a guaranteed 404, so the action is only offered for a real server id.
        if !record.id.hasPrefix("date:") {
          Button(isWorking ? "Regenerating…" : "Regenerate") {
            Task { await runRegenerate(record) }
          }
          .buttonStyle(OmiButtonStyle(.secondary, size: .compact))
          .disabled(isWorking)
        }
      }
      if let errorMessage {
        Text(errorMessage)
          .scaledFont(size: OmiType.micro, weight: .regular)
          .foregroundStyle(Ink.secondary)
      }
    }
    .padding(.horizontal, OmiSpacing.md)
    .padding(.vertical, OmiSpacing.sm)
    .frame(maxWidth: .infinity, alignment: .leading)
    .glassRow(.rest, cornerRadius: InkGlass.cornerRadius)
    .padding(.top, SpineMetrics.attachedGap)
    .accessibilityIdentifier("spine-day-recap")
  }

  @ViewBuilder
  private func highlightChips(in record: DailySummaryRecord) -> some View {
    let highlights = Array(ChatDailySummaryCard.highlights(in: record).prefix(3))
    if !highlights.isEmpty {
      HStack(spacing: OmiSpacing.xs) {
        ForEach(Array(highlights.enumerated()), id: \.offset) { _, highlight in
          HStack(spacing: OmiSpacing.xxs) {
            if let emoji = nonEmpty(highlight.emoji) {
              Text(emoji).scaledFont(size: OmiType.micro)
            }
            if let topic = nonEmpty(highlight.topic) {
              Text(topic)
                .scaledFont(size: OmiType.micro, weight: .medium)
                .foregroundStyle(Ink.primary)
                .lineLimit(1)
            }
          }
          .padding(.horizontal, OmiSpacing.sm)
          .padding(.vertical, OmiSpacing.xxs)
          .background(Capsule().fill(Ink.rowFill))
          .overlay(Capsule().stroke(Ink.separator, lineWidth: 1))
        }
      }
    }
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
    } catch APIError.httpError(statusCode: 409, detail: _) {
      // The scheduled run for this day is mid-flight. Saying "couldn't generate" would be a
      // false negative at the one moment the recap is actually on its way.
      errorMessage = "Already being generated — check back in a moment."
    } catch {
      errorMessage = "Couldn't generate this recap."
    }
  }

  private func runRegenerate(_ record: DailySummaryRecord) async {
    isWorking = true
    errorMessage = nil
    defer { isWorking = false }
    let store = ChatDailySummaryCoordinator.shared.store
    guard let isOwnerStillCurrent = store.captureOwnerFence() else { return }
    do {
      let updated = try await APIClient.shared.regenerateDailySummary(id: record.id)
      store.upsert(updated, isOwnerStillCurrent: isOwnerStillCurrent)
    } catch {
      errorMessage = "Couldn't regenerate this recap."
    }
  }

  private func nonEmpty(_ value: String?) -> String? {
    guard let value, !value.isEmpty else { return nil }
    return value
  }
}
