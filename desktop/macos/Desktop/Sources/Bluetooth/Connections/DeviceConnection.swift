import Combine
import CoreBluetooth
import Foundation
import os.log

// MARK: - Connection State

/// Device connection state
/// Ported from: omi/app/lib/services/devices.dart
enum DeviceConnectionState: String, Sendable {
    case connected
    case disconnected
}

// MARK: - Connection Error

/// Device connection errors
enum DeviceConnectionError: LocalizedError {
    case alreadyConnected
    case connectionFailed(String)
    case notConnected
    case operationFailed(String)

    var errorDescription: String? {
        switch self {
        case .alreadyConnected:
            return "Connection already established. Disconnect before starting a new connection."
        case .connectionFailed(let reason):
            return "Connection failed: \(reason)"
        case .notConnected:
            return "Device is not connected"
        case .operationFailed(let reason):
            return "Operation failed: \(reason)"
        }
    }
}

// MARK: - Oriented Image (OpenGlass)

/// Image with orientation data from OpenGlass camera
struct OrientedImage {
    let imageData: Data
    let orientation: ImageOrientation
}

// MARK: - Accelerometer Data

/// Accelerometer and gyroscope data from device
/// Ported from: omi/app/lib/services/devices/omi_connection.dart
struct AccelerometerData {
    /// Accelerometer X axis value
    let accelX: Double
    /// Accelerometer Y axis value
    let accelY: Double
    /// Accelerometer Z axis value
    let accelZ: Double
    /// Gyroscope X axis value
    let gyroX: Double
    /// Gyroscope Y axis value
    let gyroY: Double
    /// Gyroscope Z axis value
    let gyroZ: Double

    /// Calculate magnitude for fall detection
    /// Returns sqrt(accelX² + accelY² + accelZ²)
    var magnitude: Double {
        sqrt(accelX * accelX + accelY * accelY + accelZ * accelZ)
    }

    /// Check if this reading indicates a potential fall (magnitude > 30)
    var indicatesFall: Bool {
        magnitude > 30.0
    }
}

// MARK: - Device Connection Delegate

/// Delegate for device connection events
protocol DeviceConnectionDelegate: AnyObject {
    /// Called when device disconnects unexpectedly during an operation
    func deviceConnection(_ connection: DeviceConnection, didDisconnectUnexpectedly device: BtDevice)

    /// Called when a potential fall is detected
    func deviceConnection(_ connection: DeviceConnection, didDetectFall data: AccelerometerData)
}

// MARK: - Device Connection Protocol

/// Abstract protocol for device connections
/// Ported from: omi/app/lib/services/devices/device_connection.dart
protocol DeviceConnection: AnyObject {

    // MARK: - Properties

    /// The connected device
    var device: BtDevice { get set }

    /// The underlying transport
    var transport: DeviceTransport { get }

    /// Current connection state
    var connectionState: DeviceConnectionState { get }

    /// Publisher for connection state changes
    var connectionStatePublisher: AnyPublisher<DeviceConnectionState, Never> { get }

    /// Last successful ping time
    var lastPongAt: Date? { get }

    /// Cached device features
    var cachedFeatures: OmiFeatures? { get }

    /// Delegate for connection events
    var delegate: DeviceConnectionDelegate? { get set }

    /// Alias for connectionState (Flutter compatibility)
    var status: DeviceConnectionState { get }

    // MARK: - Connection Lifecycle

    /// Unpair the device (clear pairing info)
    func unpair() async

    /// Connect to the device
    func connect() async throws

    /// Disconnect from the device
    func disconnect() async

    /// Check if connected
    func isConnected() async -> Bool

    /// Ping the device to verify connection
    func ping() async -> Bool

    // MARK: - Battery

    /// Get current battery level (0-100, or -1 if unavailable)
    func getBatteryLevel() async -> Int

    /// Get a stream of battery level updates
    func getBatteryLevelStream() -> AsyncThrowingStream<Int, Error>

    // MARK: - Audio

    /// Get the audio codec used by the device
    func getAudioCodec() async -> BleAudioCodec

    /// Get a stream of audio data from the device
    func getAudioStream() -> AsyncThrowingStream<Data, Error>

    // MARK: - Button

    /// Get the current button state
    func getButtonState() async -> [UInt8]

