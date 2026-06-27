import AppKit
import ApplicationServices
import Foundation

@MainActor
enum CloudConnectorFormAutomation {
  private struct FieldValue {
    let label: String
    let value: String
    let optional: Bool
    let aliases: [String]
  }

  private struct AccessibleNode {
    let element: AXUIElement
    let role: String
    let title: String
    let value: String
    let placeholder: String
    let description: String
    let help: String
    let frame: CGRect

    var searchableText: String {
      [role, title, value, placeholder, description, help]
        .filter { !$0.isEmpty }
        .joined(separator: " ")
        .lowercased()
    }
  }

  private enum ClaudeConnectorPageState: Equatable {
    case addCustomConnectorModal
    case connectorDetail
    case other
  }

  static func fill(_ args: [String: Any]) async -> String {
    let provider = ((args["provider"] as? String) ?? "").lowercased()
    guard provider == "claude" || provider == "chatgpt" else {
      return "Error: provider must be 'claude' or 'chatgpt'."
    }

    guard let serverURL = nonEmptyString(args["server_url"]) else {
      return "Error: server_url is required."
    }

    let connectorName = nonEmptyString(args["name"]) ?? "Omi Memory"
    let clientID = nonEmptyString(args["oauth_client_id"]) ?? "omi"
    let clientSecret = nonEmptyString(args["oauth_client_secret"])
    let submit = (args["submit"] as? Bool) ?? false

    var values = [
      FieldValue(
        label: "Name",
        value: connectorName,
        optional: false,
        aliases: ["name", "connector name", "app name"]),
      FieldValue(
        label: "Remote MCP server URL",
        value: serverURL,
        optional: false,
        aliases: ["remote mcp server url", "mcp server url", "server url", "url"]),
      FieldValue(
        label: "OAuth Client ID",
        value: clientID,
        optional: provider == "chatgpt",
        aliases: ["oauth client id", "client id"]),
    ]

    if let clientSecret {
      values.append(
        FieldValue(
          label: "OAuth Client Secret",
          value: clientSecret,
          optional: provider == "chatgpt",
          aliases: ["oauth client secret", "client secret"]))
    }

    if provider == "chatgpt" {
      values.append(contentsOf: [
        FieldValue(
          label: "Authentication",
          value: nonEmptyString(args["authentication"]) ?? "OAuth",
          optional: true,
          aliases: ["authentication", "auth type"]),
        FieldValue(
          label: "Token auth method",
          value: nonEmptyString(args["token_auth_method"]) ?? "client_secret_post",
          optional: true,
          aliases: ["token auth method", "token authentication method"]),
      ])
      if let authURL = nonEmptyString(args["auth_url"]) {
        values.append(
          FieldValue(
            label: "Auth URL",
            value: authURL,
            optional: true,
            aliases: ["auth url", "authorization url", "authorize url"]))
      }
      if let tokenURL = nonEmptyString(args["token_url"]) {
        values.append(
          FieldValue(
            label: "Token URL",
            value: tokenURL,
            optional: true,
            aliases: ["token url"]))
      }
    }

    guard accessibilityLooksUsable() else {
      return
        "Error: Accessibility permission is not available to Omi, so the native connector form filler cannot inspect browser fields."
    }

    guard let form = findBestForm(provider: provider, values: values) else {
      if let result = await fillClaudeConnectorByKeyboard(
        provider: provider,
        values: values,
        submit: submit)
      {
        return result
      }
      return
        "Error: Could not find a visible \(provider) custom connector form. Open the add connector modal in the signed-in browser, then call this tool again."
    }

    if needsAdvancedSettings(values: values, nodes: form.nodes),
      let disclosure = findActionNode(
        in: form.nodes,
        matching: ["advanced settings", "advanced"])
    {
      _ = AXUIElementPerformAction(disclosure.element, kAXPressAction as CFString)
      try? await Task.sleep(nanoseconds: 400_000_000)
    }

    let refreshedNodes = collectNodes(from: form.root, maxDepth: 12, maxNodes: 700)
    let fields = refreshedNodes
      .filter { isInputField($0) }
      .sorted(by: visualOrder)
    var usedElementIDs = Set<ObjectIdentifier>()
    var filled: [String] = []
    var missing: [String] = []

    for value in values {
      if let match = findField(for: value, in: fields, usedElementIDs: usedElementIDs)
        ?? fallbackField(for: value, in: fields, usedElementIDs: usedElementIDs, provider: provider)
      {
        usedElementIDs.insert(ObjectIdentifier(match.element))
        if setField(match.element, to: value.value) {
          filled.append(value.label)
        } else if value.optional {
          missing.append("\(value.label) (optional, set failed)")
        } else {
          missing.append("\(value.label) (set failed)")
        }
      } else if !value.optional {
        missing.append(value.label)
      }
    }

    if !missing.isEmpty,
      let result = await fillClaudeConnectorByKeyboard(
        provider: provider,
        values: values,
        submit: submit)
    {
      return result
    }

    var pressedButton: String?
    if submit && missing.isEmpty {
      let submitNodes = collectNodes(from: form.root, maxDepth: 12, maxNodes: 700)
      if let button = findActionNode(
        in: submitNodes,
        matching: ["add", "connect", "create", "save"])
      {
        _ = AXUIElementPerformAction(button.element, kAXPressAction as CFString)
        pressedButton = bestLabel(for: button)
      }
    }

    var lines = [
      "Native connector form filler result:",
      "Provider: \(provider)",
      "Browser/app: \(form.app.localizedName ?? form.app.bundleIdentifier ?? "unknown")",
      "Filled: \(filled.isEmpty ? "none" : filled.joined(separator: ", "))",
    ]
    if !missing.isEmpty {
      lines.append("Missing: \(missing.joined(separator: ", "))")
    }
    if let pressedButton {
      lines.append("Submitted with button: \(pressedButton)")
    } else {
      lines.append(submit ? "Submit skipped: no enabled Add/Connect button found." : "Submit skipped by request.")
    }
    return lines.joined(separator: "\n")
  }

