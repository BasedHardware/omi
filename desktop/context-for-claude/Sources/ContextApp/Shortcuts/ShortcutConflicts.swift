import AppKit
import ContextCore
import Foundation

/// Whether another agent tool on this Mac already owns one of our chords.
///
/// The reference shows a row reading "Codex also uses ⌘⌘" with a one-click remedy. That row is only
/// honest if the claim behind it is, so everything here is built around one rule: **a conflict is
/// reported only when it can be traced to a value we actually read.** Three outcomes, and the row is
/// drawn for exactly one of them:
///
/// - `bound` — we read a chord out of the tool's own config file, or out of the default the installed
///   build falls back to when that key is absent. Only this can produce a conflict.
/// - `noGlobalBinding` — the tool is here and provably binds nothing system-wide.
/// - `undetermined` — we could not tell. Nothing is shown. Never a guess, and never a row.
///
/// What this deliberately does **not** do is edit another product's configuration. See `Remedy`.
enum ShortcutConflicts {

    // MARK: - Tools

    enum Tool: String, CaseIterable, Sendable {
        case claudeDesktop
        case codex
        case cursor

        var name: String {
            switch self {
            case .claudeDesktop: return "Claude"
            case .codex: return "Codex"
            case .cursor: return "Cursor"
            }
        }
    }

    // MARK: - Evidence

    /// Where a claim came from. Carried all the way to the UI, because "your config says so" and
    /// "this is what the app falls back to" are not the same strength of claim and the row should not
    /// pretend they are.
    enum Evidence: Equatable, Sendable {
        /// Read out of the user's own configuration file.
        case configFile(path: String)
        /// The key was absent, so the installed build's own fallback applies. `note` records how that
        /// fallback was established.
        case shippedDefault(note: String)

        var sentence: String {
            switch self {
            case .configFile(let path): return "Read from \(path)."
            case .shippedDefault(let note): return note
            }
        }
    }

    /// One binding belonging to another product, in the most specific form we could establish.
    struct ForeignBinding: Equatable, Sendable {
        /// How to print it: `⌥⌥`, `⌘⇧K`, `left ⌘`.
        let display: String
        /// The chord, when it is one our own vocabulary can express exactly.
        let chord: ShortcutChord?
        /// Set when the binding is a *single* bare modifier press.
        ///
        /// This is a real collision that comparing chords would miss: a tool listening for one bare ⌘
        /// fires on the first ⌘ of either of our gestures — the first half of a ⌘⌘, and the first of
        /// the two keys in a ⌘ + ⌘ — so the user gets both behaviours every time.
        let bareModifier: ShortcutModifiers?

        init(display: String, chord: ShortcutChord? = nil, bareModifier: ShortcutModifiers? = nil) {
            self.display = display
            self.chord = chord
            self.bareModifier = bareModifier
        }

        func collides(with ours: ShortcutChord) -> Bool {
            if let chord, chord == ours { return true }
            guard let bareModifier else { return false }
            switch ours {
            case .doubleTap(let tapped, _):
                return tapped == bareModifier
            case .bothCommandKeys:
                // Whichever of the two the user's hand reaches first is a bare Command press, so a
                // tool watching for one fires halfway through the gesture. Note the *other*
                // direction is not a collision and is not listed as one: a tool watching for two
                // taps of ⌘ never sees them, because both keys going down puts the `.command` bit
                // down once. Moving the timeline off ⌘⌘ genuinely took it out of Codex's way.
                return bareModifier == .command
            case .key:
                // A bare modifier is not a key equivalent and cannot take one.
                return false
            }
        }
    }

    /// What we could establish about one tool.
    enum Finding: Equatable, Sendable {
        case notInstalled
        /// Installed, and it binds something system-wide.
        case bound(feature: String, binding: ForeignBinding, evidence: Evidence)
        /// Installed, and provably binds nothing system-wide.
        case noGlobalBinding(reason: String)
        /// Installed, and we cannot tell. Shows nothing.
        case undetermined(reason: String)
    }

    /// A real, evidenced overlap. One per (our action × their feature).
    struct Conflict: Equatable, Sendable {
        let tool: Tool
        let action: GlobalShortcuts.Action
        let chord: ShortcutChord
        let feature: String
        let evidence: Evidence
        let remedy: Remedy

        /// The reference's row title, in our words: "Claude also uses ⌥⌥".
        var title: String { "\(tool.name) also uses \(chord.display)" }

