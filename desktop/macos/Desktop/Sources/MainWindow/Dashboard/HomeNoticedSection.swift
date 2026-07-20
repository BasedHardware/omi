import OmiTheme
import SwiftUI

/// "What Omi noticed" — the hero of the redesigned Home hub.
///
/// Merges the two proactive-intelligence streams into one quiet feed:
/// canonical What-Matters-Now recommendations (task intelligence, with its
/// feedback contract intact) and today's local proactive insights — the
/// advice stream that previously only surfaced as floating-bar notifications
/// (99.4% dismissed there; the content earns its keep on Home instead).
///
/// Rows are ambient: icon + text + caption, actions appear on hover. No
/// bordered card container — borders and strong color stay reserved for
/// real errors per the design language.
struct HomeNoticedSection: View {
  @ObservedObject var intelligenceStore: DashboardIntelligenceStore
  @ObservedObject var todayStore: HomeTodayStore
  let onOpenRecommendation: (DashboardRecommendation) async -> Bool
  let onOpenInsights: () -> Void

  private static let maxRows = 5

  private var visibleInsights: [HomeTodayStore.InsightItem] {
    let remaining = Self.maxRows - intelligenceStore.recommendations.count
    guard remaining > 0 else { return [] }
    return Array(todayStore.content.insights.prefix(remaining))
  }

  private var isEmpty: Bool {
    intelligenceStore.recommendations.isEmpty && todayStore.content.insights.isEmpty
  }

  var body: some View {
    if !isEmpty {
      VStack(alignment: .leading, spacing: OmiSpacing.xs) {
        Text("What Omi noticed")
          .scaledFont(size: OmiType.micro, weight: .semibold)
          .kerning(1.1)
          .textCase(.uppercase)
          .foregroundStyle(HomeStagePalette.muted)
          .padding(.bottom, OmiSpacing.xxs)

        ForEach(intelligenceStore.recommendations) { recommendation in
          HomeNoticedRecommendationRow(
            recommendation: recommendation,
            onOpen: {
              if await onOpenRecommendation(recommendation) {
                await intelligenceStore.recordPrimaryAction(recommendation)
              }
            },
            onLater: { await intelligenceStore.later(recommendation) },
            onDismiss: { reason in await intelligenceStore.dismiss(recommendation, reason: reason) }
          )
        }

        ForEach(visibleInsights) { insight in
          HomeNoticedInsightRow(
            insight: insight,
            onOpen: onOpenInsights,
            onDismiss: { await todayStore.dismissInsight(insight) }
          )
        }
      }
      .accessibilityIdentifier("what-matters-now")
    }
  }
}

// MARK: - Rows

private struct HomeNoticedRecommendationRow: View {
  let recommendation: DashboardRecommendation
  let onOpen: () async -> Void
  let onLater: () async -> Void
  let onDismiss: (OmiAPI.TaskIntelligenceFeedbackReason?) async -> Void

  @State private var isHovering = false

  var body: some View {
    HomeNoticedRowChrome(
      isHovering: $isHovering,
      onTap: { Task { await onOpen() } },
      icon: {
        Image(systemName: "sparkle")
          .scaledFont(size: OmiType.caption, weight: .semibold)
          .foregroundStyle(HomeStagePalette.secondary)
          .frame(width: 18)
      },
      content: {
        VStack(alignment: .leading, spacing: 2) {
          Text(recommendation.headline)
            .scaledFont(size: OmiType.body, weight: .medium)
            .foregroundStyle(HomeStagePalette.ink)
            .lineLimit(2)
          Text(captionText)
            .scaledFont(size: OmiType.micro, weight: .medium)
            .foregroundStyle(HomeStagePalette.muted)
            .lineLimit(1)
        }
      },
      actions: {
        Button(recommendation.recommendedAction) { Task { await onOpen() } }
          .buttonStyle(.borderedProminent)
          .tint(HomeStagePalette.ink)
          .foregroundColor(.black)
          .controlSize(.small)
          .lineLimit(1)
          .accessibilityIdentifier("wmn-primary-\(recommendation.interventionID)")

        Menu {
          Button("Later") { Task { await onLater() } }
          Menu("Dismiss") {
            Button("Already handled") { Task { await onDismiss(.already_handled) } }
            Button("Not mine") { Task { await onDismiss(.not_mine) } }
            Button("Not useful") { Task { await onDismiss(.not_useful) } }
            Button("No reason") { Task { await onDismiss(nil) } }
          }
        } label: {
          Image(systemName: "ellipsis")
            .scaledFont(size: OmiType.caption, weight: .semibold)
            .foregroundStyle(HomeStagePalette.secondary)
        }
        .menuStyle(.borderlessButton)
        .menuIndicator(.hidden)
        .frame(width: 26)
        .accessibilityIdentifier("wmn-dismiss-\(recommendation.interventionID)")
      }
    )
  }

