import Foundation

/// Compile-checked `UserDefaults` keys (S-13, BL-004 partial).
///
/// The defect: `UserDefaults` keys were raw inline string literals scattered
/// across the app — `"auth_userId"` alone appeared inline ~18 times. A single
/// typo (`"auth_userld"`) silently reads `nil` with no error, so auth /
/// onboarding state fails to restore and the failure is invisible.
///
/// Routing keys through this enum turns a typo from a silent `nil` into a
/// compile error, and gives the app one source of truth for each key's string.
///
/// This is the auth slice of the migration. New keys should be added here and
/// read/written through the typed `UserDefaults` accessors below rather than as
/// inline literals. `desktop/macos/scripts/check-userdefaults-key-ratchet.py` is
/// a CI/pre-push gate that prevents new raw inline `forKey:` string literals from being
/// introduced elsewhere (the count may only shrink).
enum DefaultsKey: String {
    case authIsSignedIn = "auth_isSignedIn"
    case authUserEmail = "auth_userEmail"
    case authUserId = "auth_userId"
    case authGivenName = "auth_givenName"
    case authFamilyName = "auth_familyName"
    case authIdToken = "auth_idToken"
    case authRefreshToken = "auth_refreshToken"
    case authTokenExpiry = "auth_tokenExpiry"
    case authTokenUserId = "auth_tokenUserId"  // User ID that owns the stored token
    case authIsImpersonating = "auth_isImpersonating"
    case chatBridgeMode = "chatBridgeMode"
    case onboardingStep = "onboardingStep"
    case chatScreenshotSharingEnabled = "chatScreenshotSharingEnabled"
}

/// Typed accessors that take a `DefaultsKey` instead of a `String`.
///
/// Each forwards to the stdlib `String`-keyed method via `key.rawValue`, so
/// overload resolution picks the stdlib method (no recursion). Call sites read
/// as `UserDefaults.standard.string(forKey: .authUserId)` — the key is now
/// compiler-checked.
extension UserDefaults {
    func string(forKey key: DefaultsKey) -> String? { string(forKey: key.rawValue) }
    func bool(forKey key: DefaultsKey) -> Bool { bool(forKey: key.rawValue) }
    func integer(forKey key: DefaultsKey) -> Int { integer(forKey: key.rawValue) }
    func double(forKey key: DefaultsKey) -> Double { double(forKey: key.rawValue) }

    func set(_ value: Any?, forKey key: DefaultsKey) { set(value, forKey: key.rawValue) }
    func removeObject(forKey key: DefaultsKey) { removeObject(forKey: key.rawValue) }
}
