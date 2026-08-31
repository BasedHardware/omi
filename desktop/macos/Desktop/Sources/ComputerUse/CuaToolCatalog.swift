import AppKit
import CoreGraphics
import Foundation

/// One block of a tool's answer, in MCP's own vocabulary.
enum CuaContentBlock {
  case text(String)
  case image(base64: String, mimeType: String)

  var json: [String: Any] {
    switch self {
    case .text(let text):
      return ["type": "text", "text": text]
    case .image(let base64, let mimeType):
      return ["type": "image", "data": base64, "mimeType": mimeType]
    }
  }
}

struct CuaToolResult {
  let content: [CuaContentBlock]
  let isError: Bool

  static func text(_ text: String) -> CuaToolResult {
    CuaToolResult(content: [.text(text)], isError: false)
  }

  static func error(_ text: String) -> CuaToolResult {
    CuaToolResult(content: [.text(text)], isError: true)
  }
}

/// A JSON Schema is `[String: Any]` by nature, which no compiler can prove
/// Sendable. The catalog is a `let` built once at launch and never written
/// again, which is the guarantee the annotation stands in for.
struct CuaTool: @unchecked Sendable {
  let name: String
  let description: String
  let inputSchema: [String: Any]
}

/// The computer-use tools, and what each one does.
///
/// Two lanes, and the descriptions say which to reach for first. The
/// accessibility lane (`ui_snapshot` then `ui_action`) names controls and presses
/// them by reference: a few hundred tokens, and it cannot miss. The pixel lane
/// (`screenshot` then `click`) costs a couple of thousand visual tokens per look
/// and aims by coordinate, but it works in apps that publish no accessibility
/// tree at all — which is most games, many Electron apps, and anything drawing
/// into a canvas.
///
/// Coordinates are always in the space of a screenshot the model has been shown.
/// `CuaFrameRegistry` holds those frames and `CuaFrameGeometry` does the
/// conversion, so a click means the same thing on a Retina laptop, a scaled 5K
/// display, and a second monitor sitting at a negative origin.
enum CuaToolCatalog {
  static let tools: [CuaTool] = [
    CuaTool(
      name: "list_displays",
      description:
        "List the Mac's displays with their size and position. Call this first when more than one screen may be attached.",
      inputSchema: object()),
    CuaTool(
      name: "list_windows",
      description:
        "List open windows with their app, title and position. Cheaper than a screenshot for finding out what is open.",
      inputSchema: object(
        properties: ["app": string("Only windows belonging to this app name or bundle id.")])),
    CuaTool(
      name: "screenshot",
      description:
        "Capture a display or a single window. Returns the picture plus the frame id that later coordinates are measured against. Prefer ui_snapshot when you only need to find a control.",
      inputSchema: object(properties: [
        "display": integer("Display number from list_displays. Defaults to the main display."),
        "window_id": integer("Capture just this window instead of a whole display."),
        "max_long_edge": integer("Long edge of the returned image in pixels. Defaults to 1568."),
      ])),
    CuaTool(
      name: "ui_snapshot",
      description:
        "List an app's on-screen controls from its accessibility tree, each with a ref you can act on. Far cheaper and more reliable than a screenshot when the app publishes a tree.",
      inputSchema: object(properties: [
        "app": string("App name or bundle id. Defaults to the frontmost app."),
        "max_nodes": integer("Cap on controls returned. Defaults to 250."),
        "max_depth": integer("How deep to walk the tree. Defaults to 12."),
      ])),
    CuaTool(
      name: "ui_action",
      description:
        "Press, focus or set the value of a control returned by ui_snapshot. Always try this before clicking a coordinate.",
      inputSchema: object(
        properties: [
          "ref": string("Control reference from ui_snapshot, e.g. e12."),
          "snapshot": string("Snapshot id from ui_snapshot. Defaults to the most recent one."),
          "action": enumeration(
            ["press", "focus", "set_value", "show_menu", "confirm", "cancel"],
            "What to do with the control."),
          "value": string("Text to set, for set_value."),
        ],
        required: ["ref", "action"])),
    CuaTool(
      name: "click",
      description:
        "Click at a coordinate in the last screenshot. Use ui_action instead when the control came from ui_snapshot. A click on a window that is not frontmost usually only brings it forward, so focus_window first when acting on a background app.",
      inputSchema: object(
        properties: [
          "x": number("Horizontal position in the screenshot."),
          "y": number("Vertical position in the screenshot."),
          "frame": string("Frame id from screenshot. Defaults to the most recent frame."),
          "button": enumeration(["left", "right", "middle"], "Mouse button. Defaults to left."),
          "count": integer("1 for a click, 2 for a double click, 3 for a triple click."),
          "modifiers": string("Held modifiers, e.g. \"cmd+shift\"."),
        ],
        required: ["x", "y"])),
    CuaTool(
      name: "move_cursor",
      description: "Move the pointer without clicking, to reveal a hover state or open a menu.",
      inputSchema: object(
        properties: [
          "x": number("Horizontal position in the screenshot."),
          "y": number("Vertical position in the screenshot."),
          "frame": string("Frame id from screenshot. Defaults to the most recent frame."),
        ],
        required: ["x", "y"])),
    CuaTool(
      name: "drag",
      description:
        "Press at one point, move, and release at another — for reordering, selecting a range, or dragging a file.",
      inputSchema: object(
        properties: [
          "from_x": number("Where the drag starts."),
          "from_y": number("Where the drag starts."),
          "to_x": number("Where the drag ends."),
          "to_y": number("Where the drag ends."),
          "frame": string("Frame id from screenshot. Defaults to the most recent frame."),
          "button": enumeration(["left", "right", "middle"], "Mouse button. Defaults to left."),
        ],
        required: ["from_x", "from_y", "to_x", "to_y"])),
    CuaTool(
      name: "scroll",
      description: "Scroll at a coordinate. Positive y scrolls further down the content.",
      inputSchema: object(
        properties: [
          "x": number("Horizontal position in the screenshot."),
          "y": number("Vertical position in the screenshot."),
          "frame": string("Frame id from screenshot. Defaults to the most recent frame."),
          "dx": integer("Horizontal scroll in lines."),
          "dy": integer("Vertical scroll in lines."),
        ],
        required: ["x", "y"])),
    CuaTool(
      name: "type_text",
      description:
        "Type text into whatever is focused. Newlines are typed as Return. For a long value in a text field, ui_action set_value is faster and cannot be interrupted.",
      inputSchema: object(
        properties: ["text": string("The text to type.")],
        required: ["text"])),
    CuaTool(
      name: "key",
      description:
        "Press a key or chord, e.g. \"cmd+s\", \"escape\", \"cmd+shift+4\". Layout-aware, so a chord means the same on any keyboard.",
      inputSchema: object(
        properties: [
          "combo": string("The chord to press."),
          "count": integer("How many times to press it. Defaults to 1."),
        ],
        required: ["combo"])),
    CuaTool(
      name: "cursor_position",
      description: "Where the pointer is now, in global points and in the last frame's coordinates.",
      inputSchema: object()),
    CuaTool(
      name: "read_clipboard",
      description: "Read the text on the clipboard.",
      inputSchema: object()),
    CuaTool(
      name: "set_clipboard",
      description:
        "Put text on the clipboard. Pasting a long value with cmd+v is much faster than typing it.",
      inputSchema: object(
        properties: ["text": string("The text to place on the clipboard.")],
        required: ["text"])),
    CuaTool(
      name: "open_app",
      description: "Launch an app, or bring it forward if it is already running.",
      inputSchema: object(
        properties: ["app": string("App name, bundle id, or path to the bundle.")],
        required: ["app"])),
    CuaTool(
      name: "focus_window",
      description: "Bring an app's window to the front and make it the active app.",
      inputSchema: object(
        properties: [
          "app": string("App name or bundle id."),
          "title": string("Pick the window whose title contains this. Defaults to the frontmost one."),
        ],
        required: ["app"])),
    CuaTool(
      name: "move_window",
      description:
        "Move or resize a window, in global points. Give either position, size, or both.",
      inputSchema: object(
        properties: [
          "app": string("App name or bundle id."),
          "title": string("Pick the window whose title contains this."),
          "x": number("New left edge."),
          "y": number("New top edge."),
          "width": number("New width."),
          "height": number("New height."),
        ],
        required: ["app"])),
    CuaTool(
      name: "run_applescript",
      description:
        "Run AppleScript. The exact way to ask an app a question or drive it without clicking — the selected mail, the front tab's URL, every open document. Prefer it over screenshots when the app is scriptable.",
      inputSchema: object(
        properties: [
          "script": string("The AppleScript source. Its result is returned as text."),
          "timeout_ms": integer("How long to allow, up to 120000. Defaults to 20000."),
        ],
        required: ["script"])),
    CuaTool(
      name: "permissions",
      description:
        "What Omi is allowed to do on this Mac, and a prompt for anything missing. Call this when a tool says a permission is missing.",
      inputSchema: object()),
    CuaTool(
      name: "wait",
      description:
        "Pause before looking again, for a window that is still opening or a page that is still loading.",
      inputSchema: object(
        properties: ["ms": integer("Milliseconds to wait, up to 10000.")],
        required: ["ms"])),
  ]

