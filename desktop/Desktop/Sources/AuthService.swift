import Foundation
@preconcurrency import FirebaseAuth
import CryptoKit
import AppKit
import AuthenticationServices
import Sentry

@MainActor
class AuthService {
    static let shared = AuthService()

    // Use AuthState for UI updates - it's a pure Swift ObservableObject
    // that doesn't reference Firebase types at the class level
    private var authState: AuthState { AuthState.shared }

    var isSignedIn: Bool {
        get { authState.isSignedIn }
        set { authState.isSignedIn = newValue }
    }
    var isLoading: Bool {
        get { authState.isLoading }
        set { authState.isLoading = newValue }
    }
    var error: String? {
        get { authState.error }
        set { authState.error = newValue }
    }

    private var authStateHandle: AuthStateDidChangeListenerHandle?
    private var isConfigured: Bool = false

    // OAuth state for CSRF protection
    private var pendingOAuthState: String?
    private var oauthContinuation: CheckedContinuation<(code: String, state: String), Error>?

    // Native Apple Sign In
    private var currentNonce: String?
    private var appleSignInDelegate: AppleSignInDelegate?

    // API Configuration
    // Production: Cloud Run backend
    private let apiBaseURL: String = "https://omi-desktop-auth-208440318997.us-central1.run.app/"
    private var redirectURI: String {
        return "\(urlScheme)://auth/callback"
    }

    private var urlScheme: String {
        if let urlTypes = Bundle.main.infoDictionary?["CFBundleURLTypes"] as? [[String: Any]],
           let firstType = urlTypes.first,
           let schemes = firstType["CFBundleURLSchemes"] as? [String],
           let scheme = schemes.first {
            return scheme
        }
        return "omi-computer"
    }

    // UserDefaults keys for auth persistence (dev builds with ad-hoc signing)
    private let kAuthIsSignedIn = "auth_isSignedIn"
    private let kAuthUserEmail = "auth_userEmail"
    private let kAuthUserId = "auth_userId"
    private let kAuthGivenName = "auth_givenName"
    private let kAuthFamilyName = "auth_familyName"
    private let kAuthIdToken = "auth_idToken"
    private let kAuthRefreshToken = "auth_refreshToken"
    private let kAuthTokenExpiry = "auth_tokenExpiry"
    private let kAuthTokenUserId = "auth_tokenUserId"  // User ID that owns the stored token

    // Firebase Web API key (from GoogleService-Info.plist)
    private let firebaseApiKey = "AIzaSyD9dzBdglc7IO9pPDIOvqnCoTis_xKkkC8"

    // MARK: - User Name Properties

    /// Get the user's given name (first name)
    var givenName: String {
        get { UserDefaults.standard.string(forKey: kAuthGivenName) ?? "" }
        set { UserDefaults.standard.set(newValue, forKey: kAuthGivenName) }
    }

    /// Get the user's family name (last name)
    var familyName: String {
        get { UserDefaults.standard.string(forKey: kAuthFamilyName) ?? "" }
        set { UserDefaults.standard.set(newValue, forKey: kAuthFamilyName) }
    }

    /// Get the user's full display name
    var displayName: String {
        let given = givenName
        let family = familyName
        if !given.isEmpty && !family.isEmpty {
            return "\(given) \(family)"
        } else if !given.isEmpty {
            return given
        } else if !family.isEmpty {
            return family
        }
        return ""
    }

    init() {
        // Initialize without super
    }

    // MARK: - Configuration (call after FirebaseApp.configure())

    func configure() {
        guard !isConfigured else { return }
        isConfigured = true
        restoreAuthState()
        setupAuthStateListener()

        // Timeout: if auth isn't restored within 5 seconds, stop showing loading
        DispatchQueue.main.asyncAfter(deadline: .now() + 5.0) {
            if AuthState.shared.isRestoringAuth {
                NSLog("OMI AUTH: Auth restore timed out after 5s, clearing loading state")
                AuthState.shared.isRestoringAuth = false
            }
        }
    }

    // MARK: - Auth Persistence (UserDefaults for dev builds)

    private func saveAuthState(isSignedIn: Bool, email: String?, userId: String?) {
        UserDefaults.standard.set(isSignedIn, forKey: kAuthIsSignedIn)
        UserDefaults.standard.set(email, forKey: kAuthUserEmail)
        UserDefaults.standard.set(userId, forKey: kAuthUserId)
        UserDefaults.standard.synchronize()  // Force flush before process can be killed
        NSLog("OMI AUTH: Saved auth state - signedIn: %@, email: %@", isSignedIn ? "true" : "false", email ?? "nil")
    }

