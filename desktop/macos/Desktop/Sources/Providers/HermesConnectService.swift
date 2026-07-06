import AppKit
import Foundation

/// Fast, file-based detection of whether Hermes has any usable inference
/// credential. Hermes stores OAuth state and its credential pool in
/// `<hermes-home>/auth.json` and provider API keys in `<hermes-home>/.env`.
/// Erring toward "has credentials" is deliberate: a false positive just
/// preserves today's behavior (the runtime tries and reports its own error),
/// while a false negative would hijack a working setup into the connect flow.
enum HermesAuthProbe {
    static func hermesHome(
        environment: [String: String] = ProcessInfo.processInfo.environment,
        homeDirectory: String = NSHomeDirectory()
    ) -> String {
        let override = environment["HERMES_HOME"]?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        if !override.isEmpty { return override }
        return (homeDirectory as NSString).appendingPathComponent(".hermes")
    }

    /// True when Hermes has at least one credential signal: a Nous OAuth
    /// refresh token, any provider state or pool entry in auth.json, an API
    /// key in `<hermes-home>/.env`, or a known provider key in the process
    /// environment.
    static func hasAnyInferenceCredential(
        environment: [String: String] = ProcessInfo.processInfo.environment,
        fileManager: FileManager = .default,
        homeDirectory: String = NSHomeDirectory()
    ) -> Bool {
        let home = hermesHome(environment: environment, homeDirectory: homeDirectory)
        if authStoreHasCredentials(atPath: (home as NSString).appendingPathComponent("auth.json"), fileManager: fileManager) {
            return true
        }
        if envFileHasAPIKey(atPath: (home as NSString).appendingPathComponent(".env"), fileManager: fileManager) {
            return true
        }
        return environmentHasKnownProviderKey(environment)
    }

    /// True when the Nous provider specifically is signed in (refresh token
    /// present in auth.json). Used to confirm success after the connect flow.
    static func isNousAuthenticated(
        environment: [String: String] = ProcessInfo.processInfo.environment,
        fileManager: FileManager = .default,
        homeDirectory: String = NSHomeDirectory()
    ) -> Bool {
        let home = hermesHome(environment: environment, homeDirectory: homeDirectory)
        let path = (home as NSString).appendingPathComponent("auth.json")
        guard let store = readJSONObject(atPath: path, fileManager: fileManager),
              let providers = store["providers"] as? [String: Any],
              let nous = providers["nous"] as? [String: Any]
        else { return false }
        return hasNonEmptyString(nous, key: "refresh_token")
    }

    private static func authStoreHasCredentials(atPath path: String, fileManager: FileManager) -> Bool {
        guard let store = readJSONObject(atPath: path, fileManager: fileManager) else { return false }

        if let providers = store["providers"] as? [String: Any] {
            for value in providers.values {
                guard let state = value as? [String: Any] else { continue }
                if hasNonEmptyString(state, key: "refresh_token") || hasNonEmptyString(state, key: "access_token") {
                    return true
                }
            }
        }

        if let pool = store["credential_pool"] as? [String: Any] {
            for value in pool.values {
                if let entries = value as? [Any], !entries.isEmpty {
                    return true
                }
            }
        }

        return false
    }

    private static func envFileHasAPIKey(atPath path: String, fileManager: FileManager) -> Bool {
        guard fileManager.fileExists(atPath: path),
              let data = fileManager.contents(atPath: path),
              let content = String(data: data, encoding: .utf8)
        else { return false }

        for line in content.split(whereSeparator: \.isNewline) {
            let trimmed = line.trimmingCharacters(in: .whitespaces)
            guard !trimmed.hasPrefix("#"), let equals = trimmed.firstIndex(of: "=") else { continue }
            let name = String(trimmed[..<equals])
            let value = String(trimmed[trimmed.index(after: equals)...]).trimmingCharacters(in: .whitespaces)
            guard !value.isEmpty else { continue }
            if name.hasSuffix("_API_KEY") || name.hasSuffix("_TOKEN") || name == "HF_TOKEN" {
                return true
            }
        }
        return false
    }

    private static func environmentHasKnownProviderKey(_ environment: [String: String]) -> Bool {
        let knownKeys = [
            "OPENROUTER_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY", "ANTHROPIC_TOKEN",
            "GOOGLE_API_KEY", "GEMINI_API_KEY", "DEEPSEEK_API_KEY", "XAI_API_KEY",
            "NOUS_API_KEY", "NVIDIA_API_KEY", "GLM_API_KEY", "ZAI_API_KEY", "KIMI_API_KEY",
            "MINIMAX_API_KEY", "DASHSCOPE_API_KEY", "HF_TOKEN",
        ]
        return knownKeys.contains { !(environment[$0] ?? "").trimmingCharacters(in: .whitespacesAndNewlines).isEmpty }
    }