        /// The reference's subtitle, with the evidence attached so the claim is inspectable.
        var subtitle: String {
            "\(tool.name)'s \(feature) and this app both use \(chord.display). \(evidence.sentence)"
        }
    }

    /// What the user should change, and where.
    ///
    /// **We do not rewrite another product's configuration**, and the reference's one-click
    /// "Switch Codex to ⌥⌥" button is therefore not implemented as a write. Three reasons, all of
    /// them fatal to the button rather than to the feature:
    ///
    /// 1. **We could not tell the user the truth about whether it worked.** Codex registers its
    ///    global hotkey from an in-memory keymap and rewrites `keybindings.json` wholesale whenever a
    ///    binding changes. Writing that file under a running Codex leaves the old chord registered
    ///    until it relaunches, and clobbers our edit the next time the user changes anything. A
    ///    button that reports success while the conflict is still live is worse than no button.
    /// 2. **⌥⌥ is not free.** Claude's own Quick Entry defaults to a double tap of Option, so the
    ///    reference's specific remedy would trade one collision for another on this very machine.
    /// 3. It is the user's other app. Editing it silently is not ours to do.
    ///
    /// So the row states the collision, names the file, and offers to reveal it. Changing our own
    /// shortcut is the other half of the remedy, and that one *is* one click — it is our setting.
    struct Remedy: Equatable, Sendable {
        /// One sentence, imperative, naming the place.
        let instruction: String
        /// The file to reveal in Finder, when there is one.
        let revealPath: String?

        func reveal() {
            guard let revealPath else { return }
            NSWorkspace.shared.selectFile(revealPath, inFileViewerRootedAtPath: "")
        }
    }

    struct Report: Equatable, Sendable {
        let findings: [Tool: Finding]
        /// Empty unless something is genuinely, evidently in the way.
        let conflicts: [Conflict]
    }

    // MARK: - Where to look

    /// Every path the scan reads. Injectable so the tests can put real fixture files on disk and
    /// assert on what they produce, rather than asserting against whatever is installed on the
    /// machine running them.
    struct Locations: Sendable {
        var claudeApp: String
        var claudeConfig: String
        var codexApp: String
        var codexKeymap: String
        var codexGlobalState: String
        var cursorApp: String
        var cursorMainScript: String

        static func live(
            home: URL = URL(fileURLWithPath: NSHomeDirectory(), isDirectory: true),
            environment: [String: String] = ProcessInfo.processInfo.environment
        ) -> Locations {
            // `${CODEX_HOME:-$HOME/.codex}` — Codex's own spelling, lifted from the installed build.
            let codexHome = environment["CODEX_HOME"].flatMap { $0.isEmpty ? nil : $0 }
                ?? home.appendingPathComponent(".codex", isDirectory: true).path
            let support = home.appendingPathComponent("Library/Application Support", isDirectory: true)
            return Locations(
                claudeApp: "/Applications/Claude.app",
                claudeConfig: support.appendingPathComponent("Claude/config.json").path,
                codexApp: "/Applications/Codex.app",
                codexKeymap: URL(fileURLWithPath: codexHome).appendingPathComponent("keybindings.json").path,
                codexGlobalState: URL(fileURLWithPath: codexHome)
                    .appendingPathComponent(".codex-global-state.json").path,
                cursorApp: "/Applications/Cursor.app",
                cursorMainScript: "/Applications/Cursor.app/Contents/Resources/app/out/main.js")
        }
    }

    // MARK: - Scan

    /// - Parameter airgapMode: when on, nothing here reads another app's files at all.
    ///
    ///   No network is involved either way — every source is a local config file — but a user who has
    ///   asked the app to stop reaching outside itself did not have "reads Claude's and Codex's
    ///   settings" in mind, and the honest cost of respecting that is one row that says it cannot tell.
    ///   Driven by `ExclusionEngine.shared.current.airgapMode`; there is no second flag for it.
    static func scan(
        ours: [GlobalShortcuts.Action: ShortcutChord],
        at locations: Locations = .live(),
        airgapMode: Bool = ExclusionEngine.shared.current.airgapMode
    ) -> Report {
        guard !airgapMode else {
            let reason = "Airgap Mode is on, so I'm not reading other apps' settings."
            return Report(
                findings: Dictionary(uniqueKeysWithValues: Tool.allCases.map { ($0, .undetermined(reason: reason)) }),
                conflicts: [])
        }

        let findings: [Tool: Finding] = [
            .claudeDesktop: claudeDesktop(at: locations),
            .codex: codex(at: locations),
            .cursor: cursor(at: locations),
        ]

        var conflicts: [Conflict] = []
        // Stable order, so the row does not move between scans.
        for tool in Tool.allCases {
            guard case .bound(let feature, let binding, let evidence) = findings[tool] else { continue }
            for action in GlobalShortcuts.Action.allCases {
                guard let chord = ours[action], binding.collides(with: chord) else { continue }
                conflicts.append(
                    Conflict(
                        tool: tool,
                        action: action,
                        chord: chord,
                        feature: feature,
                        evidence: evidence,
                        remedy: remedy(for: tool, feature: feature, at: locations)))
            }
        }
        return Report(findings: findings, conflicts: conflicts)
    }

