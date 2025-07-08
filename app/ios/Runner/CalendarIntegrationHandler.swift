import Flutter
import UIKit
import SafariServices
import Security
import LocalAuthentication
import BackgroundTasks

@available(iOS 13.0, *)
class CalendarIntegrationHandler: NSObject, FlutterPlugin {
    
    private var safariViewController: SFSafariViewController?
    private var pendingResult: FlutterResult?
    private let keychainService = "com.omi.calendar"
    
    static func register(with registrar: FlutterPluginRegistrar) {
        let channel = FlutterMethodChannel(name: "calendar_integration", binaryMessenger: registrar.messenger())
        let instance = CalendarIntegrationHandler()
        registrar.addMethodCallDelegate(instance, channel: channel)
        
        // Register background task
        BGTaskScheduler.shared.register(forTaskWithIdentifier: "calendar_token_refresh", using: nil) { task in
            instance.handleBackgroundTokenRefresh(task: task as! BGAppRefreshTask)
        }
    }
    
    func handle(_ call: FlutterMethodCall, result: @escaping FlutterResult) {
        switch call.method {
        case "initiateIOSOAuth":
            initiateIOSOAuth(arguments: call.arguments as? [String: Any], result: result)
        case "storeTokensIOSKeychain":
            storeTokensInKeychain(arguments: call.arguments as? [String: Any], result: result)
        case "retrieveTokensIOSKeychain":
            retrieveTokensFromKeychain(arguments: call.arguments as? [String: Any], result: result)
        case "scheduleIOSBackgroundRefresh":
            scheduleBackgroundRefresh(arguments: call.arguments as? [String: Any], result: result)
        case "handleOAuthInterruption":
            handleOAuthInterruption(arguments: call.arguments as? [String: Any], result: result)
        case "checkPlatformCapabilities":
            checkPlatformCapabilities(result: result)
        default:
            result(FlutterMethodNotImplemented)
        }
    }
    
    private func initiateIOSOAuth(arguments: [String: Any]?, result: @escaping FlutterResult) {
        guard let args = arguments,
              let useSafariVC = args["use_safari_view_controller"] as? Bool else {
            result(FlutterError(code: "INVALID_ARGUMENTS", message: "Missing arguments", details: nil))
            return
        }
        
        // Get auth URL from backend
        guard let authURL = getAuthURLFromBackend() else {
            result(FlutterError(code: "AUTH_URL_ERROR", message: "Failed to get auth URL", details: nil))
            return
        }
        
        if useSafariVC {
            presentSafariViewController(url: authURL, result: result)
        } else {
            // Fallback to external Safari
            if UIApplication.shared.canOpenURL(authURL) {
                UIApplication.shared.open(authURL)
                result([
                    "auth_url": authURL.absoluteString,
                    "session_id": UUID().uuidString,
                    "method": "external_safari"
                ])
            } else {
                result(FlutterError(code: "SAFARI_UNAVAILABLE", message: "Safari is not available", details: nil))
            }
        }
    }
    
    private func presentSafariViewController(url: URL, result: @escaping FlutterResult) {
        guard let rootViewController = UIApplication.shared.keyWindow?.rootViewController else {
            result(FlutterError(code: "NO_ROOT_VC", message: "No root view controller", details: nil))
            return
        }
        
        let config = SFSafariViewController.Configuration()
        config.entersReaderIfAvailable = false
        
        safariViewController = SFSafariViewController(url: url, configuration: config)
        safariViewController?.delegate = self
        
        let sessionId = UUID().uuidString
        pendingResult = result
        
        rootViewController.present(safariViewController!, animated: true)
        
        result([
            "auth_url": url.absoluteString,
            "session_id": sessionId,
            "method": "safari_view_controller"
        ])
    }
    
    private func storeTokensInKeychain(arguments: [String: Any]?, result: @escaping FlutterResult) {
        guard let args = arguments,
              let tokens = args["tokens"] as? [String: Any],
              let biometricProtection = args["biometric_protection"] as? Bool else {
            result(FlutterError(code: "INVALID_ARGUMENTS", message: "Missing arguments", details: nil))
            return
        }
        
        do {
            let tokenData = try JSONSerialization.data(withJSONObject: tokens)
            
            var query: [String: Any] = [
                kSecClass as String: kSecClassGenericPassword,
                kSecAttrService as String: keychainService,
                kSecAttrAccount as String: "calendar_tokens",
                kSecValueData as String: tokenData
            ]
            
            if biometricProtection {
                // Add biometric protection
                let access = SecAccessControlCreateWithFlags(
                    nil,
                    kSecAttrAccessibleWhenUnlockedThisDeviceOnly,
                    .biometryAny,
                    nil
                )
                query[kSecAttrAccessControl as String] = access
            } else {
                query[kSecAttrAccessible as String] = kSecAttrAccessibleWhenUnlockedThisDeviceOnly
            }
            
            // Delete existing item first
            SecItemDelete(query as CFDictionary)
            
            // Add new item
            let status = SecItemAdd(query as CFDictionary, nil)
            
            if status == errSecSuccess {
                result(["success": true])
            } else {
                result(FlutterError(
                    code: "KEYCHAIN_ERROR",
                    message: "Failed to store tokens in keychain",
                    details: ["status": status]
                ))
            }
        } catch {
            result(FlutterError(
                code: "SERIALIZATION_ERROR",
                message: "Failed to serialize tokens",
                details: error.localizedDescription
            ))
        }
    }
    
