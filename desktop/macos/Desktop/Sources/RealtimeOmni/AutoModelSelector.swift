import Foundation

// MARK: - Auto model selector
//
// When the user picks "Auto", we choose the realtime provider whose underlying
// model currently scores best on a simple quality/speed formula, refreshed once
// a day from Artificial Analysis (https://artificialanalysis.ai — attribution
// required by their free API terms).
//
// The realtime audio variants aren't always in AA's LLM index, so each selectable
// provider maps to the closest representative model slug as a quality/speed proxy.
// The whole thing degrades gracefully: no key / network error / unknown schema →
// we keep the last good pick, or fall back to Gemini (cheapest + fastest).
//
// Production note: for "all Auto users to agree", the canonical pick should come
// from a backend cron writing one value all clients read. This client-side daily
// fetch is the same formula and a safe fallback when that endpoint is absent;
// `applyServerPick(_:)` lets the backend override.

@MainActor
final class AutoModelSelector {
    static let shared = AutoModelSelector()

    private let pickKey = "realtimeOmniAutoPick"
    private let pickDateKey = "realtimeOmniAutoPickDate"
    private let refreshInterval: TimeInterval = 24 * 60 * 60

    private init() {}

    /// The current cached pick, if any.
    var currentPick: RealtimeOmniProvider? {
        UserDefaults.standard.string(forKey: pickKey).flatMap(RealtimeOmniProvider.init(rawValue:))
    }

    private var lastRefresh: Date? {
        UserDefaults.standard.object(forKey: pickDateKey) as? Date
    }

    /// Call at launch and once a day. No-op if a fresh pick already exists.
    func refreshIfStale() {
        if let last = lastRefresh, Date().timeIntervalSince(last) < refreshInterval, currentPick != nil {
            return
        }
        Task { await refresh() }
    }

    /// Lets a backend-provided pick win over the local computation.
    func applyServerPick(_ provider: RealtimeOmniProvider) {
        store(provider)
    }

    /// Read the daily pick from the omi backend (which runs the Artificial
    /// Analysis quality/speed scoring server-side, keeping the AA key off the
    /// client). Falls back to Gemini only if we've never had a pick.
    func refresh() async {
        let httpBase = DesktopBackendEnvironment.pythonBaseURL()
            .replacingOccurrences(of: "wss://", with: "https://")
            .replacingOccurrences(of: "ws://", with: "http://")
        let base = httpBase.hasSuffix("/") ? String(httpBase.dropLast()) : httpBase
        guard let url = URL(string: "\(base)/v1/auto/model-pick") else {
            if currentPick == nil { store(.geminiFlashLive) }
            return
        }
        do {
            var req = URLRequest(url: url)
            req.timeoutInterval = 15
            if let auth = try? await AuthService.shared.getAuthHeader() {
                req.setValue(auth, forHTTPHeaderField: "Authorization")
            }
            let (data, resp) = try await URLSession.shared.data(for: req)
            guard let http = resp as? HTTPURLResponse, (200..<300).contains(http.statusCode),
                  let obj = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
                  let raw = obj["provider"] as? String,
                  let provider = RealtimeOmniProvider(rawValue: raw) else {
                if currentPick == nil { store(.geminiFlashLive) }
                return
            }
            store(provider)
        } catch {
            if currentPick == nil { store(.geminiFlashLive) }
        }
    }

    private func store(_ provider: RealtimeOmniProvider) {
        UserDefaults.standard.set(provider.rawValue, forKey: pickKey)
        UserDefaults.standard.set(Date(), forKey: pickDateKey)
        NotificationCenter.default.post(name: .realtimeOmniSettingsDidChange, object: nil)
        log("AutoModelSelector: picked \(provider.displayName)")
    }

}
