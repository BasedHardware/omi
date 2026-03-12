import CoreBluetooth
import Foundation

/// Factory for creating device-specific connections
/// Ported from: omi/app/lib/services/devices/device_connection.dart
struct DeviceConnectionFactory {

    /// Create a device connection for the given device
    /// - Parameters:
    ///   - device: The device to connect to
    ///   - peripheral: The CoreBluetooth peripheral
    ///   - centralManager: The central manager (for transport)
    /// - Returns: A device connection, or nil if unsupported
    static func create(
        device: BtDevice,
        peripheral: CBPeripheral,
        centralManager: CBCentralManager
    ) -> DeviceConnection? {

        // Create BLE transport
        let transport = BleTransport(peripheral: peripheral, centralManager: centralManager)

        // Create device-specific connection
        switch device.type {
        case .omi, .openglass:
            return OmiDeviceConnection(device: device, transport: transport)

        case .plaud:
            return PlaudDeviceConnection(device: device, transport: transport)

        case .bee:
            return BeeDeviceConnection(device: device, transport: transport)

        case .fieldy:
            return FieldyDeviceConnection(device: device, transport: transport)

        case .friendPendant:
            return FriendPendantConnection(device: device, transport: transport)

        case .limitless:
            return LimitlessDeviceConnection(device: device, transport: transport)

        case .frame:
            // Frame uses Brilliant Labs SDK, but basic BLE fallback is available
            return FrameDeviceConnection(device: device, transport: transport)

        case .appleWatch:
            // Apple Watch uses WatchConnectivity, not BLE
            // TODO: Implement when adding watchOS support
            return nil
        }
    }

    /// Create a connection for a device using BluetoothManager's discovered peripherals
    /// - Parameter device: The device to connect to
    /// - Returns: A device connection, or nil if peripheral not found
    @MainActor
    static func create(device: BtDevice) -> DeviceConnection? {
        let manager = BluetoothManager.shared

        guard let peripheral = manager.peripheral(for: device) else {
            return nil
        }

        return create(
            device: device,
            peripheral: peripheral,
            centralManager: manager.centralManager
        )
    }
}
