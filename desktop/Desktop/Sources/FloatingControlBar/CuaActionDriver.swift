import AppKit

@MainActor
final class CuaActionDriver: OmiActionDriver {

    // MARK: - click

    func click(at point: CGPoint, targetApp: NSRunningApplication?) async throws {
        if let app = targetApp {
            app.activate(options: .activateIgnoringOtherApps)
            try await Task.sleep(for: .milliseconds(80))
        }

        // `point` is already in CG screen space (top-left origin) from
        // OmiElementResolver — no flip needed for CGEvent.
        let cgPoint = point

        let src = CGEventSource(stateID: .hidSystemState)
        let move = CGEvent(mouseEventSource: src, mouseType: .mouseMoved,      mouseCursorPosition: cgPoint, mouseButton: .left)
        let down = CGEvent(mouseEventSource: src, mouseType: .leftMouseDown,   mouseCursorPosition: cgPoint, mouseButton: .left)
        let up   = CGEvent(mouseEventSource: src, mouseType: .leftMouseUp,     mouseCursorPosition: cgPoint, mouseButton: .left)
        move?.post(tap: .cghidEventTap)
        down?.post(tap: .cghidEventTap)
        up?.post(tap: .cghidEventTap)

        log("CuaActionDriver: clicked at \(cgPoint)")
    }

    // MARK: - type

    func type(text: String, targetApp: NSRunningApplication?) async throws {
        if let app = targetApp {
            app.activate(options: .activateIgnoringOtherApps)
            try await Task.sleep(for: .milliseconds(80))
        }

        // Try AX direct insertion first
        let systemWide = AXUIElementCreateSystemWide()
        var focusedElement: CFTypeRef?
        let focusResult = AXUIElementCopyAttributeValue(systemWide, kAXFocusedUIElementAttribute as CFString, &focusedElement)

        if focusResult == .success, let focused = focusedElement {
            let axElement = focused as! AXUIElement
            let setResult = AXUIElementSetAttributeValue(axElement, kAXSelectedTextAttribute as CFString, text as CFTypeRef)
            if setResult == .success {
                log("CuaActionDriver: typed via AX direct insertion")
                return
            }
        }

        log("CuaActionDriver: falling back to clipboard paste for type")
        let pasteboard = NSPasteboard.general
        pasteboard.clearContents()
        pasteboard.setString(text, forType: .string)

        let src = CGEventSource(stateID: .hidSystemState)
        let keyDown = CGEvent(keyboardEventSource: src, virtualKey: 9, keyDown: true)
        let keyUp   = CGEvent(keyboardEventSource: src, virtualKey: 9, keyDown: false)
        keyDown?.flags = .maskCommand
        keyUp?.flags   = .maskCommand
        keyDown?.post(tap: .cghidEventTap)
        keyUp?.post(tap: .cghidEventTap)
    }

    // MARK: - pressShortcut

    func pressShortcut(_ keys: String, targetApp: NSRunningApplication?) async throws {
        if let app = targetApp {
            app.activate(options: .activateIgnoringOtherApps)
            try await Task.sleep(for: .milliseconds(80))
        }

        let tokens = keys.components(separatedBy: "+").map { $0.trimmingCharacters(in: .whitespaces) }
        guard !tokens.isEmpty else { throw OmiActionDriverError.unparseableShortcut(keys) }

        var modifiers = CGEventFlags()
        let modifierTokens = tokens.dropLast()
        let keyToken = tokens.last!

        for token in modifierTokens {
            switch token.lowercased() {
            case "cmd", "command":
                modifiers.insert(.maskCommand)
            case "shift":
                modifiers.insert(.maskShift)
            case "opt", "option", "alt":
                modifiers.insert(.maskAlternate)
            case "ctrl", "control":
                modifiers.insert(.maskControl)
            default:
                throw OmiActionDriverError.unparseableShortcut(keys)
            }
        }

        guard let keyCode = keyCodeFor(keyToken) else {
            throw OmiActionDriverError.unparseableShortcut(keys)
        }

        let src = CGEventSource(stateID: .hidSystemState)
        let keyDown = CGEvent(keyboardEventSource: src, virtualKey: keyCode, keyDown: true)
        let keyUp   = CGEvent(keyboardEventSource: src, virtualKey: keyCode, keyDown: false)
        keyDown?.flags = modifiers
        keyUp?.flags   = modifiers
        keyDown?.post(tap: .cghidEventTap)
        keyUp?.post(tap: .cghidEventTap)

        log("CuaActionDriver: pressed shortcut \(keys)")
    }

    // MARK: - scroll

