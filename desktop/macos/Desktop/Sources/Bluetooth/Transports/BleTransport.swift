import Combine
import CoreBluetooth
import Foundation
import os.log

/// BLE transport implementation using CoreBluetooth
/// Ported from: omi/app/lib/services/devices/transports/ble_transport.dart
final class BleTransport: NSObject, DeviceTransport {

    // MARK: - DeviceTransport Protocol

    let deviceId: String

    var state: DeviceTransportState {
        _state
    }

    var connectionStatePublisher: AnyPublisher<DeviceTransportState, Never> {
        connectionStateSubject.eraseToAnyPublisher()
    }

    // MARK: - Private Properties

    private let peripheral: CBPeripheral
    private let centralManager: CBCentralManager
    private let logger = Logger(subsystem: "me.omi.desktop", category: "BleTransport")

    private var _state: DeviceTransportState = .disconnected
    private let connectionStateSubject = PassthroughSubject<DeviceTransportState, Never>()

    private var discoveredServices: [CBService] = []
    private var characteristicContinuations: [CBUUID: CheckedContinuation<Data, Error>] = [:]
    private var writeContinuations: [CBUUID: CheckedContinuation<Void, Error>] = [:]
    private var characteristicStreams: [String: CharacteristicStreamHandler] = [:]

    private var connectionContinuation: CheckedContinuation<Void, Error>?
    private var serviceDiscoveryContinuation: CheckedContinuation<[CBService], Error>?

    private var isDisposed = false
    private var centralManagerObserver: NSObjectProtocol?

    // MARK: - Initialization

    init(peripheral: CBPeripheral, centralManager: CBCentralManager) {
        self.peripheral = peripheral
        self.centralManager = centralManager
        self.deviceId = peripheral.identifier.uuidString
        super.init()
        peripheral.delegate = self
        setupConnectionObserver()
    }

    private func setupConnectionObserver() {
        // Observe connection state changes via NotificationCenter
        // BluetoothManager posts these when CBCentralManagerDelegate methods fire
        centralManagerObserver = NotificationCenter.default.addObserver(
            forName: .bleDeviceConnected,
            object: nil,
            queue: .main
        ) { [weak self] notification in
            guard let self = self,
                  let peripheralId = notification.userInfo?["peripheralId"] as? UUID,
                  peripheralId == self.peripheral.identifier else { return }

            self.handleConnectionSuccess()
        }

        NotificationCenter.default.addObserver(
            forName: .bleDeviceDisconnected,
            object: nil,
            queue: .main
        ) { [weak self] notification in
            guard let self = self,
                  let peripheralId = notification.userInfo?["peripheralId"] as? UUID,
                  peripheralId == self.peripheral.identifier else { return }

            let error = notification.userInfo?["error"] as? Error
            self.handleDisconnection(error: error)
        }

        NotificationCenter.default.addObserver(
            forName: .bleDeviceFailedToConnect,
            object: nil,
            queue: .main
        ) { [weak self] notification in
            guard let self = self,
                  let peripheralId = notification.userInfo?["peripheralId"] as? UUID,
                  peripheralId == self.peripheral.identifier else { return }

            let error = notification.userInfo?["error"] as? Error
            self.handleConnectionFailure(error: error)
        }
    }

    private func handleConnectionSuccess() {
        connectionContinuation?.resume()
        connectionContinuation = nil
    }

    private func handleConnectionFailure(error: Error?) {
        let transportError = DeviceTransportError.connectionFailed(error?.localizedDescription ?? "Unknown error")
        connectionContinuation?.resume(throwing: transportError)
        connectionContinuation = nil
        updateState(.disconnected)
    }

    private func handleDisconnection(error: Error?) {
        if let continuation = connectionContinuation {
            continuation.resume(throwing: DeviceTransportError.connectionFailed("Disconnected during connection"))
            connectionContinuation = nil
        }
        updateState(.disconnected)
    }

    deinit {
        if let observer = centralManagerObserver {
            NotificationCenter.default.removeObserver(observer)
        }
        NotificationCenter.default.removeObserver(self)
    }

    // MARK: - Connection

