import AppKit
import Carbon.HIToolbox
import ContextCore
import SwiftUI

/// General: the two shortcut recorders, the conflict row when there is one, launch at login, Airgap
/// Mode, and the version.
///
/// **The Updates row is live, and on most builds it says so by refusing to be.** `ContextUpdater`
/// answers `UpdatePolicy` before Sparkle is ever constructed, and the policy turns the updater off
/// for any bundle signed without a Team ID — which is every local `scripts/build.sh` install. So the
/// row a developer sees states the version and explains why it will not check, while the row a
/// Developer ID build shows offers a real check against this app's own appcast. Neither advertises a
/// feature that is not there, which is what `I7` and `J7` actually ask for.
struct SettingsGeneralPane: View {
    @ObservedObject var store: SettingsStore
    let shortcuts: ShortcutBindingProvider
    @ObservedObject var exclusions: ExclusionsObserver

    /// The Airgap row's subtitle, lifted out of `body` for the same reason `SettingsStoragePane`
    /// lifts its three confirmation strings out: it is the whole of the promise this switch makes,
    /// and a promise no test can read is a promise nothing holds to its claims. See the row below
    /// for why each clause is worded as it is.
    static let airgapSubtitle =
        "Stops this app from reaching the network: no screen or conversation uploads, no cloud "
        + "transcription, no favicon requests, and no signing in. Capture, transcription, and search "
        + "keep working on this Mac, and anything waiting to upload stays queued until you turn this "
        + "off. It does not restrict Claude: the MCP tools still read what was captured here, so "
        + "whatever you ask Claude about still reaches Anthropic."

    /// Bumped whenever the provider says something changed, which is what re-reads the recorders.
    @State private var shortcutGeneration = 0
    @State private var recording: ShortcutAction?
    @State private var rejection: String?
    @State private var isLaunchAtLoginOn = LoginItem.isEnabled
    /// The readiness the rows were last drawn with, so an activation that changed nothing does not
    /// rebuild the pane out from under the user's scroll position.
    @State private var lastReadiness: [ShortcutReadiness] = []

