import SwiftUI

enum ScoreTab: String, CaseIterable {
    case daily = "Daily"
    case weekly = "Weekly"
    case overall = "Overall"
}

struct ScoreWidget: View {
    let scoreResponse: ScoreResponse?
    @State private var selectedTab: ScoreTab = .overall

    init(scoreResponse: ScoreResponse?) {
        self.scoreResponse = scoreResponse
        // Set initial tab based on defaultTab from response
        if let response = scoreResponse {
            let initialTab: ScoreTab
            switch response.defaultTab {
            case "daily":
                initialTab = .daily
            case "weekly":
                initialTab = .weekly
            default:
                initialTab = .overall
            }
            _selectedTab = State(initialValue: initialTab)
        }
    }

    private var currentScore: ScoreData {
        guard let response = scoreResponse else {
            return ScoreData(score: 0, completedTasks: 0, totalTasks: 0)
        }
        switch selectedTab {
        case .daily:
            return response.daily
        case .weekly:
            return response.weekly
        case .overall:
            return response.overall
        }
    }

    private var scoreColor: Color {
        if !currentScore.hasTasks {
            return Color.gray
        }
        let score = currentScore.score
        if score >= 80 {
            return .green
        } else if score >= 60 {
            return Color(red: 0.8, green: 0.8, blue: 0.0)
        } else if score >= 40 {
            return .orange
        } else {
            return .red
        }
    }

    private var subtitleText: String {
        switch selectedTab {
        case .daily:
            return "Due today"
        case .weekly:
            return "Last 7 days"
        case .overall:
            return "All time"
        }
    }

    private var noTasksText: String {
        switch selectedTab {
        case .daily:
            return "No tasks due today"
        case .weekly:
            return "No tasks this week"
        case .overall:
            return "No tasks yet"
        }
    }

    var body: some View {
        HStack(spacing: 16) {
            // Tabs on the left sidebar
            VStack(spacing: 4) {
                ForEach(ScoreTab.allCases, id: \.self) { tab in
                    Button(action: {
                        withAnimation(.easeInOut(duration: 0.2)) {
                            selectedTab = tab
                        }
                    }) {
                        Text(tab.rawValue)
                            .font(.system(size: 12, weight: selectedTab == tab ? .semibold : .regular))
                            .foregroundColor(selectedTab == tab ? OmiColors.textPrimary : OmiColors.textTertiary)
                            .frame(maxWidth: .infinity, alignment: .leading)
                            .padding(.horizontal, 10)
                            .padding(.vertical, 6)
                            .background(
                                selectedTab == tab
                                    ? RoundedRectangle(cornerRadius: 6)
                                        .fill(OmiColors.backgroundQuaternary)
                                    : nil
                            )
                    }
                    .buttonStyle(.plain)
                }
                Spacer()
            }
            .frame(width: 72)

            // Gauge + info on the right
            VStack(spacing: 12) {
                // Semicircle gauge
                ZStack {
                    // Background arc
                    SemicircleShape()
                        .stroke(OmiColors.backgroundQuaternary, style: StrokeStyle(lineWidth: 12, lineCap: .round))
                        .frame(width: 140, height: 70)

                    // Progress arc
                    SemicircleShape()
                        .trim(from: 0, to: min(currentScore.score / 100, 1.0))
                        .stroke(scoreColor, style: StrokeStyle(lineWidth: 12, lineCap: .round))
                        .frame(width: 140, height: 70)
                        .animation(.easeInOut(duration: 0.3), value: currentScore.score)

                    // Score text
                    VStack(spacing: 2) {
                        Text("\(Int(currentScore.score))%")
                            .font(.system(size: 28, weight: .bold))
                            .foregroundColor(OmiColors.textPrimary)
                            .contentTransition(.numericText())
                    }
                    .offset(y: 10)
                }

                // Task count and subtitle
                VStack(spacing: 4) {
                    if currentScore.hasTasks {
                        HStack(spacing: 4) {
                            Image(systemName: "checkmark.circle.fill")
                                .font(.system(size: 12))
                                .foregroundColor(scoreColor)
                            Text("\(currentScore.completedTasks) of \(currentScore.totalTasks) tasks completed")
                                .font(.system(size: 12).monospacedDigit())
                                .foregroundColor(OmiColors.textTertiary)
                                .contentTransition(.numericText())
                        }
                    } else {
                        Text(noTasksText)
                            .font(.system(size: 12))
                            .foregroundColor(OmiColors.textTertiary)
                    }

                    Text(subtitleText)
                        .font(.system(size: 10))
                        .foregroundColor(OmiColors.textQuaternary)
                }
            }
        }
        .padding(20)
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .top)
        .background(
            RoundedRectangle(cornerRadius: 16)
                .fill(OmiColors.backgroundTertiary.opacity(0.5))
                .overlay(
                    RoundedRectangle(cornerRadius: 16)
                        .stroke(OmiColors.backgroundQuaternary.opacity(0.5), lineWidth: 1)
                )
        )
        .onChange(of: scoreResponse?.defaultTab) { oldValue, newValue in
            // Update tab when data first arrives (oldValue was nil)
            if let defaultTab = newValue, oldValue == nil {
                withAnimation(.easeInOut(duration: 0.2)) {
                    switch defaultTab {
                    case "daily": selectedTab = .daily
                    case "weekly": selectedTab = .weekly
                    default: selectedTab = .overall
                    }
                }
            }
        }
    }
}

