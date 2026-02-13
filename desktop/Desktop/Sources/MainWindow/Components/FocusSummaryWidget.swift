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
        VStack(alignment: .leading, spacing: 12) {
            // Header with tabs
            HStack {
                Text("Focus")
                    .font(.system(size: 16, weight: .semibold))
                    .foregroundColor(OmiColors.textPrimary)

                Spacer()

                // Tab picker
                HStack(spacing: 0) {
                    ForEach(FocusTab.allCases, id: \.self) { tab in
                        Button(action: {
                            withAnimation(.easeInOut(duration: 0.15)) {
                                selectedTab = tab
                            }
                        }) {
                            Text(tab.rawValue)
                                .font(.system(size: 11, weight: selectedTab == tab ? .semibold : .regular))
                                .foregroundColor(selectedTab == tab ? OmiColors.textPrimary : OmiColors.textTertiary)
                                .padding(.horizontal, 10)
                                .padding(.vertical, 4)
                                .background(
                                    RoundedRectangle(cornerRadius: 6)
                                        .fill(selectedTab == tab ? OmiColors.backgroundQuaternary.opacity(0.6) : Color.clear)
                                )
                        }
                        .buttonStyle(.plain)
                    }
                }
                .padding(2)
                .background(
                    RoundedRectangle(cornerRadius: 8)
                        .fill(OmiColors.backgroundTertiary.opacity(0.5))
                )
            }

            // Stats row - all in one line
            HStack(spacing: 10) {
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
        .padding(20)
        .frame(maxHeight: .infinity, alignment: .topLeading)
        .background(
            RoundedRectangle(cornerRadius: 16)
                .fill(OmiColors.backgroundTertiary.opacity(0.5))
                .overlay(
                    RoundedRectangle(cornerRadius: 16)
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
        VStack(alignment: .center, spacing: 4) {
            HStack(alignment: .center, spacing: 4) {
                Image(systemName: icon)
                    .font(.system(size: 12))
                    .foregroundColor(OmiColors.textSecondary)

                HStack(alignment: .lastTextBaseline, spacing: 1) {
                    Text(value)
                        .font(.system(size: 18, weight: .bold))
                        .foregroundColor(OmiColors.textPrimary)

                    if !unit.isEmpty {
                        Text(unit)
                            .font(.system(size: 10))
                            .foregroundColor(OmiColors.textTertiary)
                    }
                }
            }
            .lineLimit(1)
            .minimumScaleFactor(0.5)

            Text(title)
                .font(.system(size: 10))
                .foregroundColor(OmiColors.textTertiary)
        }
        .frame(maxWidth: .infinity)
        .padding(.vertical, 10)
        .padding(.horizontal, 8)
        .background(
            RoundedRectangle(cornerRadius: 10)
                .fill(OmiColors.backgroundTertiary.opacity(0.6))
        )
    }
}

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
