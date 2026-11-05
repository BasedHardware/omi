import Foundation
import OmiDevice

/// A pretend Omi for simulator QA (`-omiFakeDevice nearby|connected`, Debug only): "nearby"
/// shows two Omis to pair with, "connected" behaves like a paired Omi that is in range, with
/// battery, firmware and every control. No audio ever arrives.
final class DebugDeviceDriver: DeviceDriving, @unchecked Sendable {
    let events: AsyncStream<OmiDeviceManager.Event>
    private let continuation: AsyncStream<OmiDeviceManager.Event>.Continuation
    static let pairedID = UUID(uuidString: "6F1D0C3A-1B2C-4D5E-8F90-123456789ABC")!

    init() {
        (events, continuation) = AsyncStream.makeStream()
        continuation.yield(.bluetooth(.ready))
    }

    func startScan() {
        continuation.yield(.discovered(.init(id: Self.pairedID, name: "Omi", rssi: -52)))
        let devKit = UUID(uuidString: "0B9E2F44-7A1C-4E2B-9D3F-5C6A7B8C9D0E")!
        continuation.yield(.discovered(.init(id: devKit, name: "Omi DevKit 2", rssi: -78)))
    }

    func stopScan() {}

    func connect(_ id: UUID) {
        continuation.yield(.connecting(id))
        let continuation = continuation
        Task {
            try? await Task.sleep(for: .milliseconds(600))
            continuation.yield(.connected(id: id, name: "Omi"))
            continuation.yield(.info(model: "Omi CV 1", firmware: "2.0.10", manufacturer: "Based Hardware", hardware: "CV1"))
            continuation.yield(.serialNumber("OMI-24A7-91C3"))
            continuation.yield(.features([.button, .battery, .haptic, .offlineStorage, .ledDimming, .micGain]))
            continuation.yield(.battery(76))
            continuation.yield(.charging(false))
            continuation.yield(.ledBrightness(60))
            continuation.yield(.micGain(5))
            continuation.yield(.codec(.opus))
        }
    }

    func disconnect() {
        continuation.yield(.disconnected(id: Self.pairedID, error: nil))
    }

    func readBattery() {
        continuation.yield(.battery(76))
    }

    /// The encoded paired device a "connected" launch starts with.
    static var pairedJSON: String? {
        var device = PairedDevice(id: pairedID.uuidString, name: "Omi", rssi: -52)
        device.modelNumber = "Omi CV 1"
        device.firmwareRevision = "2.0.10"
        return device.encoded
    }
}
