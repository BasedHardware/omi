import AppKit
import Foundation
import Network
import OmiKit
import OmiUI

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
    private var listener: NWListener?
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
        if listener != nil { return boundPort != 0 }
        do {
            let parameters = NWParameters.tcp
            parameters.allowLocalEndpointReuse = true
            let listener = try NWListener(using: parameters, on: .any)
            listener.newConnectionHandler = { [weak self] connection in
                self?.accept(connection)
            }
            let bound = DispatchSemaphore(value: 0)
            listener.stateUpdateHandler = { [weak self] state in
                switch state {
                case .ready:
                    self?.boundPort = listener.port?.rawValue ?? 0
                    bound.signal()
                case .failed:
                    bound.signal()
                default: break
                }
            }
            listener.start(queue: queue)
            self.listener = listener
            _ = bound.wait(timeout: .now() + 5)
            return boundPort != 0
        } catch {
            return false
        }
    }

    func presentAuthorizeURL(_ url: String, state: String) async -> String? {
        // One outstanding browser leg at a time: a new request resolves the
        // previous wait as cancelled (matches OmiAuthSession attempt
        // fencing).
        pending?.resume(returning: nil)
        expectedState = state
        receivedQuery = nil
        guard let authorizeURL = URL(string: url) else { return nil }
        NSWorkspace.shared.open(authorizeURL)
        let callbackURL: String? = await withCheckedContinuation {
            continuation in
            queue.async {
                // A fast redirect may already have landed while the browser
                // opened; otherwise the connection handler stores us.
                if let query = self.receivedQuery,
                    self.matchesArmed(state: state)
                {
                    self.receivedQuery = nil
                    continuation.resume(
                        returning: self.makeCallbackURL(query: query))
                } else {
                    self.pending = continuation
                }
            }
        }
        expectedState = nil
        return callbackURL
    }

    private func matchesArmed(state: String) -> Bool {
        expectedState == state
    }

    private func makeCallbackURL(query: String) -> String {
        "http://127.0.0.1:\(boundPort)/callback?\(query)"
    }

    private func accept(_ connection: NWConnection) {
        connection.start(queue: queue)
        connection.receive(minimumIncompleteLength: 1, maximumLength: 16 * 1024) {
            [weak self] data, _, _, error in
            guard let self, error == nil, let data,
                let request = String(data: data, encoding: String.Encoding.utf8)
            else {
                connection.cancel()
                return
            }
            // First line: "GET /callback?code=…&state=… HTTP/1.1"
            let firstLine = request.split(
                separator: "\r\n", maxSplits: 1, omittingEmptySubsequences: true
            ).first.map(String.init) ?? request
            let parts = firstLine.split(separator: " ")
            guard parts.count >= 2, parts[1].hasPrefix("/callback?") else {
                self.respond(
                    connection, status: "404 Not Found",
                    body: "<html><body>Not found</body></html>")
                return
            }
            let query = String(parts[1].dropFirst("/callback?".count))
            let state = URLComponents(string: "?\(query)")?
                .queryItems?.first { $0.name == "state" }?.value
            self.queue.async {
                if let state, state == self.expectedState {
                    self.receivedQuery = query
                    self.resolvePending()
                }
            }
            self.respond(
                connection, status: "200 OK",
                body:
                    "<html><body style='font-family:-apple-system,sans-serif;background:#141414;color:#f4f4f4;display:flex;align-items:center;justify-content:center;height:100vh;margin:0'><p>Signing you in — return to Omi.</p></body></html>"
            )
        }
    }

    private func resolvePending() {
        guard let continuation = pending, let query = receivedQuery else {
            return
        }
        pending = nil
        receivedQuery = nil
        continuation.resume(returning: makeCallbackURL(query: query))
    }

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
            AppStore(services: DemoServices.makeServices())
        } else {
            AppStore(services: makeServices())
        }
    }

    /// The real macOS service bundle.
    static func makeServices() -> AppServices {
        let credentials = KeychainCredentialStore()
        let portal = LoopbackAuthPortal.shared
        portal.start()
        let firebaseApiKey =
            Bundle.main.object(forInfoDictionaryKey: "OMIFirebaseAPIKey")
            as? String ?? ""
        let auth = OmiAuthSession(
            config: AuthSessionConfig(
                firebaseApiKey: firebaseApiKey,
                legacyRedirectURI: portal.redirectURI),
            credentials: credentials,
            browserAuth: portal)
        let transport = HTTPBackendTransport(
            credentials: credentials,
            planeSelection: HTTPBackendTransport.PlaneSelection(
                storedPlane: UserDefaults.standard.string(
                    forKey: SOFTWARE_PLANE_DEFAULTS_KEY),
                stampedValid: false))
        return AppServices(
            auth: auth,
            chat: ChatService(transport: transport),
            reads: ReadsService(transport: transport),
            tasks: TasksService(transport: transport),
            cloud: CloudService(transport: transport),
            settings: SettingsStore(storage: UserDefaultsKeyValueStore()),
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
