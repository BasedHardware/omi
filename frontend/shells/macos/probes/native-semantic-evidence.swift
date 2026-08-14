// Native semantic evidence probe for an AppKit/WKWebView scratch shell.
//
// This is intentionally a separate executable: it never changes the product
// shell, captures no pixels, and does not inspect page JavaScript. Accessibility
// observations come from AXUIElement and keyboard events come from CoreGraphics.
// AX-only observations do not activate the target. Keyboard traces temporarily
// activate a background scratch window, then hide it and restore the app that
// was frontmost before the trace:
//
//   swiftc -O -framework AppKit -framework ApplicationServices \
//     -framework CoreGraphics -o /tmp/omi-native-semantic-evidence \
//     core/shells/macos/probes/native-semantic-evidence.swift
//   /tmp/omi-native-semantic-evidence --pid <shell-pid> \
//     --keys cmd+k,escape --json
//
// `--activate` is required when sending keys. Activation is bounded to the key
// sequence and automatically undone before evidence is emitted.
import ApplicationServices
import AppKit
import CoreGraphics
import Foundation

private extension Array {
  subscript(safe index: Index) -> Element? {
    indices.contains(index) ? self[index] : nil
  }
}

private let schema = "omi.native-semantic-evidence.v2"
private let fullSHA = try! NSRegularExpression(pattern: "^[0-9a-f]{40}$")
private let safeRunID = try! NSRegularExpression(pattern: "^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
private let allowedRoles: Set<String> = [
  "AXApplication", "AXButton", "AXCheckBox", "AXComboBox", "AXDialog", "AXGroup",
  "AXHeading", "AXImage", "AXLink", "AXList", "AXListItem", "AXMenu", "AXMenuItem",
  "AXRadioButton", "AXRow", "AXScrollArea", "AXSearchField", "AXStaticText", "AXTab",
  "AXTabGroup", "AXTable", "AXTextArea", "AXTextField", "AXToolbar", "AXWebArea",
  "AXWindow",
]
private let allowedNames: Set<String> = [
  "app", "main", "window", "content", "route", "home", "tasks", "memories", "conversations",
  "folders", "listen", "chat", "settings", "primary-navigation", "bottom-navigation",
  "command-palette", "command-palette-dialog", "command-input", "open-command-palette",
  "search", "composer", "chat-composer", "listen-transcript", "task-list", "memory-list",
  "conversation-list", "send", "save", "retry", "latest", "dialog", "main-window", "omi",
]

private func bounded(_ value: String?, limit: Int = 64) -> String? {
  guard let value, !value.isEmpty, value.utf8.count <= limit else { return nil }
  return value
}

private func valid(_ value: String, _ expression: NSRegularExpression) -> Bool {
  let range = NSRange(value.startIndex..<value.endIndex, in: value)
  return expression.firstMatch(in: value, range: range) != nil
}

private struct AXNode: Codable, Equatable {
  let role: String
  let subrole: String?
  let name: String?
  let identifier: String?
  let window: String?
  // Ordinal/window-path context is used only for focus identity. It is not
  // serialized, keeping the evidence surface to redacted role/name tokens.
  var focusWindowContext: String? = nil

  enum CodingKeys: String, CodingKey {
    case role, subrole, name, identifier, window
  }

  init(role: String, subrole: String?, name: String?, identifier: String?, window: String?, focusWindowContext: String? = nil) {
    self.role = role; self.subrole = subrole; self.name = name; self.identifier = identifier; self.window = window; self.focusWindowContext = focusWindowContext
  }

  var focusIdentity: String? {
    // AX titles/descriptions are not identity.  A keyboard trace may only
    // claim focus restoration when the target supplies a stable, allowlisted
    // identifier and a stable window token; otherwise collisions/all-nil
    // metadata fail closed.
    guard let identifier, !identifier.isEmpty, let window, !window.isEmpty else { return nil }
    return [role, subrole ?? "", identifier, window, focusWindowContext ?? ""].joined(separator: "|")
  }
}

private struct KeyObservation: Codable {
  let key: String
  let keyCode: UInt16
  let modifiers: [String]
  let posted: Bool
  let focusedBefore: AXNode?
  let focusedAfter: AXNode?
  let targetConsumed: Bool
  let expectedLandmark: String?
}

private struct WindowObservation: Codable {
  let role: String
  let name: String?
  let identifier: String?
}

private struct TargetBinding: Codable {
  let pid: Int32
  let bundleId: String
  let processNameBound: Bool
  let expectedPid: Int32
  let expectedBundleId: String
  let bound: Bool
}

private struct Evidence: Codable {
  let schema: String
  let shell: String
  let runId: String
  let targetPid: Int32?
  let target: TargetBinding?
  let axTrusted: Bool
  let evidenceClass: String
  let kind: String?
  let coordinate: String?
  let sourceCoreSha: String?
  let sourcePlatformSha: String?
  let windows: [WindowObservation]
  let nodes: [AXNode]
  let domainLandmark: String?
  let domainLandmarkFound: Bool
  let focusedBefore: AXNode?
  let keys: [KeyObservation]
  let focusRestored: Bool?
  var frontmostRestored: Bool?
  let matrixEligible: Bool
  let error: String?
}

private enum ProbeError: Error, CustomStringConvertible {
  case usage(String)
  case targetNotFound(String)
  case targetAmbiguous(String)
  case targetIdentityMismatch(String)
  case accessibilityNotTrusted
  case targetNotActive
  case noAccessibleWindow
  case noDomainLandmark(String)
  case invalidMatrixBinding(String)
  case keyboardTransitionNotObserved(String)
  case focusNotRestored
  case frontmostNotRestored
  case cannotPostKeys

  var description: String {
    switch self {
    case .usage(let message): return "usage: \(message)"
    case .targetNotFound(let message): return "target-not-found: \(message)"
    case .targetAmbiguous(let message): return "target-ambiguous: \(message)"
    case .targetIdentityMismatch(let message): return "target-identity-mismatch: \(message)"
    case .accessibilityNotTrusted:
      return "accessibility-not-trusted: grant Accessibility access to this probe"
    case .targetNotActive: return "target-not-active: pass --activate before --keys"
    case .noAccessibleWindow: return "no-accessible-window: target has no observable native window"
    case .noDomainLandmark(let message): return "no-domain-landmark: \(message)"
    case .invalidMatrixBinding(let message): return "invalid-matrix-binding: \(message)"
    case .keyboardTransitionNotObserved(let message): return "keyboard-transition-not-observed: \(message)"
    case .focusNotRestored: return "focus-not-restored: Escape did not return to the bound focus identity"
    case .frontmostNotRestored: return "frontmost-not-restored: the previously active app could not be restored"
    case .cannotPostKeys: return "cannot-post-keys: CGEvent creation failed"
    }
  }
}

private struct Options {
  var pid: Int32?
  var bundleId: String?
  var expectedBundleId: String?
  var expectedProcessName: String?
  var name: String?
  var runId = "native-semantic"
  var sourceCoreSha: String?
  var sourcePlatformSha: String?
  var coordinate: String?
  var kind: String?
  var landmark: String?
  var expectedAfter: [String?] = []
  var requireMatrix = false
  var keys: [String] = []
  var activate = false
  var json = false
  var help = false
  var selfTest = false
  var requestTrust = false
}

private func printHelp() {
  print("""
  Usage: native-semantic-evidence (--pid PID | --name NAME) [options]

  Options:
    --pid PID             Exact target process (preferred for scratch shells)
    --bundle-id ID        Assert the resolved process bundle identifier
    --expected-bundle-id ID  Required exact bundle identifier for matrix evidence
    --expected-process-name NAME  Required scratch process name for matrix evidence
    --name NAME            Resolve one running application by process name
    --run-id ID             Stable evidence identifier (default: native-semantic)
    --source-core-sha SHA   Exact 40-character core source SHA
    --source-platform-sha SHA Exact 40-character platform source SHA
    --coordinate KEY        Exact matrix coordinate binding
    --kind KIND             ax_snapshot or keyboard_trace
    --landmark NAME         Allowlisted domain landmark required for success
    --expect-after LIST     Comma-separated allowlisted landmarks after keys; '-' means none
    --require-matrix        Fail unless all matrix bindings and observations are proven
    --keys SPEC             Comma-separated keys, e.g. cmd+k,escape
    --activate              Temporarily activate for keys, then hide and restore prior app
    --request-trust         Prompt Accessibility for THIS probe binary and open Settings if needed
    --json                  Emit one JSON evidence document
    --self-test              Run deterministic redaction/focus guard tests
    --help                  Show this help

  Keys: cmd+k, ctrl+k, shift+enter, enter, escape, tab, shift+tab,
        arrow-up, arrow-down, arrow-left, arrow-right

  AX snapshots can use the shell's off-screen mode. Keyboard traces should use
  OMI_SEMANTIC_WINDOW=1, which shows a small background accessory window only
  while the trace needs it. This probe observes bounded AXUIElement roles,
  allowlisted AX roles/names and posts native CGEvents; it does not take screenshots or
  claim that a browser preview is native evidence.
  """)
}

private func parseOptions(_ arguments: [String]) throws -> Options {
  var options = Options()
  var index = 0
  while index < arguments.count {
    let argument = arguments[index]
    switch argument {
    case "--help", "-h":
      options.help = true
      index += 1
    case "--pid":
      guard index + 1 < arguments.count, let value = Int32(arguments[index + 1]), value > 0
      else { throw ProbeError.usage("--pid needs a positive integer") }
      options.pid = value
      index += 2
    case "--bundle-id":
      guard index + 1 < arguments.count, !arguments[index + 1].isEmpty
      else { throw ProbeError.usage("--bundle-id needs a value") }
      options.bundleId = arguments[index + 1]
      index += 2
    case "--expected-bundle-id":
      guard index + 1 < arguments.count, !arguments[index + 1].isEmpty
      else { throw ProbeError.usage("--expected-bundle-id needs a value") }
      options.expectedBundleId = arguments[index + 1]
      index += 2
    case "--expected-process-name":
      guard index + 1 < arguments.count, !arguments[index + 1].isEmpty
      else { throw ProbeError.usage("--expected-process-name needs a value") }
      options.expectedProcessName = arguments[index + 1]
      index += 2
    case "--name":
      guard index + 1 < arguments.count, !arguments[index + 1].isEmpty
      else { throw ProbeError.usage("--name needs a value") }
      options.name = arguments[index + 1]
      index += 2
    case "--run-id":
      guard index + 1 < arguments.count, !arguments[index + 1].isEmpty
      else { throw ProbeError.usage("--run-id needs a value") }
      options.runId = arguments[index + 1]
      index += 2
    case "--source-core-sha":
      guard index + 1 < arguments.count, valid(arguments[index + 1].lowercased(), fullSHA)
      else { throw ProbeError.usage("--source-core-sha needs a full SHA") }
      options.sourceCoreSha = arguments[index + 1].lowercased()
      index += 2
    case "--source-platform-sha":
      guard index + 1 < arguments.count, valid(arguments[index + 1].lowercased(), fullSHA)
      else { throw ProbeError.usage("--source-platform-sha needs a full SHA") }
      options.sourcePlatformSha = arguments[index + 1].lowercased()
      index += 2
    case "--coordinate":
      guard index + 1 < arguments.count, !arguments[index + 1].isEmpty,
        arguments[index + 1].utf8.count <= 256,
        arguments[index + 1].allSatisfy({ $0.isASCII && ( $0.isLetter || $0.isNumber || "_:-|".contains($0)) })
      else { throw ProbeError.usage("--coordinate needs a bounded matrix key") }
      options.coordinate = arguments[index + 1]
      index += 2
    case "--kind":
      guard index + 1 < arguments.count, ["ax_snapshot", "keyboard_trace"].contains(arguments[index + 1])
      else { throw ProbeError.usage("--kind must be ax_snapshot or keyboard_trace") }
      options.kind = arguments[index + 1]
      index += 2
    case "--landmark":
      guard index + 1 < arguments.count, allowedNames.contains(arguments[index + 1].lowercased())
      else { throw ProbeError.usage("--landmark must be an allowlisted name") }
      options.landmark = arguments[index + 1].lowercased()
      index += 2
    case "--expect-after":
      guard index + 1 < arguments.count else { throw ProbeError.usage("--expect-after needs a value") }
      options.expectedAfter = arguments[index + 1].split(separator: ",", omittingEmptySubsequences: false).map { token in
        let value = String(token).lowercased()
        return value == "-" ? nil : value
      }
      index += 2
    case "--require-matrix":
      options.requireMatrix = true
      index += 1
    case "--keys":
      guard index + 1 < arguments.count else { throw ProbeError.usage("--keys needs a value") }
      options.keys = arguments[index + 1].split(separator: ",", omittingEmptySubsequences: true).map(String.init)
      index += 2
    case "--activate":
      options.activate = true
      index += 1
    case "--json":
      options.json = true
      index += 1
    case "--self-test":
      options.selfTest = true
      index += 1
    case "--request-trust":
      options.requestTrust = true
      index += 1
    default:
      throw ProbeError.usage("unknown option \(argument)")
    }
  }
  if options.help { return options }
  if options.selfTest { return options }
  if options.requestTrust { return options }
  guard options.pid != nil || options.name != nil else { throw ProbeError.usage("provide --pid or --name") }
  guard valid(options.runId, safeRunID) else { throw ProbeError.usage("--run-id must be a bounded stable identifier") }
  if !options.keys.isEmpty && !options.activate {
    throw ProbeError.usage("--keys requires --activate")
  }
  guard options.keys.allSatisfy({ $0.utf8.count <= 32 && $0.allSatisfy({ $0.isASCII }) }) else {
    throw ProbeError.usage("--keys contains an invalid bounded key")
  }
  guard options.expectedAfter.allSatisfy({ value in value == nil || (value!.utf8.count <= 64 && allowedNames.contains(value!)) }) else {
    throw ProbeError.usage("--expect-after contains an unallowlisted landmark")
  }
  if options.requireMatrix {
    guard let pid = options.pid, pid > 0, options.bundleId != nil,
      let expectedBundleId = options.expectedBundleId, expectedBundleId == options.bundleId,
      let expectedProcessName = options.expectedProcessName, expectedProcessName.hasPrefix("omi-on-"),
      valid(options.runId, safeRunID), options.sourceCoreSha != nil, options.sourcePlatformSha != nil,
      options.coordinate != nil, let kind = options.kind, options.landmark != nil,
      allowedNames.contains(options.landmark!.lowercased()), !expectedProcessName.contains("/"),
      expectedProcessName.utf8.count <= 64,
      expectedProcessName.allSatisfy({ $0.isASCII && ($0.isLetter || $0.isNumber || ".-_".contains($0)) }),
      expectedBundleId.contains("omi"), expectedBundleId.utf8.count <= 128,
      expectedBundleId.allSatisfy({ $0.isASCII && !$0.isWhitespace }) else { throw ProbeError.invalidMatrixBinding("matrix target, source, run, coordinate, kind, and landmark are required") }
    if kind == "keyboard_trace" {
      guard !options.keys.isEmpty, options.expectedAfter.count == options.keys.count else {
        throw ProbeError.invalidMatrixBinding("keyboard expected-after count must match keys")
      }
    }
  }
  return options
}

private func copyAttribute(_ element: AXUIElement, _ attribute: String) -> CFTypeRef? {
  var value: CFTypeRef?
  let status = AXUIElementCopyAttributeValue(element, attribute as CFString, &value)
  guard status == .success else { return nil }
  return value
}

private func stringAttribute(_ element: AXUIElement, _ attribute: String) -> String? {
  guard let value = copyAttribute(element, attribute) else { return nil }
  return value as? String
}

private func boolAttribute(_ element: AXUIElement, _ attribute: String) -> Bool? {
  guard let value = copyAttribute(element, attribute) else { return nil }
  return (value as? NSNumber)?.boolValue
}

private func allowlistedName(_ element: AXUIElement) -> String? {
  for attribute in [kAXIdentifierAttribute, kAXTitleAttribute, kAXDescriptionAttribute] {
    guard let raw = stringAttribute(element, attribute)?.lowercased(), bounded(raw) != nil else { continue }
    if allowedNames.contains(raw) { return raw }
  }
  return nil
}

private func node(_ element: AXUIElement?, window: String? = nil, focusWindowContext: String? = nil) -> AXNode? {
  guard let element else { return nil }
  guard let role = stringAttribute(element, kAXRoleAttribute), allowedRoles.contains(role) else { return nil }
  let rawIdentifier = stringAttribute(element, kAXIdentifierAttribute)?.lowercased()
  let identifier = rawIdentifier.flatMap { allowedNames.contains($0) ? bounded($0) : nil }
  // Subroles are implementation-specific AX strings and may contain titles or
  // other host-provided text.  The matrix contract only permits the bounded
  // role/name token surface, so keep the optional field deliberately empty.
  return AXNode(role: role, subrole: nil, name: allowlistedName(element), identifier: identifier, window: window, focusWindowContext: focusWindowContext)
}

private func elementAttribute(_ element: AXUIElement, _ attribute: String) -> AXUIElement? {
  guard let value = copyAttribute(element, attribute) else { return nil }
  guard CFGetTypeID(value) == AXUIElementGetTypeID() else { return nil }
  return unsafeBitCast(value, to: AXUIElement.self)
}

private func elementArrayAttribute(_ element: AXUIElement, _ attribute: String) -> [AXUIElement] {
  guard let value = copyAttribute(element, attribute), CFGetTypeID(value) == CFArrayGetTypeID()
  else { return [] }
  let array = unsafeBitCast(value, to: CFArray.self)
  var elements: [AXUIElement] = []
  for index in 0..<CFArrayGetCount(array) {
    let item = CFArrayGetValueAtIndex(array, index)
    guard let item else { continue }
    let itemRef = unsafeBitCast(item, to: CFTypeRef.self)
    guard CFGetTypeID(itemRef) == AXUIElementGetTypeID() else { continue }
    elements.append(unsafeBitCast(itemRef, to: AXUIElement.self))
  }
  return elements
}

private func windowObservations(_ application: AXUIElement) -> [WindowObservation] {
  elementArrayAttribute(application, kAXWindowsAttribute).compactMap { window -> WindowObservation? in
    let role = stringAttribute(window, kAXRoleAttribute)
    // Some macOS releases include the application element in AXWindows. Never
    // report it as a window; doing so would turn an inactive shell into a false
    // native-window success.
    guard let role, role == kAXWindowRole, allowedRoles.contains(role) else { return nil }
    let identifier: String?
    if let raw = stringAttribute(window, kAXIdentifierAttribute)?.lowercased(), allowedNames.contains(raw) {
      identifier = bounded(raw)
    } else {
      identifier = nil
    }
    return WindowObservation(
      role: role,
      name: allowlistedName(window),
      identifier: identifier)
  }
}

private func focusedElement(_ application: AXUIElement, windows: [AXUIElement]) -> AXUIElement? {
  if let element = elementAttribute(application, kAXFocusedUIElementAttribute) { return element }
  for window in windows {
    if let element = elementAttribute(window, kAXFocusedUIElementAttribute) { return element }
  }
  return nil
}

private func focusedNode(_ application: AXUIElement, windows: [AXUIElement]) -> AXNode? {
  for (index, window) in windows.enumerated() {
    guard let focused = elementAttribute(window, kAXFocusedUIElementAttribute) else { continue }
    // A raw window identifier can contain host/user text.  If it is not one
    // of the exact semantic tokens, fail closed instead of serializing it.
    let windowToken = allowlistedName(window)
    let context = windowToken.map { "\($0)#\(index)" }
    if let value = node(focused, window: windowToken, focusWindowContext: context) { return value }
  }
  return node(elementAttribute(application, kAXFocusedUIElementAttribute))
}

private struct AXScan {
  var nodes: [AXNode] = []
  var foundLandmark = false
}

private func scan(_ element: AXUIElement, window: String?, depth: Int, landmark: String?, result: inout AXScan) {
  guard depth <= 8, result.nodes.count < 128 else { return }
  if let value = node(element, window: window) {
    result.nodes.append(value)
    if let landmark, value.name == landmark { result.foundLandmark = true }
  }
  for child in elementArrayAttribute(element, kAXChildrenAttribute) {
    scan(child, window: window, depth: depth + 1, landmark: landmark, result: &result)
    if result.nodes.count >= 128 { return }
  }
}

private func isScratchProcess(_ app: NSRunningApplication, expectedName: String) -> Bool {
  guard expectedName.hasPrefix("omi-on-"), app.localizedName == expectedName else { return false }
  guard let bundle = app.bundleURL?.lastPathComponent, bundle.hasPrefix("omi-on-"), bundle.hasSuffix(".app") else { return false }
  return true
}

private func sameFocus(_ first: AXNode?, _ second: AXNode?) -> Bool {
  guard let first, let second else { return false }
  // Values and enabled state can legitimately change while a command palette
  // opens and closes. Focus restoration is an identity assertion, not a stale
  // value snapshot.
  guard let firstIdentity = first.focusIdentity, let secondIdentity = second.focusIdentity else { return false }
  return firstIdentity == secondIdentity
}

private struct KeySpec {
  let label: String
  let keyCode: CGKeyCode
  let modifiers: CGEventFlags
  let modifierLabels: [String]
}

private func keySpec(_ raw: String) -> KeySpec? {
  let parts = raw.lowercased().split(separator: "+").map(String.init)
  guard let key = parts.last else { return nil }
  var flags: CGEventFlags = []
  var labels: [String] = []
  for modifier in parts.dropLast() {
    switch modifier {
    case "cmd", "command", "meta": flags.insert(.maskCommand); labels.append("command")
    case "ctrl", "control": flags.insert(.maskControl); labels.append("control")
    case "shift": flags.insert(.maskShift); labels.append("shift")
    case "alt", "option": flags.insert(.maskAlternate); labels.append("option")
    default: return nil
    }
  }
  let keyCodes: [String: CGKeyCode] = [
    "k": 40, "enter": 36, "return": 36, "escape": 53, "esc": 53,
    "tab": 48, "arrow-up": 126, "arrow-down": 125, "arrow-left": 123,
    "arrow-right": 124,
  ]
  guard let code = keyCodes[key] else { return nil }
  return KeySpec(label: raw, keyCode: code, modifiers: flags, modifierLabels: labels)
}

private func post(_ spec: KeySpec) throws {
  guard let source = CGEventSource(stateID: .hidSystemState),
    let down = CGEvent(keyboardEventSource: source, virtualKey: spec.keyCode, keyDown: true),
    let up = CGEvent(keyboardEventSource: source, virtualKey: spec.keyCode, keyDown: false)
  else { throw ProbeError.cannotPostKeys }
  down.flags = spec.modifiers
  up.flags = spec.modifiers
  down.post(tap: .cghidEventTap)
  usleep(60_000)
  up.post(tap: .cghidEventTap)
  usleep(220_000)
}

private func emit(_ evidence: Evidence, json: Bool) {
  let encoder = JSONEncoder()
  if json { encoder.outputFormatting = [.sortedKeys] }
  else { encoder.outputFormatting = [.prettyPrinted, .sortedKeys] }
  if let data = try? encoder.encode(evidence), let text = String(data: data, encoding: .utf8) {
    print(text)
  }
}

private func failureEvidence(_ options: Options, error: Error, app: NSRunningApplication? = nil) -> Evidence {
  Evidence(
    schema: schema,
    shell: "macos",
    runId: options.runId,
    targetPid: app?.processIdentifier,
    target: nil,
    axTrusted: AXIsProcessTrusted(),
    evidenceClass: "supplementary_observation",
    kind: options.kind,
    coordinate: options.coordinate,
    sourceCoreSha: options.sourceCoreSha,
    sourcePlatformSha: options.sourcePlatformSha,
    windows: [],
    nodes: [],
    domainLandmark: options.landmark,
    domainLandmarkFound: false,
    focusedBefore: nil,
    keys: [],
    focusRestored: nil,
    frontmostRestored: nil,
    matrixEligible: false,
    error: String(describing: error))
}

private func resolveTarget(_ options: Options) throws -> NSRunningApplication {
  if let pid = options.pid {
    guard let app = NSRunningApplication(processIdentifier: pid) else {
      throw ProbeError.targetNotFound("pid \(pid) is not running")
    }
    if let bundleId = options.bundleId, app.bundleIdentifier != bundleId {
      throw ProbeError.targetIdentityMismatch("bundle identifier does not match expected process")
    }
    if let expected = options.expectedBundleId, app.bundleIdentifier != expected {
      throw ProbeError.targetIdentityMismatch("bundle identifier does not match matrix binding")
    }
    if options.requireMatrix, let expectedName = options.expectedProcessName, !isScratchProcess(app, expectedName: expectedName) {
      throw ProbeError.targetIdentityMismatch("process is not the expected omi-on-* scratch shell")
    }
    return app
  }
  let candidates = NSWorkspace.shared.runningApplications.filter { app in
    if let bundleId = options.bundleId { return app.bundleIdentifier == bundleId }
    return app.localizedName == options.name
  }
  guard !candidates.isEmpty else {
    throw ProbeError.targetNotFound(options.bundleId ?? options.name ?? "application")
  }
  guard candidates.count == 1 else {
    let names = candidates.map { "\($0.processIdentifier):\($0.localizedName ?? "?")" }.joined(separator: ",")
    throw ProbeError.targetAmbiguous(names)
  }
  if options.requireMatrix { throw ProbeError.invalidMatrixBinding("matrix evidence requires an exact PID") }
  return candidates[0]
}

private func runResolved(_ options: Options, app: NSRunningApplication) throws -> Evidence {
  guard let bundleId = app.bundleIdentifier else {
    throw ProbeError.targetIdentityMismatch("target bundle identifier is unavailable")
  }
  let expectedBundle = options.expectedBundleId ?? options.bundleId ?? bundleId
  let processBound = options.expectedProcessName.map { isScratchProcess(app, expectedName: $0) } ?? true
  let target = TargetBinding(
    pid: app.processIdentifier,
    bundleId: bundleId,
    processNameBound: processBound,
    expectedPid: options.pid ?? app.processIdentifier,
    expectedBundleId: expectedBundle,
    bound: app.processIdentifier == (options.pid ?? app.processIdentifier) && bundleId == expectedBundle && processBound)
  guard !options.requireMatrix || target.bound else {
    throw ProbeError.targetIdentityMismatch("PID, bundle identifier, or scratch process name is not bound")
  }
  if options.activate {
    _ = app.activate(options: [])
    usleep(180_000)
  }
  let application = AXUIElementCreateApplication(app.processIdentifier)
  let axWindows = elementArrayAttribute(application, kAXWindowsAttribute)
  if options.activate {
    for window in axWindows where stringAttribute(window, kAXRoleAttribute) == kAXWindowRole {
      _ = AXUIElementPerformAction(window, kAXRaiseAction as CFString)
    }
    usleep(120_000)
  }
  let windows = windowObservations(application)
  guard !windows.isEmpty else { throw ProbeError.noAccessibleWindow }
  if !options.keys.isEmpty {
    let isActive = NSRunningApplication(processIdentifier: app.processIdentifier)?.isActive ?? false
    guard isActive else { throw ProbeError.targetNotActive }
  }
  var snapshot = AXScan()
  for window in axWindows where stringAttribute(window, kAXRoleAttribute) == kAXWindowRole {
    scan(window, window: allowlistedName(window), depth: 0, landmark: options.landmark, result: &snapshot)
    if snapshot.nodes.count >= 128 { break }
  }
  guard !options.requireMatrix || snapshot.foundLandmark else {
    throw ProbeError.noDomainLandmark(options.landmark ?? "required allowlisted landmark")
  }
  let before = focusedNode(application, windows: axWindows)
  var observations: [KeyObservation] = []
  for (index, rawKey) in options.keys.enumerated() {
    guard let spec = keySpec(rawKey) else { throw ProbeError.usage("unknown key \(rawKey)") }
    let keyBefore = focusedNode(application, windows: axWindows)
    let expected = options.expectedAfter[safe: index] ?? nil
    var beforeScan = AXScan()
    if let expected {
      for window in axWindows where stringAttribute(window, kAXRoleAttribute) == kAXWindowRole {
        scan(window, window: allowlistedName(window), depth: 0, landmark: expected, result: &beforeScan)
        if beforeScan.nodes.count >= 128 { break }
      }
    }
    try post(spec)
    var afterScan = AXScan()
    for window in axWindows where stringAttribute(window, kAXRoleAttribute) == kAXWindowRole {
      scan(window, window: allowlistedName(window), depth: 0, landmark: expected, result: &afterScan)
      if afterScan.nodes.count >= 128 { break }
    }
    let keyAfter = focusedNode(application, windows: axWindows)
    // A landmark that was already present before the key is not evidence of a
    // transition. Escape remains a focus-identity restoration proof.
    let consumed = expected.map { _ in !beforeScan.foundLandmark && afterScan.foundLandmark } ?? (rawKey.lowercased() == "escape" && sameFocus(keyBefore, keyAfter))
    observations.append(KeyObservation(
      key: spec.label,
      keyCode: spec.keyCode,
      modifiers: spec.modifierLabels,
      posted: true,
      focusedBefore: keyBefore,
      focusedAfter: keyAfter,
      targetConsumed: consumed,
      expectedLandmark: expected))
    guard !options.requireMatrix || consumed else {
      throw ProbeError.keyboardTransitionNotObserved(spec.label)
    }
  }
  let after = focusedNode(application, windows: axWindows)
  let restored = options.keys.isEmpty ? nil : sameFocus(before, after)
  if options.requireMatrix && options.kind == "keyboard_trace" && restored != true {
    throw ProbeError.focusNotRestored
  }
  // Generic operator observations are supplementary by definition.  Matrix
  // eligibility is earned only by an explicit, fully bound --require-matrix
  // invocation with the required landmark/keyboard transition proof.
  let matrixEligible = options.requireMatrix && (options.kind == "ax_snapshot" ? snapshot.foundLandmark : observations.allSatisfy(\.targetConsumed) && restored == true)
  return Evidence(
    schema: schema,
    shell: "macos",
    runId: options.runId,
    targetPid: app.processIdentifier,
    target: target,
    axTrusted: true,
    evidenceClass: matrixEligible ? (options.kind == "keyboard_trace" ? "native_keyboard_trace" : "native_ax_snapshot") : "supplementary_observation",
    kind: options.kind,
    coordinate: options.coordinate,
    sourceCoreSha: options.sourceCoreSha,
    sourcePlatformSha: options.sourcePlatformSha,
    windows: windows,
    nodes: snapshot.nodes,
    domainLandmark: options.landmark,
    domainLandmarkFound: snapshot.foundLandmark,
    focusedBefore: before,
    keys: observations,
    focusRestored: restored,
    frontmostRestored: nil,
    matrixEligible: matrixEligible,
    error: nil)
}

private func restoreFrontmost(
  _ prior: NSRunningApplication?, target: NSRunningApplication
) throws -> Bool {
  guard let prior else {
    target.hide()
    return true
  }
  if prior.processIdentifier == target.processIdentifier { return true }
  target.hide()
  if prior.isTerminated { return true }
  _ = prior.activate(options: [])
  for _ in 0..<20 {
    if NSRunningApplication(processIdentifier: prior.processIdentifier)?.isActive == true {
      return true
    }
    usleep(25_000)
  }
  throw ProbeError.frontmostNotRestored
}

private func run(_ options: Options) throws -> Evidence {
  guard AXIsProcessTrusted() else { throw ProbeError.accessibilityNotTrusted }
  let app = try resolveTarget(options)
  let prior = options.activate ? NSWorkspace.shared.frontmostApplication : nil
  do {
    var evidence = try runResolved(options, app: app)
    if options.activate {
      evidence.frontmostRestored = try restoreFrontmost(prior, target: app)
    }
    return evidence
  } catch {
    if options.activate {
      do {
        _ = try restoreFrontmost(prior, target: app)
      } catch {
        throw ProbeError.frontmostNotRestored
      }
    }
    throw error
  }
}

private func selfTest() -> Bool {
  let noIdentity = AXNode(role: "AXTextField", subrole: nil, name: "composer", identifier: nil, window: "main-window", focusWindowContext: nil)
  let sameA = AXNode(role: "AXTextField", subrole: nil, name: "composer", identifier: "composer", window: "main-window", focusWindowContext: "main-window#0")
  let sameB = AXNode(role: "AXTextField", subrole: nil, name: "composer", identifier: "composer", window: "main-window", focusWindowContext: "main-window#0")
  let collision = AXNode(role: "AXTextField", subrole: nil, name: "composer", identifier: "composer", window: "main-window", focusWindowContext: "main-window#1")
  return !sameFocus(nil, nil) && !sameFocus(noIdentity, noIdentity) && sameFocus(sameA, sameB) && !sameFocus(sameA, collision) && allowlistedNameToken("composer") != nil && allowlistedNameToken("arbitrary-user-text") == nil
}

private func probeExecutablePath() -> String {
  URL(fileURLWithPath: CommandLine.arguments[0]).standardizedFileURL.path
}

/// Mirror desktop AppState+Permissions: prompt this process, then open the
/// Sequoia Accessibility Settings pane when the API no longer shows a dialog.
private func requestAccessibilityTrust() -> (trusted: Bool, settingsOpened: Bool) {
  if AXIsProcessTrusted() {
    return (true, false)
  }
  let options =
    [kAXTrustedCheckOptionPrompt.takeUnretainedValue() as String: true] as CFDictionary
  let trusted = AXIsProcessTrustedWithOptions(options)
  var settingsOpened = false
  if !trusted {
    if let url = URL(
      string: "x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility")
    {
      settingsOpened = NSWorkspace.shared.open(url)
    }
  }
  return (AXIsProcessTrusted(), settingsOpened)
}

private func emitTrustRequest(trusted: Bool, settingsOpened: Bool) {
  let payload: [String: Any] = [
    "schema": "omi.native-semantic-trust-request.v1",
    "axTrusted": trusted,
    "settingsOpened": settingsOpened,
    "probePath": probeExecutablePath(),
  ]
  if let data = try? JSONSerialization.data(withJSONObject: payload, options: [.sortedKeys]),
    let text = String(data: data, encoding: .utf8)
  {
    print(text)
  }
}

private func allowlistedNameToken(_ value: String) -> String? {
  let lower = value.lowercased()
  return allowedNames.contains(lower) ? bounded(lower) : nil
}

let arguments = Array(CommandLine.arguments.dropFirst())
do {
  let options = try parseOptions(arguments)
  if options.help {
    printHelp()
    exit(0)
  }
  if options.selfTest {
    let passed = selfTest()
    print("{\"schema\":\"omi.native-semantic-self-test.v1\",\"passed\":\(passed ? "true" : "false")}")
    exit(passed ? 0 : 1)
  }
  if options.requestTrust {
    let result = requestAccessibilityTrust()
    emitTrustRequest(trusted: result.trusted, settingsOpened: result.settingsOpened)
    if result.trusted {
      exit(0)
    }
    fputs("accessibility-not-trusted: enable this probe in System Settings > Privacy & Security > Accessibility: \(probeExecutablePath())\n", stderr)
    exit(1)
  }
  do {
    emit(try run(options), json: options.json)
    exit(0)
  } catch {
    emit(failureEvidence(options, error: error), json: options.json)
    fputs("\(error)\n", stderr)
    exit(1)
  }
} catch {
  fputs("\(error)\n", stderr)
  printHelp()
  exit(2)
}
