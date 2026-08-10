import CoreBluetooth
import Foundation

private let omiServiceUUID = CBUUID(string: "19b10000-e8f2-537e-4f6c-d104768a1214")
private let omiAudioUUID = CBUUID(string: "19b10001-e8f2-537e-4f6c-d104768a1214")

final class OmiBluetoothController: NSObject, CBCentralManagerDelegate, CBPeripheralDelegate {
  private var central: CBCentralManager!
  private var peripherals: [String: CBPeripheral] = [:]
  private var results: [String: [String: Any]] = [:]
  private(set) var state = "unknown"
  private(set) var connection = "disconnected"
  private(set) var scanActive = false
  private(set) var lastError: String?
  private(set) var audioNotifications = false
  private(set) var lastPacketBytes = 0

  override init() {
    super.init()
    central = CBCentralManager(delegate: self, queue: .main)
  }

  func centralManagerDidUpdateState(_ central: CBCentralManager) {
    switch central.state {
    case .poweredOn: state = "poweredOn"
    case .poweredOff: state = "poweredOff"
    case .unauthorized: state = "unauthorized"
    case .unsupported: state = "unsupported"
    case .resetting: state = "resetting"
    case .unknown: state = "unknown"
    @unknown default: state = "unknown"
    }
  }

  func capabilities() -> [String: Any] {
    [
      "available": central.state != .unsupported,
      "enabled": central.state == .poweredOn,
      "scan": central.state == .poweredOn,
      "connection": connection,
      "scanActive": scanActive,
      "state": state,
      "lastError": lastError ?? NSNull(),
      "audioNotifications": audioNotifications,
      "lastPacketBytes": lastPacketBytes,
      "implementation": "ios-core-bluetooth"
    ]
  }

  func startScan() -> [String: Any] {
    guard central.state == .poweredOn else {
      lastError = "Bluetooth is not powered on: \(state)"
      return capabilities()
    }
    results.removeAll()
    lastError = nil
    central.scanForPeripherals(withServices: [omiServiceUUID], options: [CBCentralManagerScanOptionAllowDuplicatesKey: false])
    scanActive = true
    return capabilities()
  }

  func stopScan() -> [String: Any] {
    central.stopScan()
    scanActive = false
    return capabilities()
  }

  func scanResults() -> [[String: Any]] {
    results.values.sorted { ($0["id"] as? String ?? "") < ($1["id"] as? String ?? "") }
  }

  func connect(identifier: String) -> [String: Any] {
    stopScan()
    guard let uuid = UUID(uuidString: identifier) else {
      lastError = "Invalid Bluetooth identifier: \(identifier)"
      return capabilities()
    }
    let peripheral = peripherals[identifier] ?? central.retrievePeripherals(withIdentifiers: [uuid]).first
    guard let peripheral else {
      lastError = "Omi peripheral not discovered: \(identifier)"
      return capabilities()
    }
    peripherals[identifier] = peripheral
    connection = "connecting"
    central.connect(peripheral, options: nil)
    return capabilities()
  }

  func disconnect() -> [String: Any] {
    for peripheral in peripherals.values where peripheral.state == .connected {
      central.cancelPeripheralConnection(peripheral)
    }
    connection = "disconnected"
    return capabilities()
  }

  func centralManager(_ central: CBCentralManager, didDiscover peripheral: CBPeripheral,
                      advertisementData: [String: Any], rssi RSSI: NSNumber) {
    let id = peripheral.identifier.uuidString
    peripherals[id] = peripheral
    results[id] = [
      "id": id,
      "name": peripheral.name ?? advertisementData[CBAdvertisementDataLocalNameKey] as? String ?? "Omi",
      "rssi": RSSI.intValue,
      "source": "ios-core-bluetooth"
    ]
  }

  func centralManager(_ central: CBCentralManager, didConnect peripheral: CBPeripheral) {
    connection = "connected"
    peripheral.delegate = self
    peripheral.discoverServices([omiServiceUUID])
  }

  func centralManager(_ central: CBCentralManager, didFailToConnect peripheral: CBPeripheral, error: Error?) {
    connection = "disconnected"
    lastError = error?.localizedDescription ?? "Omi connection failed"
  }

  func centralManager(_ central: CBCentralManager, didDisconnectPeripheral peripheral: CBPeripheral, error: Error?) {
    connection = "disconnected"
    if let error { lastError = error.localizedDescription }
  }

  func peripheral(_ peripheral: CBPeripheral, didDiscoverServices error: Error?) {
    if let error {
      lastError = error.localizedDescription
      return
    }
    guard let service = peripheral.services?.first(where: { $0.uuid == omiServiceUUID }) else {
      lastError = "Omi service not found after connection"
      return
    }
    peripheral.discoverCharacteristics([omiAudioUUID], for: service)
  }

  func peripheral(_ peripheral: CBPeripheral, didDiscoverCharacteristicsFor service: CBService, error: Error?) {
    if let error {
      lastError = error.localizedDescription
      return
    }
    guard let audio = service.characteristics?.first(where: { $0.uuid == omiAudioUUID }) else {
      lastError = "Omi audio characteristic not found"
      return
    }
    peripheral.setNotifyValue(true, for: audio)
  }

  func peripheral(_ peripheral: CBPeripheral, didUpdateNotificationStateFor characteristic: CBCharacteristic, error: Error?) {
    if let error {
      lastError = error.localizedDescription
      return
    }
    if characteristic.uuid == omiAudioUUID {
      audioNotifications = characteristic.isNotifying
    }
  }

  func peripheral(_ peripheral: CBPeripheral, didUpdateValueFor characteristic: CBCharacteristic, error: Error?) {
    if let error {
      lastError = error.localizedDescription
      return
    }
    if characteristic.uuid == omiAudioUUID {
      lastPacketBytes = characteristic.value?.count ?? 0
    }
  }
}
