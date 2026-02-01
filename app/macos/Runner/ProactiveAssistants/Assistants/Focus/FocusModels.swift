import Foundation

// MARK: - Focus Status

enum FocusStatus: String, Codable {
    case focused
    case distracted
}

// MARK: - Screen Analysis Result

struct ScreenAnalysis: Codable, AssistantResult {
    let status: FocusStatus
    let appOrSite: String
    let description: String
    let message: String?

    enum CodingKeys: String, CodingKey {
        case status
        case appOrSite = "app_or_site"
        case description
        case message
    }

    /// Convert to dictionary for Flutter
    func toDictionary() -> [String: Any] {
        var dict: [String: Any] = [
            "status": status.rawValue,
            "appOrSite": appOrSite,
            "description": description
        ]
        if let message = message {
            dict["message"] = message
        }
        return dict
    }
}

// MARK: - Focus Event (for Flutter communication)

struct FocusEvent {
    let status: FocusStatus
    let appOrSite: String
    let description: String
    let message: String?
    let timestamp: Date

    init(from analysis: ScreenAnalysis) {
        self.status = analysis.status
        self.appOrSite = analysis.appOrSite
        self.description = analysis.description
        self.message = analysis.message
        self.timestamp = Date()
    }

    /// Convert to dictionary for Flutter EventChannel
    func toDictionary() -> [String: Any?] {
        return [
            "status": status.rawValue,
            "appOrSite": appOrSite,
            "description": description,
            "message": message,
            "timestamp": ISO8601DateFormatter().string(from: timestamp)
        ]
    }
}
