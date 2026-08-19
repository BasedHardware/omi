import AppKit
import ContextCore
import SwiftUI

/// Agents: how Claude is opened, and whether Claude can reach this app at all.
///
/// **A third section, "Detected on this Mac", is gone.** It surveyed the machine for Claude Code,
/// Claude Desktop, Codex and Cursor and drew a row per surface with an Installed / Configured /
/// Not found pill. Every row was read-only: nothing on this pane acts on the survey, and the two
/// surfaces this app actually registers with are named by the tip above it either way — so it was
/// a list the user could not do anything with, in the pane where the two controls that do something
/// live. Removed on the report *"remove the detected on this mac from UI in settings"*.
///
/// The reference's third row is a toggle that installs a `coast` CLI into `~/.local/bin`. We ship no
/// CLI — `docs/rewind-and-settings.md` says outright that our equivalent is the MCP registration — so
/// the row is `ClaudeRegistrar`, which is the machinery that actually gives an agent access to this
/// data. That is a real toggle with a real effect on disk (`~/.claude.json`, Claude Desktop's
/// `claude_desktop_config.json`) rather than a second, invented one.
///
/// The reference's *first* row, "Route to Agent", is absent for the opposite reason: nothing read the
/// preference it wrote, and its subtitle advertised a ⌘↵ chord `SearchBarView` does not implement,
/// routing to a path this product deliberately removed. See `SettingsPreferences`.
struct SettingsAgentsPane: View {
    @ObservedObject var store: SettingsStore

    /// Nil until the probe below has answered.
    ///
    /// It used to be `= ClaudeRegistrar.status()`, which opens and JSON-parses `~/.claude.json` and
    /// Claude Desktop's config **synchronously in `View.init`** — and SwiftUI re-inits a view body's
    /// struct freely, so two file reads rode along with every unrelated state change on this pane.
    /// It is a disk probe like the other two here, so it belongs where they are.
    @State private var registration: ClaudeConnection?
    @State private var registrationMessage: String?
    /// Bumped by each attempt so the expiry below restarts rather than clearing a newer message.
    @State private var registrationMessageAttempt = 0
    @State private var isRegistering = false
    /// What each Claude target would really do *on this Mac*, from `ClaudeRouter`'s own probe. Nil
    /// until it has answered, which is one frame — see `targetSubtitle` for what stands in.
    @State private var targetDetail: String?

    /// How long the result of a connect/disconnect stays under the section.
    ///
    /// It is feedback about something the user just did, not a description of the row, so it has to
    /// expire: without this it replaced the standing explanation of what the toggle writes for as
    /// long as the pane stayed open, and a sentence in the past tense reads as the present one.
    private static let registrationMessageLifetime: Duration = .seconds(12)