    private static func readJSONObject(atPath path: String, fileManager: FileManager) -> [String: Any]? {
        guard fileManager.fileExists(atPath: path),
              let data = fileManager.contents(atPath: path),
              let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any]
        else { return nil }
        return json
    }

    private static func hasNonEmptyString(_ dict: [String: Any], key: String) -> Bool {
        guard let value = dict[key] as? String else { return false }
        return !value.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
    }
}

/// Parses the stdout of `hermes auth add nous --type oauth --no-browser`,
/// which prints (RFC 8628 device-code flow):
///
///     To continue:
///       1. Open: https://portal.nousresearch.com/activate?user_code=XXXX
///       2. If prompted, enter code: XXXX
///     Waiting for approval (polling every 5s)...
///
/// Kept as a standalone type so it is unit-testable without a process.
struct HermesDeviceCodeOutputParser {
    private(set) var verificationURL: URL?
    private(set) var userCode: String?

    mutating func consume(line rawLine: String) {
        let line = rawLine.trimmingCharacters(in: .whitespaces)
        if verificationURL == nil, let range = line.range(of: "Open: ") {
            let candidate = String(line[range.upperBound...]).trimmingCharacters(in: .whitespaces)
            if let url = URL(string: candidate), let scheme = url.scheme, scheme.hasPrefix("http") {
                verificationURL = url
            }
        }
        if userCode == nil, let range = line.range(of: "enter code: ") {
            let code = String(line[range.upperBound...]).trimmingCharacters(in: .whitespaces)
            if !code.isEmpty {
                userCode = code
            }
        }
    }
}

/// Runs the Hermes → Nous Portal sign-in from inside the app.
///
/// Hermes has no non-interactive API-key path for Nous (OAuth device-code
/// only), so this wraps the CLI's own flow: spawn
/// `hermes auth add nous --type oauth --no-browser`, parse the verification
/// URL and user code from stdout, open the URL in the default browser, and
/// wait — the CLI polls the token endpoint itself and exits 0 once the user
/// approves in the browser (writing tokens to `~/.hermes/auth.json`).
@MainActor
final class HermesConnectService: ObservableObject {
    enum Phase: Equatable {
        case idle
        case starting
        case waitingForApproval(verificationURL: URL, userCode: String?)
        case connected
        case failed(message: String)

        var isBusy: Bool {
            switch self {
            case .starting, .waitingForApproval: return true
            case .idle, .connected, .failed: return false
            }
        }

        var automationValue: String {
            switch self {
            case .idle: return "idle"
            case .starting: return "starting"
            case .waitingForApproval: return "waitingForApproval"
            case .connected: return "connected"
            case .failed: return "failed"
            }
        }
    }

    static let shared = HermesConnectService()

    @Published private(set) var phase: Phase = .idle

    /// Device codes expire server-side (typically 15 minutes); this is a
    /// safety net so an orphaned CLI can't wait forever.
    private static let approvalTimeout: TimeInterval = 20 * 60

    private var process: Process?
    private var timeoutTask: Task<Void, Never>?
    private let openURL: (URL) -> Void

    init(openURL: @escaping (URL) -> Void = { NSWorkspace.shared.open($0) }) {
        self.openURL = openURL
    }

    var isNousAuthenticated: Bool {
        HermesAuthProbe.isNousAuthenticated()
    }

