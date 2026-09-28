import CoreBluetooth
import Foundation

/// Pure decisions for connection recovery and GATT authentication failures.
enum OmiBleConnectionPolicy {
    enum ReadyRecoveryAction: Equatable {
        case connect
        case replayReady
        case discoverServices
    }

    /// A Dart connection request can arrive after CoreBluetooth restored a link.
    /// Reuse completed GATT discovery when possible; otherwise do one discovery
    /// for this request instead of starting another physical connection.
    static func readyRecoveryAction(
        peripheralState: CBPeripheralState,
        nativeReady: Bool,
        hasCompleteServices: Bool
    ) -> ReadyRecoveryAction {
        guard peripheralState == .connected else { return .connect }
        return nativeReady && hasCompleteServices ? .replayReady : .discoverServices
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
