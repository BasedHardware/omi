import Foundation

struct OmiConfig {
    // API Configuration
    static let baseURL = "https://api.omi.me" // Update with actual Omi API URL
    static let chatEndpoint = "/v1/chat"
    static let audioEndpoint = "/v1/audio/process"
    
    // Audio Configuration
    static let audioSampleRate: Double = 16000
    static let audioChannels: Int = 1
    static let audioFormat = "wav"
    
    // Chat Configuration
    static let maxMessageLength = 1000
    static let timeout: TimeInterval = 30.0
    
    // User Configuration (will be populated from Flutter app or stored preferences)
    static var userToken: String? {
        get {
            return UserDefaults.standard.string(forKey: "omi_user_token")
        }
        set {
            UserDefaults.standard.set(newValue, forKey: "omi_user_token")
        }
    }
    
    static var deviceId: String? {
        get {
            return UserDefaults.standard.string(forKey: "omi_device_id")
        }
        set {
            UserDefaults.standard.set(newValue, forKey: "omi_device_id")
        }
    }
    
    // Helper methods
    static func fullChatURL() -> String {
        return baseURL + chatEndpoint
    }
    
    static func fullAudioURL() -> String {
        return baseURL + audioEndpoint
    }
    
    static func isConfigured() -> Bool {
        return userToken != nil && !userToken!.isEmpty
    }
}

// Extension for debugging
extension OmiConfig {
    static func printConfiguration() {
        print("Omi Configuration:")
        print("- Base URL: \(baseURL)")
        print("- Chat URL: \(fullChatURL())")
        print("- Audio URL: \(fullAudioURL())")
        print("- User Token: \(userToken != nil ? "Set" : "Not set")")
        print("- Device ID: \(deviceId ?? "Not set")")
        print("- Is Configured: \(isConfigured())")
    }
}