  static func tool(named name: String) -> CuaTool? {
    tools.first { $0.name == name }
  }

  // MARK: - Dispatch

  static func call(_ name: String, arguments: [String: Any]) async -> CuaToolResult {
    let args = CuaArguments(arguments)
    switch name {
    case "list_displays": return listDisplays()
    case "list_windows": return await listWindows(args)
    case "screenshot": return await screenshot(args)
    case "ui_snapshot": return await uiSnapshot(args)
    case "ui_action": return await uiAction(args)
    case "click": return await click(args)
    case "move_cursor": return await moveCursor(args)
    case "drag": return await drag(args)
    case "scroll": return await scroll(args)
    case "type_text": return await typeText(args)
    case "key": return await key(args)
    case "cursor_position": return cursorPosition()
    case "read_clipboard": return await readClipboard()
    case "set_clipboard": return await setClipboard(args)
    case "open_app": return await openApp(args)
    case "focus_window": return await focusWindow(args)
    case "move_window": return await moveWindow(args)
    case "run_applescript": return await runAppleScript(args)
    case "permissions": return await permissions()
    case "wait": return await wait(args)
    default: return .error("Unknown tool \(name).")
    }
  }

  // MARK: - Observing

  private static func listDisplays() -> CuaToolResult {
    let displays = CuaScreenObserver.displays()
    guard !displays.isEmpty else { return .error("No active displays.") }
    let lines = displays.enumerated().map { index, display in
      "\(index + 1). \(Int(display.bounds.width))x\(Int(display.bounds.height)) points at "
        + "(\(Int(display.bounds.minX)), \(Int(display.bounds.minY)))"
        + ", \(display.pixelWidth)x\(display.pixelHeight) pixels"
        + (display.isMain ? ", main" : "")
    }
    return .text(lines.joined(separator: "\n"))
  }

