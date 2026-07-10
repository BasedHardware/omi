/// Base class for all errors raised by `meta_wearables_dat_flutter`.
///
/// The plugin maps native [PlatformException]s with known DAT codes to one of
/// the typed subclasses below ([RegistrationError], [UnregistrationError],
/// [HandleUrlError], [PermissionError], [DeviceSessionError],
/// [SessionError] (== `StreamSessionError`), [CaptureError]) so host apps
/// can `try` / `on` against the concrete category. Anything the plugin does
/// not recognise is surfaced as the base [DatError].
class DatError implements Exception {
  /// Creates a [DatError].
  const DatError({
    required this.code,
    required this.message,
    this.details,
  });

  /// Machine-readable code, mirroring the upstream SDK's error category.
  final String code;

  /// Human-readable message. Safe to show to developers; not safe to show
  /// to end users without translation.
  final String message;

  /// Optional structured payload that accompanies some errors.
  final Object? details;

  @override
  String toString() => 'DatError(code: $code, message: $message)';
}

/// An error raised by the registration flow
/// ([MetaWearablesDat.startRegistration],
/// [MetaWearablesDat.startUnregistration], [MetaWearablesDat.handleUrl]).
///
/// Use the `is*` convenience getters to inspect specific cases without
/// hardcoding the [code] string in host code.
class RegistrationError extends DatError {
  /// Creates a [RegistrationError].
  const RegistrationError({
    required super.code,
    required super.message,
    super.details,
  });

  /// True when the host app's `Info.plist` / `AndroidManifest.xml`
  /// validation failed (e.g. missing `MWDAT` keys, invalid URL scheme).
  bool get isConfigurationInvalid => code == DatErrorCodes.configurationInvalid;

  /// True when the Meta AI companion app is not installed (or is too old).
  bool get isMetaAiNotInstalled => code == DatErrorCodes.metaAiNotInstalled;

  /// True when the host app is already registered for this device.
  bool get isAlreadyRegistered => code == DatErrorCodes.alreadyRegistered;

  /// True when the registration handshake required an internet connection
  /// that was unavailable.
  bool get isNetworkUnavailable => code == DatErrorCodes.networkUnavailable;

  @override
  String toString() => 'RegistrationError(code: $code, message: $message)';
}

/// An error raised by [MetaWearablesDat.startUnregistration].
class UnregistrationError extends DatError {
  /// Creates an [UnregistrationError].
  const UnregistrationError({
    required super.code,
    required super.message,
    super.details,
  });

  /// True when the host app is not currently registered, so there is
  /// nothing to unregister.
  bool get isNotRegistered => code == DatErrorCodes.notRegistered;

  @override
  String toString() => 'UnregistrationError(code: $code, message: $message)';
}

/// An error raised by [MetaWearablesDat.handleUrl].
class HandleUrlError extends DatError {
  /// Creates a [HandleUrlError].
  const HandleUrlError({
    required super.code,
    required super.message,
    super.details,
  });

  /// True when the URL handed to `handleUrl` did not belong to a
  /// registration callback.
  bool get isInvalidUrl => code == DatErrorCodes.invalidUrl;

  @override
  String toString() => 'HandleUrlError(code: $code, message: $message)';
}

/// An error raised when a permission cannot be requested or has been denied.
///
/// Includes both Android runtime permissions (Bluetooth, Internet) and the
/// Meta-AI-bottom-sheet-driven on-device camera permission.
class PermissionError extends DatError {
  /// Creates a [PermissionError].
  const PermissionError({
    required super.code,
    required super.message,
    super.details,
  });

  /// True when the host activity does not extend `FlutterFragmentActivity`
  /// / `ComponentActivity` (Android only).
  bool get isMissingFragmentActivity => code == DatErrorCodes.missingFragmentActivity;

  /// True when the user denied the permission via the Meta AI bottom sheet.
  bool get isDenied => code == DatErrorCodes.permissionDenied;

  @override
  String toString() => 'PermissionError(code: $code, message: $message)';
}