    var body: some View {
        SettingsPaneScroll {
            SettingsSection(title: "Shortcuts") {
                SettingsRowStack(items: ShortcutAction.allCases) { action in
                    SettingsRow(
                        icon: action.symbol,
                        title: action.title,
                        // The row says outright when the chord beside it cannot fire. Appended to
                        // the standing subtitle rather than replacing it, because "clear it to use
                        // ⌘ + ⌘" is still true — it is the *firing* that is not.
                        subtitle: subtitle(for: action)
                    ) {
                        ShortcutRecorderField(
                            chord: shortcuts.binding(for: action),
                            fallback: action.defaultChord,
                            isArmed: shortcuts.readiness(for: action).isArmed,
                            isRecording: recording == action,
                            beginRecording: { begin(action) },
                            capture: { capture($0, for: action) },
                            cancelRecording: { recording = nil },
                            clear: { clear(action) })
                    }
                }
            }

            if let rejection {
                Text(rejection)
                    .font(.system(size: 11))
                    .foregroundStyle(Ink.errorRed)
                    .padding(.horizontal, 4)
            }

            // The one press that fixes the state the rows have just reported. Offered only when
            // Accessibility is what is missing: a refused key equivalent is not repaired by opening
            // a privacy pane, and a button that cannot help is worse than no button.
            if needsAccessibility {
                SettingsSection {
                    SettingsRow(
                        icon: "hand.raised",
                        title: "Accessibility",
                        subtitle: Self.accessibilitySubtitle
                    ) {
                        Button("Open Accessibility Settings") {
                            Sound.effect(.click)
                            Permissions.openSettings(for: .accessibility)
                        }
                        .controlSize(.small)
                    }
                }
            }

            // Shown **only** on a live conflict. The provider is asked every time the pane renders
            // rather than a flag being persisted: a stored conflict would keep this row on screen
            // after the user uninstalled the other tool.
            let conflicts = shortcuts.conflicts()
            if !conflicts.isEmpty {
                SettingsSection(title: "Conflicts") {
                    SettingsRowStack(items: conflicts) { conflict in
                        SettingsRow(
                            icon: "exclamationmark.triangle",
                            title: conflict.title,
                            subtitle: conflict.subtitle
                        ) {
                            if let remedy = conflict.remedyTitle {
                                Button(remedy) {
                                    Sound.effect(.click)
                                    shortcuts.resolve(conflict)
                                    shortcutGeneration += 1
                                }
                                .buttonStyle(.borderedProminent)
                                .controlSize(.small)
                            }
                        }
                    }
                }
            }

            SettingsSection(title: "Startup and privacy") {
                SettingsRow(
                    icon: "power",
                    title: "Launch on Login",
                    subtitle: "Whether the app automatically starts when you sign in to your computer."
                ) {
                    SettingsToggle(
                        title: "Launch on Login",
                        isOn: Binding(
                            get: { isLaunchAtLoginOn },
                            set: { setLaunchAtLogin($0) }))
                }

                SettingsRowDivider()

                // The subtitle is the promise, so it names exactly what stops and what that costs.
                // It used to advertise "telemetry, update checks, and remote favicon requests" —
                // update checks do not exist in this build, telemetry never leaves this Mac in the
                // first place (`Support/Telemetry.swift`), and meanwhile the app went on uploading
                // the contents of the user's screen every sixty seconds. Every clause below is now
                // enforced in code by `Backend/NetworkEgress.swift`, and all of it is immediate:
                // there is nothing left here that waits for a relaunch.
                //
                // **It no longer opens with "Stops all network access", because that was false.**
                // What the switch is enforced against is this app's own remote clients — every case
                // of `NetworkEgress.Client`, the update check included — plus the one living in the
                // MCP server, `OmiBackend`, which `ContextMCPKit/Airgap.swift` suppresses in that
                // separate process. What it is *not* enforced against, deliberately, is that same
                // server's local tools: `recall`, `screen`, `activity` and the rest read this Mac's
                // own capture database, and `Airgap.swift` states the reason — suppressing them
                // "costs a tool its account half and never its answer". So a user with the switch
                // on who asks Claude what they were working on gets an answer assembled from OCR'd
                // screen text, and Claude carries that text to Anthropic as part of the conversation
                // the user opened. That is the product behaving as designed. A subtitle that claimed
                // no network access while it happened was the defect, so the last sentence says it
                // outright instead of leaving the user to infer it — the switch bounds what *this
                // app* sends on its own initiative, not what Claude sends when asked.
                SettingsRow(
                    icon: "airplane",
                    title: "Airgap Mode",
                    subtitle: Self.airgapSubtitle
                ) {
                    SettingsToggle(
                        title: "Airgap Mode",
                        isOn: Binding(
                            get: { exclusions.snapshot.airgapMode },
                            set: { ExclusionEngine.shared.setAirgapMode($0) }),
                        onChange: { _ in Sound.effect(.click) })
                }

                SettingsRowDivider()

                SettingsRow(
                    icon: "music.note",
                    title: "Sound",
                    subtitle: "Plays the ambient bed during the first-run sequence. "
                        + "Click sounds follow your system's interface-sound setting."
                ) {
                    SettingsToggle(
                        title: "Sound",
                        isOn: Binding(
                            get: { Sound.music.isEnabled },
                            set: { enabled in
                                Sound.music.isEnabled = enabled
                                if enabled { Sound.effect(.click) }
                            }))
                }
            }

            SettingsSection(title: "About") {
                UpdatesSettingsRow(updater: ContextUpdater.shared)
            }
        }
        .onAppear {
            isLaunchAtLoginOn = LoginItem.isEnabled
            // Accessibility can have been granted since this window was last built, and the readiness
            // rows above are only as fresh as the registration behind them.
            GlobalShortcuts.shared.refresh()
            lastReadiness = readinessSnapshot
        }
        // Coming back to the app is the whole of the signal that a permission changed: it is granted
        // in System Settings and macOS posts nothing when it happens. `GlobalShortcuts` and
        // `LiveShortcutBindings` both re-arm on this notification; this is what makes the rows say so.
        //
        // The generation is bumped **only when an answer actually moved**, because bumping it rebuilds
        // the pane through `.id` and that puts the scroll position back at the top. Re-activating the
        // app is something a user does constantly with a settings window open, and a pane that jumped
        // every time would be a worse bug than the one this is fixing.
        .onReceive(NotificationCenter.default.publisher(for: NSApplication.didBecomeActiveNotification)) {
            _ in
            isLaunchAtLoginOn = LoginItem.isEnabled
            GlobalShortcuts.shared.refresh()
            let current = readinessSnapshot
            guard current != lastReadiness else { return }
            lastReadiness = current
            shortcutGeneration += 1
        }
        // `id` on the generation forces the recorders to re-read the provider after a record or clear
        // without this pane holding a second copy of the bindings.
        .id(shortcutGeneration)
    }

