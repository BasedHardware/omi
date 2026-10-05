import AppKit
import AVFoundation
import CoreBluetooth
import Foundation
import Network
import OmiKit
import OmiUI
import UserNotifications

// macOS bootstrap: real service assembly (keychain credentials, browser +
// loopback auth, authenticated HTTP transport, UserDefaults-backed settings,
// CoreBluetooth device transport, ScreenCaptureKit rewind engine) and the
// labeled `-omiDemoData` bundle used for screenshots and UI exploration.
// Injection contract (../README.md): hosts own only bootstrap — every
// product behavior lives in OmiKit + OmiUI.

// MARK: - Defaults-backed settings storage

/// `UserDefaults` backend for `SettingsStore`. The store round-trips only
/// the whitelisted desktop preference keys, so value typing follows each
/// stored object's actual type (CFBoolean → bool, integer, string).
/// macOS permission prompts, matching `OmiDesktopCommandsModule.mm`.
/// A denied permission opens the System Settings pane the RN host opens;
/// that is not a grant.
enum MacPermissionBroker {
    static func status() async -> [PermissionKind: PermissionState] {
        let screen: PermissionState = CGPreflightScreenCaptureAccess() ? .granted : .denied
        let microphone = AVCaptureDevice.authorizationStatus(for: .audio)
        let mic: PermissionState
        switch microphone {
        case .authorized: mic = .granted
        case .denied, .restricted: mic = .denied
        default: mic = .unknown
        }
        let notifications = await notificationState()
        return [
            .screen: screen,
            .microphone: mic,
            .notifications: notifications,
            .bluetooth: bluetoothState(),
        ]
    }

    static func request(_ kind: PermissionKind) async -> PermissionState {
        switch kind {
        case .screen:
            // The system dialog is the only ask. Do not open Settings.
            let granted = await MainActor.run {
                CGPreflightScreenCaptureAccess() || CGRequestScreenCaptureAccess()
            }
            return granted ? .granted : .denied
        case .microphone:
            let granted = await AVCaptureDevice.requestAccess(for: .audio)
            return granted ? .granted : .denied
        case .notifications:
            let granted = await requestNotifications()
            return granted ? .granted : .denied
        case .bluetooth:
            return await requestBluetooth()
        }
    }

    /// Creating a central manager is the macOS Bluetooth prompt. The state
    /// update is the answer; we do not open Settings.
    private static func requestBluetooth() async -> PermissionState {
        await withCheckedContinuation { continuation in
            let box = BluetoothAsk()
            box.start { state in
                continuation.resume(returning: state)
            }
        }
    }

    private static func bluetoothState() -> PermissionState {
        switch CBCentralManager.authorization {
        case .allowedAlways: return .granted
        case .denied, .restricted: return .denied
        default: return .unknown
        }
    }

    /// The allow/deny prompt. A previous denial makes this API return no
    /// without a dialog, which is why the button snapped back to Allow.
    /// Clear that decision, then ask again. Do not open Settings.
    private static func requestNotifications() async -> Bool {
        let bundle = Bundle.main.bundleIdentifier ?? "org.reactjs.native.omi-v5-macos"
        let reset = Process()
        reset.executableURL = URL(fileURLWithPath: "/usr/bin/tccutil")
        reset.arguments = ["reset", "Notifications", bundle]
        try? reset.run()
        reset.waitUntilExit()
        return await withCheckedContinuation { continuation in
            UNUserNotificationCenter.current().requestAuthorization(
                options: [.alert, .sound, .badge]
            ) { granted, _ in
                continuation.resume(returning: granted)
            }
        }
    }

    private static func notificationState() async -> PermissionState {
        let settings = await UNUserNotificationCenter.current().notificationSettings()
        switch settings.authorizationStatus {
        case .authorized, .provisional, .ephemeral: return .granted
        case .denied: return .denied
        default: return .unknown
        }
    }
}

