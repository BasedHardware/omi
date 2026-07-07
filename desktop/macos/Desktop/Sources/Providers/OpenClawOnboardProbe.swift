import Foundation

/// Detects whether OpenClaw has been **onboarded** — i.e. `openclaw onboard`
/// has generated a usable config (a Gateway + a default model runtime).
///
/// This is distinct from "installed": the app's install command runs
/// `... install.sh | bash -s -- --no-onboard`, which drops the `openclaw`
/// binary but writes no `~/.openclaw/openclaw.json`. Without onboarding the
/// Gateway daemon and model auth are absent, so `openclaw acp` can't actually
/// run an agent. Treating that state as "available" is what left fresh users
/// with a silently non-working OpenClaw.
///
/// File-based (no process spawn), mirroring `HermesAuthProbe`.
enum OpenClawOnboardProbe {
    static func openClawHome(
        environment: [String: String] = ProcessInfo.processInfo.environment,
        homeDirectory: String = NSHomeDirectory()
    ) -> String {
        let override = environment["OPENCLAW_STATE_DIR"]?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        if !override.isEmpty { return override }
        return (homeDirectory as NSString).appendingPathComponent(".openclaw")
    }

    static func configPath(
        environment: [String: String] = ProcessInfo.processInfo.environment,
        homeDirectory: String = NSHomeDirectory()
    ) -> String {
        let override = environment["OPENCLAW_CONFIG_PATH"]?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        if !override.isEmpty { return override }
        let home = openClawHome(environment: environment, homeDirectory: homeDirectory)
        return (home as NSString).appendingPathComponent("openclaw.json")
    }

    /// True when the config exists and describes a usable setup: a Gateway
    /// (port) plus a configured default model. Erring toward "not onboarded"
    /// is deliberate — a false negative just surfaces the connect prompt (which
    /// re-runs a safe, idempotent onboard), while a false positive would let a
    /// broken install look ready and fail opaquely at agent-run time.
    static func isOnboarded(
        environment: [String: String] = ProcessInfo.processInfo.environment,
        fileManager: FileManager = .default,
        homeDirectory: String = NSHomeDirectory()
    ) -> Bool {
        let path = configPath(environment: environment, homeDirectory: homeDirectory)
        guard fileManager.fileExists(atPath: path),
              let data = fileManager.contents(atPath: path),
              let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any]
        else { return false }
        return hasGateway(json) && hasDefaultModel(json)
    }

    private static func hasGateway(_ json: [String: Any]) -> Bool {
        guard let gateway = json["gateway"] as? [String: Any] else { return false }
        // A port (Int or numeric String) marks a configured Gateway.
        if let port = gateway["port"] as? Int, port > 0 { return true }
        if let portString = gateway["port"] as? String, let port = Int(portString), port > 0 { return true }
        return false
    }

    private static func hasDefaultModel(_ json: [String: Any]) -> Bool {
        guard let agents = json["agents"] as? [String: Any],
              let defaults = agents["defaults"] as? [String: Any],
              let model = defaults["model"] as? [String: Any],
              let primary = model["primary"] as? String
        else { return false }
        return !primary.trimmingCharacters(in: .whitespaces).isEmpty
    }
}
