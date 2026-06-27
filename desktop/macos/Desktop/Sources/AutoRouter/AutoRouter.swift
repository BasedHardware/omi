import Foundation

// MARK: - AutoRouter
//
// Multi-task model selector that calls the backend `/v1/auto-router/pick`
// endpoint and caches picks per task in UserDefaults with a 24h TTL.
//
// Mirrors the singleton + UserDefaults + 24h TTL pattern from
// `RealtimeOmni/AutoModelSelector.swift` but extended to multiple task types.
// The upstream auto-router handles ONE task (realtime voice); this handles FIVE
// task types with configurable per-task weights. v1 does NOT modify or extend
// the upstream `AutoModelSelector`.
//
// Endpoint contract (matches `backend/routers/auto_router.py`):
//   GET <base>/v1/auto-router/pick?task=<snake_case_task>
//   Returns: `{"task": str, "model": str|null, "scores": {id: float, ...},
//             "detail": {weights, candidates, reason}, "updated_at": str,
//             "attribution": str}`
//   HTTP 400 if task is unknown; HTTP 422 if `task` query param is missing.

@MainActor
final class AutoRouter {
    static let shared = AutoRouter()

    /// UserDefaults key prefix for per-task picks and refresh timestamps.
    private static let pickKeyPrefix = "autoRouterPick."
    private static let pickDateKeyPrefix = "autoRouterPickDate."
    /// Refresh interval (24h, matching upstream `/v1/auto/model-pick` and the
    /// backend `DailyRefreshCache` TTL).
    private static let refreshInterval: TimeInterval = 24 * 60 * 60

    /// Endpoint path — kept as a static so tests can build URLs without
    /// instantiating the singleton.
    static let endpointPath = "/v1/auto-router/pick"

    /// HTTP request timeout, in seconds.
    private static let requestTimeout: TimeInterval = 15

    private init() {}

    // MARK: - UserDefaults keys

    private func pickKey(for task: AutoRouterTask) -> String {
        Self.pickKeyPrefix + task.rawValue
    }

    private func pickDateKey(for task: AutoRouterTask) -> String {
        Self.pickDateKeyPrefix + task.rawValue
    }

    // MARK: - Read cached picks

    /// The current cached model ID for `task`, if any (regardless of staleness).
    func currentPick(for task: AutoRouterTask) -> String? {
        UserDefaults.standard.string(forKey: pickKey(for: task))
    }

    /// The last successful refresh timestamp for `task`, or nil if never refreshed.
    private func lastRefresh(for task: AutoRouterTask) -> Date? {
        UserDefaults.standard.object(forKey: pickDateKey(for: task)) as? Date
    }

    // MARK: - URL building (testable)

    /// Build the endpoint URL for `task` against the given base URL.
    /// Returns nil if the URL is malformed.
    static func endpointURL(base: String, task: AutoRouterTask) -> URL? {
        let cleanedBase = base.hasSuffix("/") ? String(base.dropLast()) : base
        var components = URLComponents(string: cleanedBase + endpointPath)
        components?.queryItems = [URLQueryItem(name: "task", value: task.rawValue)]
        return components?.url
    }

    // MARK: - Refresh

    /// In-flight refresh deduplication (cubic review). When multiple
    /// callers invoke `refreshIfStale(for:)` concurrently, only the first
    /// starts a network request; subsequent callers wait on the same Task.
    /// Keyed by task; cleared when the Task completes.
    private var inFlightRefreshes: [AutoRouterTask: Task<Void, Never>] = [:]