    var body: some View {
        SettingsPaneScroll {
            SettingsSection(title: "Routing") {
                SettingsRow(
                    icon: "macwindow",
                    title: "Claude target",
                    subtitle: targetSubtitle
                ) {
                    // Titled, then `labelsHidden()`: the row's own title is the label a sighted user
                    // reads, and the empty string this used to carry was also the accessibility
                    // label — leaving VoiceOver to announce an unnamed picker. Same fix, same
                    // reason, as `SettingsToggle`.
                    Picker("Claude target", selection: $store.claudeTarget) {
                        ForEach(ClaudeRouter.Target.allCases, id: \.self) { Text($0.title).tag($0) }
                    }
                    .labelsHidden()
                    .frame(width: 150)
                    .controlSize(.small)
                }
            }

            SettingsSection(
                title: "Access",
                // **Names all three things the switch writes.** It used to say "writes only the one
                // entry, into Claude's own config", which was already understating it — a skill has
                // been installed alongside the registration for some time — and the standing
                // instruction in the user's global `CLAUDE.md` makes the omission a real one: that
                // file is loaded into every prompt they run, so a switch that edits it has to say
                // so where it is switched. All three are removed again on disconnect.
                footnote: registrationMessage
                    ?? "Registers this app's MCP server so Claude can read what was captured, "
                    + "installs a skill in ~/.claude/skills, and adds a block to your global "
                    + "~/.claude/CLAUDE.md telling Claude to check this Mac's context before "
                    + "answering. Nothing else in those files is touched, and disconnecting "
                    + "removes all three."
            ) {
                SettingsRow(
                    icon: "point.3.connected.trianglepath.dotted",
                    title: "Claude Connection",
                    subtitle: connectionSubtitle
                ) {
                    // The spinner also covers "not read yet": a switch drawn off while the config
                    // is still being parsed states a connection status we do not have, and the user
                    // would see it flip under their hand a moment later.
                    if isRegistering || registration == nil {
                        ProgressView().controlSize(.small)
                    } else {
                        SettingsToggle(
                            title: "Claude Connection",
                            isOn: Binding(
                                get: {
                                    // Registration, not reachability: the switch's job is whether
                                    // this app has written itself into Claude's config, and a
                                    // Claude Desktop that has not restarted yet has not undone
                                    // that. Flipping the switch off under the user because their
                                    // Claude is stale would offer disconnecting as the cure for
                                    // needing a restart.
                                    registration?.claudeCode == true || registration?.claudeDesktop == true
                                },
                                set: { setRegistered($0) }))
                    }
                }
            }

            // The tip line, then the illustrative mock beneath it.
            VStack(alignment: .leading, spacing: 8) {
                // Names only the two surfaces `ClaudeRegistrar` actually writes. It used to say
                // "Claude Code, Codex or Cursor": nothing in this package writes a Codex or a Cursor
                // MCP config and we ship no CLI, so two thirds of that sentence described work the
                // user would have had to do by hand without being told.
                Text(
                    "Once connected, you can use Context for Claude directly inside Claude Code and "
                        + "Claude Desktop by mentioning it in your prompt. Those are the two surfaces "
                        + "this app registers itself with."
                )
                .font(.system(size: 11))
                .foregroundStyle(Ink.secondary)
                .fixedSize(horizontal: false, vertical: true)
                .padding(.horizontal, 4)

                AgentPromptMock()
            }

        }
        .task {
            // Every probe on this pane touches the disk or LaunchServices, and none of them belongs
            // in `body` or in a `@State` initialiser — SwiftUI runs both far more often than once,
            // so a probe placed there is a file read per unrelated state change. Here they run once
            // per appearance instead. The registrar's two JSON parses go off the main actor as well,
            // because they are the only ones that open and decode a file.
            targetDetail = ClaudeRouter.targetSubtitle(surface: ClaudeHandoff.surface)
            registration = await Task.detached(priority: .userInitiated) {
                ClaudeConnection.current()
            }.value
        }
        // The result of the last connect/disconnect, expired rather than pinned. `.task(id:)`
        // restarts on each attempt, so a newer message is never cleared by an older sleep.
        .task(id: registrationMessageAttempt) {
            guard registrationMessage != nil else { return }
            try? await Task.sleep(for: Self.registrationMessageLifetime)
            guard !Task.isCancelled else { return }
            registrationMessage = nil
        }
    }

    /// The Claude-target row's subtitle: what the choice governs, then what each option would really
    /// do on this Mac.
    ///
    /// The second half comes from `ClaudeRouter` rather than from a sentence typed here, because the
    /// true answer is machine-specific — which app answers `claude://`, whether there is a `claude`
    /// on the PATH this app can see, which terminal opens `.command` files — and a hard-coded
    /// description would be wrong on somebody's Mac and have no way of knowing. It asks about
    /// `ClaudeHandoff.surface` specifically: the row must describe the surface the handoff really
    /// opens, and this pane naming a different one would be the same defect in reverse.
    private var targetSubtitle: String {
        let lead = "Where your question goes when I hand one to Claude for you."
        guard let targetDetail else { return lead }
        return "\(lead) \(targetDetail)"
    }

    private var connectionSubtitle: String {
        Self.connectionSubtitle(registration)
    }

    /// The row's subtitle, as a function of the probe's answer.
    ///
    /// `static` and not a computed property on the view, for the reason `ClaudeConnectorLine` is a
    /// value: this sentence is the one place the pane makes a claim about somebody else's process,
    /// and it shipped making a false one — `Connected to Claude Code and Claude Desktop.` over a
    /// Claude Desktop whose server had failed to spawn at every launch for three days. A claim that
    /// wrong has to be reachable from a test, and a `private var` on a `View` is not.
    static func connectionSubtitle(_ connection: ClaudeConnection?) -> String {
        guard let connection else { return "Checking whether Claude is connected…" }
        // `desktopIsReachable`, so a registration Claude Desktop has not picked up is never
        // reported as a working connection. The remedy is appended rather than replacing the
        // sentence: what is connected and what is pending are both facts the user needs.
        let connected = switch (connection.claudeCode, connection.desktopIsReachable) {
        case (true, true): "Connected to Claude Code and Claude Desktop."
        case (true, false): "Connected to Claude Code."
        case (false, true): "Connected to Claude Desktop."
        case (false, false): "Not connected. Claude cannot read anything captured here yet."
        }
        guard let notice = connection.restartNotice else { return connected }
        return "\(connected) \(notice)"
    }

