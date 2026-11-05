import AuthenticationServices
import OmiDesign
import OmiNetwork
import OmiService
import SwiftUI

/// Connect / disconnect wording and the sign-in, shared by onboarding, Settings › Capabilities and
/// chat's Connect card.
@MainActor
public enum CapabilitiesList {
    /// The sign-in for one connection (also Home's "Connect …" card): the backend's OAuth page in
    /// a web sheet, then a fresh state. Without a URL the store has recorded why.
    public static func connect(
        _ integration: Integration, store: CapabilitiesStore, webAuthentication: WebAuthenticationSession
    ) async {
        guard let url = await store.authorizationURL(for: integration) else { return }
        do {
            // The backend's callback page redirects to omi://<key>/callback?success=true.
            let callback = try await webAuthentication.authenticate(
                using: url, callbackURLScheme: "omi", preferredBrowserSession: .ephemeral
            )
            let success = URLComponents(url: callback, resolvingAgainstBaseURL: false)?
                .queryItems?.first { $0.name == "success" }?.value
            if success == "false" { store.loginEnded(integration, cancelled: false) }
        } catch let error as ASWebAuthenticationSessionError where error.code == .canceledLogin {
            store.loginEnded(integration, cancelled: true)
        } catch {
            store.loginEnded(integration, cancelled: false)
        }
        await store.load()
    }

    public static func message(_ failure: CapabilitiesStore.ConnectFailure, name: String) -> String {
        switch failure {
        case .notConfigured: L("nativeCapabilityNotConfigured", name)
        case .offline: L("nativeCapabilityOffline")
        case .cancelled: L("nativeCapabilityCancelled")
        case .failed: L("nativeCapabilityLoginFailed", name)
        }
    }

    public static func name(_ id: String) -> String {
        switch id {
        case "google_calendar": "Google Calendar"
        case "gmail": "Gmail"
        case "todoist": "Todoist"
        case "asana": "Asana"
        case "clickup": "ClickUp"
        case "google_tasks": "Google Tasks"
        default: id
        }
    }

    public static func purposeKey(_ id: String) -> String {
        switch id {
        case "google_calendar": "nativeCapabilityCalendar"
        case "gmail": "nativeCapabilityMail"
        default: "nativeCapabilityTasks"
        }
    }
}
