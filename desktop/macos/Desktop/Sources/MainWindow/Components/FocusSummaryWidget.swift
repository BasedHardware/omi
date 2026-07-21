import OmiTheme
import SwiftUI

struct FocusSummaryWidget: View {
  let todayStats: FocusDayStats
  let totalStats: FocusDayStats

  @State private var selectedTab: FocusTab = .total

  enum FocusTab: String, CaseIterable {
    case today = "Today"
    case total = "Total"
  }

  private var stats: FocusDayStats {
    selectedTab == .today ? todayStats : totalStats
  }

  var body: some View {
    VStack(alignment: .leading, spacing: OmiSpacing.md) {
      // Header with tabs
      HStack {
        Text("Focus")
          .scaledFont(size: OmiType.subheading, weight: .semibold)
          .foregroundColor(OmiColors.textPrimary)

        Spacer()

        // Tab picker
        HStack(spacing: 0) {
          ForEach(FocusTab.allCases, id: \.self) { tab in
            Button(action: {
              OmiMotion.withGated(.easeInOut(duration: 0.15)) {
                selectedTab = tab
              }
            }) {
              Text(tab.rawValue)
                .scaledFont(size: OmiType.caption, weight: selectedTab == tab ? .semibold : .regular)
                .foregroundColor(selectedTab == tab ? OmiColors.textPrimary : OmiColors.textTertiary)
                .padding(.horizontal, OmiSpacing.sm)
                .padding(.vertical, OmiSpacing.xxs)
                .background(
                  RoundedRectangle(cornerRadius: OmiChrome.badgeRadius)
                    .fill(selectedTab == tab ? OmiColors.backgroundQuaternary.opacity(0.6) : Color.clear)
                )
            }
            .buttonStyle(.plain)
          }
        }
        .padding(OmiSpacing.hairline)
        .background(
          RoundedRectangle(cornerRadius: OmiChrome.elementRadius)
            .fill(OmiColors.backgroundTertiary.opacity(0.5))
        )
      }

      // Stats row - all in one line
      HStack(spacing: OmiSpacing.sm) {
        FocusStatCard(
          title: "Focus Time",
          value: "\(stats.focusedMinutes)",
          unit: "min",
          icon: "eye.fill",
          color: Color.green
        )

        FocusStatCard(
          title: "Distracted",
          value: "\(stats.distractedMinutes)",
          unit: "min",
          icon: "eye.slash.fill",
          color: Color.orange
        )

        FocusStatCard(
          title: "Focus Rate",
          value: String(format: "%.0f", stats.focusRate),
          unit: "%",
          icon: "chart.pie.fill",
          color: OmiColors.info
        )

        FocusStatCard(
          title: "Sessions",
          value: "\(stats.sessionCount)",
          unit: "",
          icon: "clock.fill",
          color: OmiColors.info
        )
      }
    }
    .padding(OmiSpacing.xl)
    .frame(maxHeight: .infinity, alignment: .topLeading)
    .background(
      RoundedRectangle(cornerRadius: OmiChrome.controlRadius)
        .fill(OmiColors.backgroundTertiary.opacity(0.5))
        .overlay(
          RoundedRectangle(cornerRadius: OmiChrome.controlRadius)
            .stroke(OmiColors.backgroundQuaternary.opacity(0.5), lineWidth: 1)
        )
    )
  }
}

// MARK: - Stat Card

struct FocusStatCard: View {
  let title: String
  let value: String
  let unit: String
  let icon: String
  let color: Color

  var body: some View {
    VStack(alignment: .center, spacing: OmiSpacing.xxs) {
      HStack(alignment: .center, spacing: OmiSpacing.xxs) {
        Image(systemName: icon)
          .scaledFont(size: OmiType.caption)
          .foregroundColor(OmiColors.textSecondary)

        HStack(alignment: .lastTextBaseline, spacing: OmiSpacing.hairline) {
          Text(value)
            .scaledFont(size: OmiType.heading, weight: .bold)
            .foregroundColor(OmiColors.textPrimary)

          if !unit.isEmpty {
            Text(unit)
              .scaledFont(size: OmiType.micro)
              .foregroundColor(OmiColors.textTertiary)
          }
        }
      }
      .lineLimit(1)
      .minimumScaleFactor(0.5)

      Text(title)
        .scaledFont(size: OmiType.micro)
        .foregroundColor(OmiColors.textTertiary)
    }
    .frame(maxWidth: .infinity)
    .padding(.vertical, OmiSpacing.sm)
    .padding(.horizontal, OmiSpacing.sm)
    .background(
      RoundedRectangle(cornerRadius: OmiChrome.smallControlRadius)
        .fill(OmiColors.backgroundTertiary.opacity(0.6))
    )
  }
}

#if canImport(PreviewsMacros)
  #Preview {
    FocusSummaryWidget(
      todayStats: FocusDayStats(
        date: Date(),
        focusedMinutes: 45,
        distractedMinutes: 15,
        sessionCount: 8,
        focusedCount: 6,
        distractedCount: 2,
        topDistractions: []
      ),
      totalStats: FocusDayStats(
        date: Date(),
        focusedMinutes: 320,
        distractedMinutes: 80,
        sessionCount: 52,
        focusedCount: 40,
        distractedCount: 12,
        topDistractions: []
      )
    )
    .padding()
    .background(OmiColors.backgroundPrimary)
  }
#endif
