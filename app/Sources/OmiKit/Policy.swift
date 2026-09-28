#if !SKIP
import CNativeCore
#endif

// Swift facade over the shared C++ middleware in `native-core/`.
//
// The middleware stays C++ everywhere (codec, transport policy, HTTP plan
// facade, recording rules) — it is never re-derived in Swift and never
// ported to Kotlin. Apple and Windows bind it directly through the C ABI
// (`DefaultPolicyBridge` below compiles the real `CNativeCore` sources);
// Android binds the same C++ through JNI, and its Kotlin bridge object is
// injected into `Policy.bridge` at host bootstrap.

public protocol NativePolicyBridge: Sendable {
    /// Strip path at the first '?' or '#'.
    func routeStrip(_ path: String) -> String?
    /// True when the path is a capture/v5 backend route.
    func isCapturePath(_ path: String) -> Bool
    /// Request timeout seconds (transcribe POST → 150, else 60).
    func requestTimeoutSeconds(method: String, path: String) -> Int
    /// True when example-platform allows the method+path.
    func examplePlatformSupported(method: String, path: String) -> Bool
    func isLoopbackHostname(_ hostname: String) -> Bool
    func isCloudHostname(_ hostname: String) -> Bool
    func isAllowedV5Hostname(_ hostname: String) -> Bool
    /// True when the new software plane is selected.
    func softwarePlaneIsNew(stored: String?, stampedValid: Bool) -> Bool
    func recordingCapturedAtValid(_ capturedAtSeconds: Double) -> Bool
    func recordingRetryableStatus(_ status: Int) -> Bool
    func recordingOwnerKeyValid(_ ownerKey: String) -> Bool
    func recordingReceiptValid(_ receipt: String) -> Bool
    func recordingUUIDValid(_ value: String) -> Bool
    func packetChecksum(_ data: [UInt8]) -> UInt32
    /// Normalizes a framed packet; returns (status, payload) with status 0
    /// on success, mirroring `OMI_STATUS_*` from `omi_native_boundary.h`.
    func normalizePacket(_ raw: [UInt8]) -> (status: Int32, payload: [UInt8])
    /// Native host capability JSON.
    func nativeCapabilities() -> String?

    // Portable BLE device logic (`omi_device`): naming, energy rule,
    // device-info parsing, packet assembly, capture machine. Handles are
    // opaque Int64 tokens (native pointers under the C ABI / JNI globals on
    // Android); every rule itself lives in the C++ middleware only.

    func deviceDiscoveredName(
        advertisedLocalName: String?, cachedName: String?, manufacturerData: [UInt8]?
    ) -> String
    func deviceIsNotePinAdvertisement(_ manufacturerData: [UInt8]?) -> Bool
    func deviceIsOmiLike(_ name: String) -> Bool
    func deviceShouldPersistBatteryReading(
        previousLevel: Int32?, previousTimestampMs: Int64?, level: Int32, nowMs: Int64
    ) -> Bool
    func deviceCharacteristicText(_ bytes: [UInt8]?) -> String?
    func deviceAssemblerCreate() -> Int64
    func deviceAssemblerDestroy(_ handle: Int64)
    func deviceAssemblerReset(_ handle: Int64)
    func deviceAssemblerClassify(_ handle: Int64, raw: [UInt8]) -> DevicePacketDecision
    func deviceCaptureCreate() -> Int64
    func deviceCaptureDestroy(_ handle: Int64)
    func deviceCaptureStage(_ handle: Int64) -> Int32
    func deviceCaptureIsCapturing(_ handle: Int64) -> Bool
    func deviceCaptureOpen(
        _ handle: Int64, deviceId: String, deviceName: String?, codec: Int32, nowMs: Int64
    ) -> Bool
    /// -1 when the packet was not accepted, else the accepted packet index.
    func deviceCaptureIngest(_ handle: Int64, raw: [UInt8], receivedAtMs: Int64) -> Int64
    func deviceCaptureFail(_ handle: Int64)
    /// Non-nil when a nonempty batch was handed off and is readable through
    /// `deviceCaptureHandoff`'s return value copies.
    func deviceCaptureHandoff(_ handle: Int64, nowMs: Int64) -> DeviceCaptureHandoff?
    func deviceCaptureBatchCount(_ handle: Int64) -> Int
    func deviceCaptureBatchByteCount(_ handle: Int64) -> Int
    func deviceCaptureStartedAtMs(_ handle: Int64) -> Int64
    func deviceCaptureDeviceId(_ handle: Int64) -> String
    func deviceCaptureDeviceName(_ handle: Int64) -> String?
    func deviceCaptureCodec(_ handle: Int64) -> Int32
}

