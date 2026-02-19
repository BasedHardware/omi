import Combine
import CoreBluetooth
import Foundation
import os.log

/// Device connection implementation for Brilliant Labs Frame devices
/// Note: Frame devices use a proprietary SDK with Lua scripting.
/// This implementation provides basic BLE fallback functionality.
/// Full Frame SDK support would require the native Frame SDK for macOS.
/// Ported from: omi/app/lib/services/devices/frame_connection.dart
final class FrameDeviceConnection: BaseDeviceConnection {

    // MARK: - Constants

    /// JPEG header used to prepend to raw image data from Frame
    /// Frame sends raw JPEG data without the standard header
    private static let photoHeader = Data(base64Encoded:
        "/9j/4AAQSkZJRgABAgAAZABkAAD/2wBDACAWGBwYFCAcGhwkIiAmMFA0MCwsMGJGSjpQdGZ6" +
        "eHJmcG6AkLicgIiuim5woNqirr7EztDOfJri8uDI8LjKzsb/2wBDASIkJDAqMF40NF7GhHCE" +
        "xsbGxsbGxsbGxsbGxsbGxsbGxsbGxsbGxsbGxsbGxsbGxsbGxsbGxsbGxsbGxsbGxsb/wAAR" +
        "CAIAAgADASIAAhEBAxEB/8QAHwAAAQUBAQEBAQEAAAAAAAAAAAECAwQFBgcICQoL/8QAHwEA" +
        "AwEBAQEBAQEBAQAAAAAAAAECAwQFBgcICQoL/8QAtRAAAgEDAwIEAwUFBAQAAAF9AQIDAAQR" +
        "BRIhMUEGE1FhByJxFDKBkaEII0KxwRVS0fAkM2JyggkKFhcYGRolJicoKSo0NTY3ODk6Q0RF" +
        "RkdISUpTVFVWV1hZWmNkZWZnaGlqc3R1dnd4eXqDhIWGh4iJipKTlJWWl5iZmqKjpKWmp6ip" +
        "qrKztLW2t7i5usLDxMXGx8jJytLT1NXW19jZ2uHi4+Tl5ufo6erx8vP09fb3+Pn6/8QAtREA" +
        "AgECBAQDBAcFBAQAAQJ3AAECAxEEBSExBhJBUQdhcRMiMoEIFEKRobHBCSMzUvAVYnLRChYk" +
        "NOEl8RcYGRomJygpKjU2Nzg5OkNERUZHSElKU1RVVldYWVpjZGVmZ2hpanN0dXZ3eHl6goOE" +
        "hYaHiImKkpOUlZaXmJmaoqOkpaanqKmqsrO0tba3uLm6wsPExcbHyMnK0tPU1dbX2Nna4uPk" +
        "5ebn6Onq8vP09fb3+Pn6/9oADAMBAAIRAxEAPwA="
    )!

    // MARK: - Properties

    private let logger = Logger(subsystem: "me.omi.desktop", category: "FrameDeviceConnection")
    private var cachedBatteryLevel: Int?

    // MARK: - Initialization

    override init(device: BtDevice, transport: DeviceTransport) {
        super.init(device: device, transport: transport)
    }

    // MARK: - Connection

    override func connect() async throws {
        try await super.connect()

        // Update device info
        device.firmwareRevision = "Frame"
        device.hardwareRevision = "Brilliant Labs Frame"
        device.manufacturerName = "Brilliant Labs"
        device.modelNumber = "Frame"

        // Get initial battery level
        cachedBatteryLevel = await getBatteryLevel()
        if cachedBatteryLevel == -1 {
            cachedBatteryLevel = nil
        }

        logger.info("Connected to Frame device")
    }

    // MARK: - Battery

    override func getBatteryLevel() async -> Int {
        guard await isConnected() else { return -1 }

        do {
            let data = try await transport.readCharacteristic(
                serviceUUID: DeviceUUIDs.Battery.service,
                characteristicUUID: DeviceUUIDs.Battery.level
            )
            if !data.isEmpty {
                cachedBatteryLevel = Int(data[0])
                return cachedBatteryLevel!
            }
            return cachedBatteryLevel ?? -1
        } catch {
            logger.debug("Error reading battery level: \(error.localizedDescription)")
            return cachedBatteryLevel ?? -1
        }
    }

    override func getBatteryLevelStream() -> AsyncThrowingStream<Int, Error> {
        let stream = transport.getCharacteristicStream(
            serviceUUID: DeviceUUIDs.Battery.service,
            characteristicUUID: DeviceUUIDs.Battery.level
        )

        return AsyncThrowingStream { [weak self] continuation in
            Task { [weak self] in
                guard let self = self else {
                    continuation.finish()
                    return
                }

                do {
                    for try await data in stream {
                        if !data.isEmpty {
                            let level = Int(data[0])
                            if level != self.cachedBatteryLevel {
                                self.cachedBatteryLevel = level
                                continuation.yield(level)
                            }
                        }
                    }
                    continuation.finish()
                } catch {
                    continuation.finish(throwing: error)
                }
            }
        }
    }