    /// Refresh the pick for `task` only if the cache is stale (>24h) or empty.
    /// No-op if a fresh pick already exists.
    /// `onComplete` is called when the refresh finishes (success OR failure).
    /// Used by callers that need to re-warm their model state when the router
    /// pick changes after a background refresh (cubic review).
    func refreshIfStale(
        for task: AutoRouterTask,
        onComplete: ((AutoRouterTask) -> Void)? = nil
    ) {
        if let last = lastRefresh(for: task),
           Date().timeIntervalSince(last) < Self.refreshInterval,
           currentPick(for: task) != nil {
            // Cache is fresh — still fire onComplete so the caller can
            // know there's nothing to update.
            onComplete?(task)
            return
        }
        // In-flight dedup (cubic review): if a refresh for this task is
        // already running, don't start a second one. Subsequent callers
        // either join the existing task (re-awaiting the same result) or
        // skip if the task is already done. Avoids duplicate network
        // round-trips when multiple callers invoke refreshIfStale
        // concurrently.
        if let existing = inFlightRefreshes[task] {
            log("AutoRouter: refresh for \(task.rawValue) already in flight, joining")
            Task { _ = await existing.value; onComplete?(task) }
            return
        }
        let taskHandle = Task { [weak self] in
            await self?.refresh(task: task)
            onComplete?(task)
        }
        inFlightRefreshes[task] = taskHandle
        // Clean up the dedup entry when the task completes (success or failure).
        // Cubic review: also add a hard timeout via a parallel Task to avoid
        // permanently locking out refreshes if the underlying Task never
        // completes (e.g., a hung AuthService call with no explicit timeout).
        // 30s matches URLSession's default timeout — the auth/network stack
        // will have given up by then.
        Task {
            _ = await taskHandle.value
            inFlightRefreshes[task] = nil
        }
        Task { [weak self] in
            try? await Task.sleep(nanoseconds: 30_000_000_000)
            // If the original task is STILL running, force-clear the dedup
            // entry so subsequent calls can proceed. The original task will
            // complete and update UserDefaults on its own.
            if let self_ = self, self_.inFlightRefreshes[task] != nil {
                self_.inFlightRefreshes[task] = nil
            }
        }
    }

    /// Force a refresh of the pick for `task`. Reads from the backend endpoint,
    /// caches in UserDefaults, and gracefully degrades on any failure (keeps
    /// the last good pick, or returns nil on first-ever failure).
    func refresh(task: AutoRouterTask) async {
        let base = DesktopBackendEnvironment.pythonBaseURL()
        guard let url = Self.endpointURL(base: base, task: task) else {
            log("AutoRouter: invalid URL for \(task.rawValue) at base=\(base)")
            return
        }

        var req = URLRequest(url: url)
        req.timeoutInterval = Self.requestTimeout
        if let auth = try? await AuthService.shared.getAuthHeader() {
            req.setValue(auth, forHTTPHeaderField: "Authorization")
        }

        do {
            let (data, resp) = try await URLSession.shared.data(for: req)
            guard let http = resp as? HTTPURLResponse, (200..<300).contains(http.statusCode),
                  let obj = try? JSONSerialization.jsonObject(with: data) as? [String: Any] else {
                log("AutoRouter: non-success response for \(task.rawValue)")
                return
            }
            // The endpoint may legitimately return `"model": null` when no candidates are
            // registered for a task. In that case, CLEAR the cached pick so callers
            // don't keep using a stale model — the absence of a candidate today should
            // not be masked by a model that was valid yesterday.
            if let raw = obj["model"] as? String {
                store(raw, for: task)
            } else {
                UserDefaults.standard.removeObject(forKey: pickKey(for: task))
                // Update the refresh date even on null model so that
                // refreshIfStale respects the 24h TTL (without this,
                // every subsequent call would re-fire because currentPick
                // is nil — potential backend flooding).
                UserDefaults.standard.set(Date(), forKey: pickDateKey(for: task))
                log("AutoRouter: no model available for \(task.rawValue) (cleared stale cache)")
            }
        } catch {
            log("AutoRouter: refresh failed for \(task.rawValue): \(error.localizedDescription)")
            // Keep last good pick (if any) — graceful degradation.
        }
    }

    // MARK: - Store (also used by tests / server overrides)

    /// Store a model ID for `task`. Used internally by `refresh`; can also
    /// be called externally to apply a server-provided pick (mirrors upstream's
    /// `applyServerPick` pattern).
    func store(_ modelId: String, for task: AutoRouterTask) {
        UserDefaults.standard.set(modelId, forKey: pickKey(for: task))
        UserDefaults.standard.set(Date(), forKey: pickDateKey(for: task))
        log("AutoRouter: \(task.rawValue) → \(modelId)")
    }

    /// Clear the cached pick for `task` (forces the next `refreshIfStale` to fetch).
    /// Clears both the model ID AND the refresh date — callers should not see a
    /// stale pick after invalidation.
    func invalidate(task: AutoRouterTask) {
        UserDefaults.standard.removeObject(forKey: pickKey(for: task))
        UserDefaults.standard.removeObject(forKey: pickDateKey(for: task))
    }

    // MARK: - Logging

    private func log(_ message: String) {
        // Single-line log format matching upstream AutoModelSelector style.
        // Kept private so callers can't bypass the structured log path.
        NSLog("[AutoRouter] %@", message)
    }
}
