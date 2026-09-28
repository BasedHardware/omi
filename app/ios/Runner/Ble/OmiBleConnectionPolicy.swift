import CoreBluetooth
import Foundation

/// Pure decisions for connection recovery and GATT authentication failures.
enum OmiBleConnectionPolicy {
    enum ReadyRecoveryAction: Equatable {
        case connect
        case replayReady
        case awaitDiscovery
        case discoverServices
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
        discoveryInFlight: Bool
    ) -> ReadyRecoveryAction {
        guard peripheralState == .connected else { return .connect }
        if nativeReady && hasCompleteServices { return .replayReady }
        return discoveryInFlight ? .awaitDiscovery : .discoverServices
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