    func connect() {
        guard !phase.isBusy else { return }

        // .needsAuthentication is the expected state here; only a genuinely
        // absent executable should stop the flow.
        guard let executable = hermesExecutablePath() else {
            phase = .failed(message: "Hermes is not installed. Install it first, then retry.")
            return
        }

        phase = .starting
        log("HermesConnect: starting device-code flow via \(executable)")

        let process = Process()
        let stdout = Pipe()
        process.executableURL = URL(fileURLWithPath: executable)
        process.arguments = ["auth", "add", "nous", "--type", "oauth", "--no-browser"]
        // Null stdin: if a shared credential store exists the CLI asks
        // "Import these credentials? [Y/n]" — EOF makes it default to yes.
        process.standardInput = FileHandle.nullDevice
        process.standardOutput = stdout
        process.standardError = stdout
        // Hermes is a Python CLI; without a tty its prints are block-buffered
        // and the verification URL would only arrive at process exit.
        var environment = ProcessInfo.processInfo.environment
        environment["PYTHONUNBUFFERED"] = "1"
        process.environment = environment

        var lineBuffer = ""
        var transcript = ""
        var parser = HermesDeviceCodeOutputParser()
        stdout.fileHandleForReading.readabilityHandler = { [weak self] handle in
            let data = handle.availableData
            guard !data.isEmpty, let chunk = String(data: data, encoding: .utf8) else { return }
            Task { @MainActor [weak self] in
                guard let self else { return }
                transcript += chunk
                lineBuffer += chunk
                while let newline = lineBuffer.firstIndex(of: "\n") {
                    let line = String(lineBuffer[..<newline])
                    lineBuffer = String(lineBuffer[lineBuffer.index(after: newline)...])
                    self.handleOutput(line: line, parser: &parser)
                }
            }
        }

        process.terminationHandler = { [weak self] finished in
            stdout.fileHandleForReading.readabilityHandler = nil
            let status = finished.terminationStatus
            Task { @MainActor [weak self] in
                self?.handleExit(status: status, transcript: transcript)
            }
        }

        do {
            try process.run()
        } catch {
            stdout.fileHandleForReading.readabilityHandler = nil
            phase = .failed(message: "Couldn't launch hermes: \(error.localizedDescription)")
            return
        }

        self.process = process
        timeoutTask = Task { [weak self] in
            try? await Task.sleep(nanoseconds: UInt64(Self.approvalTimeout * 1_000_000_000))
            guard let self, !Task.isCancelled, self.phase.isBusy else { return }
            log("HermesConnect: approval timed out; terminating CLI")
            self.process?.terminate()
        }
    }

    func cancel() {
        guard phase.isBusy else { return }
        log("HermesConnect: cancelled by user")
        timeoutTask?.cancel()
        timeoutTask = nil
        process?.terminate()
        process = nil
        phase = .idle
    }

    /// Re-check auth on demand (e.g. when the settings card appears).
    func refreshConnectionState() {
        guard !phase.isBusy else { return }
        if case .failed = phase { return }
        let authenticated = isNousAuthenticated
        // Migrate already-connected installs onto the free model too — the paid
        // default only surfaces at first inference, long after sign-in.
        if authenticated {
            HermesModelProvisioner.ensureFreeDefaultModel()
        }
        phase = authenticated ? .connected : .idle
    }

    private func handleOutput(line: String, parser: inout HermesDeviceCodeOutputParser) {
        let hadURL = parser.verificationURL != nil
        parser.consume(line: line)

        guard let url = parser.verificationURL else { return }
        if !hadURL {
            log("HermesConnect: opening verification URL \(url.absoluteString)")
            openURL(url)
        }
        if phase.isBusy {
            phase = .waitingForApproval(verificationURL: url, userCode: parser.userCode)
        }
    }

    private func handleExit(status: Int32, transcript: String) {
        timeoutTask?.cancel()
        timeoutTask = nil
        process = nil
        guard phase.isBusy else { return }

        if status == 0, isNousAuthenticated {
            log("HermesConnect: connected (CLI exit 0, nous refresh token present)")
            // Pin the default to a free model so the very first inference after
            // sign-in doesn't 404 on the paid-model credit wall.
            HermesModelProvisioner.ensureFreeDefaultModel()
            phase = .connected
            return
        }

        let detail = Self.failureDetail(fromTranscript: transcript)
        log("HermesConnect: failed (exit \(status)) \(detail)")
        if status == 0 {
            phase = .failed(message: "Sign-in finished but no Nous credentials were saved. \(detail)")
        } else {
            phase = .failed(message: detail.isEmpty ? "Hermes sign-in failed (exit \(status))." : detail)
        }
    }

    nonisolated static func failureDetail(fromTranscript transcript: String) -> String {
        let lines = transcript
            .split(whereSeparator: \.isNewline)
            .map { $0.trimmingCharacters(in: .whitespaces) }
            .filter { !$0.isEmpty && !$0.hasPrefix("Waiting for approval") }
        let tail = lines.suffix(3).joined(separator: " ")
        guard tail.count > 300 else { return tail }
        return String(tail.suffix(300))
    }

    private func hermesExecutablePath() -> String? {
        LocalAgentProviderDetector.executablePath(for: .hermes)
    }

    private func log(_ message: String) {
        NSLog("%@", message)
    }
}
