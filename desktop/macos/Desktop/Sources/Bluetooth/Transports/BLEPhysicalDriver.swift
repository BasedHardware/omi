@preconcurrency import CoreBluetooth
import Foundation

/// Narrow CoreBluetooth side-effect seam used by `BleTransport`.
///
/// Keeping the physical driver separate lets the transport's operation,
/// timeout, and disposal contracts run deterministically in unit tests without
/// constructing private CoreBluetooth objects or touching Bluetooth hardware.
@MainActor
protocol BLEPhysicalDriving: AnyObject {
  var identifier: UUID { get }
  var state: CBPeripheralState { get }
  var delegate: CBPeripheralDelegate? { get set }

  func connect(sessionGeneration: UInt64) throws -> BluetoothConnectionLease
  func disconnect()
  func discoverServices(_ serviceUUIDs: [CBUUID]?)
  func discoverCharacteristics(_ characteristicUUIDs: [CBUUID]?, for service: CBService)
  func readValue(for characteristic: CBCharacteristic)
  func writeValue(
    _ data: Data,
    for characteristic: CBCharacteristic,
    type: CBCharacteristicWriteType
  )
  func setNotifyValue(_ enabled: Bool, for characteristic: CBCharacteristic)
  func readRSSI()
}

@MainActor
final class CoreBluetoothPhysicalDriver: BLEPhysicalDriving {
  private let peripheral: CBPeripheral
  private let connectionController: any BluetoothCentralConnectionControlling
  private var connectionLease: BluetoothConnectionLease?

  init(
    peripheral: CBPeripheral,
    connectionController: any BluetoothCentralConnectionControlling
  ) {
    self.peripheral = peripheral
    self.connectionController = connectionController
  }

  var identifier: UUID { peripheral.identifier }
  var state: CBPeripheralState { peripheral.state }
  var delegate: CBPeripheralDelegate? {
    get { peripheral.delegate }
    set { peripheral.delegate = newValue }
  }

  func connect(sessionGeneration: UInt64) throws -> BluetoothConnectionLease {
    let lease = try connectionController.beginConnection(
      to: peripheral,
      sessionGeneration: sessionGeneration
    )
    connectionLease = lease
    return lease
  }

  func disconnect() {
    guard let connectionLease else { return }
    connectionController.cancelConnection(
      to: peripheral,
      lease: connectionLease
    )
    self.connectionLease = nil
  }

  func discoverServices(_ serviceUUIDs: [CBUUID]?) {
    peripheral.discoverServices(serviceUUIDs)
  }

  func discoverCharacteristics(
    _ characteristicUUIDs: [CBUUID]?,
    for service: CBService
  ) {
    peripheral.discoverCharacteristics(characteristicUUIDs, for: service)
  }

  func readValue(for characteristic: CBCharacteristic) {
    peripheral.readValue(for: characteristic)
  }

  func writeValue(
    _ data: Data,
    for characteristic: CBCharacteristic,
    type: CBCharacteristicWriteType
  ) {
    peripheral.writeValue(data, for: characteristic, type: type)
  }

  func setNotifyValue(_ enabled: Bool, for characteristic: CBCharacteristic) {
    peripheral.setNotifyValue(enabled, for: characteristic)
  }

  func readRSSI() {
    peripheral.readRSSI()
  }
}
