import Foundation
import AVFoundation
import CallKit

/// CallKit-based call coordinator with provider reset recovery and readiness tracking.
///
/// Thread safety: All state mutations happen on `queue`. The CXProviderDelegate callbacks
/// are dispatched onto `queue` by setting it as the delegate queue.
///
/// Provider reset recovery: When the system resets the provider (e.g., Do Not Disturb toggle),
/// the coordinator invalidates, recreates, and re-signals readiness. Pending call completions
/// are failed with `.providerNotReady`.
final class OmiCallCoordinator: NSObject, OmiCallCoordinatorProtocol {

    // MARK: - Protocol callbacks

    var onAudioSessionActivated: (() -> Void)?
    var onAudioSessionDeactivated: (() -> Void)?
    var onSystemEndCall: (() -> Void)?
    var onSystemToggleMute: ((Bool) -> Void)?
    var onProviderReset: (() -> Void)?

    // MARK: - State (protected by queue)

    private let queue = DispatchQueue(label: "com.omi.callcoordinator")

    private var provider: CXProvider?
    private let callController = CXCallController()
    private var isProviderReady = false

    // Pending completions keyed by call UUID
    private var pendingStartCalls: [UUID: (Result<Void, Error>) -> Void] = [:]
    private var pendingEndCalls: [UUID: (Result<Void, Error>) -> Void] = [:]

    // Waiters for provider readiness
    private var providerReadyWaiters: [(Result<Void, Error>) -> Void] = []

    private static let readinessTimeoutSeconds: TimeInterval = 3.0

    // MARK: - Init / Deinit

    override init() {
        super.init()
        setupProvider()
    }

    deinit {
        // Fail all pending operations
        for (_, completion) in pendingStartCalls {
            completion(.failure(OmiCallCoordinatorError.coordinatorDeallocated))
        }
        pendingStartCalls.removeAll()

        for (_, completion) in pendingEndCalls {
            completion(.failure(OmiCallCoordinatorError.coordinatorDeallocated))
        }
        pendingEndCalls.removeAll()

        for waiter in providerReadyWaiters {
            waiter(.failure(OmiCallCoordinatorError.coordinatorDeallocated))
        }
        providerReadyWaiters.removeAll()

        provider?.invalidate()
        provider = nil
    }

    // MARK: - Provider Setup

    private func setupProvider() {
        let configuration = CXProviderConfiguration()
        configuration.maximumCallGroups = 1
        configuration.maximumCallsPerCallGroup = 1
        configuration.supportsVideo = false
        configuration.supportedHandleTypes = [.phoneNumber]

        let newProvider = CXProvider(configuration: configuration)
        newProvider.setDelegate(self, queue: queue)
        provider = newProvider
        isProviderReady = false

        print("OmiCallCoordinator: provider configured, waiting for readiness")
    }

    /// Waits for the provider to become ready, with a timeout.
    private func ensureProviderReady(completion: @escaping (Result<Void, Error>) -> Void) {
        queue.async { [weak self] in
            guard let self = self else {
                completion(.failure(OmiCallCoordinatorError.coordinatorDeallocated))
                return
            }

            if self.isProviderReady {
                completion(.success(()))
                return
            }

            // Store waiter
            self.providerReadyWaiters.append(completion)

            // Schedule timeout
            self.queue.asyncAfter(deadline: .now() + Self.readinessTimeoutSeconds) { [weak self] in
                guard let self = self else { return }
                // If still waiting, fail
                if !self.providerReadyWaiters.isEmpty && !self.isProviderReady {
                    let waiters = self.providerReadyWaiters
                    self.providerReadyWaiters.removeAll()
                    for waiter in waiters {
                        waiter(.failure(OmiCallCoordinatorError.providerReadinessTimeout))
                    }
                }
            }
        }
    }

    // MARK: - OmiCallCoordinatorProtocol

    func startCall(uuid: UUID, phoneNumber: String, contactName: String?,
                   completion: @escaping (Result<Void, Error>) -> Void) {
        ensureProviderReady { [weak self] result in
            guard let self = self else {
                completion(.failure(OmiCallCoordinatorError.coordinatorDeallocated))
                return
            }

            switch result {
            case .failure(let error):
                completion(.failure(error))
            case .success:
                self.queue.async {
                    self.pendingStartCalls[uuid] = completion

                    let handle = CXHandle(type: .phoneNumber, value: phoneNumber)
                    let action = CXStartCallAction(call: uuid, handle: handle)
                    action.isVideo = false
                    action.contactIdentifier = contactName

                    let transaction = CXTransaction(action: action)

                    print("OmiCallCoordinator: requesting start call for \(phoneNumber)")

                    self.callController.request(transaction) { [weak self] error in
                        guard let self = self else { return }
                        self.queue.async {
                            if let error = error {
                                print("OmiCallCoordinator: start call rejected: \(error.localizedDescription)")
                                let pending = self.pendingStartCalls.removeValue(forKey: uuid)
                                pending?(.failure(OmiCallCoordinatorError.callkitRejected(error.localizedDescription)))
                            }
                            // On success, completion is called from the CXProviderDelegate callback
                        }
                    }
                }
            }
        }
    }