  private static func fillClaudeConnectorByKeyboard(
    provider: String,
    values: [FieldValue],
    submit: Bool
  ) async -> String? {
    guard provider == "claude" else { return nil }
    guard let target = findClaudeConnectorKeyboardTarget(expectedState: .addCustomConnectorModal) else {
      return nil
    }
    guard let name = values.first(where: { $0.label == "Name" })?.value,
      let serverURL = values.first(where: { $0.label == "Remote MCP server URL" })?.value,
      let clientID = values.first(where: { $0.label == "OAuth Client ID" })?.value,
      let clientSecret = values.first(where: { $0.label == "OAuth Client Secret" })?.value
    else { return nil }

    target.app.activate()
    try? await Task.sleep(nanoseconds: 450_000_000)
    guard let active = NSWorkspace.shared.frontmostApplication,
      active.processIdentifier == target.app.processIdentifier,
      let activeTarget = frontmostClaudeConnectorKeyboardTarget(),
      activeTarget.state == .addCustomConnectorModal
    else {
      return
        "Error: Refusing keyboard fallback because the active window is not Claude's add custom connector modal."
    }

    // Claude's modal currently focuses the close button when opened. Atlas does
    // not expose the page fields through AX, so use the modal's stable tab order.
    pressTab(count: 3)
    pasteIntoFocusedField(name)
    pressTab(count: 1)
    pasteIntoFocusedField(serverURL)
    pressTab(count: 2)
    pasteIntoFocusedField(clientID)
    pressTab(count: 1)
    pasteIntoFocusedField(clientSecret)

    var lines = [
      "Native connector form filler result:",
      "Provider: claude",
      "Browser/app: \(target.app.localizedName ?? target.app.bundleIdentifier ?? "unknown")",
      "Filled: Name, Remote MCP server URL, OAuth Client ID, OAuth Client Secret",
      "Method: keyboard fallback",
    ]

    if submit {
      pressTab(count: 2)
      sendKey(49)
      lines.append("Submitted with button: Add (keyboard fallback)")
    } else {
      lines.append("Submit skipped by request.")
    }

    return lines.joined(separator: "\n")
  }

  private static func nonEmptyString(_ value: Any?) -> String? {
    guard let string = value as? String else { return nil }
    let trimmed = string.trimmingCharacters(in: .whitespacesAndNewlines)
    return trimmed.isEmpty ? nil : trimmed
  }

  private static func accessibilityLooksUsable() -> Bool {
    AXIsProcessTrusted()
  }

