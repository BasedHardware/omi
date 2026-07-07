import Combine
import CoreBluetooth
import XCTest

@testable import Omi_Computer

@MainActor
final class DeviceProviderTests: XCTestCase {
  private var defaultsToRemove: [UserDefaults] = []

  override func tearDown() {
    for defaults in defaultsToRemove {
      removeDefaults(defaults)
    }
    defaultsToRemove = []
    super.tearDown()
  }

  func testLoadsPersistedPairedDeviceFromInjectedDefaults() {
    let defaults = makeDefaults()
    defaults.set(testDevice.id, forKey: "pairedDeviceId")
    defaults.set(testDevice.name, forKey: "pairedDeviceName")
    defaults.set(testDevice.type.rawValue, forKey: "pairedDeviceType")
    defer { removeDefaults(defaults) }

    let provider = makeProvider(defaults: defaults)

    XCTAssertEqual(provider.pairedDevice, testDevice)
  }

  func testConnectPersistsPairedDeviceToInjectedDefaults() async {
    let defaults = makeDefaults()
    defer { removeDefaults(defaults) }
    let provider = makeProvider(defaults: defaults)

    await provider.connect(to: testDevice)

    XCTAssertTrue(provider.isConnected)
    XCTAssertEqual(provider.connectedDevice, testDevice)
    XCTAssertEqual(provider.pairedDevice, testDevice)
    XCTAssertEqual(defaults.string(forKey: "pairedDeviceId"), testDevice.id)
    XCTAssertEqual(defaults.string(forKey: "pairedDeviceName"), testDevice.name)
    XCTAssertEqual(defaults.string(forKey: "pairedDeviceType"), testDevice.type.rawValue)
  }

  func testFailedConnectionCleansUpTransientStateAndDoesNotPersistPairing() async {
    let defaults = makeDefaults()
    defer { removeDefaults(defaults) }
    let provider = DeviceProvider(
      bluetoothManager: FakeDeviceBluetoothManager(state: .poweredOn),
      userDefaults: defaults,
      notificationCenter: NotificationCenter(),
      connectionFactory: { FakeDeviceConnection(device: $0, connectError: DeviceTransportError.connectionFailed("boom")) },
      storageDataChecker: { nil },
      autoReconnectEnabled: false
    )

    await provider.connect(to: testDevice)

    XCTAssertFalse(provider.isConnecting)
    XCTAssertFalse(provider.isConnected)
    XCTAssertNil(provider.connectedDevice)
    XCTAssertNil(provider.activeConnection)
    XCTAssertNil(provider.pairedDevice)
    XCTAssertNil(defaults.string(forKey: "pairedDeviceId"))
    XCTAssertEqual(provider.errorMessage, "Failed to connect: Connection failed: boom")
  }

  func testStartDiscoveryDoesNotScanWhenBluetoothIsNotPoweredOn() {
    let bluetooth = FakeDeviceBluetoothManager(state: .poweredOff)
    let provider = makeProvider(bluetooth: bluetooth)

    provider.startDiscovery(timeout: 1.0)

    XCTAssertEqual(bluetooth.prepareForStateUpdatesCallCount, 1)
    XCTAssertEqual(bluetooth.startScanningTimeouts, [])
    XCTAssertFalse(provider.isScanning)
    XCTAssertEqual(provider.errorMessage, "Bluetooth is not available")
  }

  func testStartDiscoveryScansWhenBluetoothIsPoweredOn() {
    let bluetooth = FakeDeviceBluetoothManager(state: .poweredOn)
    let provider = makeProvider(bluetooth: bluetooth)

    provider.startDiscovery(timeout: 1.5)

    XCTAssertEqual(bluetooth.prepareForStateUpdatesCallCount, 1)
    XCTAssertEqual(bluetooth.startScanningTimeouts, [1.5])
    XCTAssertNil(provider.errorMessage)
  }

