import Combine
import CoreBluetooth
import XCTest

@testable import Omi_Computer

// MARK: - Test doubles

enum BluetoothReliabilityTestError: Error {
    case expected
}

@MainActor
final class AudioControllerHarness {
    var suspendStart = false
    private(set) var startCallCount = 0
    private(set) var startCompletionCount = 0
    private(set) var stopCallCount = 0
    private var startContinuation: CheckedContinuation<Void, Never>?
    private var stopContinuation: CheckedContinuation<Void, Error>?

    func start() async throws {
        startCallCount += 1
        if suspendStart {
            await withCheckedContinuation { continuation in
                startContinuation = continuation
            }
        }
        startCompletionCount += 1
    }

    func resumeStart() {
        startContinuation?.resume()
        startContinuation = nil
        suspendStart = false
    }

    func stop() async throws {
        stopCallCount += 1
        try await withCheckedThrowingContinuation { continuation in
            stopContinuation = continuation
        }
    }

    func failStop(_ error: Error) {
        stopContinuation?.resume(throwing: error)
        stopContinuation = nil
    }

    func succeedStop() {
        stopContinuation?.resume()
        stopContinuation = nil
    }
}

var bluetoothReliabilityTestDevice: BtDevice {
    BtDevice(
        id: "11111111-2222-3333-4444-555555555555",
        name: "Test Omi",
        type: .omi,
        rssi: -42
    )
}

actor ManualDeviceOperationClock: DeviceOperationClock {
    private var sleepers: [CheckedContinuation<Void, Error>] = []

    var sleeperCount: Int { sleepers.count }

    func sleep(for duration: Duration) async throws {
        try await withCheckedThrowingContinuation { continuation in
            sleepers.append(continuation)
        }
    }

    func advanceAll() {
        let current = sleepers
        sleepers.removeAll()
        current.forEach { $0.resume() }
    }
}

@MainActor
func waitForBluetoothReliabilityCondition(
    _ predicate: @escaping @MainActor () async -> Bool,
    file: StaticString = #filePath,
    line: UInt = #line
) async {
    for _ in 0..<500 {
        if await predicate() { return }
        await Task.yield()
    }
    XCTFail("Timed out waiting for condition", file: file, line: line)
}

@MainActor
final class FakeBLEPhysicalDriver: BLEPhysicalDriving {
    let identifier = UUID(uuidString: bluetoothReliabilityTestDevice.id)!
    var state: CBPeripheralState = .disconnected
    weak var delegate: CBPeripheralDelegate?
    var connectCallCount = 0
    var disconnectCallCount = 0
    var discoverServicesCallCount = 0
    var discoverCharacteristicsCallCount = 0
    var readValueCallCount = 0
    var writeValueCallCount = 0
    private(set) var writtenData: [Data] = []
    private(set) var issuedLeases: [BluetoothConnectionLease] = []
    private let firstLeaseToken: UInt64

    init(firstLeaseToken: UInt64 = 1) {
        self.firstLeaseToken = firstLeaseToken
    }

    func connect(sessionGeneration: UInt64) throws -> BluetoothConnectionLease {
        connectCallCount += 1
        state = .connecting
        let lease = BluetoothConnectionLease(
            peripheralID: identifier,
            token: firstLeaseToken + UInt64(connectCallCount - 1),
            sessionGeneration: sessionGeneration
        )
        issuedLeases.append(lease)
        return lease
    }

    func disconnect() {
        disconnectCallCount += 1
        state = .disconnected
    }

    func discoverServices(_ serviceUUIDs: [CBUUID]?) {
        discoverServicesCallCount += 1
    }
    func discoverCharacteristics(_ characteristicUUIDs: [CBUUID]?, for service: CBService) {
        discoverCharacteristicsCallCount += 1
    }
    func readValue(for characteristic: CBCharacteristic) {
        readValueCallCount += 1
    }
    func writeValue(
        _ data: Data,
        for characteristic: CBCharacteristic,
        type: CBCharacteristicWriteType
    ) {
        writeValueCallCount += 1
        writtenData.append(data)
    }
    func setNotifyValue(_ enabled: Bool, for characteristic: CBCharacteristic) {}
    func readRSSI() {}
}

@MainActor
final class ReliabilityTestTransport: DeviceTransport {
    let deviceId = bluetoothReliabilityTestDevice.id
    let sessionGeneration: UInt64
    var state: DeviceTransportState = .disconnected
    private let stateSubject = PassthroughSubject<DeviceTransportState, Never>()
    var connectionStatePublisher: AnyPublisher<DeviceTransportState, Never> {
        stateSubject.eraseToAnyPublisher()
    }

    var connectCallCount = 0
    var disconnectCallCount = 0
    var disposeCallCount = 0
    var writeCallCount = 0
    private(set) var writtenData: [Data] = []