  private static func findBestForm(
    provider: String,
    values: [FieldValue]
  ) -> (app: NSRunningApplication, root: AXUIElement, nodes: [AccessibleNode])? {
    let ownBundleID = Bundle.main.bundleIdentifier
    var candidates: [NSRunningApplication] = []
    if let frontmost = NSWorkspace.shared.frontmostApplication {
      candidates.append(frontmost)
    }
    candidates.append(contentsOf: NSWorkspace.shared.runningApplications.filter { app in
      guard app.bundleIdentifier != ownBundleID else { return false }
      let name = (app.localizedName ?? app.bundleIdentifier ?? "").lowercased()
      return name.contains("chrome")
        || name.contains("atlas")
        || name.contains("brave")
        || name.contains("edge")
        || name.contains("arc")
        || name.contains("opera")
        || name.contains("vivaldi")
        || name.contains("chromium")
    })
    candidates.append(contentsOf: NSWorkspace.shared.runningApplications.filter { app in
      app.activationPolicy == .regular && app.bundleIdentifier != ownBundleID
    })

    var seen = Set<pid_t>()
    for app in candidates where !seen.contains(app.processIdentifier) {
      seen.insert(app.processIdentifier)
      let appElement = AXUIElementCreateApplication(app.processIdentifier)
      let roots = focusedAndWindowRoots(for: appElement)
      for root in roots {
        let nodes = collectNodes(from: root, maxDepth: 12, maxNodes: 700)
        if formScore(provider: provider, values: values, nodes: nodes) >= 3 {
          return (app, root, nodes)
        }
      }
    }
    return nil
  }

  private static func focusedAndWindowRoots(for appElement: AXUIElement) -> [AXUIElement] {
    var roots: [AXUIElement] = []
    if let focused = elementAttribute(appElement, "AXFocusedWindow") {
      roots.append(focused)
    }
    for window in elementArrayAttribute(appElement, "AXWindows") {
      roots.append(window)
    }
    return roots
  }

  private static func formScore(
    provider: String,
    values: [FieldValue],
    nodes: [AccessibleNode]
  ) -> Int {
    let allText = nodes.map(\.searchableText).joined(separator: " ")
    var score = 0
    if allText.contains("custom connector") { score += 2 }
    if allText.contains("mcp") { score += 1 }
    if provider == "claude" && allText.contains("claude") { score += 1 }
    if provider == "chatgpt" && (allText.contains("chatgpt") || allText.contains("connector")) {
      score += 1
    }
    for value in values where value.aliases.contains(where: { allText.contains($0) }) {
      score += 1
    }
    return score
  }

  private static func needsAdvancedSettings(values: [FieldValue], nodes: [AccessibleNode]) -> Bool {
    let text = nodes.map(\.searchableText).joined(separator: " ")
    return values.contains { $0.label.lowercased().contains("oauth") }
      && !text.contains("oauth client")
      && text.contains("advanced")
  }

  private static func collectNodes(
    from root: AXUIElement,
    maxDepth: Int,
    maxNodes: Int
  ) -> [AccessibleNode] {
    var output: [AccessibleNode] = []
    var seen = Set<ObjectIdentifier>()

    func walk(_ element: AXUIElement, depth: Int) {
      guard depth <= maxDepth, output.count < maxNodes else { return }
      let id = ObjectIdentifier(element)
      guard !seen.contains(id) else { return }
      seen.insert(id)

      output.append(node(from: element))
      for child in elementArrayAttribute(element, "AXChildren") {
        walk(child, depth: depth + 1)
      }
      for child in elementArrayAttribute(element, "AXVisibleChildren") {
        walk(child, depth: depth + 1)
      }
    }

    walk(root, depth: 0)
    return output
  }

  private static func node(from element: AXUIElement) -> AccessibleNode {
    AccessibleNode(
      element: element,
      role: stringAttribute(element, "AXRole"),
      title: stringAttribute(element, "AXTitle"),
      value: stringAttribute(element, "AXValue"),
      placeholder: stringAttribute(element, "AXPlaceholderValue"),
      description: stringAttribute(element, "AXDescription"),
      help: stringAttribute(element, "AXHelp"),
      frame: frameAttribute(element)
    )
  }

  private static func isInputField(_ node: AccessibleNode) -> Bool {
    let role = node.role.lowercased()
    return role.contains("textfield") || role.contains("textarea") || role.contains("combobox")
  }