/// One classified audio notification (`omi_device` assembler outcome).
public struct DevicePacketDecision: Sendable, Equatable {
    /// `OMI_DEVICE_PACKET_*`: 0 accepted, 1 duplicate, 2 short frame,
    /// 3 codec-invalid.
    public var kind: Int32
    public var index: UInt16
    public var payload: [UInt8]
    /// `OMI_STATUS_*` from the codec when kind is 3, else 0.
    public var codecStatus: Int32

    public init(kind: Int32, index: UInt16, payload: [UInt8], codecStatus: Int32) {
        self.kind = kind
        self.index = index
        self.payload = payload
        self.codecStatus = codecStatus
    }
}

/// The completed handoff of one capture: journal identity fields plus the
/// batched packets (readable copies, not live references).
public struct DeviceCaptureHandoff: Sendable, Equatable {
    public struct Packet: Sendable, Equatable {
        public var index: UInt16
        public var payload: [UInt8]
        public var receivedAtMs: Int64

        public init(index: UInt16, payload: [UInt8], receivedAtMs: Int64) {
            self.index = index
            self.payload = payload
            self.receivedAtMs = receivedAtMs
        }
    }

    public var startedAtMs: Int64
    public var endedAtMs: Int64
    public var byteCount: Int
    public var packets: [Packet]

    public init(
        startedAtMs: Int64, endedAtMs: Int64, byteCount: Int, packets: [Packet]
    ) {
        self.startedAtMs = startedAtMs
        self.endedAtMs = endedAtMs
        self.byteCount = byteCount
        self.packets = packets
    }
}

/// The process-wide bridge. Apple/Windows use the C++ binding by default;
/// the Android host replaces it with its JNI bridge at bootstrap.
public enum Policy {
    public nonisolated(unsafe) static var bridge: NativePolicyBridge =
        DefaultPolicyBridge()

    public static func routeStrip(_ path: String) -> String? {
        bridge.routeStrip(path)
    }
    public static func isCapturePath(_ path: String) -> Bool {
        bridge.isCapturePath(path)
    }
    public static func requestTimeoutSeconds(method: String, path: String) -> Int {
        bridge.requestTimeoutSeconds(method: method, path: path)
    }
    public static func examplePlatformSupported(method: String, path: String) -> Bool {
        bridge.examplePlatformSupported(method: method, path: path)
    }
    public static func isLoopbackHostname(_ hostname: String) -> Bool {
        bridge.isLoopbackHostname(hostname)
    }
    public static func isCloudHostname(_ hostname: String) -> Bool {
        bridge.isCloudHostname(hostname)
    }
    public static func isAllowedV5Hostname(_ hostname: String) -> Bool {
        bridge.isAllowedV5Hostname(hostname)
    }
    public static func softwarePlaneIsNew(stored: String?, stampedValid: Bool) -> Bool {
        bridge.softwarePlaneIsNew(stored: stored, stampedValid: stampedValid)
    }
    public static func recordingCapturedAtValid(_ seconds: Double) -> Bool {
        bridge.recordingCapturedAtValid(seconds)
    }
    public static func recordingRetryableStatus(_ status: Int) -> Bool {
        bridge.recordingRetryableStatus(status)
    }
    public static func recordingOwnerKeyValid(_ ownerKey: String) -> Bool {
        bridge.recordingOwnerKeyValid(ownerKey)
    }
    public static func recordingReceiptValid(_ receipt: String) -> Bool {
        bridge.recordingReceiptValid(receipt)
    }
    public static func recordingUUIDValid(_ value: String) -> Bool {
        bridge.recordingUUIDValid(value)
    }
    public static func packetChecksum(_ data: [UInt8]) -> UInt32 {
        bridge.packetChecksum(data)
    }
    public static func normalizePacket(_ raw: [UInt8]) -> (status: Int32, payload: [UInt8]) {
        bridge.normalizePacket(raw)
    }
    public static func nativeCapabilities() -> String? {
        bridge.nativeCapabilities()
    }

    // MARK: Portable BLE device logic (omi_device)

