import AVFoundation
import CallKit

/// Who owns the call's audio session: CallKit (system call UI, lock screen, Recents) or, where CallKit
/// is not allowed, the app itself. Flutter `OmiCallCoordinatorProtocol`.
@MainActor
protocol CallSystemCoordinator: AnyObject {
    var onAudioSessionActivated: (() -> Void)? { get set }
    var onSystemEndCall: (() -> Void)? { get set }
    var onSystemMute: ((Bool) -> Void)? { get set }
    var onReset: (() -> Void)? { get set }

    /// Returns once the system allowed the call.
    func startCall(uuid: UUID, phoneNumber: String, contactName: String?) async throws
    func endCall(uuid: UUID)
    func reportConnected(uuid: UUID)
    func reportEnded(uuid: UUID, failed: Bool)
}

enum CallSystemError: LocalizedError {
    case notReady
    case rejected(String)

    var errorDescription: String? {
        switch self {
        case .notReady: "The call system is not ready"
        case let .rejected(detail): "The call system rejected the call: \(detail)"
        }
    }
}

/// 48 kHz with 20 ms buffers (shorter buffers garble AirPods, per the Flutter app's testing).
enum CallAudioSession {
    static func configure(_ session: AVAudioSession, mode: AVAudioSession.Mode) throws {
        try session.setCategory(.playAndRecord, mode: mode, options: [.allowBluetoothHFP, .allowBluetoothA2DP])
        try session.setPreferredSampleRate(48000)
        try session.setPreferredIOBufferDuration(0.020)
    }
}

/// CallKit: the call shows like any phone call. The provider's delegate runs on the main queue.
/// Recovers from a provider reset (Do Not Disturb toggles) by building a new provider.
@MainActor
final class CallKitCoordinator: NSObject, CallSystemCoordinator {
    var onAudioSessionActivated: (() -> Void)?
    var onSystemEndCall: (() -> Void)?
    var onSystemMute: ((Bool) -> Void)?
    var onReset: (() -> Void)?

    private var provider: CXProvider?
    private let controller = CXCallController()
    private var isReady = false
    private var pendingStarts: [UUID: CheckedContinuation<Void, any Error>] = [:]
    private var names: [UUID: String] = [:]

    override init() {
        super.init()
        makeProvider()
    }

    private func makeProvider() {
        let configuration = CXProviderConfiguration()
        configuration.maximumCallGroups = 1
        configuration.maximumCallsPerCallGroup = 1
        configuration.supportsVideo = false
        configuration.supportedHandleTypes = [.phoneNumber]
        let provider = CXProvider(configuration: configuration)
        provider.setDelegate(self, queue: nil)
        self.provider = provider
        isReady = false
    }

    func startCall(uuid: UUID, phoneNumber: String, contactName: String?) async throws {
        // `providerDidBegin` arrives right after the provider is made; wait up to 3 s like Flutter.
        for _ in 0 ..< 60 where !isReady {
            try await Task.sleep(for: .milliseconds(50))
        }
        guard isReady else { throw CallSystemError.notReady }
        if let contactName { names[uuid] = contactName }
        let action = CXStartCallAction(call: uuid, handle: CXHandle(type: .phoneNumber, value: phoneNumber))
        try await withCheckedThrowingContinuation { (continuation: CheckedContinuation<Void, any Error>) in
            pendingStarts[uuid] = continuation
            controller.request(CXTransaction(action: action)) { [weak self] error in
                guard let error else { return } // success resumes in `perform CXStartCallAction`
                Task { @MainActor in
                    self?.pendingStarts.removeValue(forKey: uuid)?.resume(throwing: CallSystemError.rejected(error.localizedDescription))
                }
            }
        }
    }

    func endCall(uuid: UUID) {
        controller.request(CXTransaction(action: CXEndCallAction(call: uuid))) { _ in }
    }

    func reportConnected(uuid: UUID) {
        provider?.reportOutgoingCall(with: uuid, connectedAt: Date())
    }

    func reportEnded(uuid: UUID, failed: Bool) {
        provider?.reportCall(with: uuid, endedAt: Date(), reason: failed ? .failed : .remoteEnded)
    }
}

extension CallKitCoordinator: @preconcurrency CXProviderDelegate {
    func providerDidBegin(_: CXProvider) {
        isReady = true
    }

    func providerDidReset(_ provider: CXProvider) {
        for continuation in pendingStarts.values {
            continuation.resume(throwing: CallSystemError.notReady)
        }
        pendingStarts = [:]
        onReset?()
        provider.invalidate()
        self.provider = nil
        isReady = false
        Task { @MainActor [weak self] in
            try? await Task.sleep(for: .milliseconds(500))
            self?.makeProvider()
        }
    }

    func provider(_ provider: CXProvider, perform action: CXStartCallAction) {
        provider.reportOutgoingCall(with: action.callUUID, startedConnectingAt: Date())
        if let name = names.removeValue(forKey: action.callUUID) {
            let update = CXCallUpdate()
            update.remoteHandle = action.handle
            update.localizedCallerName = name
            provider.reportCall(with: action.callUUID, updated: update)
        }
        pendingStarts.removeValue(forKey: action.callUUID)?.resume()
        action.fulfill()
    }

    func provider(_: CXProvider, perform action: CXEndCallAction) {
        onSystemEndCall?()
        action.fulfill()
    }

    func provider(_: CXProvider, perform action: CXSetMutedCallAction) {
        onSystemMute?(action.isMuted)
        action.fulfill()
    }

    func provider(_: CXProvider, didActivate audioSession: AVAudioSession) {
        try? CallAudioSession.configure(audioSession, mode: .default)
        onAudioSessionActivated?()
    }

    func provider(_: CXProvider, didDeactivate _: AVAudioSession) {}

    func provider(_: CXProvider, timedOutPerforming action: CXAction) {
        if let start = action as? CXStartCallAction {
            pendingStarts.removeValue(forKey: start.callUUID)?.resume(throwing: CallSystemError.notReady)
        }
        action.fulfill()
    }
}

/// Without CallKit (China): the app activates the audio session itself; no system call UI.
@MainActor
final class DirectCallCoordinator: CallSystemCoordinator {
    var onAudioSessionActivated: (() -> Void)?
    var onSystemEndCall: (() -> Void)?
    var onSystemMute: ((Bool) -> Void)?
    var onReset: (() -> Void)?

    func startCall(uuid _: UUID, phoneNumber _: String, contactName _: String?) async throws {
        let session = AVAudioSession.sharedInstance()
        try CallAudioSession.configure(session, mode: .voiceChat)
        try session.setActive(true)
        onAudioSessionActivated?()
    }

    func endCall(uuid _: UUID) {
        try? AVAudioSession.sharedInstance().setActive(false, options: .notifyOthersOnDeactivation)
    }

    func reportConnected(uuid _: UUID) {}

    func reportEnded(uuid: UUID, failed _: Bool) {
        endCall(uuid: uuid)
    }
}