  func testDisconnectNotificationClearsConnectedStateButKeepsPairing() async {
    let notificationCenter = NotificationCenter()
    let provider = makeProvider(notificationCenter: notificationCenter, autoReconnectEnabled: false)

    await provider.connect(to: testDevice)
    XCTAssertTrue(provider.isConnected)

    notificationCenter.post(
      name: .bleDeviceDisconnected,
      object: nil,
      userInfo: ["peripheralId": UUID(uuidString: testDevice.id)!]
    )
    await drainMainQueue()

    XCTAssertFalse(provider.isConnected)
    XCTAssertNil(provider.connectedDevice)
    XCTAssertNil(provider.activeConnection)
    XCTAssertEqual(provider.batteryLevel, -1)
    XCTAssertFalse(provider.isDeviceStorageSupported)
    XCTAssertEqual(provider.pairedDevice, testDevice)
  }

  func testDisconnectNotificationForDifferentPeripheralDoesNotClearCurrentDevice() async {
    let notificationCenter = NotificationCenter()
    let provider = makeProvider(notificationCenter: notificationCenter, autoReconnectEnabled: false)

    await provider.connect(to: testDevice)
    XCTAssertTrue(provider.isConnected)

    notificationCenter.post(
      name: .bleDeviceDisconnected,
      object: nil,
      userInfo: ["peripheralId": UUID(uuidString: "AAAAAAAA-BBBB-CCCC-DDDD-EEEEEEEEEEEE")!]
    )
    await drainMainQueue()

    XCTAssertTrue(provider.isConnected)
    XCTAssertEqual(provider.connectedDevice, testDevice)
    XCTAssertNotNil(provider.activeConnection)
    XCTAssertEqual(provider.pairedDevice, testDevice)
    XCTAssertEqual(provider.batteryLevel, 82)
  }

  func testConnectReflectsBatteryAndStorageSupport() async {
    let defaults = makeDefaults()
    defer { removeDefaults(defaults) }
    let provider = DeviceProvider(
      bluetoothManager: FakeDeviceBluetoothManager(state: .poweredOn),
      userDefaults: defaults,
      notificationCenter: NotificationCenter(),
      connectionFactory: { FakeDeviceConnection(device: $0, batteryLevel: 25, storageList: [8_000]) },
      storageDataChecker: { nil },
      autoReconnectEnabled: false
    )

    await provider.connect(to: testDevice)

    XCTAssertTrue(provider.isConnected)
    XCTAssertEqual(provider.batteryLevel, 25)
    XCTAssertTrue(provider.isDeviceStorageSupported)
  }

  func testFirmwareUpdateInProgressStateCanBeToggled() {
    let provider = makeProvider(autoReconnectEnabled: false)

    provider.setFirmwareUpdateInProgress(true)
    XCTAssertTrue(provider.isFirmwareUpdateInProgress)

    provider.setFirmwareUpdateInProgress(false)
    XCTAssertFalse(provider.isFirmwareUpdateInProgress)
  }

  func testStartReconnectionTimerAttemptsPersistedPairingImmediately() async {
    let defaults = makeDefaults()
    defaults.set(testDevice.id, forKey: "pairedDeviceId")
    defaults.set(testDevice.name, forKey: "pairedDeviceName")
    defaults.set(testDevice.type.rawValue, forKey: "pairedDeviceType")
    defer { removeDefaults(defaults) }
    var attemptedDevices: [BtDevice] = []
    let provider = DeviceProvider(
      bluetoothManager: FakeDeviceBluetoothManager(state: .poweredOn),
      userDefaults: defaults,
      notificationCenter: NotificationCenter(),
      connectionFactory: { device in
        attemptedDevices.append(device)
        return FakeDeviceConnection(device: device)
      },
      storageDataChecker: { nil },
      autoReconnectEnabled: true
    )

    provider.startReconnectionTimer()
    await waitUntil { provider.isConnected }
    provider.stopReconnectionTimer()

    XCTAssertEqual(attemptedDevices, [testDevice])
    XCTAssertTrue(provider.isConnected)
    XCTAssertEqual(provider.connectedDevice, testDevice)
  }

