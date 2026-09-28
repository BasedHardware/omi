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
}
#endif