    init(sessionGeneration: UInt64) {
        self.sessionGeneration = sessionGeneration
    }

    func connect() async throws {
        connectCallCount += 1
        state = .connected
        stateSubject.send(.connected)
    }

    func disconnect() async {
        disconnectCallCount += 1
        state = .disconnected
        stateSubject.send(.disconnected)
    }

    func isConnected() async -> Bool { state == .connected }
    func ping() async -> Bool { true }
    func getCharacteristicStream(
        serviceUUID: CBUUID,
        characteristicUUID: CBUUID
    ) -> AsyncThrowingStream<Data, Error> {
        AsyncThrowingStream { $0.finish() }
    }
    func readCharacteristic(
        serviceUUID: CBUUID,
        characteristicUUID: CBUUID
    ) async throws -> Data { Data() }
    func writeCharacteristic(
        data: Data,
        serviceUUID: CBUUID,
        characteristicUUID: CBUUID,
        withResponse: Bool
    ) async throws {
        writeCallCount += 1
        writtenData.append(data)
    }
    func dispose() async {
        disposeCallCount += 1
        state = .disconnected
        stateSubject.send(.disconnected)
    }

    func emitDisconnected() {
        state = .disconnected
        stateSubject.send(.disconnected)
    }
}

@MainActor
final class LifecycleHookConnection: BaseDeviceConnection {
    var prepareCallCount = 0
    var teardownCallCount = 0
    var prepareError: Error?

    override func prepareDeviceAfterConnect() async throws {
        prepareCallCount += 1
        if let prepareError { throw prepareError }
    }

    override func teardownDevice() async {
        teardownCallCount += 1
    }
}

@MainActor
final class ConnectionDelegateDouble: DeviceConnectionDelegate {
    var unexpectedDisconnectCount = 0

    func deviceConnection(
        _ connection: DeviceConnection,
        didDisconnectUnexpectedly device: BtDevice
    ) {
        unexpectedDisconnectCount += 1
    }

    func deviceConnection(
        _ connection: DeviceConnection,
        didDetectFall data: AccelerometerData
    ) {}
}

@MainActor
final class SessionConnectionDouble: DeviceConnection {
    var device: BtDevice
    let transport: DeviceTransport
    let sessionGeneration: UInt64
    var lastPongAt: Date?
    var cachedFeatures: OmiFeatures?
    weak var delegate: DeviceConnectionDelegate?

    var suspendConnect = false
    var suspendDisconnect = false
    var suspendUnpair = false
    var connectCallCount = 0
    var disconnectCallCount = 0
    var unpairCallCount = 0
    var batteryLevel = -1
    var suspendBattery = false
    var batteryCallCount = 0
    var batteryStreamCallCount = 0
    private var connectContinuation: CheckedContinuation<Void, Error>?
    private var disconnectContinuation: CheckedContinuation<Void, Never>?
    private var unpairContinuation: CheckedContinuation<Void, Never>?
    private var batteryContinuation: CheckedContinuation<Int, Never>?
    private var batteryStreamContinuation: AsyncThrowingStream<Int, Error>.Continuation?

    init(device: BtDevice, sessionGeneration: UInt64) {
        self.device = device
        self.sessionGeneration = sessionGeneration
        self.transport = ReliabilityTestTransport(sessionGeneration: sessionGeneration)
    }

    func connect() async throws {
        connectCallCount += 1
        guard suspendConnect else { return }
        try await withCheckedThrowingContinuation { continuation in
            connectContinuation = continuation
        }
    }

    func completeConnectSuccessfully() {
        connectContinuation?.resume()
        connectContinuation = nil
    }

    func failConnect(_ error: Error) {
        connectContinuation?.resume(throwing: error)
        connectContinuation = nil
    }

