enum WifiSyncErrorCode {
  success(0x00),
  invalidPacketLength(0x01),
  invalidSetupLength(0x02),
  ssidLengthInvalid(0x03),
  passwordLengthInvalid(0x04),
  wifiHardwareNotAvailable(0xFE),
  unknownCommand(0xFF);

  final int code;
  const WifiSyncErrorCode(this.code);

  static WifiSyncErrorCode fromCode(int code) {
    return WifiSyncErrorCode.values.firstWhere(
      (e) => e.code == code,
      orElse: () => WifiSyncErrorCode.unknownCommand,
    );
  }

  String get userMessage {
    switch (this) {
      case WifiSyncErrorCode.success:
        return '';
      case WifiSyncErrorCode.invalidPacketLength:
        return 'Internal error - please try again';
      case WifiSyncErrorCode.invalidSetupLength:
        return 'Internal error - please try again';
      case WifiSyncErrorCode.ssidLengthInvalid:
        return 'Device name must be 1-32 characters';
      case WifiSyncErrorCode.passwordLengthInvalid:
        return 'Password must be 8-63 characters';
      case WifiSyncErrorCode.wifiHardwareNotAvailable:
        return 'Your device does not support WiFi sync';
      case WifiSyncErrorCode.unknownCommand:
        return 'Please update your device firmware';
    }
  }

  bool get isSuccess => this == WifiSyncErrorCode.success;
}

/// Result of a WiFi sync setup operation
class WifiSyncSetupResult {
  final bool success;
  final WifiSyncErrorCode? errorCode;
  final String? errorMessage;

  const WifiSyncSetupResult._({
    required this.success,
    this.errorCode,
    this.errorMessage,
  });

  factory WifiSyncSetupResult.success() {
    return const WifiSyncSetupResult._(success: true);
  }

  factory WifiSyncSetupResult.failure(WifiSyncErrorCode code, {String? customMessage}) {
    return WifiSyncSetupResult._(
      success: false,
      errorCode: code,
      errorMessage: customMessage ?? code.userMessage,
    );
  }

  factory WifiSyncSetupResult.timeout() {
    return const WifiSyncSetupResult._(
      success: false,
      errorMessage: 'Device did not respond - please try again',
    );
  }

  factory WifiSyncSetupResult.connectionFailed() {
    return const WifiSyncSetupResult._(
      success: false,
      errorMessage: 'Failed to communicate with device',
    );
  }
}

/// Exception thrown when WiFi sync fails
class WifiSyncException implements Exception {
  final WifiSyncErrorCode? errorCode;
  final String message;

  WifiSyncException(this.message, {this.errorCode});

  factory WifiSyncException.fromErrorCode(WifiSyncErrorCode code) {
    return WifiSyncException(code.userMessage, errorCode: code);
  }

  @override
  String toString() => 'WifiSyncException: $message';
}

/// Validation helper for WiFi credentials
class WifiCredentialsValidator {
  static const int maxSsidLength = 32;
  static const int minPasswordLength = 8;
  static const int maxPasswordLength = 63;

  /// Validates SSID and returns error message if invalid, null if valid
  static String? validateSsid(String ssid) {
    if (ssid.isEmpty) {
      return 'Network name is required';
    }
    if (ssid.length > maxSsidLength) {
      return 'Network name must be at most $maxSsidLength characters';
    }
    // Check byte length (UTF-8 encoded)
    final byteLength = ssid.codeUnits.length;
    if (byteLength > maxSsidLength) {
      return 'Network name is too long';
    }
    return null;
  }

  /// Validates password and returns error message if invalid, null if valid
  static String? validatePassword(String password) {
    if (password.isEmpty) {
      return 'Password is required';
    }
    if (password.length < minPasswordLength) {
      return 'Password must be at least $minPasswordLength characters';
    }
    if (password.length > maxPasswordLength) {
      return 'Password must be at most $maxPasswordLength characters';
    }
    // Check byte length (UTF-8 encoded)
    final byteLength = password.codeUnits.length;
    if (byteLength > maxPasswordLength) {
      return 'Password is too long';
    }
    return null;
  }

  /// Validates both SSID and password, returns first error or null if both valid
  static String? validate(String ssid, String password) {
    return validateSsid(ssid) ?? validatePassword(password);
  }
}
