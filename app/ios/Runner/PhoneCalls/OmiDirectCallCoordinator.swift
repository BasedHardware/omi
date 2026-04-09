import Foundation
import AVFoundation

/// Call coordinator for regions where CallKit is restricted (e.g., China).
/// Manages AVAudioSession directly without CallKit — no system call UI,
/// no Phone.app recents, no green status bar.
final class OmiDirectCallCoordinator: OmiCallCoordinatorProtocol {

    var onAudioSessionActivated: (() -> Void)?
    var onAudioSessionDeactivated: (() -> Void)?
    var onSystemEndCall: (() -> Void)?
    var onSystemToggleMute: ((Bool) -> Void)?
    var onProviderReset: (() -> Void)?

    func startCall(uuid: UUID, phoneNumber: String, contactName: String?,
                   completion: @escaping (Result<Void, Error>) -> Void) {
        print("OmiDirectCallCoordinator: starting call to \(phoneNumber) (no CallKit)")

        // Configure audio session directly
        do {
            let session = AVAudioSession.sharedInstance()
            try session.setCategory(
                .playAndRecord,
                mode: .voiceChat,
                options: [.allowBluetooth, .allowBluetoothA2DP]
            )
            try session.setPreferredSampleRate(48000)
            try session.setPreferredIOBufferDuration(0.020)
            try session.setActive(true)
        } catch {
            print("OmiDirectCallCoordinator: audio session setup failed: \(error)")
            completion(.failure(error))
            return
        }

        print("OmiDirectCallCoordinator: audio session activated")
        completion(.success(()))

        DispatchQueue.main.async { [weak self] in
            self?.onAudioSessionActivated?()
        }
    }

    func endCall(uuid: UUID, completion: @escaping (Result<Void, Error>) -> Void) {
        print("OmiDirectCallCoordinator: ending call (no CallKit)")

        do {
            try AVAudioSession.sharedInstance().setActive(false, options: .notifyOthersOnDeactivation)
        } catch {
            print("OmiDirectCallCoordinator: audio session deactivation error: \(error)")
        }

        DispatchQueue.main.async { [weak self] in
            self?.onAudioSessionDeactivated?()
        }

        completion(.success(()))
    }

    func reportCallConnected(uuid: UUID) {
        // No-op: no system to report to without CallKit
    }

    func reportCallEnded(uuid: UUID, failed: Bool) {
        // No-op: no system to report to without CallKit
    }
}
