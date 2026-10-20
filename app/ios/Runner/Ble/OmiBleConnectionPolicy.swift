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