  private static func listWindows(_ args: CuaArguments) async -> CuaToolResult {
    // SCShareableContent is Screen Recording territory. Without the grant it
    // throws and the window list comes back empty, which reads to a model as an
    // empty desk rather than a missing permission — so it acts on the lie.
    if let refusal = await refusal(needs: [.screenRecording]) {
      return .error(refusal.message)
    }
    var windows = await CuaScreenObserver.windows()
    if let filter = args.string("app")?.lowercased() {
      windows = windows.filter {
        $0.appName.lowercased().contains(filter) || $0.bundleID.lowercased().contains(filter)
      }
    }
    guard !windows.isEmpty else { return .text("No matching windows.") }
    let lines = windows.map { window in
      "[\(window.id)] \(window.appName)\(window.isActive ? " (active)" : "") — "
        + "\(window.title.isEmpty ? "untitled" : window.title) at "
        + "(\(Int(window.frame.minX)), \(Int(window.frame.minY))) "
        + "\(Int(window.frame.width))x\(Int(window.frame.height))"
    }
    return .text(lines.joined(separator: "\n"))
  }

  private static func screenshot(_ args: CuaArguments) async -> CuaToolResult {
    if let refusal = await refusal(needs: [.screenRecording]) {
      return .error(refusal.message)
    }
    let maxLongEdge =
      args.double("max_width").map { CGFloat($0) }
      ?? CuaScreenObserver
      .defaultMaxLongEdge

    let capture: CuaScreenObserver.Capture?
    if let windowID = args.int("window_id") {
      capture = await CuaScreenObserver.captureWindow(
        id: CGWindowID(windowID), maxLongEdge: maxLongEdge)
    } else {
      let displays = CuaScreenObserver.displays()
      let index = (args.int("display") ?? 1) - 1
      guard let display = displays.indices.contains(index) ? displays[index] : displays.first(where: { $0.isMain })
      else { return .error("No such display.") }
      capture = await CuaScreenObserver.captureDisplay(display, maxLongEdge: maxLongEdge)
    }

    if capture != nil {
      // A frame came back, so the grant is real whatever a preflight says. This
      // is what stops a stale "not granted" from following the user around for
      // the rest of the session.
      await MainActor.run { CuaPermission.markGranted(.screenRecording) }
    }
    guard let capture, let png = CuaScreenObserver.pngData(from: capture.image) else {
      return .error(
        "Capture failed. Screen Recording permission may be missing — grant it in System Settings ▸ Privacy & Security ▸ Screen Recording."
      )
    }
    let frameID = CuaFrameRegistry.shared.store(capture.geometry)
    let size = capture.geometry.imageSize
    return CuaToolResult(
      content: [
        .text(
          "\(frameID): \(Int(size.width))x\(Int(size.height)) image of the region "
            + "(\(Int(capture.geometry.bounds.minX)), \(Int(capture.geometry.bounds.minY))) "
            + "\(Int(capture.geometry.bounds.width))x\(Int(capture.geometry.bounds.height)) points. "
            + "Give click coordinates in this image's pixels."),
        .image(base64: png.base64EncodedString(), mimeType: "image/png"),
      ],
      isError: false)
  }

