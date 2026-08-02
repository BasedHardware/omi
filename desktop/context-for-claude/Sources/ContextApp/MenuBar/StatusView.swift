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
///
/// **This surface is a menu, so it is drawn like one.** Plain SF Pro at `NSFont.systemFontSize`,
/// `Divider()` between groups, 22 pt rows, no fills, no tracking, no capsules and no cards. None of
/// the onboarding sheet's type roles appear here: `.inkStyle` carries the letter-spacing that gives
/// that sheet its character, and letter-spaced type in a menu bar panel is the single clearest tell
/// that the panel was drawn by a website rather than by macOS. Colour is `Ink`, which is system
/// semantics throughout, resolved in the appearance `StatusItemController` pins the popover to.
///
/// **It has no ground of its own, and must not grow one.** Every other surface in this app wears
/// `InkGlassView`; this one is the exception, and the exception is deliberate. An `NSPopover` brings
/// its own frosted chrome — a translucent frame *and the arrow that ties it to the menu bar icon* —
/// drawn by AppKit in a window this process does not own, and there is no public way to switch it
/// off. Putting the app's glass inside it would not replace that chrome, it would stack a second
/// material on top of the first: roughly a third of the desktop passthrough the panel is tuned for,
/// arrived at by paying twice for the same blur. `StatusItemController` pins the popover to
/// `InkGlass.appearance` instead, which is what makes the system's own material light and `Ink`'s
/// ladder resolve dark on it. So this view stays entirely transparent, which is exactly what lets
/// that chrome show through.
///
/// **It shares the glass's appearance, not the glass's ground, and that distinction is the reason
/// this file keeps a rung the rest of the app has lost.** `InkGlassTests` measures the ladder against
/// `Ink.surface` at `InkGlass.scrim` over `.hudWindow` over the desktop — a ground of 154/255 over a
/// black desktop, where `Ink.tertiary` is 3.60:1 and therefore banned. None of that describes this
/// surface: AppKit owns the popover's chrome, this app cannot measure or tune it, and the ladder here
/// is held against **opaque `Ink.surface`** by `MenuBarPresentationTests.testTheLabelLadderMeetsWCAG…`,
/// where `tertiary` is 5.24:1 and a legitimate glance step. This line used to claim the two grounds
/// were the same; they are not, and reading it that way is how the popover's exemption in
/// `InkGlassTests` looks arbitrary instead of load-bearing.
struct StatusView: View {
    @ObservedObject private var engine = Engine.shared
    @ObservedObject private var auth = OmiAuth.shared
    @ObservedObject private var uploads = ConversationUploader.shared

    @State private var claude: (claudeCode: Bool, claudeDesktop: Bool) = (false, false)
    @State private var claudeNote: String?

    /// Whether the two provider rows are showing under the account line.
    ///
    /// A disclosure rather than two rows that are always there: the signed-out state is meant to
    /// read as one sentence with one thing to press, and a menu that permanently carries two
    /// provider rows for a state most users are never in is a menu that has grown a settings pane.
    /// `@State`, so re-opening the popover comes back to the resting state — which is right, because
    /// re-opening it is how a user backs out of a menu on this platform.
    @State private var offeringProviders = false

    /// Permissions are flipped in System Settings, outside this process, and a system-audio consent
    /// dialog can be answered while the popover is still on screen. The subscription lives and dies
    /// with the popover, so this costs nothing the other 23 hours of the day.
    private let tick = Timer.publish(every: 1, on: .main, in: .common).autoconnect()

