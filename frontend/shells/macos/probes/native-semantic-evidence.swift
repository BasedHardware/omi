// Native semantic evidence probe for a headed AppKit/WKWebView shell.
//
// This is intentionally a separate executable: it never changes the product
// shell, captures no pixels, and does not inspect page JavaScript. Accessibility
// observations come from AXUIElement and keyboard events come from CoreGraphics.
// Run it while the target scratch shell is frontmost:
//
//   swiftc -O -framework AppKit -framework ApplicationServices \
//     -framework CoreGraphics -o /tmp/omi-native-semantic-evidence \
//     core/shells/macos/probes/native-semantic-evidence.swift
//   /tmp/omi-native-semantic-evidence --pid <shell-pid> \
//     --keys cmd+k,escape --json
//
// `--activate` is required when sending keys. This makes focus-stealing an
// explicit operator choice instead of an accidental side effect of inspection.
import ApplicationServices
import AppKit
import CoreGraphics
import Foundation

private let schema = "omi.native-semantic-evidence.v1"

private struct AXNode: Codable, Equatable {
  let role: String?
  let subrole: String?
  let title: String?
  let description: String?
  let identifier: String?
  let value: String?
  let enabled: Bool?

  var focusIdentity: [String?] {
    [role, subrole, title, description, identifier]
  }
}

private struct KeyObservation: Codable {
  let key: String
  let keyCode: UInt16
  let modifiers: [String]
  let posted: Bool
  let focusedBefore: AXNode?
  let focusedAfter: AXNode?
}

private struct WindowObservation: Codable {
  let role: String?
  let title: String?
  let identifier: String?
}

private struct Evidence: Codable {
  let schema: String
  let shell: String
  let runId: String
  let targetPid: Int32?
  let targetName: String?
  let targetBundleId: String?
  let axTrusted: Bool
  let windows: [WindowObservation]
  let focusedBefore: AXNode?
  let keys: [KeyObservation]
  let focusRestored: Bool?
  let error: String?
}

private enum ProbeError: Error, CustomStringConvertible {
  case usage(String)
  case targetNotFound(String)
  case targetAmbiguous(String)
  case accessibilityNotTrusted
  case targetNotActive
  case noAccessibleWindow
  case cannotPostKeys

  var description: String {
    switch self {
    case .usage(let message): return "usage: \(message)"
    case .targetNotFound(let message): return "target-not-found: \(message)"
    case .targetAmbiguous(let message): return "target-ambiguous: \(message)"
    case .accessibilityNotTrusted:
      return "accessibility-not-trusted: grant Accessibility access to this probe"
    case .targetNotActive: return "target-not-active: pass --activate before --keys"
    case .noAccessibleWindow: return "no-accessible-window: keep the headed shell frontmost"
    case .cannotPostKeys: return "cannot-post-keys: CGEvent creation failed"
    }
  }
}

private struct Options {
  var pid: Int32?
  var bundleId: String?
  var name: String?
  var runId = "native-semantic"
  var keys: [String] = []
  var activate = false
  var json = false
  var help = false
}