  private static func uiSnapshot(_ args: CuaArguments) async -> CuaToolResult {
    if let refusal = await refusal(needs: [.accessibility]) {
      return .error(refusal.message)
    }
    let named = args.string("app")
    let resolved = await MainActor.run {
      named.map { CuaAxReader.processID(forAppNamed: $0) } ?? CuaAxReader.frontmostProcessID()
    }
    guard let pid = resolved else {
      return .error(
        named.map { "No running app named \($0)." }
          ?? "Omi is frontmost; bring the app you mean forward first.")
    }
    guard
      let snapshot = await CuaAxReader.snapshot(
        pid: pid,
        maxDepth: args.int("max_depth") ?? 12,
        maxNodes: args.int("max_nodes") ?? 250)
    else { return .error("Could not read that app's accessibility tree.") }

    if !snapshot.nodes.isEmpty {
      await MainActor.run { CuaPermission.markGranted(.accessibility) }
    }
    guard !snapshot.nodes.isEmpty else {
      return .text(
        "\(snapshot.appName) publishes no accessibility tree. Use screenshot and click instead.")
    }
    let lines = snapshot.nodes.map { node -> String in
      let label = node.label.isEmpty ? "" : " \"\(node.label)\""
      let value = node.value.isEmpty ? "" : " = \"\(node.value.prefix(60))\""
      let state = [node.enabled ? nil : "disabled", node.focused ? "focused" : nil]
        .compactMap { $0 }.joined(separator: ",")
      let actions = node.actions.isEmpty ? "" : " [\(node.actions.joined(separator: ","))]"
      return "\(node.ref) \(node.role)\(label)\(value)"
        + (state.isEmpty ? "" : " (\(state))") + actions
        + " at (\(Int(node.frame.minX)),\(Int(node.frame.minY))) "
        + "\(Int(node.frame.width))x\(Int(node.frame.height))"
    }
    let header =
      "\(snapshot.appName), snapshot \(snapshot.id)"
      + (snapshot.truncated ? " (truncated — raise max_nodes or narrow the app)" : "")
    return .text(([header] + lines).joined(separator: "\n"))
  }

