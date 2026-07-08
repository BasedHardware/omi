import Combine
import CoreBluetooth
import Foundation

/// Transport layer state for device communication
/// Ported from: omi/app/lib/services/devices/transports/device_transport.dart
enum DeviceTransportState: String, Sendable {
    case disconnected
    case connecting
    case connected
    case disconnecting
}

/// Abstract transport layer protocol for device communication
/// Provides a unified interface for different communication protocols (BLE, etc.)
/// Ported from: omi/app/lib/services/devices/transports/device_transport.dart
protocol DeviceTransport: AnyObject {

    /// Unique identifier for the connected device
    var deviceId: String { get }

    /// Current connection state
    var state: DeviceTransportState { get }

    /// Publisher for connection state changes
    var connectionStatePublisher: AnyPublisher<DeviceTransportState, Never> { get }

    /// Connect to the device
    func connect() async throws

    /// Disconnect from the device
    func disconnect() async

    /// Check if the device is currently connected
    func isConnected() async -> Bool

    /// Ping the device to verify connection is alive
    func ping() async -> Bool

    /// Get a stream of data from a characteristic
    /// - Parameters:
    ///   - serviceUUID: The service UUID
    ///   - characteristicUUID: The characteristic UUID
    /// - Returns: An AsyncStream of data from the characteristic
    func getCharacteristicStream(
        serviceUUID: CBUUID,
        characteristicUUID: CBUUID
    ) -> AsyncThrowingStream<Data, Error>

    /// Read a characteristic value
    /// - Parameters:
    ///   - serviceUUID: The service UUID
    ///   - characteristicUUID: The characteristic UUID
    /// - Returns: The characteristic data, or empty data if read fails
    func readCharacteristic(
        serviceUUID: CBUUID,
        characteristicUUID: CBUUID
    ) async throws -> Data

    /// Write data to a characteristic
    /// - Parameters:
    ///   - data: The data to write
    ///   - serviceUUID: The service UUID
    ///   - characteristicUUID: The characteristic UUID
    ///   - withResponse: Whether to wait for a write response
    func writeCharacteristic(
        data: Data,
        serviceUUID: CBUUID,
        characteristicUUID: CBUUID,
        withResponse: Bool
    ) async throws

    /// Clean up resources
    func dispose() async
}

// MARK: - Default Implementations

extension DeviceTransport {

    /// Write with response by default
    func writeCharacteristic(
        data: Data,
        serviceUUID: CBUUID,
        characteristicUUID: CBUUID
    ) async throws {
        try await writeCharacteristic(
            data: data,
            serviceUUID: serviceUUID,
            characteristicUUID: characteristicUUID,
            withResponse: true
        )
    }
}

// MARK: - Transport Errors

enum DeviceTransportError: LocalizedError {
    case notConnected
    case connectionFailed(String)
    case serviceNotFound(CBUUID)
    case characteristicNotFound(CBUUID)
    case readFailed(String)
    case writeFailed(String)
    case timeout
    case disposed

    var errorDescription: String? {
        switch self {
        case .notConnected:
            return "Device is not connected"
        case .connectionFailed(let reason):
            return "Connection failed: \(reason)"
        case .serviceNotFound(let uuid):
            return "Service not found: \(uuid.uuidString)"
        case .characteristicNotFound(let uuid):
            return "Characteristic not found: \(uuid.uuidString)"
        case .readFailed(let reason):
            return "Read failed: \(reason)"
        case .writeFailed(let reason):
            return "Write failed: \(reason)"
        case .timeout:
            return "Operation timed out"
        case .disposed:
            return "Transport has been disposed"
        }
    }
}