    public static func deviceDiscoveredName(
        advertisedLocalName: String?, cachedName: String?, manufacturerData: [UInt8]?
    ) -> String {
        bridge.deviceDiscoveredName(
            advertisedLocalName: advertisedLocalName, cachedName: cachedName,
            manufacturerData: manufacturerData)
    }
    public static func deviceIsNotePinAdvertisement(_ manufacturerData: [UInt8]?) -> Bool {
        bridge.deviceIsNotePinAdvertisement(manufacturerData)
    }
    public static func deviceIsOmiLike(_ name: String) -> Bool {
        bridge.deviceIsOmiLike(name)
    }
    public static func deviceShouldPersistBatteryReading(
        previousLevel: Int32?, previousTimestampMs: Int64?, level: Int32, nowMs: Int64
    ) -> Bool {
        bridge.deviceShouldPersistBatteryReading(
            previousLevel: previousLevel, previousTimestampMs: previousTimestampMs,
            level: level, nowMs: nowMs)
    }
    public static func deviceCharacteristicText(_ bytes: [UInt8]?) -> String? {
        bridge.deviceCharacteristicText(bytes)
    }
    public static func deviceAssemblerCreate() -> Int64 {
        bridge.deviceAssemblerCreate()
    }
    public static func deviceAssemblerDestroy(_ handle: Int64) {
        bridge.deviceAssemblerDestroy(handle)
    }
    public static func deviceAssemblerReset(_ handle: Int64) {
        bridge.deviceAssemblerReset(handle)
    }
    public static func deviceAssemblerClassify(
        _ handle: Int64, raw: [UInt8]
    ) -> DevicePacketDecision {
        bridge.deviceAssemblerClassify(handle, raw: raw)
    }
    public static func deviceCaptureCreate() -> Int64 {
        bridge.deviceCaptureCreate()
    }
    public static func deviceCaptureDestroy(_ handle: Int64) {
        bridge.deviceCaptureDestroy(handle)
    }
    public static func deviceCaptureStage(_ handle: Int64) -> Int32 {
        bridge.deviceCaptureStage(handle)
    }
    public static func deviceCaptureIsCapturing(_ handle: Int64) -> Bool {
        bridge.deviceCaptureIsCapturing(handle)
    }
    public static func deviceCaptureOpen(
        _ handle: Int64, deviceId: String, deviceName: String?, codec: Int32, nowMs: Int64
    ) -> Bool {
        bridge.deviceCaptureOpen(
            handle, deviceId: deviceId, deviceName: deviceName, codec: codec, nowMs: nowMs)
    }
    public static func deviceCaptureIngest(
        _ handle: Int64, raw: [UInt8], receivedAtMs: Int64
    ) -> Int64 {
        bridge.deviceCaptureIngest(handle, raw: raw, receivedAtMs: receivedAtMs)
    }
    public static func deviceCaptureFail(_ handle: Int64) {
        bridge.deviceCaptureFail(handle)
    }
    public static func deviceCaptureHandoff(
        _ handle: Int64, nowMs: Int64
    ) -> DeviceCaptureHandoff? {
        bridge.deviceCaptureHandoff(handle, nowMs: nowMs)
    }
    public static func deviceCaptureBatchCount(_ handle: Int64) -> Int {
        bridge.deviceCaptureBatchCount(handle)
    }
    public static func deviceCaptureBatchByteCount(_ handle: Int64) -> Int {
        bridge.deviceCaptureBatchByteCount(handle)
    }
    public static func deviceCaptureStartedAtMs(_ handle: Int64) -> Int64 {
        bridge.deviceCaptureStartedAtMs(handle)
    }
    public static func deviceCaptureDeviceId(_ handle: Int64) -> String {
        bridge.deviceCaptureDeviceId(handle)
    }
    public static func deviceCaptureDeviceName(_ handle: Int64) -> String? {
        bridge.deviceCaptureDeviceName(handle)
    }
    public static func deviceCaptureCodec(_ handle: Int64) -> Int32 {
        bridge.deviceCaptureCodec(handle)
    }
}

#if !SKIP
/// Direct binding to the C++ middleware via its C ABI.
struct DefaultPolicyBridge: NativePolicyBridge {
    func routeStrip(_ path: String) -> String? {
        var buffer = [CChar](repeating: 0, count: 4096)
        let written = path.withCString { pointer in
            omi_backend_route_strip(pointer, &buffer, buffer.count)
        }
        guard written >= 0 else { return nil }
        return String(cString: buffer)
    }