  private static func cursorPosition() -> CuaToolResult {
    let global = CuaInputSynth.cursorPosition()
    guard let latest = CuaFrameRegistry.shared.latest(),
      let inFrame = latest.geometry.imagePoint(forGlobalPoint: global)
    else {
      return .text("Pointer at global point (\(Int(global.x)), \(Int(global.y))).")
    }
    return .text(
      "Pointer at (\(Int(inFrame.x)), \(Int(inFrame.y))) in \(latest.id), "
        + "global point (\(Int(global.x)), \(Int(global.y))).")
  }

  private static func readClipboard() async -> CuaToolResult {
    guard let text = await MainActor.run(body: { CuaAppControl.readClipboard() }) else {
      return .text("The clipboard holds no text.")
    }
    return .text(text)
  }

  // MARK: - Acting

  private static func uiAction(_ args: CuaArguments) async -> CuaToolResult {
    guard let ref = args.string("ref"), let action = args.string("action") else {
      return .error("ui_action needs a ref and an action.")
    }
    guard let snapshotID = args.string("snapshot") ?? CuaAxRegistry.shared.latestSnapshotID() else {
      return .error("Call ui_snapshot first.")
    }
    if let refusal = await refusal(needs: [.accessibility]) {
      return .error(refusal.message)
    }

    let outcome: CuaAxReader.ActionOutcome
    switch action {
    case "set_value":
      guard let value = args.string("value") else { return .error("set_value needs a value.") }
      outcome = await CuaAxReader.setValue(value, ref: ref, snapshot: snapshotID)
    case "focus":
      outcome = await CuaAxReader.focus(ref: ref, snapshot: snapshotID)
    case "press", "show_menu", "confirm", "cancel":
      let axAction =
        [
          "press": kAXPressAction, "show_menu": kAXShowMenuAction,
          "confirm": kAXConfirmAction, "cancel": kAXCancelAction,
        ][action] ?? kAXPressAction
      outcome = await CuaAxReader.perform(action: axAction, ref: ref, snapshot: snapshotID)
    default:
      return .error("Unknown action \(action).")
    }

    await CuaControlGate.shared.noteActivity()
    switch outcome {
    case .performed:
      return .text("\(action) on \(ref) succeeded.")
    case .unknownReference:
      return .error("\(ref) is not in snapshot \(snapshotID). Take a fresh ui_snapshot.")
    case .failed(let code):
      return .error("\(action) on \(ref) failed (accessibility error \(code)).")
    }
  }

