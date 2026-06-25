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

    /// Refresh the pick for `task` only if the cache is stale (>24h) or empty.
    /// No-op if a fresh pick already exists.
    func refreshIfStale(for task: AutoRouterTask) {
        if let last = lastRefresh(for: task),
           Date().timeIntervalSince(last) < Self.refreshInterval,
           currentPick(for: task) != nil {
            return
        }
        Task { await refresh(task: task) }
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
                  let obj = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
                  let raw = obj["model"] as? String else {
                log("AutoRouter: non-success or missing 'model' for \(task.rawValue)")
                return
            }
            store(raw, for: task)
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
    func invalidate(task: AutoRouterTask) {
        UserDefaults.standard.removeObject(forKey: pickDateKey(for: task))
    }

    // MARK: - Logging

    private func log(_ message: String) {
        // Single-line log format matching upstream AutoModelSelector style.
        // Kept private so callers can't bypass the structured log path.
        NSLog("[AutoRouter] %@", message)
    }
}
