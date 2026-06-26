import Foundation
import SwiftUI

// MARK: - AutoRouterSettingsViewModel
//
// Drives the Settings → Auto-router page. Owns the user's prefs state, exposes
// per-task weight bindings, debounces saves (~500ms), and surfaces save errors.
//
// State flow:
//   1. View calls `load()` on appear.
//   2. View passes `$viewModel.weights(for: .pttResponse)` to each WeightSlider.
//   3. Slider writes propagate via `setWeights(_:for:)` → debounced save.
//   4. Save fires `UserPrefsClient.shared.save(prefs:)` after 500ms of inactivity.
//   5. Errors set `errorState`; UI shows error state with retry button.
//
// Concurrency:
//   - All public methods are `@MainActor` (called from SwiftUI views).
//   - Debounce uses a serial DispatchQueue + a single in-flight Task.
//   - Cancel-and-replace semantics: the latest save supersedes any pending one.
//
// Defaults:
//   - `loadTaskDefaults()` provides each task's default weights from the
//     backend's task registry (read at startup). This lets the UI render
//     sliders pre-populated with sensible defaults even when the user has
//     no overrides.

@MainActor
final class AutoRouterSettingsViewModel: ObservableObject {
    // MARK: - Published state

    /// Per-task weight overrides. Empty when the user has no overrides.
    @Published private(set) var prefs: UserPrefs = .empty

    /// Current save status — drives loading indicator + error state in the view.
    @Published private(set) var saveStatus: SaveStatus = .idle

    /// True until the initial `load()` completes.
    @Published private(set) var isLoading: Bool = true

    /// Error from the last save attempt (if any). Cleared on next successful save.
    @Published var errorState: PrefsError?

    /// Per-task defaults (read from backend task registry at startup).
    /// Nil if `loadTaskDefaults()` hasn't completed yet.
    private(set) var taskDefaults: [AutoRouterTask: TaskWeights] = [:]

    /// Test-only setter for `taskDefaults`. Used by `setUp` in unit tests
    /// to skip the network roundtrip (production code uses `loadTaskDefaults`).
    #if DEBUG
    func _setTaskDefaultsForTesting(_ defaults: [AutoRouterTask: TaskWeights]) {
        self.taskDefaults = defaults
    }
    #endif

    // MARK: - Configuration

    /// Debounce interval — multiple slider writes within this window coalesce
    /// into one PUT. 500ms is the typical UX sweet spot (responsive but
    /// not chatty over a slow network).
    static let debounceInterval: TimeInterval = 0.5

    // MARK: - Internals

    private var pendingSaveTask: Task<Void, Never>?
    private let client: UserPrefsClient

    // MARK: - Init

    init(client: UserPrefsClient? = nil) {
        // Resolve `.shared` lazily here (not in the default arg) to avoid a
        // Swift 6 actor-isolation warning when the default value is read
        // from a nonisolated context. The init itself is @MainActor (the
        // whole class is), so resolving `.shared` here is safe.
        self.client = client ?? .shared
    }

    // MARK: - Load

    /// Initial load: fetch prefs + task defaults in parallel.
    /// Sets `isLoading = false` when both complete (even on partial failure —
    /// we want the UI to render even if the backend is down).
    func load() async {
        isLoading = true
        defer { isLoading = false }

        async let prefsLoad: () = loadPrefs()
        async let defaultsLoad: () = loadTaskDefaults()
        _ = await (prefsLoad, defaultsLoad)
    }

    private func loadPrefs() async {
        do {
            let fetched = try await client.fetch()
            self.prefs = fetched
        } catch {
            // Fail-open: render with empty prefs (uses task defaults).
            self.errorState = error as? PrefsError ?? .transport(underlying: error.localizedDescription)
            NSLog("[AutoRouterSettingsViewModel] prefs fetch failed: \(error.localizedDescription)")
        }
    }

    private func loadTaskDefaults() async {
        // Fetch from backend's GET /pick endpoint with default weights for
        // each task. The picker returns the chosen model + the WEIGHTS USED
        // (which are the task defaults from TaskRegistry). We then extract
        // the weights from the `detail.weights` field.
        // Fallback: if the fetch fails, fall back to balanced weights for
        // every task (1/3 each).
        //
        // Parallelized via `withTaskGroup` so all 5 task fetches fire
        // concurrently (sequential fetches would add ~5 round-trips of
        // latency on a flaky network). Each fetch is independent.
        let defaults: [AutoRouterTask: TaskWeights] = await withTaskGroup(
            of: (AutoRouterTask, TaskWeights?).self
        ) { group in
            for task in AutoRouterTask.allCases {
                group.addTask { (task, await self.fetchDefaultWeights(for: task)) }
            }
            var result: [AutoRouterTask: TaskWeights] = [:]
            for await (task, weights) in group {
                result[task] = weights ?? .balanced
            }
            return result
        }
        self.taskDefaults = defaults
    }

