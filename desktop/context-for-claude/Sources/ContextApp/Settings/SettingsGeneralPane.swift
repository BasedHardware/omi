import AppKit
import ContextCore
import SwiftUI

/// General: the two shortcut recorders, the conflict row when there is one, launch at login, Airgap
/// Mode, and the version.
///
/// **There is no `Update Now` and no `Automatic Updates`, deliberately.** This package ships no
/// updater. Porting `desktop/macos/`'s Sparkle integration is not cheap: it needs the dependency in
/// `Package.swift`, `SUFeedURL` and `SUPublicEDKey` in `Resources/Info.plist`, an EdDSA signing key,
/// and a hosted appcast plus a release job that signs and publishes each zip — none of which exists
/// for this package, whose only distribution path today is `scripts/build.sh` copying into
/// `/Applications`. So the row states the real version and stops there. A disabled `Update Now` would
/// still advertise a feature that does not exist, which `I7` and `J7` both rule out.
struct SettingsGeneralPane: View {
    @ObservedObject var store: SettingsStore
    let shortcuts: ShortcutBindingProvider
    @ObservedObject var exclusions: ExclusionsObserver

    /// Bumped whenever the provider says something changed, which is what re-reads the recorders.
    @State private var shortcutGeneration = 0
    @State private var recording: ShortcutAction?
    @State private var rejection: String?
    @State private var isLaunchAtLoginOn = LoginItem.isEnabled

    var body: some View {
        SettingsPaneScroll {
            SettingsSection(title: "Shortcuts") {
                SettingsRowStack(items: ShortcutAction.allCases) { action in
                    SettingsRow(
                        icon: action.symbol,
                        title: action.title,
                        subtitle: action.subtitle
                    ) {
                        ShortcutRecorderField(
                            chord: shortcuts.binding(for: action),
                            fallback: action.defaultChord,
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

            SettingsSection(title: "Startup and privacy") {
                SettingsRow(
                    icon: "power",
                    title: "Launch on Login",
                    subtitle: "Whether the app automatically starts when you sign in to your computer."
                ) {
                    Toggle(
                        "",
                        isOn: Binding(
                            get: { isLaunchAtLoginOn },
                            set: { setLaunchAtLogin($0) })
                    )
                    .labelsHidden()
                    .toggleStyle(.switch)
                    .controlSize(.small)
                }

                SettingsRowDivider()

                SettingsRow(
                    icon: "airplane",
                    title: "Airgap Mode",
                    subtitle: "Suppresses telemetry, update checks, and remote favicon requests. "
                        + "Favicons stop immediately; the rest takes effect after relaunch."
                ) {
                    Toggle(
                        "",
                        isOn: Binding(
                            get: { exclusions.snapshot.airgapMode },
                            set: { enabled in
                                Sound.effect(.click)
                                ExclusionEngine.shared.setAirgapMode(enabled)
                            })
                    )
                    .labelsHidden()
                    .toggleStyle(.switch)
                    .controlSize(.small)
                }

                SettingsRowDivider()

                SettingsRow(
                    icon: "music.note",
                    title: "Sound",
                    subtitle: "Plays the ambient bed during the first-run sequence. "
                        + "Click sounds follow your system's interface-sound setting."
                ) {
                    Toggle(
                        "",
                        isOn: Binding(
                            get: { Sound.music.isEnabled },
                            set: { enabled in
                                Sound.music.isEnabled = enabled
                                if enabled { Sound.effect(.click) }
                            })
                    )
                    .labelsHidden()
                    .toggleStyle(.switch)
                    .controlSize(.small)
                }
            }

            SettingsSection(
                title: "About",
                footnote: "This build has no auto-updater, so there is nothing here to check for one. "
                    + "Reinstall from source to move to a newer version."
            ) {
                SettingsRow(
                    icon: "info.circle",
                    title: "Updates",
                    subtitle: AppVersion.display
                ) {
                    EmptyView()
                }
            }
        }
        .onAppear { isLaunchAtLoginOn = LoginItem.isEnabled }
        // `id` on the generation forces the recorders to re-read the provider after a record or clear
        // without this pane holding a second copy of the bindings.
        .id(shortcutGeneration)
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
                    .foregroundStyle(isCleared ? Ink.tertiary : Ink.primary)
                    .frame(minWidth: 62)
                    .padding(.horizontal, 8)
                    .padding(.vertical, 4)
                    .background(
                        RoundedRectangle(cornerRadius: 6, style: .continuous)
                            .fill(Ink.wash)
                    )
                    .overlay(
                        RoundedRectangle(cornerRadius: 6, style: .continuous)
                            .strokeBorder(isRecording ? Ink.accent : Ink.hairline, lineWidth: isRecording ? 2 : 1))
            }
            .buttonStyle(.plain)
            .help(isRecording ? "Press the shortcut, or Escape to stop" : "Click to record a shortcut")

            Button(action: clear) {
                Image(systemName: "xmark.circle.fill")
                    .font(.system(size: 11))
                    .foregroundStyle(Ink.tertiary)
            }
            .buttonStyle(.plain)
            .opacity(isCleared ? 0 : 1)
            .disabled(isCleared)
            .help("Clear it to use \(fallback.displayString)")
        }
        .onChange(of: isRecording) { _, recording in
            recording ? arm() : disarm()
        }
        .onDisappear(perform: disarm)
    }

    /// A cleared slot shows the default chord greyed, which is what "Clear it to use ⌘⌘" describes:
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
            guard event.keyCode != 53 else {
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