    /// Get a stream of button press events
    func getButtonStream() -> AsyncThrowingStream<[UInt8], Error>

    // MARK: - Storage

    /// Get list of storage files/lengths
    func getStorageList() async -> [Int32]

    /// Write command to storage
    func writeToStorage(fileNum: Int, command: Int, offset: Int) async -> Bool

    /// Get a stream of storage data
    func getStorageStream() -> AsyncThrowingStream<Data, Error>

    // MARK: - Camera (OpenGlass)

    /// Check if device has photo streaming capability
    func hasPhotoStreaming() async -> Bool

    /// Start photo capture controller
    func startPhotoCapture() async

    /// Stop photo capture controller
    func stopPhotoCapture() async

    /// Get a stream of images from the camera
    func getImageStream() -> AsyncThrowingStream<OrientedImage, Error>

    // MARK: - Accelerometer

    /// Get a stream of accelerometer/gyroscope data
    func getAccelerometerStream() -> AsyncThrowingStream<AccelerometerData, Error>

    // MARK: - Speaker/Haptic

    /// Play haptic feedback (1=20ms, 2=50ms, 3=500ms)
    func playHaptic(level: Int) async -> Bool

    // MARK: - Features

    /// Get device feature flags
    func getFeatures() async -> OmiFeatures

    // MARK: - Settings

    /// Set LED dim ratio (0-100)
    func setLedDimRatio(_ ratio: Int) async

    /// Get LED dim ratio
    func getLedDimRatio() async -> Int?

    /// Set microphone gain (0-100)
    func setMicGain(_ gain: Int) async

    /// Get microphone gain
    func getMicGain() async -> Int?

    // MARK: - WiFi Sync

    /// Check if WiFi sync is supported
    func isWifiSyncSupported() async -> Bool

    /// Setup WiFi sync with credentials
    func setupWifiSync(ssid: String, password: String) async -> WifiSyncSetupResult

    /// Start WiFi sync
    func startWifiSync() async -> Bool

    /// Stop WiFi sync
    func stopWifiSync() async -> Bool

    /// Get a stream of WiFi sync status updates
    func getWifiSyncStatusStream() -> AsyncThrowingStream<Int, Error>
}

// MARK: - Base Implementation

/// Base class providing common device connection functionality
/// Subclasses implement device-specific behavior
class BaseDeviceConnection: DeviceConnection {

    // MARK: - Properties

    var device: BtDevice
    let transport: DeviceTransport

    private(set) var connectionState: DeviceConnectionState = .disconnected
    private let connectionStateSubject = PassthroughSubject<DeviceConnectionState, Never>()

    var connectionStatePublisher: AnyPublisher<DeviceConnectionState, Never> {
        connectionStateSubject.eraseToAnyPublisher()
    }

    private(set) var lastPongAt: Date?
    private(set) var cachedFeatures: OmiFeatures?

    /// Delegate for connection events
    weak var delegate: DeviceConnectionDelegate?

    /// Alias for connectionState (Flutter compatibility)
    var status: DeviceConnectionState { connectionState }

    private var transportStateSubscription: AnyCancellable?
    private let logger = Logger(subsystem: "me.omi.desktop", category: "DeviceConnection")

    // MARK: - Initialization

    init(device: BtDevice, transport: DeviceTransport) {
        self.device = device
        self.transport = transport

        // Listen to transport state changes
        transportStateSubscription = transport.connectionStatePublisher
            .sink { [weak self] transportState in
                self?.handleTransportStateChange(transportState)
            }
    }

    deinit {
        transportStateSubscription?.cancel()
    }

    private func handleTransportStateChange(_ transportState: DeviceTransportState) {
        let newState: DeviceConnectionState = transportState == .connected ? .connected : .disconnected

        if connectionState != newState {
            connectionState = newState
            connectionStateSubject.send(newState)
        }
    }

    // MARK: - Connection Lifecycle

    func unpair() async {
        // Clear any cached pairing information
        cachedFeatures = nil
        lastPongAt = nil

        // Disconnect if connected
        if await isConnected() {
            await disconnect()
        }

        logger.info("Device unpaired: \(self.device.displayName)")
    }