  private static func click(_ args: CuaArguments) async -> CuaToolResult {
    guard let point = resolvePoint(args, xKey: "x", yKey: "y") else {
      return .error("click needs x and y.")
    }
    let button = CuaInputSynth.Button(rawValue: args.string("button") ?? "left") ?? .left
    let count = args.int("count") ?? 1
    let flags: CGEventFlags
    if let modifiers = args.string("modifiers") {
      guard let parsed = CuaKeyMap.flags(from: modifiers) else {
        return .error("\(modifiers) is not a modifier list.")
      }
      flags = parsed
    } else {
      flags = []
    }
    return await perform("Clicked at (\(Int(point.x)), \(Int(point.y)))") {
      CuaInputSynth.click(at: point, button: button, count: count, flags: flags)
    }
  }

  private static func moveCursor(_ args: CuaArguments) async -> CuaToolResult {
    guard let point = resolvePoint(args, xKey: "x", yKey: "y") else {
      return .error("move_cursor needs x and y.")
    }
    return await perform("Pointer moved to (\(Int(point.x)), \(Int(point.y)))") {
      CuaInputSynth.moveCursor(to: point)
    }
  }

  private static func drag(_ args: CuaArguments) async -> CuaToolResult {
    guard let start = resolvePoint(args, xKey: "from_x", yKey: "from_y"),
      let end = resolvePoint(args, xKey: "to_x", yKey: "to_y")
    else { return .error("drag needs from_x, from_y, to_x and to_y.") }
    let button = CuaInputSynth.Button(rawValue: args.string("button") ?? "left") ?? .left
    return await perform("Dragged to (\(Int(end.x)), \(Int(end.y)))") {
      CuaInputSynth.drag(from: start, to: end, button: button)
    }
  }

  private static func scroll(_ args: CuaArguments) async -> CuaToolResult {
    guard let point = resolvePoint(args, xKey: "x", yKey: "y") else {
      return .error("scroll needs x and y.")
    }
    let dx = args.int("dx") ?? 0
    let dy = args.int("dy") ?? 0
    guard dx != 0 || dy != 0 else { return .error("scroll needs a non-zero dx or dy.") }
    return await perform("Scrolled \(dx), \(dy)") {
      CuaInputSynth.scroll(at: point, deltaX: dx, deltaY: dy)
    }
  }

  private static func typeText(_ args: CuaArguments) async -> CuaToolResult {
    guard let text = args.string("text"), !text.isEmpty else {
      return .error("type_text needs text.")
    }
    let layout = await MainActor.run { CuaKeyMap.KeyboardLayout.current() }
    return await perform("Typed \(text.count) characters") {
      CuaInputSynth.typeText(text, layout: layout)
    }
  }

  private static func key(_ args: CuaArguments) async -> CuaToolResult {
    guard let combo = args.string("combo") else { return .error("key needs a combo.") }
    let layout = await MainActor.run { CuaKeyMap.KeyboardLayout.current() }
    guard let chord = CuaKeyMap.chord(from: combo, layout: layout) else {
      return .error("\(combo) is not a key this keyboard has.")
    }
    let count = min(max(args.int("count") ?? 1, 1), 20)
    return await perform("Pressed \(combo)\(count > 1 ? " \(count) times" : "")") {
      for _ in 0..<count { CuaInputSynth.key(chord) }
    }
  }

  private static func setClipboard(_ args: CuaArguments) async -> CuaToolResult {
    guard let text = args.string("text") else { return .error("set_clipboard needs text.") }
    if let refusal = await refusal() {
      return .error(refusal.message)
    }
    await MainActor.run { CuaAppControl.writeClipboard(text) }
    return .text("Clipboard set (\(text.count) characters).")
  }

  private static func openApp(_ args: CuaArguments) async -> CuaToolResult {
    guard let app = args.string("app") else { return .error("open_app needs an app.") }
    if let refusal = await refusal() {
      return .error(refusal.message)
    }
    guard CuaAppControl.open(app: app) else { return .error("Could not open \(app).") }
    return .text("Opened \(app).")
  }

