import Foundation

// MARK: - UserPrefsClient
//
// Desktop client for the backend `/v1/auto-router/prefs` endpoint.
// Mirrors the `AutoRouter.shared` singleton pattern (one per app process).
//
// v3 created the design; v5 actually ports the file (v3's commit message
// claimed to add it but the file was never landed). v5's Settings UI
// depends on it (WeightSlider + AutoRouterSettingsViewModel).
//
// Endpoint contract (matches `backend/routers/auto_router.py`):
//   GET  <base>/v1/auto-router/prefs
//   → 200 {"uid": str, "prefs": {<task>: {quality, latency, cost}},
//          "updated_at": ISO-8601|null}
//   PUT  <base>/v1/auto-router/prefs
//   body: {"prefs": {<task>: {quality, latency, cost}}}
//   → 200 {"uid": str, "prefs": {...}, "updated_at": ISO-8601}
//   → 400 with error code on invalid weights
//   → 503 on backend unavailable
//
// Both methods require authentication (Authorization header via
// `AuthService.shared.getAuthHeader()`).

@MainActor
final class UserPrefsClient {
    static let shared = UserPrefsClient()

    /// Endpoint path — kept as a static so tests can build URLs without
    /// instantiating the singleton.
    static let endpointPath = "/v1/auto-router/prefs"

    /// HTTP request timeout, in seconds. Exposed as `internal` so other
    /// parts of the app (e.g., the Settings view model's `loadTaskDefaults`)
    /// can reuse the same timeout when hitting the `/pick` endpoint.
    static let requestTimeoutSeconds: TimeInterval = 15
    private static var requestTimeout: TimeInterval { requestTimeoutSeconds }

    private init() {}

    // MARK: - URL building (testable)

    /// Build the prefs endpoint URL against the given base URL.
    /// Returns nil if the URL is malformed.
    static func endpointURL(base: String, path: String = endpointPath) -> URL? {
        let cleanedBase = base.hasSuffix("/") ? String(base.dropLast()) : base
        let cleanedPath = path.hasPrefix("/") ? path : "/" + path
        return URL(string: cleanedBase + cleanedPath)
    }

    // MARK: - Fetch

    /// Fetch the current user's per-task weight overrides.
    /// Returns an empty `UserPrefs` if the user has not set any overrides
    /// (the backend returns `prefs: {}` in that case).
    /// Throws `PrefsError` on auth/transport/decoding failures.
    func fetch() async throws -> UserPrefs {
        let base = DesktopBackendEnvironment.pythonBaseURL()
        guard let url = Self.endpointURL(base: base) else {
            throw PrefsError.invalidURL(base: base)
        }

        var req = URLRequest(url: url)
        req.httpMethod = "GET"
        req.timeoutInterval = Self.requestTimeout
        req.setValue("application/json", forHTTPHeaderField: "Accept")
        if let auth = try? await AuthService.shared.getAuthHeader() {
            req.setValue(auth, forHTTPHeaderField: "Authorization")
        }

        do {
            let (data, resp) = try await URLSession.shared.data(for: req)
            guard let http = resp as? HTTPURLResponse else {
                throw PrefsError.invalidResponse
            }
            switch http.statusCode {
            case 200..<300:
                guard let obj = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
                      let rawPrefs = obj["prefs"] as? [String: [String: Double]] else {
                    throw PrefsError.decodingFailed
                }
                return UserPrefs.from(rawPrefs)
            case 401, 403:
                throw PrefsError.unauthorized
            default:
                throw PrefsError.serverError(status: http.statusCode)
            }
        } catch let err as PrefsError {
            throw err
        } catch {
            throw PrefsError.transport(underlying: error.localizedDescription)
        }
    }

    /// Save the user's per-task weight overrides. An empty `prefs` clears
    /// all overrides (server treats empty prefs as "use defaults").
    /// Throws `PrefsError` on auth/transport/server-validation failures.
    func save(prefs: UserPrefs) async throws -> UserPrefs {
        let base = DesktopBackendEnvironment.pythonBaseURL()
        guard let url = Self.endpointURL(base: base) else {
            throw PrefsError.invalidURL(base: base)
        }

        var req = URLRequest(url: url)
        req.httpMethod = "PUT"
        req.timeoutInterval = Self.requestTimeout
        req.setValue("application/json", forHTTPHeaderField: "Accept")
        req.setValue("application/json", forHTTPHeaderField: "Content-Type")
        if let auth = try? await AuthService.shared.getAuthHeader() {
            req.setValue(auth, forHTTPHeaderField: "Authorization")
        }
        req.httpBody = try JSONSerialization.data(withJSONObject: ["prefs": prefs.toRawDict()])

        do {
            let (data, resp) = try await URLSession.shared.data(for: req)
            guard let http = resp as? HTTPURLResponse else {
                throw PrefsError.invalidResponse
            }
            switch http.statusCode {
            case 200..<300:
                guard let obj = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
                      let rawPrefs = obj["prefs"] as? [String: [String: Double]] else {
                    throw PrefsError.decodingFailed
                }
                return UserPrefs.from(rawPrefs)
            case 400:
                throw PrefsError.invalidWeights
            case 401, 403:
                throw PrefsError.unauthorized
            case 503:
                throw PrefsError.unavailable
            default:
                throw PrefsError.serverError(status: http.statusCode)
            }
        } catch let err as PrefsError {
            throw err
        } catch {
            throw PrefsError.transport(underlying: error.localizedDescription)
        }
    }
}