  private static func findField(
    for value: FieldValue,
    in fields: [AccessibleNode],
    usedElementIDs: Set<ObjectIdentifier>
  ) -> AccessibleNode? {
    fields.first { field in
      !usedElementIDs.contains(ObjectIdentifier(field.element))
        && value.aliases.contains { alias in
          field.searchableText.contains(alias.lowercased())
        }
    }
  }

  private static func fallbackField(
    for value: FieldValue,
    in fields: [AccessibleNode],
    usedElementIDs: Set<ObjectIdentifier>,
    provider: String
  ) -> AccessibleNode? {
    let fallbackOrder: [String]
    if provider == "claude" {
      fallbackOrder = ["Name", "Remote MCP server URL", "OAuth Client ID", "OAuth Client Secret"]
    } else {
      fallbackOrder = [
        "Name",
        "Remote MCP server URL",
        "Authentication",
        "OAuth Client ID",
        "OAuth Client Secret",
        "Token auth method",
        "Auth URL",
        "Token URL",
      ]
    }
    guard let index = fallbackOrder.firstIndex(of: value.label) else { return nil }
    let available = fields.filter { !usedElementIDs.contains(ObjectIdentifier($0.element)) }
    guard index < available.count else { return nil }
    return available[index]
  }

  private static func findClaudeConnectorKeyboardTarget(
    expectedState: ClaudeConnectorPageState
  ) -> (app: NSRunningApplication, state: ClaudeConnectorPageState)? {
    let ownBundleID = Bundle.main.bundleIdentifier
    let browserApps = NSWorkspace.shared.runningApplications.filter { app in
      app.bundleIdentifier != ownBundleID && isSupportedBrowserApp(app)
    }

    let frontmost = NSWorkspace.shared.frontmostApplication
    let candidates = ([frontmost].compactMap { $0 } + browserApps).uniquedByPID()
    for app in candidates {
      let appElement = AXUIElementCreateApplication(app.processIdentifier)
      for root in focusedAndWindowRoots(for: appElement) {
        let nodes = collectNodes(from: root, maxDepth: 10, maxNodes: 500)
        let state = claudeConnectorPageState(nodes: nodes)
        if state == expectedState {
          return (app, state)
        }
      }
    }
    return nil
  }

  private static func frontmostClaudeConnectorKeyboardTarget() -> (
    app: NSRunningApplication, state: ClaudeConnectorPageState
  )? {
    guard let app = NSWorkspace.shared.frontmostApplication,
      isSupportedBrowserApp(app)
    else { return nil }

    let appElement = AXUIElementCreateApplication(app.processIdentifier)
    for root in focusedAndWindowRoots(for: appElement) {
      let nodes = collectNodes(from: root, maxDepth: 10, maxNodes: 500)
      let state = claudeConnectorPageState(nodes: nodes)
      if state != .other {
        return (app, state)
      }
    }
    return nil
  }

  private static func claudeConnectorPageState(nodes: [AccessibleNode]) -> ClaudeConnectorPageState {
    let text = nodes.map(\.searchableText).joined(separator: " ")
    guard text.contains("claude.ai/customize/connectors") else { return .other }

    if text.contains("modal=add-custom-connector")
      || text.contains("add custom connector")
    {
      return .addCustomConnectorModal
    }

    if text.contains("you are not connected to omi yet")
      || text.contains("not connected to omi")
    {
      return .connectorDetail
    }

    return .other
  }

  private static func isSupportedBrowserApp(_ app: NSRunningApplication) -> Bool {
    let name = (app.localizedName ?? app.bundleIdentifier ?? "").lowercased()
    return name.contains("chrome")
      || name.contains("atlas")
      || name.contains("brave")
      || name.contains("edge")
      || name.contains("arc")
      || name.contains("opera")
      || name.contains("vivaldi")
      || name.contains("chromium")
  }

  private static func setField(_ element: AXUIElement, to value: String) -> Bool {
    if AXUIElementSetAttributeValue(element, "AXValue" as CFString, value as CFTypeRef) == .success {
      return true
    }
    _ = AXUIElementSetAttributeValue(element, "AXFocused" as CFString, kCFBooleanTrue)
    Thread.sleep(forTimeInterval: 0.08)
    NSPasteboard.general.clearContents()
    NSPasteboard.general.setString(value, forType: .string)
    sendKey(0, flags: .maskCommand)
    sendKey(9, flags: .maskCommand)
    return true
  }