    private func restoreAuthState() {
        // Check if we have a saved auth state
        let savedSignedIn = UserDefaults.standard.bool(forKey: kAuthIsSignedIn)
        let savedEmail = UserDefaults.standard.string(forKey: kAuthUserEmail)

        NSLog("OMI AUTH: Checking saved auth state - savedSignedIn: %@, savedEmail: %@",
              savedSignedIn ? "true" : "false", savedEmail ?? "nil")

        // Set auth state synchronously (we're already on main thread from configure()).
        // Using DispatchQueue.main.async here would defer to the next run-loop tick,
        // creating a race window where the Firebase auth state listener can fire first
        // with user=nil and flip isSignedIn to false before we restore it.
        if savedSignedIn {
            // Check if Firebase also has a current user (session might still be valid)
            if let currentUser = Auth.auth().currentUser {
                NSLog("OMI AUTH: Restored auth state from Firebase - uid: %@", currentUser.uid)
                self.isSignedIn = true
                AuthState.shared.userEmail = currentUser.email ?? savedEmail
                AuthState.shared.isRestoringAuth = false
                self.loadNameFromFirebaseIfNeeded()
            } else {
                // Firebase doesn't have user, but we have saved state
                // This can happen with ad-hoc signing where Keychain doesn't persist
                NSLog("OMI AUTH: Restored auth state from UserDefaults (Firebase session expired)")

                // Migration: Fix empty userId by extracting from stored idToken
                let savedUserId = UserDefaults.standard.string(forKey: kAuthUserId) ?? ""
                if savedUserId.isEmpty, let storedToken = storedIdToken {
                    if let payload = decodeJWT(storedToken),
                       let userId = payload["user_id"] as? String ?? payload["sub"] as? String {
                        NSLog("OMI AUTH: Migrating empty userId - extracted from JWT: %@", userId)
                        UserDefaults.standard.set(userId, forKey: kAuthUserId)
                    }
                }

                self.isSignedIn = true
                AuthState.shared.userEmail = savedEmail
                AuthState.shared.isRestoringAuth = false
            }
        } else {
            NSLog("OMI AUTH: No saved auth state found")
            AuthState.shared.isRestoringAuth = false
        }
    }

    // MARK: - Auth State Listener

    private func setupAuthStateListener() {
        authStateHandle = Auth.auth().addStateDidChangeListener { [weak self] _, user in
            Task { @MainActor in
                if user != nil {
                    // Firebase has a user - trust it
                    log("AUTH_LISTENER: Firebase user present (uid=\(user?.uid ?? "nil")), setting isSignedIn=true")
                    self?.isSignedIn = true
                    AuthState.shared.userEmail = user?.email
                    AuthState.shared.isRestoringAuth = false
                    self?.saveAuthState(isSignedIn: true, email: user?.email, userId: user?.uid)
                    // Load name from Firebase Auth displayName if we don't have it locally
                    self?.loadNameFromFirebaseIfNeeded()
                    // Sync assistant settings from backend (fire-and-forget)
                    Task { await SettingsSyncManager.shared.syncFromServer() }
                } else {
                    // Firebase has no user - check if we have a saved session (for dev builds where Keychain doesn't persist)
                    let savedSignedIn = UserDefaults.standard.bool(forKey: self?.kAuthIsSignedIn ?? "")
                    log("AUTH_LISTENER: Firebase user nil, savedSignedIn=\(savedSignedIn), currentIsSignedIn=\(self?.isSignedIn ?? false)")
                    if !savedSignedIn {
                        // No saved session either - user is truly signed out
                        log("AUTH_LISTENER: No saved session - setting isSignedIn=false")
                        self?.isSignedIn = false
                        AuthState.shared.userEmail = nil
                        AuthState.shared.isRestoringAuth = false
                    } else {
                        log("AUTH_LISTENER: Keeping saved session (not overriding isSignedIn)")
                    }
                }
            }
        }
    }

    // MARK: - Sign in with Apple (Web OAuth Flow)

    @MainActor
    func signInWithApple() async throws {
        try await signIn(provider: "apple")
    }

    // MARK: - Sign in with Google (Web OAuth Flow)

    @MainActor
    func signInWithGoogle() async throws {
        try await signIn(provider: "google")
    }

    // MARK: - Generic OAuth Sign In