  func testStartReconnectionTimerWithoutPairingDoesNotAttemptConnection() async {
    let defaults = makeDefaults()
    defer { removeDefaults(defaults) }
    var connectionFactoryCallCount = 0
    let provider = DeviceProvider(
      bluetoothManager: FakeDeviceBluetoothManager(state: .poweredOn),
      userDefaults: defaults,
      notificationCenter: NotificationCenter(),
      connectionFactory: { device in
        connectionFactoryCallCount += 1
        return FakeDeviceConnection(device: device)
      },
      storageDataChecker: { nil },
      autoReconnectEnabled: true
    )

    provider.startReconnectionTimer()
    await drainMainQueue()

    XCTAssertEqual(connectionFactoryCallCount, 0)
    XCTAssertFalse(provider.isConnected)
  }

  func testUnpairDisconnectsAndClearsPersistedPairing() async {
    let defaults = makeDefaults()
    defer { removeDefaults(defaults) }
    var connection: FakeDeviceConnection?
    let provider = DeviceProvider(
      bluetoothManager: FakeDeviceBluetoothManager(state: .poweredOn),
      userDefaults: defaults,
      notificationCenter: NotificationCenter(),
      connectionFactory: { device in
        let newConnection = FakeDeviceConnection(device: device)
        connection = newConnection
        return newConnection
      },
      storageDataChecker: { nil },
      autoReconnectEnabled: false
    )

    await provider.connect(to: testDevice)
    await provider.unpair()

    XCTAssertEqual(connection?.unpairCallCount, 1)
    XCTAssertFalse(provider.isConnected)
    XCTAssertNil(provider.connectedDevice)
    XCTAssertNil(provider.pairedDevice)
    XCTAssertNil(defaults.string(forKey: "pairedDeviceId"))
    XCTAssertNil(defaults.string(forKey: "pairedDeviceName"))
    XCTAssertNil(defaults.string(forKey: "pairedDeviceType"))
  }

  private var testDevice: BtDevice {
    BtDevice(
      id: "11111111-2222-3333-4444-555555555555",
      name: "Test Omi",
      type: .omi,
      rssi: -45
    )
  }

  private func makeProvider(
    bluetooth: FakeDeviceBluetoothManager? = nil,
    defaults: UserDefaults? = nil,
    notificationCenter: NotificationCenter = NotificationCenter(),
    autoReconnectEnabled: Bool = false
  ) -> DeviceProvider {
    DeviceProvider(
      bluetoothManager: bluetooth ?? FakeDeviceBluetoothManager(state: .poweredOn),
      userDefaults: defaults ?? makeDefaults(),
      notificationCenter: notificationCenter,
      connectionFactory: { FakeDeviceConnection(device: $0) },
      storageDataChecker: { nil },
      autoReconnectEnabled: autoReconnectEnabled
    )
  }

  private func makeDefaults() -> UserDefaults {
    let suiteName = "DeviceProviderTests.\(UUID().uuidString)"
    let defaults = UserDefaults(suiteName: suiteName)!
    defaults.set(suiteName, forKey: "__testSuiteName")
    defaultsToRemove.append(defaults)
    return defaults
  }

  private func removeDefaults(_ defaults: UserDefaults) {
    guard let suiteName = defaults.string(forKey: "__testSuiteName") else {
      return
    }
    defaults.removePersistentDomain(forName: suiteName)
  }

  private func drainMainQueue() async {
    await Task.yield()
    await Task.yield()
  }

  private func waitUntil(
    _ predicate: @MainActor () -> Bool,
    file: StaticString = #filePath,
    line: UInt = #line
  ) async {
    for _ in 0..<100 {
      if predicate() {
        return
      }
      await Task.yield()
    }
    XCTFail("Timed out waiting for condition", file: file, line: line)
  }
}

@MainActor
private final class FakeDeviceBluetoothManager: DeviceBluetoothManaging {
  private let bluetoothStateSubject: CurrentValueSubject<CBManagerState, Never>
  private let isScanningSubject: CurrentValueSubject<Bool, Never>
  private let discoveredDevicesSubject: CurrentValueSubject<[BtDevice], Never>