    // MARK: - Claude

    /// Claude's Quick Entry window is the one global shortcut it registers, and the value is a plain
    /// key in its own JSON config.
    ///
    /// The absent case matters more than it looks: Claude writes `quickEntryShortcut` only once the
    /// user changes it, so on a stock install the key is missing and the shipped fallback applies.
    /// That fallback is `double-tap-option` — ⌥⌥ — read out of the installed build's own default
    /// table. It is recorded here as a `shippedDefault` rather than a config read, because it is a
    /// weaker claim and the row says which one it is.
    private static let claudeQuickEntryDefault = "double-tap-option"
    private static let claudeDefaultNote =
        "Claude has not written this setting, so its shipped default applies — Quick Entry is a double tap of Option."

    private static func claudeDesktop(at locations: Locations) -> Finding {
        guard FileManager.default.fileExists(atPath: locations.claudeApp) else { return .notInstalled }

        let feature = "Quick Entry"
        guard let document = json(at: locations.claudeConfig) else {
            // No config at all is a Claude that has never run. Its default still applies.
            return .bound(
                feature: feature,
                binding: parseClaudeShortcut(claudeQuickEntryDefault) ?? ForeignBinding(display: "⌥⌥"),
                evidence: .shippedDefault(note: claudeDefaultNote))
        }

        guard let raw = document["quickEntryShortcut"] else {
            guard let binding = parseClaudeShortcut(claudeQuickEntryDefault) else {
                return .undetermined(reason: "Could not interpret Claude's default Quick Entry shortcut.")
            }
            return .bound(feature: feature, binding: binding, evidence: .shippedDefault(note: claudeDefaultNote))
        }

        if let word = raw as? String {
            if word == "off" {
                return .noGlobalBinding(reason: "Claude's Quick Entry shortcut is turned off.")
            }
            guard let binding = parseClaudeShortcut(word) else {
                return .undetermined(reason: "Claude's Quick Entry shortcut is a value I don't recognise.")
            }
            return .bound(feature: feature, binding: binding, evidence: .configFile(path: display(locations.claudeConfig)))
        }

        if let object = raw as? [String: Any], let accelerator = object["accelerator"] as? String {
            guard let binding = parseAccelerator(accelerator) else {
                return .undetermined(reason: "Claude's Quick Entry shortcut is a value I don't recognise.")
            }
            return .bound(feature: feature, binding: binding, evidence: .configFile(path: display(locations.claudeConfig)))
        }

        return .undetermined(reason: "Claude's Quick Entry shortcut is a value I don't recognise.")
    }

    /// The two spellings Claude's own config schema allows for a modifier gesture.
    private static func parseClaudeShortcut(_ word: String) -> ForeignBinding? {
        switch word {
        case "double-tap-option":
            return ForeignBinding(display: "⌥⌥", chord: .doubleTap(.option, alsoHeld: []))
        case "double-tap-capslock", "capslock":
            // Caps Lock is never part of one of our chords — we drop it out of every snapshot — so it
            // is bound, and it cannot collide.
            return ForeignBinding(display: "Caps Lock")
        default:
            return nil
        }
    }

    // MARK: - Codex

    /// The three Codex commands whose scope is the whole OS. Every other Codex binding is a menu or
    /// window shortcut and cannot collide with a global chord.
    ///
    /// None of them ships with a default binding — the command table in the installed build gives
    /// `defaultKeybindings` to menu commands only — so a Codex with no `keybindings.json` and no
    /// legacy value binds nothing system-wide. That is the *reason* the reference's "Codex also uses
    /// ⌘⌘" row must be conditional: on a stock Codex it is simply not true.
    private static let codexGlobalCommands: [String: String] = [
        "hotkeyWindow": "Popout Window",
        "globalDictationHold": "hold-to-dictate",
        "globalDictationToggle": "dictation toggle",
    ]