    func isCapturePath(_ path: String) -> Bool {
        path.withCString { omi_backend_is_capture_path($0) == 1 }
    }

    func requestTimeoutSeconds(method: String, path: String) -> Int {
        method.withCString { methodPointer in
            path.withCString { pathPointer in
                Int(omi_backend_request_timeout_seconds(methodPointer, pathPointer))
            }
        }
    }

    func examplePlatformSupported(method: String, path: String) -> Bool {
        method.withCString { methodPointer in
            path.withCString { pathPointer in
                omi_backend_example_platform_supported(methodPointer, pathPointer) == 1
            }
        }
    }

    func isLoopbackHostname(_ hostname: String) -> Bool {
        hostname.withCString { omi_backend_is_loopback_hostname($0) == 1 }
    }

    func isCloudHostname(_ hostname: String) -> Bool {
        hostname.withCString { omi_backend_is_cloud_hostname($0) == 1 }
    }

    func isAllowedV5Hostname(_ hostname: String) -> Bool {
        hostname.withCString { omi_backend_is_allowed_v5_hostname($0) == 1 }
    }

    func softwarePlaneIsNew(stored: String?, stampedValid: Bool) -> Bool {
        let flag: Int32 = stampedValid ? 1 : 0
        let result = stored.map { pointer in
            pointer.withCString { omi_backend_software_plane_is_new($0, flag) }
        } ?? omi_backend_software_plane_is_new(nil, flag)
        return result == 1
    }

    func recordingCapturedAtValid(_ capturedAtSeconds: Double) -> Bool {
        omi_backend_recording_captured_at_valid(capturedAtSeconds) == 1
    }

    func recordingRetryableStatus(_ status: Int) -> Bool {
        omi_backend_recording_retryable_status(Int32(status)) == 1
    }

    func recordingOwnerKeyValid(_ ownerKey: String) -> Bool {
        ownerKey.withCString { omi_backend_recording_owner_key_valid($0) == 1 }
    }

    func recordingReceiptValid(_ receipt: String) -> Bool {
        receipt.withCString { omi_backend_recording_receipt_valid($0) == 1 }
    }

    func recordingUUIDValid(_ value: String) -> Bool {
        value.withCString { omi_backend_recording_uuid_valid($0) == 1 }
    }

    func packetChecksum(_ data: [UInt8]) -> UInt32 {
        data.withUnsafeBufferPointer { buffer in
            omi_calculate_packet_checksum(buffer.baseAddress, buffer.count)
        }
    }

    func normalizePacket(_ raw: [UInt8]) -> (status: Int32, payload: [UInt8]) {
        var output = [UInt8](repeating: 0, count: max(raw.count, 4096))
        var outputLength = 0
        let status = raw.withUnsafeBufferPointer { buffer in
            omi_normalize_packet(
                buffer.baseAddress, buffer.count, &output, output.count,
                &outputLength
            )
        }
        guard status == OMI_STATUS_OK else { return (status, []) }
        return (status, Array(output[..<outputLength]))
    }

    func nativeCapabilities() -> String? {
        var buffer = [CChar](repeating: 0, count: 8192)
        let status = omi_get_native_capabilities(&buffer, buffer.count)
        guard status == OMI_STATUS_OK else { return nil }
        return String(cString: buffer)
    }

    // MARK: omi_device (portable BLE device logic)

    private static func deviceString(
        _ status: Int32, buffer: [CChar]
    ) -> String? {
        guard status >= 0 else { return nil }
        return String(cString: buffer)
    }

    func deviceDiscoveredName(
        advertisedLocalName: String?, cachedName: String?, manufacturerData: [UInt8]?
    ) -> String {
        var buffer = [CChar](repeating: 0, count: 256)
        var data = manufacturerData ?? []
        let advertisedCopy = advertisedLocalName ?? ""
        let cachedCopy = cachedName ?? ""
        let status = data.withUnsafeMutableBufferPointer { dataBuffer in
            advertisedCopy.withCString { advertised in
                cachedCopy.withCString { cached in
                    omi_device_discovered_name(
                        advertisedLocalName == nil ? nil : advertised,
                        cachedName == nil ? nil : cached, dataBuffer.baseAddress,
                        dataBuffer.count, &buffer, buffer.count)
                }
            }
        }
        guard status >= 0 else { return "" }
        return String(cString: buffer)
    }

