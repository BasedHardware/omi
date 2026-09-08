import Foundation

/// The packaged files the agent runtime resolves *after* the bridge script, and
/// therefore the ones no existing startup check can see.
///
/// `AgentRuntimeProcess` spawns `agent/dist/index.js`; the pi-mono adapter inside
/// it then resolves `../../../pi-mono-extension/index.ts` from its own module URL.
/// That extension is what registers the `omi` provider, so a bundle that shipped
/// without it makes pi-mono exit 1 with `Unknown provider "omi"` on *every* turn —
/// after the app has already accepted the message. Checking node + bridge script
/// alone is not enough: they were both present in the bundle that failed.
///
/// This is a startup contract, not a diagnostic. A runtime that cannot answer a
/// turn must refuse the turn with a stated reason instead of accepting it.
enum AgentRuntimePayload {
  struct Component: Equatable, Sendable {
    enum Kind: Equatable, Sendable {
      case file
      case directory
    }

    let relativePath: String
    let kind: Kind
  }

  /// Resolved relative to the runtime root, i.e. the directory that holds both
  /// `agent/` and `pi-mono-extension/`. `agent/dist/index.js` is deliberately
  /// absent: `findBridgeScript()` already proved it exists.
  static let components: [Component] = [
    Component(relativePath: "agent/dist/runtime/omi-tool-manifest.js", kind: .file),
    Component(relativePath: "agent/package.json", kind: .file),
    Component(relativePath: "agent/node_modules", kind: .directory),
    Component(relativePath: "pi-mono-extension/index.ts", kind: .file),
    Component(relativePath: "pi-mono-extension/node_modules", kind: .directory),
  ]

  /// `<root>/agent/dist/index.js` → `<root>`. Mirrors the adapter's own
  /// `new URL("../../../pi-mono-extension/index.ts", import.meta.url)` so the
  /// check and the spawn cannot disagree about where the payload lives. Holds
  /// for both bundle (`Contents/Resources/…`) and repo checkout layouts.
  static func runtimeRoot(forBridgeScriptPath bridgeScriptPath: String) -> String {
    let distDirectory = (bridgeScriptPath as NSString).deletingLastPathComponent
    let agentDirectory = (distDirectory as NSString).deletingLastPathComponent
    return (agentDirectory as NSString).deletingLastPathComponent
  }

  /// Relative paths of every component that is missing, empty, or the wrong
  /// kind. Empty result means this runtime can attempt a turn.
  static func missingComponents(
    bridgeScriptPath: String,
    fileManager: FileManager = .default
  ) -> [String] {
    let root = runtimeRoot(forBridgeScriptPath: bridgeScriptPath)
    return components.compactMap { component in
      let path = (root as NSString).appendingPathComponent(component.relativePath)
      return isUsable(path: path, kind: component.kind, fileManager: fileManager)
        ? nil : component.relativePath
    }
  }

  /// An empty directory or a zero-byte file fails at spawn exactly like an
  /// absent one — a truncated copy is not a working runtime.
  private static func isUsable(path: String, kind: Component.Kind, fileManager: FileManager) -> Bool {
    var isDirectory: ObjCBool = false
    guard fileManager.fileExists(atPath: path, isDirectory: &isDirectory) else { return false }
    switch kind {
    case .file:
      guard !isDirectory.boolValue else { return false }
      let size = (try? fileManager.attributesOfItem(atPath: path)[.size] as? NSNumber)??.intValue
      return (size ?? 0) > 0
    case .directory:
      guard isDirectory.boolValue else { return false }
      let entries = (try? fileManager.contentsOfDirectory(atPath: path)) ?? []
      return !entries.isEmpty
    }
  }
}

extension AgentRuntimePayload {
  /// Why a start must be refused, and what to say about it — one value so the coordinator neither
  /// decides nor phrases it.
  ///
  /// This lives here rather than at the call site because the convergence ratchet bounds
  /// `AgentRuntimeProcess`: the two historic coordinator files are meant to shrink toward deletion,
  /// so a policy that can live beside the thing it describes belongs beside it.
  struct StartRefusal {
    let missing: [String]
    var logLine: String {
      "AgentRuntimeProcess: pi-mono start refused, agent runtime payload incomplete "
        + "missing=\(missing.joined(separator: ","))"
    }
    var error: BridgeError { .agentRuntimePayloadIncomplete(missing: missing) }
  }

  /// `nil` when the bundle can actually answer a turn.
  static func startRefusal(bridgeScriptPath: String) -> StartRefusal? {
    let missing = missingComponents(bridgeScriptPath: bridgeScriptPath)
    return missing.isEmpty ? nil : StartRefusal(missing: missing)
  }
}
