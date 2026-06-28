import Combine
import CoreBluetooth
import Foundation
import os.log

/// Device connection implementation for Friend Pendant devices
/// Uses LC3 codec at 16 kHz with 10ms frames (30 bytes per frame)
/// Packets contain 3 frames (90 bytes LC3 data + 5 bytes footer = 95 bytes total)
/// Ported from: omi/app/lib/services/devices/friend_pendant_connection.dart
final class FriendPendantConnection: BaseDeviceConnection {

    // MARK: - Constants

    private static let packetFooterSize = 5
    private static let packetSize = 95
    private static let lc3DataSize = 90  // 3 frames of 30 bytes each
    private static let lc3FrameSize = 30 // Single LC3 frame size

    // MARK: - Private Properties

    private let logger = Logger(subsystem: "me.omi.desktop", category: "FriendPendantConnection")
    private var audioStreamSubject = PassthroughSubject<Data, Error>()
    private var audioSubscription: Task<Void, Never>?
    private var isRecording = false

    // MARK: - Initialization

    override init(device: BtDevice, transport: DeviceTransport) {
        super.init(device: device, transport: transport)
    }

    // MARK: - Connection

    override func connect() async throws {
        try await super.connect()

        // Wait for connection to stabilize
        try? await Task.sleep(nanoseconds: 1_000_000_000)

        // Subscribe to audio stream
        startAudioListener()
    }

    override func disconnect() async {
        isRecording = false
        audioSubscription?.cancel()
        audioSubscription = nil

        await super.disconnect()
    }

    // MARK: - Audio Handling

    private func startAudioListener() {
        let stream = transport.getCharacteristicStream(
            serviceUUID: DeviceUUIDs.FriendPendant.service,
            characteristicUUID: DeviceUUIDs.FriendPendant.audioCharacteristic
        )

        audioSubscription = Task { [weak self] in
            guard let self = self else { return }

            do {
                for try await data in stream {
                    if let payload = self.processAudioPacket(Array(data)) {
                        // Split 90-byte payload into 30-byte LC3 frames
                        var offset = 0
                        while offset < payload.count {
                            let end = min(offset + Self.lc3FrameSize, payload.count)
                            let chunk = Array(payload[offset..<end])

                            if chunk.count == Self.lc3FrameSize {
                                self.audioStreamSubject.send(Data(chunk))
                            }
                            offset += Self.lc3FrameSize
                        }
                    }
                }
            } catch {
                self.logger.debug("Audio stream ended: \(error.localizedDescription)")
            }
        }
    }

    /// Process audio packet by stripping the 5-byte footer
    private func processAudioPacket(_ data: [UInt8]) -> [UInt8]? {
        guard data.count >= Self.packetFooterSize else {
            return nil
        }

        // Strip the 5-byte footer to get LC3 audio data
        return Array(data.prefix(data.count - Self.packetFooterSize))
    }

    // MARK: - Battery

    override func getBatteryLevel() async -> Int {
        // Friend Pendant doesn't have battery level reporting via BLE
        // Return a placeholder value
        return 90
    }

    override func getBatteryLevelStream() -> AsyncThrowingStream<Int, Error> {
        return AsyncThrowingStream { continuation in
            Task {
                // Send initial battery level
                continuation.yield(90)

                // Send 90% every 30 seconds
                while !Task.isCancelled {
                    try? await Task.sleep(nanoseconds: 30_000_000_000)
                    continuation.yield(90)
                }

                continuation.finish()
            }
        }
    }

    // MARK: - Audio

    override func getAudioCodec() async -> BleAudioCodec {
        .lc3FS1030
    }

    override func getAudioStream() -> AsyncThrowingStream<Data, Error> {
        return AsyncThrowingStream { [weak self] continuation in
            guard let self = self else {
                continuation.finish()
                return
            }

            self.isRecording = true

            let cancellable = self.audioStreamSubject
                .sink(
                    receiveCompletion: { _ in
                        continuation.finish()
                    },
                    receiveValue: { data in
                        continuation.yield(data)
                    }
                )

            continuation.onTermination = { @Sendable _ in
                cancellable.cancel()
                Task { @MainActor in
                    self.isRecording = false
                }
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

    // MARK: - Device Info Override

    override func updateDeviceInfo() async {
        // Friend Pendant uses fixed device info
        device.modelNumber = "Friend Pendant"
        device.firmwareRevision = "1.0.0"
        device.hardwareRevision = "Friend"
        device.manufacturerName = "Friend"
    }
}
