import SwiftUI

/// The calm "one next move" home — mockup `home.html`, live-wired.
struct RedesignHomePage: View {
  @ObservedObject var appState: AppState
  @ObservedObject var memoriesViewModel: MemoriesViewModel
  @ObservedObject var dashboardViewModel: DashboardViewModel
  @ObservedObject private var tasksStore = TasksStore.shared
  @Binding var selectedIndex: Int

  private var name: String {
    let given = AuthService.shared.givenName.trimmingCharacters(in: .whitespaces)
    if !given.isEmpty { return given }
    let display = AuthService.shared.displayName.trimmingCharacters(in: .whitespaces)
    return display.isEmpty ? "there" : display.components(separatedBy: " ").first ?? display
  }

  private var greeting: String {
    let hour = Calendar.current.component(.hour, from: Date())
    switch hour {
    case 5..<12: return "Good morning"
    case 12..<17: return "Good afternoon"
    case 17..<22: return "Good evening"
    default: return "Still up"
    }
  }

  private var dateLine: String {
    let f = DateFormatter()
    f.dateFormat = "EEEE, MMMM d"
    return f.string(from: Date())
  }

  private var nextTask: TaskActionItem? {
    tasksStore.overdueTasks.first ?? tasksStore.todaysTasks.first
      ?? tasksStore.incompleteTasks.first
  }

  private var waitingCount: Int {
    max(0, tasksStore.incompleteTasks.count - 1)
  }

  var body: some View {
    ScrollView {
      VStack(alignment: .leading, spacing: 24) {
        header
        nextCard
        askBar
        statsRow
        footer
      }
      .frame(maxWidth: 840, alignment: .leading)
      .frame(maxWidth: .infinity, alignment: .center)
      .padding(.horizontal, 48)
      .padding(.vertical, 44)
    }
    .frame(maxWidth: .infinity, maxHeight: .infinity)
    .background(Ink.canvas)
  }

  private var header: some View {
    HStack(alignment: .top) {
      VStack(alignment: .leading, spacing: 8) {
        Text(dateLine).inkMonoCaption()
        Text("\(greeting), \(name).").inkH1()
      }
      Spacer()
      Button {
        if let url = URL(string: "https://affiliate.omi.me") { NSWorkspace.shared.open(url) }
      } label: { MemberBadge(text: "Member") }
      .buttonStyle(.plain)
    }
  }

  @ViewBuilder private var nextCard: some View {
    NextCard {
      if let task = nextTask {
        VStack(alignment: .leading, spacing: 14) {
          HStack {
            HStack(spacing: 7) {
              Circle().fill(Ink.accent).frame(width: 6, height: 6)
              Text("DO THIS NEXT")
                .font(InkFont.sans(11, .semibold)).foregroundColor(Ink.accentStrong)
                .tracking(1.2)
            }
            Spacer()
            if waitingCount > 0 {
              Text("\(waitingCount) more waiting").inkCaption()
            }
          }
          Text(task.description)
            .font(InkFont.serif(24, .medium)).foregroundColor(Ink.ink).tracking(-0.3)
            .fixedSize(horizontal: false, vertical: true)
          Text(subtitle(for: task)).inkSmall()
            .fixedSize(horizontal: false, vertical: true)
          HStack(spacing: 12) {
            InkButton(title: "Open in Tasks", systemImage: "arrow.up.right", kind: .primary) {
              selectedIndex = 4
            }
            InkButton(title: "Ask about it", kind: .ghost) {
              FloatingControlBarManager.shared.openAIInputWithQuery(task.description)
            }
          }
          .padding(.top, 2)
        }
      } else {
        VStack(alignment: .leading, spacing: 12) {
          HStack(spacing: 7) {
            Circle().fill(Ink.live).frame(width: 6, height: 6)
            Text("YOU'RE CLEAR")
              .font(InkFont.sans(11, .semibold)).foregroundColor(Ink.sentText).tracking(1.2)
          }
          Text("Nothing on your plate right now.")
            .font(InkFont.serif(24, .medium)).foregroundColor(Ink.ink).tracking(-0.3)
          Text("I'll surface things here the moment they come up — from your calls, screen, and messages.")
            .inkSmall().fixedSize(horizontal: false, vertical: true)
        }
      }
    }
  }

  private func subtitle(for task: TaskActionItem) -> String {
    let src = (task.source ?? "").lowercased()
    if src.contains("screenshot") { return "I caught this on your screen. Take a look." }
    if src.contains("transcription") { return "From something you said today. Take a look." }
    if task.dueAt != nil { return "You said you'd get to this. Take a look." }
    return "Here when you're ready. Take a look."
  }

  private var askBar: some View {
    Button {
      FloatingControlBarManager.shared.openAIInput()
    } label: {
      HStack(spacing: 12) {
        Image(systemName: "sparkles").font(.system(size: 15)).foregroundColor(Ink.faint)
        Text("Ask omi anything — it remembers what you saw and said")
          .font(InkFont.sans(14)).foregroundColor(Ink.faint)
        Spacer()
        Text("⌘K").font(InkFont.mono(11)).foregroundColor(Ink.faint)
          .padding(.horizontal, 6).padding(.vertical, 2)
          .background(RoundedRectangle(cornerRadius: 5).fill(Ink.surface2)
            .overlay(RoundedRectangle(cornerRadius: 5).strokeBorder(Ink.hair, lineWidth: 1)))
      }
      .padding(.horizontal, 18)
      .frame(height: 52)
      .background(
        Capsule().fill(Ink.surface).overlay(Capsule().strokeBorder(Ink.hair2, lineWidth: 1)))
      .contentShape(Capsule())
    }
    .buttonStyle(.plain)
  }

  private var statsRow: some View {
    HStack(alignment: .top, spacing: 40) {
      statButton(number: "\(memoriesViewModel.memories.count)", label: "Remembered") { selectedIndex = 3 }
      statButton(number: "\(tasksStore.todaysTasks.count)", label: "Tasks today") { selectedIndex = 4 }
      statButton(number: "\(appState.conversations.count)", label: "Conversations") { selectedIndex = 1 }
      statButton(number: "\(dashboardViewModel.goals.count)", label: "Goals") { selectedIndex = 0 }
      Spacer()
    }
    .padding(.top, 8)
  }

  private func statButton(number: String, label: String, action: @escaping () -> Void) -> some View {
    Button(action: action) { InkStat(number: number, label: label) }
      .buttonStyle(.plain)
  }

  private var footer: some View {
    HStack(spacing: 6) {
      Image(systemName: "lock").font(.system(size: 11)).foregroundColor(Ink.faint)
      Text("On your Mac · encrypted · you own it all.").inkCaption()
    }
    .padding(.top, 8)
  }
}