    func connect() async throws {
        guard connectionState != .connected else {
            throw DeviceConnectionError.alreadyConnected
        }

        do {
            try await transport.connect()

            // Verify connection with ping
            let pingSuccess = await ping()
            if !pingSuccess {
                logger.warning("Ping failed after connection, but continuing")
            }

            // Update device info
            await updateDeviceInfo()

            connectionState = .connected
            connectionStateSubject.send(.connected)

        } catch {
            throw DeviceConnectionError.connectionFailed(error.localizedDescription)
        }
    }

    func disconnect() async {
        connectionState = .disconnected
        connectionStateSubject.send(.disconnected)

        await transport.disconnect()
        transportStateSubscription?.cancel()
        transportStateSubscription = nil
    }

    func isConnected() async -> Bool {
        await transport.isConnected()
    }

    func ping() async -> Bool {
        let result = await transport.ping()
        if result {
            lastPongAt = Date()
        }
        return result
    }

    /// Update device info from device information service
    func updateDeviceInfo() async {
        // Read device info characteristics
        do {
            let modelData = try await transport.readCharacteristic(
                serviceUUID: DeviceUUIDs.DeviceInfo.service,
                characteristicUUID: DeviceUUIDs.DeviceInfo.modelNumber
            )
            if !modelData.isEmpty {
                device.modelNumber = String(data: modelData, encoding: .utf8)
            }

            let firmwareData = try await transport.readCharacteristic(
                serviceUUID: DeviceUUIDs.DeviceInfo.service,
                characteristicUUID: DeviceUUIDs.DeviceInfo.firmwareRevision
            )
            if !firmwareData.isEmpty {
                device.firmwareRevision = String(data: firmwareData, encoding: .utf8)
            }

            let hardwareData = try await transport.readCharacteristic(
                serviceUUID: DeviceUUIDs.DeviceInfo.service,
                characteristicUUID: DeviceUUIDs.DeviceInfo.hardwareRevision
            )
            if !hardwareData.isEmpty {
                device.hardwareRevision = String(data: hardwareData, encoding: .utf8)
            }

            let manufacturerData = try await transport.readCharacteristic(
                serviceUUID: DeviceUUIDs.DeviceInfo.service,
                characteristicUUID: DeviceUUIDs.DeviceInfo.manufacturerName
            )
            if !manufacturerData.isEmpty {
                device.manufacturerName = String(data: manufacturerData, encoding: .utf8)
            }
        } catch {
            logger.debug("Failed to read device info: \(error.localizedDescription)")
        }
    }

    // MARK: - Battery (Default Implementation)

    func getBatteryLevel() async -> Int {
        guard await isConnected() else { return -1 }

        do {
            let data = try await transport.readCharacteristic(
                serviceUUID: DeviceUUIDs.Battery.service,
                characteristicUUID: DeviceUUIDs.Battery.level
            )
            return data.isEmpty ? -1 : Int(data[0])
        } catch {
            logger.debug("Failed to read battery level: \(error.localizedDescription)")
            return -1
        }
    }

    func getBatteryLevelStream() -> AsyncThrowingStream<Int, Error> {
        let stream = transport.getCharacteristicStream(
            serviceUUID: DeviceUUIDs.Battery.service,
            characteristicUUID: DeviceUUIDs.Battery.level
        )

        return AsyncThrowingStream { continuation in
            Task {
                do {
                    for try await data in stream {
                        if !data.isEmpty {
                            continuation.yield(Int(data[0]))
                        }
                    }
                    continuation.finish()
                } catch {
                    continuation.finish(throwing: error)
                }
            }
        }
    }

    // MARK: - Audio (Default Implementation)

    func getAudioCodec() async -> BleAudioCodec {
        guard await isConnected() else { return .pcm8 }

        do {
            let data = try await transport.readCharacteristic(
                serviceUUID: DeviceUUIDs.Omi.mainService,
                characteristicUUID: DeviceUUIDs.Omi.audioCodec
            )

            guard !data.isEmpty else { return .pcm8 }

            let codecId = Int(data[0])
            switch codecId {
            case 1: return .pcm8
            case 20: return .opus
            case 21: return .opusFS320
            default: return .pcm8
            }
        } catch {
            logger.debug("Failed to read audio codec: \(error.localizedDescription)")
            return .pcm8
        }
    }

