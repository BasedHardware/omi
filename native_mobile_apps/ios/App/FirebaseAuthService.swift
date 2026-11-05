@preconcurrency import FirebaseAuth
@preconcurrency import FirebaseCore
@preconcurrency import GoogleSignIn
import OmiNetwork
import OmiService
import UIKit

/// Firebase-backed identity. The Firebase iOS SDK stores the session in the keychain under the
/// same service the Flutter app's FlutterFire plugin used, so a user signed in on the Flutter
/// build stays signed in after the native update (ADR 0002, verified in P1).
@MainActor
final class FirebaseAuthService: AuthServicing {
    init(emulator: (host: String, port: Int)?) {
        if let emulator {
            Auth.auth().useEmulator(withHost: emulator.host, port: emulator.port)
        }
        if let clientID = FirebaseApp.app()?.options.clientID {
            GIDSignIn.sharedInstance.configuration = GIDConfiguration(clientID: clientID)
        }
    }

    var currentUserID: String? {
        Auth.auth().currentUser?.uid
    }

    /// Google sign-in is offered only when the bundled Firebase config has a Google client.
    static var supportsGoogle: Bool {
        FirebaseApp.app()?.options.clientID != nil
    }

    func signIn(customToken: String) async throws -> AuthenticatedUser {
        try await Self.user(Auth.auth().signIn(withCustomToken: customToken).user)
    }

    func signIn(with credential: ProviderCredential) async throws -> AuthenticatedUser {
        let firebaseCredential: AuthCredential = switch credential {
        case let .apple(idToken, rawNonce, given, family):
            OAuthProvider.appleCredential(
                withIDToken: idToken, rawNonce: rawNonce,
                fullName: PersonNameComponents(givenName: given, familyName: family)
            )
        case let .google(idToken, accessToken):
            GoogleAuthProvider.credential(withIDToken: idToken, accessToken: accessToken)
        }
        return try await Self.user(Auth.auth().signIn(with: firebaseCredential).user)
    }

    func updateDisplayName(_ name: String) async throws {
        guard let user = Auth.auth().currentUser, !name.isEmpty else { return }
        let change = user.createProfileChangeRequest()
        change.displayName = name
        try await change.commitChanges()
    }

    func signOut() throws {
        GIDSignIn.sharedInstance.signOut()
        try Auth.auth().signOut()
    }

    /// Presents Google's sheet and returns its tokens.
    static func googleCredential() async throws -> ProviderCredential {
        guard let presenter = UIApplication.shared.connectedScenes
            .compactMap({ ($0 as? UIWindowScene)?.keyWindow?.rootViewController }).first
        else {
            throw APIError.transport("no window")
        }
        let result = try await GIDSignIn.sharedInstance.signIn(withPresenting: presenter)
        guard let idToken = result.user.idToken?.tokenString else { throw APIError.decoding("missing Google id token") }
        return .google(idToken: idToken, accessToken: result.user.accessToken.tokenString)
    }

    private static func user(_ user: User) -> AuthenticatedUser {
        AuthenticatedUser(uid: user.uid, email: user.email, displayName: user.displayName)
    }
}

/// ID tokens for `Authorization: Bearer`. Firebase refreshes them transparently.
struct FirebaseTokenProvider: AuthTokenProviding {
    func idToken(forceRefresh: Bool) async throws -> String {
        try await Self.token(forceRefresh: forceRefresh)
    }

    @MainActor
    private static func token(forceRefresh: Bool) async throws -> String {
        guard let user = Auth.auth().currentUser else { throw APIError.notSignedIn }
        return try await user.getIDTokenResult(forcingRefresh: forceRefresh).token
    }
}
