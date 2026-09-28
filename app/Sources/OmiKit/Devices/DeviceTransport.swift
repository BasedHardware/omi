import Foundation

// Platform-neutral device transport surface for the Omi wearable layer.
//
// This is the seam the UI wave consumes. Implementations live per platform
// (CoreBluetooth under `#if canImport(CoreBluetooth)` in OmiKit/Devices,
// Android BLE behind the Skip host bridge). Codec and transport-policy
// decisions are never made here: framing/normalization go through
// `Policy.normalizePacket` / `Policy.packetChecksum` (the shared C++
// middleware in `native-core/`).

/// A peripheral seen during discovery. `id` is the stable platform
/// identifier (CoreBluetooth peripheral UUID string) used for connect.
public struct DiscoveredDevice: Sendable, Hashable, Identifiable {
    public var id: String
    public var name: String
    public var rssi: Int?

    public init(id: String, name: String, rssi: Int? = nil) {
        self.id = id
        self.name = name
        self.rssi = rssi
    }
}

/// One audio notification as it arrived off the radio, before any codec
/// processing. `raw` is the full characteristic value (sequence index +
/// 0xAA 0x55 framed body). `receivedAtMs` is host receipt wall-clock time —
/// per the capture-time contract it is sampled at the BLE callback, never
/// derived from firmware RTC.
public struct DeviceAudioPacket: Sendable, Hashable {
    public var deviceId: String
    public var connectionId: String
    public var raw: [UInt8]
    public var receivedAtMs: Int64

    public init(
        deviceId: String, connectionId: String, raw: [UInt8], receivedAtMs: Int64
    ) {
        self.deviceId = deviceId
        self.connectionId = connectionId
        self.raw = raw
        self.receivedAtMs = receivedAtMs
    }
}

/// Connection lifecycle event: phase transitions carry the device
/// information snapshot once available (after Device Information service
/// reads complete during `connecting → connected`).
public struct DeviceConnectionEvent: Sendable, Hashable {
    public var deviceId: String
    public var connectionId: String
    public var phase: ConnectionPhase
    public var info: BleDeviceInfo?

    public init(
        deviceId: String, connectionId: String, phase: ConnectionPhase,
        info: BleDeviceInfo? = nil
    ) {
        self.deviceId = deviceId
        self.connectionId = connectionId
        self.phase = phase
        self.info = info
    }
}

public enum DeviceTransportFailure: Error, Sendable, Equatable {
    /// The radio is off, unauthorized, or otherwise unusable.
    case bluetoothUnavailable(BluetoothState)
    /// A scan or connect is already in flight for this transport.
    case busy
    /// The identifier does not match a known peripheral.
    case unknownDevice
    /// The link failed before readiness (GATT error / timeout).
    case connectFailed(String)
}

/// The Omi wearable device transport: discovery, connection, and audio
/// packet delivery. All streams are single-subscription streams owned by
/// the transport; UI layers should forward from them into their own state.
///
/// Implementations must:
/// - Map platform radio state onto `BluetoothState` (Models.swift).
/// - Report `ConnectionPhase.connecting` from the connect call until codec +
///   audio-notification readiness, then `connected` (per
///   docs/hardware-device-parity.md: success requires a codec plus confirmed
///   audio notifications).
/// - Deliver every audio notification verbatim in `audioPackets`; the
///   capture state machine (`CaptureSessionMachine`) owns normalization,
///   dedupe, and journal handoff.
public protocol DeviceTransport: Sendable {
    /// Radio state changes (powered on/off/unauthorized).
    var bluetoothStates: AsyncStream<BluetoothState> { get }
    /// Connection phase transitions, including the resolved device info.
    var connectionEvents: AsyncStream<DeviceConnectionEvent> { get }
    /// Raw audio notification payloads from the connected device.
    var audioPackets: AsyncStream<DeviceAudioPacket> { get }

    func currentBluetoothState() async -> BluetoothState

    /// Discovers Omi-like peripherals for up to `durationSeconds`, resolving
    /// with the discovered set.
    func startScan(durationSeconds: Int) async throws -> [DiscoveredDevice]
    func stopScan() async

    /// Connects and prepares the device. Returns on readiness
    /// (`connected` phase with device info). Throws
    /// `DeviceTransportFailure` on radio/GATT failure.
    @discardableResult
    func connect(deviceId: String) async throws -> DeviceConnectionEvent
    func disconnect(deviceId: String) async

    /// Last-known Device Information snapshot for a device, if read.
    func deviceInfo(deviceId: String) async -> BleDeviceInfo?
}

/// Pure classification helper: which discovered names are Omi-like.
/// Mirrors the upstream discoverer's `name.contains("notepin")` /
/// Omi-name matching without touching platform types.
public enum OmiDiscoveryFilter {
    /// Delegates to the shared C++ middleware (`omi_device_is_omi_like`).
    public static func isOmiLike(_ name: String) -> Bool {
        Policy.deviceIsOmiLike(name)
    }
}