    // MARK: - Readiness

    // Internal rather than private, like `SettingsStoragePane`'s three confirmation strings and for
    // the same reason: this is the only warning the user gets that a shortcut they can see does not
    // work, and copy nothing reads is copy nothing can hold to its claims. A sentence built inside
    // `body` is not reachable from a test, which is how the pane went on printing `⌘ + ⌘` over a
    // dead gesture with a full suite passing.

    /// Reference copy plus the truth about whether the chord fires, in that order.
    func subtitle(for action: ShortcutAction) -> String {
        guard let note = shortcuts.readiness(for: action).note else { return action.subtitle }
        return "\(action.subtitle) \(note)"
    }

    var needsAccessibility: Bool {
        ShortcutAction.allCases.contains { shortcuts.readiness(for: $0) == .needsAccessibility }
    }

    /// Both slots' answers, for the "did anything move?" comparison above. An array rather than a
    /// dictionary because there are two of them and `ShortcutAction.allCases` fixes the order.
    private var readinessSnapshot: [ShortcutReadiness] {
        ShortcutAction.allCases.map { shortcuts.readiness(for: $0) }
    }

    /// Why the app cannot simply ask. Accessibility has no system prompt — the only route is the
    /// Settings row — which is why this is a button that opens a pane rather than one that requests.
    static let accessibilitySubtitle =
        "The gesture shortcuts are watched for system-wide, and macOS only allows that with "
        + "Accessibility granted. There is no prompt for it: switch Context for Claude on in "
        + "Privacy & Security ▸ Accessibility, then come back. A shortcut you record with a key in "
        + "it works without this."

    // MARK: - Shortcuts

    private func begin(_ action: ShortcutAction) {
        Sound.effect(.click)
        rejection = nil
        recording = action
    }

    private func capture(_ chord: SettingsShortcutChord, for action: ShortcutAction) {
        recording = nil
        switch shortcuts.record(chord, for: action) {
        case .recorded:
            Sound.effect(.click)
            rejection = nil
        case .rejected(let reason):
            rejection = reason
        }
        shortcutGeneration += 1
    }

    private func clear(_ action: ShortcutAction) {
        Sound.effect(.click)
        rejection = nil
        shortcuts.clear(action)
        shortcutGeneration += 1
    }

    // MARK: - Login item

    /// Reads the live system state back rather than trusting the write: `SMAppService` can succeed and
    /// still land in `requiresApproval`, and a toggle that showed on while macOS held the item would
    /// be lying about a state the user has to go and fix in System Settings.
    private func setLaunchAtLogin(_ enabled: Bool) {
        Sound.effect(.click)
        if enabled {
            LoginItem.enable()
        } else {
            LoginItem.disable()
        }
        isLaunchAtLoginOn = LoginItem.isEnabled
    }
}

// MARK: - The recorder

/// A shortcut field: shows the chord, records a new one on click, and clears back to the default.
///
/// It captures the chord with a local `NSEvent` monitor while armed, and hands it to the provider — it
/// never registers anything globally itself. Registration is the shortcut layer's job, and a recorder
/// that installed its own hotkey would be a second owner of the same chord.
struct ShortcutRecorderField: View {
    let chord: SettingsShortcutChord?
    let fallback: SettingsShortcutChord
    /// Whether the chord printed here will actually fire. A field that looks identical armed and
    /// dead is a field that lies about the one thing it is for.
    var isArmed: Bool = true
    let isRecording: Bool
    let beginRecording: () -> Void
    let capture: (SettingsShortcutChord) -> Void
    let cancelRecording: () -> Void
    let clear: () -> Void