/// An error raised by the underlying `DeviceSession` (separate from
/// stream-level errors).
///
/// Surfaced by [MetaWearablesDat.deviceSessionErrorStream]. Mirrors the
/// `DeviceSessionError` enum in Meta's iOS / Android DAT SDKs.
class DeviceSessionError extends DatError {
  /// Creates a [DeviceSessionError].
  const DeviceSessionError({
    required super.code,
    required super.message,
    super.details,
  });

  /// True when the SDK could not find any device eligible to host a
  /// session (no paired glasses, none connected, none donned).
  bool get isNoEligibleDevice => code == DatErrorCodes.noEligibleDevice;

  /// True when a `stop()` was issued against a session that was already
  /// stopped.
  bool get isSessionAlreadyStopped => code == DatErrorCodes.sessionAlreadyStopped;

  /// True when `createSession()` was called while a session already exists
  /// for the same selector.
  bool get isSessionAlreadyExists => code == DatErrorCodes.sessionAlreadyExists;

  /// True when an operation required the session to be started but the
  /// session is idle.
  bool get isSessionIdle => code == DatErrorCodes.sessionIdle;

  /// True when `addStream()` was called for a capability that is already
  /// active.
  bool get isCapabilityAlreadyActive => code == DatErrorCodes.capabilityAlreadyActive;

  /// True when the requested capability is not available on the connected
  /// device.
  bool get isCapabilityNotFound => code == DatErrorCodes.capabilityNotFound;

  /// True when the DAT app running on the glasses is too old to host the
  /// requested session and must be updated (added in DAT 0.7.0).
  bool get isDatAppUpdateRequired => code == DatErrorCodes.datAppUpdateRequired;

  /// True for any error the plugin could not map to a known case.
  bool get isUnexpectedError => code == DatErrorCodes.unexpectedError;

  @override
  String toString() => 'DeviceSessionError(code: $code, message: $message)';
}

/// An error raised by a streaming session
/// ([MetaWearablesDat.startStreamSession], [MetaWearablesDat.stopStreamSession],
/// etc.). Also accessible under the alias [StreamSessionError].
class SessionError extends DatError {
  /// Creates a [SessionError].
  const SessionError({
    required super.code,
    required super.message,
    super.details,
  });

  /// True when the device entered a thermally-critical state and the
  /// stream was paused or stopped.
  bool get isThermalCritical => code == DatErrorCodes.thermalCritical;

  /// True when the glasses' hinges closed mid-stream.
  bool get isHingesClosed => code == DatErrorCodes.hingesClosed;

  /// True when the device-side camera permission was not granted (or was
  /// revoked).
  bool get isPermissionDenied => code == DatErrorCodes.permissionDenied;

  /// True when the underlying device disconnected during streaming.
  bool get isDeviceDisconnected => code == DatErrorCodes.deviceDisconnected;

  /// True when the SDK reported `videoStreamingError`.
  bool get isVideoStreamingError => code == DatErrorCodes.videoStreamingError;

  /// True when the SDK reported an internal error.
  bool get isInternalError => code == DatErrorCodes.internalError;

  /// True when the SDK timed out waiting for a device-side response.
  bool get isTimeout => code == DatErrorCodes.timeout;

  @override
  String toString() => 'SessionError(code: $code, message: $message)';
}

/// Alias matching Meta SDK naming (`StreamSessionError`).
typedef StreamSessionError = SessionError;

/// An error raised by a still-capture call ([MetaWearablesDat.capturePhoto]
/// or [MetaWearablesDat.captureStreamFrame]).
class CaptureError extends DatError {
  /// Creates a [CaptureError].
  const CaptureError({
    required super.code,
    required super.message,
    super.details,
  });

  /// True when the underlying device disconnected mid-capture.
  bool get isDeviceDisconnected => code == DatErrorCodes.deviceDisconnected;

  /// True when another capture was already in flight.
  bool get isCaptureInProgress => code == DatErrorCodes.captureInProgress;

  /// True when the device-side capture pipeline failed.
  bool get isCaptureFailed => code == DatErrorCodes.captureFailed;

