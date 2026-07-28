import ContextCore
import AppKit
import Combine
import SwiftUI

/// The entire non-onboarding UI: one 320 pt popover hanging off the menu bar mark.
///
/// Deliberately not a settings window. Everything Context for Claude knows is answered by Claude through MCP,
/// so this surface only has to answer three questions a person actually asks of a background
/// recorder — is it on, can it hear and see, and does Claude know about it — plus how to stop it.
/// If a second screen ever seems necessary, the product has drifted.
struct StatusView: View {
    @ObservedObject private var engine = Engine.shared
    @ObservedObject private var auth = OmiAuth.shared
    @ObservedObject private var uploads = ConversationUploader.shared

    @State private var claude: (claudeCode: Bool, claudeDesktop: Bool) = (false, false)
    @State private var claudeNote: String?

    /// Permissions are flipped in System Settings, outside this process, and a system-audio consent
    /// dialog can be answered while the popover is still on screen. The subscription lives and dies
    /// with the popover, so this costs nothing the other 23 hours of the day.
    private let tick = Timer.publish(every: 1, on: .main, in: .common).autoconnect()

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            statusBlock
            hairline
            capabilityRows
            hairline
            claudeLine
            accountLine
            footer
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 14)
        .frame(width: 320)
        .background(Ink.ink)
        .onAppear(perform: refresh)
        .onReceive(tick) { _ in engine.refreshCapabilities() }
    }

    // MARK: - Status

    private var statusBlock: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack(spacing: 8) {
                Circle()
                    .fill(engine.isCapturing ? Ink.listeningGreen : Ink.creamDim)
                    .frame(width: 7, height: 7)

                Text(engine.isCapturing ? "Listening · \(todayLabel)" : "Paused")
                    .inkStyle(.rowCopy)
                    .foregroundStyle(Ink.cream)
            }

            // Shown even while capturing: sources fail independently, so "Listening" plus "System
            // audio unavailable" is a real and important state. Claude reports the same gap through
            // `status()`, and the two must never disagree.
            if let reason = engine.pausedReason, !reason.isEmpty {
                Text(reason)
                    .inkStyle(.statusLabel)
                    .foregroundStyle(Ink.creamHint)
                    .fixedSize(horizontal: false, vertical: true)
            }

            lastLine
        }
    }

    /// The single best proof-of-life in the product. A line landing here means the capture stack,
    /// the transcriber and the store are all alive — nothing else in this popover proves that.
    private var lastLine: some View {
        Text(engine.lastLine ?? idlePlaceholder)
            .inkStyle(.statusLabel)
            .italic()
            .foregroundStyle(Ink.creamDim)
            .lineLimit(2)
            // The newest words are at the end of a transcript line, so keep the tail.
            .truncationMode(.head)
            .fixedSize(horizontal: false, vertical: true)
            .frame(maxWidth: .infinity, minHeight: 30, alignment: .topLeading)
    }

    private var idlePlaceholder: String {
        engine.isCapturing ? "waiting for something to hear" : "nothing is being captured"
    }

    private var todayLabel: String {
        let total = Int(engine.todaySeconds.rounded())
        let hours = total / 3600
        let minutes = (total % 3600) / 60
        if hours > 0 { return "\(hours)h \(minutes)m today" }
        if minutes > 0 { return "\(minutes)m today" }
        return "just started"
    }

    // MARK: - Capabilities

    private var capabilityRows: some View {
        VStack(spacing: 8) {
            ForEach(reports, id: \.name) { report in
                InkPermissionRow(
                    title: label(for: report.name),
                    granted: report.granted,
                    // `Permissions` owns the status word, so this popover and the onboarding rows can
                    // never disagree about what the user still has to do.
                    status: report.detail,
                    action: { handle(report) }
                )
                .frame(maxWidth: .infinity)
            }
        }
    }

    /// The Engine republishes these on every poll; the direct call only covers the first frame after
    /// launch, before the first poll has landed.
    private var reports: [CapabilityReport] {
        engine.capabilities.isEmpty ? Permissions.report() : engine.capabilities
    }

    /// `Capability.title` is the first-person sentence onboarding uses to introduce itself. This is a
    /// glance surface for a user who has already been introduced, so it gets the noun instead.
    private func label(for name: String) -> String {
        guard let capability = Capability(rawValue: name) else { return name }
        switch capability {
        case .microphone: return "Microphone"
        case .systemAudio: return "Call audio"
        case .screen: return "Screen"
        }
    }

    private func handle(_ report: CapabilityReport) {
        guard let capability = Capability(rawValue: report.name) else { return }

        // A granted Screen Recording checkbox over a dead capture is the one row that lies, and the
        // only cure is a relaunch — so that is what tapping it does.
        if capability == .screen, Permissions.screenNeedsRelaunch {
            Permissions.relaunchApp()
        }

        // A granted row is still worth a tap: the pane is the only route to revoking it.
        guard !report.granted else {
            Permissions.openSettings(for: capability)
            return
        }

        // `Permissions.request` is itself two-stage — it raises the system prompt the first time and
        // opens the Settings pane on every ask after a denial, because TCC never re-prompts.
        Task { @MainActor in
            await Permissions.request(capability)
            engine.refreshCapabilities()
        }
    }

    // MARK: - Claude

    private var claudeLine: some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack(alignment: .firstTextBaseline, spacing: 8) {
                Text(claudeSummary)
                    .inkStyle(.statusLabel)
                    .foregroundStyle(isConnected ? Ink.creamHint : Ink.creamDim)
                    .fixedSize(horizontal: false, vertical: true)

                Spacer(minLength: 0)

                if !isConnected {
                    Button("Connect", action: connect)
                        .buttonStyle(.plain)
                        .inkStyle(.statusLabel)
                        .foregroundStyle(Ink.cursorBlue)
                }
            }

            if let claudeNote, !claudeNote.isEmpty {
                Text(claudeNote)
                    .inkStyle(.statusLabel)
                    .foregroundStyle(Ink.creamDim)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
    }

    /// Which Omi account the recordings land in, and whether anything is stuck on the way there.
    /// A recorder that is quietly not syncing looks identical to one that is, which is why the
    /// backlog is on screen rather than in a log.
    private var accountLine: some View {
        HStack(alignment: .firstTextBaseline, spacing: 8) {
            VStack(alignment: .leading, spacing: 2) {
                Text(accountSummary)
                    .inkStyle(.statusLabel)
                    .foregroundStyle(auth.isSignedIn ? Ink.creamHint : Ink.creamDim)
                    .fixedSize(horizontal: false, vertical: true)

                if let note = uploadNote {
                    Text(note)
                        .inkStyle(.statusLabel)
                        .foregroundStyle(uploads.lastError == nil ? Ink.creamDim : Ink.errorRed)
                        .fixedSize(horizontal: false, vertical: true)
                }
            }

            Spacer(minLength: 0)

            if auth.isSignedIn {
                Button("Sign out") { auth.signOut() }
                    .buttonStyle(.plain)
                    .inkStyle(.statusLabel)
                    .foregroundStyle(Ink.creamDim)
            }
        }
    }

    private var accountSummary: String {
        guard auth.isSignedIn else { return "Not signed in — nothing is reaching your Omi account" }
        return "Syncing to \(auth.email ?? "your Omi account")"
    }

    private var uploadNote: String? {
        if let error = uploads.lastError { return error }
        if uploads.pendingCount > 0 {
            return "\(uploads.pendingCount) conversation\(uploads.pendingCount == 1 ? "" : "s") waiting to upload"
        }
        return nil
    }

    private var isConnected: Bool { claude.claudeCode || claude.claudeDesktop }

    private var claudeSummary: String {
        switch (claude.claudeCode, claude.claudeDesktop) {
        case (true, true): return "Connected to Claude Code and Claude Desktop"
        case (true, false): return "Connected to Claude Code"
        case (false, true): return "Connected to Claude Desktop"
        case (false, false): return "Not connected to Claude"
        }
    }

    private func connect() {
        let result = ClaudeRegistrar.register()
        claude = (result.claudeCode, result.claudeDesktop)
        claudeNote = result.message
    }

    // MARK: - Controls

    private var footer: some View {
        HStack(spacing: 12) {
            InkButton(engine.isCapturing ? "Pause" : "Resume", kind: .secondary) {
                if engine.isCapturing {
                    engine.pause()
                } else {
                    engine.resume()
                }
            }

            Spacer(minLength: 0)

            Button("Quit") { NSApp.terminate(nil) }
                .buttonStyle(.plain)
                .inkStyle(.statusLabel)
                .foregroundStyle(Ink.creamDim)
                .keyboardShortcut("q")
        }
    }

    // MARK: - Chrome

    private var hairline: some View {
        Rectangle()
            .fill(Ink.creamHairline)
            .frame(height: 1)
    }

    /// Claude's two config files are edited by hand, by installers, and by Claude itself, so the
    /// connection line is re-read on open rather than cached for the life of the process. Once per
    /// open is enough — parsing `~/.claude.json` is not something to do on a one-second tick.
    private func refresh() {
        engine.refreshCapabilities()
        claude = ClaudeRegistrar.status()
        claudeNote = nil
    }
}
