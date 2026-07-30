import Foundation

/// Fire-and-forget PostHog capture from the MCP process (no SDK — stdout is the protocol channel).
enum ContextMCPAnalytics {
    private static let apiKey = "phc_z3qUFhGUgYIOMYnfxVSrLmYISQvbgph8iREQv3sez3Y"
    private static let host = "https://us.i.posthog.com"
    private static let session = URLSession(configuration: .ephemeral)

    static func toolInvoked(_ name: String) {
        #if DEBUG
        return
        #else
        guard let url = URL(string: "\(host)/capture/") else { return }
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.timeoutInterval = 5
        let body: [String: Any] = [
            "api_key": apiKey,
            "event": "mcp_tool_invoked",
            "distinct_id": "context-for-claude-mcp",
            "properties": [
                "product": "context-for-claude",
                "platform": "macos",
                "tool": name,
            ],
        ]
        request.httpBody = try? JSONSerialization.data(withJSONObject: body)
        session.dataTask(with: request).resume()
        #endif
    }
}