    func connect() async throws {
        guard !isDisposed else { throw DeviceTransportError.disposed }
        guard _state != .connected else { return }

        updateState(.connecting)

        do {
            // Connect to the peripheral
            try await withCheckedThrowingContinuation { (continuation: CheckedContinuation<Void, Error>) in
                self.connectionContinuation = continuation
                self.centralManager.connect(self.peripheral, options: nil)
            }

            // Discover services
            discoveredServices = try await withCheckedThrowingContinuation { (continuation: CheckedContinuation<[CBService], Error>) in
                self.serviceDiscoveryContinuation = continuation
                self.peripheral.discoverServices(nil)
            }

            // Discover characteristics for each service
            for service in discoveredServices {
                peripheral.discoverCharacteristics(nil, for: service)
            }

            // Wait briefly for characteristic discovery
            try await Task.sleep(nanoseconds: 500_000_000) // 0.5 seconds

            updateState(.connected)
            logger.info("Connected to device \(self.deviceId)")

        } catch {
            updateState(.disconnected)
            throw DeviceTransportError.connectionFailed(error.localizedDescription)
        }
    }

    func disconnect() async {
        guard !isDisposed else { return }
        guard _state != .disconnected else { return }

        updateState(.disconnecting)

        // Cancel all characteristic streams
        for handler in characteristicStreams.values {
            handler.finish()
        }
        characteristicStreams.removeAll()

        // Cancel pending continuations
        connectionContinuation?.resume(throwing: CancellationError())
        connectionContinuation = nil
        serviceDiscoveryContinuation?.resume(throwing: CancellationError())
        serviceDiscoveryContinuation = nil

        for (_, continuation) in characteristicContinuations {
            continuation.resume(throwing: CancellationError())
        }
        characteristicContinuations.removeAll()

        for (_, continuation) in writeContinuations {
            continuation.resume(throwing: CancellationError())
        }
        writeContinuations.removeAll()

        // Disconnect
        centralManager.cancelPeripheralConnection(peripheral)
        updateState(.disconnected)

        logger.info("Disconnected from device \(self.deviceId)")
    }

    func isConnected() async -> Bool {
        peripheral.state == .connected
    }

    func ping() async -> Bool {
        guard peripheral.state == .connected else { return false }
        do {
            _ = try await peripheral.readRSSIAsync()
            return true
        } catch {
            logger.debug("Ping failed: \(error.localizedDescription)")
            return false
        }
    }

    // MARK: - Characteristic Operations

    func getCharacteristicStream(
        serviceUUID: CBUUID,
        characteristicUUID: CBUUID
    ) -> AsyncThrowingStream<Data, Error> {
        let key = "\(serviceUUID.uuidString):\(characteristicUUID.uuidString)"

        // Return existing stream if available
        if let existing = characteristicStreams[key] {
            return existing.stream
        }

        // Create new stream handler
        let handler = CharacteristicStreamHandler()
        characteristicStreams[key] = handler

        // Set up characteristic notification
        Task {
            do {
                guard let characteristic = findCharacteristic(
                    serviceUUID: serviceUUID,
                    characteristicUUID: characteristicUUID
                ) else {
                    handler.finish(throwing: DeviceTransportError.characteristicNotFound(characteristicUUID))
                    return
                }

                peripheral.setNotifyValue(true, for: characteristic)
                logger.debug("Enabled notifications for \(characteristicUUID.uuidString)")
            }
        }

        return handler.stream
    }

    func readCharacteristic(
        serviceUUID: CBUUID,
        characteristicUUID: CBUUID
    ) async throws -> Data {
        guard !isDisposed else { throw DeviceTransportError.disposed }
        guard _state == .connected else { throw DeviceTransportError.notConnected }

        guard let characteristic = findCharacteristic(
            serviceUUID: serviceUUID,
            characteristicUUID: characteristicUUID
        ) else {
            throw DeviceTransportError.characteristicNotFound(characteristicUUID)
        }

        return try await withCheckedThrowingContinuation { continuation in
            characteristicContinuations[characteristicUUID] = continuation
            peripheral.readValue(for: characteristic)
        }
    }

    func writeCharacteristic(
        data: Data,
        serviceUUID: CBUUID,
        characteristicUUID: CBUUID,
        withResponse: Bool
    ) async throws {
        guard !isDisposed else { throw DeviceTransportError.disposed }
        guard _state == .connected else { throw DeviceTransportError.notConnected }

        guard let characteristic = findCharacteristic(
            serviceUUID: serviceUUID,
            characteristicUUID: characteristicUUID
        ) else {
            throw DeviceTransportError.characteristicNotFound(characteristicUUID)
        }

        let writeType: CBCharacteristicWriteType = withResponse ? .withResponse : .withoutResponse

        if withResponse {
            try await withCheckedThrowingContinuation { (continuation: CheckedContinuation<Void, Error>) in
                writeContinuations[characteristicUUID] = continuation
                peripheral.writeValue(data, for: characteristic, type: writeType)
            }
        } else {
            peripheral.writeValue(data, for: characteristic, type: writeType)
        }
    }