    @State private var monitor: Any?

    var body: some View {
        HStack(spacing: 4) {
            Button(action: beginRecording) {
                Text(label)
                    .font(.system(size: 11, weight: .semibold, design: .monospaced))
                    .foregroundStyle(isCleared || !isArmed ? Ink.secondary : Ink.primary)
                    .frame(minWidth: 62)
                    .padding(.horizontal, 8)
                    .padding(.vertical, 4)
                    .background(
                        RoundedRectangle(cornerRadius: 6, style: .continuous)
                            .fill(Ink.wash)
                    )
                    .overlay(
                        RoundedRectangle(cornerRadius: 6, style: .continuous)
                            .strokeBorder(border, lineWidth: isRecording ? 2 : 1))
            }
            .buttonStyle(.plain)
            .help(helpText)
            .accessibilityLabel(Text("Shortcut"))
            .accessibilityValue(Text(accessibilityValue))

            Button(action: clear) {
                Image(systemName: "xmark.circle.fill")
                    .font(.system(size: 11))
                    .foregroundStyle(Ink.secondary)
            }
            .buttonStyle(.plain)
            .opacity(isCleared ? 0 : 1)
            .disabled(isCleared)
            .help("Clear it to use \(fallback.displayString)")
            .accessibilityLabel(Text("Clear shortcut"))
            .accessibilityHidden(isCleared)
        }
        .onChange(of: isRecording) { _, recording in
            recording ? arm() : disarm()
        }
        // Rebuilt views arrive with `isRecording` already true and no `onChange` to fire — the pane
        // re-`id`s itself on every record, clear and app activation. Without this the field would go
        // on showing "…" over a monitor that had been torn down with the previous instance.
        .onAppear { if isRecording { arm() } }
        .onDisappear(perform: disarm)
    }

    /// Red for a chord that cannot fire, so the field carries the state as well as the copy under
    /// it. `Ink.errorRed` and never a purple — see `INV-UI-1`.
    private var border: Color {
        if isRecording { return Ink.accent }
        return isArmed ? Ink.hairline : Ink.errorRed
    }

    private var helpText: String {
        if isRecording { return "Press the shortcut, or Escape to stop" }
        if !isArmed { return "This shortcut is not active. Click to record one that is." }
        return "Click to record a shortcut"
    }

    /// Spoken, not glyphs. `⌘ + ⌘` reads out as three symbols and none of the meaning, which is what
    /// `SettingsShortcutChord.spokenDescription` exists for.
    private var accessibilityValue: String {
        if isRecording { return "Recording" }
        let spoken = (chord ?? fallback).spokenDescription
        return isArmed ? spoken : "\(spoken), not active"
    }

    /// A cleared slot shows the default chord greyed, which is what "Clear it to use ⌘ + ⌘" describes:
    /// the shortcut still works, it is just not a recorded override.
    private var isCleared: Bool { chord == nil }

    private var label: String {
        if isRecording { return "…" }
        return (chord ?? fallback).displayString
    }

    private func arm() {
        disarm()
        monitor = NSEvent.addLocalMonitorForEvents(matching: [.keyDown]) { event in
            // Escape abandons the recording rather than binding ⎋, which nothing should be bound to.
            // Named rather than `53`, and it is the same constant `GlobalShortcuts.Recorded`
            // refuses on the other path — two spellings of one key code is how the recorder and the
            // registrar drift into disagreeing about what may be bound.
            guard event.keyCode != UInt16(kVK_Escape) else {
                cancelRecording()
                return nil
            }
            let modifiers = event.modifierFlags.intersection(.deviceIndependentFlagsMask)
            // A bare key is not a global shortcut; requiring a modifier is what stops the user
            // binding "k" and losing the letter everywhere.
            guard !modifiers.isEmpty else { return nil }
            capture(SettingsShortcutChord(keyCode: event.keyCode, modifierFlags: modifiers))
            return nil
        }
    }

    private func disarm() {
        if let monitor { NSEvent.removeMonitor(monitor) }
        monitor = nil
    }
}
