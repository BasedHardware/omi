import Foundation
import OmiKit

// Port of the state layer of `react-native/src/app/DeviceSession.tsx` —
// the `homeConnectionStatus` derivation — as a pure function over the
// AppStore's device state. Pure logic only, unit-testable.

/// One home-status reading: the coarse status enum plus the exact label the
/// surfaces render. (The TS also returns a color; surfaces own color tokens.)
public struct HomeStatusRead: Sendable, Equatable {
    public var status: HomeConnectionStatus
    public var label: String

    public init(status: HomeConnectionStatus, label: String) {
        self.status = status
        self.label = label
    }
}

/// Port of `bluetoothStatusLabel` (app/bluetooth.ts) for the native
/// `BluetoothState` vocabulary (no web Bluetooth states here).
public func bluetoothStatusLabel(_ state: BluetoothState) -> String {
    switch state {
    case .poweredOn: return "Bluetooth on"
    case .unauthorized: return "Bluetooth permission needed"
    case .poweredOff: return "Bluetooth off"
    case .unknown: return "Bluetooth status unknown"
    }
}

/// Port of `homeConnectionStatus(snapshot)`:
/// - connecting phase wins → "Connecting to Omi…"
/// - no snapshot yet → "Checking Bluetooth…"
/// - no connected device → "Omi disconnected" (radio on) or the Bluetooth
///   status label otherwise
/// - connected → "Connected · Ready / Waiting for audio / Listening" from
///   the capture stage.
public func homeConnectionStatus(
    hasSnapshot: Bool,
    bluetoothState: BluetoothState,
    phaseConnecting: Bool,
    connectedDeviceName: String?,
    captureStage: CaptureStage
) -> HomeStatusRead {
    if phaseConnecting {
        return HomeStatusRead(status: .connecting, label: "Connecting to Omi…")
    }
    guard hasSnapshot else {
        return HomeStatusRead(status: .disconnected, label: "Checking Bluetooth…")
    }
    guard connectedDeviceName != nil else {
        let label =
            bluetoothState == .poweredOn
            ? "Omi disconnected" : bluetoothStatusLabel(bluetoothState)
        return HomeStatusRead(status: .disconnected, label: label)
    }
    switch captureStage {
    case .waiting:
        return HomeStatusRead(
            status: .waitingForAudio, label: "Connected · Waiting for audio")
    case .active:
        return HomeStatusRead(status: .connected, label: "Connected · Listening")
    default:
        return HomeStatusRead(status: .connected, label: "Connected · Ready")
    }
}
