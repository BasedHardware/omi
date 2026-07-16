import Combine
import CoreBluetooth
import Foundation

/// Factory for creating device-specific connections
/// Ported from: omi/app/lib/services/devices/device_connection.dart
struct DeviceConnectionFactory {

  /// Create a device connection for the given device
  /// - Parameters:
  ///   - device: The device to connect to
  ///   - peripheral: The CoreBluetooth peripheral
  ///   - connectionController: The central manager's leased connection boundary
  /// - Returns: A device connection, or nil if unsupported
  @MainActor
  static func create(
    device: BtDevice,
    peripheral: CBPeripheral,
    connectionController: any BluetoothCentralConnectionControlling,
    centralEvents: AnyPublisher<BluetoothCentralEvent, Never>,
    sessionGeneration: UInt64,
    operationClock: any DeviceOperationClock = ContinuousDeviceOperationClock()
  ) -> DeviceConnection? {

    // Create BLE transport
    let transport = BleTransport(
      peripheral: peripheral,
      connectionController: connectionController,
      centralEvents: centralEvents,
      sessionGeneration: sessionGeneration,
      operationClock: operationClock
    )

    // Create device-specific connection
    switch device.type {
    case .omi, .openglass:
      return OmiDeviceConnection(
        device: device,
        transport: transport,
        operationClock: operationClock
      )

    case .plaud:
      return PlaudDeviceConnection(
        device: device,
        transport: transport,
        operationClock: operationClock
      )

    case .bee:
      return BeeDeviceConnection(
        device: device,
        transport: transport,
        operationClock: operationClock
      )

    case .fieldy:
      return FieldyDeviceConnection(
        device: device,
        transport: transport,
        operationClock: operationClock
      )

    case .friendPendant:
      return FriendPendantConnection(
        device: device,
        transport: transport,
        operationClock: operationClock
      )

    case .limitless:
      return LimitlessDeviceConnection(
        device: device,
        transport: transport,
        operationClock: operationClock
      )

    case .frame:
      // Frame uses Brilliant Labs SDK, but basic BLE fallback is available
      return FrameDeviceConnection(
        device: device,
        transport: transport,
        operationClock: operationClock
      )

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
  static func create(
    device: BtDevice,
    sessionGeneration: UInt64,
    operationClock: any DeviceOperationClock = ContinuousDeviceOperationClock()
  ) -> DeviceConnection? {
    let manager = BluetoothManager.shared

    guard let peripheral = manager.peripheral(for: device) else {
      return nil
    }

    return create(
      device: device,
      peripheral: peripheral,
      connectionController: manager,
      centralEvents: manager.centralEventPublisher,
      sessionGeneration: sessionGeneration,
      operationClock: operationClock
    )
  }
}