    private func retrieveTokensFromKeychain(arguments: [String: Any]?, result: @escaping FlutterResult) {
        guard let args = arguments,
              let biometricPrompt = args["biometric_prompt"] as? String else {
            result(FlutterError(code: "INVALID_ARGUMENTS", message: "Missing arguments", details: nil))
            return
        }
        
        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: keychainService,
            kSecAttrAccount as String: "calendar_tokens",
            kSecReturnData as String: true,
            kSecMatchLimit as String: kSecMatchLimitOne,
            kSecUseOperationPrompt as String: biometricPrompt
        ]
        
        var item: CFTypeRef?
        let status = SecItemCopyMatching(query as CFDictionary, &item)
        
        if status == errSecSuccess {
            guard let tokenData = item as? Data else {
                result(FlutterError(code: "DATA_ERROR", message: "Invalid token data", details: nil))
                return
            }
            
            do {
                let tokens = try JSONSerialization.jsonObject(with: tokenData) as? [String: Any]
                result(["tokens": tokens])
            } catch {
                result(FlutterError(
                    code: "DESERIALIZATION_ERROR",
                    message: "Failed to deserialize tokens",
                    details: error.localizedDescription
                ))
            }
        } else if status == errSecUserCancel {
            result(FlutterError(code: "USER_CANCELLED", message: "User cancelled authentication", details: nil))
        } else if status == errSecItemNotFound {
            result(["tokens": nil])
        } else {
            result(FlutterError(
                code: "KEYCHAIN_ERROR",
                message: "Failed to retrieve tokens from keychain",
                details: ["status": status]
            ))
        }
    }
    
    private func scheduleBackgroundRefresh(arguments: [String: Any]?, result: @escaping FlutterResult) {
        guard let args = arguments,
              let identifier = args["identifier"] as? String,
              let earliestBeginDate = args["earliest_begin_date"] as? Double else {
            result(FlutterError(code: "INVALID_ARGUMENTS", message: "Missing arguments", details: nil))
            return
        }
        
        let request = BGAppRefreshTaskRequest(identifier: identifier)
        request.earliestBeginDate = Date(timeIntervalSince1970: earliestBeginDate / 1000)
        
        do {
            try BGTaskScheduler.shared.submit(request)
            result(["success": true])
        } catch {
            result(FlutterError(
                code: "BACKGROUND_TASK_ERROR",
                message: "Failed to schedule background task",
                details: error.localizedDescription
            ))
        }
    }
    
    private func handleBackgroundTokenRefresh(task: BGAppRefreshTask) {
        task.expirationHandler = {
            task.setTaskCompleted(success: false)
        }
        
        // Perform token refresh
        refreshTokensInBackground { success in
            task.setTaskCompleted(success: success)
            
            // Schedule next refresh
            self.scheduleBackgroundRefresh(arguments: [
                "identifier": "calendar_token_refresh",
                "earliest_begin_date": Date().addingTimeInterval(24 * 60 * 60).timeIntervalSince1970 * 1000
            ]) { _ in }
        }
    }
    
    private func refreshTokensInBackground(completion: @escaping (Bool) -> Void) {
        // Retrieve current tokens
        retrieveTokensFromKeychain(arguments: ["biometric_prompt": "Refresh calendar tokens"]) { result in
            // Implement token refresh logic here
            // This would call your backend API to refresh the tokens
            completion(true)
        }
    }
    
    private func handleOAuthInterruption(arguments: [String: Any]?, result: @escaping FlutterResult) {
        guard let args = arguments,
              let interruptionType = args["interruption_type"] as? String else {
            result(FlutterError(code: "INVALID_ARGUMENTS", message: "Missing arguments", details: nil))
            return
        }
        
        switch interruptionType {
        case "app_backgrounded":
            // Handle app backgrounding during OAuth
            result(["can_resume": true])
        case "safari_dismissed":
            // Handle Safari dismissal
            safariViewController?.dismiss(animated: true)
            result(["can_resume": false])
        default:
            result(["can_resume": false])
        }
    }
    
    private func checkPlatformCapabilities(result: @escaping FlutterResult) {
        let context = LAContext()
        var error: NSError?
        let biometricAvailable = context.canEvaluatePolicy(.deviceOwnerAuthenticationWithBiometrics, error: &error)
        
        result([
            "safari_view_controller": true,
            "keychain_access": true,
            "background_refresh": true,
            "biometric_authentication": biometricAvailable,
            "universal_links": true
        ])
    }
    
    private func getAuthURLFromBackend() -> URL? {
        // This would make an API call to your backend to get the OAuth URL
        // For now, return a placeholder
        return URL(string: "https://accounts.google.com/oauth2/auth?client_id=your_client_id")
    }
}

// MARK: - SFSafariViewControllerDelegate
@available(iOS 13.0, *)
extension CalendarIntegrationHandler: SFSafariViewControllerDelegate {
    func safariViewController(_ controller: SFSafariViewController, didCompleteInitialLoad didLoadSuccessfully: Bool) {
        if !didLoadSuccessfully {
            pendingResult?(FlutterError(
                code: "SAFARI_LOAD_ERROR",
                message: "Safari view controller failed to load",
                details: nil
            ))
            pendingResult = nil
        }
    }
    
    func safariViewControllerDidFinish(_ controller: SFSafariViewController) {
        // User dismissed Safari
        pendingResult?(FlutterError(
            code: "USER_CANCELLED",
            message: "User cancelled OAuth",
            details: nil
        ))
        pendingResult = nil
    }
}