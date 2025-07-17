import Foundation

// MARK: - Authentication Bridge
// This class handles syncing authentication data between Flutter app and Swift overlay
class AuthBridge: NSObject {
    static let shared = AuthBridge()
    
    private override init() {
        super.init()
        setupUserDefaultsObserver()
    }
    
    // MARK: - Flutter to Swift Sync
    
    /// Sync authentication data from Flutter app UserDefaults
    func syncFromFlutterApp() {
        // Try to get auth data from Flutter's UserDefaults keys
        if let flutterToken = UserDefaults.standard.string(forKey: "flutter.authToken") {
            OmiConfig.userToken = flutterToken
            print("Synced auth token from Flutter app")
        }
        
        if let flutterUserId = UserDefaults.standard.string(forKey: "flutter.userId") {
            OmiConfig.userId = flutterUserId
            print("Synced user ID from Flutter app")
        }
        
        if let selectedApp = UserDefaults.standard.string(forKey: "flutter.selectedChatAppId") {
            OmiConfig.selectedAppId = selectedApp == "no_selected" ? nil : selectedApp
            print("Synced selected app ID from Flutter app: \(selectedApp)")
        }
        
        // Check for device ID
        if let deviceId = UserDefaults.standard.string(forKey: "flutter.deviceId") {
            OmiConfig.deviceId = deviceId
            print("Synced device ID from Flutter app")
        }
    }
    
    /// Setup observer for UserDefaults changes
    private func setupUserDefaultsObserver() {
        NotificationCenter.default.addObserver(
            self,
            selector: #selector(userDefaultsDidChange),
            name: UserDefaults.didChangeNotification,
            object: nil
        )
    }
    
    @objc private func userDefaultsDidChange(_ notification: Notification) {
        // Auto-sync when Flutter app updates its preferences
        syncFromFlutterApp()
    }
    
    // MARK: - Manual Sync Methods
    
    /// Force sync authentication data
    func forceSync() {
        syncFromFlutterApp()
        
        if OmiConfig.isConfigured() {
            print("✅ Authentication sync successful")
            OmiConfig.printConfiguration()
        } else {
            print("❌ Authentication sync failed - missing required data")
            attemptAlternativeSync()
        }
    }
    
    /// Try alternative keys that might be used by the Flutter app
    private func attemptAlternativeSync() {
        print("Attempting alternative sync methods...")
        
        // Try common Flutter SharedPreferences patterns
        let possibleTokenKeys = [
            "flutter.authToken",
            "authToken", 
            "omi_auth_token",
            "user_token",
            "firebase_token"
        ]
        
        let possibleUserIdKeys = [
            "flutter.userId",
            "userId",
            "user_id", 
            "omi_user_id",
            "firebase_uid"
        ]
        
        for key in possibleTokenKeys {
            if let token = UserDefaults.standard.string(forKey: key), !token.isEmpty {
                OmiConfig.userToken = token
                print("Found auth token with key: \(key)")
                break
            }
        }
        
        for key in possibleUserIdKeys {
            if let userId = UserDefaults.standard.string(forKey: key), !userId.isEmpty {
                OmiConfig.userId = userId
                print("Found user ID with key: \(key)")
                break
            }
        }
    }
    
    // MARK: - Status Methods
    
    func getAuthStatus() -> (isAuthenticated: Bool, missingData: [String]) {
        var missingData: [String] = []
        
        if OmiConfig.userToken?.isEmpty ?? true {
            missingData.append("User Token")
        }
        
        if OmiConfig.userId?.isEmpty ?? true {
            missingData.append("User ID")
        }
        
        return (missingData.isEmpty, missingData)
    }
    
    func printAvailableKeys() {
        print("Available UserDefaults keys:")
        for (key, value) in UserDefaults.standard.dictionaryRepresentation() {
            if key.lowercased().contains("auth") || 
               key.lowercased().contains("token") || 
               key.lowercased().contains("user") ||
               key.lowercased().contains("firebase") {
                print("  \(key): \(String(describing: value).prefix(50))...")
            }
        }
    }
}

// MARK: - Flutter Communication Channel
extension AuthBridge {
    /// Setup method channel for communication with Flutter
    func setupFlutterChannel() {
        // This would be called from the Flutter engine delegate
        // to establish a proper communication channel
        print("Setting up Flutter communication channel...")
        
        // For now, we'll rely on UserDefaults sync
        // In the future, this could use platform channels for real-time sync
    }
    
    /// Send authentication status to Flutter app
    func sendStatusToFlutter() {
        let status = getAuthStatus()
        UserDefaults.standard.set(status.isAuthenticated, forKey: "swift_overlay_auth_status")
        UserDefaults.standard.set(status.missingData, forKey: "swift_overlay_missing_data")
    }
}
