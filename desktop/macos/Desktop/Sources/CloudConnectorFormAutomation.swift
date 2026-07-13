import AppKit
import ApplicationServices
import Foundation
import Vision

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

  private struct PasteboardSnapshot {
    let string: String?

    static func capture() -> PasteboardSnapshot {
      PasteboardSnapshot(string: NSPasteboard.general.string(forType: .string))
    }

    func restore() {
      NSPasteboard.general.clearContents()
      if let string {
        NSPasteboard.general.setString(string, forType: .string)
      }
    }
  }

  struct OCRTextCandidate: Equatable {
    let text: String
    let confidence: Double
    let imageRect: CGRect
  }

  enum ClaudeConnectorPageState: Equatable {
    case addCustomConnectorModal
    case connectorDetailNotConnected
    case connectorDetailConnected
    case other
  }

  enum ClaudeConnectorAction: Equatable {
    case fillAddModal
    case pressConnect
    case alreadyConnected
    case refuse
  }

  static func fill(
    _ args: [String: Any],
    expectedOwnerID: String? = nil
  ) async -> String {
    guard ChatToolExecutor.isExpectedOwnerCurrent(expectedOwnerID) else {
      return ChatToolExecutor.authorizedOwnerChangedResult()
    }
    let provider = ((args["provider"] as? String) ?? "").lowercased()
    guard provider == "claude" || provider == "chatgpt" else {
      return "Error: provider must be 'claude' or 'chatgpt'."
    }

    guard let serverURL = nonEmptyString(args["server_url"]) else {
      return "Error: server_url is required."
    }

    let connectorName = nonEmptyString(args["name"]) ?? "Omi Memory"
    let clientID = nonEmptyString(args["oauth_client_id"]) ?? defaultOAuthClientID(for: provider)
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
          value:
            nonEmptyString(args["token_auth_method"])
            ?? (clientSecret == nil ? "none" : "client_secret_post"),
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

    if provider == "claude" {
      if let result = await advanceClaudeConnectorStateMachine(
        provider: provider,
        values: values,
        submit: submit,
        expectedOwnerID: expectedOwnerID)
      {
        return result
      }
      return
        "Error: Could not find a visible \(provider) custom connector form. Open the add connector modal in the signed-in browser, then call this tool again."
    }

    guard let form = findBestForm(provider: provider, values: values) else {
      if let result = await advanceClaudeConnectorStateMachine(
        provider: provider,
        values: values,
        submit: submit,
        expectedOwnerID: expectedOwnerID)
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
      guard ChatToolExecutor.isExpectedOwnerCurrent(expectedOwnerID) else {
        return ChatToolExecutor.authorizedOwnerChangedResult()
      }
      _ = AXUIElementPerformAction(disclosure.element, kAXPressAction as CFString)
      try? await Task.sleep(nanoseconds: 400_000_000)
      guard ChatToolExecutor.isExpectedOwnerCurrent(expectedOwnerID) else {
        return ChatToolExecutor.authorizedOwnerChangedResult()
      }
    }

    let refreshedNodes = collectNodes(from: form.root, maxDepth: 12, maxNodes: 700)
    let fields =
      refreshedNodes
      .filter { isInputField($0) }
      .sorted(by: visualOrder)
    var usedElementIDs = Set<ObjectIdentifier>()
    var filled: [String] = []
    var missing: [String] = []

    for value in values {
      guard ChatToolExecutor.isExpectedOwnerCurrent(expectedOwnerID) else {
        return ChatToolExecutor.authorizedOwnerChangedResult()
      }
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
      let result = await advanceClaudeConnectorStateMachine(
        provider: provider,
        values: values,
        submit: submit,
        expectedOwnerID: expectedOwnerID)
    {
      return result
    }

    var pressedButton: String?
    if submit && missing.isEmpty {
      guard ChatToolExecutor.isExpectedOwnerCurrent(expectedOwnerID) else {
        return ChatToolExecutor.authorizedOwnerChangedResult()
      }
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
      lines.append(
        submit
          ? "Submit skipped: no enabled Add/Connect button found." : "Submit skipped by request.")
    }
    return lines.joined(separator: "\n")
  }

  private static func advanceClaudeConnectorStateMachine(
    provider: String,
    values: [FieldValue],
    submit: Bool,
    expectedOwnerID: String?
  ) async -> String? {
    guard ChatToolExecutor.isExpectedOwnerCurrent(expectedOwnerID) else {
      return ChatToolExecutor.authorizedOwnerChangedResult()
    }
    guard provider == "claude" else { return nil }
    guard let target = findClaudeConnectorTargetWithNodes().map({ (app: $0.app, state: $0.state) })
    else {
      return nil
    }

    switch claudeConnectorAction(for: target.state, submit: submit) {
    case .fillAddModal:
      return await fillClaudeConnectorAddModalByKeyboard(
        target: target,
        values: values,
        submit: submit,
        expectedOwnerID: expectedOwnerID)
    case .pressConnect:
      return await pressClaudeConnectorConnectButton(
        target: target,
        expectedOwnerID: expectedOwnerID)
    case .alreadyConnected:
      return [
        "Native connector form filler result:",
        "Provider: claude",
        "Browser/app: \(target.app.localizedName ?? target.app.bundleIdentifier ?? "unknown")",
        "Claude connector connected.",
      ].joined(separator: "\n")
    case .refuse:
      return nil
    }
  }

  nonisolated static func claudeConnectorAction(
    for state: ClaudeConnectorPageState,
    submit: Bool
  ) -> ClaudeConnectorAction {
    switch state {
    case .addCustomConnectorModal:
      return .fillAddModal
    case .connectorDetailNotConnected:
      return submit ? .pressConnect : .refuse
    case .connectorDetailConnected:
      return .alreadyConnected
    case .other:
      return .refuse
    }
  }

  static func showClaudeConnectGuidanceOverlay() -> Bool {
    guard let target = findClaudeConnectorTargetWithNodes(),
      target.state == .connectorDetailNotConnected,
      let rawWindowFrame = largestWindowFrame(in: target.nodes),
      let screen = SpatialOverlayGeometry.screenForTopLeftFrame(rawWindowFrame)
    else {
      return false
    }
    let windowFrame = SpatialOverlayGeometry.globalAppKitFrame(topLeftFrame: rawWindowFrame)

    target.app.activate()
    CloudConnectorGuidanceOverlay.shared.presentClaudeConnectHint(
      windowFrame: windowFrame,
      candidates: claudeConnectGuidanceCandidates(
        windowFrame: windowFrame,
        nodes: target.nodes,
        screen: screen
      )
    )
    return true
  }

  static func showClaudeAddGuidanceOverlay() -> Bool {
    guard let target = findClaudeConnectorTargetWithNodes(),
      target.state == .addCustomConnectorModal,
      let rawWindowFrame = largestWindowFrame(in: target.nodes),
      let screen = SpatialOverlayGeometry.screenForTopLeftFrame(rawWindowFrame)
    else {
      return false
    }
    let windowFrame = SpatialOverlayGeometry.globalAppKitFrame(topLeftFrame: rawWindowFrame)

    let candidates = claudeAddGuidanceCandidates(
      windowFrame: windowFrame,
      windowTopLeftFrame: rawWindowFrame,
      nodes: target.nodes,
      screen: screen
    )

    target.app.activate()
    guard !candidates.isEmpty else {
      CloudConnectorGuidanceOverlay.shared.presentInstructionCard(
        title: "Finish in Claude",
        subtitle: "Click Add in the connector window to finish creating the Omi connector.",
        near: windowFrame
      )
      return true
    }

    CloudConnectorGuidanceOverlay.shared.presentClaudeAddHint(
      windowFrame: windowFrame,
      candidates: candidates
    )
    return true
  }

  static func dismissGuidanceOverlay() {
    CloudConnectorGuidanceOverlay.shared.dismiss()
  }

  /// Fallback guidance shown when we cannot anchor to Claude's Add button and must send
  /// the user to System Settings to grant Screen Recording. We never leave them staring
  /// at a bare settings pane: an instruction card explains what to enable and where to
  /// return. Placed near the System Settings window so the two read as one step.
  static func showScreenRecordingSettingsInstructionOverlay(actionLabel: String = "Add") async {
    let appName =
      (Bundle.main.infoDictionary?["CFBundleName"] as? String)
      ?? (Bundle.main.infoDictionary?["CFBundleDisplayName"] as? String)
      ?? "Omi"
    var anchor: CGRect?
    for _ in 0..<12 {
      if let frame = systemSettingsWindowAppKitFrame() {
        anchor = frame
        break
      }
      try? await Task.sleep(nanoseconds: 200_000_000)
    }
    CloudConnectorGuidanceOverlay.shared.presentInstructionCard(
      title: "Allow Screen Recording for \(appName)",
      subtitle:
        "Flip the \(appName) toggle on under Screen & System Audio Recording, then return to Claude and click \(actionLabel).",
      near: anchor
    )
  }

  private static func systemSettingsWindowAppKitFrame() -> CGRect? {
    guard
      let app = NSWorkspace.shared.runningApplications.first(where: {
        $0.bundleIdentifier == "com.apple.systempreferences"
      })
    else { return nil }
    let appElement = AXUIElementCreateApplication(app.processIdentifier)
    var windowElement: AXUIElement?
    var focused: CFTypeRef?
    if AXUIElementCopyAttributeValue(appElement, "AXFocusedWindow" as CFString, &focused)
      == .success,
      let focused
    {
      windowElement = (focused as! AXUIElement)
    } else {
      var windowsRef: CFTypeRef?
      if AXUIElementCopyAttributeValue(appElement, "AXWindows" as CFString, &windowsRef)
        == .success,
        let windows = windowsRef as? [AXUIElement], let first = windows.first
      {
        windowElement = first
      }
    }
    guard let windowElement else { return nil }
    let topLeft = frameAttribute(windowElement)
    guard !topLeft.isNull, !topLeft.isEmpty else { return nil }
    return SpatialOverlayGeometry.globalAppKitFrame(topLeftFrame: topLeft)
  }

  /// Read-only diagnostic: runs the real Claude detection (no overlay, no clicks) and
  /// reports what the accessibility tree actually exposes, so we can see whether the
  /// Add/Cancel buttons are even found before guessing a position.
  static func claudeAddGuidanceDiagnostics() -> [String: String] {
    guard let target = findClaudeConnectorTargetWithNodes() else {
      return ["found": "false", "reason": "no-claude-connector-target"]
    }
    func rectStr(_ r: CGRect) -> String {
      "\(Int(r.minX)),\(Int(r.minY)),\(Int(r.width)),\(Int(r.height))"
    }
    var out: [String: String] = [
      "found": "true",
      "state": "\(target.state)",
      "app": target.app.localizedName ?? target.app.bundleIdentifier ?? "?",
      "nodeCount": "\(target.nodes.count)",
    ]
    let buttons = target.nodes.filter { $0.role.lowercased().contains("button") }
    out["buttonCount"] = "\(buttons.count)"
    out["buttonLabels"] =
      buttons
      .map { bestLabel(for: $0).trimmingCharacters(in: .whitespacesAndNewlines) }
      .filter { !$0.isEmpty }
      .prefix(50)
      .joined(separator: " | ")
    if let raw = largestWindowFrame(in: target.nodes) {
      out["rawWindowFrameTopLeft"] = rectStr(raw)
    }
    let add = findActionNode(in: target.nodes, matching: ["add"])
    let cancel = findActionNode(in: target.nodes, matching: ["cancel"])
    if let add {
      out["addNodeTopLeft"] = rectStr(add.frame)
      out["addNodeLabel"] = bestLabel(for: add)
    } else {
      out["addNode"] = "nil"
    }
    if let cancel {
      out["cancelNodeTopLeft"] = rectStr(cancel.frame)
      out["cancelNodeLabel"] = bestLabel(for: cancel)
    } else {
      out["cancelNode"] = "nil"
    }
    let windowTopLeft = largestWindowFrame(in: target.nodes) ?? .null
    let modalRect = locatedClaudeModalRect(in: target.nodes, within: windowTopLeft)
    out["locatedModalRect"] = modalRect.map(rectStr) ?? "nil"
    // Which guidance path the live overlay would take.
    out["chosenPath"] =
      add != nil
      ? "explicit-add"
      : cancel != nil ? "cancel-inference" : modalRect != nil ? "modal-footer" : "suppressed"
    return out
  }

  nonisolated static func claudeConnectGuidanceCandidates(
    windowFrame: CGRect,
    explicitTargetFrames: [CGRect]
  ) -> [SpatialOverlayAnchorCandidate] {
    guidanceCandidates(
      windowFrame: windowFrame,
      explicitTargetFrames: explicitTargetFrames,
      heuristicID: "claude-connect-heuristic",
      heuristicPoint: claudeConnectGuidanceAnchor(in: windowFrame),
      heuristicTargetSize: CGSize(width: 132, height: 54)
    )
  }

  nonisolated static func claudeAddGuidanceCandidates(
    windowFrame: CGRect,
    explicitTargetFrames: [CGRect]
  ) -> [SpatialOverlayAnchorCandidate] {
    guidanceCandidates(
      windowFrame: windowFrame,
      explicitTargetFrames: explicitTargetFrames,
      heuristicID: "claude-add-heuristic",
      heuristicPoint: claudeAddGuidanceAnchor(in: windowFrame),
      heuristicTargetSize: CGSize(width: 92, height: 54)
    )
  }

  private static func claudeConnectGuidanceCandidates(
    windowFrame: CGRect,
    nodes: [AccessibleNode],
    screen: SpatialOverlayScreen
  ) -> [SpatialOverlayAnchorCandidate] {
    let explicitFrames =
      findClaudeConnectorDetailConnectButton(in: nodes)
      .map { [SpatialOverlayGeometry.globalAppKitFrame(topLeftFrame: $0.frame)] }
      ?? []
    return claudeConnectGuidanceCandidates(
      windowFrame: windowFrame,
      explicitTargetFrames: explicitFrames
    )
  }

  /// Live Add-guidance candidates. Every candidate is anchored to an element we
  /// actually located in the accessibility tree — the Add button, the Cancel button, or
  /// the modal itself. We deliberately never fall back to a whole-window percentage
  /// guess: pointing confidently at an invented coordinate (which lands below the modal
  /// and covers the real button) is worse than not pointing. If nothing is located we
  /// return [] and the caller suppresses the overlay.
  private static func claudeAddGuidanceCandidates(
    windowFrame: CGRect,
    windowTopLeftFrame: CGRect,
    nodes: [AccessibleNode],
    screen: SpatialOverlayScreen
  ) -> [SpatialOverlayAnchorCandidate] {
    let overlayScreen = SpatialOverlayScreen(
      id: "claude-window", frame: windowFrame, visibleFrame: windowFrame)
    let window = SpatialOverlayWindow(
      id: "claude-window", frame: windowFrame, screenID: overlayScreen.id)

    // 1) Exact Add button exposed by accessibility — the ideal case.
    if let add = findActionNode(in: nodes, matching: ["add"]) {
      let rect = SpatialOverlayGeometry.globalAppKitFrame(topLeftFrame: add.frame)
      return [
        SpatialOverlayAnchorCandidate(
          id: "claude-add-explicit-0",
          targetRect: rect,
          screen: overlayScreen,
          window: window,
          evidence: [
            SpatialOverlayTargetEvidence(
              source: .accessibility, confidence: 0.95, label: "Claude Add button")
          ],
          confidence: 0.95,
          allowedUses: [.displayGuidance, .performClick])
      ]
    }

    // 2) Cancel is located but Add is not — infer Add to the right of Cancel.
    if let cancel = findActionNode(in: nodes, matching: ["cancel"]) {
      let rect = SpatialOverlayGeometry.globalAppKitFrame(
        topLeftFrame: inferredClaudeAddButtonFrameFromCancel(cancel.frame))
      return [
        SpatialOverlayAnchorCandidate(
          id: "claude-add-inferred-from-cancel",
          targetRect: rect,
          screen: overlayScreen,
          window: window,
          evidence: [
            SpatialOverlayTargetEvidence(
              source: .layoutHeuristic, confidence: 0.82,
              label: "Claude Add inferred from Cancel button",
              diagnostics: ["display-guidance-only", "inferred-from-cancel-button"])
          ],
          confidence: 0.82,
          allowedUses: [.displayGuidance])
      ]
    }

    // 3) Neither button is located, but the modal's form fields are. Point at the
    //    located modal's footer (where Add lives) instead of guessing against the window.
    if let modalTopLeft = locatedClaudeModalRect(in: nodes, within: windowTopLeftFrame),
      let footer = claudeAddFallbackFooterTarget(
        modalTopLeft: modalTopLeft,
        window: windowTopLeftFrame
      )
    {
      // Treat the located modal as a hard exclusion zone so the bubble is placed beside
      // it rather than on top of the form, while the arrow still reaches the footer.
      let modalExclusion = SpatialOverlayExclusionZone(
        rect: SpatialOverlayGeometry.globalAppKitFrame(topLeftFrame: modalTopLeft),
        kind: .targetWindowChrome,
        isHard: true)
      let screenWithModal = SpatialOverlayScreen(
        id: overlayScreen.id, frame: windowFrame, visibleFrame: windowFrame,
        exclusionZones: [modalExclusion])
      return [
        SpatialOverlayAnchorCandidate(
          id: "claude-add-modal-footer",
          targetRect: SpatialOverlayGeometry.globalAppKitFrame(topLeftFrame: footer.rect),
          targetPoint: SpatialOverlayGeometry.globalAppKitPoint(topLeft: footer.point),
          screen: screenWithModal,
          window: window,
          evidence: [
            SpatialOverlayTargetEvidence(
              source: .layoutHeuristic, confidence: 0.55,
              label: "Claude modal footer (Add button area)",
              diagnostics: ["display-guidance-only", "anchored-to-located-modal"])
          ],
          confidence: 0.55,
          allowedUses: [.displayGuidance])
      ]
    }

    // 4) Nothing located — suppress the overlay rather than point at a guess.
    return []
  }

  /// Bounding rect (top-left coords) of Claude's connector modal, derived from the
  /// form-field frames we located in the accessibility tree. Returns nil if too few
  /// fields are located to be confident. Pure and testable.
  nonisolated static func claudeModalRect(
    fromFieldFrames frames: [CGRect], titleFrame: CGRect? = nil
  ) -> CGRect? {
    let valid = frames.filter { !$0.isNull && !$0.isEmpty }
    guard valid.count >= 2 else { return nil }
    var rect = valid.dropFirst().reduce(valid[0]) { $0.union($1) }
    if let titleFrame, !titleFrame.isNull, !titleFrame.isEmpty {
      rect = rect.union(titleFrame)
    }
    return rect
  }

  /// Footer target (top-left coords) for the modal's Add button area, anchored to the
  /// located modal rect. The footer band sits just below the located form content,
  /// biased to the bottom-right where Add renders. Clamped inside the window so it can
  /// never land in off-screen dead space. Pure and testable.
  nonisolated static func claudeAddFallbackFooterTarget(
    modalTopLeft modal: CGRect, window: CGRect
  ) -> (rect: CGRect, point: CGPoint)? {
    guard !modal.isNull, !modal.isEmpty else { return nil }
    let footerWidth = min(240, max(120, modal.width * 0.5))
    let footerHeight: CGFloat = 84
    var rect = CGRect(
      x: modal.maxX - footerWidth, y: modal.maxY, width: footerWidth, height: footerHeight)
    // Keep the footer inside the window (top-left coords: clamp against window bounds).
    if window.width > 0, window.height > 0 {
      let maxY = window.maxY - footerHeight
      rect.origin.y = Swift.min(rect.origin.y, Swift.max(window.minY, maxY))
      rect.origin.x = Swift.min(
        Swift.max(rect.origin.x, window.minX), Swift.max(window.minX, window.maxX - footerWidth))
    }
    // Aim at the upper-right of the footer, nearest the located content.
    let point = CGPoint(x: rect.maxX - footerWidth * 0.3, y: rect.minY + 26)
    return (rect, point)
  }

  private static func locatedClaudeModalRect(
    in nodes: [AccessibleNode], within window: CGRect
  ) -> CGRect? {
    let fieldFrames =
      nodes
      .filter { isInputField($0) && !$0.frame.isNull && !$0.frame.isEmpty }
      .map(\.frame)
      .filter { window.isNull || window.isEmpty || window.intersects($0) }
    let titleFrame =
      nodes.first { $0.searchableText.contains("add custom connector") }?.frame
    return claudeModalRect(fromFieldFrames: fieldFrames, titleFrame: titleFrame)
  }

  nonisolated static func inferredClaudeAddButtonFrameFromCancel(_ cancelFrame: CGRect) -> CGRect {
    CGRect(
      x: cancelFrame.maxX + 12,
      y: cancelFrame.minY,
      width: max(72, min(96, cancelFrame.height * 1.65)),
      height: cancelFrame.height
    )
  }

  nonisolated private static func guidanceCandidates(
    windowFrame: CGRect,
    explicitTargetFrames: [CGRect],
    heuristicID: String,
    heuristicPoint: CGPoint,
    heuristicTargetSize: CGSize
  ) -> [SpatialOverlayAnchorCandidate] {
    let screen = SpatialOverlayScreen(
      id: "claude-window", frame: windowFrame, visibleFrame: windowFrame)
    let window = SpatialOverlayWindow(
      id: "claude-window",
      frame: windowFrame,
      screenID: screen.id
    )
    let explicitCandidates = explicitTargetFrames.enumerated().map { index, frame in
      SpatialOverlayAnchorCandidate(
        id: "\(heuristicID)-explicit-\(index)",
        targetRect: frame,
        screen: screen,
        window: window,
        evidence: [
          SpatialOverlayTargetEvidence(
            source: .accessibility, confidence: 0.95, label: "Claude action button")
        ],
        confidence: 0.95 - Double(index) * 0.01,
        allowedUses: [.displayGuidance, .performClick]
      )
    }
    let heuristicCandidate = SpatialOverlayAnchorCandidate(
      id: heuristicID,
      targetRect: CGRect(
        x: heuristicPoint.x - heuristicTargetSize.width / 2,
        y: heuristicPoint.y - heuristicTargetSize.height / 2,
        width: heuristicTargetSize.width,
        height: heuristicTargetSize.height
      ),
      targetPoint: heuristicPoint,
      screen: screen,
      window: window,
      evidence: [
        SpatialOverlayTargetEvidence(
          source: .layoutHeuristic,
          confidence: 0.58,
          label: "Claude layout estimate",
          diagnostics: ["guidance-only"]
        )
      ],
      confidence: 0.58,
      allowedUses: [.displayGuidance]
    )
    return explicitCandidates + [heuristicCandidate]
  }

  nonisolated static func claudeConnectGuidanceAnchor(in windowFrame: CGRect) -> CGPoint {
    CGPoint(
      x: windowFrame.minX + windowFrame.width * 0.72,
      y: windowFrame.minY + windowFrame.height * 0.33
    )
  }

  nonisolated static func claudeAddGuidanceAnchor(in windowFrame: CGRect) -> CGPoint {
    // When Screen Recording is unavailable, Claude's Add button is not visible to OCR
    // or AX. Estimate the button from the modal's geometry. The previous estimate put
    // the Y a flat 20% up from the *window bottom*, which for a tall browser window
    // lands below the vertically-centered modal's footer (the "arrow below the modal"
    // bug). Model the modal as a centered dialog and anchor on its footer's bottom-right
    // instead. Guidance-only: submit clicks still require a verified AX or OCR target.
    return claudeFooterButtonAnchor(in: windowFrame, fromRightEdgeInset: 70)
  }

  /// Bottom-right footer-button anchor for Claude's centered "Add custom connector"
  /// modal, in AppKit coordinates. `fromRightEdgeInset` is the distance from the modal's
  /// right edge to the button center.
  nonisolated static func claudeFooterButtonAnchor(
    in windowFrame: CGRect, fromRightEdgeInset: CGFloat
  ) -> CGPoint {
    let modalWidth = min(windowFrame.width * 0.52, 1_040)
    let modalMaxX = windowFrame.midX + modalWidth / 2
    // Centered dialog; the footer sits just inside the modal's bottom edge.
    let modalHeight = min(windowFrame.height * 0.74, 760)
    let modalBottomY = windowFrame.midY - modalHeight / 2  // AppKit: bottom edge
    let footerButtonCenterY = modalBottomY + 30 + 27  // footer inset + half button height
    return CGPoint(x: modalMaxX - fromRightEdgeInset, y: footerButtonCenterY)
  }

  private static func fillClaudeConnectorAddModalByKeyboard(
    target: (app: NSRunningApplication, state: ClaudeConnectorPageState),
    values: [FieldValue],
    submit: Bool,
    expectedOwnerID: String?
  ) async -> String? {
    guard ChatToolExecutor.isExpectedOwnerCurrent(expectedOwnerID) else {
      return ChatToolExecutor.authorizedOwnerChangedResult()
    }
    guard target.state == .addCustomConnectorModal else { return nil }
    guard let name = values.first(where: { $0.label == "Name" })?.value,
      let serverURL = values.first(where: { $0.label == "Remote MCP server URL" })?.value,
      let clientID = values.first(where: { $0.label == "OAuth Client ID" })?.value
    else { return nil }
    let clientSecret = values.first(where: { $0.label == "OAuth Client Secret" })?.value

    let pasteboardSnapshot = PasteboardSnapshot.capture()
    defer { pasteboardSnapshot.restore() }

    target.app.activate()
    try? await Task.sleep(nanoseconds: 450_000_000)
    guard ChatToolExecutor.isExpectedOwnerCurrent(expectedOwnerID) else {
      return ChatToolExecutor.authorizedOwnerChangedResult()
    }
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
    guard ChatToolExecutor.isExpectedOwnerCurrent(expectedOwnerID) else {
      return ChatToolExecutor.authorizedOwnerChangedResult()
    }
    pressTab(count: 3)
    pasteIntoFocusedField(name)
    pressTab(count: 1)
    pasteIntoFocusedField(serverURL)
    pressTab(count: 2)
    pasteIntoFocusedField(clientID)
    if let clientSecret {
      pressTab(count: 1)
      pasteIntoFocusedField(clientSecret)
    }

    var lines = [
      "Native connector form filler result:",
      "Provider: claude",
      "Browser/app: \(target.app.localizedName ?? target.app.bundleIdentifier ?? "unknown")",
      clientSecret == nil
        ? "Filled: Name, Remote MCP server URL, OAuth Client ID"
        : "Filled: Name, Remote MCP server URL, OAuth Client ID, OAuth Client Secret",
      "Method: keyboard fallback",
    ]

    if submit {
      lines.append(
        await pressClaudeConnectorAddButtonByOCR(
          target: target,
          expectedOwnerID: expectedOwnerID))
    } else {
      lines.append("Submit skipped by request.")
    }

    return lines.joined(separator: "\n")
  }

  private static func pressClaudeConnectorAddButtonByOCR(
    target: (app: NSRunningApplication, state: ClaudeConnectorPageState),
    expectedOwnerID: String?
  ) async -> String {
    guard ChatToolExecutor.isExpectedOwnerCurrent(expectedOwnerID) else {
      return ChatToolExecutor.authorizedOwnerChangedResult()
    }
    guard CGPreflightScreenCaptureAccess() else {
      return
        "Error: Screen Recording permission is not available to Omi, so the native connector form filler cannot OCR Claude's hidden Add button."
    }

    let appElement = AXUIElementCreateApplication(target.app.processIdentifier)
    let nodes = focusedAndWindowRoots(for: appElement)
      .flatMap { collectNodes(from: $0, maxDepth: 10, maxNodes: 500) }
    guard claudeConnectorPageState(nodes: nodes) == .addCustomConnectorModal else {
      return "Error: Refusing Claude Add because the verified page state changed."
    }

    guard let clickPoint = await resolveClaudeConnectorAddPointByOCR(target: target, nodes: nodes)
    else {
      return
        "Error: The Claude add connector button is not exposed to Accessibility. Refusing blind coordinate or keyboard clicks."
    }
    guard ChatToolExecutor.isExpectedOwnerCurrent(expectedOwnerID) else {
      return ChatToolExecutor.authorizedOwnerChangedResult()
    }

    guard let activeTarget = frontmostClaudeConnectorKeyboardTarget(),
      activeTarget.state == .addCustomConnectorModal,
      let refreshedPoint = await resolveClaudeConnectorAddPointByOCR(target: target, nodes: nodes),
      pointDistance(refreshedPoint, clickPoint) <= 8
    else {
      return "Error: Refusing Claude Add because the OCR target was not stable."
    }

    guard ChatToolExecutor.isExpectedOwnerCurrent(expectedOwnerID) else {
      return ChatToolExecutor.authorizedOwnerChangedResult()
    }
    postLeftClick(at: refreshedPoint)
    try? await Task.sleep(nanoseconds: 700_000_000)
    return "Submitted with button: Add (OCR)"
  }

  private static func pressClaudeConnectorConnectButton(
    target: (app: NSRunningApplication, state: ClaudeConnectorPageState),
    expectedOwnerID: String?
  ) async -> String? {
    guard ChatToolExecutor.isExpectedOwnerCurrent(expectedOwnerID) else {
      return ChatToolExecutor.authorizedOwnerChangedResult()
    }
    guard target.state == .connectorDetailNotConnected else { return nil }

    target.app.activate()
    try? await Task.sleep(nanoseconds: 450_000_000)
    guard ChatToolExecutor.isExpectedOwnerCurrent(expectedOwnerID) else {
      return ChatToolExecutor.authorizedOwnerChangedResult()
    }
    guard let active = NSWorkspace.shared.frontmostApplication,
      active.processIdentifier == target.app.processIdentifier,
      let activeTarget = frontmostClaudeConnectorKeyboardTarget(),
      activeTarget.state == .connectorDetailNotConnected
    else {
      return
        "Error: Refusing Claude Connect because the active window is not the Omi connector detail page."
    }

    let appElement = AXUIElementCreateApplication(target.app.processIdentifier)
    let nodes = focusedAndWindowRoots(for: appElement)
      .flatMap { collectNodes(from: $0, maxDepth: 10, maxNodes: 500) }
    guard claudeConnectorPageState(nodes: nodes) == .connectorDetailNotConnected else {
      return "Error: Refusing Claude Connect because the verified page state changed."
    }
    if let button = findClaudeConnectorDetailConnectButton(in: nodes) {
      guard ChatToolExecutor.isExpectedOwnerCurrent(expectedOwnerID) else {
        return ChatToolExecutor.authorizedOwnerChangedResult()
      }
      _ = AXUIElementPerformAction(button.element, kAXPressAction as CFString)
      try? await Task.sleep(nanoseconds: 700_000_000)
      return await claudeConnectResultLines(
        target: target, appElement: appElement, method: "Accessibility")
    }

    guard CGPreflightScreenCaptureAccess() else {
      return
        "Error: Screen Recording permission is not available to Omi, so the native connector form filler cannot OCR the hidden Claude Connect button."
    }

    guard
      let clickPoint = await resolveClaudeConnectorConnectPointByOCR(
        target: target,
        nodes: nodes
      )
    else {
      return
        "Error: Claude connector is added, but the Connect button is not exposed to Accessibility. Refusing blind coordinate or keyboard clicks."
    }

    guard let activeTarget = frontmostClaudeConnectorKeyboardTarget(),
      activeTarget.state == .connectorDetailNotConnected,
      let refreshedPoint = await resolveClaudeConnectorConnectPointByOCR(
        target: target, nodes: nodes),
      pointDistance(refreshedPoint, clickPoint) <= 8
    else {
      return "Error: Refusing Claude Connect because the OCR target was not stable."
    }

    guard ChatToolExecutor.isExpectedOwnerCurrent(expectedOwnerID) else {
      return ChatToolExecutor.authorizedOwnerChangedResult()
    }
    postLeftClick(at: refreshedPoint)
    try? await Task.sleep(nanoseconds: 700_000_000)

    return await claudeConnectResultLines(target: target, appElement: appElement, method: "OCR")
  }

  private static func claudeConnectResultLines(
    target: (app: NSRunningApplication, state: ClaudeConnectorPageState),
    appElement: AXUIElement,
    method: String
  ) async -> String {
    let afterNodes = focusedAndWindowRoots(for: appElement)
      .flatMap { collectNodes(from: $0, maxDepth: 10, maxNodes: 500) }
    let afterState = claudeConnectorPageState(nodes: afterNodes)
    var lines = [
      "Native connector form filler result:",
      "Provider: claude",
      "Browser/app: \(target.app.localizedName ?? target.app.bundleIdentifier ?? "unknown")",
      "Submitted with button: Connect (\(method))",
    ]
    if afterState == .connectorDetailConnected {
      lines.append("Claude connector connected.")
    } else {
      lines.append("Connect pressed; waiting for Claude to finish or show OAuth consent.")
    }
    return lines.joined(separator: "\n")
  }

  private static func nonEmptyString(_ value: Any?) -> String? {
    guard let string = value as? String else { return nil }
    let trimmed = string.trimmingCharacters(in: .whitespacesAndNewlines)
    return trimmed.isEmpty ? nil : trimmed
  }

  private static func defaultOAuthClientID(for provider: String) -> String {
    switch provider {
    case "chatgpt": return MemoryExportDestination.chatgpt.cloudOAuthClientID ?? ""
    case "claude": return MemoryExportDestination.claude.cloudOAuthClientID ?? ""
    default: return ""
    }
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
    candidates.append(
      contentsOf: NSWorkspace.shared.runningApplications.filter { app in
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
    candidates.append(
      contentsOf: NSWorkspace.shared.runningApplications.filter { app in
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

  private static func findClaudeConnectorTargetWithNodes() -> (
    app: NSRunningApplication, state: ClaudeConnectorPageState, nodes: [AccessibleNode]
  )? {
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
        if state != .other {
          return (app, state, nodes)
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

  private static func claudeConnectorPageState(nodes: [AccessibleNode]) -> ClaudeConnectorPageState
  {
    let text = nodes.map(\.searchableText).joined(separator: " ")
    return classifyClaudeConnectorPageText(text)
  }

  nonisolated static func classifyClaudeConnectorPageText(_ text: String)
    -> ClaudeConnectorPageState
  {
    let text = text.lowercased()
    guard text.contains("claude.ai/customize/connectors") else { return .other }

    let hasAddModalURL = text.contains("modal=add-custom-connector")
    let hasAddModalTitle = text.contains("add custom connector")
    let hasClaudeCustomizeWindowTitle = text.contains("customize - claude")
    let hasAddModalFields =
      text.contains("remote mcp server url")
      && text.contains("oauth client id")
      && text.contains("oauth client secret")
    if hasAddModalTitle && (hasAddModalURL || hasAddModalFields) {
      return .addCustomConnectorModal
    }
    if hasAddModalURL && hasClaudeCustomizeWindowTitle {
      return .addCustomConnectorModal
    }

    let mcpServerURL = MemoryExportDestination.mcpServerURL.lowercased()
    let hasOmiConnector =
      text.contains("omi custom")
      || (text.contains("omi") && text.contains(mcpServerURL))
    guard hasOmiConnector else { return .other }

    if text.contains("you are not connected to omi yet")
      || text.contains("not connected to omi yet")
    {
      return .connectorDetailNotConnected
    }

    if text.contains("you are connected to omi")
      || text.contains("connected to omi.")
    {
      return .connectorDetailConnected
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
    if AXUIElementSetAttributeValue(element, "AXValue" as CFString, value as CFTypeRef) == .success
    {
      return true
    }
    _ = AXUIElementSetAttributeValue(element, "AXFocused" as CFString, kCFBooleanTrue)
    Thread.sleep(forTimeInterval: 0.08)
    NSPasteboard.general.clearContents()
    NSPasteboard.general.setString(value, forType: .string)
    sendKey(0, flags: .maskCommand)
    sendKey(9, flags: .maskCommand)
    Thread.sleep(forTimeInterval: 0.12)
    return fieldValueMatches(element, expected: value)
  }

  private static func fieldValueMatches(_ element: AXUIElement, expected: String) -> Bool {
    var rawValue: CFTypeRef?
    guard AXUIElementCopyAttributeValue(element, "AXValue" as CFString, &rawValue) == .success
    else {
      return false
    }
    guard let actual = rawValue as? String else { return false }
    return actual == expected
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

  private static func findClaudeConnectorDetailConnectButton(
    in nodes: [AccessibleNode]
  ) -> AccessibleNode? {
    let windowFrames =
      nodes
      .filter { $0.role.lowercased().contains("window") && !$0.frame.isNull && !$0.frame.isEmpty }
      .map(\.frame)
    guard let windowFrame = windowFrames.max(by: { $0.width * $0.height < $1.width * $1.height })
    else {
      return nil
    }

    let centerX = windowFrame.midX
    let candidates = nodes.filter { node in
      let label = bestLabel(for: node).trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
      return node.role.lowercased().contains("button")
        && label == "connect"
        && !node.frame.isNull
        && !node.frame.isEmpty
        && node.frame.midX > centerX
    }
    guard candidates.count == 1 else { return nil }
    return candidates[0]
  }

  private static func resolveClaudeConnectorConnectPointByOCR(
    target: (app: NSRunningApplication, state: ClaudeConnectorPageState),
    nodes: [AccessibleNode]
  ) async -> CGPoint? {
    guard target.state == .connectorDetailNotConnected else { return nil }
    guard let windowFrame = largestWindowFrame(in: nodes),
      let windowID = frontmostWindowID(for: target.app.processIdentifier, matching: windowFrame)
    else { return nil }

    let captureService = ScreenCaptureService()
    guard case .success(let image) = await captureService.captureWindowCGImage(windowID: windowID)
    else {
      return nil
    }

    let candidates = (try? await ocrTextCandidates(in: image)) ?? []
    guard
      let candidate = findClaudeConnectOCRCandidate(
        candidates,
        imageSize: CGSize(width: image.width, height: image.height),
        windowFrame: windowFrame
      )
    else { return nil }

    let imageSize = CGSize(width: image.width, height: image.height)
    let screenRect = imageRectToScreen(
      candidate.imageRect, imageSize: imageSize, windowFrame: windowFrame)
    let point = CGPoint(x: screenRect.midX, y: screenRect.midY)
    guard pointIsInVerifiedBrowserContent(point, app: target.app, windowFrame: windowFrame) else {
      return nil
    }
    return point
  }

  private static func resolveClaudeConnectorAddPointByOCR(
    target: (app: NSRunningApplication, state: ClaudeConnectorPageState),
    nodes: [AccessibleNode]
  ) async -> CGPoint? {
    guard target.state == .addCustomConnectorModal else { return nil }
    guard let windowFrame = largestWindowFrame(in: nodes),
      let windowID = frontmostWindowID(for: target.app.processIdentifier, matching: windowFrame)
    else { return nil }

    let captureService = ScreenCaptureService()
    guard case .success(let image) = await captureService.captureWindowCGImage(windowID: windowID)
    else {
      return nil
    }

    let candidates = (try? await ocrTextCandidates(in: image)) ?? []
    guard
      let candidate = findClaudeAddOCRCandidate(
        candidates,
        imageSize: CGSize(width: image.width, height: image.height),
        windowFrame: windowFrame
      )
    else { return nil }

    let imageSize = CGSize(width: image.width, height: image.height)
    let screenRect = imageRectToScreen(
      candidate.imageRect, imageSize: imageSize, windowFrame: windowFrame)
    let point = CGPoint(x: screenRect.midX, y: screenRect.midY)
    guard pointIsInVerifiedBrowserContent(point, app: target.app, windowFrame: windowFrame) else {
      return nil
    }
    return point
  }

  nonisolated static func findClaudeConnectOCRCandidate(
    _ candidates: [OCRTextCandidate],
    imageSize: CGSize,
    windowFrame: CGRect
  ) -> OCRTextCandidate? {
    let safeTopInset = max(88, windowFrame.height * 0.08)
    let matching = candidates.filter { candidate in
      let label = candidate.text.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
      let screenRect = imageRectToScreen(
        candidate.imageRect, imageSize: imageSize, windowFrame: windowFrame)
      return label == "connect"
        && candidate.confidence >= 0.75
        && screenRect.midX > windowFrame.midX
        && screenRect.midY > windowFrame.minY + safeTopInset
        && screenRect.maxX < windowFrame.maxX - 12
        && screenRect.minY > windowFrame.minY + 12
        && screenRect.maxY < windowFrame.maxY - 12
    }
    guard matching.count == 1 else { return nil }
    return matching[0]
  }

  nonisolated static func findClaudeAddOCRCandidate(
    _ candidates: [OCRTextCandidate],
    imageSize: CGSize,
    windowFrame: CGRect
  ) -> OCRTextCandidate? {
    let safeTopInset = max(88, windowFrame.height * 0.08)
    let matching = candidates.filter { candidate in
      let label = candidate.text.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
      let screenRect = imageRectToScreen(
        candidate.imageRect, imageSize: imageSize, windowFrame: windowFrame)
      return label == "add"
        && candidate.confidence >= 0.75
        && screenRect.midX > windowFrame.midX
        && screenRect.midY > windowFrame.minY + windowFrame.height * 0.12
        && screenRect.midY < windowFrame.minY + windowFrame.height * 0.50
        && screenRect.midY > windowFrame.minY + safeTopInset
        && screenRect.maxX < windowFrame.maxX - 12
        && screenRect.minY > windowFrame.minY + 12
        && screenRect.maxY < windowFrame.maxY - 12
    }
    guard matching.count == 1 else { return nil }
    return matching[0]
  }

  private static func ocrTextCandidates(in image: CGImage) async throws -> [OCRTextCandidate] {
    try await withCheckedThrowingContinuation { continuation in
      let request = VNRecognizeTextRequest { request, error in
        if let error {
          continuation.resume(throwing: error)
          return
        }

        let observations = (request.results as? [VNRecognizedTextObservation]) ?? []
        let candidates = observations.compactMap { observation -> OCRTextCandidate? in
          guard let candidate = observation.topCandidates(1).first else { return nil }
          let rect = observation.boundingBox
          guard rect.origin.x.isFinite, rect.origin.y.isFinite, rect.width.isFinite,
            rect.height.isFinite
          else { return nil }
          let imageRect = CGRect(
            x: rect.origin.x * CGFloat(image.width),
            y: (1 - rect.origin.y - rect.height) * CGFloat(image.height),
            width: rect.width * CGFloat(image.width),
            height: rect.height * CGFloat(image.height)
          )
          return OCRTextCandidate(
            text: candidate.string,
            confidence: Double(candidate.confidence),
            imageRect: imageRect
          )
        }
        continuation.resume(returning: candidates)
      }
      request.recognitionLevel = .accurate
      request.usesLanguageCorrection = true
      request.recognitionLanguages = ["en-US"]
      do {
        try VNImageRequestHandler(cgImage: image, options: [:]).perform([request])
      } catch {
        continuation.resume(throwing: error)
      }
    }
  }

  nonisolated private static func pointDistance(_ lhs: CGPoint, _ rhs: CGPoint) -> CGFloat {
    hypot(lhs.x - rhs.x, lhs.y - rhs.y)
  }

  private static func largestWindowFrame(in nodes: [AccessibleNode]) -> CGRect? {
    nodes
      .filter { $0.role.lowercased().contains("window") && !$0.frame.isNull && !$0.frame.isEmpty }
      .map(\.frame)
      .max(by: { $0.width * $0.height < $1.width * $1.height })
  }

  private static func frontmostWindowID(
    for pid: pid_t,
    matching frame: CGRect
  ) -> CGWindowID? {
    guard
      let windowList = CGWindowListCopyWindowInfo(
        [.optionOnScreenOnly, .excludeDesktopElements], kCGNullWindowID) as? [[String: Any]]
    else { return nil }

    let candidate = windowList.first { window in
      guard let windowPID = window[kCGWindowOwnerPID as String] as? Int32,
        windowPID == pid,
        let bounds = window[kCGWindowBounds as String] as? [String: CGFloat],
        let x = bounds["X"],
        let y = bounds["Y"],
        let width = bounds["Width"],
        let height = bounds["Height"]
      else { return false }
      let windowFrame = CGRect(x: x, y: y, width: width, height: height)
      return abs(windowFrame.midX - frame.midX) <= 4
        && abs(windowFrame.midY - frame.midY) <= 4
        && abs(windowFrame.width - frame.width) <= 8
        && abs(windowFrame.height - frame.height) <= 8
    }
    return candidate?[kCGWindowNumber as String] as? CGWindowID
  }

  nonisolated private static func imageRectToScreen(
    _ imageRect: CGRect,
    imageSize: CGSize,
    windowFrame: CGRect
  ) -> CGRect {
    let scaleX = windowFrame.width / imageSize.width
    let scaleY = windowFrame.height / imageSize.height
    return CGRect(
      x: windowFrame.minX + imageRect.minX * scaleX,
      y: windowFrame.minY + imageRect.minY * scaleY,
      width: imageRect.width * scaleX,
      height: imageRect.height * scaleY
    )
  }

  private static func pointIsInVerifiedBrowserContent(
    _ point: CGPoint,
    app: NSRunningApplication,
    windowFrame: CGRect
  ) -> Bool {
    guard point.x > windowFrame.midX,
      point.y > windowFrame.minY + max(88, windowFrame.height * 0.08),
      point.x < windowFrame.maxX - 12,
      point.y < windowFrame.maxY - 12
    else { return false }

    var rawElement: AXUIElement?
    let appElement = AXUIElementCreateApplication(app.processIdentifier)
    let result = AXUIElementCopyElementAtPosition(
      appElement,
      Float(point.x),
      Float(point.y),
      &rawElement
    )
    guard result == .success, let element = rawElement else { return false }
    let node = node(from: element)
    let text = node.searchableText
    if text.contains("address") || text.contains("toolbar") || text.contains("tab")
      || text.contains("search")
    {
      return false
    }
    return true
  }

  private static func postLeftClick(at point: CGPoint) {
    let source = CGEventSource(stateID: .hidSystemState)
    let down = CGEvent(
      mouseEventSource: source,
      mouseType: .leftMouseDown,
      mouseCursorPosition: point,
      mouseButton: .left
    )
    let up = CGEvent(
      mouseEventSource: source,
      mouseType: .leftMouseUp,
      mouseCursorPosition: point,
      mouseButton: .left
    )
    down?.post(tap: .cghidEventTap)
    Thread.sleep(forTimeInterval: 0.05)
    up?.post(tap: .cghidEventTap)
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

  private static func elementAttribute(_ element: AXUIElement, _ attribute: String) -> AXUIElement?
  {
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

extension Array where Element == NSRunningApplication {
  fileprivate func uniquedByPID() -> [NSRunningApplication] {
    var seen = Set<pid_t>()
    var output: [NSRunningApplication] = []
    for app in self where !seen.contains(app.processIdentifier) {
      seen.insert(app.processIdentifier)
      output.append(app)
    }
    return output
  }
}
