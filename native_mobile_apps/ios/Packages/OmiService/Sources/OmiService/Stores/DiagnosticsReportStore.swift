import Foundation
import Observation
import OmiNetwork

/// My Devices › Diagnostics › Share / Send to support (Flutter `_exportDiagnostics`,
/// `_sendToSupport`): the bundle shared as a JSON file, or uploaded for a support ticket.
@MainActor
@Observable
public final class DiagnosticsReportStore {
    public enum Phase: Equatable, Sendable {
        case idle
        case sending
        case sent(ticket: String)
        case failed
    }

    public private(set) var phase: Phase = .idle

    private let api: any APIClientProtocol
    private let devices: DeviceStore
    private let environment: DeviceDiagnosticsLog.Environment

    public init(api: any APIClientProtocol, devices: DeviceStore, environment: DeviceDiagnosticsLog.Environment = .current) {
        self.api = api
        self.devices = devices
        self.environment = environment
    }

    /// The bundle as shown before sending, and as shared.
    public func bundle() -> Data {
        devices.diagnostics.bundle(
            device: devices.paired, battery: devices.connection == .connected ? devices.battery : nil,
            charging: devices.isCharging, environment: environment
        )
    }

    public func send() async {
        guard phase != .sending else { return }
        phase = .sending
        do {
            phase = try await .sent(ticket: api.uploadDeviceDiagnostics(bundle()))
        } catch {
            phase = .failed
        }
    }

    public func dismiss() {
        if phase != .sending { phase = .idle }
    }
}

public extension DeviceDiagnosticsLog.Environment {
    /// This app and phone (`CFBundleShortVersionString`, the hardware model, e.g. `iPhone17,1`).
    static var current: Self {
        let info = Bundle.main.infoDictionary ?? [:]
        var system = utsname()
        uname(&system)
        let machine = withUnsafeBytes(of: system.machine) { bytes in
            String(bytes: bytes.prefix { $0 != 0 }, encoding: .utf8) ?? ""
        }
        let os = ProcessInfo.processInfo.operatingSystemVersion
        return Self(
            appVersion: info["CFBundleShortVersionString"] as? String ?? "",
            appBuild: info["CFBundleVersion"] as? String ?? "",
            osVersion: "\(os.majorVersion).\(os.minorVersion).\(os.patchVersion)",
            phoneModel: machine
        )
    }
}