private func printHelp() {
  print("""
  Usage: native-semantic-evidence (--pid PID | --bundle-id ID | --name NAME) [options]

  Options:
    --pid PID             Exact target process (preferred for scratch shells)
    --bundle-id ID        Resolve one running application by bundle identifier
    --name NAME            Resolve one running application by process name
    --run-id ID             Stable evidence identifier (default: native-semantic)
    --keys SPEC             Comma-separated keys, e.g. cmd+k,escape
    --activate              Activate/raise the target before posting keys
    --json                  Emit one JSON evidence document
    --help                  Show this help

  Keys: cmd+k, ctrl+k, shift+enter, enter, escape, tab, shift+tab,
        arrow-up, arrow-down, arrow-left, arrow-right

  The target must be a headed native shell. This probe observes AXUIElement
  roles/titles/focus and posts native CGEvents; it does not take screenshots or
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
    default:
      throw ProbeError.usage("unknown option \(argument)")
    }
  }
  if options.help { return options }
  let selectors = [options.pid != nil, options.bundleId != nil, options.name != nil].filter { $0 }.count
  guard selectors == 1 else { throw ProbeError.usage("provide exactly one of --pid, --bundle-id, or --name") }
  if !options.keys.isEmpty && !options.activate {
    throw ProbeError.usage("--keys requires --activate")
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

private func node(_ element: AXUIElement?) -> AXNode? {
  guard let element else { return nil }
  return AXNode(
    role: stringAttribute(element, kAXRoleAttribute),
    subrole: stringAttribute(element, kAXSubroleAttribute),
    title: stringAttribute(element, kAXTitleAttribute),
    description: stringAttribute(element, kAXDescriptionAttribute),
    identifier: stringAttribute(element, kAXIdentifierAttribute),
    value: stringAttribute(element, kAXValueAttribute),
    enabled: boolAttribute(element, kAXEnabledAttribute)
  )
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
  elementArrayAttribute(application, kAXWindowsAttribute).compactMap { window in
    let role = stringAttribute(window, kAXRoleAttribute)
    // Some macOS releases include the application element in AXWindows. Never
    // report it as a window; doing so would turn an inactive shell into a false
    // native-window success.
    guard role == kAXWindowRole else { return nil }
    return WindowObservation(
      role: role,
      title: stringAttribute(window, kAXTitleAttribute),
      identifier: stringAttribute(window, kAXIdentifierAttribute))
  }
}

private func focusedElement(_ application: AXUIElement, windows: [AXUIElement]) -> AXUIElement? {
  if let element = elementAttribute(application, kAXFocusedUIElementAttribute) { return element }
  for window in windows {
    if let element = elementAttribute(window, kAXFocusedUIElementAttribute) { return element }
  }
  return nil
}

private func sameFocus(_ first: AXNode?, _ second: AXNode?) -> Bool {
  guard let first, let second else { return false }
  // Values and enabled state can legitimately change while a command palette
  // opens and closes. Focus restoration is an identity assertion, not a stale
  // value snapshot.
  return first.focusIdentity == second.focusIdentity
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
    targetName: app?.localizedName,
    targetBundleId: app?.bundleIdentifier,
    axTrusted: AXIsProcessTrusted(),
    windows: [],
    focusedBefore: nil,
    keys: [],
    focusRestored: nil,
    error: String(describing: error))
}

private func resolveTarget(_ options: Options) throws -> NSRunningApplication {
  if let pid = options.pid {
    guard let app = NSRunningApplication(processIdentifier: pid) else {
      throw ProbeError.targetNotFound("pid \(pid) is not running")
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
  return candidates[0]
}

private func run(_ options: Options) throws -> Evidence {
  guard AXIsProcessTrusted() else {
    throw ProbeError.accessibilityNotTrusted
  }
  let app = try resolveTarget(options)
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
  let beforeElement = focusedElement(application, windows: axWindows)
  let before = node(beforeElement)
  var observations: [KeyObservation] = []
  for rawKey in options.keys {
    guard let spec = keySpec(rawKey) else { throw ProbeError.usage("unknown key \(rawKey)") }
    let keyBefore = node(focusedElement(application, windows: axWindows))
    try post(spec)
    let keyAfter = node(focusedElement(application, windows: axWindows))
    observations.append(KeyObservation(
      key: spec.label,
      keyCode: spec.keyCode,
      modifiers: spec.modifierLabels,
      posted: true,
      focusedBefore: keyBefore,
      focusedAfter: keyAfter))
  }
  let after = node(focusedElement(application, windows: axWindows))
  let restored = options.keys.isEmpty ? nil : sameFocus(before, after)
  return Evidence(
    schema: schema,
    shell: "macos",
    runId: options.runId,
    targetPid: app.processIdentifier,
    targetName: app.localizedName,
    targetBundleId: app.bundleIdentifier,
    axTrusted: true,
    windows: windows,
    focusedBefore: before,
    keys: observations,
    focusRestored: restored,
    error: nil)
}

let arguments = Array(CommandLine.arguments.dropFirst())
do {
  let options = try parseOptions(arguments)
  if options.help {
    printHelp()
    exit(0)
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