/// Holds the central manager until macOS answers the Bluetooth prompt.
final class BluetoothAsk: NSObject, CBCentralManagerDelegate {
    private var manager: CBCentralManager?
    private var finish: ((PermissionState) -> Void)?

    func start(_ finish: @escaping (PermissionState) -> Void) {
        self.finish = finish
        manager = CBCentralManager(delegate: self, queue: nil)
    }

    func centralManagerDidUpdateState(_ central: CBCentralManager) {
        let state: PermissionState
        switch central.state {
        case .unauthorized: state = .denied
        case .poweredOn, .poweredOff, .resetting: state = .granted
        default: return
        }
        let done = finish
        finish = nil
        manager = nil
        done?(state)
    }
}

/// Settings store that asks macOS. `SettingsStore` returns `.unknown`
/// for every permission, which is why Allow did nothing.
final class MacSettingsStore: SettingsStoring, @unchecked Sendable {
    private let preferences: SettingsStore

    init(storage: KeyValueStoring) {
        preferences = SettingsStore(storage: storage)
    }

    func loadPreferences() async -> DesktopPreferences {
        await preferences.loadPreferences()
    }

    func setPreference(_ key: String, _ value: PreferenceValue) async -> DesktopPreferences {
        await preferences.setPreference(key, value)
    }

    func permissionStatus() async -> [PermissionKind: PermissionState] {
        await MacPermissionBroker.status()
    }

    func requestPermission(_ kind: PermissionKind) async -> PermissionState {
        await MacPermissionBroker.request(kind)
    }
}