    func getAudioStream() -> AsyncThrowingStream<Data, Error> {
        transport.getCharacteristicStream(
            serviceUUID: DeviceUUIDs.Omi.mainService,
            characteristicUUID: DeviceUUIDs.Omi.audioDataStream
        )
    }

    // MARK: - Button (Default Implementation)

    func getButtonState() async -> [UInt8] {
        guard await isConnected() else { return [] }

        do {
            let data = try await transport.readCharacteristic(
                serviceUUID: DeviceUUIDs.Button.service,
                characteristicUUID: DeviceUUIDs.Button.trigger
            )
            return Array(data)
        } catch {
            logger.debug("Failed to read button state: \(error.localizedDescription)")
            return []
        }
    }

    func getButtonStream() -> AsyncThrowingStream<[UInt8], Error> {
        let stream = transport.getCharacteristicStream(
            serviceUUID: DeviceUUIDs.Button.service,
            characteristicUUID: DeviceUUIDs.Button.trigger
        )

        return AsyncThrowingStream { continuation in
            Task {
                do {
                    for try await data in stream {
                        continuation.yield(Array(data))
                    }
                    continuation.finish()
                } catch {
                    continuation.finish(throwing: error)
                }
            }
        }
    }

    // MARK: - Storage (Default Implementation)

    func getStorageList() async -> [Int32] {
        guard await isConnected() else { return [] }

        do {
            let data = try await transport.readCharacteristic(
                serviceUUID: DeviceUUIDs.Storage.service,
                characteristicUUID: DeviceUUIDs.Storage.readControl
            )

            var lengths: [Int32] = []
            let totalEntries = data.count / 4

            for i in 0..<totalEntries {
                let baseIndex = i * 4
                let value = Int32(data[baseIndex]) |
                           (Int32(data[baseIndex + 1]) << 8) |
                           (Int32(data[baseIndex + 2]) << 16) |
                           (Int32(data[baseIndex + 3]) << 24)
                lengths.append(value)
            }

            return lengths
        } catch {
            logger.debug("Failed to read storage list: \(error.localizedDescription)")
            return []
        }
    }

    func writeToStorage(fileNum: Int, command: Int, offset: Int) async -> Bool {
        guard await isConnected() else { return false }

        let offsetBytes: [UInt8] = [
            UInt8((offset >> 24) & 0xFF),
            UInt8((offset >> 16) & 0xFF),
            UInt8((offset >> 8) & 0xFF),
            UInt8(offset & 0xFF)
        ]

        let data = Data([
            UInt8(command & 0xFF),
            UInt8(fileNum & 0xFF),
            offsetBytes[0], offsetBytes[1], offsetBytes[2], offsetBytes[3]
        ])

        do {
            try await transport.writeCharacteristic(
                data: data,
                serviceUUID: DeviceUUIDs.Storage.service,
                characteristicUUID: DeviceUUIDs.Storage.dataStream,
                withResponse: true
            )
            return true
        } catch {
            logger.debug("Failed to write to storage: \(error.localizedDescription)")
            return false
        }
    }

    func getStorageStream() -> AsyncThrowingStream<Data, Error> {
        transport.getCharacteristicStream(
            serviceUUID: DeviceUUIDs.Storage.service,
            characteristicUUID: DeviceUUIDs.Storage.dataStream
        )
    }

    // MARK: - Camera (Default - Override in subclass)

    func hasPhotoStreaming() async -> Bool { false }
    func startPhotoCapture() async {}
    func stopPhotoCapture() async {}

    func getImageStream() -> AsyncThrowingStream<OrientedImage, Error> {
        AsyncThrowingStream { $0.finish() }
    }

    // MARK: - Accelerometer (Default)