    @MainActor
    private func signIn(provider: String) async throws {
        // Guard against double sign-in (e.g., rapid button clicks before UI updates)
        guard !isLoading else {
            NSLog("OMI AUTH: Sign in already in progress, ignoring duplicate request")
            return
        }

        NSLog("OMI AUTH: Starting Sign in with %@ (Web OAuth)", provider)
        isLoading = true
        error = nil

        // Track sign-in started
        AnalyticsManager.shared.signInStarted(provider: provider)

        defer { isLoading = false }

        do {
            // Step 1: Generate state for CSRF protection
            let state = generateState()
            pendingOAuthState = state
            NSLog("OMI AUTH: Generated OAuth state")

            // Step 2: Build authorization URL
            let authURL = buildAuthorizationURL(provider: provider, state: state)
            NSLog("OMI AUTH: Opening browser for authentication")

            // Step 3: Open browser for authentication
            guard let url = URL(string: authURL) else {
                throw AuthError.invalidURL
            }
            NSWorkspace.shared.open(url)

            // Step 4: Wait for callback with authorization code
            NSLog("OMI AUTH: Waiting for OAuth callback...")
            let (code, returnedState) = try await waitForOAuthCallback()

            // Step 5: Verify state matches
            guard returnedState == state else {
                NSLog("OMI AUTH: State mismatch - potential CSRF attack")
                throw AuthError.stateMismatch
            }
            NSLog("OMI AUTH: Received valid authorization code")

            // Step 6: Exchange code for custom token and user info
            NSLog("OMI AUTH: Exchanging code for Firebase token...")
            let tokenResult = try await exchangeCodeForToken(code: code)
            NSLog("OMI AUTH: Got Firebase custom token")

            // Save user info from OAuth response immediately (before Firebase sign-in)
            // This ensures we have the name even if Firebase session doesn't persist
            if let extractedGivenName = tokenResult.givenName, !extractedGivenName.isEmpty {
                givenName = extractedGivenName
                familyName = tokenResult.familyName ?? ""
                NSLog("OMI AUTH: Saved name from OAuth: %@ %@", givenName, familyName)
            }
            if let extractedEmail = tokenResult.email {
                AuthState.shared.userEmail = extractedEmail
            }

            // Step 7: Exchange custom token for ID token via REST API
            // This bypasses keychain issues with Firebase SDK on dev builds
            NSLog("OMI AUTH: Exchanging custom token for ID token via REST API...")
            let firebaseTokens = try await exchangeCustomTokenForIdToken(customToken: tokenResult.customToken)
            NSLog("OMI AUTH: Got Firebase ID token via REST API")

            // Store tokens for API calls (include userId to validate token ownership on retrieval)
            saveTokens(idToken: firebaseTokens.idToken, refreshToken: firebaseTokens.refreshToken, expiresIn: firebaseTokens.expiresIn, userId: firebaseTokens.localId)

            // Also try Firebase SDK sign-in (best effort for other Firebase features)
            do {
                let authResult = try await Auth.auth().signIn(withCustomToken: tokenResult.customToken)
                NSLog("OMI AUTH: Firebase SDK sign-in SUCCESS - uid: %@", authResult.user.uid)
            } catch let firebaseError as NSError {
                // Keychain errors are expected on dev builds - we have REST API tokens as fallback
                NSLog("OMI AUTH: Firebase SDK sign-in failed (using REST API tokens): %@", firebaseError.localizedDescription)
            }

            isSignedIn = true

            // Save auth state immediately
            let userId = firebaseTokens.localId
            saveAuthState(isSignedIn: true, email: tokenResult.email, userId: userId)

            // Try to load name from Firebase (as backup if OAuth didn't provide it)
            if givenName.isEmpty {
                loadNameFromFirebaseIfNeeded()
            }

            // Identify user first, then track sign-in completed
            // (identify must happen before events for PostHog person profiles to work)
            AnalyticsManager.shared.identify()
            AnalyticsManager.shared.signInCompleted(provider: provider)

            // Set Sentry user context for error tracking (skip in dev builds)
            if !AnalyticsManager.isDevBuild {
                let sentryUser = User(userId: userId)
                sentryUser.email = tokenResult.email
                sentryUser.username = displayName.isEmpty ? nil : displayName
                SentrySDK.setUser(sentryUser)
            }

            NSLog("OMI AUTH: Sign in complete!")

            // Fetch conversations after successful sign-in
            fetchConversations()

        } catch {
            NSLog("OMI AUTH: Error during sign in: %@", error.localizedDescription)
            AnalyticsManager.shared.signInFailed(provider: provider, error: error.localizedDescription)
            self.error = error.localizedDescription
            throw error
        }
    }