struct UserDefaultsKeyValueStore: KeyValueStoring {
    func value(forKey key: String) -> PreferenceValue? {
        guard let object = UserDefaults.standard.object(forKey: key) else {
            return nil
        }
        if let number = object as? NSNumber {
            if CFGetTypeID(number) == CFBooleanGetTypeID() {
                return .bool(number.boolValue)
            }
            return .integer(number.intValue)
        }
        if let string = object as? String {
            return .string(string)
        }
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

// MARK: - Browser + loopback auth leg

/// The browser leg of the legacy OAuth PKCE flow: one ephemeral loopback
/// port bound at launch, the authorize URL opened in the default browser,
/// and the `/callback?code=…&state=…` redirect handed back to
/// `OmiAuthSession.signInWithLegacyPKCE`. Mirrors the RN macOS
/// `OmiAuthModule` loopback flow.
final class LoopbackAuthPortal: BrowserAuthControlling, @unchecked Sendable {
    static let shared = LoopbackAuthPortal()

    private let queue = DispatchQueue(label: "omi.v5.loopback-auth")
    private var posixSource: DispatchSourceRead?
    private var boundPort: UInt16 = 0
    private var pending: CheckedContinuation<String?, Never>?
    private var expectedState: String?
    private var receivedQuery: String?

    /// The redirect URI the session config must carry; only usable after
    /// `start()` bound the listener.
    var redirectURI: String { "http://127.0.0.1:\(boundPort)/callback" }

    private init() {}

    /// Binds the loopback listener (idempotent). Returns whether a port
    /// was bound.
    @discardableResult
    func start() -> Bool {
        if posixSource != nil { return boundPort != 0 }
        // The redirect is http://127.0.0.1. Network.framework's `.any`
        // binds IPv6 only here, and the browser's IPv4 bounce never
        // arrives. A POSIX listener on 127.0.0.1 is the socket the RN host uses.
        let fileDescriptor = socket(AF_INET, SOCK_STREAM, IPPROTO_TCP)
        guard fileDescriptor >= 0 else { return false }
        var reuse: Int32 = 1
        setsockopt(
            fileDescriptor, SOL_SOCKET, SO_REUSEADDR, &reuse,
            socklen_t(MemoryLayout<Int32>.size))
        var address = sockaddr_in()
        address.sin_len = UInt8(MemoryLayout<sockaddr_in>.size)
        address.sin_family = sa_family_t(AF_INET)
        address.sin_addr.s_addr = inet_addr("127.0.0.1")
        address.sin_port = 0
        let bound = withUnsafePointer(to: &address) {
            $0.withMemoryRebound(to: sockaddr.self, capacity: 1) {
                bind(fileDescriptor, $0, socklen_t(MemoryLayout<sockaddr_in>.size))
            }
        }
        guard bound == 0, listen(fileDescriptor, 16) == 0 else {
            close(fileDescriptor)
            return false
        }
        var boundAddress = sockaddr_in()
        var length = socklen_t(MemoryLayout<sockaddr_in>.size)
        let named = withUnsafeMutablePointer(to: &boundAddress) {
            $0.withMemoryRebound(to: sockaddr.self, capacity: 1) {
                getsockname(fileDescriptor, $0, &length)
            }
        }
        guard named == 0 else {
            close(fileDescriptor)
            return false
        }
        boundPort = UInt16(bigEndian: boundAddress.sin_port)
        let source = DispatchSource.makeReadSource(
            fileDescriptor: fileDescriptor, queue: queue)
        source.setEventHandler { [weak self] in
            self?.acceptPOSIX(fileDescriptor)
        }
        source.setCancelHandler { close(fileDescriptor) }
        source.resume()
        posixSource = source
        return boundPort != 0
    }

    /// Read one HTTP request off an accepted 127.0.0.1 client and hand it
    /// to the same callback matcher the Network path used.
    private func acceptPOSIX(_ listener: Int32) {
        var peer = sockaddr_in()
        var length = socklen_t(MemoryLayout<sockaddr_in>.size)
        let client = withUnsafeMutablePointer(to: &peer) {
            $0.withMemoryRebound(to: sockaddr.self, capacity: 1) {
                Darwin.accept(listener, $0, &length)
            }
        }
        guard client >= 0 else { return }
        var accumulator = AuthHTTPRequestHeaderAccumulator()
        var buffer = [UInt8](repeating: 0, count: 4096)
        let deadline = DispatchTime.now().uptimeNanoseconds + 2_000_000_000
        while true {
            let now = DispatchTime.now().uptimeNanoseconds
            guard now < deadline else {
                writePOSIX(client, status: "408 Request Timeout", body: "Invalid callback")
                return
            }
            let remainingMilliseconds = max(1, Int((deadline - now) / 1_000_000))
            var readiness = pollfd(fd: client, events: Int16(POLLIN), revents: 0)
            let ready = poll(&readiness, 1, Int32(remainingMilliseconds))
            if ready == 0 {
                writePOSIX(client, status: "408 Request Timeout", body: "Invalid callback")
                return
            }
            if ready < 0 {
                if errno == EINTR { continue }
                close(client)
                return
            }
            let count = recv(client, &buffer, buffer.count, 0)
            if count < 0 {
                if errno == EINTR { continue }
                close(client)
                return
            }
            guard count > 0 else {
                close(client)
                return
            }
            switch accumulator.append(Data(buffer.prefix(count))) {
            case .incomplete:
                continue
            case .complete(let request):
                handlePOSIX(request, client: client)
                return
            case .invalidEncoding:
                writePOSIX(client, status: "400 Bad Request", body: "Invalid callback")
                return
            case .tooLarge:
                writePOSIX(
                    client, status: "431 Request Header Fields Too Large",
                    body: "Invalid callback")
                return
            }
        }
    }

    private func handlePOSIX(_ request: String, client: Int32) {
        let firstLine = request.split(separator: "\r\n", maxSplits: 1).first.map(String.init) ?? request
        let parts = firstLine.split(separator: " ").map(String.init)
        guard parts.count >= 2, parts[0] == "GET" else {
            writePOSIX(client, status: "400 Bad Request", body: "Invalid callback")
            return
        }
        let target = parts[1]
        guard isLoopbackAuthCallbackRequestTarget(target) else {
            writePOSIX(client, status: "404 Not Found", body: "Not found")
            return
        }
        let query = target.split(separator: "?", maxSplits: 1).dropFirst().first.map(String.init) ?? ""
        let items = URLComponents(string: "http://127.0.0.1/callback?\(query)")?.queryItems
        let state = items?.first { $0.name == "state" }?.value
        let code = items?.first { $0.name == "code" }?.value
        let oauthError = items?.first { $0.name == "error" }?.value
        guard code?.isEmpty == false || oauthError?.isEmpty == false else {
            writePOSIX(client, status: "400 Bad Request", body: "Invalid callback")
            return
        }
        // A bounce can land before the continuation is stored. Keep the
        // query; presentAuthorizeURL picks it up instead of waiting forever.
        // Keep the query whenever it can belong to this attempt. Calling
        // settle before the waiter exists clears the query and sign-in
        // hangs on "Signing in…" forever.
        let armed = expectedState != nil
        let matched = state == expectedState && armed
        if matched || !armed {
            if pending != nil {
                settle(query)
            } else {
                receivedQuery = query
            }
        }
        writePOSIX(
            client,
            status: (matched || !armed) ? "200 OK" : "400 Bad Request",
            body: (matched || !armed)
                ? Self.signedInPage
                : "This sign-in link does not match the app. Return to Omi and try again.")
    }

    private func writePOSIX(_ client: Int32, status: String, body: String) {
        let payload =
            "HTTP/1.1 \(status)\r\nContent-Type: text/html; charset=utf-8\r\nContent-Length: \(body.utf8.count)\r\nConnection: close\r\n\r\n\(body)"
        _ = payload.withCString { send(client, $0, strlen($0), 0) }
        close(client)
    }

    func presentAuthorizeURL(_ url: String, state: String) async -> String? {
        guard start(), boundPort != 0, let authorizeURL = URL(string: url) else {
            return nil
        }
        // Arm on the listener queue before the browser opens. The Google
        // bounce can land in the same turn the window opens; arming after
        // `open` drops that callback and sign-in never returns.
        await withCheckedContinuation { (armed: CheckedContinuation<Void, Never>) in
            queue.async {
                self.settle(nil)
                self.expectedState = state
                self.receivedQuery = nil
                armed.resume()
            }
        }
        NSWorkspace.shared.open(authorizeURL)
        let callbackURL: String? = await withCheckedContinuation {
            continuation in
            queue.async {
                // A callback that beat this continuation is already stored.
                if let query = self.receivedQuery {
                    self.receivedQuery = nil
                    continuation.resume(returning: self.makeCallbackURL(query: query))
                } else {
                    self.pending = continuation
                }
            }
        }
        queue.async {
            if self.expectedState == state { self.expectedState = nil }
        }
        return callbackURL
    }

    /// Resume the waiting browser leg exactly once.
    private func settle(_ query: String?) {
        let continuation = pending
        pending = nil
        receivedQuery = nil
        continuation?.resume(returning: query.map { makeCallbackURL(query: $0) })
        if query != nil {
            DispatchQueue.main.async {
                NSApp.activate(ignoringOtherApps: true)
                NSApp.windows.first { !($0 is NSPanel) }?.makeKeyAndOrderFront(nil)
            }
        }
    }

    private func matchesArmed(state: String) -> Bool {
        expectedState == state
    }

    private func makeCallbackURL(query: String) -> String {
        "http://127.0.0.1:\(boundPort)/callback?\(query)"
    }

    private func accept(_ connection: NWConnection) {
        connection.start(queue: queue)
        receiveRequest(on: connection, accumulated: Data())
    }

    /// Google's bounce can arrive as several TCP chunks, and the browser
    /// probes `/favicon.ico` on the same port. A single incomplete read used
    /// to answer "Not found" and drop the real callback.
    private func receiveRequest(on connection: NWConnection, accumulated: Data) {
        connection.receive(minimumIncompleteLength: 1, maximumLength: 16 * 1024) {
            [weak self] data, _, isComplete, error in
            guard let self else {
                connection.cancel()
                return
            }
            var buffer = accumulated
            if let data { buffer.append(data) }
            let text = String(data: buffer, encoding: String.Encoding.utf8) ?? ""
            let headerComplete = text.contains("\r\n\r\n") || text.contains("\n\n")
            if !headerComplete, error == nil, !isComplete, buffer.count < 16 * 1024 {
                self.receiveRequest(on: connection, accumulated: buffer)
                return
            }
            guard error == nil, !text.isEmpty else {
                connection.cancel()
                return
            }
            self.handleRequest(text, on: connection)
        }
    }

    private func handleRequest(_ request: String, on connection: NWConnection) {
        // First line: "GET /callback?code=…&state=… HTTP/1.1"
        let firstLine = request.split(
            separator: "\r\n", maxSplits: 1, omittingEmptySubsequences: false
        ).first.map(String.init)
            ?? request.split(separator: "\n", maxSplits: 1).first.map(String.init)
            ?? request
        let parts = firstLine.split(separator: " ").map(String.init)
        guard parts.count >= 2, parts[0] == "GET" else {
            respond(
                connection, status: "400 Bad Request",
                body: "<html><body>Invalid callback</body></html>")
            return
        }
        let target = parts[1]
        // Browser probes (favicon, well-known) must not kill the wait.
        guard isLoopbackAuthCallbackRequestTarget(target) else {
            respond(
                connection, status: "404 Not Found",
                body: "<html><body>Not found</body></html>")
            return
        }
        let query: String
        if let question = target.firstIndex(of: "?") {
            query = String(target[target.index(after: question)...])
        } else {
            query = ""
        }
        let items = URLComponents(string: "http://127.0.0.1/callback?\(query)")?.queryItems
        let state = items?.first { $0.name == "state" }?.value
        let code = items?.first { $0.name == "code" }?.value
        let oauthError = items?.first { $0.name == "error" }?.value
        // A callback without a code or an OAuth error is a probe — keep waiting.
        guard code?.isEmpty == false || oauthError?.isEmpty == false else {
            respond(
                connection, status: "400 Bad Request",
                body: "<html><body>Invalid callback</body></html>")
            return
        }
        // Compare on this queue. `accept` already runs here, so a main-thread
        // read of `expectedState` raced the arm and rejected a real callback.
        let matched = state == expectedState && expectedState != nil
        NSLog(
            "Omi auth callback matched=%d armed=%d code=%d",
            matched ? 1 : 0, expectedState == nil ? 0 : 1, (code ?? "").isEmpty ? 0 : 1)
        if matched {
            receivedQuery = query
            settle(query)
        }
        respond(
            connection, status: matched ? "200 OK" : "400 Bad Request",
            body: matched
                ? Self.signedInPage
                : "<html><body>This sign-in link does not match the app. Return to Omi and try again.</body></html>")
    }

    /// The leftover callback tab. Mirrors the RN `OmiAuthBlankCallbackHTML`
    /// confirmation so the browser never sits on "Not found".
    static let signedInPage = """
        <!doctype html><html><head><meta charset="utf-8">\
        <meta name="viewport" content="width=device-width,initial-scale=1">\
        <style>html,body{margin:0;height:100%;background:#101210;color:#f4f1ea;\
        font-family:-apple-system,system-ui,sans-serif}\
        .wrap{height:100%;display:flex;align-items:center;justify-content:center}\
        .card{text-align:center;padding:0 24px;max-width:360px}\
        h1{font-size:22px;margin:0 0 8px;font-weight:600;letter-spacing:-0.02em}\
        p{font-size:15px;margin:0;line-height:1.45;color:rgba(244,241,234,0.72)}\
        </style></head><body><div class="wrap"><div class="card">\
        <h1>Return to Omi</h1>\
        <p>Finish signing in in the app. You can close this tab.</p>\
        </div></div></body></html>
        """

    private func respond(_ connection: NWConnection, status: String, body: String) {
        let payload =
            "HTTP/1.1 \(status)\r\nContent-Type: text/html; charset=utf-8\r\nContent-Length: \(body.utf8.count)\r\nConnection: close\r\n\r\n\(body)"
        connection.send(
            content: payload.data(using: String.Encoding.utf8),
            completion: .contentProcessed { _ in connection.cancel() })
    }
}

// MARK: - Service assembly

enum OmiBootstrap {
    /// `-omiDemoData` swaps the real bundle for the labeled in-memory demo
    /// bundle (DemoServices.swift). Everything else is the real stack.
    static var demoMode: Bool {
        ProcessInfo.processInfo.arguments.contains("-omiDemoData")
    }

    /// The wired store for this launch.
    @MainActor
    static func makeStore() -> AppStore {
        if demoMode {
            AppStore(services: MacDemoServices.makeServices())
        } else {
            AppStore(services: makeServices())
        }
    }

    /// The stamped New-plane origin for the desktop handoff, per
    /// RELEASE.md: `OMI_V5_BACKEND_URL` (https only, `*.workers.dev` or the
    /// pinned origins; loopback for a dev Worker). Nil when unset or not
    /// allowlisted, so sign-in falls back to the legacy api.omi.me flow.
    static func stampedV5Origin() -> String? {
        guard
            let raw = ProcessInfo.processInfo.environment[V5_BACKEND_URL_ENV],
            let origin = parseOrigin(raw),
            isAllowedV5Hostname(origin.hostname)
        else {
            return nil
        }
        return origin.origin
    }

    /// The real macOS service bundle.
    static func makeServices() -> AppServices {
        let credentials = KeychainCredentialStore()
        let planeStore = UserDefaultsSoftwarePlaneStore()
        let origin = stampedV5Origin()
        let portal = LoopbackAuthPortal.shared
        portal.start()
        let firebaseApiKey =
            Bundle.main.object(forInfoDictionaryKey: "OMIFirebaseAPIKey")
            as? String ?? ""
        let auth = OmiAuthSession(
            config: AuthSessionConfig(
                firebaseApiKey: firebaseApiKey,
                v5BackendOrigin: origin,
                legacyRedirectURI: portal.redirectURI),
            credentials: credentials,
            browserAuth: portal, planeStore: planeStore)
        let backend = HTTPBackendTransport(
            credentials: credentials,
            planeSelection: HTTPBackendTransport.PlaneSelection(
                storedPlane: UserDefaults.standard.string(
                    forKey: SOFTWARE_PLANE_DEFAULTS_KEY),
                stampedValid: origin != nil),
            originOverride: origin,
            bearerResolver: { await auth.resolveBearerToken() }, planeStore: planeStore)
        let journalRoot = FileManager.default.urls(
            for: .applicationSupportDirectory, in: .userDomainMask)[0]
            .appendingPathComponent("Omi/RecordingJournals", isDirectory: true)
        let transport = EncryptedRecordingJournalTransport(
            backend: backend,
            ownerProvider: AppleRecordingJournalOwnerProvider(transport: backend),
            vault: AppleKeychainRecordingJournalVault(),
            files: POSIXAtomicRecordingJournalFiles(), root: journalRoot)
        return AppServices(
            auth: auth,
            chat: ChatService(transport: transport),
            reads: ReadsService(transport: transport),
            tasks: TasksService(transport: transport),
            cloud: CloudService(transport: transport),
            settings: MacSettingsStore(storage: UserDefaultsKeyValueStore()),
            devices: CoreBluetoothDeviceTransport(),
            rewindCapture: OmiRewindEngine.shared.bridge,
            rewindTimeline: RewindTimelineBridge { source, query, cursor, limit in
                try OmiRewindEngine.shared.frames(
                    source: source, query: query, cursor: cursor, limit: limit)
            },
            rewindFrameImage: { OmiRewindEngine.shared.frameJPEG(id: $0) },
            transport: transport)
    }
}