// MARK: - UserPrefs data type

/// Per-task weight overrides. Empty `overrides` means "use task defaults
/// for everything". Mirrors the backend's `UserPrefs` (frozen dataclass).
/// Per-task weight overrides + per-task model pins.
///
/// v3 introduced `overrides` (per-task weights). v6 added `modelOverrides`
/// (per-task model pinning — user can lock to a specific model instead of
/// trusting the auto-router's pick). Both default to empty — no behavior
/// change for users who haven't set anything.
///
/// Mirrors the backend's `UserPrefs` dataclass. Wire format (v6):
/// `{overrides: {task: {quality, latency, cost}, ...},
///   model_overrides: {task: model_id, ...}}`
struct UserPrefs: Equatable, Codable, Sendable {
    /// Keyed by task rawValue (e.g. "ptt_response"), value is the weights.
    var overrides: [String: TaskWeights]
    /// Keyed by task rawValue, value is the pinned model ID (v6).
    /// Empty means "let the auto-router choose".
    var modelOverrides: [String: String]

    init(overrides: [String: TaskWeights] = [:], modelOverrides: [String: String] = [:]) {
        self.overrides = overrides
        self.modelOverrides = modelOverrides
    }

    static let empty = UserPrefs(overrides: [:], modelOverrides: [:])

    /// Decode from the backend's wire format (v6 nested).
    /// Backward-compat: accepts the legacy v3 flat format
    /// (`{task: {quality, latency, cost}}` — top-level IS overrides)
    /// when no wrapper keys are present.
    ///
    /// Unknown / non-numeric fields are dropped (defensive — backend validates).
    static func from(_ raw: [String: Any]) -> UserPrefs {
        let isLegacyFormat = !raw.keys.contains("overrides")
            && !raw.keys.contains("model_overrides")

        if isLegacyFormat {
            // Legacy: top-level IS the overrides dict.
            var overrides: [String: TaskWeights] = [:]
            for (task, value) in raw {
                guard let fields = value as? [String: Double] else { continue }
                if let weights = TaskWeights.fromRaw(fields) {
                    overrides[task] = weights
                }
            }
            return UserPrefs(overrides: overrides, modelOverrides: [:])
        }

        // New v6 format. Each field is optional (sparse / partial).
        var overrides: [String: TaskWeights] = [:]
        var modelOverrides: [String: String] = [:]

        if let rawOverrides = raw["overrides"] as? [String: [String: Double]] {
            for (task, fields) in rawOverrides {
                if let weights = TaskWeights.fromRaw(fields) {
                    overrides[task] = weights
                }
            }
        }
        if let rawModelOverrides = raw["model_overrides"] as? [String: String] {
            modelOverrides = rawModelOverrides
        }

        return UserPrefs(overrides: overrides, modelOverrides: modelOverrides)
    }

    /// Encode to the backend's wire format (v6 nested). Always includes both
    /// keys (even when empty) for forward-compat.
    ///
    /// Return type is `[String: Any]` because the inner values are mixed
    /// (`[String: Double]` for overrides, `String` for model IDs). The single
    /// caller (`save(prefs:)`) feeds the result directly to `JSONSerialization`,
    /// which accepts the loose `Any` shape.
    func toRawDict() -> [String: Any] {
        return [
            "overrides": overrides.mapValues { $0.toRawDict() },
            "model_overrides": modelOverrides,
        ]
    }
}

// MARK: - TaskWeights data type

/// Per-task weights (quality/latency/cost). Mirrors backend's `TaskWeights`:
/// each value in [0.0, 1.0], they must sum to 1.0 (tolerance 1e-3).
struct TaskWeights: Equatable, Codable, Sendable {
    var quality: Double
    var latency: Double
    var cost: Double

    /// Construct with validation. Throws if weights are out of [0, 1] or don't sum to 1.0.
    init(quality: Double, latency: Double, cost: Double) throws {
        try Self.validate(quality: quality, latency: latency, cost: cost)
        self.quality = quality
        self.latency = latency
        self.cost = cost
    }

    /// Unchecked initializer for trust-but-verify callers (deserialization
    /// from the backend, where validation already happened, and the
    /// `WeightSlider` auto-rebalance which is guaranteed-correct by
    /// construction — see `TaskWeights.fromUnchecked`).
    init(unchecked quality: Double, latency: Double, cost: Double) {
        self.quality = quality
        self.latency = latency
        self.cost = cost
    }