    func endCall(uuid: UUID, completion: @escaping (Result<Void, Error>) -> Void) {
        queue.async { [weak self] in
            guard let self = self else {
                completion(.failure(OmiCallCoordinatorError.coordinatorDeallocated))
                return
            }

            self.pendingEndCalls[uuid] = completion

            let action = CXEndCallAction(call: uuid)
            let transaction = CXTransaction(action: action)

            self.callController.request(transaction) { [weak self] error in
                guard let self = self else { return }
                self.queue.async {
                    if let error = error {
                        print("OmiCallCoordinator: end call error: \(error.localizedDescription)")
                        let pending = self.pendingEndCalls.removeValue(forKey: uuid)
                        pending?(.failure(OmiCallCoordinatorError.callkitRejected(error.localizedDescription)))
                    }
                    // On success, completion is called from the CXProviderDelegate callback
                }
            }
        }
    }

    func reportCallConnected(uuid: UUID) {
        queue.async { [weak self] in
            self?.provider?.reportOutgoingCall(with: uuid, connectedAt: Date())
        }
    }

    func reportCallEnded(uuid: UUID, failed: Bool) {
        queue.async { [weak self] in
            let reason: CXCallEndedReason = failed ? .failed : .remoteEnded
            self?.provider?.reportCall(with: uuid, endedAt: Date(), reason: reason)
        }
    }
}

// MARK: - CXProviderDelegate

extension OmiCallCoordinator: CXProviderDelegate {

    func providerDidBegin(_ provider: CXProvider) {
        print("OmiCallCoordinator: provider did begin (ready)")
        isProviderReady = true

        // Resume all readiness waiters
        let waiters = providerReadyWaiters
        providerReadyWaiters.removeAll()
        for waiter in waiters {
            waiter(.success(()))
        }
    }

    func providerDidReset(_ provider: CXProvider) {
        print("OmiCallCoordinator: provider reset")

        // Fail all pending start calls
        for (_, completion) in pendingStartCalls {
            completion(.failure(OmiCallCoordinatorError.providerNotReady))
        }
        pendingStartCalls.removeAll()

        // Fail all pending end calls
        for (_, completion) in pendingEndCalls {
            completion(.failure(OmiCallCoordinatorError.providerNotReady))
        }
        pendingEndCalls.removeAll()

        // Notify plugin to tear down
        DispatchQueue.main.async { [weak self] in
            self?.onProviderReset?()
        }

        // Invalidate and recreate
        self.provider?.invalidate()
        self.provider = nil
        isProviderReady = false

        print("OmiCallCoordinator: scheduling provider reconfiguration")
        queue.asyncAfter(deadline: .now() + 0.5) { [weak self] in
            self?.setupProvider()
        }
    }

    func provider(_ provider: CXProvider, perform action: CXStartCallAction) {
        print("OmiCallCoordinator: CXStartCallAction")

        // Report connecting
        provider.reportOutgoingCall(with: action.callUUID, startedConnectingAt: Date())

        // Resume the pending completion
        let completion = pendingStartCalls.removeValue(forKey: action.callUUID)
        completion?(.success(()))

        action.fulfill()
    }

    func provider(_ provider: CXProvider, perform action: CXEndCallAction) {
        print("OmiCallCoordinator: CXEndCallAction — UUID: \(action.callUUID)")

        let completion = pendingEndCalls.removeValue(forKey: action.callUUID)
        completion?(.success(()))

        DispatchQueue.main.async { [weak self] in
            self?.onSystemEndCall?()
        }

        action.fulfill()
    }

    func provider(_ provider: CXProvider, perform action: CXSetMutedCallAction) {
        DispatchQueue.main.async { [weak self] in
            self?.onSystemToggleMute?(action.isMuted)
        }
        action.fulfill()
    }

    func provider(_ provider: CXProvider, didActivate audioSession: AVAudioSession) {
        // Configure audio session: 48kHz, 20ms buffer, voice chat with Bluetooth
        // 20ms is critical — 5ms corrupts AirPods audio, tested extensively
        do {
            try audioSession.setCategory(
                .playAndRecord,
                mode: .default,
                options: [.allowBluetooth, .allowBluetoothA2DP]
            )
            try audioSession.setPreferredSampleRate(48000)
            try audioSession.setPreferredIOBufferDuration(0.020)
        } catch {
            print("OmiCallCoordinator: audio session config error: \(error)")
        }

        print("OmiCallCoordinator: audio session activated (rate: \(audioSession.sampleRate)Hz, buffer: \(audioSession.ioBufferDuration * 1000)ms)")

        DispatchQueue.main.async { [weak self] in
            self?.onAudioSessionActivated?()
        }
    }

    func provider(_ provider: CXProvider, didDeactivate audioSession: AVAudioSession) {
        print("OmiCallCoordinator: audio session deactivated")
        DispatchQueue.main.async { [weak self] in
            self?.onAudioSessionDeactivated?()
        }
    }

    func provider(_ provider: CXProvider, timedOutPerforming action: CXAction) {
        print("OmiCallCoordinator: timed out performing \(type(of: action))")
        if let startAction = action as? CXStartCallAction {
            let completion = pendingStartCalls.removeValue(forKey: startAction.callUUID)
            completion?(.failure(OmiCallCoordinatorError.providerReadinessTimeout))
        }
        action.fulfill()
    }
}
