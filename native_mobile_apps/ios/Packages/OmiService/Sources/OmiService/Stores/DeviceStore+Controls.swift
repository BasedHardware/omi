import Foundation
import OmiDevice

/// Which of My Devices › Controls the connected firmware offers, and one-shot requests to it.
public extension DeviceStore {
    /// Whether the firmware has the haptic motor (assumed when it does not report features).
    var canFind: Bool {
        connection == .connected && (features.map { $0.contains(.haptic) } ?? true)
    }

    /// Brightness slider: only once the firmware said it dims and the value was read.
    var canDimLED: Bool {
        connection == .connected && features?.contains(.ledDimming) == true && ledBrightness != nil
    }

    var canSetMicGain: Bool {
        connection == .connected && features?.contains(.micGain) == true && micGain != nil
    }

    /// Asks the connected Omi for its signal strength (Diagnostics polls it while on screen).
    func readSignal() {
        guard connection == .connected else { return }
        driverInstance?.readRSSI()
    }

    /// One pulse on the Omi's motor (question started, answer arriving).
    func playHaptic(_ pulse: OmiGATT.Haptic) {
        guard connection == .connected else { return }
        driverInstance?.write(.haptic, pulse.payload)
    }
}
