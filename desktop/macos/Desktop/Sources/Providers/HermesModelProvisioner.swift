import Foundation

/// Keeps Hermes pointed at a **free** Nous model so it works without paid
/// credits. Hermes' CLI writes `~/.hermes/config.yaml` with `model.default`
/// set to a paid model (e.g. `qwen/qwen3-235b-a22b-2507`), which 404s on a
/// zero-credit account ("requires available credits"). The app owns this
/// choice: whenever we confirm Hermes is connected (fresh device-code sign-in
/// or an existing authenticated install), we pin the default to a known free
/// model so a live run never hits the paid-credit wall.
///
/// The rewrite is line-based (no YAML dependency), idempotent, and only touches
/// `model.default`; everything else in the file is preserved verbatim.
enum HermesModelProvisioner {
    /// A Nous model priced at $0.00/1M — confirmed to answer on the free tier.
    static let freeDefaultModel = "stepfun/step-3.7-flash:free"

    static func defaultConfigPath(
        environment: [String: String] = ProcessInfo.processInfo.environment,
        homeDirectory: String = NSHomeDirectory()
    ) -> String {
        let home = HermesAuthProbe.hermesHome(environment: environment, homeDirectory: homeDirectory)
        return (home as NSString).appendingPathComponent("config.yaml")
    }

    /// Ensures `model.default` in the Hermes config is a free model. Returns
    /// true when the file was created or modified. Safe to call repeatedly.
    @discardableResult
    static func ensureFreeDefaultModel(
        configPath: String = defaultConfigPath(),
        fileManager: FileManager = .default
    ) -> Bool {
        let existing: String
        if fileManager.fileExists(atPath: configPath),
           let data = fileManager.contents(atPath: configPath),
           let text = String(data: data, encoding: .utf8) {
            existing = text
        } else {
            existing = ""
        }

        guard let updated = rewrite(existing) else { return false }

        do {
            let dir = (configPath as NSString).deletingLastPathComponent
            if !dir.isEmpty, !fileManager.fileExists(atPath: dir) {
                try fileManager.createDirectory(atPath: dir, withIntermediateDirectories: true)
            }
            try updated.write(toFile: configPath, atomically: true, encoding: .utf8)
            NSLog("HermesModelProvisioner: pinned model.default to %@ in %@", freeDefaultModel, configPath)
            return true
        } catch {
            NSLog("HermesModelProvisioner: failed to write %@: %@", configPath, error.localizedDescription)
            return false
        }
    }

    /// True when a `model.default` value already names a free (`:free`) model.
    static func isFreeModel(_ value: String) -> Bool {
        value.trimmingCharacters(in: .whitespaces).hasSuffix(":free")
    }

    /// Pure transform: returns the rewritten YAML, or nil when no change is
    /// needed (the default is already a free model).
    ///
    /// Handles three shapes:
    ///  - a top-level `model:` block with a `default:` child (replace value),
    ///  - a `model:` block without a `default:` child (insert one), and
    ///  - no `model:` block at all / empty file (prepend a minimal block).
    static func rewrite(_ contents: String) -> String? {
        let desired = "  default: \(freeDefaultModel)"
        var lines = contents.isEmpty ? [] : contents.components(separatedBy: "\n")

        guard let modelIdx = topLevelKeyIndex(in: lines, key: "model") else {
            // No model block — prepend one. Keep provider on nous for OAuth.
            let block = ["model:", desired, "  provider: nous"]
            let body = lines.isEmpty ? [] : lines
            return (block + body).joined(separator: "\n")
        }

        // Scan the model block's children (more-indented lines) for `default:`.
        var defaultIdx: Int?
        var i = modelIdx + 1
        while i < lines.count {
            let line = lines[i]
            let trimmed = line.trimmingCharacters(in: .whitespaces)
            let isIndented = line.first == " " || line.first == "\t"
            if !trimmed.isEmpty && !isIndented { break } // next top-level key ends the block
            if isIndented && trimmed.hasPrefix("default:") {
                defaultIdx = i
                break
            }
            i += 1
        }

        if let defaultIdx {
            let currentValue = lines[defaultIdx]
                .trimmingCharacters(in: .whitespaces)
                .replacingOccurrences(of: "default:", with: "")
                .trimmingCharacters(in: .whitespaces)
            if isFreeModel(currentValue) { return nil } // already free — nothing to do
            lines[defaultIdx] = desired
            return lines.joined(separator: "\n")
        }

        // model block exists but has no default — insert as its first child.
        lines.insert(desired, at: modelIdx + 1)
        return lines.joined(separator: "\n")
    }

    /// Index of a top-level (unindented) `key:` line, if present.
    private static func topLevelKeyIndex(in lines: [String], key: String) -> Int? {
        for (idx, line) in lines.enumerated() {
            guard line.first != " ", line.first != "\t" else { continue }
            if line.trimmingCharacters(in: .whitespaces) == "\(key):" {
                return idx
            }
        }
        return nil
    }
}
