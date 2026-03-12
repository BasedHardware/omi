import Foundation

// MARK: - WiFi Sync Error Codes

/// Error codes for WiFi sync operations
/// Ported from: omi/app/lib/services/devices/wifi_sync_error.dart
enum WifiSyncErrorCode: Int, CaseIterable {
    case success = 0x00
    case invalidPacketLength = 0x01
    case invalidSetupLength = 0x02
    case ssidLengthInvalid = 0x03
    case passwordLengthInvalid = 0x04
    case sessionAlreadyRunning = 0x05
    case wifiHardwareNotAvailable = 0xFE
    case unknownCommand = 0xFF

    /// Create from raw response code
    static func from(code: Int) -> WifiSyncErrorCode {
        WifiSyncErrorCode(rawValue: code) ?? .unknownCommand
    }

    /// User-friendly error message
    var userMessage: String {
        switch self {
        case .success:
            return ""
        case .invalidPacketLength:
            return "Internal error - please try again"
        case .invalidSetupLength:
            return "Internal error - please try again"
        case .ssidLengthInvalid:
            return "Network name must be 1-32 characters"
        case .passwordLengthInvalid:
            return "Password must be 8-63 characters"
        case .sessionAlreadyRunning:
            return "Previous sync session is still running"
        case .wifiHardwareNotAvailable:
            return "Your device does not support WiFi sync"
        case .unknownCommand:
            return "Please update your device firmware"
        }
    }

    /// Whether this is a success code
    var isSuccess: Bool {
        self == .success
    }
}

// MARK: - WiFi Sync Setup Result

/// Result of a WiFi sync setup operation
struct WifiSyncSetupResult {
    let success: Bool
    let errorCode: WifiSyncErrorCode?
    let errorMessage: String?

    private init(success: Bool, errorCode: WifiSyncErrorCode? = nil, errorMessage: String? = nil) {
        self.success = success
        self.errorCode = errorCode
        self.errorMessage = errorMessage
    }

    /// Create a success result
    static func success() -> WifiSyncSetupResult {
        WifiSyncSetupResult(success: true)
    }

    /// Create a failure result with error code
    static func failure(_ code: WifiSyncErrorCode, customMessage: String? = nil) -> WifiSyncSetupResult {
        WifiSyncSetupResult(
            success: false,
            errorCode: code,
            errorMessage: customMessage ?? code.userMessage
        )
    }

    /// Create a timeout result
    static func timeout() -> WifiSyncSetupResult {
        WifiSyncSetupResult(
            success: false,
            errorMessage: "Device did not respond - please try again"
        )
    }

    /// Create a connection failed result
    static func connectionFailed() -> WifiSyncSetupResult {
        WifiSyncSetupResult(
            success: false,
            errorMessage: "Failed to communicate with device"
        )
    }
}

// MARK: - WiFi Sync Exception

/// Exception thrown when WiFi sync fails
struct WifiSyncError: LocalizedError {
    let errorCode: WifiSyncErrorCode?
    let message: String

    init(_ message: String, errorCode: WifiSyncErrorCode? = nil) {
        self.message = message
        self.errorCode = errorCode
    }

    static func from(errorCode: WifiSyncErrorCode) -> WifiSyncError {
        WifiSyncError(errorCode.userMessage, errorCode: errorCode)
    }

    var errorDescription: String? {
        message
    }
}

// MARK: - WiFi Credentials Validator

/// Validation helper for WiFi credentials
struct WifiCredentialsValidator {
    static let maxSsidLength = 32
    static let minPasswordLength = 8
    static let maxPasswordLength = 63

    /// Validates SSID and returns error message if invalid, nil if valid
    static func validateSsid(_ ssid: String) -> String? {
        if ssid.isEmpty {
            return "Network name is required"
        }
        if ssid.count > maxSsidLength {
            return "Network name must be at most \(maxSsidLength) characters"
        }
        // Check byte length (UTF-8 encoded)
        let byteLength = ssid.utf8.count
        if byteLength > maxSsidLength {
            return "Network name is too long"
        }
        return nil
    }

    /// Validates password and returns error message if invalid, nil if valid
    static func validatePassword(_ password: String) -> String? {
        if password.isEmpty {
            return "Password is required"
        }
        if password.count < minPasswordLength {
            return "Password must be at least \(minPasswordLength) characters"
        }
        if password.count > maxPasswordLength {
            return "Password must be at most \(maxPasswordLength) characters"
        }
        // Check byte length (UTF-8 encoded)
        let byteLength = password.utf8.count
        if byteLength > maxPasswordLength {
            return "Password is too long"
        }
        return nil
    }

    /// Validates both SSID and password, returns first error or nil if both valid
    static func validate(ssid: String, password: String) -> String? {
        validateSsid(ssid) ?? validatePassword(password)
    }
}