    func getAccelerometerStream() -> AsyncThrowingStream<AccelerometerData, Error> {
        let stream = transport.getCharacteristicStream(
            serviceUUID: DeviceUUIDs.Accelerometer.service,
            characteristicUUID: DeviceUUIDs.Accelerometer.dataStream
        )

        return AsyncThrowingStream { [weak self] continuation in
            Task { [weak self] in
                guard let self = self else {
                    continuation.finish()
                    return
                }

                do {
                    for try await data in stream {
                        // Parse 6-axis accelerometer/gyroscope data
                        // Format: 12 bytes = 6 x Int16 (little-endian)
                        // [accelX, accelY, accelZ, gyroX, gyroY, gyroZ]
                        guard data.count >= 12 else {
                            // Fallback: if only 1 byte, treat as simple magnitude
                            if !data.isEmpty {
                                let accelData = AccelerometerData(
                                    accelX: Double(data[0]),
                                    accelY: 0,
                                    accelZ: 0,
                                    gyroX: 0,
                                    gyroY: 0,
                                    gyroZ: 0
                                )
                                continuation.yield(accelData)
                            }
                            continue
                        }

                        // Parse Int16 values (little-endian)
                        func parseInt16(at offset: Int) -> Double {
                            let low = Int16(data[offset])
                            let high = Int16(data[offset + 1])
                            let value = low | (high << 8)
                            return Double(value)
                        }

                        let accelData = AccelerometerData(
                            accelX: parseInt16(at: 0),
                            accelY: parseInt16(at: 2),
                            accelZ: parseInt16(at: 4),
                            gyroX: parseInt16(at: 6),
                            gyroY: parseInt16(at: 8),
                            gyroZ: parseInt16(at: 10)
                        )

                        continuation.yield(accelData)

                        // Check for fall detection and notify delegate
                        if accelData.indicatesFall {
                            self.logger.warning("Fall detected! Magnitude: \(accelData.magnitude)")
                            self.delegate?.deviceConnection(self, didDetectFall: accelData)
                        }
                    }
                    continuation.finish()
                } catch {
                    continuation.finish(throwing: error)
                }
            }
        }
    }

    // MARK: - Speaker/Haptic (Default)

    func playHaptic(level: Int) async -> Bool {
        guard await isConnected() else { return false }

        do {
            try await transport.writeCharacteristic(
                data: Data([UInt8(level & 0xFF)]),
                serviceUUID: DeviceUUIDs.Speaker.service,
                characteristicUUID: DeviceUUIDs.Speaker.dataStream,
                withResponse: true
            )
            return true
        } catch {
            logger.debug("Failed to play haptic: \(error.localizedDescription)")
            return false
        }
    }

    // MARK: - Features (Default - Override in subclass)

    func getFeatures() async -> OmiFeatures {
        if let cached = cachedFeatures {
            return cached
        }

        guard await isConnected() else { return [] }

        do {
            let data = try await transport.readCharacteristic(
                serviceUUID: DeviceUUIDs.Omi.featuresService,
                characteristicUUID: DeviceUUIDs.Omi.featuresCharacteristic
            )

            guard data.count >= 4 else { return [] }

            let rawValue = Int(data[0]) |
                          (Int(data[1]) << 8) |
                          (Int(data[2]) << 16) |
                          (Int(data[3]) << 24)

            let features = OmiFeatures(rawValue: rawValue)
            cachedFeatures = features
            return features
        } catch {
            logger.debug("Failed to read features: \(error.localizedDescription)")
            return []
        }
    }

    // MARK: - Settings (Default - Override in subclass)

    func setLedDimRatio(_ ratio: Int) async {}
    func getLedDimRatio() async -> Int? { nil }
    func setMicGain(_ gain: Int) async {}
    func getMicGain() async -> Int? { nil }

    // MARK: - WiFi Sync (Default - Override in subclass)

    func isWifiSyncSupported() async -> Bool { false }

    func setupWifiSync(ssid: String, password: String) async -> WifiSyncSetupResult {
        // Validate credentials first
        if let ssidError = WifiCredentialsValidator.validateSsid(ssid) {
            return .failure(.ssidLengthInvalid, customMessage: ssidError)
        }
        if let passwordError = WifiCredentialsValidator.validatePassword(password) {
            return .failure(.passwordLengthInvalid, customMessage: passwordError)
        }

        // Default implementation returns not supported
        return .failure(.wifiHardwareNotAvailable)
    }

    func startWifiSync() async -> Bool { false }
    func stopWifiSync() async -> Bool { false }

    func getWifiSyncStatusStream() -> AsyncThrowingStream<Int, Error> {
        // Default implementation returns empty stream
        AsyncThrowingStream { $0.finish() }
    }

    // MARK: - Helper Methods

    /// Notify delegate of unexpected disconnection
    func notifyUnexpectedDisconnection() {
        delegate?.deviceConnection(self, didDisconnectUnexpectedly: device)
    }
}