    /// A menu item's own font size, which is what every line on this surface is set in.
    private static let menuFontSize = NSFont.systemFontSize
    /// A menu's secondary line — the same size AppKit uses for a menu item's subtitle.
    private static let menuSmallFontSize = NSFont.smallSystemFontSize
    /// The height AppKit gives a menu item, matched by `InkPermissionRow`'s native row.
    private static let rowHeight = InkPermissionRow.menuRowHeight

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            statusBlock
            Divider()
            capabilityRows
            Divider()
            claudeLine
            accountLine
            Divider()
            footer
        }
        // Menu insets: AppKit's own menus are tight horizontally and barely padded at all
        // vertically, because the rows carry their own height.
        .padding(.horizontal, 12)
        .padding(.vertical, 8)
        .frame(width: 320)
        .onAppear(perform: refresh)
        .onReceive(tick) { _ in engine.refreshCapabilities() }
    }

    // MARK: - Status

    private var statusBlock: some View {
        VStack(alignment: .leading, spacing: 2) {
            HStack(spacing: 6) {
                Circle()
                    .fill(engine.isCapturing ? Ink.listeningGreen : Ink.tertiary)
                    .frame(width: 7, height: 7)
                    // The same column the capability rows hold open for their checkmark, so the dot
                    // and the checkmarks share one left edge.
                    .frame(width: 12, alignment: .leading)

                Text(engine.isCapturing ? "Listening · \(todayLabel)" : "Paused")
                    .font(.system(size: Self.menuFontSize))
                    .foregroundStyle(Ink.primary)
            }
            .frame(height: Self.rowHeight)

            // Shown even while capturing: sources fail independently, so "Listening" plus "System
            // audio unavailable" is a real and important state. Claude reports the same gap through
            // `status()`, and the two must never disagree.
            if let reason = engine.pausedReason, !reason.isEmpty {
                Text(reason)
                    .font(.system(size: Self.menuSmallFontSize))
                    .foregroundStyle(Ink.secondary)
                    .fixedSize(horizontal: false, vertical: true)
                    .padding(.leading, Self.rowTextInset)
            }

            lastLine
        }
        .padding(.horizontal, 4)
    }

    /// The one left edge every line of text on this surface shares — the 12 pt checkmark column
    /// plus the 6 pt gap after it, which is where a menu item's title starts. Lines that sit outside
    /// a row (the transcript line, the Claude line, the account line) are inset by hand to land on
    /// it; a menu whose text has two left margins is the other half of looking counterfeit.
    private static let rowTextInset: CGFloat = 18

    /// The single best proof-of-life in the product. A line landing here means the capture stack,
    /// the transcriber and the store are all alive — nothing else in this popover proves that.
    private var lastLine: some View {
        Text(engine.lastLine ?? idlePlaceholder)
            .font(.system(size: Self.menuSmallFontSize))
            .italic()
            .foregroundStyle(Ink.secondary)
            .lineLimit(2)
            // The newest words are at the end of a transcript line, so keep the tail.
            .truncationMode(.head)
            .fixedSize(horizontal: false, vertical: true)
            .frame(maxWidth: .infinity, minHeight: 28, alignment: .topLeading)
            .padding(.leading, Self.rowTextInset)
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
        // No spacing: menu rows abut, and each row already carries its own 22 pt height.
        VStack(spacing: 0) {
            ForEach(reports, id: \.name) { report in
                InkPermissionRow(
                    title: label(for: report.name),
                    granted: report.granted,
                    // `Permissions` owns the status word, so this popover and the onboarding rows can
                    // never disagree about what the user still has to do.
                    status: report.detail,
                    native: true,
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
        CapabilityGroup(rawValue: name)?.title ?? name
    }

    private func handle(_ report: CapabilityReport) {
        guard let group = CapabilityGroup(rawValue: report.name) else { return }
        // The row stands for several grants, so a tap acts on the nearest one still missing — and on
        // the first member when they are all in, because that is the pane a user opens to revoke.
        let capability = group.members.first { !Permissions.check($0) } ?? group.members[0]

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
        VStack(alignment: .leading, spacing: 2) {
            HStack(alignment: .firstTextBaseline, spacing: 8) {
                Text(claudeSummary)
                    .font(.system(size: Self.menuFontSize))
                    // Not connected is the state with something to do about it, so it is the state
                    // that gets full contrast. Settled recedes to secondary.
                    .foregroundStyle(isConnected ? Ink.secondary : Ink.primary)
                    .fixedSize(horizontal: false, vertical: true)

                Spacer(minLength: 8)

                if !isConnected {
                    Button("Connect", action: connect)
                        .buttonStyle(.plain)
                        .font(.system(size: Self.menuFontSize))
                        .foregroundStyle(Ink.accent)
                }
            }
            .frame(minHeight: Self.rowHeight)

            if let claudeNote, !claudeNote.isEmpty {
                Text(claudeNote)
                    .font(.system(size: Self.menuSmallFontSize))
                    .foregroundStyle(Ink.secondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
        .padding(.leading, Self.rowTextInset)
        .padding(.trailing, 4)
    }

    /// Which Omi account the recordings land in, whether anything is stuck on the way there, and —
    /// when there is no account — the way back in.
    ///
    /// A recorder that is quietly not syncing looks identical to one that is, which is why the
    /// backlog is on screen rather than in a log. The same argument is why the sign-in is here: this
    /// popover carried a `Sign out` and nothing to undo it with, so a user who signed out had no
    /// route back to an account anywhere in the app — onboarding does not run twice, and there is no
    /// Dock icon, window menu or Account pane to find one in. A state the app can enter and cannot
    /// leave is a dead end, not a preference.
    private var accountLine: some View {
        let account = self.account
        return VStack(alignment: .leading, spacing: 0) {
            HStack(alignment: .firstTextBaseline, spacing: 8) {
                VStack(alignment: .leading, spacing: 2) {
                    Text(account.summary)
                        .font(.system(size: Self.menuFontSize))
                        // Not signed in is the state with something to do about it, so it is the
                        // state that gets full contrast — the same rule the Claude line follows.
                        .foregroundStyle(auth.isSignedIn ? Ink.secondary : Ink.primary)
                        .fixedSize(horizontal: false, vertical: true)

                    if let note = account.note {
                        Text(note)
                            .font(.system(size: Self.menuSmallFontSize))
                            .foregroundStyle(account.noteIsError ? Ink.errorRed : Ink.secondary)
                            .fixedSize(horizontal: false, vertical: true)
                    }
                }

                Spacer(minLength: 8)

                if let action = account.action {
                    Button(action.title) { perform(action) }
                        .buttonStyle(.plain)
                        .font(.system(size: Self.menuFontSize))
                        .foregroundStyle(action.isRepair ? Ink.accent : Ink.tertiary)
                }
            }
            .frame(minHeight: Self.rowHeight)
            .padding(.leading, Self.rowTextInset)
            .padding(.trailing, 4)

            // Outside the inset above on purpose: these are commands, and every command on this
            // surface starts on the one left edge `MenuCommand` holds open for a checkmark.
            // Indenting them under the sentence would give the popover a second left margin.
            if account.showsProviders {
                ForEach(AccountPresentation.providers) { choice in
                    MenuCommand(title: choice.title) { begin(choice.provider) }
                }
            }
        }
    }

    /// The account line as a value. Every branch lives in `AccountPresentation`, so this view has no
    /// judgement of its own about a state it cannot be driven through in a test.
    private var account: AccountPresentation {
        AccountPresentation(
            signedIn: auth.isSignedIn,
            signingIn: auth.isSigningIn,
            email: auth.email,
            offeringProviders: offeringProviders,
            signInError: auth.lastSignInError,
            uploadNote: uploadNote,
            uploadFailed: uploads.lastError != nil)
    }

    private func perform(_ action: AccountPresentation.Action) {
        switch action {
        case .signOut:
            auth.signOut()
            // Not opened for them: signing out and being handed a provider menu reads as the app
            // arguing with the choice they just made.
            offeringProviders = false
        case .signIn:
            offeringProviders = true
        case .dismissProviders:
            offeringProviders = false
        }
    }

    /// Opens the browser. The task lives on `OmiAuth` and not on this view: the popover is
    /// `.transient`, so macOS closes it — and destroys this view — the instant the browser takes
    /// focus, which is a few milliseconds into the round trip. Everything downstream of an account
    /// (`ConversationUploader`, `ListenSocket`, `ScreenActivityUploader`, `MCPKeyProvisioner`)
    /// already subscribes to `OmiAuth.$isSignedIn`, so nothing here has to restart them.
    private func begin(_ provider: OmiAuthProvider) {
        offeringProviders = false
        auth.beginSignIn(provider: provider)
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

    /// The two commands, as menu items rather than as a pill and a link.
    ///
    /// `InkButton`'s 42 pt stadium is the onboarding sheet's action shape and belongs there; a menu
    /// has no buttons in it. Both commands take the full label colour a menu item takes — a command
    /// set in `tertiaryLabelColor` inside a 22 pt row reads as disabled, which is the opposite of
    /// what either of these is.
    private var footer: some View {
        VStack(spacing: 0) {
            MenuCommand(title: engine.isCapturing ? "Pause" : "Resume") {
                if engine.isCapturing {
                    engine.pause()
                } else {
                    engine.resume()
                }
            }

            // The timeline and Settings both existed with nothing able to open them. The shortcuts are
            // the fast path, but a menu-bar-only app whose windows are reachable ONLY by an
            // undiscoverable modifier double-tap has effectively hidden them — and the shortcut is
            // gated on Accessibility, so without these rows an ungranted user cannot reach either
            // window at all.
            MenuCommand(title: "Open Timeline", shortcut: GlobalShortcuts.shared.display(for: .openTimeline)) {
                // Nil until the database finishes opening on the engine's queue. Declining beats
                // presenting a timeline with nothing behind it.
                guard let store = Engine.shared.contextStore else { return }
                RewindWindow.present(
                    store: store,
                    onOpenSettings: { SettingsWindow.present() },
                    onSearch: { query in SearchBarWindow.present(prefill: query) })
            }

            MenuCommand(title: "Settings…", shortcut: "⌘,") { SettingsWindow.present() }
                .keyboardShortcut(",")

            Divider()
                .padding(.vertical, 4)

            MenuCommand(title: "Quit", shortcut: "⌘Q") { NSApp.terminate(nil) }
                .keyboardShortcut("q")
        }
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

// MARK: - Menu command

/// One command row, drawn the way AppKit draws a menu item: full-width hit target, 22 pt tall, the
/// title at `NSFont.systemFontSize` in the label colour, an optional key-equivalent trailing in
/// secondary, and a highlight only under the pointer.
private struct MenuCommand: View {
    let title: String
    var shortcut: String?
    let action: () -> Void

    @State private var isHovering = false

    var body: some View {
        Button(action: action) {
            HStack(spacing: 8) {
                Text(title)
                    .font(.system(size: NSFont.systemFontSize))
                    .foregroundStyle(Ink.primary)
                    // The same column the capability rows hold open for their checkmark, so every
                    // row on this surface shares one left edge.
                    .padding(.leading, 18)

                Spacer(minLength: 8)

                if let shortcut {
                    Text(shortcut)
                        .font(.system(size: NSFont.systemFontSize))
                        .foregroundStyle(Ink.secondary)
                }
            }
            .padding(.horizontal, 4)
            .frame(height: InkPermissionRow.menuRowHeight)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(
                RoundedRectangle(cornerRadius: 4, style: .continuous)
                    .fill(isHovering ? Ink.rowHover : Color.clear)
            )
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .onHover { isHovering = $0 }
        .animation(InkReduceMotion.animation(.easeOut(duration: InkMotion.press)), value: isHovering)
    }
}
