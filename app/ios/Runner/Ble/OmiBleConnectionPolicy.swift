import CoreBluetooth
import Foundation

/// Pure decisions for connection recovery and GATT authentication failures.
enum OmiBleConnectionPolicy {
    static func savedRetryAllowed(saved: Bool, everConnected: Bool, manual: Bool, pairingLost: Bool) -> Bool {
        (saved || everConnected) && !manual && !pairingLost
    }

    static func savedRetryDelay(attempt: Int) -> TimeInterval {
        min(60, pow(2, Double(min(max(attempt - 1, 0), 6))))
    }

    static let savedScanWindow: TimeInterval = 5
    static let savedScanRest: TimeInterval = 55

    enum ReadyRecoveryAction: Equatable {
        case connect
        case replayReady
        case hydrateReady
        case awaitDiscovery
        case discoverServices
        case awaitCaptureReset
    }

    enum DiscoveryFailureAction: Equatable {
        case ignore
        case retry
        case fail
    }

    /// A later explicit request may retry discovery if CoreBluetooth never calls back.
    static let discoveryRetryAfter: TimeInterval = 15

    static func discoveryIsActive(startedAt: TimeInterval?, now: TimeInterval) -> Bool {
        guard let startedAt else { return false }
        return now - startedAt < discoveryRetryAfter
    }

    /// A Dart connection request can arrive after CoreBluetooth restored a link.
    /// Reuse completed GATT discovery when possible; otherwise do one discovery
    /// for this request instead of starting another physical connection.
    static func readyRecoveryAction(
        peripheralState: CBPeripheralState,
        nativeReady: Bool,
        hasCompleteServices: Bool,
        discoveryInFlight: Bool,
        captureResetInProgress: Bool = false
    ) -> ReadyRecoveryAction {
        if captureResetInProgress { return .awaitCaptureReset }
        guard peripheralState == .connected else { return .connect }
        if hasCompleteServices { return nativeReady ? .replayReady : .hydrateReady }
        return discoveryInFlight ? .awaitDiscovery : .discoverServices
    }

    static func captureResetCanConnect(disconnectObserved: Bool, alreadyReconnected: Bool,
                                       authorized: Bool, pairingLost: Bool) -> Bool {
        disconnectObserved && !alreadyReconnected && authorized && !pairingLost
    }

    static func captureResetReady(disconnectObserved: Bool, freshConnection: Bool, source: String) -> Bool {
        disconnectObserved && freshConnection && source == "discovery"
    }

    static func discoveryFailureAction(
        peripheralState: CBPeripheralState,
        nativeReady: Bool,
        requestPending: Bool,
        retries: Int
    ) -> DiscoveryFailureAction {
        guard peripheralState == .connected, !nativeReady, requestPending else { return .ignore }
        return retries == 0 ? .retry : .fail
    }

    static func requiresPairingRecovery(_ error: Error?) -> Bool {
        guard let error else { return false }
        let nsError = error as NSError
        guard nsError.domain == CBATTErrorDomain else { return false }
        return nsError.code == CBATTError.insufficientAuthentication.rawValue
            || nsError.code == CBATTError.insufficientAuthorization.rawValue
            || nsError.code == CBATTError.insufficientEncryptionKeySize.rawValue
            || nsError.code == CBATTError.insufficientEncryption.rawValue
    }
}

/// At most seven distinct intermediate states plus the connected outcome per outage.
struct OmiSavedReconnectTelemetry {
    private var reported: Set<String> = []
    mutating func admit(_ result: String) -> Bool {
        guard !reported.contains(result), reported.count < 7 || result == "connected" else { return false }
        reported.insert(result)
        return true
    }
}

/// Native reconnect intent must be available before the Flutter engine starts.
/// Capture authorization and recovery budgets deliberately do not enter this policy.
struct OmiSavedReconnectIntent {
    private static let savedKey = "ble_saved_reconnect_targets"
    private static let blockedKey = "ble_manual_reconnect_blocks"
    private(set) var saved: Set<String>
    private(set) var blocked: Set<String>
    private let defaults: UserDefaults

    init(defaults: UserDefaults = .standard) {
        self.defaults = defaults
        saved = Set(defaults.stringArray(forKey: Self.savedKey) ?? [])
        blocked = Set(defaults.stringArray(forKey: Self.blockedKey) ?? [])
    }

    mutating func configure(_ uuid: String, enabled: Bool) {
        if enabled { saved.insert(uuid) } else { saved.remove(uuid) }
        try? SafeDefaults.store(.array(saved.sorted().map { .string($0) }), forKey: Self.savedKey, in: defaults)
    }

    mutating func suppress(_ uuid: String) {
        blocked.insert(uuid)
        // Persist the block first: termination between writes cannot resurrect intent.
        try? SafeDefaults.store(.array(blocked.sorted().map { .string($0) }), forKey: Self.blockedKey, in: defaults)
        configure(uuid, enabled: false)
    }

    mutating func resume(_ uuid: String) {
        blocked.remove(uuid)
        try? SafeDefaults.store(.array(blocked.sorted().map { .string($0) }), forKey: Self.blockedKey, in: defaults)
    }

    /// A transport can be released by capture recovery. Only a prior explicit
    /// intent disarm turns that release into durable user suppression.
    mutating func releaseTransport(_ uuid: String) -> Bool {
        let keepReconnect = saved.contains(uuid) && !blocked.contains(uuid)
        if !keepReconnect { suppress(uuid) }
        return keepReconnect
    }

    /// Process teardown is not a user disconnect. Keep saved OS requests eligible
    /// for CoreBluetooth restoration; only unsaved/blocked owners are retired.
    func terminationTargets(_ known: Set<String>) -> Set<String> {
        known.subtracting(saved.subtracting(blocked))
    }

    enum Action { case waitForAdapter, suppressed, scan, connect, keepPending, connected }
    func action(_ uuid: String, poweredOn: Bool, state: CBPeripheralState?) -> Action {
        guard saved.contains(uuid), !blocked.contains(uuid) else { return .suppressed }
        guard poweredOn else { return .waitForAdapter }
        guard let state else { return .scan }
        switch state {
        case .connected: return .connected
        case .connecting, .disconnecting: return .keepPending
        case .disconnected: return .connect
        @unknown default: return .keepPending
        }
    }
}
