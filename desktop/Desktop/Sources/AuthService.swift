import Foundation
@preconcurrency import FirebaseAuth
import CryptoKit
import AppKit
import AuthenticationServices
import Sentry

extension Notification.Name {
    /// Posted by AuthService.signOut() so views can reset @AppStorage-backed properties directly.
    static let userDidSignOut = Notification.Name("com.omi.desktop.userDidSignOut")
}

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
                self.loadNameFromBackendIfNeeded()
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
                    // Load name from backend profile (Firestore), then Firebase Auth as fallback
                    self?.loadNameFromBackendIfNeeded()
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

    // MARK: - Sign in with Apple (Native with Web OAuth Fallback)

    @MainActor
    func signInWithApple() async throws {
        // Use web OAuth directly — native Apple Sign In requires entitlements that
        // don't work reliably across dev/release builds. Web OAuth works everywhere.
        try await signIn(provider: "apple")
    }

    // MARK: - Native Apple Sign In (requires com.apple.developer.applesignin entitlement)

    @MainActor
    private func signInWithAppleNative() async throws {
        NSLog("OMI AUTH: Starting native Apple Sign In")
        isLoading = true
        error = nil
        AnalyticsManager.shared.signInStarted(provider: "apple")
        defer { isLoading = false }

        // Step 1: Generate nonce for security
        let nonce = generateNonce()
        currentNonce = nonce
        let hashedNonce = sha256(nonce)

        // Step 2: Perform native Apple Sign In
        let appleCredential = try await performAppleSignIn(hashedNonce: hashedNonce)
        appleSignInDelegate = nil  // Clean up

        // Step 3: Extract identity token
        guard let identityTokenData = appleCredential.identityToken,
              let identityToken = String(data: identityTokenData, encoding: .utf8) else {
            throw AuthError.missingToken
        }
        NSLog("OMI AUTH: Got Apple identity token")

        // Save user name if provided (Apple only sends name on first sign-in)
        if let fullName = appleCredential.fullName {
            let given = fullName.givenName ?? ""
            let family = fullName.familyName ?? ""
            if !given.isEmpty {
                givenName = given
                familyName = family
                NSLog("OMI AUTH: Saved name from Apple: %@ %@", given, family)
            }
        }
        if let email = appleCredential.email {
            AuthState.shared.userEmail = email
        }

        // Step 4: Sign in with Firebase using Apple credential
        // Use Firebase SDK first (handles native bundle ID audience correctly),
        // fall back to REST API (for web OAuth audience 'me.omi.web')
        NSLog("OMI AUTH: Signing in with Firebase using Apple identity token...")

        let credential = OAuthProvider.credential(providerID: .apple, idToken: identityToken, rawNonce: nonce)
        var userId = ""

        do {
            // Firebase SDK sign-in (works with native bundle ID as token audience)
            let authResult = try await Auth.auth().signIn(with: credential)
            NSLog("OMI AUTH: Firebase SDK sign-in SUCCESS - uid: %@", authResult.user.uid)
            userId = authResult.user.uid

            // Get ID token from Firebase SDK for API calls
            let tokenResult = try await authResult.user.getIDTokenResult()
            let idToken = tokenResult.token
            let refreshToken = authResult.user.refreshToken ?? ""
            let expiresIn = Int(tokenResult.expirationDate.timeIntervalSinceNow)

            saveTokens(idToken: idToken, refreshToken: refreshToken, expiresIn: expiresIn, userId: userId)
        } catch {
            // Fall back to REST API (works when Firebase SDK has keychain issues)
            let nsError = error as NSError
            NSLog("OMI AUTH: Firebase SDK Apple sign-in failed (domain=%@ code=%d): %@", nsError.domain, nsError.code, error.localizedDescription)
            logError("AUTH: Firebase SDK Apple sign-in failed (domain=\(nsError.domain) code=\(nsError.code))", error: error)
            NSLog("OMI AUTH: Falling back to REST API for Apple sign-in...")
            let firebaseTokens = try await signInWithAppleIdentityToken(identityToken: identityToken, nonce: nonce)
            userId = firebaseTokens.localId
            saveTokens(idToken: firebaseTokens.idToken, refreshToken: firebaseTokens.refreshToken, expiresIn: firebaseTokens.expiresIn, userId: userId)
        }

        isSignedIn = true

        // Extract email from identity token if not provided by Apple
        if AuthState.shared.userEmail == nil {
            if let payload = decodeJWT(identityToken),
               let email = payload["email"] as? String {
                AuthState.shared.userEmail = email
            }
        }

        saveAuthState(isSignedIn: true, email: AuthState.shared.userEmail, userId: userId)

        if givenName.isEmpty {
            loadNameFromBackendIfNeeded()
        }

        AnalyticsManager.shared.identify()
        AnalyticsManager.shared.signInCompleted(provider: "apple")

        if !AnalyticsManager.isDevBuild {
            let sentryUser = User(userId: userId)
            sentryUser.email = AuthState.shared.userEmail
            sentryUser.username = displayName.isEmpty ? nil : displayName
            SentrySDK.setUser(sentryUser)
        }

        NSLog("OMI AUTH: Apple Sign in complete!")
        fetchConversations()
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

            // Try to load name from backend profile (Firestore), then Firebase Auth as fallback
            if givenName.isEmpty {
                loadNameFromBackendIfNeeded()
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
            let nsError = error as NSError
            NSLog("OMI AUTH: Error during sign in: %@", error.localizedDescription)
            logError("AUTH: \(provider) web OAuth sign-in failed (domain=\(nsError.domain) code=\(nsError.code))", error: error)
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

    /// Update the user's given name (stores locally, updates Firebase Auth, and syncs to backend profile)
    @MainActor
    func updateGivenName(_ fullName: String) async {
        let trimmedName = fullName.trimmingCharacters(in: .whitespaces)
        let nameParts = trimmedName.split(separator: " ", maxSplits: 1)
        let newGivenName = nameParts.first.map(String.init) ?? trimmedName
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
                changeRequest.displayName = trimmedName
                try await changeRequest.commitChanges()
                NSLog("OMI AUTH: Updated Firebase displayName to: %@", trimmedName)
            } catch {
                NSLog("OMI AUTH: Failed to update Firebase displayName (non-fatal): %@", error.localizedDescription)
            }
        }

        // Also save to backend profile (Firestore) so it persists across sign-in methods
        if !isImpersonating {
            do {
                try await APIClient.shared.updateUserProfile(name: trimmedName)
                NSLog("OMI AUTH: Updated backend profile name to: %@", trimmedName)
            } catch {
                NSLog("OMI AUTH: Failed to update backend profile name (non-fatal): %@", error.localizedDescription)
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

    /// Load name from backend profile (Firestore) first, then fall back to Firebase Auth.
    /// This handles cases like Apple Sign-In where Firebase Auth displayName may be empty
    /// but the user already has a name stored in Firestore from a previous sign-up.
    func loadNameFromBackendIfNeeded() {
        guard givenName.isEmpty else { return }
        Task {
            do {
                let profile = try await APIClient.shared.getUserProfile()
                if let name = profile.name, !name.trimmingCharacters(in: .whitespaces).isEmpty {
                    let nameParts = name.trimmingCharacters(in: .whitespaces).split(separator: " ", maxSplits: 1)
                    await MainActor.run {
                        givenName = nameParts.first.map(String.init) ?? name.trimmingCharacters(in: .whitespaces)
                        familyName = nameParts.count > 1 ? String(nameParts[1]) : ""
                        NSLog("OMI AUTH: Loaded name from backend profile - given: %@, family: %@", givenName, familyName)
                    }
                    return
                }
            } catch {
                NSLog("OMI AUTH: Failed to fetch backend profile for name (non-fatal): %@", error.localizedDescription)
            }
            // Fall back to Firebase Auth displayName
            await MainActor.run {
                loadNameFromFirebaseIfNeeded()
            }
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

        // Stop background services that make API calls before clearing caches
        Task {
            await AgentSyncService.shared.stop()
        }

        // Close database and invalidate all storage caches so the next sign-in
        // opens a fresh per-user database.
        // Capture the current configureGeneration so closeIfStale() can detect if
        // a new sign-in session has already called configure() by the time this runs.
        let closeGeneration = RewindDatabase.configureGeneration
        Task {
            await RewindDatabase.shared.closeIfStale(generation: closeGeneration)
            await RewindIndexer.shared.reset()
            await RewindStorage.shared.reset()
            await TranscriptionStorage.shared.invalidateCache()
            await MemoryStorage.shared.invalidateCache()
            await ActionItemStorage.shared.invalidateCache()
            await ProactiveStorage.shared.invalidateCache()
            await NoteStorage.shared.invalidateCache()
            await AIUserProfileService.shared.invalidateCache()
        }

        // Notify observers (DesktopHomeView) to reset @AppStorage-backed properties directly.
        // Using removeObject() on @AppStorage properties doesn't work because the cached value
        // in AppState (an ObservableObject, not a View) gets written back immediately.
        NotificationCenter.default.post(name: .userDidSignOut, object: nil)

        // Clear non-@AppStorage onboarding keys via UserDefaults (these work fine).
        UserDefaults.standard.removeObject(forKey: "onboardingStep")
        UserDefaults.standard.removeObject(forKey: "hasTriggeredNotification")
        UserDefaults.standard.removeObject(forKey: "hasTriggeredAutomation")
        UserDefaults.standard.removeObject(forKey: "hasTriggeredScreenRecording")
        UserDefaults.standard.removeObject(forKey: "hasTriggeredMicrophone")
        UserDefaults.standard.removeObject(forKey: "hasTriggeredSystemAudio")

        // screenAnalysisEnabled: Don't removeObject here — SettingsSyncManager overwrites
        // it from the server within ~200ms of sign-in. Instead, onboarding force-starts
        // monitoring regardless of this setting.
        // transcriptionEnabled: removeObject works since nothing writes it back.
        UserDefaults.standard.removeObject(forKey: "transcriptionEnabled")

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

    // MARK: - Native Apple Sign In Helpers

    /// Show the native Apple Sign In dialog and return the credential
    private func performAppleSignIn(hashedNonce: String) async throws -> ASAuthorizationAppleIDCredential {
        try await withCheckedThrowingContinuation { continuation in
            let provider = ASAuthorizationAppleIDProvider()
            let request = provider.createRequest()
            request.requestedScopes = [.fullName, .email]
            request.nonce = hashedNonce

            let controller = ASAuthorizationController(authorizationRequests: [request])
            let delegate = AppleSignInDelegate(continuation: continuation)
            self.appleSignInDelegate = delegate  // Keep delegate alive
            controller.delegate = delegate
            controller.presentationContextProvider = delegate
            controller.performRequests()
        }
    }

    /// Sign in with Firebase using an Apple identity token via REST API
    /// This bypasses the backend entirely - Firebase verifies the Apple JWT directly
    private func signInWithAppleIdentityToken(identityToken: String, nonce: String) async throws -> FirebaseTokenResult {
        let url = URL(string: "https://identitytoolkit.googleapis.com/v1/accounts:signInWithIdp?key=\(firebaseApiKey)")!

        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")

        let postBody = "id_token=\(identityToken)&providerId=apple.com&nonce=\(nonce)"
        let body: [String: Any] = [
            "postBody": postBody,
            "requestUri": "http://localhost",
            "returnIdpCredential": true,
            "returnSecureToken": true
        ]

        request.httpBody = try JSONSerialization.data(withJSONObject: body)

        let (data, response) = try await URLSession.shared.data(for: request)

        guard let httpResponse = response as? HTTPURLResponse else {
            throw AuthError.invalidResponse
        }

        guard httpResponse.statusCode == 200 else {
            let errorBody = String(data: data, encoding: .utf8) ?? "unknown"
            NSLog("OMI AUTH: Firebase signInWithIdp error: %@", errorBody)
            throw AuthError.tokenExchangeFailed(httpResponse.statusCode)
        }

        guard let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
              let idToken = json["idToken"] as? String,
              let refreshToken = json["refreshToken"] as? String else {
            NSLog("OMI AUTH: Failed to parse Firebase signInWithIdp response")
            throw AuthError.invalidResponse
        }

        let expiresIn: Int
        if let expiresInStr = json["expiresIn"] as? String {
            expiresIn = Int(expiresInStr) ?? 3600
        } else if let expiresInInt = json["expiresIn"] as? Int {
            expiresIn = expiresInInt
        } else {
            expiresIn = 3600
        }

        var localId = json["localId"] as? String ?? ""
        if localId.isEmpty {
            if let payload = decodeJWT(idToken),
               let userId = payload["user_id"] as? String ?? payload["sub"] as? String {
                localId = userId
            }
        }

        // Get email from response if not already set
        if AuthState.shared.userEmail == nil {
            if let email = json["email"] as? String {
                AuthState.shared.userEmail = email
            }
        }

        return FirebaseTokenResult(
            idToken: idToken,
            refreshToken: refreshToken,
            expiresIn: expiresIn,
            localId: localId
        )
    }

    /// Generate a random nonce string for Apple Sign In
    private func generateNonce(length: Int = 32) -> String {
        var bytes = [UInt8](repeating: 0, count: length)
        _ = SecRandomCopyBytes(kSecRandomDefault, bytes.count, &bytes)
        let charset: [Character] = Array("0123456789ABCDEFGHIJKLMNOPQRSTUVXYZabcdefghijklmnopqrstuvwxyz-._")
        return String(bytes.map { charset[Int($0) % charset.count] })
    }

    /// SHA-256 hash of a string (for Apple Sign In nonce)
    private func sha256(_ input: String) -> String {
        let data = Data(input.utf8)
        let hash = SHA256.hash(data: data)
        return hash.compactMap { String(format: "%02x", $0) }.joined()
    }
}

// MARK: - Apple Sign In Delegate

private class AppleSignInDelegate: NSObject, ASAuthorizationControllerDelegate, ASAuthorizationControllerPresentationContextProviding {
    private var continuation: CheckedContinuation<ASAuthorizationAppleIDCredential, Error>?

    init(continuation: CheckedContinuation<ASAuthorizationAppleIDCredential, Error>) {
        self.continuation = continuation
        super.init()
    }

    func authorizationController(controller: ASAuthorizationController, didCompleteWithAuthorization authorization: ASAuthorization) {
        guard let credential = authorization.credential as? ASAuthorizationAppleIDCredential else {
            continuation?.resume(throwing: AuthError.invalidCredential)
            continuation = nil
            return
        }
        continuation?.resume(returning: credential)
        continuation = nil
    }

    func authorizationController(controller: ASAuthorizationController, didCompleteWithError error: Error) {
        continuation?.resume(throwing: error)
        continuation = nil
    }

    func presentationAnchor(for controller: ASAuthorizationController) -> ASPresentationAnchor {
        return NSApp.keyWindow ?? NSApp.windows.first!
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