  var prepareForStateUpdatesCallCount = 0
  var startScanningTimeouts: [TimeInterval] = []
  var stopScanningCallCount = 0

  init(
    state: CBManagerState,
    isScanning: Bool = false,
    discoveredDevices: [BtDevice] = []
  ) {
    bluetoothStateSubject = CurrentValueSubject(state)
    isScanningSubject = CurrentValueSubject(isScanning)
    discoveredDevicesSubject = CurrentValueSubject(discoveredDevices)
  }

  var currentBluetoothState: CBManagerState { bluetoothStateSubject.value }
  var currentIsScanning: Bool { isScanningSubject.value }
  var currentDiscoveredDevices: [BtDevice] { discoveredDevicesSubject.value }
  var bluetoothStatePublisher: AnyPublisher<CBManagerState, Never> {
    bluetoothStateSubject.eraseToAnyPublisher()
  }
  var isScanningPublisher: AnyPublisher<Bool, Never> {
    isScanningSubject.eraseToAnyPublisher()
  }
  var discoveredDevicesPublisher: AnyPublisher<[BtDevice], Never> {
    discoveredDevicesSubject.eraseToAnyPublisher()
  }

  func prepareForStateUpdates() {
    prepareForStateUpdatesCallCount += 1
  }

  func startScanning(timeout: TimeInterval) {
    startScanningTimeouts.append(timeout)
    isScanningSubject.send(true)
  }

  func stopScanning() {
    stopScanningCallCount += 1
    isScanningSubject.send(false)
  }
}

private final class FakeDeviceConnection: BaseDeviceConnection {
  private let connectError: Error?
  private let batteryLevel: Int
  private let storageList: [Int32]
  var unpairCallCount = 0

  init(
    device: BtDevice,
    connectError: Error? = nil,
    batteryLevel: Int = 82,
    storageList: [Int32] = []
  ) {
    self.connectError = connectError
    self.batteryLevel = batteryLevel
    self.storageList = storageList
    super.init(device: device, transport: FakeDeviceTransport(deviceId: device.id))
  }

  override func connect() async throws {
    if let connectError {
      throw connectError
    }
    try await super.connect()
  }

  override func unpair() async {
    unpairCallCount += 1
    await super.unpair()
  }

  override func getBatteryLevel() async -> Int {
    batteryLevel
  }

  override func getBatteryLevelStream() -> AsyncThrowingStream<Int, Error> {
    AsyncThrowingStream { continuation in
      continuation.finish()
    }
  }

  override func getStorageList() async -> [Int32] {
    storageList
  }
}

private final class FakeDeviceTransport: DeviceTransport {
  let deviceId: String
  private(set) var state: DeviceTransportState = .disconnected
  private let connectionStateSubject = PassthroughSubject<DeviceTransportState, Never>()

  init(deviceId: String) {
    self.deviceId = deviceId
  }

  var connectionStatePublisher: AnyPublisher<DeviceTransportState, Never> {
    connectionStateSubject.eraseToAnyPublisher()
  }

  func connect() async throws {
    state = .connected
    connectionStateSubject.send(.connected)
  }

  func disconnect() async {
    state = .disconnected
    connectionStateSubject.send(.disconnected)
  }

  func isConnected() async -> Bool {
    state == .connected
  }

  func ping() async -> Bool {
    true
  }

  func getCharacteristicStream(
    serviceUUID: CBUUID,
    characteristicUUID: CBUUID
  ) -> AsyncThrowingStream<Data, Error> {
    AsyncThrowingStream { continuation in
      continuation.finish()
    }
  }

  func readCharacteristic(
    serviceUUID: CBUUID,
    characteristicUUID: CBUUID
  ) async throws -> Data {
    Data()
  }

  func writeCharacteristic(
    data: Data,
    serviceUUID: CBUUID,
    characteristicUUID: CBUUID,
    withResponse: Bool
  ) async throws {}

  func dispose() async {}
}