    func scroll(direction: String, amount: Int, targetApp: NSRunningApplication?) async throws {
        if let app = targetApp {
            app.activate(options: .activateIgnoringOtherApps)
            try await Task.sleep(for: .milliseconds(80))
        }

        let mouseLocation = NSEvent.mouseLocation
        let targetScreen = NSScreen.screens.first(where: { $0.frame.contains(mouseLocation) }) ?? NSScreen.main ?? NSScreen.screens.first
        let screenHeight = targetScreen?.frame.height ?? 0
        let cgPoint = CGPoint(x: mouseLocation.x, y: screenHeight - mouseLocation.y)

        var scroll1: Int32 = 0
        var scroll2: Int32 = 0

        switch direction.lowercased() {
        case "up":    scroll1 = Int32(amount)
        case "down":  scroll1 = -Int32(amount)
        case "left":  scroll2 = Int32(amount)
        case "right": scroll2 = -Int32(amount)
        default:
            log("CuaActionDriver: unknown scroll direction '\(direction)', defaulting to down")
            scroll1 = -Int32(amount)
        }

        let src = CGEventSource(stateID: .hidSystemState)
        let event = CGEvent(
            scrollWheelEvent2Source: src,
            units: .line,
            wheelCount: 2,
            wheel1: scroll1,
            wheel2: scroll2,
            wheel3: 0
        )
        event?.location = cgPoint
        event?.post(tap: CGEventTapLocation.cghidEventTap)

        log("CuaActionDriver: scrolled \(direction) by \(amount) at \(cgPoint)")
    }

    // MARK: - openApp

    func openApp(named: String) async throws {
        let workspace = NSWorkspace.shared

        // Try to find running app first
        if let running = workspace.runningApplications.first(where: {
            $0.localizedName?.lowercased() == named.lowercased()
        }) {
            running.activate(options: .activateIgnoringOtherApps)
            log("CuaActionDriver: activated already-running app '\(named)'")
            return
        }

        // Try to launch by name
        guard workspace.launchApplication(named) else {
            throw OmiActionDriverError.appNotFound(name: named)
        }

        log("CuaActionDriver: launched app '\(named)', waiting for it to become frontmost")

        // Wait up to 3 seconds for it to become frontmost
        for _ in 0..<30 {
            try await Task.sleep(for: .milliseconds(100))
            if NSWorkspace.shared.frontmostApplication?.localizedName?.lowercased() == named.lowercased() {
                log("CuaActionDriver: '\(named)' is now frontmost")
                return
            }
        }

        log("CuaActionDriver: '\(named)' launched but did not become frontmost within 3 s")
    }

    // MARK: - Private helpers

    private func keyCodeFor(_ token: String) -> CGKeyCode? {
        let lower = token.lowercased()

        // Named keys
        switch lower {
        case "space":          return 49
        case "return", "enter": return 36
        case "escape", "esc":  return 53
        case "tab":            return 48
        case "delete", "backspace": return 51
        case "up":             return 126
        case "down":           return 125
        case "left":           return 123
        case "right":          return 124
        default: break
        }

        // Single character keys
        if token.count == 1, let char = token.unicodeScalars.first {
            if let code = charKeyCodeMap[char.value] {
                return code
            }
        }

        return nil
    }

    // US-ANSI key code map for a-z and 0-9
    private let charKeyCodeMap: [UInt32: CGKeyCode] = [
        // a-z
        UInt32(("a" as UnicodeScalar).value): 0,
        UInt32(("s" as UnicodeScalar).value): 1,
        UInt32(("d" as UnicodeScalar).value): 2,
        UInt32(("f" as UnicodeScalar).value): 3,
        UInt32(("h" as UnicodeScalar).value): 4,
        UInt32(("g" as UnicodeScalar).value): 5,
        UInt32(("z" as UnicodeScalar).value): 6,
        UInt32(("x" as UnicodeScalar).value): 7,
        UInt32(("c" as UnicodeScalar).value): 8,
        UInt32(("v" as UnicodeScalar).value): 9,
        UInt32(("b" as UnicodeScalar).value): 11,
        UInt32(("q" as UnicodeScalar).value): 12,
        UInt32(("w" as UnicodeScalar).value): 13,
        UInt32(("e" as UnicodeScalar).value): 14,
        UInt32(("r" as UnicodeScalar).value): 15,
        UInt32(("y" as UnicodeScalar).value): 16,
        UInt32(("t" as UnicodeScalar).value): 17,
        UInt32(("1" as UnicodeScalar).value): 18,
        UInt32(("2" as UnicodeScalar).value): 19,
        UInt32(("3" as UnicodeScalar).value): 20,
        UInt32(("4" as UnicodeScalar).value): 21,
        UInt32(("6" as UnicodeScalar).value): 22,
        UInt32(("5" as UnicodeScalar).value): 23,
        UInt32(("=" as UnicodeScalar).value): 24,
        UInt32(("9" as UnicodeScalar).value): 25,
        UInt32(("7" as UnicodeScalar).value): 26,
        UInt32(("-" as UnicodeScalar).value): 27,
        UInt32(("8" as UnicodeScalar).value): 28,
        UInt32(("0" as UnicodeScalar).value): 29,
        UInt32(("o" as UnicodeScalar).value): 31,
        UInt32(("u" as UnicodeScalar).value): 32,
        UInt32(("i" as UnicodeScalar).value): 34,
        UInt32(("p" as UnicodeScalar).value): 35,
        UInt32(("l" as UnicodeScalar).value): 37,
        UInt32(("j" as UnicodeScalar).value): 38,
        UInt32(("k" as UnicodeScalar).value): 40,
        UInt32(("n" as UnicodeScalar).value): 45,
        UInt32(("m" as UnicodeScalar).value): 46,
    ]
}