    static let balanced = try! TaskWeights(quality: 1.0 / 3.0, latency: 1.0 / 3.0, cost: 1.0 / 3.0)

    static func validate(quality: Double, latency: Double, cost: Double) throws {
        for (label, w) in [("quality", quality), ("latency", latency), ("cost", cost)] {
            guard w.isFinite else {
                throw PrefsError.invalidWeight(reason: "\(label) must be finite, got \(w)")
            }
            guard w >= 0.0 && w <= 1.0 else {
                throw PrefsError.invalidWeight(reason: "\(label) must be in [0.0, 1.0], got \(w)")
            }
        }
        let sum = quality + latency + cost
        if abs(sum - 1.0) > 1e-3 {
            throw PrefsError.invalidWeight(reason: "weights must sum to 1.0, got \(sum)")
        }
    }

    /// True if `self` equals `other` within `1e-3` tolerance on every component.
    /// (Floating-point equality with tolerance — strict equality would be flaky
    /// across server/client arithmetic paths.)
    func approximatelyEquals(_ other: TaskWeights, tolerance: Double = 1e-3) -> Bool {
        abs(quality - other.quality) <= tolerance
            && abs(latency - other.latency) <= tolerance
            && abs(cost - other.cost) <= tolerance
    }

    /// Decode from raw `{quality, latency, cost}` double map. Returns nil
    /// if any required field is missing or the weights fail validation.
    static func fromRaw(_ fields: [String: Double]) -> TaskWeights? {
        guard let q = fields["quality"],
              let l = fields["latency"],
              let c = fields["cost"]
        else { return nil }
        do {
            return try TaskWeights(quality: q, latency: l, cost: c)
        } catch {
            return nil
        }
    }

    func toRawDict() -> [String: Double] {
        ["quality": quality, "latency": latency, "cost": cost]
    }

    /// Construct `TaskWeights` without validation, normalizing so the sum is
    /// exactly 1.0. Used by the auto-rebalance math in `WeightSlider`, which
    /// is guaranteed-correct by construction (it computes the new value of
    /// the OTHER two axes from the changed axis and the original total, so
    /// the sum is always 1.0 modulo floating-point error). The normalize
    /// step here absorbs that error.
    ///
    /// Do NOT use this from untrusted input — prefer the throwing `init`.
    static func fromUnchecked(quality: Double, latency: Double, cost: Double) -> TaskWeights {
        let sum = quality + latency + cost
        if abs(sum - 1.0) < 1e-9 {
            return TaskWeights(unchecked: quality, latency: latency, cost: cost)
        }
        // Normalize: scale all three so sum = 1.0 exactly.
        let scale = sum > 1e-9 ? 1.0 / sum : 1.0 / 3.0
        return TaskWeights(unchecked: quality * scale, latency: latency * scale, cost: cost * scale)
    }
}

// MARK: - PrefsError

/// Errors from `UserPrefsClient.fetch()` / `.save(prefs:)`.
/// Conforms to Equatable for test assertions.
enum PrefsError: Error, Equatable {
    /// Base URL is malformed.
    case invalidURL(base: String)
    /// HTTP response wasn't an HTTPURLResponse.
    case invalidResponse
    /// Response body wasn't decodable as `{prefs: ...}`.
    case decodingFailed
    /// HTTP 401/403.
    case unauthorized
    /// HTTP 400 (server-side validation rejected the weights).
    case invalidWeights
    /// HTTP 503 (server temporarily unavailable).
    case unavailable
    /// Any other non-2xx.
    case serverError(status: Int)
    /// Underlying transport error (network down, timeout, DNS, etc.).
    case transport(underlying: String)
    /// Local validation rejected the weights (sum != 1.0, out of [0,1], NaN).
    case invalidWeight(reason: String)

    /// User-facing description for the Settings → Auto-router error banner.
    /// Kept here (not on the view) so it's testable in isolation and so all
    /// callers show consistent messaging.
    var userMessage: String {
        switch self {
        case .unauthorized:
            return "Sign in to save preferences."
        case .invalidWeights:
            return "Server rejected the weight values. Try adjusting the sliders."
        case .invalidWeight:
            return "These weight values are invalid. Try adjusting the sliders."
        case .unavailable:
            return "Server is temporarily unavailable. Your changes are still on this screen."
        case .transport:
            return "Network error. Your changes are still on this screen."
        case .invalidURL:
            return "Auto-router URL is misconfigured. Please report this bug."
        case .invalidResponse:
            return "Server returned an unexpected response."
        case .decodingFailed:
            return "Couldn't read the server response. Please try again."
        case .serverError(let status):
            return "Server error (\(status)). Please try again."
        }
    }
}
