import CryptoKit
import Foundation

/// Fetches API keys from the backend at runtime instead of bundling them in the app.
/// Developer overrides (set in Settings) take precedence over backend-provided keys.
///
/// Also hosts the Bring-Your-Own-Key (BYOK) free-plan flow: when the user supplies
/// their own OpenAI, Anthropic, Gemini, and Deepgram keys, the app sends them along
/// with every request and the backend skips subscription billing. Keys live in
/// UserDefaults (reusing the existing dev-override AppStorage pattern); the backend
/// only ever sees SHA-256 fingerprints for state tracking.
///
/// NOTE: Deepgram, Gemini, Anthropic keys are NO LONGER fetched from the backend —
/// they are proxied server-side (issues #5861, #6594).
/// NOTE: ElevenLabs key is NO LONGER fetched — proxied via /v1/tts/synthesize (issue #6622).
/// Firebase and Calendar keys are still served via /v1/config/api-keys.

/// Keys that participate in the BYOK free-plan flow.
enum BYOKProvider: String, CaseIterable {
    case openai
    case anthropic
    case gemini
    case deepgram

    var storageKey: String {
        switch self {
        case .openai: return "dev_openai_api_key"
        case .anthropic: return "dev_anthropic_api_key"
        case .gemini: return "dev_gemini_api_key"
        case .deepgram: return "dev_deepgram_api_key"
        }
    }

    var headerName: String {
        switch self {
        case .openai: return "X-BYOK-OpenAI"
        case .anthropic: return "X-BYOK-Anthropic"
        case .gemini: return "X-BYOK-Gemini"
        case .deepgram: return "X-BYOK-Deepgram"
        }
    }

    var displayName: String {
        switch self {
        case .openai: return "OpenAI"
        case .anthropic: return "Anthropic"
        case .gemini: return "Gemini"
        case .deepgram: return "Deepgram"
        }
    }
}
@MainActor
final class APIKeyService: ObservableObject {
    static let shared = APIKeyService()

    // Backend-provided keys (in-memory only, never persisted to disk)
    @Published private(set) var geminiApiKey: String?
    @Published private(set) var firebaseApiKey: String?
    @Published private(set) var googleCalendarApiKey: String?
    @Published private(set) var isLoaded: Bool = false
    @Published private(set) var loadError: String?

    /// The in-flight fetch task, so callers can await it instead of polling.
    private var fetchTask: Task<Void, Never>?

    /// Start fetching keys in the background. Callers can await via waitForKeys().
    func startFetchingKeys() {
        fetchTask = Task { await self.fetchKeys() }
    }

    /// Wait for keys to be loaded. Returns immediately if already loaded.
    /// If no fetch is in-flight, starts one (handles app-restart-while-signed-in case).
    func waitForKeys() async {
        if isLoaded { return }
        if fetchTask == nil {
            log("APIKeyService: waitForKeys called but no fetch in-flight, starting one")
            fetchTask = Task { await fetchKeys() }
        }
        await fetchTask?.value
    }

    var effectiveGeminiKey: String? {
        nonEmpty(UserDefaults.standard.string(forKey: "dev_gemini_api_key")) ?? geminiApiKey
    }

    var effectiveFirebaseApiKey: String? {
        firebaseApiKey
    }

    var effectiveGoogleCalendarApiKey: String? {
        googleCalendarApiKey
    }

    /// Fetch keys from the backend. Call after Firebase auth is ready.
    func fetchKeys() async {
        loadError = nil

        // Retry up to 3 times with backoff
        for attempt in 1...3 {
            do {
                let keys = try await APIClient.shared.fetchApiKeys()
                self.geminiApiKey = keys.geminiApiKey
                self.firebaseApiKey = keys.firebaseApiKey
                self.googleCalendarApiKey = keys.googleCalendarApiKey
                self.isLoaded = true

                // Set env vars so existing getenv() consumers keep working during transition
                applyToEnvironment()

                log("APIKeyService: Fetched keys from backend (gemini=\(keys.geminiApiKey != nil), firebase=\(keys.firebaseApiKey != nil), calendar=\(keys.googleCalendarApiKey != nil))")
                return
            } catch {
                let delay = pow(2.0, Double(attempt - 1))
                log("APIKeyService: Fetch attempt \(attempt)/3 failed: \(error.localizedDescription), retrying in \(delay)s")
                if attempt < 3 {
                    try? await Task.sleep(nanoseconds: UInt64(delay * 1_000_000_000))
                }
            }
        }

        loadError = "Failed to fetch API keys from backend"
        log("APIKeyService: All fetch attempts failed — features requiring API keys will be unavailable")

        // Still apply env vars from developer overrides if set
        applyToEnvironment()
    }