    func deviceIsNotePinAdvertisement(_ manufacturerData: [UInt8]?) -> Bool {
        var data = manufacturerData ?? []
        return data.withUnsafeMutableBufferPointer { buffer in
            omi_device_is_note_pin_advertisement(buffer.baseAddress, buffer.count) == 1
        }
    }

    func deviceIsOmiLike(_ name: String) -> Bool {
        name.withCString { omi_device_is_omi_like($0) == 1 }
    }

    func deviceShouldPersistBatteryReading(
        previousLevel: Int32?, previousTimestampMs: Int64?, level: Int32, nowMs: Int64
    ) -> Bool {
        omi_device_should_persist_battery_reading(
            previousLevel ?? 0, previousLevel != nil ? 1 : 0,
            previousTimestampMs ?? 0, previousTimestampMs != nil ? 1 : 0,
            level, nowMs) == 1
    }

    func deviceCharacteristicText(_ bytes: [UInt8]?) -> String? {
        guard var bytes, !bytes.isEmpty else { return nil }
        var buffer = [CChar](repeating: 0, count: bytes.count + 1)
        let status = bytes.withUnsafeMutableBufferPointer { input in
            omi_device_characteristic_text(
                input.baseAddress, input.count, &buffer, buffer.count)
        }
        guard status >= 0 else { return nil }
        return String(cString: buffer)
    }

    func deviceAssemblerCreate() -> Int64 {
        guard let handle = omi_device_assembler_create() else { return 0 }
        return Int64(bitPattern: UInt64(UInt(bitPattern: handle)))
    }

    func deviceAssemblerDestroy(_ handle: Int64) {
        guard handle != 0 else { return }
        omi_device_assembler_destroy(UnsafeMutableRawPointer(bitPattern: UInt(bitPattern: Int(handle))))
    }

    func deviceAssemblerReset(_ handle: Int64) {
        guard handle != 0 else { return }
        omi_device_assembler_reset(UnsafeMutableRawPointer(bitPattern: UInt(bitPattern: Int(handle))))
    }

    func deviceAssemblerClassify(_ handle: Int64, raw: [UInt8]) -> DevicePacketDecision {
        guard handle != 0 else {
            return DevicePacketDecision(kind: 3, index: 0, payload: [], codecStatus: -1)
        }
        let machine = UnsafeMutableRawPointer(bitPattern: UInt(bitPattern: Int(handle)))
        var index: UInt16 = 0
        var payload = [UInt8](repeating: 0, count: max(raw.count, 16))
        var payloadLength = 0
        var codecStatus: Int32 = 0
        let kind = raw.withUnsafeBufferPointer { input in
            omi_device_assembler_classify(
                machine, input.baseAddress, input.count, &index, &payload,
                payload.count, &payloadLength, &codecStatus)
        }
        guard kind == 0 else {
            return DevicePacketDecision(
                kind: kind, index: index, payload: [], codecStatus: codecStatus)
        }
        return DevicePacketDecision(
            kind: kind, index: index, payload: Array(payload[..<payloadLength]),
            codecStatus: codecStatus)
    }

    func deviceCaptureCreate() -> Int64 {
        guard let handle = omi_device_capture_create() else { return 0 }
        return Int64(bitPattern: UInt64(UInt(bitPattern: handle)))
    }

    func deviceCaptureDestroy(_ handle: Int64) {
        guard handle != 0 else { return }
        omi_device_capture_destroy(UnsafeMutableRawPointer(bitPattern: UInt(bitPattern: Int(handle))))
    }

    func deviceCaptureStage(_ handle: Int64) -> Int32 {
        guard handle != 0 else { return 0 }
        return omi_device_capture_stage(
            UnsafeMutableRawPointer(bitPattern: UInt(bitPattern: Int(handle))))
    }

    func deviceCaptureIsCapturing(_ handle: Int64) -> Bool {
        guard handle != 0 else { return false }
        return omi_device_capture_is_capturing(
            UnsafeMutableRawPointer(bitPattern: UInt(bitPattern: Int(handle)))) == 1
    }

    func deviceCaptureOpen(
        _ handle: Int64, deviceId: String, deviceName: String?, codec: Int32, nowMs: Int64
    ) -> Bool {
        guard handle != 0 else { return false }
        let machine = UnsafeMutableRawPointer(bitPattern: UInt(bitPattern: Int(handle)))
        let deviceNameCopy = deviceName ?? ""
        return deviceId.withCString { deviceIdPointer in
            deviceNameCopy.withCString { deviceNamePointer in
                omi_device_capture_open(
                    machine, deviceIdPointer,
                    deviceName == nil ? nil : deviceNamePointer, codec, nowMs)
                    == OMI_STATUS_OK
            }
        }
    }

