import Foundation

// Port of the state shape of `react-native/src/app/useRewindCapture.ts` —
// the desktop screen-capture toggle state, permission outcomes, and error
// copy. The macOS capture engine itself is a platform host capability
// (the native `OmiRewind` module in the RN tree): AppStore drives it through
// the injected `RewindCaptureControlling` bridge. When no bridge is
// installed (mobile, or a host that has not wired the engine yet) capture is
// honestly unavailable — no fake progress, no fake frames.

/// Native `requestCapturePermission` outcomes.
public enum RewindCapturePermission: String, Sendable, Equatable {
    case granted
    case denied
    case restartRequired
    case unsupported
}

/// Host-supplied capture engine bridge (mirrors the native `OmiRewind`
/// module surface). Absent → capture is unavailable.
public struct RewindCaptureControlling: Sendable {
    /// Probes without prompting (used by automatic starts and the
    /// availability re-probe when the app becomes active again).
    public var permissionStatus: @Sendable () async -> RewindCapturePermission
    /// Prompts for Screen Recording (explicit user-initiated starts).
    public var requestPermission: @Sendable () async -> RewindCapturePermission
    public var start: @Sendable () async throws -> Void
    public var stop: @Sendable () async throws -> Void
    /// Grabs one frame; returns whether a frame was actually captured.
    public var captureFrame: @Sendable () async -> Bool

    public init(
        permissionStatus: @escaping @Sendable () async -> RewindCapturePermission,
        requestPermission: @escaping @Sendable () async -> RewindCapturePermission,
        start: @escaping @Sendable () async throws -> Void,
        stop: @escaping @Sendable () async throws -> Void,
        captureFrame: @escaping @Sendable () async -> Bool
    ) {
        self.permissionStatus = permissionStatus
        self.requestPermission = requestPermission
        self.start = start
        self.stop = stop
        self.captureFrame = captureFrame
    }
}

/// Observable capture toggle state (`available/capturing/busy/error` from
/// `useRewindCapture`).
public struct RewindCaptureState: Sendable, Equatable {
    public var available: Bool
    public var capturing: Bool
    public var busy: Bool
    public var errorCopy: String?

    public init(
        available: Bool = false, capturing: Bool = false, busy: Bool = false,
        errorCopy: String? = nil
    ) {
        self.available = available
        self.capturing = capturing
        self.busy = busy
        self.errorCopy = errorCopy
    }
}

// Exact failure copy from useRewindCapture.ts.
public let rewindCaptureRestartCopy =
    "Restart this app to use the newly granted screen recording permission."
public let rewindCaptureUnsupportedCopy =
    "Screen capture requires macOS 14 or later."
public let rewindCaptureDeniedCopy =
    "Allow Screen Recording for this app in System Settings, then try again."
public let rewindCaptureQuotaCopy =
    "Capture stopped because this app’s Rewind storage reached its 1 GB limit."
public let rewindCaptureStoppedCopy =
    "Capture stopped. Start again when your Mac is unlocked and this account is ready."
public let rewindCaptureFrameCopy =
    "Capture stopped because a frame could not be saved. Check permission and available storage, then try again."
public let rewindCaptureStopUnconfirmedCopy =
    "Could not confirm capture stopped. Restart this app before capturing again."

/// Maps a permission outcome onto the start-failure copy (port of the
/// `permission !== 'granted'` branch in `start`).
public func rewindCapturePermissionCopy(
    _ permission: RewindCapturePermission
) -> String? {
    switch permission {
    case .granted: return nil
    case .restartRequired: return rewindCaptureRestartCopy
    case .unsupported: return rewindCaptureUnsupportedCopy
    case .denied: return rewindCaptureDeniedCopy
    }
}

/// The 3-second frame tick from `useRewindCapture`'s capture loop.
public let rewindCaptureTickMs: Int64 = 3_000
