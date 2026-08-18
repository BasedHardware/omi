import AppKit
import Carbon.HIToolbox
import ContextCore
import SwiftUI

/// General: the shortcut recorder, the conflict row when there is one, launch at login, the Dock
/// icon, and the version.
///
/// **Three rows this pane used to carry are gone, and none of them was a narrowing.** The Airgap
/// Mode and Sound switches were removed on the report *"remove the option to toggle sound and
/// airgap mode in settings"*; the machinery behind Airgap is untouched and still enforced by
/// `Backend/NetworkEgress.swift` for anyone whose `exclusions.json` already carries it, and the
/// cinematic keeps its own mute button, which is the surface where music is actually playing. The
/// third was a standing **Accessibility** section under the recorders, and it went because it could
/// not do its job: it appeared only when the grant was missing, offered a pane where this app was
/// not even listed, and read as an unexplained privacy row bolted to a keyboard section.
/// `GlobalShortcuts.askForAccessibility()` now raises the real system alert instead, which both
/// explains itself and lists the app. The recorder's own subtitle still says outright when the
/// chord cannot fire.
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

    /// **The four strings the reset row is made of**, internal for the same reason
    /// `SettingsStoragePane`'s three confirmation strings are: they are the whole of what the user
    /// is told before a press that takes over their screen for several minutes, and copy nothing reads
    /// is copy nothing can hold to its claims.
    ///
    /// Every clause of the subtitle is a promise `OnboardingReset` keeps: it clears three defaults and
    /// touches nothing else — no sign-out, no TCC call, no write to the capture database, no
    /// `context.settings.*` key. The sentence exists because "reset" is a word people reasonably read
    /// as "wipe", and a row that made them find out by pressing it would be the failure.
    static let resetSubtitle =
        "Starts the first-run experience over: the opening sequence, the onboarding cards, then the "
        + "walkthrough. Nothing is deleted — what you have captured, your settings, your permissions "
        + "and your sign-in all stay exactly as they are."

    /// **"Onboarding", not "setup", in all four strings and in the row's own title.** Reported as
    /// *"don't call it run setup again, call it run onboarding again or something"* — and the
    /// rename is the accurate word as well as the asked-for one: the button replays the first-run
    /// *experience* (the cinematic, the cards, the walkthrough), it does not re-run an installer or
    /// reconfigure anything.
    static let resetConfirmationTitle = "Run onboarding again?"

    /// Says what happens to the window the press came from, because it happens immediately and a
    /// window that vanishes without having been mentioned reads as a crash.
    static let resetConfirmationMessage =
        "Settings closes and the opening sequence starts, followed by the onboarding cards and the "
        + "walkthrough. It takes a few minutes, and you can leave at any point. Nothing is deleted: "
        + "your recordings, transcripts, settings, permissions and sign-in are untouched."

    static let resetConfirmationAction = "Run onboarding again"

    /// Bumped whenever the provider says something changed, which is what re-reads the recorders.
    @State private var shortcutGeneration = 0
    /// Whether the reset row's confirmation is on screen. Plain view state — see the modifier below.
    @State private var isConfirmingReset = false
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

            SettingsSection(title: "Startup") {
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

                // Moved here from the Appearance pane, which no longer exists. It never was an
                // appearance choice: it decides whether this app has a second home besides the menu
                // bar, which is a fact about how it starts and is found — the same question the row
                // above answers. `DockPresence` owns the default and the mapping either way.
                SettingsRow(
                    icon: "dock.rectangle",
                    title: "Show Dock Icon",
                    subtitle: "Keeps the app's icon visible in the Dock during normal use."
                ) {
                    SettingsToggle(
                        title: "Show Dock Icon", isOn: $store.showsDockIcon,
                        onChange: { _ in Sound.effect(.click) })
                }
            }

            // Its own section rather than a third row under "Startup": this one does not set a
            // preference, it starts something, and a button that takes over the screen for a few
            // minutes should not be sitting in a stack of switches.
            SettingsSection(title: "Onboarding") {
                SettingsRow(
                    icon: "arrow.counterclockwise",
                    title: Self.resetConfirmationAction,
                    subtitle: Self.resetSubtitle
                ) {
                    Button(Self.resetConfirmationAction) {
                        Sound.effect(.click)
                        isConfirmingReset = true
                    }
                    .controlSize(.small)
                }
            }

            SettingsSection(title: "About") {
                UpdatesSettingsRow(updater: ContextUpdater.shared)
            }
        }
        // **Asked before it happens**, because the cost of a mis-click is the whole flow: the intro,
        // six cards and the walkthrough, over a user who meant to press the row above.
        //
        // The presentation is bound to plain view state, unlike `SettingsStoragePane`'s — which binds
        // to its model with a no-op setter because SwiftUI is free to write `isPresented = false`
        // before it runs the tapped button's action, and there that ordering nulled the pending
        // selection the action was about to commit. Nothing here is parked anywhere: the action reads
        // no state at all, so there is nothing a dismissal can take out from under it.
        //
        // No `.destructive` role either, and that is a claim rather than an oversight — red in a macOS
        // dialog means data is about to go, and nothing here deletes anything. The message says so
        // outright, because "reset" is a word users have every reason to read as "wipe".
        .confirmationDialog(
            Self.resetConfirmationTitle,
            isPresented: $isConfirmingReset,
            titleVisibility: .visible
        ) {
            Button(Self.resetConfirmationAction) {
                Sound.effect(.click)
                OnboardingReset.restart()
            }
            Button("Cancel", role: .cancel) {}
        } message: {
            Text(Self.resetConfirmationMessage)
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

    /// Every slot's answer, for the "did anything move?" comparison above. An array rather than a
    /// dictionary because `ShortcutAction.allCases` fixes the order.
    private var readinessSnapshot: [ShortcutReadiness] {
        ShortcutAction.allCases.map { shortcuts.readiness(for: $0) }
    }

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

    /// Which arming of the shared monitor is this field's. Not the monitor itself: the token is the
    /// only thing a view is allowed to hold, so a view that goes away without disarming leaks
    /// nothing that `ShortcutRecorderMonitor` cannot reclaim on its own.
    @State private var armed: ShortcutRecorderMonitor.Armed?

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

    /// **Only the window the recorder is in, and never for longer than the recorder exists.**
    ///
    /// `addLocalMonitorForEvents` is a *process* monitor and every branch below returns `nil` — so an
    /// armed recorder used to swallow every keystroke in every window of this app. Concretely: while
    /// the field said "…", ⌘W would not close the timeline and **⌘Q would not quit**, because Quit
    /// was captured here, then rejected as a reserved chord, and the user was shown a rejection
    /// message for a key they meant for the application. `ShortcutRecorderMonitor` owns both halves
    /// of that now: which window may be heard, and that an abandoned monitor removes itself rather
    /// than waiting on a SwiftUI lifecycle callback this view cannot guarantee will run.
    private func arm() {
        armed = ShortcutRecorderMonitor.shared.arm { event in
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
        if let armed { ShortcutRecorderMonitor.shared.disarm(armed) }
        armed = nil
    }
}

// MARK: - How far an armed recorder reaches

/// Whether a key press belongs to the shortcut recorder, as a value.
///
/// **The recorder is the one control in this app that consumes raw key events**, and it does it
/// through `NSEvent.addLocalMonitorForEvents`, which is process-wide. Every window of this
/// application shares that monitor, so the question "is this keystroke mine" is the whole of
/// whether an armed field is a text input or an app-wide keyboard outage.
///
/// Split out from the closure because none of it can be produced in a headless suite — an `NSEvent`
/// carries a window this test bundle has no way to make key — and because the rule is one sentence
/// that has to survive being reread: **a recorder only ever hears the window it is drawn in.**
@MainActor
enum ShortcutRecorderScope {

    /// - Parameter eventWindow: `NSEvent.window`. **`nil` is not ours**: a key event with no window
    ///   was not delivered to a window of this app at all, and consuming it would be the process-wide
    ///   swallow this type exists to stop.
    /// - Parameter settingsWindow: injected rather than read, so the rule is assertable without a
    ///   Settings window on screen. Production passes the real one.
    static func belongsToTheRecorder(_ eventWindow: NSWindow?, settingsWindow: NSWindow?) -> Bool {
        guard let eventWindow, let settingsWindow else { return false }
        return eventWindow === settingsWindow
    }
}
