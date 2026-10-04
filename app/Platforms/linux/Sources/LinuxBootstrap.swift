import Foundation
import OmiKit
import OmiUI

// Linux bootstrap. Injection contract (../README.md): hosts own only
// bootstrap — platform credential storage, settings backends, and service
// assembly. Every product behavior lives in OmiKit + OmiUI, and every
// absent `AppServices` dependency degrades honestly in OmiUI (no fake data).
//
// Wired here (see README.md for what is still pending):
//   - `FileCredentialStore` — file-backed `CredentialStoring` under
//     XDG_DATA_HOME (0600). Interim until a libsecret/gnome-keyring
//     implementation lands; deliberately NOT presented as a secure store.
//   - `UserDefaultsKeyValueStore` — corelibs-Foundation `UserDefaults` is
//     file-backed on Linux, so the same `KeyValueStoring` shape as macOS.
//   - The real `HTTPBackendTransport`, `ChatService`, `ReadsService`,
//     `TasksService`, `CloudService`, and `SettingsStore` from OmiKit.
// Pending (nil → honest degradation):
//   - `auth` — needs a browser + loopback portal (`BrowserAuthControlling`);
//     `Network.NWListener` does not exist on Linux, so the portal needs a
//     different loopback server (Glib main loop, SwiftNIO, or sockets).
//   - `devices` — CoreBluetooth is Apple-only; Linux BLE (BlueZ) is a
//     separate platform transport to be designed.
//   - `rewindCapture` / `rewindTimeline` / `rewindFrameImage` — the macOS
//     rewind engine (ScreenCaptureKit) has no Linux counterpart yet.

// MARK: - File-backed credential store (interim)

/// `CredentialStoring` backed by a single 0600 JSON file under
/// `$XDG_DATA_HOME/omi-v5/session.json` (`~/.local/share` by default).
///
/// This is an interim store so the host can hold a session at all. It does
/// NOT meet the repo rule that credentials live in the platform credential
/// store (root AGENTS.md): the Linux platform credential store is
/// gnome-keyring/libsecret (KWallet on KDE), and swapping this out for a
/// Secret Service implementation is tracked in README.md.
struct FileCredentialStore: CredentialStoring {
    private let url: URL
    private let queue = DispatchQueue(label: "omi.v5.linux-credentials")

    init(directory: URL? = nil) {
        let base = directory
            ?? ProcessInfo.processInfo.environment["XDG_DATA_HOME"]
                .flatMap { $0.isEmpty ? nil : URL(fileURLWithPath: $0) }
            ?? URL(fileURLWithPath: NSHomeDirectory())
                .appendingPathComponent(".local/share")
        self.url = base
            .appendingPathComponent("omi-v5", isDirectory: true)
            .appendingPathComponent("session.json")
    }

    private struct Blob: Codable {
        var idToken: String
        var refreshToken: String
        var expiresAtMs: Int64
        var uid: String?
        var firebaseApiKey: String?
    }

    func load() async -> StoredSession? {
        queue.sync {
            guard let data = try? Data(contentsOf: url),
                let blob = try? JSONDecoder().decode(Blob.self, from: data)
            else { return nil }
            return StoredSession(
                idToken: blob.idToken, refreshToken: blob.refreshToken,
                expiresAtMs: blob.expiresAtMs, uid: blob.uid,
                firebaseApiKey: blob.firebaseApiKey)
        }
    }

    func store(_ session: StoredSession) async {
        queue.sync {
            let blob = Blob(
                idToken: session.idToken, refreshToken: session.refreshToken,
                expiresAtMs: session.expiresAtMs, uid: session.uid,
                firebaseApiKey: session.firebaseApiKey)
            guard let data = try? JSONEncoder().encode(blob) else { return }
            try? FileManager.default.createDirectory(
                at: url.deletingLastPathComponent(), withIntermediateDirectories: true)
            try? data.write(to: url, options: .atomic)
            // Best effort; only meaningful when the file is newly created.
            try? FileManager.default.setAttributes(
                [.posixPermissions: 0o600], ofItemAtPath: url.path)
        }
    }

    func clear() async {
        queue.sync {
            try? FileManager.default.removeItem(at: url)
        }
    }
}

// MARK: - Defaults-backed settings storage

/// Same shape as the macOS host's store, but portable to corelibs-Foundation:
/// no CoreFoundation type sniffing (`CFBooleanGetTypeID` does not exist on
/// Linux), so value typing goes `Bool → Int → String` in that order.
struct UserDefaultsKeyValueStore: KeyValueStoring {
    func value(forKey key: String) -> PreferenceValue? {
        guard let object = UserDefaults.standard.object(forKey: key) else {
            return nil
        }
        if let bool = object as? Bool { return .bool(bool) }
        if let int = object as? Int { return .integer(int) }
        if let string = object as? String { return .string(string) }
        return nil
    }

    func set(_ value: PreferenceValue?, forKey key: String) {
        let defaults = UserDefaults.standard
        guard let value else {
            defaults.removeObject(forKey: key)
            return
        }
        switch value {
        case .bool(let bool): defaults.set(bool, forKey: key)
        case .integer(let int): defaults.set(int, forKey: key)
        case .string(let string): defaults.set(string, forKey: key)
        }
    }
}

// MARK: - Service assembly

enum OmiBootstrap {
    /// Firebase Web API key. The macOS host reads it from Info.plist; a Linux
    /// executable has no app bundle convention, so the environment carries it
    /// (`OMI_FIREBASE_API_KEY=… omi-linux-host`).
    static var firebaseApiKey: String {
        ProcessInfo.processInfo.environment["OMI_FIREBASE_API_KEY"] ?? ""
    }

    /// The real Linux service bundle (auth portal and device/rewind legs
    /// pending — see the module comment; absent legs degrade honestly).
    static func makeServices() -> AppServices {
        let credentials = FileCredentialStore()
        let transport = HTTPBackendTransport(
            credentials: credentials,
            planeSelection: HTTPBackendTransport.PlaneSelection(
                storedPlane: UserDefaults.standard.string(
                    forKey: SOFTWARE_PLANE_DEFAULTS_KEY),
                stampedValid: false))
        return AppServices(
            auth: nil,
            chat: ChatService(transport: transport),
            reads: ReadsService(transport: transport),
            tasks: TasksService(transport: transport),
            cloud: CloudService(transport: transport),
            settings: SettingsStore(storage: UserDefaultsKeyValueStore()),
            devices: nil,
            rewindCapture: nil,
            rewindTimeline: nil,
            rewindFrameImage: nil,
            transport: transport)
    }
}
