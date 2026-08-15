import OmiTheme
import SwiftUI

struct ScoreWidget: View {
  let scoreResponse: ScoreResponse?

  private var weeklyScore: ScoreData {
    scoreResponse?.weekly ?? ScoreData(score: 0, completedTasks: 0, totalTasks: 0)
  }

  private var scoreColor: Color {
    if !weeklyScore.hasTasks {
      return Ink.secondary
    }
    let score = weeklyScore.score
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

  var body: some View {
    GeometryReader { geometry in
      let gaugeWidth = min(geometry.size.width * 0.55, 180)
      let gaugeHeight = gaugeWidth / 2
      let lineWidth = max(gaugeWidth * 0.085, 8)
      let fontSize = max(gaugeWidth * 0.2, 18)

      VStack(spacing: OmiSpacing.lg) {
        // Semicircle gauge
        ZStack {
          // Background arc
          SemicircleShape()
            .stroke(Ink.rowFillHover, style: StrokeStyle(lineWidth: lineWidth, lineCap: .round))
            .frame(width: gaugeWidth, height: gaugeHeight)

          // Progress arc
          SemicircleShape()
            .trim(from: 0, to: min(weeklyScore.score / 100, 1.0))
            .stroke(scoreColor, style: StrokeStyle(lineWidth: lineWidth, lineCap: .round))
            .frame(width: gaugeWidth, height: gaugeHeight)
            .omiAnimation(.easeInOut(duration: 0.3), value: weeklyScore.score)

          // Score text
          VStack(spacing: OmiSpacing.hairline) {
            Text("\(Int(weeklyScore.score))%")
              .scaledFont(size: fontSize, weight: .bold)
              .foregroundColor(Ink.primary)
              .contentTransition(.numericText())
          }
          .offset(y: gaugeHeight * 0.14)
        }

        // Task count and subtitle
        VStack(spacing: OmiSpacing.xxs) {
          if weeklyScore.hasTasks {
            HStack(spacing: OmiSpacing.xxs) {
              Image(systemName: "checkmark.circle.fill")
                .scaledFont(size: OmiType.caption)
                .foregroundColor(scoreColor)
              Text("\(weeklyScore.completedTasks) of \(weeklyScore.totalTasks) tasks completed")
                .scaledMonospacedDigitFont(size: 12)
                .foregroundColor(Ink.secondary)
                .contentTransition(.numericText())
            }
          } else {
            Text("No tasks this week")
              .scaledFont(size: OmiType.caption)
              .foregroundColor(Ink.secondary)
          }

          Text("Last 7 days")
            .scaledFont(size: OmiType.micro)
            .foregroundColor(Ink.secondary)
        }
      }
      .frame(maxWidth: .infinity, maxHeight: .infinity)
      .padding(OmiSpacing.xl)
    }
    .frame(minHeight: 200)
    .glassCard()
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
      return Ink.secondary
    }
    if score >= 80 {
      return .green
    } else if score >= 60 {
      return Color(red: 0.8, green: 0.8, blue: 0.0)  // Lime/Yellow
    } else if score >= 40 {
      return .orange
    } else {
      return .red
    }
  }

  var body: some View {
    VStack(spacing: OmiSpacing.lg) {
      // Header
      HStack {
        Text("Daily Score")
          .scaledFont(size: OmiType.subheading, weight: .semibold)
          .foregroundColor(Ink.primary)
        Spacer()
      }

      // Semicircle gauge
      ZStack {
        // Background arc
        SemicircleShape()
          .stroke(Ink.rowFillHover, style: StrokeStyle(lineWidth: 12, lineCap: .round))
          .frame(width: 140, height: 70)

        // Progress arc
        SemicircleShape()
          .trim(from: 0, to: min(score / 100, 1.0))
          .stroke(scoreColor, style: StrokeStyle(lineWidth: 12, lineCap: .round))
          .frame(width: 140, height: 70)

        // Score text
        VStack(spacing: OmiSpacing.hairline) {
          Text("\(Int(score))%")
            .scaledFont(size: OmiType.title, weight: .bold)
            .foregroundColor(Ink.primary)
        }
        .offset(y: 10)
      }

      // Task count
      if let ds = dailyScore, ds.totalTasks > 0 {
        HStack(spacing: OmiSpacing.xxs) {
          Image(systemName: "checkmark.circle.fill")
            .scaledFont(size: OmiType.caption)
            .foregroundColor(scoreColor)
          Text("\(ds.completedTasks) of \(ds.totalTasks) tasks completed")
            .scaledMonospacedDigitFont(size: 12)
            .foregroundColor(Ink.secondary)
        }
      } else {
        Text("No tasks due today")
          .scaledFont(size: OmiType.caption)
          .foregroundColor(Ink.secondary)
      }
    }
    .padding(OmiSpacing.xl)
    .glassCard()
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