  private static func focusWindow(_ args: CuaArguments) async -> CuaToolResult {
    guard let app = args.string("app") else { return .error("focus_window needs an app.") }
    if let refusal = await refusal(needs: [.accessibility]) {
      return .error(refusal.message)
    }
    guard let pid = await MainActor.run(body: { CuaAxReader.processID(forAppNamed: app) }) else {
      return .error("No running app named \(app).")
    }
    let raised = await CuaAppControl.raiseWindow(pid: pid, titled: args.string("title"))
    let activated = await MainActor.run { CuaAppControl.activate(app: app) }
    guard raised || activated else { return .error("Could not focus \(app).") }
    return .text("Focused \(app).")
  }

  private static func moveWindow(_ args: CuaArguments) async -> CuaToolResult {
    guard let app = args.string("app") else { return .error("move_window needs an app.") }
    if let refusal = await refusal(needs: [.accessibility]) {
      return .error(refusal.message)
    }
    guard let pid = await MainActor.run(body: { CuaAxReader.processID(forAppNamed: app) }) else {
      return .error("No running app named \(app).")
    }
    var origin: CGPoint?
    if let x = args.double("x"), let y = args.double("y") { origin = CGPoint(x: x, y: y) }
    var size: CGSize?
    if let width = args.double("width"), let height = args.double("height") {
      size = CGSize(width: width, height: height)
    }
    guard origin != nil || size != nil else {
      return .error("move_window needs x and y, or width and height.")
    }
    let moved = await CuaAppControl.setWindowFrame(
      pid: pid, titled: args.string("title"), origin: origin, size: size)
    return moved ? .text("Moved \(app)'s window.") : .error("Could not move \(app)'s window.")
  }

  private static func wait(_ args: CuaArguments) async -> CuaToolResult {
    let ms = min(max(args.int("ms") ?? 0, 0), 10_000)
    try? await Task.sleep(nanoseconds: UInt64(ms) * 1_000_000)
    return .text("Waited \(ms)ms.")
  }

  private static func runAppleScript(_ args: CuaArguments) async -> CuaToolResult {
    guard let script = args.string("script") else {
      return .error("run_applescript needs a script.")
    }
    if let refusal = await refusal() {
      return .error(refusal.message)
    }
    let timeout = min(max(Double(args.int("timeout_ms") ?? 20_000), 1_000), 120_000) / 1000

    // Off the caller's queue: the runner waits on a child process, and the
    // endpoint's queue is the one every other request is also waiting on.
    let result = await withCheckedContinuation { (continuation: CheckedContinuation<CuaAppleScript.Result, Never>) in
      DispatchQueue.global(qos: .userInitiated).async {
        continuation.resume(returning: CuaAppleScript.run(script, timeout: timeout))
      }
    }
    await CuaControlGate.shared.noteActivity()

    if let failure = result.failure {
      // A refused Apple Event names the app it was refused for, which is the one
      // thing the user needs in order to fix it.
      let isPermission = failure.contains("-1743") || failure.localizedCaseInsensitiveContains("not allowed")
      return .error(isPermission ? "\(CuaPermission.appleEvents.refusalMessage)\n\(failure)" : failure)
    }
    return .text(result.output.isEmpty ? "The script ran and returned nothing." : result.output)
  }

  /// The permission surface, in one call.
  ///
  /// Every grant Omi already holds is used without asking; the ones it does not
  /// are requested here, which is what shows the user the system prompt. Apple
  /// Events is per target and has no process-wide answer, so it is reported as
  /// such rather than guessed at.
  private static func permissions() async -> CuaToolResult {
    // The switch is asked first, and nothing is requested while it is off: a
    // system prompt for a capability the user has not enabled is a dialog they
    // did not ask for, about a feature that is not running.
    let gate = await refusal()
    let mayRequest = gate == nil
    let lines = await MainActor.run { () -> [String] in
      CuaPermission.allCases.map { permission -> String in
        let label = "\(permission.title) (\(permission.rawValue))"
        switch permission {
        case .appleEvents:
          return "\(label): granted per app, on first use."
        default:
          if permission.isGranted() { return "\(label): granted." }
          guard mayRequest else { return "\(label): not granted." }
          permission.request()
          return
            "\(label): NOT granted. Omi has asked macOS for it — the user has to approve it, "
            + "and a grant given now applies from Omi's next launch."
        }
      }
    }
    let switchLine =
      gate.map { "Computer control: off — \($0.message)" }
      ?? "Computer control: on."
    return .text(([switchLine] + lines).joined(separator: "\n"))
  }

