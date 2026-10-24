import Foundation
import Observation
import OmiCore
import OmiNetwork
import OmiPersistence

/// Owns the app's top-level phase: who is signed in, and which root screen shows.
@MainActor
@Observable
public final class SessionStore {
    public enum Phase: Equatable, Sendable {
        case launching
        case signedOut
        /// Signed in, AI-processing consent not given on this install yet (local, like Flutter's
        /// `aiConsentGiven`; shown again after every sign-in).
        case consent(userID: String)
        /// Signed in, onboarding not finished (also for Flutter users who stopped mid-onboarding).
        case onboarding(userID: String)
        case ready(userID: String)
    }

    public private(set) var phase: Phase = .launching
    public private(set) var isWorking = false
    public private(set) var errorMessage: String?

    let auth: any AuthServicing
    private let api: any APIClientProtocol
    private let configuration: AppConfiguration
    let preferences: Preferences

    public init(
        auth: any AuthServicing,
        api: any APIClientProtocol,
        configuration: AppConfiguration,
        preferences: Preferences
    ) {
        self.auth = auth
        self.api = api
        self.configuration = configuration
        self.preferences = preferences
    }

    public var displayName: String? {
        preferences.displayName
    }

    public var canUseLocalDevSignIn: Bool {
        configuration.isLocalDev
    }

    /// Resolves the launch phase from the persisted session (no network). A session and the
    /// onboarding flag written by the Flutter build are honored as-is (ADR 0002).
    public func restore() {
        guard let userID = auth.currentUserID else {
            phase = .signedOut
            return
        }
        phase = signedInPhase(userID)
    }

    public var userID: String? {
        switch phase {
        case let .consent(id), let .onboarding(id), let .ready(id): id
        case .launching, .signedOut: nil
        }
    }

    public func giveConsent() {
        preferences.set(true, for: .aiConsentGiven)
        if case let .consent(userID) = phase { phase = signedInPhase(userID) }
    }

    public func completeOnboarding() {
        saveOnboardingCompleted()
        if case let .onboarding(userID) = phase { phase = .ready(userID: userID) }
    }

    /// Setup is done while "You're ready" and the introduction still show: an app closed during
    /// them opens on Home next time.
    public func saveOnboardingCompleted() {
        guard !preferences.bool(.onboardingCompleted) else { return }
        preferences.set(true, for: .onboardingCompleted)
        preferences.set(true, for: .permissionsCompleted)
        Task { try? await api.updateOnboarding(completed: true, acquisitionSource: nil) }
    }

    /// Walks a signed-in user through onboarding again (pairing a new Omi, or QA); finishing it
    /// returns to the app as before.
    public func replayOnboarding() {
        if case let .ready(userID) = phase { phase = .onboarding(userID: userID) }
    }

    /// The short introduction to the app on its own (Help › Replay introduction), over Home.
    public private(set) var showsIntroduction = false

    public func replayIntroduction() {
        if case .ready = phase { showsIntroduction = true }
    }

    public func introductionFinished() {
        showsIntroduction = false
    }

    /// A Settings section to open once Home shows (the introduction's "Choose how often").
    public var settingsAfterIntroduction: String?

    private func signedInPhase(_ userID: String) -> Phase {
        if !preferences.bool(.aiConsentGiven) { return .consent(userID: userID) }
        return preferences.bool(.onboardingCompleted) ? .ready(userID: userID) : .onboarding(userID: userID)
    }

    /// Sign in with Apple / Google (native sheets, like the Flutter production build).
    public func signIn(with credential: ProviderCredential) async {
        guard !isWorking else { return }
        isWorking = true
        errorMessage = nil
        defer { isWorking = false }
        do {
            let user = try await auth.signIn(with: credential)
            var given: String?
            var family: String?
            if case let .apple(_, _, appleGiven, appleFamily) = credential, let appleGiven, !appleGiven.isEmpty {
                // Apple shares the name only on the first sign-in.
                given = appleGiven
                family = appleFamily
                try? await auth.updateDisplayName([appleGiven, appleFamily].compactMap(\.self).joined(separator: " "))
            }
            await didSignIn(user, givenName: given, familyName: family)
        } catch {
            errorMessage = Self.describe(error)
        }
    }

    /// Mirrors Flutter's `_updateUserPreferences` + `_restoreOnboardingState` after any sign-in.
    func didSignIn(_ user: AuthenticatedUser, givenName: String? = nil, familyName: String? = nil) async {
        if preferences.string(.uid) != user.uid { preferences.clearUser() }
        preferences.set(user.uid, for: .uid)
        if let email = user.email, !email.isEmpty { preferences.set(email, for: .email) }
        let parts = user.displayName?.split(separator: " ", maxSplits: 1).map(String.init) ?? []
        if let given = givenName ?? parts.first, !given.isEmpty { preferences.set(given, for: .givenName) }
        if let family = familyName ?? (parts.count > 1 ? parts[1] : nil), !family.isEmpty { preferences.set(family, for: .familyName) }
        if let state = try? await api.onboardingState() {
            if state.completed { preferences.set(true, for: .onboardingCompleted) }
            if let source = state.acquisitionSource { preferences.set(source, for: .foundOmiSource) }
        }
        if let language = try? await api.primaryLanguage() {
            preferences.set(language, for: .userPrimaryLanguage)
            preferences.set(true, for: .hasSetPrimaryLanguage)
        }
        try? await api.setTimeZone(TimeZone.current.identifier)
        phase = signedInPhase(user.uid)
    }

    /// Deletes the account server-side, then clears everything local (nothing kept).
    public func deleteAccount(reason: String?) async -> Bool {
        do {
            try await api.deleteAccount(reason: reason)
            try? auth.signOut()
            preferences.clearUser()
            preferences.set(nil as String?, for: .btDevice)
            phase = .signedOut
            return true
        } catch {
            errorMessage = Self.describe(error)
            return false
        }
    }

    /// Local harness sign-in: backend mints a custom token for `uid`, Firebase signs in with it.
    /// Same path as the Flutter app's `signInWithLocalDevToken`.
    public func signInLocalDev(uid: String = "local-dev-user") async {
        guard canUseLocalDevSignIn, !isWorking else { return }
        isWorking = true
        errorMessage = nil
        defer { isWorking = false }
        do {
            let token = try await api.localDevCustomToken(uid: uid)
            let user = try await auth.signIn(customToken: token)
            await didSignIn(user)
        } catch {
            errorMessage = Self.describe(error)
        }
    }

    public func signOut() {
        do {
            try auth.signOut()
            preferences.clearUser()
            phase = .signedOut
        } catch {
            errorMessage = Self.describe(error)
        }
    }

    static func describe(_ error: any Error) -> String {
        switch error {
        case APIError.http(404, _):
            "This backend has no local sign-in. Start the harness with make dev-up."
        case let APIError.http(status, _):
            "Sign-in failed (HTTP \(status))."
        case APIError.transport:
            "Cannot reach the backend. Is the local harness running?"
        default:
            error.localizedDescription
        }
    }
}