    private static func codex(at locations: Locations) -> Finding {
        guard FileManager.default.fileExists(atPath: locations.codexApp) else { return .notInstalled }

        let keymapExists = FileManager.default.fileExists(atPath: locations.codexKeymap)
        if keymapExists {
            guard let data = try? Data(contentsOf: URL(fileURLWithPath: locations.codexKeymap)),
                let entries = try? JSONSerialization.jsonObject(with: data) as? [[String: Any]]
            else {
                return .undetermined(reason: "Codex's keybindings.json would not parse.")
            }
            for entry in entries {
                guard let command = entry["command"] as? String,
                    let feature = codexGlobalCommands[command],
                    let key = entry["key"] as? String,
                    let binding = parseCodexKey(key)
                else { continue }
                return .bound(
                    feature: feature, binding: binding,
                    evidence: .configFile(path: display(locations.codexKeymap)))
            }
        }

        // The pre-keymap home of the popout window's chord. Still read, because a Codex that was
        // configured before the keymap existed has its value here and nowhere else.
        if let state = json(at: locations.codexGlobalState),
            let legacy = state["hotkeyWindowHotkey"] as? String,
            let binding = parseCodexKey(legacy) {
            return .bound(
                feature: "Popout Window", binding: binding,
                evidence: .configFile(path: display(locations.codexGlobalState)))
        }

        return .noGlobalBinding(
            reason: keymapExists
                ? "Codex's keybindings.json binds none of its three system-wide commands."
                : "Codex has no keybindings.json, and it ships no default binding for its system-wide commands.")
    }

    /// Codex accepts either an Electron accelerator or a bare-modifier name for these commands.
    ///
    /// The bare-modifier names and their normalisation (whitespace, `-` and `_` stripped, then
    /// lower-cased) are Codex's, taken from the alias table in the installed build.
    private static func parseCodexKey(_ key: String) -> ForeignBinding? {
        let normalized = key.replacingOccurrences(of: "[\\s_-]", with: "", options: .regularExpression).lowercased()
        if let bare = bareModifierNames[normalized] { return bare }
        return parseAccelerator(key)
    }

    /// Codex's bare-modifier vocabulary, mapped to what it means for us.
    ///
    /// The `left…+right…` spellings are Codex's own aliases for the double-tap monitors, not two keys
    /// pressed together — which is why they land on `.doubleTap` and not on `.bothCommandKeys`, even
    /// now that this app has a chord for exactly that gesture and `leftCommand+rightCommand` reads
    /// like a description of it. The alias table in the installed build is the evidence, and being
    /// wrong here would put a row in front of a user for a collision that cannot happen.
    private static let bareModifierNames: [String: ForeignBinding] = {
        var out: [String: ForeignBinding] = [:]
        let doubles: [(names: [String], modifier: ShortcutModifiers, display: String)] = [
            (["doublecommand", "leftcommand+rightcommand", "leftcmd+rightcmd", "leftmeta+rightmeta"], .command, "⌘⌘"),
            (["doubleoption", "doublealt", "leftoption+rightoption", "leftalt+rightalt"], .option, "⌥⌥"),
            (["doubleshift", "leftshift+rightshift"], .shift, "⇧⇧"),
        ]
        for double in doubles {
            for name in double.names {
                out[name] = ForeignBinding(
                    display: double.display, chord: .doubleTap(double.modifier, alsoHeld: []))
            }
        }
        // A single bare modifier. No chord of ours equals it, but it fires on the first half of a
        // double tap of the same key, which `collides(with:)` accounts for.
        let singles: [(names: [String], modifier: ShortcutModifiers, display: String)] = [
            (["leftcommand", "leftcmd", "leftmeta"], .command, "left ⌘"),
            (["rightcommand", "rightcmd", "rightmeta"], .command, "right ⌘"),
            (["leftoption", "leftalt"], .option, "left ⌥"),
            (["rightoption", "rightalt"], .option, "right ⌥"),
            (["leftcontrol", "leftctrl"], .control, "left ⌃"),
            (["rightcontrol", "rightctrl"], .control, "right ⌃"),
            (["leftshift"], .shift, "left ⇧"),
            (["rightshift"], .shift, "right ⇧"),
        ]
        for single in singles {
            for name in single.names {
                out[name] = ForeignBinding(display: single.display, bareModifier: single.modifier)
            }
        }
        out["fn"] = ForeignBinding(display: "fn")
        return out
    }()