// MARK: - Legacy Widget (for backwards compatibility)

struct DailyScoreWidget: View {
    let dailyScore: DailyScore?

    private var score: Double {
        dailyScore?.score ?? 0
    }

    private var hasTasksToday: Bool {
        (dailyScore?.totalTasks ?? 0) > 0
    }

    private var scoreColor: Color {
        // Grey when no tasks (like Flutter)
        if !hasTasksToday {
            return Color.gray
        }
        if score >= 80 {
            return .green
        } else if score >= 60 {
            return Color(red: 0.8, green: 0.8, blue: 0.0) // Lime/Yellow
        } else if score >= 40 {
            return .orange
        } else {
            return .red
        }
    }

    var body: some View {
        VStack(spacing: 16) {
            // Header
            HStack {
                Text("Daily Score")
                    .font(.system(size: 16, weight: .semibold))
                    .foregroundColor(OmiColors.textPrimary)
                Spacer()
            }

            // Semicircle gauge
            ZStack {
                // Background arc
                SemicircleShape()
                    .stroke(OmiColors.backgroundQuaternary, style: StrokeStyle(lineWidth: 12, lineCap: .round))
                    .frame(width: 140, height: 70)

                // Progress arc
                SemicircleShape()
                    .trim(from: 0, to: min(score / 100, 1.0))
                    .stroke(scoreColor, style: StrokeStyle(lineWidth: 12, lineCap: .round))
                    .frame(width: 140, height: 70)

                // Score text
                VStack(spacing: 2) {
                    Text("\(Int(score))%")
                        .font(.system(size: 28, weight: .bold))
                        .foregroundColor(OmiColors.textPrimary)
                }
                .offset(y: 10)
            }

            // Task count
            if let ds = dailyScore, ds.totalTasks > 0 {
                HStack(spacing: 4) {
                    Image(systemName: "checkmark.circle.fill")
                        .font(.system(size: 12))
                        .foregroundColor(scoreColor)
                    Text("\(ds.completedTasks) of \(ds.totalTasks) tasks completed")
                        .font(.system(size: 12).monospacedDigit())
                        .foregroundColor(OmiColors.textTertiary)
                }
            } else {
                Text("No tasks due today")
                    .font(.system(size: 12))
                    .foregroundColor(OmiColors.textTertiary)
            }
        }
        .padding(20)
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

// MARK: - Semicircle Shape

struct SemicircleShape: Shape {
    func path(in rect: CGRect) -> Path {
        var path = Path()
        let center = CGPoint(x: rect.midX, y: rect.maxY)
        let radius = min(rect.width, rect.height * 2) / 2

        path.addArc(
            center: center,
            radius: radius,
            startAngle: .degrees(180),
            endAngle: .degrees(0),
            clockwise: false
        )

        return path
    }
}