  private var captionText: String {
    var parts: [String] = []
    if !recommendation.whyNow.isEmpty { parts.append(recommendation.whyNow) }
    if let context = recommendation.contextLabel, !context.isEmpty { parts.append(context) }
    return parts.joined(separator: " · ")
  }
}

private struct HomeNoticedInsightRow: View {
  let insight: HomeTodayStore.InsightItem
  let onOpen: () -> Void
  let onDismiss: () async -> Void

  @State private var isHovering = false

  var body: some View {
    HomeNoticedRowChrome(
      isHovering: $isHovering,
      onTap: onOpen,
      icon: {
        Image(systemName: "lightbulb")
          .scaledFont(size: OmiType.caption, weight: .semibold)
          .foregroundStyle(HomeStagePalette.secondary)
          .frame(width: 18)
      },
      content: {
        VStack(alignment: .leading, spacing: 2) {
          Text(insight.text)
            .scaledFont(size: OmiType.body, weight: .medium)
            .foregroundStyle(HomeStagePalette.ink)
            .lineLimit(2)
          Text("\(insight.sourceApp) · \(insight.createdAt.formatted(date: .omitted, time: .shortened))")
            .scaledFont(size: OmiType.micro, weight: .medium)
            .foregroundStyle(HomeStagePalette.muted)
            .lineLimit(1)
        }
      },
      actions: {
        Button {
          Task { await onDismiss() }
        } label: {
          Image(systemName: "xmark")
            .scaledFont(size: OmiType.micro, weight: .semibold)
            .foregroundStyle(HomeStagePalette.secondary)
        }
        .buttonStyle(.plain)
        .frame(width: 26)
        .help("Dismiss")
      }
    )
  }
}

/// Shared row chrome: full-width tap target, hover tint, actions revealed on
/// hover (reserved space so rows don't jump).
private struct HomeNoticedRowChrome<Icon: View, Content: View, Actions: View>: View {
  @Binding var isHovering: Bool
  let onTap: () -> Void
  @ViewBuilder let icon: () -> Icon
  @ViewBuilder let content: () -> Content
  @ViewBuilder let actions: () -> Actions

  var body: some View {
    HStack(alignment: .center, spacing: OmiSpacing.sm) {
      Button(action: onTap) {
        HStack(alignment: .firstTextBaseline, spacing: OmiSpacing.sm) {
          icon()
          content()
          Spacer(minLength: 0)
        }
        .contentShape(Rectangle())
      }
      .buttonStyle(.plain)

      HStack(spacing: OmiSpacing.xs) {
        actions()
      }
      .opacity(isHovering ? 1 : 0)
    }
    .padding(.horizontal, OmiSpacing.sm)
    .padding(.vertical, OmiSpacing.xs)
    .background(
      RoundedRectangle(cornerRadius: OmiChrome.smallControlRadius, style: .continuous)
        .fill(isHovering ? HomeStagePalette.tileHover.opacity(0.7) : Color.clear)
    )
    .onHover { isHovering = $0 }
  }
}