    func deviceCaptureIngest(_ handle: Int64, raw: [UInt8], receivedAtMs: Int64) -> Int64 {
        guard handle != 0 else { return -1 }
        let machine = UnsafeMutableRawPointer(bitPattern: UInt(bitPattern: Int(handle)))
        var index: UInt16 = 0
        let accepted = raw.withUnsafeBufferPointer { input in
            omi_device_capture_ingest(
                machine, input.baseAddress, input.count, receivedAtMs, &index)
        }
        guard accepted == 1 else { return -1 }
        return Int64(index)
    }

    func deviceCaptureFail(_ handle: Int64) {
        guard handle != 0 else { return }
        omi_device_capture_fail(
            UnsafeMutableRawPointer(bitPattern: UInt(bitPattern: Int(handle))))
    }

    func deviceCaptureHandoff(_ handle: Int64, nowMs: Int64) -> DeviceCaptureHandoff? {
        guard handle != 0 else { return nil }
        let machine = UnsafeMutableRawPointer(bitPattern: UInt(bitPattern: Int(handle)))
        var startedAtMs: Int64 = 0
        var endedAtMs: Int64 = 0
        var byteCount = 0
        let outcome = omi_device_capture_handoff(
            machine, nowMs, &startedAtMs, &endedAtMs, &byteCount)
        guard outcome == 1 else { return nil }
        let count = omi_device_capture_packet_count(machine)
        var packets: [DeviceCaptureHandoff.Packet] = []
        packets.reserveCapacity(count)
        for position in 0..<count {
            var index: UInt16 = 0
            var payload = [UInt8](repeating: 0, count: 1024)
            var payloadLength = 0
            var receivedAtMs: Int64 = 0
            let status = omi_device_capture_packet_at(
                machine, position, &index, &payload, payload.count,
                &payloadLength, &receivedAtMs)
            guard status == OMI_STATUS_OK else { continue }
            packets.append(
                DeviceCaptureHandoff.Packet(
                    index: index, payload: Array(payload[..<payloadLength]),
                    receivedAtMs: receivedAtMs))
        }
        return DeviceCaptureHandoff(
            startedAtMs: startedAtMs, endedAtMs: endedAtMs,
            byteCount: byteCount, packets: packets)
    }

    func deviceCaptureBatchCount(_ handle: Int64) -> Int {
        guard handle != 0 else { return 0 }
        return Int(omi_device_capture_batch_count(
            UnsafeMutableRawPointer(bitPattern: UInt(bitPattern: Int(handle)))))
    }

    func deviceCaptureBatchByteCount(_ handle: Int64) -> Int {
        guard handle != 0 else { return 0 }
        return Int(omi_device_capture_batch_byte_count(
            UnsafeMutableRawPointer(bitPattern: UInt(bitPattern: Int(handle)))))
    }

    func deviceCaptureStartedAtMs(_ handle: Int64) -> Int64 {
        guard handle != 0 else { return 0 }
        return omi_device_capture_started_at_ms(
            UnsafeMutableRawPointer(bitPattern: UInt(bitPattern: Int(handle))))
    }

    func deviceCaptureDeviceId(_ handle: Int64) -> String {
        guard handle != 0 else { return "" }
        var buffer = [CChar](repeating: 0, count: 256)
        let status = omi_device_capture_device_id(
            UnsafeMutableRawPointer(bitPattern: UInt(bitPattern: Int(handle))),
            &buffer, buffer.count)
        guard status >= 0 else { return "" }
        return String(cString: buffer)
    }

    func deviceCaptureDeviceName(_ handle: Int64) -> String? {
        guard handle != 0 else { return nil }
        var buffer = [CChar](repeating: 0, count: 256)
        let status = omi_device_capture_device_name(
            UnsafeMutableRawPointer(bitPattern: UInt(bitPattern: Int(handle))),
            &buffer, buffer.count)
        return Self.deviceString(status, buffer: buffer)
    }

    func deviceCaptureCodec(_ handle: Int64) -> Int32 {
        guard handle != 0 else { return 0 }
        return omi_device_capture_codec(
            UnsafeMutableRawPointer(bitPattern: UInt(bitPattern: Int(handle))))
    }
}
#endif
