import SwiftUI

/// The calm "how your focus went" page — mockup `focus.html`, light-wired.
/// Reads real focus stats/sessions from `FocusStorage.shared`.
struct RedesignFocusPage: View {
  @ObservedObject private var storage = FocusStorage.shared
  @Binding var selectedIndex: Int

  @State private var protecting = false

  // MARK: - Derived data

  private var stats: FocusDayStats { storage.todayStats }

  /// Today's focused sessions, newest first (the "protected" deep-work blocks).
  private var focusedSessions: [StoredFocusSession] {
    storage.todaySessions.filter { $0.status == .focused }
  }

  private var hasData: Bool { !storage.todaySessions.isEmpty }

  private var score: Int { Int(stats.focusRate.rounded()) }

  private var weekday: String {
    let f = DateFormatter()
    f.dateFormat = "EEEE"
    return f.string(from: Date())
  }

  private var headline: String {
    guard hasData else { return "Nothing tracked yet." }
    switch score {
    case 80...: return "Sharp focus."
    case 60..<80: return "Solid stretch."
    case 40..<60: return "Getting there."
    default: return "Scattered day."
    }
  }

  private var subline: String {
    guard hasData else {
      return "Once you get into your work, I'll show how your day went here."
    }
    if stats.focusedMinutes > 0 {
      return "You held \(stats.focusedMinutes) focused minute\(stats.focusedMinutes == 1 ? "" : "s") today. I kept your best hours clear."
    }
    return "A busy one. I'll keep guarding the hours where you do your best work."
  }

  // MARK: - Body

  var body: some View {
    ScrollView {
      VStack(alignment: .leading, spacing: 24) {
        Text("FOCUS · \(weekday)").inkEyebrow()
        scoreRow
        deepWorkCard
        tomorrowCard
      }
      .frame(maxWidth: 760, alignment: .leading)
      .frame(maxWidth: .infinity, alignment: .center)
      .padding(.horizontal, 48)
      .padding(.vertical, 44)
    }
    .frame(maxWidth: .infinity, maxHeight: .infinity)
    .background(Ink.canvas)
  }

  private var scoreRow: some View {
    HStack(alignment: .bottom, spacing: 24) {
      Text(hasData ? "\(score)" : "—")
        .font(InkFont.serif(72, .medium)).foregroundColor(Ink.ink).tracking(-1)
        .monospacedDigit()
      VStack(alignment: .leading, spacing: 6) {
        Text(headline).inkH3()
        Text(subline).inkSmall()
          .frame(maxWidth: 360, alignment: .leading)
          .fixedSize(horizontal: false, vertical: true)
      }
      .padding(.bottom, 12)
      Spacer(minLength: 0)
    }
    .padding(.top, 4)
  }

  @ViewBuilder private var deepWorkCard: some View {
    InkCard {
      VStack(alignment: .leading, spacing: 0) {
        Text("Today's deep work").inkH3()
          .padding(.bottom, 12)

        if !hasData {
          Text("No focus sessions tracked yet today. I'll fill this in as you work.")
            .inkSmall()
            .fixedSize(horizontal: false, vertical: true)
            .padding(.vertical, 4)
        } else {
          let blocks = Array(focusedSessions.prefix(3))
          ForEach(Array(blocks.enumerated()), id: \.element.id) { index, session in
            deepWorkRow(session, showDivider: index < blocks.count - 1 || stats.distractedCount > 0)
          }
          if stats.distractedCount > 0 {
            distractionRow
          }
          if blocks.isEmpty && stats.distractedCount == 0 {
            Text("Heads-down time will appear here as I catch it.")
              .inkSmall().padding(.vertical, 4)
          }
        }
      }
    }
  }

  private func deepWorkRow(_ session: StoredFocusSession, showDivider: Bool) -> some View {
    VStack(spacing: 0) {
      HStack(spacing: 12) {
        Image(systemName: "lock").font(.system(size: 13)).foregroundColor(Ink.faint)
        Text(timeRange(for: session)).inkBody()
        Text(session.description.isEmpty ? "Protected" : "Protected · \(session.description)")
          .inkSmall()
          .lineLimit(1)
        Spacer(minLength: 8)
        InkBadge(text: "Held", kind: .sent)
      }
      .padding(.vertical, 10)
      if showDivider {
        Rectangle().fill(Ink.hair).frame(height: 1)
      }
    }
  }

  private var distractionRow: some View {
    HStack(spacing: 12) {
      Image(systemName: "display").font(.system(size: 13)).foregroundColor(Ink.faint)
      Text("Pulled away \(stats.distractedCount)×").font(InkFont.sans(14)).foregroundColor(Ink.muted)
      if let top = stats.topDistractions.first {
        Text("mostly \(top.appOrSite)").inkSmall().lineLimit(1)
      }
      Spacer(minLength: 8)
    }
    .padding(.vertical, 10)
  }

  @ViewBuilder private var tomorrowCard: some View {
    NextCard {
      VStack(alignment: .leading, spacing: 14) {
        HStack(spacing: 7) {
          Circle().fill(Ink.accent).frame(width: 6, height: 6)
          Text("TOMORROW")
            .font(InkFont.sans(11, .semibold)).foregroundColor(Ink.accentStrong).tracking(1.2)
        }
        Text("I'll guard 9–11am again — it's where you do your best work. Meetings after 4pm stay off your calendar.")
          .inkBody()
          .frame(maxWidth: 520, alignment: .leading)
          .fixedSize(horizontal: false, vertical: true)
        if protecting {
          HStack(spacing: 8) {
            Image(systemName: "checkmark.circle.fill").font(.system(size: 14)).foregroundColor(Ink.live)
            Text("Protecting your mornings.").font(InkFont.sans(13, .medium)).foregroundColor(Ink.sentText)
          }
        } else {
          InkButton(title: "Protect my mornings", kind: .primary) {
            protecting = true
          }
        }
      }
    }
  }

  // MARK: - Helpers

  private func timeRange(for session: StoredFocusSession) -> String {
    let f = DateFormatter()
    f.dateFormat = "h:mm"
    let start = session.createdAt
    guard let seconds = session.durationSeconds, seconds > 0 else {
      return f.string(from: start)
    }
    let end = start.addingTimeInterval(TimeInterval(seconds))
    return "\(f.string(from: start)) – \(f.string(from: end))"
  }
}
