import Foundation
import Intercom
import OmiService

/// Intercom's messenger, as Flutter's `IntercomManager`: set up at launch, the signed-in account
/// identified by its uid (no email or name leaves the app here), opened from Help and feedback.
/// Off unless the build sets `OMI_INTERCOM_APP_ID` and `OMI_INTERCOM_IOS_API_KEY` (Info.plist
/// `OmiIntercomAppID` / `OmiIntercomAPIKey`); Help then shows only the help center and feedback.
@MainActor
enum SupportChat {
    private static let appID = configured("OmiIntercomAppID")
    private static let apiKey = configured("OmiIntercomAPIKey")
    private static var loggedInUser: String?

    static var isConfigured: Bool {
        appID != nil && apiKey != nil
    }

    static func configure() {
        guard let appID, let apiKey else { return }
        Intercom.setApiKey(apiKey, forAppId: appID)
    }

    /// Who the conversations belong to; signed out, Intercom forgets them.
    static func sessionChanged(_ phase: SessionStore.Phase) {
        guard isConfigured else { return }
        switch phase {
        case let .ready(userID), let .onboarding(userID), let .consent(userID):
            guard loggedInUser != userID else { return }
            if loggedInUser != nil { Intercom.logout() }
            loggedInUser = userID
            let attributes = ICMUserAttributes()
            attributes.userId = userID
            Intercom.loginUser(with: attributes)
        case .signedOut:
            guard loggedInUser != nil else { return }
            loggedInUser = nil
            Intercom.logout()
        case .launching:
            break
        }
    }

    /// Replies from support arrive as pushes (Info.plist turns Intercom's own push hooks off).
    static func registerPushToken(_ token: Data) {
        guard isConfigured else { return }
        Intercom.setDeviceToken(token, completion: nil)
    }

    static func present() {
        guard isConfigured else { return }
        Intercom.present()
    }

    private static func configured(_ key: String) -> String? {
        (Bundle.main.object(forInfoDictionaryKey: key) as? String).flatMap { $0.isEmpty ? nil : $0 }
    }
}