    private func fetchDefaultWeights(for task: AutoRouterTask) async -> TaskWeights? {
        // Calls GET /pick?task=<name> — the response `detail.weights` field
        // contains the task's default weights (from the backend TaskRegistry).
        // We don't care about the chosen model here, only the weights.
        let base = DesktopBackendEnvironment.pythonBaseURL()
        guard let url = AutoRouter.endpointURL(base: base, task: task) else {
            return nil
        }
        var req = URLRequest(url: url)
        req.timeoutInterval = UserPrefsClient.requestTimeoutSeconds
        if let auth = try? await AuthService.shared.getAuthHeader() {
            req.setValue(auth, forHTTPHeaderField: "Authorization")
        }
        do {
            let (data, _) = try await URLSession.shared.data(for: req)
            guard let obj = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
                  let detail = obj["detail"] as? [String: Any],
                  let weights = detail["weights"] as? [String: Double]
            else { return nil }
            return TaskWeights.fromRaw(weights)
        } catch {
            NSLog("[AutoRouterSettingsViewModel] default weights fetch failed for \(task.rawValue): \(error.localizedDescription)")
            return nil
        }
    }

    // MARK: - Per-task binding accessors

    /// Returns the effective weights for `task` (override if set, else default).
    func weights(for task: AutoRouterTask) -> TaskWeights {
        if let override = prefs.overrides[task.rawValue] {
            return override
        }
        return taskDefaults[task] ?? .balanced
    }

    /// True when `task` has a custom override (different from default).
    func isCustomized(for task: AutoRouterTask) -> Bool {
        guard let override = prefs.overrides[task.rawValue] else { return false }
        let default_ = taskDefaults[task] ?? .balanced
        return !override.approximatelyEquals(default_)
    }

    /// Update the weights for `task` (writes the override + schedules debounced save).
    /// The binding used by WeightSlider writes through this method.
    func setWeights(_ weights: TaskWeights, for task: AutoRouterTask) {
        var updated = prefs.overrides
        updated[task.rawValue] = weights
        prefs = UserPrefs(overrides: updated)
        scheduleSave()
    }

    /// Reset `task` to its default weights (removes the override).
    func resetToDefaults(for task: AutoRouterTask) {
        var updated = prefs.overrides
        updated.removeValue(forKey: task.rawValue)
        prefs = UserPrefs(overrides: updated)
        scheduleSave()
    }

    /// Reset all tasks to defaults (clears all overrides).
    func resetAllToDefaults() {
        prefs = .empty
        scheduleSave()
    }

    /// Retry the last failed save (called by the retry button in error state).
    func retrySave() {
        scheduleSave()
    }

    // MARK: - Debounced save

    /// Schedule a debounced save. Cancels any pending save first.
    /// Multiple slider writes within `debounceInterval` coalesce into one PUT.
    private func scheduleSave() {
        pendingSaveTask?.cancel()
        let snapshot = prefs
        pendingSaveTask = Task { [weak self] in
            try? await Task.sleep(nanoseconds: UInt64(Self.debounceInterval * 1_000_000_000))
            if Task.isCancelled { return }
            await self?.performSave(snapshot)
        }
    }

    /// Execute the save (called by the debounce timer).
    private func performSave(_ prefsToSave: UserPrefs) async {
        // Cubic review: catch CancellationError separately so a cancelled
        // save (caused by a newer debounced save superseding this one) is
        // not surfaced as a real failure in the UI. Cancellation is normal
        // (the newer save takes over) and shouldn't trigger the error banner.
        saveStatus = .saving
        errorState = nil
        do {
            let updated = try await client.save(prefs: prefsToSave)
            // If a newer save was scheduled while we were awaiting, let IT
            // run instead of clobbering the UI state with our stale result.
            if Task.isCancelled { return }
            self.prefs = updated
            self.saveStatus = .saved
        } catch is CancellationError {
            // Expected — a newer save superseded us. Don't surface as a failure.
            return
        } catch let err as PrefsError {
            if Task.isCancelled { return }
            self.errorState = err
            self.saveStatus = .failed(err)
            NSLog("[AutoRouterSettingsViewModel] save failed: \(err)")
        } catch {
            if Task.isCancelled { return }
            self.errorState = .transport(underlying: error.localizedDescription)
            self.saveStatus = .failed(.transport(underlying: error.localizedDescription))
            NSLog("[AutoRouterSettingsViewModel] save failed: \(error.localizedDescription)")
        }
    }

    // MARK: - Save status

    enum SaveStatus: Equatable {
        case idle
        case saving
        case saved
        case failed(PrefsError)
    }
}

// MARK: - SwiftUI binding helpers

extension AutoRouterSettingsViewModel {
    /// Get a SwiftUI Binding<TaskWeights> for `task` that writes through
    /// `setWeights(_:for:)` (which triggers debounced save). Used by the view.
    func binding(for task: AutoRouterTask) -> Binding<TaskWeights> {
        Binding(
            get: { [weak self] in self?.weights(for: task) ?? .balanced },
            set: { [weak self] newValue in self?.setWeights(newValue, for: task) }
        )
    }
}