    // MARK: - Audio

    override func getAudioCodec() async -> BleAudioCodec {
        // Frame uses PCM 8-bit audio
        .pcm8
    }

    override func getAudioStream() -> AsyncThrowingStream<Data, Error> {
        // Frame audio requires Frame SDK with Lua scripting
        // This would need to send "MIC START" command and listen for 0xEE prefixed data
        // For now, return an empty stream
        logger.warning("Frame audio streaming requires Frame SDK (not available on macOS)")
        return AsyncThrowingStream { $0.finish() }
    }

    // MARK: - Camera

    override func hasPhotoStreaming() async -> Bool {
        // Frame supports photo streaming through Frame SDK
        // Return true since Frame hardware supports it
        true
    }

    override func startPhotoCapture() async {
        // Frame camera control requires Frame SDK
        // Would need to send "CAMERA START" command
        logger.warning("Frame camera control requires Frame SDK (not available on macOS)")
    }

    override func stopPhotoCapture() async {
        // Frame camera control requires Frame SDK
        // Would need to send "CAMERA STOP" command
        logger.warning("Frame camera control requires Frame SDK (not available on macOS)")
    }

    override func getImageStream() -> AsyncThrowingStream<OrientedImage, Error> {
        // Frame images require Frame SDK
        // Would need to listen for FrameDataTypePrefixes.photoData
        logger.warning("Frame image streaming requires Frame SDK (not available on macOS)")
        return AsyncThrowingStream { $0.finish() }
    }

    // MARK: - Unsupported Features

    override func getFeatures() async -> OmiFeatures {
        // Frame does not support Omi features
        []
    }

    override func getButtonState() async -> [UInt8] {
        // Frame does not have a button
        []
    }

    override func getButtonStream() -> AsyncThrowingStream<[UInt8], Error> {
        AsyncThrowingStream { $0.finish() }
    }

    override func getAccelerometerStream() -> AsyncThrowingStream<AccelerometerData, Error> {
        AsyncThrowingStream { $0.finish() }
    }

    override func setLedDimRatio(_ ratio: Int) async {
        // Frame does not support LED dimming
    }

    override func getLedDimRatio() async -> Int? {
        nil
    }

    override func setMicGain(_ gain: Int) async {
        // Frame does not support mic gain control
    }

    override func getMicGain() async -> Int? {
        nil
    }

    override func playHaptic(level: Int) async -> Bool {
        // Frame does not support haptic feedback
        false
    }

    // MARK: - Storage

    override func getStorageList() async -> [Int32] {
        // Frame does not support storage
        []
    }

    override func writeToStorage(fileNum: Int, command: Int, offset: Int) async -> Bool {
        // Frame does not support storage
        false
    }

    override func getStorageStream() -> AsyncThrowingStream<Data, Error> {
        AsyncThrowingStream { $0.finish() }
    }

    // MARK: - WiFi Sync

    override func isWifiSyncSupported() async -> Bool {
        // Frame does not support WiFi sync
        false
    }

    // MARK: - Device Info

    override func updateDeviceInfo() async {
        device.modelNumber = "Frame"
        device.firmwareRevision = "Frame"
        device.hardwareRevision = "Brilliant Labs Frame"
        device.manufacturerName = "Brilliant Labs"

        // Try to read firmware version from standard BLE characteristic
        do {
            let data = try await transport.readCharacteristic(
                serviceUUID: DeviceUUIDs.DeviceInfo.service,
                characteristicUUID: DeviceUUIDs.DeviceInfo.firmwareRevision
            )
            if !data.isEmpty {
                device.firmwareRevision = String(data: data, encoding: .utf8) ?? "Frame"
            }
        } catch {
            // Use default
        }
    }
}

// MARK: - Frame SDK Notes

/*
 Full Frame support would require:

 1. Frame SDK Integration:
    - The Brilliant Labs Frame SDK uses a Lua runtime on the device
    - Commands are sent as text strings (e.g., "MIC START", "CAMERA START")
    - Responses come with data type prefixes (0xEE for audio, 0xCC for battery, etc.)

 2. Lua Script Management:
    - A main.lua script must be uploaded to the device
    - The script defines how the Frame responds to commands
    - Script hash is checked to determine if update is needed

 3. Heartbeat:
    - Regular heartbeat messages must be sent to keep the connection alive
    - "HEARTBEAT" command sent every 5 seconds

 4. Data Streams:
    - Audio: 0xEE prefix
    - Battery: 0xCC prefix
    - Status responses: 0xE1-0xE4 prefixes
    - Photo data: Special photo data type

 5. Echo Protocol:
    - Commands are acknowledged with "ECHO:<command>"
    - Must retry commands if echo not received

 If Frame SDK becomes available for macOS, this class should be updated to use it.
 */