    /// Connect or disconnect, off the main actor, in the same shape as the probe in `.task` above.
    ///
    /// **The spinner is why this is async.** `isRegistering = true` … `register()` … `status()` …
    /// `isRegistering = false` ran as one straight-line main-actor job with no suspension point in
    /// it, so SwiftUI never got a chance to draw a frame between the first assignment and the last:
    /// the spinner this method exists to show was mathematically unreachable. What it hid is two
    /// files read, JSON-decoded and rewritten — `~/.claude.json`, which is Claude Code's own state
    /// store and grows with the user's history rather than with anything we write, and Claude
    /// Desktop's config — so the window froze under the click for however long that took on that
    /// Mac. No size is asserted here because it is not ours to predict; the defect is that the work
    /// is synchronous on the actor that has to draw, which is true at any size. The same commit
    /// already moved the identical `status()` call off the main actor at `.task` and gave the reason
    /// there; a second call site doing it the other way is the inconsistency, not a second opinion.
    ///
    /// `Task { … }` then `Task.detached` inside it, matching `SettingsStoragePane.measure()`: the
    /// outer task's `await` is the suspension point that lets the spinner render, and the detached
    /// one is what keeps the file work off the main actor. Both `@State` writes happen after the
    /// awaits, back on the actor the outer task started on.
    private func setRegistered(_ enabled: Bool) {
        Sound.effect(.click)
        isRegistering = true
        // Cleared first: the previous outcome must not sit under a spinner describing the attempt
        // that is running now.
        registrationMessage = nil
        Task {
            let result = await Task.detached(priority: .userInitiated) {
                enabled ? ClaudeRegistrar.register() : ClaudeRegistrar.unregister()
            }.value
            registrationMessage = result.message
            registrationMessageAttempt += 1
            // Re-read rather than trusting `result`: the registrar reports what it *did*, and the row
            // states what is *on disk*. A write that half-succeeded must show the disk's answer.
            registration = await Task.detached(priority: .userInitiated) {
                ClaudeConnection.current()
            }.value
            isRegistering = false
        }
    }
}

/// The illustrative mock of an agent prompt box.
///
/// Labelled `Example` and drawn in the app's own chrome rather than as a screenshot of Claude, because
/// a convincing fake of another product's UI is the kind of staged payoff `J7` rules out. It shows a
/// sample question and nothing that can be typed into.
struct AgentPromptMock: View {
    var body: some View {
        VStack(alignment: .leading, spacing: 7) {
            HStack(spacing: 6) {
                Image(systemName: "chevron.right")
                    .font(.system(size: 9, weight: .bold))
                    .foregroundStyle(Ink.secondary)
                Text("What was I working on before lunch yesterday?")
                    .font(.system(size: 11))
                    .foregroundStyle(Ink.primary)
                Spacer(minLength: 0)
                Text("Example")
                    .font(.system(size: 9, weight: .semibold))
                    .foregroundStyle(Ink.secondary)
                    .padding(.horizontal, 5)
                    .padding(.vertical, 1)
                    .background(Capsule().fill(Ink.wash))
            }
            Divider()
            HStack(spacing: 6) {
                Image(systemName: "sparkles")
                    .font(.system(size: 9))
                    .foregroundStyle(Ink.secondary)
                Text("Context for Claude · recall")
                    .font(.system(size: 10, design: .monospaced))
                    .foregroundStyle(Ink.secondary)
            }
        }
        .padding(11)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(
            RoundedRectangle(cornerRadius: SettingsMetrics.cardRadius, style: .continuous)
                .fill(Ink.wash)
        )
        .overlay(
            RoundedRectangle(cornerRadius: SettingsMetrics.cardRadius, style: .continuous)
                .strokeBorder(Ink.separator, style: StrokeStyle(lineWidth: 1, dash: [3, 3]))
        )
        .accessibilityLabel(
            Text("Example agent prompt: What was I working on before lunch yesterday?"))
    }
}