  private static func pasteIntoFocusedField(_ value: String) {
    NSPasteboard.general.clearContents()
    NSPasteboard.general.setString(value, forType: .string)
    sendKey(0, flags: .maskCommand)
    Thread.sleep(forTimeInterval: 0.08)
    sendKey(9, flags: .maskCommand)
    Thread.sleep(forTimeInterval: 0.12)
  }

  private static func pressTab(count: Int) {
    guard count > 0 else { return }
    for _ in 0..<count {
      sendKey(48)
      Thread.sleep(forTimeInterval: 0.12)
    }
  }

  private static func findActionNode(
    in nodes: [AccessibleNode],
    matching labels: [String]
  ) -> AccessibleNode? {
    nodes.first { node in
      node.role.lowercased().contains("button")
        && labels.contains { label in bestLabel(for: node).lowercased().contains(label) }
    }
  }

  private static func bestLabel(for node: AccessibleNode) -> String {
    if !node.title.isEmpty { return node.title }
    if !node.description.isEmpty { return node.description }
    if !node.value.isEmpty { return node.value }
    return node.help
  }

  private static func visualOrder(_ lhs: AccessibleNode, _ rhs: AccessibleNode) -> Bool {
    if abs(lhs.frame.minY - rhs.frame.minY) > 8 {
      return lhs.frame.minY < rhs.frame.minY
    }
    return lhs.frame.minX < rhs.frame.minX
  }

  private static func sendKey(_ keyCode: CGKeyCode, flags: CGEventFlags = []) {
    let source = CGEventSource(stateID: .hidSystemState)
    let down = CGEvent(keyboardEventSource: source, virtualKey: keyCode, keyDown: true)
    down?.flags = flags
    down?.post(tap: .cghidEventTap)
    let up = CGEvent(keyboardEventSource: source, virtualKey: keyCode, keyDown: false)
    up?.flags = flags
    up?.post(tap: .cghidEventTap)
  }

  private static func stringAttribute(_ element: AXUIElement, _ attribute: String) -> String {
    var raw: CFTypeRef?
    guard AXUIElementCopyAttributeValue(element, attribute as CFString, &raw) == .success else {
      return ""
    }
    if let string = raw as? String { return string }
    if let attributed = raw as? NSAttributedString { return attributed.string }
    return ""
  }

  private static func elementAttribute(_ element: AXUIElement, _ attribute: String) -> AXUIElement? {
    var raw: CFTypeRef?
    guard AXUIElementCopyAttributeValue(element, attribute as CFString, &raw) == .success else {
      return nil
    }
    return ((raw as AnyObject) as! AXUIElement)
  }

  private static func elementArrayAttribute(
    _ element: AXUIElement,
    _ attribute: String
  ) -> [AXUIElement] {
    var raw: CFTypeRef?
    guard AXUIElementCopyAttributeValue(element, attribute as CFString, &raw) == .success else {
      return []
    }
    return (raw as? [AnyObject])?.map { $0 as! AXUIElement } ?? []
  }

  private static func frameAttribute(_ element: AXUIElement) -> CGRect {
    var point = CGPoint.zero
    var size = CGSize.zero
    if let pointValue = rawAttribute(element, "AXPosition") {
      let pointValue = pointValue as! AXValue
      AXValueGetValue(pointValue, .cgPoint, &point)
    }
    if let sizeValue = rawAttribute(element, "AXSize") {
      let sizeValue = sizeValue as! AXValue
      AXValueGetValue(sizeValue, .cgSize, &size)
    }
    return CGRect(origin: point, size: size)
  }

  private static func rawAttribute(_ element: AXUIElement, _ attribute: String) -> CFTypeRef? {
    var raw: CFTypeRef?
    guard AXUIElementCopyAttributeValue(element, attribute as CFString, &raw) == .success else {
      return nil
    }
    return raw
  }
}

private extension Array where Element == NSRunningApplication {
  func uniquedByPID() -> [NSRunningApplication] {
    var seen = Set<pid_t>()
    var output: [NSRunningApplication] = []
    for app in self where !seen.contains(app.processIdentifier) {
      seen.insert(app.processIdentifier)
      output.append(app)
    }
    return output
  }
}
