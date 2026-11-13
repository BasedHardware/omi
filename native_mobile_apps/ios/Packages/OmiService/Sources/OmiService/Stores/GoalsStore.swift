import Foundation
import Observation
import OmiCore
import OmiNetwork

/// Numeric goals (Flutter `GoalsProvider` + `goals_widget.dart`): title, current of target.
/// Delete is immediate with Undo, like tasks.
@MainActor
@Observable
public final class GoalsStore {
    public enum Phase: Equatable, Sendable { case idle, loading, loaded, failed(String) }

    /// Flutter's goals widget allows four at a time.
    public static let maxGoals = 4

    public private(set) var phase: Phase = .idle
    public private(set) var goals: [Goal] = []
    public private(set) var lastError: String?
    /// The goal waiting out its undo window.
    public private(set) var pendingDeletion: Goal?

    private let api: any APIClientProtocol
    private let undoWindow: Duration
    private var deletionTask: Task<Void, Never>?
    private var deletedIndex = 0

    public init(api: any APIClientProtocol, undoWindow: Duration = .seconds(5)) {
        self.api = api
        self.undoWindow = undoWindow
    }

    public var canAdd: Bool { goals.count < Self.maxGoals }

    public func load() async {
        if goals.isEmpty { phase = .loading }
        do {
            let all = try await api.goals()
            goals = all.filter { $0.id != pendingDeletion?.id }
            phase = .loaded
        } catch {
            phase = .failed(String(describing: error))
        }
    }

    /// Returns whether the backend took it. A blank title or a fifth goal is refused.
    @discardableResult
    public func create(title: String, current: Double, target: Double) async -> Bool {
        let title = title.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !title.isEmpty, canAdd else { return false }
        lastError = nil
        do {
            goals.append(try await api.createGoal(title: title, current: current, target: target))
            return true
        } catch {
            lastError = String(describing: error)
            return false
        }
    }

    /// Optimistic edit; rolls back if the backend refuses.
    @discardableResult
    public func update(_ id: String, title: String, current: Double, target: Double) async -> Bool {
        let title = title.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !title.isEmpty, let index = goals.firstIndex(where: { $0.id == id }) else { return false }
        let previous = goals[index]
        goals[index].title = title
        goals[index].current = current
        goals[index].target = target
        return await save(previous) { try await $0.updateGoal(id: id, title: title, current: current, target: target) }
    }

    /// Optimistic progress change (the − / + on a goal).
    @discardableResult
    public func setProgress(_ id: String, current: Double) async -> Bool {
        guard let index = goals.firstIndex(where: { $0.id == id }) else { return false }
        let previous = goals[index]
        goals[index].current = max(current, 0)
        return await save(previous) { try await $0.setGoalProgress(id: id, current: max(current, 0)) }
    }

    /// Hides the goal now; the backend delete runs after the undo window. A second delete sends the first.
    public func deleteWithUndo(_ id: String) {
        guard let index = goals.firstIndex(where: { $0.id == id }) else { return }
        if let earlier = pendingDeletion {
            deletionTask?.cancel()
            pendingDeletion = nil
            Task { await send(earlier, index: deletedIndex) }
        }
        deletedIndex = index
        pendingDeletion = goals.remove(at: index)
        let window = undoWindow
        deletionTask = Task { [weak self] in
            try? await Task.sleep(for: window)
            guard !Task.isCancelled else { return }
            await self?.commitDeletion()
        }
    }

    public func undoDelete() {
        guard let goal = pendingDeletion else { return }
        deletionTask?.cancel()
        pendingDeletion = nil
        goals.insert(goal, at: min(deletedIndex, goals.count))
    }

    public func commitDeletion() async {
        guard let goal = pendingDeletion else { return }
        pendingDeletion = nil
        deletionTask?.cancel()
        await send(goal, index: deletedIndex)
    }

    private func send(_ goal: Goal, index: Int) async {
        do {
            try await api.deleteGoal(id: goal.id)
        } catch {
            goals.insert(goal, at: min(index, goals.count))
            lastError = String(describing: error)
        }
    }

    private func save(_ previous: Goal, _ call: (any APIClientProtocol) async throws -> Goal) async -> Bool {
        lastError = nil
        do {
            let saved = try await call(api)
            if let index = goals.firstIndex(where: { $0.id == saved.id }) { goals[index] = saved }
            return true
        } catch {
            if let index = goals.firstIndex(where: { $0.id == previous.id }) { goals[index] = previous }
            lastError = String(describing: error)
            return false
        }
    }
}