    func dispose() async {
        guard !isDisposed else { return }
        isDisposed = true

        await disconnect()
        logger.debug("Transport disposed for device \(self.deviceId)")
    }

    // MARK: - Private Helpers

    private func updateState(_ newState: DeviceTransportState) {
        guard _state != newState else { return }
        _state = newState
        connectionStateSubject.send(newState)
    }

    private func findCharacteristic(serviceUUID: CBUUID, characteristicUUID: CBUUID) -> CBCharacteristic? {
        guard let service = discoveredServices.first(where: {
            $0.uuid.uuidString.lowercased() == serviceUUID.uuidString.lowercased()
        }) else {
            return nil
        }

        return service.characteristics?.first(where: {
            $0.uuid.uuidString.lowercased() == characteristicUUID.uuidString.lowercased()
        })
    }

    /// Get all discovered services
    var services: [CBService] {
        discoveredServices
    }
}

// MARK: - CBPeripheralDelegate

extension BleTransport: CBPeripheralDelegate {

    func peripheral(_ peripheral: CBPeripheral, didDiscoverServices error: Error?) {
        if let error = error {
            serviceDiscoveryContinuation?.resume(throwing: error)
        } else {
            serviceDiscoveryContinuation?.resume(returning: peripheral.services ?? [])
        }
        serviceDiscoveryContinuation = nil
    }

    func peripheral(_ peripheral: CBPeripheral, didDiscoverCharacteristicsFor service: CBService, error: Error?) {
        if let error = error {
            logger.warning("Failed to discover characteristics for \(service.uuid): \(error.localizedDescription)")
        } else {
            logger.debug("Discovered \(service.characteristics?.count ?? 0) characteristics for \(service.uuid)")
        }
    }

    func peripheral(_ peripheral: CBPeripheral, didUpdateValueFor characteristic: CBCharacteristic, error: Error?) {
        let uuid = characteristic.uuid

        // Handle pending read continuation
        if let continuation = characteristicContinuations.removeValue(forKey: uuid) {
            if let error = error {
                continuation.resume(throwing: DeviceTransportError.readFailed(error.localizedDescription))
            } else {
                continuation.resume(returning: characteristic.value ?? Data())
            }
            return
        }

        // Handle stream notification
        let key = "\(characteristic.service?.uuid.uuidString ?? ""):\(uuid.uuidString)"
        if let handler = characteristicStreams[key], let value = characteristic.value {
            handler.yield(value)
        }
    }

    func peripheral(_ peripheral: CBPeripheral, didWriteValueFor characteristic: CBCharacteristic, error: Error?) {
        let uuid = characteristic.uuid

        if let continuation = writeContinuations.removeValue(forKey: uuid) {
            if let error = error {
                continuation.resume(throwing: DeviceTransportError.writeFailed(error.localizedDescription))
            } else {
                continuation.resume()
            }
        }
    }

    func peripheral(_ peripheral: CBPeripheral, didUpdateNotificationStateFor characteristic: CBCharacteristic, error: Error?) {
        if let error = error {
            logger.warning("Failed to update notification state for \(characteristic.uuid): \(error.localizedDescription)")
        } else {
            logger.debug("Notification state updated for \(characteristic.uuid): \(characteristic.isNotifying)")
        }
    }

    func peripheral(_ peripheral: CBPeripheral, didReadRSSI RSSI: NSNumber, error: Error?) {
        // RSSI read completion - used for ping
    }
}

// MARK: - Characteristic Stream Handler

/// Helper class to manage AsyncThrowingStream for characteristic notifications
private final class CharacteristicStreamHandler: @unchecked Sendable {
    private var continuation: AsyncThrowingStream<Data, Error>.Continuation?

    let stream: AsyncThrowingStream<Data, Error>

    init() {
        var capturedContinuation: AsyncThrowingStream<Data, Error>.Continuation?
        stream = AsyncThrowingStream { continuation in
            capturedContinuation = continuation
        }
        self.continuation = capturedContinuation
    }

    func yield(_ data: Data) {
        continuation?.yield(data)
    }

    func finish(throwing error: Error? = nil) {
        if let error = error {
            continuation?.finish(throwing: error)
        } else {
            continuation?.finish()
        }
        continuation = nil
    }
}

// MARK: - CBPeripheral Extension for Async RSSI

extension CBPeripheral {
    func readRSSIAsync() async throws -> Int {
        // Simple RSSI read - the delegate method handles the result
        // For now, just trigger the read and return immediately
        // A more robust implementation would use a continuation
        self.readRSSI()
        return 0 // Placeholder - ping uses this for connectivity check
    }
}
