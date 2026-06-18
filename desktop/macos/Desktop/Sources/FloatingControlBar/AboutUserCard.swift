import Foundation

/// Builds the compact, local-only `<about_user>` block injected into the hub's
/// system instruction at warm time. Identity + rough situation only; exact/current
/// lists stay behind the read tools (the card hedges this). No network calls.
enum AboutUserCard {
  /// Pure formatter — kept separate from `build()` so it is unit-testable.
  static func render(name: String, facts: [String], overdue: Int, dueToday: Int) -> String {
    var lines: [String] = ["<about_user>"]
    if !name.isEmpty { lines.append("Name: \(name)") }
    lines.append("What Omi knows about them:")
    if facts.isEmpty {
      lines.append("- Nothing saved yet.")
    } else {
      lines.append(contentsOf: facts.map { "- \($0)" })
    }
    if overdue == 0 && dueToday == 0 {
      lines.append("Right now: nothing overdue or due today.")
    } else {
      lines.append("Right now: \(overdue) overdue, \(dueToday) due today.")
    }
    lines.append(
      "(This is a quick snapshot — for the exact or current list, call get_tasks / get_action_items.)")
    lines.append("</about_user>")
    return lines.joined(separator: "\n")
  }

  /// Gathers local data (auth name, top memories, task counts) and renders the card.
  /// Best-effort: any failure degrades to a smaller card, never throws.
  @MainActor
  static func build() async -> String {
    let name = AuthService.shared.givenName.trimmingCharacters(in: .whitespacesAndNewlines)

    var facts: [String] = []
    if let memories = try? await MemoryStorage.shared.getLocalMemories(limit: 8) {
      facts = memories.prefix(8).compactMap { mem in
        let t = mem.content.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !t.isEmpty else { return nil }
        return t.count > 120 ? String(t.prefix(117)) + "…" : t
      }
    }

    await TasksStore.shared.loadDashboardTasks()
    let overdue = TasksStore.shared.overdueTasks.count
    let dueToday = TasksStore.shared.todaysTasks.count

    return render(name: name, facts: facts, overdue: overdue, dueToday: dueToday)
  }
}
