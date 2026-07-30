import Foundation

/// Product analytics for Context for Claude.
///
/// Uses PostHog's HTTP capture API rather than the iOS SDK: this app deliberately has no Firebase
/// SDK and no AppDelegate swizzling surface, and a second analytics SDK would reintroduce both.
/// Distinct IDs are Firebase uids so admin HogQL can join against the same cohort as Omi Desktop.
@MainActor
enum ContextAnalytics {
    static let product = "context-for-claude"

    private static let apiKey = "phc_z3qUFhGUgYIOMYnfxVSrLmYISQvbgph8iREQv3sez3Y"
    private static let host = "https://us.i.posthog.com"
    private static let session = URLSession(configuration: .ephemeral)

    private static var identifiedUid: String?

    #if DEBUG
    private static let enabled = false
    #else
    private static let enabled = true
    #endif

    static func identify(uid: String, email: String?) {
        guard enabled else { return }
        identifiedUid = uid
        var properties: [String: Any] = superProperties()
        if let email, !email.isEmpty { properties["email"] = email }
        post(
            event: "$identify",
            distinctId: uid,
            properties: ["$set": properties]
        )
        capture("signed_in")
    }

    static func reset() {
        identifiedUid = nil
    }

    static func capture(_ event: String, properties: [String: Any] = [:]) {
        guard enabled, let uid = identifiedUid ?? OmiAuth.shared.userId else { return }
        var props = superProperties()
        for (key, value) in properties { props[key] = value }
        post(event: event, distinctId: uid, properties: props)
    }

    static func captureStarted() { capture("capture_started") }
    static func listenConnected() { capture("listen_connected") }
    static func conversationUploaded() { capture("conversation_uploaded") }

    private static func superProperties() -> [String: Any] {
        [
            "product": product,
            "platform": "macos",
            "app_version": Bundle.main.infoDictionary?["CFBundleShortVersionString"] as? String ?? "unknown",
            "app_build": Bundle.main.infoDictionary?["CFBundleVersion"] as? String ?? "unknown",
        ]
    }

    private static func post(event: String, distinctId: String, properties: [String: Any]) {
        guard let url = URL(string: "\(host)/capture/") else { return }
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.timeoutInterval = 10
        let body: [String: Any] = [
            "api_key": apiKey,
            "event": event,
            "distinct_id": distinctId,
            "properties": properties,
            "timestamp": ISO8601DateFormatter().string(from: Date()),
        ]
        request.httpBody = try? JSONSerialization.data(withJSONObject: body)
        session.dataTask(with: request).resume()
    }
}
