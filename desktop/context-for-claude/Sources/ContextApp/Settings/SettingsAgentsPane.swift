import AppKit
import ContextCore
import SwiftUI

/// Agents: where a query goes, how Claude is opened, whether Claude can reach this app at all, and
/// which agent surfaces are genuinely on this Mac.
///
/// The reference's third row is a toggle that installs a `coast` CLI into `~/.local/bin`. We ship no
/// CLI — `docs/rewind-and-settings.md` says outright that our equivalent is the MCP registration — so
/// the row is `ClaudeRegistrar`, which is the machinery that actually gives an agent access to this
/// data. That is a real toggle with a real effect on disk (`~/.claude.json`, Claude Desktop's
/// `claude_desktop_config.json`) rather than a second, invented one.
struct SettingsAgentsPane: View {
    @ObservedObject var store: SettingsStore

    @State private var registration = ClaudeRegistrar.status()
    @State private var registrationMessage: String?
    @State private var isRegistering = false
    @State private var survey: [(surface: AgentSurface, presence: AgentPresence)] = []
    /// What each Claude target would really do *on this Mac*, from `ClaudeRouter`'s own probe. Nil
    /// until it has answered, which is one frame — see `targetSubtitle` for what stands in.
    @State private var targetDetail: String?

    var body: some View {
        SettingsPaneScroll {
            SettingsSection(title: "Routing") {
                SettingsRow(
                    icon: "arrow.turn.down.right",
                    title: "Route to Agent",
                    subtitle: "With ⌘↵ you can send your query directly to your agents."
                ) {
                    Picker("", selection: $store.agentRoute) {
                        ForEach(AgentRoute.allCases) { Text($0.title).tag($0) }
                    }
                    .labelsHidden()
                    .frame(width: 150)
                    .controlSize(.small)
                }

                SettingsRowDivider()

                SettingsRow(
                    icon: "macwindow",
                    title: "Claude target",
                    subtitle: targetSubtitle
                ) {
                    Picker("", selection: $store.claudeTarget) {
                        ForEach(ClaudeRouter.Target.allCases, id: \.self) { Text($0.title).tag($0) }
                    }
                    .labelsHidden()
                    .frame(width: 150)
                    .controlSize(.small)
                }
            }

            SettingsSection(
                title: "Access",
                footnote: registrationMessage
                    ?? "Registers this app's MCP server so Claude can read what was captured. "
                    + "Writes only the one entry, into Claude's own config."
            ) {
                SettingsRow(
                    icon: "point.3.connected.trianglepath.dotted",
                    title: "Claude Connection",
                    subtitle: connectionSubtitle
                ) {
                    if isRegistering {
                        ProgressView().controlSize(.small)
                    } else {
                        Toggle(
                            "",
                            isOn: Binding(
                                get: { registration.claudeCode || registration.claudeDesktop },
                                set: { setRegistered($0) })
                        )
                        .labelsHidden()
                        .toggleStyle(.switch)
                        .controlSize(.small)
                    }
                }
            }

            // The tip line, then the illustrative mock beneath it.
            VStack(alignment: .leading, spacing: 8) {
                Text(
                    "You can also use Context for Claude directly out of Claude Code, Codex or Cursor "
                        + "by mentioning it in your prompt."
                )
                .font(.system(size: 11))
                .foregroundStyle(Ink.secondary)
                .fixedSize(horizontal: false, vertical: true)
                .padding(.horizontal, 4)

                AgentPromptMock()
            }

            SettingsSection(
                title: "Detected on this Mac",
                footnote: survey.allSatisfy({ !$0.presence.isInstalled })
                    ? "None of these were found. This list reads the applications and command-line "
                        + "tools actually present, so it will fill in as you install them."
                    : nil
            ) {
                SettingsRowStack(items: survey.map { AgentSurveyRow(surface: $0.surface, presence: $0.presence) }) {
                    row in
                    SettingsRow(
                        icon: row.presence.isInstalled ? "checkmark.seal" : "questionmark.app.dashed",
                        title: row.surface.title,
                        subtitle: row.presence.detail
                    ) {
                        AgentPresencePill(presence: row.presence)
                    }
                }
            }
        }
        .task {
            // Off the main actor: `survey` stats a handful of paths and asks LaunchServices, and
            // neither belongs on a pane's first render. The target probe is the same kind of work —
            // one LaunchServices question and a walk of the `claude` candidates — so it goes here
            // rather than into `body`, which would re-run it on every keystroke elsewhere in the pane.
            survey = AgentDetector.live.survey()
            registration = ClaudeRegistrar.status()
            targetDetail = ClaudeRouter.targetSubtitle(surface: ClaudeHandoff.surface)
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
        switch (registration.claudeCode, registration.claudeDesktop) {
        case (true, true): "Connected to Claude Code and Claude Desktop."
        case (true, false): "Connected to Claude Code."
        case (false, true): "Connected to Claude Desktop."
        case (false, false): "Not connected. Claude cannot read anything captured here yet."
        }
    }

    private func setRegistered(_ enabled: Bool) {
        Sound.effect(.click)
        isRegistering = true
        let result = enabled ? ClaudeRegistrar.register() : ClaudeRegistrar.unregister()
        registrationMessage = result.message
        registration = ClaudeRegistrar.status()
        isRegistering = false
    }
}

/// `Identifiable` wrapper so the survey can go through `SettingsRowStack`.
private struct AgentSurveyRow: Identifiable {
    let surface: AgentSurface
    let presence: AgentPresence
    var id: String { surface.rawValue }
}

/// The green-dot `Installed` pill, and the two honest alternatives to it.
struct AgentPresencePill: View {
    let presence: AgentPresence

    var body: some View {
        HStack(spacing: 5) {
            Circle()
                .fill(dotColor)
                .frame(width: 6, height: 6)
            Text(presence.label)
                .font(.system(size: 10, weight: .medium))
                .foregroundStyle(presence.isInstalled ? Ink.primary : Ink.tertiary)
        }
        .padding(.horizontal, 8)
        .padding(.vertical, 3)
        .background(Capsule(style: .continuous).fill(Ink.wash))
        .fixedSize()
    }

    private var dotColor: Color {
        switch presence {
        case .application, .executable: Ink.listeningGreen
        // Configured but no binary found: real evidence, weaker than a green dot should imply.
        case .configured: Ink.accent
        case .absent: Ink.tertiary
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
                    .foregroundStyle(Ink.tertiary)
                Text("What was I working on before lunch yesterday?")
                    .font(.system(size: 11))
                    .foregroundStyle(Ink.primary)
                Spacer(minLength: 0)
                Text("Example")
                    .font(.system(size: 9, weight: .semibold))
                    .foregroundStyle(Ink.tertiary)
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
