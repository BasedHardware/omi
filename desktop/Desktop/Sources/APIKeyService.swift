import Foundation

/// Fetches API keys from the backend at runtime instead of bundling them in the app.
/// Developer overrides (set in Settings) take precedence over backend-provided keys.
///
/// NOTE: The current desktop app is slopped on security — API keys were hardcoded in
/// Swift source and env files. This service moves secrets server-side via /v1/config/api-keys.
/// Will remove the env-var bridge once all client-side key slop is cleaned up. — CTO
@MainActor
final class APIKeyService: ObservableObject {
    static let shared = APIKeyService()

    // Backend-provided keys (in-memory only, never persisted to disk)
    @Published private(set) var deepgramApiKey: String?
    @Published private(set) var geminiApiKey: String?
    @Published private(set) var anthropicApiKey: String?
    @Published private(set) var firebaseApiKey: String?
    @Published private(set) var googleCalendarApiKey: String?
    @Published private(set) var isLoaded: Bool = false
    @Published private(set) var loadError: String?

    /// Effective key: developer override > backend-provided > nil
    var effectiveDeepgramKey: String? {
        nonEmpty(UserDefaults.standard.string(forKey: "dev_deepgram_api_key")) ?? deepgramApiKey
    }

    var effectiveGeminiKey: String? {
        nonEmpty(UserDefaults.standard.string(forKey: "dev_gemini_api_key")) ?? geminiApiKey
    }

    var effectiveAnthropicKey: String? {
        nonEmpty(UserDefaults.standard.string(forKey: "dev_anthropic_api_key")) ?? anthropicApiKey
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
                self.deepgramApiKey = keys.deepgramApiKey
                self.geminiApiKey = keys.geminiApiKey
                self.anthropicApiKey = keys.anthropicApiKey
                self.firebaseApiKey = keys.firebaseApiKey
                self.googleCalendarApiKey = keys.googleCalendarApiKey
                self.isLoaded = true

                // Set env vars so existing getenv() consumers keep working during transition
                applyToEnvironment()

                log("APIKeyService: Fetched keys from backend (deepgram=\(keys.deepgramApiKey != nil), gemini=\(keys.geminiApiKey != nil), anthropic=\(keys.anthropicApiKey != nil), firebase=\(keys.firebaseApiKey != nil), calendar=\(keys.googleCalendarApiKey != nil))")
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
        deepgramApiKey = nil
        geminiApiKey = nil
        anthropicApiKey = nil
        firebaseApiKey = nil
        googleCalendarApiKey = nil
        isLoaded = false
        loadError = nil

        unsetenv("DEEPGRAM_API_KEY")
        unsetenv("GEMINI_API_KEY")
        unsetenv("ANTHROPIC_API_KEY")
        // NOTE: Do NOT unset FIREBASE_API_KEY — it's needed for the next sign-in
        // (auth bootstrap requires Firebase key before backend is reachable)
        unsetenv("GOOGLE_CALENDAR_API_KEY")
    }

    /// Push effective keys into the process environment for backward compatibility.
    private func applyToEnvironment() {
        if let key = effectiveDeepgramKey {
            setenv("DEEPGRAM_API_KEY", key, 1)
        }
        if let key = effectiveGeminiKey {
            setenv("GEMINI_API_KEY", key, 1)
        }
        if let key = effectiveAnthropicKey {
            setenv("ANTHROPIC_API_KEY", key, 1)
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
}