    // MARK: - OAuth URL Building

    private func buildAuthorizationURL(provider: String, state: String) -> String {
        let encodedRedirectURI = redirectURI.addingPercentEncoding(withAllowedCharacters: .urlQueryAllowed) ?? redirectURI
        return "\(apiBaseURL)v1/auth/authorize?provider=\(provider)&redirect_uri=\(encodedRedirectURI)&state=\(state)"
    }

    // MARK: - OAuth Callback Handling

    private func waitForOAuthCallback() async throws -> (code: String, state: String) {
        try await withCheckedThrowingContinuation { continuation in
            self.oauthContinuation = continuation

            // Set a timeout
            Task {
                try await Task.sleep(nanoseconds: 5 * 60 * 1_000_000_000) // 5 minutes
                if self.oauthContinuation != nil {
                    self.oauthContinuation?.resume(throwing: AuthError.timeout)
                    self.oauthContinuation = nil
                }
            }
        }
    }

    /// Called by AppDelegate when the app receives an OAuth callback URL
    @MainActor
    func handleOAuthCallback(url: URL) {
        NSLog("OMI AUTH: Received OAuth callback: %@", url.absoluteString)

        guard let components = URLComponents(url: url, resolvingAgainstBaseURL: false) else {
            NSLog("OMI AUTH: Failed to parse callback URL")
            oauthContinuation?.resume(throwing: AuthError.invalidCallback)
            oauthContinuation = nil
            return
        }

        // Check if this is our auth callback
        guard url.scheme == urlScheme && url.host == "auth" && url.path == "/callback" else {
            NSLog("OMI AUTH: Not an auth callback URL")
            return
        }

        let queryItems = components.queryItems ?? []
        let code = queryItems.first(where: { $0.name == "code" })?.value
        let state = queryItems.first(where: { $0.name == "state" })?.value
        let error = queryItems.first(where: { $0.name == "error" })?.value

        if let error = error {
            NSLog("OMI AUTH: OAuth error: %@", error)
            oauthContinuation?.resume(throwing: AuthError.oauthError(error))
            oauthContinuation = nil
            return
        }

        guard let code = code, let state = state else {
            NSLog("OMI AUTH: Missing code or state in callback")
            oauthContinuation?.resume(throwing: AuthError.missingCodeOrState)
            oauthContinuation = nil
            return
        }

        NSLog("OMI AUTH: Successfully extracted code and state from callback")
        oauthContinuation?.resume(returning: (code: code, state: state))
        oauthContinuation = nil
    }

    // MARK: - Token Exchange

    /// Response from token exchange containing custom token and user info
    struct TokenExchangeResult {
        let customToken: String
        let givenName: String?
        let familyName: String?
        let email: String?
    }

    private func exchangeCodeForToken(code: String) async throws -> TokenExchangeResult {
        guard let url = URL(string: "\(apiBaseURL)v1/auth/token") else {
            throw AuthError.invalidURL
        }

        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/x-www-form-urlencoded", forHTTPHeaderField: "Content-Type")

        let bodyParams = [
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirectURI,
            "use_custom_token": "true"
        ]

        let bodyString = bodyParams
            .map { "\($0.key)=\($0.value.addingPercentEncoding(withAllowedCharacters: .urlQueryAllowed) ?? $0.value)" }
            .joined(separator: "&")

        request.httpBody = bodyString.data(using: .utf8)

        NSLog("OMI AUTH: Sending token exchange request...")
        let (data, response) = try await URLSession.shared.data(for: request)

        guard let httpResponse = response as? HTTPURLResponse else {
            throw AuthError.invalidResponse
        }

        NSLog("OMI AUTH: Token exchange response status: %d", httpResponse.statusCode)

        guard httpResponse.statusCode == 200 else {
            let responseBody = String(data: data, encoding: .utf8) ?? "unknown"
            NSLog("OMI AUTH: Token exchange failed: %@", responseBody)
            throw AuthError.tokenExchangeFailed(httpResponse.statusCode)
        }

        // Parse response
        guard let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any] else {
            throw AuthError.invalidResponse
        }

        // Get custom token
        guard let customToken = json["custom_token"] as? String else {
            NSLog("OMI AUTH: No custom_token in response")
            throw AuthError.missingCustomToken
        }

