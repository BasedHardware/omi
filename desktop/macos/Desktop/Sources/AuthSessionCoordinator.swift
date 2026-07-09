import Foundation

extension Notification.Name {
    /// Posted when the Firebase session is invalidated (expired/revoked credentials)
    /// without a user-initiated sign-out. Observers should stop auth-dependent work
    /// (e.g. agent bridge) but must NOT wipe onboarding or stop capture.
    static let sessionDidInvalidate = Notification.Name("com.omi.desktop.sessionDidInvalidate")
}

// MARK: - Session phase

enum AuthSessionPhase: Equatable, Sendable {
    case restoring
    case authenticated
    case needsReauth
    case signedOut
}

// MARK: - Definitive auth death classifier

enum AuthDefinitiveDeathClassifier {
    /// Firebase securetoken error codes that mean the refresh credential is dead.
    static let definitiveRefreshCodes: Set<String> = [
        "INVALID_REFRESH_TOKEN",
        "USER_DISABLED",
        "USER_NOT_FOUND",
    ]

    /// Parsed Firebase Identity Toolkit / Secure Token error codes from a response body.
    static func parseFirebaseErrorCodes(from body: String) -> [String] {
        guard let data = body.data(using: .utf8),
              let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any]
        else {
            return []
        }

        var codes: [String] = []
        if let error = json["error"] as? [String: Any] {
            if let message = error["message"] as? String, !message.isEmpty {
                codes.append(message)
            }
            if let details = error["details"] as? [[String: Any]] {
                for detail in details {
                    if let reason = detail["reason"] as? String, !reason.isEmpty {
                        codes.append(reason)
                    }
                }
            }
        }
        return codes
    }

    /// True when a token refresh response proves the session cannot be recovered.
    /// Does **not** treat blanket HTTP 400 as definitive — only parsed death codes
    /// and refresh-scoped `TOKEN_EXPIRED`.
    static func isDefinitiveRefreshFailure(httpStatus: Int, errorBody: String) -> Bool {
        let codes = parseFirebaseErrorCodes(from: errorBody)
        if codes.contains(where: { definitiveRefreshCodes.contains($0) }) {
            return true
        }
        // Refresh-token expiry is definitive; ID-token expiry is not (refresh may succeed).
        if codes.contains("TOKEN_EXPIRED") || errorBody.contains("TOKEN_EXPIRED") {
            return true
        }
        _ = httpStatus  // reserved for future structured codes; not used for blanket 400
        return false
    }

    /// True when the backend still rejects the caller after a forced token refresh.
    static func isPostRefreshHTTPUnauthorized(_ statusCode: Int) -> Bool {
        statusCode == 401
    }
}

// MARK: - Coordinator

@MainActor
final class AuthSessionCoordinator {
    static let shared = AuthSessionCoordinator()

    enum InvalidateReason: String, Sendable {
        case definitiveRefreshFailure
        case postRefreshHTTP401
        case restoredSessionInvalid
        case proactiveValidationFailed
        case manual
    }

    enum EnsureValidSessionTrigger: String, Sendable {
        case appBecameActive
        case restoreValidation
        case apiUnauthorized
        case bridgeAuthMissing
    }

    private(set) var phase: AuthSessionPhase = .signedOut
    private var refreshFlight: Task<String, Error>?

    private init() {}

    func syncPhaseFromAuthState(isSignedIn: Bool, isRestoringAuth: Bool) {
        if isRestoringAuth {
            phase = .restoring
        } else if isSignedIn {
            phase = .authenticated
        } else if phase == .needsReauth {
            // Preserve needsReauth until explicit sign-in or nuclear sign-out.
        } else {
            phase = .signedOut
        }
    }

    /// Light session invalidation: clears credentials and signed-in UI state without
    /// the nuclear teardown performed by `AuthService.signOut()`.
    func invalidateSession(reason: InvalidateReason, auth: AuthService) {
        NSLog("OMI AUTH: invalidateSession reason=%@", reason.rawValue)
        auth.performLightSessionInvalidation()
        phase = .needsReauth
        NotificationCenter.default.post(
            name: .sessionDidInvalidate,
            object: nil,
            userInfo: ["reason": reason.rawValue]
        )
    }

    /// Single-flight wrapper around forced token refresh so concurrent callers share one request.
    func refreshSingleFlight(auth: AuthService) async throws -> String {
        if let refreshFlight {
            return try await refreshFlight.value
        }
        let task = Task { @MainActor in
            defer { self.refreshFlight = nil }
            return try await auth.getIdToken(forceRefresh: true)
        }
        refreshFlight = task
        return try await task.value
    }

    /// Returns true when the session has a usable ID token after optional refresh.
    func ensureValidSession(trigger: EnsureValidSessionTrigger, auth: AuthService) async -> Bool {
        syncPhaseFromAuthState(
            isSignedIn: auth.isSignedIn,
            isRestoringAuth: AuthState.shared.isRestoringAuth
        )
        guard phase != .restoring, phase != .needsReauth else { return false }
        guard auth.isSignedIn else {
            phase = .signedOut
            return false
        }
        do {
            _ = try await auth.getIdToken(forceRefresh: false)
            phase = .authenticated
            return true
        } catch {
            NSLog("OMI AUTH: ensureValidSession(%@) failed: %@", trigger.rawValue, error.localizedDescription)
            return false
        }
    }

    /// Central entry for API 401 after refresh+retry. Commit 3 wires APIClient here.
    func handleHTTPUnauthorized(
        endpoint: String,
        signOutOn401: Bool,
        auth: AuthService
    ) {
        guard signOutOn401 else { return }
        invalidateSession(reason: .postRefreshHTTP401, auth: auth)
        _ = endpoint
    }

    func resetAfterNuclearSignOut() {
        refreshFlight?.cancel()
        refreshFlight = nil
        phase = .signedOut
    }

    func resetAfterSuccessfulSignIn() {
        refreshFlight = nil
        phase = .authenticated
    }
}