  /// The gate's verdict, after giving a grant the user may have just ticked a
  /// chance to be noticed. Every tool that needs a permission goes through here,
  /// so "granted while Omi was running" works everywhere rather than in whichever
  /// call site remembered to refresh.
  private static func refusal(needs permissions: [CuaPermission] = []) async
    -> CuaControlGate.Refusal?
  {
    await CuaPermission.refreshLiveGrants(permissions)
    return await CuaControlGate.shared.refusal(needs: permissions)
  }

  // MARK: - Shared plumbing

  /// Runs a synthetic gesture behind the gate, and says what happened either way.
  private static func perform(
    _ success: String, needs permissions: [CuaPermission] = [.postEvents],
    _ effect: @escaping @Sendable () -> Void
  ) async -> CuaToolResult {
    await CuaPermission.refreshLiveGrants(permissions)
    let outcome = await CuaControlGate.shared.perform(needs: permissions, effect)
    switch outcome {
    case .success:
      return .text(success + ".")
    case .failure(let refusal):
      return .error(refusal.message)
    }
  }

  /// A coordinate pair in the model's terms, as a point on the desk.
  ///
  /// Without a frame the numbers are read as global points, which is what a
  /// caller driving this server without ever taking a screenshot means.
  private static func resolvePoint(_ args: CuaArguments, xKey: String, yKey: String) -> CGPoint? {
    guard let x = args.double(xKey), let y = args.double(yKey) else { return nil }
    let raw = CGPoint(x: x, y: y)
    if let id = args.string("frame") {
      return CuaFrameRegistry.shared.geometry(id: id)?.globalPoint(forImagePoint: raw) ?? raw
    }
    guard let latest = CuaFrameRegistry.shared.latest() else { return raw }
    return latest.geometry.globalPoint(forImagePoint: raw)
  }

  // MARK: - Schema helpers

  private static func object(
    properties: [String: [String: Any]] = [:], required: [String] = []
  ) -> [String: Any] {
    var schema: [String: Any] = ["type": "object", "properties": properties]
    if !required.isEmpty { schema["required"] = required }
    return schema
  }

  private static func string(_ description: String) -> [String: Any] {
    ["type": "string", "description": description]
  }

  private static func number(_ description: String) -> [String: Any] {
    ["type": "number", "description": description]
  }

  private static func integer(_ description: String) -> [String: Any] {
    ["type": "integer", "description": description]
  }

  private static func enumeration(_ values: [String], _ description: String) -> [String: Any] {
    ["type": "string", "enum": values, "description": description]
  }
}

/// Tool arguments as they arrive: JSON, from a model, with the types it felt
/// like using. A number written as a string is still a number here, because
/// refusing it teaches the model nothing and costs the user a turn.
struct CuaArguments {
  private let raw: [String: Any]

  init(_ raw: [String: Any]) {
    self.raw = raw
  }

  func string(_ key: String) -> String? {
    if let value = raw[key] as? String {
      return value.isEmpty ? nil : value
    }
    if let value = raw[key] as? NSNumber { return value.stringValue }
    return nil
  }

  func double(_ key: String) -> Double? {
    if let value = raw[key] as? NSNumber { return value.doubleValue }
    if let text = raw[key] as? String { return Double(text) }
    return nil
  }

  func int(_ key: String) -> Int? {
    double(key).map { Int($0.rounded()) }
  }
}
