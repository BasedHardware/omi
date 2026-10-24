import Foundation

/// A credential from a native sign-in sheet, handed to the identity provider.
public enum ProviderCredential: Sendable {
    /// Sign in with Apple: identity token + the raw nonce whose SHA-256 was sent to Apple.
    case apple(idToken: String, rawNonce: String, givenName: String?, familyName: String?)
    case google(idToken: String, accessToken: String)
}

/// The signed-in user as the identity provider reports it.
public struct AuthenticatedUser: Sendable, Equatable {
    public let uid: String
    public let email: String?
    public let displayName: String?

    public init(uid: String, email: String?, displayName: String?) {
        self.uid = uid
        self.email = email
        self.displayName = displayName
    }
}

/// The identity provider (Firebase in the app). Kept as a protocol so stores and tests never
/// link Firebase.
@MainActor
public protocol AuthServicing: AnyObject {
    /// The signed-in user's uid, if any. Restored from the keychain on launch.
    var currentUserID: String? { get }
    func signIn(customToken: String) async throws -> AuthenticatedUser
    func signIn(with credential: ProviderCredential) async throws -> AuthenticatedUser
    func updateDisplayName(_ name: String) async throws
    func signOut() throws
}
