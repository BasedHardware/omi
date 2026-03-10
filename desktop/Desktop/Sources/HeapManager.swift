import Foundation
import HeapSwiftCore
import FirebaseAuth

/// Singleton manager for Heap analytics — tracks signup/k-factor events only.
/// Complements MixpanelManager and PostHogManager via AnalyticsManager dispatch.
@MainActor
class HeapManager {
    static let shared = HeapManager()

    private let appId = "2191797670"
    private var isInitialized = false

    private init() {}

    // MARK: - Initialization

    func initialize() {
        guard !isInitialized else { return }
        Heap.shared.startRecording(appId)
        isInitialized = true
        log("Heap: Initialized successfully")
    }

    // MARK: - User Identification

    func identify() {
        guard isInitialized else { return }

        var userId: String?
        var email: String?
        var name: String?

        if let user = Auth.auth().currentUser {
            userId = user.uid
            email = user.email
            name = user.displayName
        } else if AuthState.shared.isSignedIn, let storedUserId = AuthState.shared.userId {
            userId = storedUserId
            email = AuthState.shared.userEmail
            name = AuthService.shared.displayName.isEmpty ? nil : AuthService.shared.displayName
        }

        guard let uid = userId else {
            log("Heap: Cannot identify - no user signed in")
            return
        }

        Heap.shared.identify(uid)

        var properties: [String: String] = [
            "platform": "macos",
            "app_version": Bundle.main.infoDictionary?["CFBundleShortVersionString"] as? String ?? "unknown",
        ]
        if let email = email { properties["email"] = email }
        if let name = name { properties["name"] = name }

        Heap.shared.addUserProperties(properties)
        log("Heap: Identified user \(uid)")
    }

    // MARK: - Reset

    func reset() {
        guard isInitialized else { return }
        Heap.shared.resetIdentity()
        log("Heap: Reset identity")
    }

    // MARK: - Event Tracking

    func track(_ eventName: String, properties: [String: String]? = nil) {
        guard isInitialized else { return }
        if let properties = properties {
            Heap.shared.track(eventName, properties: properties)
        } else {
            Heap.shared.track(eventName)
        }
    }
}