        // Extract user info from id_token (JWT)
        var extractedGivenName: String?
        var extractedFamilyName: String?
        var extractedEmail: String?

        if let idToken = json["id_token"] as? String {
            if let userInfo = decodeJWT(idToken) {
                extractedGivenName = userInfo["given_name"] as? String
                extractedFamilyName = userInfo["family_name"] as? String
                extractedEmail = userInfo["email"] as? String

                // Fall back to "name" field if given_name not available
                if extractedGivenName == nil, let fullName = userInfo["name"] as? String {
                    let parts = fullName.split(separator: " ", maxSplits: 1)
                    extractedGivenName = parts.first.map(String.init)
                    extractedFamilyName = parts.count > 1 ? String(parts[1]) : nil
                }

                NSLog("OMI AUTH: Extracted from id_token - name: %@ %@, email: %@",
                      extractedGivenName ?? "(none)",
                      extractedFamilyName ?? "",
                      extractedEmail ?? "(none)")
            }
        }

        return TokenExchangeResult(
            customToken: customToken,
            givenName: extractedGivenName,
            familyName: extractedFamilyName,
            email: extractedEmail
        )
    }

    /// Decode a JWT and return the payload as a dictionary
    private func decodeJWT(_ jwt: String) -> [String: Any]? {
        let parts = jwt.split(separator: ".")
        guard parts.count >= 2 else { return nil }

        // JWT payload is the second part, base64url encoded
        var base64 = String(parts[1])
            .replacingOccurrences(of: "-", with: "+")
            .replacingOccurrences(of: "_", with: "/")

        // Pad to multiple of 4
        while base64.count % 4 != 0 {
            base64 += "="
        }

        guard let data = Data(base64Encoded: base64),
              let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any] else {
            return nil
        }

        return json
    }

    // MARK: - User Name Management

    /// Update the user's given name (stores locally and optionally updates Firebase)
    @MainActor
    func updateGivenName(_ fullName: String) async {
        let nameParts = fullName.trimmingCharacters(in: .whitespaces).split(separator: " ", maxSplits: 1)
        let newGivenName = nameParts.first.map(String.init) ?? fullName.trimmingCharacters(in: .whitespaces)
        let newFamilyName = nameParts.count > 1 ? String(nameParts[1]) : ""

        // Save locally
        givenName = newGivenName
        familyName = newFamilyName
        NSLog("OMI AUTH: Updated name locally - given: %@, family: %@", newGivenName, newFamilyName)

        // Try to update Firebase profile (best effort)
        // Skip during impersonation to avoid overwriting the target user's display name
        let isImpersonating = UserDefaults.standard.bool(forKey: "auth_isImpersonating")
        if isImpersonating {
            NSLog("OMI AUTH: Skipping Firebase displayName update (impersonation mode)")
        } else if let user = Auth.auth().currentUser {
            do {
                let changeRequest = user.createProfileChangeRequest()
                changeRequest.displayName = fullName.trimmingCharacters(in: .whitespaces)
                try await changeRequest.commitChanges()
                NSLog("OMI AUTH: Updated Firebase displayName to: %@", fullName)
            } catch {
                NSLog("OMI AUTH: Failed to update Firebase displayName (non-fatal): %@", error.localizedDescription)
            }
        }
    }

    /// Try to get name from Firebase user (after OAuth sign-in)
    func getNameFromFirebase() -> String? {
        if let displayName = Auth.auth().currentUser?.displayName, !displayName.isEmpty {
            return displayName
        }
        return nil
    }

    /// Load name from Firebase if local name is empty
    func loadNameFromFirebaseIfNeeded() {
        if givenName.isEmpty, let firebaseName = getNameFromFirebase() {
            let nameParts = firebaseName.split(separator: " ", maxSplits: 1)
            givenName = nameParts.first.map(String.init) ?? firebaseName
            familyName = nameParts.count > 1 ? String(nameParts[1]) : ""
            NSLog("OMI AUTH: Loaded name from Firebase - given: %@, family: %@", givenName, familyName)
        }
    }

    // MARK: - Token Storage

    private func saveTokens(idToken: String, refreshToken: String, expiresIn: Int, userId: String) {
        UserDefaults.standard.set(idToken, forKey: kAuthIdToken)
        UserDefaults.standard.set(refreshToken, forKey: kAuthRefreshToken)
        // Store expiry time (current time + expiresIn seconds, minus 5 min buffer)
        let expiryTime = Date().addingTimeInterval(TimeInterval(expiresIn - 300))
        UserDefaults.standard.set(expiryTime.timeIntervalSince1970, forKey: kAuthTokenExpiry)
        // Store the user ID that owns these tokens (for validation on retrieval)
        UserDefaults.standard.set(userId, forKey: kAuthTokenUserId)
        NSLog("OMI AUTH: Saved tokens for user %@, expires at %@", userId, expiryTime.description)
    }

    private func clearTokens() {
        UserDefaults.standard.removeObject(forKey: kAuthIdToken)
        UserDefaults.standard.removeObject(forKey: kAuthRefreshToken)
        UserDefaults.standard.removeObject(forKey: kAuthTokenExpiry)
        UserDefaults.standard.removeObject(forKey: kAuthTokenUserId)
        NSLog("OMI AUTH: Cleared all tokens")
    }

    private var storedIdToken: String? {
        UserDefaults.standard.string(forKey: kAuthIdToken)
    }

    private var storedRefreshToken: String? {
        UserDefaults.standard.string(forKey: kAuthRefreshToken)
    }

    private var storedTokenUserId: String? {
        UserDefaults.standard.string(forKey: kAuthTokenUserId)
    }

    private var isTokenExpired: Bool {
        let expiryTime = UserDefaults.standard.double(forKey: kAuthTokenExpiry)
        guard expiryTime > 0 else { return true }
        return Date().timeIntervalSince1970 > expiryTime
    }

    // MARK: - Firebase REST API Token Exchange

    struct FirebaseTokenResult {
        let idToken: String
        let refreshToken: String
        let expiresIn: Int
        let localId: String
    }

    /// Exchange custom token for ID token using Firebase REST API
    private func exchangeCustomTokenForIdToken(customToken: String) async throws -> FirebaseTokenResult {
        let url = URL(string: "https://identitytoolkit.googleapis.com/v1/accounts:signInWithCustomToken?key=\(firebaseApiKey)")!

        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = try JSONSerialization.data(withJSONObject: [
            "token": customToken,
            "returnSecureToken": true
        ])

        let (data, response) = try await URLSession.shared.data(for: request)

        guard let httpResponse = response as? HTTPURLResponse else {
            throw AuthError.invalidResponse
        }

        guard httpResponse.statusCode == 200 else {
            let errorBody = String(data: data, encoding: .utf8) ?? "unknown"
            NSLog("OMI AUTH: Firebase REST API error: %@", errorBody)
            throw AuthError.tokenExchangeFailed(httpResponse.statusCode)
        }

        guard let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
              let idToken = json["idToken"] as? String,
              let refreshToken = json["refreshToken"] as? String else {
            NSLog("OMI AUTH: Failed to parse Firebase response: %@", String(data: data, encoding: .utf8) ?? "nil")
            throw AuthError.invalidResponse
        }

        // expiresIn can be String or Int
        let expiresIn: Int
        if let expiresInStr = json["expiresIn"] as? String {
            expiresIn = Int(expiresInStr) ?? 3600
        } else if let expiresInInt = json["expiresIn"] as? Int {
            expiresIn = expiresInInt
        } else {
            expiresIn = 3600
        }

        // localId might be missing from REST API response - extract from JWT if needed
        var localId = json["localId"] as? String ?? ""
        if localId.isEmpty {
            // Extract user_id from the JWT token payload
            if let payload = decodeJWT(idToken),
               let userId = payload["user_id"] as? String ?? payload["sub"] as? String {
                localId = userId
                NSLog("OMI AUTH: Extracted user_id from JWT: %@", localId)
            }
        }

        return FirebaseTokenResult(
            idToken: idToken,
            refreshToken: refreshToken,
            expiresIn: expiresIn,
            localId: localId
        )
    }

    /// Refresh the ID token using the refresh token
    private func refreshIdToken() async throws -> String {
        guard let refreshToken = storedRefreshToken else {
            throw AuthError.notSignedIn
        }

        let url = URL(string: "https://securetoken.googleapis.com/v1/token?key=\(firebaseApiKey)")!

        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/x-www-form-urlencoded", forHTTPHeaderField: "Content-Type")
        request.httpBody = "grant_type=refresh_token&refresh_token=\(refreshToken)".data(using: .utf8)

        let (data, response) = try await URLSession.shared.data(for: request)

        guard let httpResponse = response as? HTTPURLResponse else {
            throw AuthError.invalidResponse
        }

        guard httpResponse.statusCode == 200 else {
            let errorBody = String(data: data, encoding: .utf8) ?? "unknown"
            NSLog("OMI AUTH: Token refresh error (HTTP %d): %@", httpResponse.statusCode, errorBody)
            // Only clear tokens for definitive auth failures (invalid/revoked refresh token).
            // Transient errors (network issues, 500s) should not destroy the session.
            let isDefinitiveAuthFailure = errorBody.contains("TOKEN_EXPIRED")
                || errorBody.contains("INVALID_REFRESH_TOKEN")
                || errorBody.contains("USER_NOT_FOUND")
                || errorBody.contains("USER_DISABLED")
                || httpResponse.statusCode == 400
            if isDefinitiveAuthFailure {
                NSLog("OMI AUTH: Definitive auth failure - clearing tokens")
                clearTokens()
            }
            throw AuthError.notSignedIn
        }

        guard let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
              let newIdToken = json["id_token"] as? String,
              let newRefreshToken = json["refresh_token"] as? String,
              let expiresIn = json["expires_in"] as? String else {
            throw AuthError.invalidResponse
        }

        // Get user ID from response (Firebase returns it as "user_id")
        // Fall back to existing stored token user ID if not in response
        let userId = (json["user_id"] as? String) ?? storedTokenUserId ?? ""

        // Save new tokens with user ID
        saveTokens(idToken: newIdToken, refreshToken: newRefreshToken, expiresIn: Int(expiresIn) ?? 3600, userId: userId)
        NSLog("OMI AUTH: Refreshed ID token successfully for user %@", userId)

        return newIdToken
    }

    // MARK: - Get ID Token (for API calls)

    func getIdToken(forceRefresh: Bool = false) async throws -> String {
        // Get the expected user ID (the currently signed-in user)
        let expectedUserId = UserDefaults.standard.string(forKey: kAuthUserId)

        // First try: Use stored token if valid AND belongs to the current user
        if !forceRefresh, let token = storedIdToken, !isTokenExpired {
            // Validate token belongs to current user to prevent using stale tokens after account switch
            // Allow tokens without userId (backward compatibility with pre-c052b0b tokens)
            if let tokenUserId = storedTokenUserId {
                if expectedUserId == nil {
                    // expectedUserId missing (migration gap, crash recovery) - trust the token
                    // and backfill the userId so future calls don't hit this path
                    NSLog("OMI AUTH: expectedUserId is nil but token has userId %@ - backfilling", tokenUserId)
                    UserDefaults.standard.set(tokenUserId, forKey: kAuthUserId)
                    return token
                } else if tokenUserId == expectedUserId {
                    return token
                } else {
                    NSLog("OMI AUTH: Stored token user mismatch (token: %@, expected: %@) - clearing stale token",
                          tokenUserId, expectedUserId ?? "nil")
                    clearTokens()
                }
            } else {
                // Old token without userId - allow it (backward compatibility)
                NSLog("OMI AUTH: Using legacy token without userId")
                return token
            }
        }

        // Second try: Refresh using stored refresh token
        // Allow refresh when expectedUserId is nil (token was saved by valid sign-in)
        if let _ = storedRefreshToken {
            let tokenUserId = storedTokenUserId
            let canRefresh = tokenUserId == nil || expectedUserId == nil || tokenUserId == expectedUserId
            if canRefresh {
                do {
                    return try await refreshIdToken()
                } catch {
                    NSLog("OMI AUTH: Token refresh failed: %@", error.localizedDescription)
                }
            }
        }

        // Third try: Use Firebase SDK (only if user matches expected user)
        // This prevents returning a stale user's token during sign-out race conditions
        if let user = Auth.auth().currentUser {
            if expectedUserId == nil || user.uid == expectedUserId {
                if expectedUserId == nil {
                    // Backfill the missing userId
                    NSLog("OMI AUTH: expectedUserId is nil, backfilling from Firebase SDK user %@", user.uid)
                    UserDefaults.standard.set(user.uid, forKey: kAuthUserId)
                }
                let tokenResult = try await user.getIDTokenResult(forcingRefresh: forceRefresh)
                return tokenResult.token
            } else {
                NSLog("OMI AUTH: Firebase SDK user mismatch (firebase: %@, expected: %@) - not using",
                      user.uid, expectedUserId ?? "nil")
            }
        }

        throw AuthError.notSignedIn
    }

    func getAuthHeader() async throws -> String {
        let token = try await getIdToken(forceRefresh: false)
        return "Bearer \(token)"
    }

    // MARK: - Fetch User Conversations

    /// Fetches and logs user conversations (called after sign-in or on startup)
    func fetchConversations() {
        Task {
            do {
                log("Fetching user conversations...")
                let conversations = try await APIClient.shared.getConversations(limit: 10)
                log("Fetched \(conversations.count) conversations")

                for (index, conversation) in conversations.prefix(5).enumerated() {
                    log("[\(index + 1)] \(conversation.structured.emoji) \(conversation.title) (\(conversation.formattedDuration))")
                    if !conversation.overview.isEmpty {
                        let preview = String(conversation.overview.prefix(100))
                        log("    Summary: \(preview)\(conversation.overview.count > 100 ? "..." : "")")
                    }
                }

                if conversations.count > 5 {
                    log("... and \(conversations.count - 5) more conversations")
                }
            } catch {
                logError("Failed to fetch conversations", error: error)
            }
        }
    }

    // MARK: - Sign Out

    func signOut() throws {
        // Track sign out and reset analytics
        AnalyticsManager.shared.signedOut()
        AnalyticsManager.shared.reset()

        // Clear Sentry user context (skip in dev builds)
        if !AnalyticsManager.isDevBuild {
            SentrySDK.setUser(nil)
        }

        try Auth.auth().signOut()
        isSignedIn = false
        // Clear saved auth state and tokens
        saveAuthState(isSignedIn: false, email: nil, userId: nil)
        clearTokens()

        // Close database and invalidate all storage caches so the next sign-in
        // opens a fresh per-user database
        Task {
            await RewindDatabase.shared.close()
            await RewindStorage.shared.reset()
            await TranscriptionStorage.shared.invalidateCache()
            await MemoryStorage.shared.invalidateCache()
            await ActionItemStorage.shared.invalidateCache()
            await ProactiveStorage.shared.invalidateCache()
            await NoteStorage.shared.invalidateCache()
            await AIUserProfileService.shared.invalidateCache()
        }

        // Clear onboarding step/trigger flags but keep hasCompletedOnboarding
        // Permissions are per-app on macOS, so no need to re-show onboarding after logout
        UserDefaults.standard.removeObject(forKey: "onboardingStep")
        UserDefaults.standard.removeObject(forKey: "hasTriggeredNotification")
        UserDefaults.standard.removeObject(forKey: "hasTriggeredAutomation")
        UserDefaults.standard.removeObject(forKey: "hasTriggeredScreenRecording")
        UserDefaults.standard.removeObject(forKey: "hasTriggeredMicrophone")
        UserDefaults.standard.removeObject(forKey: "hasTriggeredSystemAudio")

        NSLog("OMI AUTH: Signed out and cleared saved state + onboarding")
    }

    // MARK: - Helper Methods

    private func generateState() -> String {
        var bytes = [UInt8](repeating: 0, count: 32)
        _ = SecRandomCopyBytes(kSecRandomDefault, bytes.count, &bytes)
        return Data(bytes).base64EncodedString()
            .replacingOccurrences(of: "+", with: "-")
            .replacingOccurrences(of: "/", with: "_")
            .replacingOccurrences(of: "=", with: "")
    }
}

// MARK: - Auth Errors

enum AuthError: LocalizedError {
    case invalidCredential
    case invalidNonce
    case missingToken
    case notSignedIn
    case invalidURL
    case stateMismatch
    case timeout
    case invalidCallback
    case oauthError(String)
    case missingCodeOrState
    case invalidResponse
    case tokenExchangeFailed(Int)
    case missingCustomToken

    var errorDescription: String? {
        switch self {
        case .invalidCredential:
            return "Invalid Apple credential"
        case .invalidNonce:
            return "Invalid nonce - please try again"
        case .missingToken:
            return "Missing identity token from Apple"
        case .notSignedIn:
            return "User is not signed in"
        case .invalidURL:
            return "Invalid authentication URL"
        case .stateMismatch:
            return "Security state mismatch - please try again"
        case .timeout:
            return "Authentication timed out - please try again"
        case .invalidCallback:
            return "Invalid authentication callback"
        case .oauthError(let error):
            return "Authentication error: \(error)"
        case .missingCodeOrState:
            return "Missing authentication code"
        case .invalidResponse:
            return "Invalid server response"
        case .tokenExchangeFailed(let code):
            return "Token exchange failed with status \(code)"
        case .missingCustomToken:
            return "Server did not return authentication token"
        }
    }
}