    // MARK: - Cursor

    /// Cursor's shortcuts are VS Code shortcuts: they are delivered to a focused window, so they
    /// cannot take a chord away from the rest of the system.
    ///
    /// That is asserted rather than assumed. An Electron app reaches an OS-global chord through
    /// `globalShortcut`, so the check is whether Cursor's main process mentions it at all. If a
    /// future Cursor does, this reports `undetermined` and shows nothing — which is the correct
    /// answer to "it might, and I can't tell".
    private static func cursor(at locations: Locations) -> Finding {
        guard FileManager.default.fileExists(atPath: locations.cursorApp) else { return .notInstalled }
        guard let data = try? Data(contentsOf: URL(fileURLWithPath: locations.cursorMainScript)),
            let source = String(data: data, encoding: .utf8)
        else {
            return .undetermined(reason: "Could not read Cursor's main script.")
        }
        guard !source.contains("globalShortcut") else {
            return .undetermined(reason: "Cursor registers system-wide shortcuts, and I can't read which.")
        }
        return .noGlobalBinding(
            reason: "Cursor's shortcuts only fire while Cursor is focused — it registers none system-wide.")
    }

    // MARK: - Remedies

    private static func remedy(for tool: Tool, feature: String, at locations: Locations) -> Remedy {
        switch tool {
        case .claudeDesktop:
            return Remedy(
                instruction:
                    "Change Claude's \(feature) shortcut in Claude → Settings, or record a different one here.",
                revealPath: FileManager.default.fileExists(atPath: locations.claudeConfig)
                    ? locations.claudeConfig : nil)
        case .codex:
            return Remedy(
                instruction:
                    "Change Codex's \(feature) shortcut in Codex → Settings → General, or record a different one here.",
                revealPath: FileManager.default.fileExists(atPath: locations.codexKeymap)
                    ? locations.codexKeymap : nil)
        case .cursor:
            return Remedy(
                instruction: "Change the shortcut in Cursor's Keyboard Shortcuts, or record a different one here.",
                revealPath: nil)
        }
    }

    // MARK: - Plumbing

    private static func json(at path: String) -> [String: Any]? {
        guard let data = try? Data(contentsOf: URL(fileURLWithPath: path)), !data.isEmpty else { return nil }
        return try? JSONSerialization.jsonObject(with: data) as? [String: Any]
    }

    /// `~`-relative, so a row of copy and a log line never carry the user's name.
    private static func display(_ path: String) -> String {
        let home = URL(fileURLWithPath: NSHomeDirectory()).standardizedFileURL.path
        let standardized = URL(fileURLWithPath: path).standardizedFileURL.path
        guard standardized.hasPrefix(home + "/") else { return standardized }
        return "~/" + String(standardized.dropFirst(home.count + 1))
    }

    /// An Electron accelerator — the string form both Claude and Codex store a key equivalent in.
    ///
    /// `CmdOrCtrl` is Command here: this only ever runs on macOS.
    static func parseAccelerator(_ accelerator: String) -> ForeignBinding? {
        var modifiers: ShortcutModifiers = []
        var key: String?
        for rawToken in accelerator.split(separator: "+") {
            let token = rawToken.trimmingCharacters(in: .whitespaces)
            switch token.lowercased() {
            case "command", "cmd", "commandorcontrol", "cmdorctrl", "super", "meta":
                modifiers.insert(.command)
            case "control", "ctrl":
                modifiers.insert(.control)
            case "alt", "option":
                modifiers.insert(.option)
            case "shift":
                modifiers.insert(.shift)
            case "":
                continue
            default:
                // More than one non-modifier token is not an accelerator we understand.
                guard key == nil else { return nil }
                key = acceleratorKeyNames[token.lowercased()] ?? token.uppercased()
            }
        }
        guard let key, !modifiers.isEmpty else { return nil }
        let chord = ShortcutChord.key(label: key, modifiers: modifiers)
        return ForeignBinding(display: chord.display, chord: chord)
    }

    /// Only the names whose upper-cased form would not match what our own recorder stores.
    private static let acceleratorKeyNames: [String: String] = [
        "space": "Space",
        "tab": "⇥",
        "backspace": "⌫",
        "delete": "⌦",
        "left": "←",
        "right": "→",
        "up": "↑",
        "down": "↓",
        "home": "↖",
        "end": "↘",
        "pageup": "⇞",
        "pagedown": "⇟",
        "plus": "+",
    ]
}
