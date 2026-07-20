import Combine
import Foundation

/// Loads the content pieces of the redesigned Home surface that are not plain
/// counts: today's proactive insights (the advice stream that previously only
/// reached the floating-bar notification surface), today's Rewind filmstrip
/// frames, and the quality-gated memories shown on the first-win hero.
///
/// All sources are local (GRDB stores + Rewind database); a loader seam keeps
/// every branch hermetically testable.
@MainActor
final class HomeTodayStore: ObservableObject {

  struct InsightItem: Identifiable, Equatable {
    let id: Int64
    let text: String
    let sourceApp: String
    let createdAt: Date
  }

  struct Content: Equatable {
    var insights: [InsightItem] = []
    var filmstrip: [Screenshot] = []
    var firstWinMemories: [String] = []
    var firstWinMemoryCount = 0
  }

  struct Loader {
    let loadTodayInsights: @MainActor @Sendable (_ startOfDay: Date) async -> [InsightItem]
    let loadFilmstrip: @MainActor @Sendable (_ startOfDay: Date) async -> [Screenshot]
    let loadFirstWinMemories: @MainActor @Sendable () async -> (memories: [String], total: Int)
    let dismissInsight: @MainActor @Sendable (_ id: Int64) async -> Void

    static let live = Loader(
      loadTodayInsights: { startOfDay in
        do {
          let records = try await ProactiveStorage.shared.getExtractions(
            type: .insight, limit: 40, includeDismissed: false)
          return
            records
            .filter { $0.createdAt >= startOfDay }
            .sorted { $0.createdAt > $1.createdAt }
            .prefix(HomeTodayStore.maxInsights)
            .compactMap { record in
              guard let id = record.id else { return nil }
              let text = record.content.trimmingCharacters(in: .whitespacesAndNewlines)
              guard !text.isEmpty else { return nil }
              return InsightItem(
                id: id, text: text, sourceApp: record.sourceApp, createdAt: record.createdAt)
            }
        } catch {
          logError("HomeTodayStore: Failed to load today's insights", error: error)
          return []
        }
      },
      loadFilmstrip: { startOfDay in
        do {
          // Thumbnails decode from video chunks; storage must be initialized
          // before Home renders frames (Rewind page normally does this).
          try await RewindStorage.shared.initialize()
          return try await RewindDatabase.shared.getScreenshotsSampled(
            from: startOfDay, to: Date(), targetCount: HomeTodayStore.filmstripTargetCount)
        } catch {
          // Common and expected before the Rewind database opens or when
          // screen capture never ran today.
          return []
        }
      },
      loadFirstWinMemories: {
        do {
          let memories = try await MemoryStorage.shared.getLocalMemories(limit: 80)
          let total = try await MemoryStorage.shared.getLocalMemoriesCount()
          let texts = FirstWinMemoryFilter.displayable(
            memories.map { $0.content }, limit: HomeTodayStore.maxFirstWinMemories)
          return (texts, total)
        } catch {
          logError("HomeTodayStore: Failed to load first-win memories", error: error)
          return ([], 0)
        }
      },
      dismissInsight: { id in
        do {
          try await ProactiveStorage.shared.dismissExtraction(id: id)
        } catch {
          logError("HomeTodayStore: Failed to dismiss insight", error: error)
        }
      }
    )
  }

  static let maxInsights = 3
  static let maxFirstWinMemories = 3
  static let filmstripTargetCount = 10

  @Published private(set) var content = Content()

  private let loader: Loader
  private let now: () -> Date
  private var refreshTask: Task<Void, Never>?

  init(loader: Loader = .live, now: @escaping () -> Date = Date.init) {
    self.loader = loader
    self.now = now
  }

  func refresh(includeFirstWin: Bool) async {
    if let refreshTask {
      await refreshTask.value
      return
    }
    let task = Task { [weak self] in
      guard let self else { return }
      await self.performRefresh(includeFirstWin: includeFirstWin)
    }
    refreshTask = task
    await task.value
    refreshTask = nil
  }

  func dismissInsight(_ item: InsightItem) async {
    content.insights.removeAll { $0.id == item.id }
    await loader.dismissInsight(item.id)
  }

  func resetSessionState() {
    refreshTask?.cancel()
    refreshTask = nil
    content = Content()
  }

  private func performRefresh(includeFirstWin: Bool) async {
    let startOfDay = Calendar.current.startOfDay(for: now())
    async let insights = loader.loadTodayInsights(startOfDay)
    async let filmstrip = loader.loadFilmstrip(startOfDay)
    let (loadedInsights, loadedFilmstrip) = await (insights, filmstrip)

    var updated = content
    updated.insights = loadedInsights
    updated.filmstrip = loadedFilmstrip
    if includeFirstWin {
      let (memories, total) = await loader.loadFirstWinMemories()
      updated.firstWinMemories = memories
      updated.firstWinMemoryCount = total
    }
    guard !Task.isCancelled else { return }
    content = updated
  }
}