    func disconnect() async {
        disconnectCallCount += 1
        guard suspendDisconnect else { return }
        await withCheckedContinuation { continuation in
            disconnectContinuation = continuation
        }
    }
    func completeDisconnect() {
        disconnectContinuation?.resume()
        disconnectContinuation = nil
    }
    func unpair() async {
        unpairCallCount += 1
        guard suspendUnpair else { return }
        await withCheckedContinuation { continuation in
            unpairContinuation = continuation
        }
    }
    func completeUnpair() {
        unpairContinuation?.resume()
        unpairContinuation = nil
    }
    func isConnected() async -> Bool { true }
    func ping() async -> Bool { true }
    func getBatteryLevel() async -> Int {
        batteryCallCount += 1
        guard suspendBattery else { return batteryLevel }
        return await withCheckedContinuation { continuation in
            batteryContinuation = continuation
        }
    }
    func completeBattery(level: Int) {
        batteryContinuation?.resume(returning: level)
        batteryContinuation = nil
    }
    func getBatteryLevelStream() -> AsyncThrowingStream<Int, Error> {
        batteryStreamCallCount += 1
        return AsyncThrowingStream { continuation in
            batteryStreamContinuation = continuation
        }
    }
    func emitBattery(level: Int) {
        batteryStreamContinuation?.yield(level)
    }
    func finishBatteryStream() {
        batteryStreamContinuation?.finish()
        batteryStreamContinuation = nil
    }
    func getAudioCodec() async -> BleAudioCodec { .pcm8 }
    func getAudioStream() -> AsyncThrowingStream<Data, Error> {
        AsyncThrowingStream { $0.finish() }
    }
    func getButtonState() async -> [UInt8] { [] }
    func getButtonStream() -> AsyncThrowingStream<[UInt8], Error> {
        AsyncThrowingStream { $0.finish() }
    }
    func getStorageList() async -> [Int32] { [] }
    func writeToStorage(fileNum: Int, command: Int, offset: Int) async -> Bool { false }
    func getStorageStream() -> AsyncThrowingStream<Data, Error> {
        AsyncThrowingStream { $0.finish() }
    }
    func hasPhotoStreaming() async -> Bool { false }
    func startPhotoCapture() async {}
    func stopPhotoCapture() async {}
    func getImageStream() -> AsyncThrowingStream<OrientedImage, Error> {
        AsyncThrowingStream { $0.finish() }
    }
    func getAccelerometerStream() -> AsyncThrowingStream<AccelerometerData, Error> {
        AsyncThrowingStream { $0.finish() }
    }
    func playHaptic(level: Int) async -> Bool { false }
    func getFeatures() async -> OmiFeatures { [] }
    func setLedDimRatio(_ ratio: Int) async {}
    func getLedDimRatio() async -> Int? { nil }
    func setMicGain(_ gain: Int) async {}
    func getMicGain() async -> Int? { nil }
    func isWifiSyncSupported() async -> Bool { false }
    func setupWifiSync(ssid: String, password: String) async -> WifiSyncSetupResult {
        .connectionFailed()
    }
    func startWifiSync() async -> Bool { false }
    func stopWifiSync() async -> Bool { false }
    func getWifiSyncStatusStream() -> AsyncThrowingStream<Int, Error> {
        AsyncThrowingStream { $0.finish() }
    }
}

@MainActor
final class NoopDeviceSessionScheduler: DeviceSessionScheduling {
    func schedule(
        after delay: Duration,
        action: @escaping @MainActor () -> Void
    ) -> any DeviceSessionScheduledAction {
        NoopScheduledAction()
    }
}

@MainActor
final class NoopScheduledAction: DeviceSessionScheduledAction {
    func cancel() {}
}

@MainActor
final class ManualDeviceSessionScheduler: DeviceSessionScheduling {
    private final class ScheduledAction: DeviceSessionScheduledAction {
        var action: (@MainActor () -> Void)?

        init(action: @escaping @MainActor () -> Void) {
            self.action = action
        }

        func cancel() {
            action = nil
        }

        func run() {
            let current = action
            action = nil
            current?()
        }
    }

    private var actions: [ScheduledAction] = []
    var activeActionCount: Int { actions.filter { $0.action != nil }.count }

    func schedule(
        after delay: Duration,
        action: @escaping @MainActor () -> Void
    ) -> any DeviceSessionScheduledAction {
        let scheduled = ScheduledAction(action: action)
        actions.append(scheduled)
        return scheduled
    }

    func runNext() {
        actions.first(where: { $0.action != nil })?.run()
    }
}

@MainActor
final class ReliabilityBluetoothManager: DeviceBluetoothManaging {
    private let stateSubject = CurrentValueSubject<CBManagerState, Never>(.poweredOn)
    private let scanningSubject = CurrentValueSubject<Bool, Never>(false)
    private let devicesSubject = CurrentValueSubject<[BtDevice], Never>([])
    private let centralSubject = PassthroughSubject<BluetoothCentralEvent, Never>()

    var currentBluetoothState: CBManagerState { stateSubject.value }
    var currentIsScanning: Bool { scanningSubject.value }
    var currentDiscoveredDevices: [BtDevice] { devicesSubject.value }
    var bluetoothStatePublisher: AnyPublisher<CBManagerState, Never> {
        stateSubject.eraseToAnyPublisher()
    }
    var isScanningPublisher: AnyPublisher<Bool, Never> {
        scanningSubject.eraseToAnyPublisher()
    }
    var discoveredDevicesPublisher: AnyPublisher<[BtDevice], Never> {
        devicesSubject.eraseToAnyPublisher()
    }
    var centralEventPublisher: AnyPublisher<BluetoothCentralEvent, Never> {
        centralSubject.eraseToAnyPublisher()
    }

    func prepareForStateUpdates() {}
    func startScanning(timeout: TimeInterval) { scanningSubject.send(true) }
    func stopScanning() { scanningSubject.send(false) }
}
