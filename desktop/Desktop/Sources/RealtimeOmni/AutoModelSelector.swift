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

    // Quality vs speed weighting. Quality leads; speed breaks ties.
    private let qualityWeight = 0.65
    private let speedWeight = 0.35
    private let speedCapTokensPerSec = 250.0  // normalize tok/s into [0,1]

    /// AA model slug used as the quality/speed proxy for each realtime provider.
    private let proxySlug: [RealtimeOmniProvider: String] = [
        .geminiFlashLive: "gemini-3-1-flash",
        .gptRealtime2: "gpt-realtime",
    ]

    private init() {}

    /// The current cached pick, if any.
    var currentPick: RealtimeOmniProvider? {
        UserDefaults.standard.string(forKey: pickKey).flatMap(RealtimeOmniProvider.init(rawValue:))
    }

    private var lastRefresh: Date? {
        UserDefaults.standard.object(forKey: pickDateKey) as? Date
    }

    private var apiKey: String? {
        if let k = UserDefaults.standard.string(forKey: "artificialAnalysisAPIKey"), !k.isEmpty { return k }
        if let k = ProcessInfo.processInfo.environment["ARTIFICIAL_ANALYSIS_API_KEY"], !k.isEmpty { return k }
        return nil
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

    func refresh() async {
        guard let scores = await fetchScores() else {
            // Keep last pick; only seed a default if we've never picked.
            if currentPick == nil { store(.geminiFlashLive) }
            return
        }
        let best = RealtimeOmniProvider.selectable
            .compactMap { p in scores[p].map { (p, $0) } }
            .max { $0.1 < $1.1 }?
            .0
        store(best ?? .geminiFlashLive)
    }

    private func store(_ provider: RealtimeOmniProvider) {
        UserDefaults.standard.set(provider.rawValue, forKey: pickKey)
        UserDefaults.standard.set(Date(), forKey: pickDateKey)
        NotificationCenter.default.post(name: .realtimeOmniSettingsDidChange, object: nil)
        log("AutoModelSelector: picked \(provider.displayName)")
    }

    // MARK: - Artificial Analysis fetch + scoring

    /// Returns a normalized [0,1]-ish score per selectable provider, or nil on failure.
    private func fetchScores() async -> [RealtimeOmniProvider: Double]? {
        guard let key = apiKey else {
            log("AutoModelSelector: no Artificial Analysis API key; using fallback")
            return nil
        }
        guard let url = URL(string: "https://artificialanalysis.ai/api/v2/data/llms/models") else { return nil }
        var req = URLRequest(url: url)
        req.setValue(key, forHTTPHeaderField: "x-api-key")
        req.timeoutInterval = 20

        do {
            let (data, response) = try await URLSession.shared.data(for: req)
            guard let http = response as? HTTPURLResponse, (200..<300).contains(http.statusCode) else {
                log("AutoModelSelector: AA HTTP error")
                return nil
            }
            let models = parseModels(data)
            guard !models.isEmpty else { return nil }

            var result: [RealtimeOmniProvider: Double] = [:]
            for provider in RealtimeOmniProvider.selectable {
                guard let slug = proxySlug[provider],
                      let metrics = bestMatch(slug: slug, in: models) else { continue }
                result[provider] = score(quality: metrics.quality, speed: metrics.speed)
            }
            return result.isEmpty ? nil : result
        } catch {
            logError("AutoModelSelector: AA fetch failed", error: error)
            return nil
        }
    }

    private func score(quality: Double, speed: Double) -> Double {
        let q = max(0, min(1, quality / 100.0))                 // intelligence index is ~0-100
        let s = max(0, min(1, speed / speedCapTokensPerSec))    // output tok/s
        return qualityWeight * q + speedWeight * s
    }

    private struct ModelMetrics { let slug: String; let quality: Double; let speed: Double }

    /// Tolerant parse: AA's schema may drift, so we read fields by several plausible
    /// keys rather than a rigid Codable model.
    private func parseModels(_ data: Data) -> [ModelMetrics] {
        guard let root = try? JSONSerialization.jsonObject(with: data) else { return [] }
        let array: [[String: Any]]
        if let dict = root as? [String: Any], let d = dict["data"] as? [[String: Any]] {
            array = d
        } else if let a = root as? [[String: Any]] {
            array = a
        } else {
            return []
        }

        return array.compactMap { item in
            let slug = (item["slug"] as? String)
                ?? (item["id"] as? String)
                ?? (item["name"] as? String)
            guard let slug else { return nil }

            let quality = firstNumber(item, [
                "artificial_analysis_intelligence_index",
                "intelligence_index", "intelligence", "quality_index", "quality",
            ], nested: item["evaluations"] as? [String: Any])

            let speed = firstNumber(item, [
                "median_output_tokens_per_second", "output_tokens_per_second",
                "output_speed", "tokens_per_second",
            ], nested: item["performance"] as? [String: Any])

            guard let quality, let speed else { return nil }
            return ModelMetrics(slug: slug.lowercased(), quality: quality, speed: speed)
        }
    }

    /// Pick the highest-quality model whose slug contains the proxy slug.
    private func bestMatch(slug: String, in models: [ModelMetrics]) -> ModelMetrics? {
        let needle = slug.lowercased()
        return models
            .filter { $0.slug.contains(needle) }
            .max { $0.quality < $1.quality }
    }

    private func firstNumber(_ item: [String: Any], _ keys: [String], nested: [String: Any]?) -> Double? {
        for key in keys {
            if let v = numberValue(item[key]) { return v }
            if let n = nested, let v = numberValue(n[key]) { return v }
        }
        return nil
    }

    private func numberValue(_ any: Any?) -> Double? {
        if let d = any as? Double { return d }
        if let i = any as? Int { return Double(i) }
        if let s = any as? String { return Double(s) }
        return nil
    }
}