    /// Clear all keys (e.g. on sign-out)
    func clear() {
        geminiApiKey = nil
        firebaseApiKey = nil
        googleCalendarApiKey = nil
        isLoaded = false
        loadError = nil

        unsetenv("GEMINI_API_KEY")
        // NOTE: Do NOT unset FIREBASE_API_KEY — it's needed for the next sign-in
        // (auth bootstrap requires Firebase key before backend is reachable)
        unsetenv("GOOGLE_CALENDAR_API_KEY")
    }

    /// Push effective keys into the process environment for backward compatibility.
    private func applyToEnvironment() {
        if let key = effectiveGeminiKey {
            setenv("GEMINI_API_KEY", key, 1)
        }
        if let key = effectiveFirebaseApiKey {
            setenv("FIREBASE_API_KEY", key, 1)
        }
        if let key = effectiveGoogleCalendarApiKey {
            setenv("GOOGLE_CALENDAR_API_KEY", key, 1)
        }
    }

    private func nonEmpty(_ s: String?) -> String? {
        guard let s, !s.trimmingCharacters(in: .whitespaces).isEmpty else { return nil }
        return s
    }

    // MARK: - Thread-safe key access (for non-MainActor contexts)
    // These read from UserDefaults (thread-safe) and getenv() (set by applyToEnvironment).
    // Use these from actors, nonisolated inits, and background threads.

    nonisolated static var currentGeminiKey: String? {
        nonEmptyStatic(UserDefaults.standard.string(forKey: "dev_gemini_api_key"))
            ?? (getenv("GEMINI_API_KEY").flatMap { String(validatingUTF8: $0) })
    }

    /// True when the app has enough configuration to start transcription and screen analysis.
    /// In proxy mode (OMI_DESKTOP_API_URL set), no client-side Deepgram/Gemini keys are needed.
    nonisolated static var keysAvailable: Bool {
        getenv("GEMINI_API_KEY") != nil || getenv("OMI_DESKTOP_API_URL") != nil
    }

    private nonisolated static func nonEmptyStatic(_ s: String?) -> String? {
        guard let s, !s.trimmingCharacters(in: .whitespaces).isEmpty else { return nil }
        return s
    }

    // MARK: - BYOK (Bring Your Own Keys) — free plan

    /// Read a BYOK key from UserDefaults. Returns nil if empty/whitespace.
    nonisolated static func byokKey(_ provider: BYOKProvider) -> String? {
        nonEmptyStatic(UserDefaults.standard.string(forKey: provider.storageKey))
    }

    /// True when the user has supplied keys for all four BYOK providers.
    /// The subscription-bypass gate: when this is true, the user is on the free
    /// plan and we attach their keys to every backend request.
    nonisolated static var isByokActive: Bool {
        BYOKProvider.allCases.allSatisfy { byokKey($0) != nil }
    }

    /// SHA-256 fingerprint of a key, used by the backend to detect when the
    /// user rotated their keys without us ever storing the key itself.
    nonisolated static func byokFingerprint(_ key: String) -> String {
        let digest = SHA256.hash(data: Data(key.utf8))
        return digest.map { String(format: "%02x", $0) }.joined()
    }

    /// Map of provider → (key, fingerprint) for every provider the user has configured.
    nonisolated static var byokSnapshot: [BYOKProvider: (key: String, fingerprint: String)] {
        var out: [BYOKProvider: (String, String)] = [:]
        for provider in BYOKProvider.allCases {
            if let key = byokKey(provider) {
                out[provider] = (key, byokFingerprint(key))
            }
        }
        return out
    }
}
