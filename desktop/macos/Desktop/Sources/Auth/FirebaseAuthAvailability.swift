@preconcurrency import FirebaseAuth
import FirebaseCore
import Foundation

/// The Firebase SDK is optional at runtime: local harnesses deliberately skip
/// it and a damaged/missing bundled plist must leave REST-backed auth usable.
/// `Auth.auth()` fatally traps without a configured default Firebase app, so
/// callers obtain SDK access only through this seam.
@MainActor
struct FirebaseAuthAvailability {
  var configuredAuth: () -> Auth?

  static let live = FirebaseAuthAvailability(
    configuredAuth: {
      guard FirebaseApp.app() != nil else { return nil }
      return Auth.auth()
    })

  func auth() -> Auth? {
    configuredAuth()
  }

  struct NativeAppleSignInResult {
    let tokens: AuthService.FirebaseTokenResult
    let fallbackReason: String?
  }

  static func signInWithNativeApple(
    auth: Auth?,
    identityToken: String,
    nonce: String,
    isSessionCurrent: () -> Bool,
    discardStaleFirebaseUser: (String) -> Void,
    restFallback: () async throws -> AuthService.FirebaseTokenResult
  ) async throws -> NativeAppleSignInResult {
    guard let auth else {
      let tokens = try await restFallback()
      return .init(tokens: tokens, fallbackReason: "config_incomplete")
    }

    let credential = OAuthProvider.credential(providerID: .apple, idToken: identityToken, rawNonce: nonce)
    do {
      let authResult = try await auth.signIn(with: credential)
      let tokenResult = try await authResult.user.getIDTokenResult()
      guard isSessionCurrent() else {
        discardStaleFirebaseUser(authResult.user.uid)
        throw AuthError.cancelled
      }
      let tokens = AuthService.FirebaseTokenResult(
        idToken: tokenResult.token,
        refreshToken: authResult.user.refreshToken ?? "",
        expiresIn: Int(tokenResult.expirationDate.timeIntervalSinceNow),
        localId: authResult.user.uid)
      return .init(tokens: tokens, fallbackReason: nil)
    } catch {
      guard isSessionCurrent() else { throw AuthError.cancelled }
      let nsError = error as NSError
      logError(
        "AUTH: Firebase SDK Apple sign-in failed (domain=\(nsError.domain) code=\(nsError.code))", error: error)
      let tokens = try await restFallback()
      return .init(tokens: tokens, fallbackReason: "auth")
    }
  }

  static func recordNativeAppleFallback(reason: String) {
    DesktopDiagnosticsManager.shared.recordFallback(
      area: "api_auth",
      from: "firebase_sdk",
      to: "firebase_rest",
      reason: reason,
      outcome: .recovered
    )
  }
}
