import Combine
import CoreBluetooth
import Foundation
import os.log

/// Device connection implementation for Fieldy devices
/// Uses Opus codec at FS320 (32kHz) with 40-byte frames
/// Ported from: omi/app/lib/services/devices/fieldy_connection.dart
final class FieldyDeviceConnection: BaseDeviceConnection {

    // MARK: - Constants

    /// Fieldy uses same characteristic for control and audio
    private static let characteristicUUID = "82a48422-3ca9-4156-ae67-4170f58666e0"
    private static let opusFrameSize = 40

    // MARK: - Private Properties

    private let logger = Logger(subsystem: "me.omi.desktop", category: "FieldyDeviceConnection")
    private var audioStreamSubject = PassthroughSubject<Data, Error>()
    private var audioSubscription: Task<Void, Never>?

    // MARK: - Initialization

    override init(device: BtDevice, transport: DeviceTransport) {
        super.init(device: device, transport: transport)
    }

    // MARK: - Connection

    override func connect() async throws {
        try await super.connect()
        try? await Task.sleep(nanoseconds: 1_000_000_000)
    }

    override func disconnect() async {
        audioSubscription?.cancel()
        audioSubscription = nil
        await super.disconnect()
    }

    // MARK: - Battery

    override func getBatteryLevel() async -> Int {
        guard await isConnected() else { return -1 }

        do {
            let data = try await transport.readCharacteristic(
                serviceUUID: DeviceUUIDs.Battery.service,
                characteristicUUID: DeviceUUIDs.Battery.level
            )
            return data.isEmpty ? -1 : Int(data[0])
        } catch {
            logger.debug("Error reading battery level: \(error.localizedDescription)")
            return -1
        }
    }

    // MARK: - Audio

    override func getAudioCodec() async -> BleAudioCodec {
        .opusFS320
    }

    override func getAudioStream() -> AsyncThrowingStream<Data, Error> {
        let stream = transport.getCharacteristicStream(
            serviceUUID: DeviceUUIDs.Fieldy.service,
            characteristicUUID: CBUUID(string: Self.characteristicUUID)
        )

        return AsyncThrowingStream { [weak self] continuation in
            guard let self = self else {
                continuation.finish()
                return
            }

            self.audioSubscription = Task { [weak self] in
                guard let self = self else {
                    continuation.finish()
                    return
                }

                do {
                    for try await data in stream {
                        guard !data.isEmpty else { continue }

                        // Each BLE notification contains 6 Opus frames of 40 bytes each (240 bytes total)
                        var offset = 0
                        while offset + Self.opusFrameSize <= data.count {
                            let frame = data.subdata(in: offset..<(offset + Self.opusFrameSize))

                            // Verify frame starts with Opus TOC byte (0xb8)
                            if frame[0] == 0xb8 {
                                continuation.yield(frame)
                            } else {
                                self.logger.debug("Frame at offset \(offset) doesn't start with 0xb8: \(String(format: "0x%02x", frame[0]))")
                                // Still send it as it might be valid
                                continuation.yield(frame)
                            }

                            offset += Self.opusFrameSize
                        }

                        // Handle remaining bytes if any
                        if offset < data.count {
                            let remaining = data.subdata(in: offset..<data.count)
                            self.logger.debug("Found \(remaining.count)-byte frame (not \(Self.opusFrameSize) bytes)")
                            if !remaining.isEmpty && remaining[0] == 0xb8 {
                                continuation.yield(remaining)
                            }
                        }
                    }
                    continuation.finish()
                } catch {
                    continuation.finish(throwing: error)
                }
            }

            continuation.onTermination = { @Sendable [weak self] _ in
                self?.audioSubscription?.cancel()
            }
        }
    }

    // MARK: - Unsupported Features

    override func getButtonState() async -> [UInt8] { [] }
    override func getButtonStream() -> AsyncThrowingStream<[UInt8], Error> {
        AsyncThrowingStream { $0.finish() }
    }
    override func hasPhotoStreaming() async -> Bool { false }
    override func getAccelerometerStream() -> AsyncThrowingStream<AccelerometerData, Error> {
        AsyncThrowingStream { $0.finish() }
    }
    override func getFeatures() async -> OmiFeatures { [] }

    // MARK: - Device Info

    override func updateDeviceInfo() async {
        // Try to read from device info service first
        await super.updateDeviceInfo()

        // Set defaults if not available
        if device.modelNumber == nil { device.modelNumber = "Fieldy" }
        if device.firmwareRevision == nil { device.firmwareRevision = "1.0.0" }
        if device.hardwareRevision == nil { device.hardwareRevision = "Fieldy Hardware" }
        if device.manufacturerName == nil { device.manufacturerName = "Fieldy" }
    }
}
