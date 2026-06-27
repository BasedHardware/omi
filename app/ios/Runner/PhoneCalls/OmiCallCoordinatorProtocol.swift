import Foundation
import AVFoundation

/// Protocol defining the call coordinator contract.
/// Both `OmiCallCoordinator` (CallKit) and `OmiDirectCallCoordinator` (China/no-CallKit)
/// conform to this protocol, allowing the plugin to swap implementations at init time.
protocol OmiCallCoordinatorProtocol: AnyObject {
    /// Start an outgoing call. Completion is called once the system approves or rejects the call.
    func startCall(uuid: UUID, phoneNumber: String, contactName: String?,
                   completion: @escaping (Result<Void, Error>) -> Void)

    /// End an active call. Completion is called once the system acknowledges the end.
    func endCall(uuid: UUID, completion: @escaping (Result<Void, Error>) -> Void)

    /// Report that the call has connected (for system UI updates like the green status bar).
    func reportCallConnected(uuid: UUID)

    /// Report that the call has ended with a reason.
    func reportCallEnded(uuid: UUID, failed: Bool)

    /// Called when the audio session is activated by the system.
    /// The coordinator configures the session (sample rate, buffer, category) then calls this.
    var onAudioSessionActivated: (() -> Void)? { get set }

    /// Called when the audio session is deactivated by the system.
    var onAudioSessionDeactivated: (() -> Void)? { get set }

    /// Called when the system ends the call (e.g., from the lock screen or CallKit UI).
    var onSystemEndCall: (() -> Void)? { get set }

    /// Called when the system toggles mute (e.g., from the native CallKit UI).
    var onSystemToggleMute: ((Bool) -> Void)? { get set }

    /// Called when the provider is reset by the system (all calls should be torn down).
    var onProviderReset: (() -> Void)? { get set }
}

/// Errors from the call coordinator.
enum OmiCallCoordinatorError: LocalizedError {
    case providerNotReady
    case providerReadinessTimeout
    case coordinatorDeallocated
    case callkitRejected(String)

    var errorDescription: String? {
        switch self {
        case .providerNotReady:
            return "Call system provider is not ready"
        case .providerReadinessTimeout:
            return "Call system provider did not become ready in time"
        case .coordinatorDeallocated:
            return "Call coordinator was deallocated"
        case .callkitRejected(let detail):
            return "Call system rejected: \(detail)"
        }
    }
}
