import Foundation

/// Durable evidence for a connection whose process may die without a callback.
final class OmiDeviceHealthStore {
    private let defaults: UserDefaults
    private var live = Set<String>()
    init(defaults: UserDefaults = .standard) { self.defaults = defaults }
    var enabled: Bool { defaults.bool(forKey: "ble_health_enabled") }
    var epoch: Int64 { Int64(defaults.integer(forKey: "ble_health_epoch")) }
    static var build: String {
        let info = Bundle.main.infoDictionary ?? [:]
        return "\(info["CFBundleShortVersionString"] as? String ?? "unknown")+\(info["CFBundleVersion"] as? String ?? "unknown")"
    }
    func setPolicy(enabled: Bool, epoch: Int64, retire: Bool) {
        defaults.set(false, forKey: "ble_health_enabled")
        if retire || self.epoch != epoch {
            for key in defaults.dictionaryRepresentation().keys where key.hasPrefix("ble_") || key.hasPrefix("battery_history_") {
                defaults.removeObject(forKey: key)
            }
            live.removeAll()
        }
        try? SafeDefaults.store(.int64(epoch), forKey: "ble_health_epoch", in: defaults)
        try? SafeDefaults.store(.bool(enabled), forKey: "ble_health_enabled", in: defaults)
        defaults.synchronize()
    }
    // The reconnect event key is separate from the audio outage: the latter can
    // predate this disconnect after a process restart and owns audio accounting.
    func recordDisconnect(_ device: String, at: Int64) {
        guard enabled else { return }
        try? SafeDefaults.store(.int64(at), forKey: "ble_reconnect_event_\(device)", in: defaults)
    }
    func reconnectEvent(_ device: String) -> Int64? {
        guard enabled else { return nil }
        return defaults.object(forKey: "ble_reconnect_event_\(device)") as? Int64
    }
    func connectedBefore(_ device: String) -> Bool {
        guard enabled else { return false }
        return defaults.bool(forKey: "ble_ever_connected_\(device)") ||
            defaults.object(forKey: "ble_session_\(device)") != nil ||
            defaults.object(forKey: "ble_audio_outage_\(device)") != nil ||
            defaults.integer(forKey: "ble_diagnostics_reconnect_count_\(device)") > 0
    }
    func recordConnected(_ device: String) {
        guard enabled else { return }
        try? SafeDefaults.store(.bool(true), forKey: "ble_ever_connected_\(device)", in: defaults)
        defaults.removeObject(forKey: "ble_reconnect_event_\(device)")
    }
    func openSince(_ device: String) -> Int64? {
        guard enabled else { return nil }
        if defaults.object(forKey: "ble_audio_outage_epoch_\(device)") as? Int64 == epoch,
           let start = defaults.object(forKey: "ble_audio_outage_\(device)") as? Int64 { return start }
        guard !live.contains(device), let session = defaults.dictionary(forKey: "ble_session_\(device)"),
              session["identity_epoch"] as? Int64 == epoch else { return nil }
        return session["started_at"] as? Int64
    }
    func start(_ device: String, at: Int64) {
        guard enabled, !live.contains(device) else { return }
        if let old = openSince(device) {
            try? SafeDefaults.store(.int64(epoch), forKey: "ble_audio_outage_epoch_\(device)", in: defaults)
            try? SafeDefaults.store(.int64(old), forKey: "ble_audio_outage_\(device)", in: defaults)
        }
        try? SafeDefaults.store(.dictionary(["device": .string(device), "started_at": .int64(at), "app_build": .string(Self.build), "identity_epoch": .int64(epoch)]), forKey: "ble_session_\(device)", in: defaults)
        defaults.synchronize()
        live.insert(device)
    }
    func end(_ device: String, at: Int64) {
        guard enabled else { return }
        let start = openSince(device) ?? at
        try? SafeDefaults.store(.int64(epoch), forKey: "ble_audio_outage_epoch_\(device)", in: defaults)
        try? SafeDefaults.store(.int64(start), forKey: "ble_audio_outage_\(device)", in: defaults)
        defaults.removeObject(forKey: "ble_session_\(device)")
        defaults.synchronize()
        live.remove(device)
    }
}
