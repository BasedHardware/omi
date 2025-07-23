import Foundation

// MARK: - Authentication Bridge
// This class handles syncing authentication data between Flutter app and Swift overlay
class AuthBridge: NSObject {
    static let shared = AuthBridge()
    
    private var isSyncing = false // Prevent infinite loop
    
    private override init() {
        super.init()
        setupUserDefaultsObserver()
    }
    
    // MARK: - Flutter to Swift Sync
    
    /// Sync authentication data from Flutter app UserDefaults
    func syncFromFlutterApp() {
        // Prevent infinite loop
        guard !isSyncing else { return }
        
        // Ensure we're on the main thread for UserDefaults access
        guard Thread.isMainThread else {
            DispatchQueue.main.async {
                self.syncFromFlutterApp()
            }
            return
        }
        
        isSyncing = true
        defer { isSyncing = false }
        
        // Try to get auth data from Flutter's UserDefaults keys with safety checks
        if let flutterToken = UserDefaults.standard.string(forKey: "flutter.authToken") {
            OmiConfig.userToken = flutterToken
            print("Synced auth token from Flutter app")
            
            // Debug: Check token expiration
            if let tokenData = Data(base64Encoded: flutterToken.components(separatedBy: ".")[1] + "=="),
               let tokenDict = try? JSONSerialization.jsonObject(with: tokenData, options: []) as? [String: Any],
               let exp = tokenDict["exp"] as? TimeInterval {
                let expirationDate = Date(timeIntervalSince1970: exp)
                let timeUntilExpiry = expirationDate.timeIntervalSinceNow
                print("Token expires: \(expirationDate), Time until expiry: \(timeUntilExpiry) seconds")
                
                if timeUntilExpiry < 300 { // Less than 5 minutes
                    print("⚠️ Token expires soon, may need refresh")
                }
            }
        }
        
        // Try multiple possible user ID keys
        let userIdKeys = ["flutter.userId", "flutter.uid"]
        var foundUserId = false
        
        for key in userIdKeys {
            if let flutterUserId = UserDefaults.standard.string(forKey: key) {
                OmiConfig.userId = flutterUserId
                print("Synced user ID from Flutter app with key '\(key)': \(flutterUserId)")
                foundUserId = true
                break
            }
        }
        
        if !foundUserId {
            // Debug: Print what keys actually exist
            let allKeys = UserDefaults.standard.dictionaryRepresentation().keys
            let userKeys = allKeys.filter { $0.lowercased().contains("user") || $0.lowercased().contains("uid") }
            print("No user ID found. Available user-related keys: \(userKeys)")
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
        // Prevent infinite loop and add delay to prevent rapid-fire updates
        guard !isSyncing else { return }
        
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.5) {
            self.syncFromFlutterApp()
        }
    }
    
    // MARK: - Manual Sync Methods
    
    /// Force sync authentication data
    func forceSync() {
        print("🔄 Starting force sync...")
        syncFromFlutterApp()
        
        if OmiConfig.isConfigured() {
            print("✅ Authentication sync successful")
            OmiConfig.printConfiguration()
        } else {
            print("❌ Authentication sync failed - missing required data")
            let status = getAuthStatus()
            print("Missing data: \(status.missingData)")
            attemptAlternativeSync()
            
            // Check again after alternative sync
            if OmiConfig.isConfigured() {
                print("✅ Alternative sync successful")
                OmiConfig.printConfiguration()
            } else {
                print("❌ Alternative sync also failed")
                printAvailableKeys()
            }
        }
    }
    
    /// Try alternative keys that might be used by the Flutter app
    private func attemptAlternativeSync() {
        print("Attempting alternative sync methods...")
        
        // First, let's print ALL keys to see what's actually available
        print("All UserDefaults keys:")
        for (key, value) in UserDefaults.standard.dictionaryRepresentation() {
            if key.contains("user") || key.contains("User") || key.contains("id") || key.contains("Id") {
                print("  Found potential user key: \(key) = \(String(describing: value).prefix(100))")
            }
        }
        
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
            "flutter.uid",
            "userId",
            "user_id", 
            "omi_user_id",
            "firebase_uid",
            "FlutterSecureStorage.userId",
            "flutter_secure_storage.userId"
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
                print("Found user ID with key: \(key) = \(userId)")
                break
            }
        }
        
        // Try checking if the flutter.userId exists as an object or different type
        if let userIdObject = UserDefaults.standard.object(forKey: "flutter.userId") {
            print("Found flutter.userId as object: \(type(of: userIdObject)) = \(userIdObject)")
            if let userIdString = userIdObject as? String {
                OmiConfig.userId = userIdString
                print("Successfully converted flutter.userId object to string")
            }
        } else {
            print("flutter.userId key does not exist at all")
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
    
    /// Request token refresh from Flutter app
    func requestTokenRefresh() {
        // Signal to Flutter app that we need a fresh token
        UserDefaults.standard.set(true, forKey: "swift_overlay_needs_token_refresh")
        UserDefaults.standard.set(Date().timeIntervalSince1970, forKey: "swift_overlay_token_refresh_timestamp")
        print("🔄 Requested token refresh from Flutter app")
    }
    
    /// Wait for fresh token from Flutter app
    func waitForFreshToken(timeout: TimeInterval = 5.0) async -> Bool {
        let startTime = Date()
        let requestTimestamp = UserDefaults.standard.double(forKey: "swift_overlay_token_refresh_timestamp")
        
        while Date().timeIntervalSince(startTime) < timeout {
            // Check if Flutter app has provided a new token
            if let newToken = UserDefaults.standard.string(forKey: "flutter.authToken") {
                let tokenTimestamp = UserDefaults.standard.double(forKey: "flutter.authTokenTimestamp")
                
                // Check if the token is newer than our request and not empty
                if tokenTimestamp > requestTimestamp && !newToken.isEmpty {
                    print("✅ Received fresh token from Flutter app")
                    // Update our config immediately
                    OmiConfig.userToken = newToken
                    // Re-sync to make sure all data is current
                    syncFromFlutterApp()
                    return true
                }
            }
            
            // Wait a shorter time for faster response
            try? await Task.sleep(nanoseconds: 250_000_000) // 0.25 seconds
        }
        
        print("❌ Timeout waiting for fresh token from Flutter app")
        return false
    }
}