  /// True when `capturePhoto` was called without an active stream session.
  bool get isNotStreaming => code == DatErrorCodes.notStreaming;

  @override
  String toString() => 'CaptureError(code: $code, message: $message)';
}

/// Well-known error codes used by [DatError.code]. Mirrors the categories
/// emitted by Meta's iOS / Android typed `*Error` enums.
abstract final class DatErrorCodes {
  // --- Category codes (used by PlatformException.code) --------------------

  /// The registration flow could not be started or completed.
  static const String registration = 'REGISTRATION_ERROR';

  /// The unregistration flow could not be started or completed.
  static const String unregistration = 'UNREGISTRATION_ERROR';

  /// `handleUrl` failed to consume the inbound URL.
  static const String handleUrl = 'HANDLE_URL_ERROR';

  /// A wearable-side permission (e.g. camera) is not granted.
  static const String permission = 'PERMISSION_ERROR';

  /// A `DeviceSession` operation failed.
  static const String deviceSession = 'DEVICE_SESSION_ERROR';

  /// A streaming session failed to start, was interrupted, or could not
  /// be torn down cleanly.
  static const String session = 'SESSION_ERROR';

  /// A photo or frame capture failed.
  static const String capture = 'CAPTURE_ERROR';

  /// The Android host activity does not extend `FlutterFragmentActivity` /
  /// `ComponentActivity`.
  static const String missingFragmentActivity = 'MISSING_FRAGMENT_ACTIVITY';

  // --- Sub-codes (used by typed event channels for is* getters) -----------

  /// RegistrationError.configurationInvalid
  static const String configurationInvalid = 'configurationInvalid';

  /// RegistrationError.metaAINotInstalled
  static const String metaAiNotInstalled = 'metaAiNotInstalled';

  /// RegistrationError.alreadyRegistered
  static const String alreadyRegistered = 'alreadyRegistered';

  /// RegistrationError.networkUnavailable
  static const String networkUnavailable = 'networkUnavailable';

  /// UnregistrationError.notRegistered
  static const String notRegistered = 'notRegistered';

  /// HandleUrlError.invalidUrl
  static const String invalidUrl = 'invalidUrl';

  /// PermissionError.permissionDenied
  static const String permissionDenied = 'permissionDenied';

  /// DeviceSessionError.noEligibleDevice
  static const String noEligibleDevice = 'noEligibleDevice';

  /// DeviceSessionError.sessionAlreadyStopped
  static const String sessionAlreadyStopped = 'sessionAlreadyStopped';

  /// DeviceSessionError.sessionAlreadyExists
  static const String sessionAlreadyExists = 'sessionAlreadyExists';

  /// DeviceSessionError.sessionIdle
  static const String sessionIdle = 'sessionIdle';

  /// DeviceSessionError.capabilityAlreadyActive
  static const String capabilityAlreadyActive = 'capabilityAlreadyActive';

  /// DeviceSessionError.capabilityNotFound
  static const String capabilityNotFound = 'capabilityNotFound';

  /// DeviceSessionError.datAppUpdateRequired — the on-glasses DAT app must
  /// be updated before a session can start (added in DAT 0.7.0).
  static const String datAppUpdateRequired = 'datAppUpdateRequired';

  /// DeviceSessionError.unexpectedError (fallback bucket).
  static const String unexpectedError = 'unexpectedError';

  /// SessionError.thermalCritical
  static const String thermalCritical = 'thermalCritical';

  /// SessionError.hingesClosed
  static const String hingesClosed = 'hingesClosed';

  /// SessionError.deviceDisconnected
  static const String deviceDisconnected = 'deviceDisconnected';

  /// SessionError.videoStreamingError
  static const String videoStreamingError = 'videoStreamingError';

  /// SessionError.internalError
  static const String internalError = 'internalError';

  /// SessionError.timeout
  static const String timeout = 'timeout';

  /// CaptureError.captureInProgress
  static const String captureInProgress = 'captureInProgress';

  /// CaptureError.captureFailed
  static const String captureFailed = 'captureFailed';

  /// CaptureError.notStreaming
  static const String notStreaming = 'notStreaming';
}
