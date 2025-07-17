import Foundation

struct OmiConfig {
    // API Configuration - Updated to match Flutter app endpoints
    static let baseURL = "https://api.omi.me"
    static let messagesEndpoint = "/v2/messages"
    static let initialMessageEndpoint = "/v2/initial-message"
    static let filesEndpoint = "/v2/files"
    static let voiceMessageEndpoint = "/v2/voice-messages"
    
    // Audio Configuration
    static let audioSampleRate: Double = 16000
    static let audioChannels: Int = 1
    static let audioFormat = "wav"
    
    // Chat Configuration
    static let maxMessageLength = 1000
    static let timeout: TimeInterval = 30.0
    
    // Thread-safe UserDefaults access
    private static let userDefaultsQueue = DispatchQueue(label: "com.omi.userdefaults", qos: .userInitiated)
    
    // User Configuration (will be populated from Flutter app or stored preferences)
    static var userToken: String? {
        get {
            return userDefaultsQueue.sync {
                UserDefaults.standard.string(forKey: "omi_user_token")
            }
        }
        set {
            userDefaultsQueue.async {
                UserDefaults.standard.set(newValue, forKey: "omi_user_token")
            }
        }
    }
    
    static var userId: String? {
        get {
            return userDefaultsQueue.sync {
                UserDefaults.standard.string(forKey: "omi_user_id")
            }
        }
        set {
            userDefaultsQueue.async {
                UserDefaults.standard.set(newValue, forKey: "omi_user_id")
            }
        }
    }
    
    static var deviceId: String? {
        get {
            return userDefaultsQueue.sync {
                UserDefaults.standard.string(forKey: "omi_device_id")
            }
        }
        set {
            userDefaultsQueue.async {
                UserDefaults.standard.set(newValue, forKey: "omi_device_id")
            }
        }
    }
    
    static var selectedAppId: String? {
        get {
            return userDefaultsQueue.sync {
                UserDefaults.standard.string(forKey: "selected_app_id")
            }
        }
        set {
            userDefaultsQueue.async {
                UserDefaults.standard.set(newValue, forKey: "selected_app_id")
            }
        }
    }
    
    // Helper methods
    static func fullMessagesURL() -> String {
        return baseURL + messagesEndpoint
    }
    
    static func fullInitialMessageURL() -> String {
        return baseURL + initialMessageEndpoint
    }
    
    static func fullFilesURL() -> String {
        return baseURL + filesEndpoint
    }
    
    static func isConfigured() -> Bool {
        return userToken != nil && !userToken!.isEmpty && userId != nil && !userId!.isEmpty
    }
    
    static func authHeader() -> String? {
        guard let token = userToken else { return nil }
        return "Bearer \(token)"
    }
}

// Extension for debugging
extension OmiConfig {
    static func printConfiguration() {
        print("Omi Configuration:")
        print("- Base URL: \(baseURL)")
        print("- Messages URL: \(fullMessagesURL())")
        print("- Initial Message URL: \(fullInitialMessageURL())")
        print("- Files URL: \(fullFilesURL())")
        print("- User Token: \(userToken != nil ? "Set (\(userToken!.prefix(10))...)" : "Not set")")
        print("- User ID: \(userId ?? "Not set")")
        print("- Device ID: \(deviceId ?? "Not set")")
        print("- Selected App ID: \(selectedAppId ?? "Not set")")
        print("- Is Configured: \(isConfigured())")
    }
}
