import AppKit
import Combine
import ContextCore
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

    /// What is registered on disk *and* whether the running Claude Desktop is serving us. The
    /// default is the honest one for "not probed yet": nothing connected, nothing to restart.
    @State private var claude = ClaudeConnection(
        claudeCode: false, claudeDesktop: false, liveness: .unknown)
    @State private var claudeNote: String?
    /// True while the two config files are being rewritten. A second press cannot start a second
    /// write, which is the same rule the account line's round trip follows.
    @State private var isConnecting = false

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

    /// The panel's width, and the only dimension of it that is fixed. The height is its content's
    /// own — see `StatusItemController.makePopover()` for what pinning that did.
    static let popoverWidth: CGFloat = 320

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
        .frame(width: Self.popoverWidth)
        .onAppear(perform: refresh)
        .onReceive(tick) { _ in
            engine.refreshCapabilities()
            readAskLedger()
        }
    }

    // MARK: - Status

    private var statusBlock: some View {
        VStack(alignment: .leading, spacing: 2) {
            HStack(spacing: 6) {
                Circle()
                    .fill(dotColour)
                    .frame(width: 7, height: 7)
                    // The same column the capability rows hold open for their checkmark, so the dot
                    // and the checkmarks share one left edge.
                    .frame(width: 12, alignment: .leading)

                Text(headline)
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
    static let rowTextInset: CGFloat = 18

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

    /// **The line the whole bug is about.**
    ///
    /// This used to be two words over one boolean — "Listening" or "Paused" — and the boolean was an
    /// *or* over three independent sensors. With the screen dead and the microphone alive it read
    /// "Listening · 4h 12m today" for twenty-nine hours, over a database whose newest screen frame
    /// was from the previous afternoon. Two words cannot describe three states, so there are now
    /// three, and the middle one is the one that was missing.
    private var headline: String {
        switch engine.health {
        case .capturing: return "Listening · \(todayLabel)"
        case .degraded: return "Partly listening · \(todayLabel)"
        case .off: return engine.isPaused ? "Paused" : "Not capturing"
        }
    }

    /// Green for whole, red for a half that has stopped working, grey for off. Red rather than a
    /// softer amber because this is the app's own rule about when to raise its voice, and a recorder
    /// that has quietly stopped recording half of what it promised is exactly that moment — the
    /// previous behaviour was to stay green.
    private var dotColour: Color {
        switch engine.health {
        case .capturing: return Ink.listeningGreen
        case .degraded: return Ink.errorRed
        case .off: return Ink.tertiary
        }
    }

    private var idlePlaceholder: String {
        engine.health == .off ? "nothing is being captured" : "waiting for something to hear"
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

    /// **The line that appears once tapping a row has stopped being worth anything.**
    ///
    /// The rows are imperatives and their vocabulary is four words wide, so none of them can say
    /// "you have done this and macOS did not give it to me" — and without somewhere to say it, the
    /// only honest response to the fourth tap would be to do nothing, which is worse. See
    /// `PermissionDeadEnd`.
    ///
    /// `@State` rather than computed in `body`, because the press that spends the last ask has to
    /// redraw the surface it was pressed on rather than wait out the one-second tick.
    @State private var deadEndNote: String?

    /// The repair control for the one screen state no click of ours can fix, and whether its last
    /// press has landed. See `ScreenRepairControl`.
    @State private var screenRepair: ScreenRepairControl?
    @State private var copiedRepairCommand = false

    private var capabilityRows: some View {
        // No spacing: menu rows abut, and each row already carries its own 22 pt height.
        VStack(spacing: 0) {
            ForEach(rows) { row in
                InkPermissionRow(
                    // The missing member's noun when a group is half granted — see
                    // `MenuBarCapabilityRow` for why the noun moves and the status word does not.
                    title: row.noun,
                    granted: row.granted,
                    // `Permissions` owns the status word, so this popover and the onboarding rows can
                    // never disagree about what the user still has to do.
                    status: row.status,
                    native: true,
                    action: { handle(row.group) }
                )
                .frame(maxWidth: .infinity)
            }

            if let screenRepair {
                repairRow(screenRepair)
            } else if let deadEndNote {
                Text(deadEndNote)
                    .font(.system(size: Self.menuSmallFontSize))
                    .foregroundStyle(Ink.secondary)
                    .fixedSize(horizontal: false, vertical: true)
                    .padding(.leading, Self.rowTextInset)
                    .padding(.trailing, 4)
                    .padding(.top, 2)
            }
        }
    }

    /// The note and the one press: an accented word under the sentence, which is the same affordance
    /// the connector line offers and the same colour it uses for it.
    ///
    /// Stacked rather than trailing, unlike that line: this sentence takes the popover's whole text
    /// column, so a control beside it would be a control on its own line anyway — with the width of
    /// the sentence taken out of it.
    private func repairRow(_ repair: ScreenRepairControl) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(repair.note)
                .font(.system(size: Self.menuSmallFontSize))
                .foregroundStyle(Ink.secondary)
                .fixedSize(horizontal: false, vertical: true)

            Button(repair.action) { copyRepairCommand(repair) }
                .buttonStyle(.plain)
                .font(.system(size: Self.menuSmallFontSize))
                .foregroundStyle(Ink.accent)
                .disabled(copiedRepairCommand)
        }
        .padding(.leading, Self.rowTextInset)
        .padding(.trailing, 4)
        .padding(.top, 2)
    }

    /// **The clipboard and nothing else.** The app never runs this: see `ScreenRepairControl`.
    private func copyRepairCommand(_ repair: ScreenRepairControl) {
        NSPasteboard.general.clearContents()
        NSPasteboard.general.setString(repair.command, forType: .string)
        copiedRepairCommand = true
        readAskLedger()
        // The label *is* the confirmation, so it has to go back to being an offer or the control
        // reads as spent. The popover is transient and may be gone before this fires, which is
        // harmless — `@State` on a destroyed view is discarded.
        Task { @MainActor in
            try? await Task.sleep(for: .seconds(2))
            copiedRepairCommand = false
            readAskLedger()
        }
    }

    /// Clears the tally for anything genuinely working, then re-reads the line.
    ///
    /// The clearing is not `Permissions.check` alone, and that is the load-bearing half: the screen's
    /// TCC record reads granted for a process the window server is refusing, so a tally cleared on
    /// the record would be cleared on every tick of exactly the state it exists to bound — and the
    /// row would go back to offering a restart that has already been spent.
    private func readAskLedger() {
        let ledger = PermissionAskLedger()
        let needsRelaunch = Permissions.screenNeedsRelaunch
        let recordIsUnusable = Permissions.screenRecordIsUnusable
        for capability in Capability.allCases
        where PermissionDeadEnd.isWorking(
            capability, granted: Permissions.check(capability), screenNeedsRelaunch: needsRelaunch)
        {
            ledger.noteWorking(capability)
        }
        // **The repair control owns the screen's line when it is showing**, which is why it is read
        // first and why `note` is told about the same state: two sentences about one row, one of them
        // recommending a reopen that provably cannot work, is the loop arriving in a new costume.
        screenRepair = ScreenRepairControl.of(Permissions.screenBlock(), copied: copiedRepairCommand)
        deadEndNote = PermissionDeadEnd.note(
            for: Capability.allCases,
            granted: { Permissions.check($0) },
            screenNeedsRelaunch: needsRelaunch,
            screenRecordIsUnusable: recordIsUnusable,
            asks: { ledger.asks($0) },
            relaunches: { ledger.relaunches($0) })
    }

    /// The Engine republishes these on every poll; the direct call only covers the first frame after
    /// launch, before the first poll has landed.
    private var reports: [CapabilityReport] {
        engine.capabilities.isEmpty ? Permissions.report() : engine.capabilities
    }

    private var rows: [MenuBarCapabilityRow] {
        reports.map { MenuBarCapabilityRow(report: $0, isGranted: { Permissions.check($0) }) }
    }

    private func handle(_ group: CapabilityGroup) {
        // The row stands for several grants, so a tap acts on the nearest one still missing — and on
        // the first member when they are all in, because that is the pane a user opens to revoke.
        // The same member `MenuBarCapabilityRow` names, so the pane that opens is the one the row
        // was pointing at.
        let missing = group.firstMissing { Permissions.check($0) }
        let capability = missing ?? group.namesake
        let ledger = PermissionAskLedger()

        // A granted Screen Recording checkbox over a dead capture is the one row that lies, and the
        // only cure is a relaunch — so that is what tapping it does.
        //
        // **Once.** `screenNeedsRelaunch` is latched by `noteScreenCaptureDeclined()`, which fires
        // again on the successor's first refused capture — so on a Mac whose TCC record no longer
        // matches this build's code requirement, the row came back saying "Action required" and
        // every subsequent tap killed and reopened the app for a remedy that had already failed.
        // After one spent reopen the tap falls through to the pane, and `deadEndNote` says why.
        if capability == .screen, Permissions.screenNeedsRelaunch {
            // **`.recordUnusable` never gets a relaunch, not even a first one.** Both flags are true
            // at once in that state — an unusable record is also a stale grant — and reopening is
            // known in advance not to help, so offering it is a dead instruction the app can see is
            // dead before it gives it. `ScreenRepairControl` is the row's real remedy there.
            if !Permissions.screenRecordIsUnusable,
                PermissionDeadEnd.mayRelaunch(after: ledger.relaunches(.screen))
            {
                ledger.noteRelaunched(.screen)
                Permissions.relaunchApp()
            }
            ledger.noteAsked(.screen)
            Permissions.openSettings(for: .screen)
            readAskLedger()
            return
        }

        // A granted row is still worth a tap: the pane is the only route to revoking it.
        guard missing != nil else {
            Permissions.openSettings(for: capability)
            return
        }

        ledger.noteAsked(capability)
        readAskLedger()
        // `Permissions.request` is itself two-stage — it raises the system prompt the first time and
        // opens the Settings pane on every ask after a denial, because TCC never re-prompts.
        Task { @MainActor in
            await Permissions.request(capability)
            engine.refreshCapabilities()
        }
    }

    // MARK: - Claude

    private var claudeLine: some View {
        let line = connector
        return VStack(alignment: .leading, spacing: 2) {
            HStack(alignment: .firstTextBaseline, spacing: 8) {
                Text(line.summary)
                    .font(.system(size: Self.menuFontSize))
                    // Not connected is the state with something to do about it, so it is the state
                    // that gets full contrast. Settled recedes to secondary.
                    .foregroundStyle(line.isConnected ? Ink.secondary : Ink.primary)
                    .fixedSize(horizontal: false, vertical: true)

                Spacer(minLength: 8)

                if let action = line.action {
                    // The label carries the in-flight state rather than a third colour: the popover's
                    // faint rung is spent (`InkGlassTests` counts it), and a word is a better signal
                    // than a shade in any case — the press writes two of Claude's config files, and
                    // saying so is what stops a second press.
                    Button(action, action: connect)
                        .buttonStyle(.plain)
                        .font(.system(size: Self.menuFontSize))
                        .foregroundStyle(Ink.accent)
                        .disabled(isConnecting)
                }
            }
            .frame(minHeight: Self.rowHeight)

            if let note = line.note, !note.isEmpty {
                Text(note)
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
            return
                "\(uploads.pendingCount) conversation\(uploads.pendingCount == 1 ? "" : "s") waiting to upload"
        }
        return nil
    }

    /// The Claude line as a value, for the reason `account` is one: this view keeps no judgement of
    /// its own about a state it cannot be driven through in a test.
    private var connector: ClaudeConnectorLine {
        ClaudeConnectorLine(connection: claude, note: claudeNote, isConnecting: isConnecting)
    }

    /// Same shape as `refresh()`, and for the same reason: `register()` reads, decodes and rewrites
    /// both of Claude's config files. Run on the actor that has to draw, it froze the popover under
    /// the press — and `isConnecting` is why the `await` matters, since without a suspension point
    /// SwiftUI never gets a frame in which to show that anything is happening.
    private func connect() {
        isConnecting = true
        claudeNote = nil
        Task {
            let result = await Task.detached(priority: .userInitiated) { ClaudeRegistrar.register() }.value
            // Re-probed rather than built from `result`: registering writes the config, and Claude
            // Desktop reads it at *its* launch, so the press that "connects" routinely leaves a
            // Claude that still cannot answer. That is the state the user most needs to be told
            // about, and it exists from the instant the write lands.
            claude = await Task.detached(priority: .userInitiated) {
                ClaudeConnection(
                    claudeCode: result.claudeCode,
                    claudeDesktop: result.claudeDesktop,
                    liveness: ClaudeServerLiveness.state(claudeDesktopPIDs: ClaudeDesktopProcesses.pids))
            }.value
            claudeNote = result.message
            isConnecting = false
        }
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
            // Keyed on `isPaused`, not on `isCapturing`, and the difference is load-bearing now
            // that `isCapturing` means "everything is running". A recorder with a dead screen and a
            // live microphone would otherwise offer **Resume** for a pause that never happened —
            // and pressing it would do nothing at all, because `resume()` returns immediately when
            // the engine was never paused. A control that cannot work is worse than no control.
            MenuCommand(title: engine.isPaused ? "Resume" : "Pause") {
                if engine.isPaused {
                    engine.resume()
                } else {
                    engine.pause()
                }
            }

            // The app's windows and Settings all existed with nothing able to open them. The
            // shortcuts are the fast path, but an app whose windows are reachable ONLY by an
            // undiscoverable modifier double-tap has effectively hidden them — and the shortcuts are
            // gated on Accessibility, so without these rows an ungranted user cannot reach any of
            // them at all. That is why there is a row for each window rather than one for whichever
            // is more important.
            //
            // Activity leads because it is the main window: it is what the Dock icon and a launch
            // open, and the timeline is what a moment inside it opens into.
            //
            // The chord printed here is `openActivity`'s — the app's advertised way in, and the one
            // a user is most likely to have seen. `openSearch` opens this same window with its field
            // focused, but a row can only print one shortcut and the primary is the one to teach.
            //
            // **Printed only while it is armed.** A key equivalent trailing a menu item is a promise
            // that pressing it does this, and the gesture defaults are watched for through a global
            // event monitor macOS gates behind Accessibility — so on a Mac that has not granted it,
            // `⌘ + ⌘` beside this row taught a gesture that does nothing. That is the same defect as
            // the Settings recorder printing it, and it is worse here: this row is the *reason* the
            // ungranted user can reach the window at all, and a dead chord beside it suggests they
            // never needed the row.
            MenuCommand(title: "Open Activity", shortcut: activityShortcut) {
                SearchBarWindow.present()
            }

            // **No shortcut, because the timeline has none.** ⌘ + ⌘ opens Activity now, and printing
            // a chord beside a row that a chord no longer reaches would send the user to the wrong
            // window every time they used it. This row *is* the timeline's keyboard-free route, which
            // is why it stays.
            //
            // The presentation itself lives in `ContextAppDelegate.openTimeline()`. It used to be
            // rebuilt here — store guard, Settings hand-off, search hand-off — and a second
            // reconstruction of three arguments is how one of them quietly stops being passed.
            MenuCommand(title: "Open Timeline") {
                ContextAppDelegate.openTimeline()
            }

            MenuCommand(title: "Settings…", shortcut: "⌘,") { SettingsWindow.present() }
                .keyboardShortcut(",")

            // **The only way back into the walkthrough once it has been left.**
            //
            // The tutorial now survives the relaunch macOS forces on it (`TutorialResume`), but a
            // user who pressed *Skip* spent that record deliberately — and until this row existed,
            // `Tutorial.start` had exactly one caller, inside onboarding's final card, which runs
            // once per install. Skipping was therefore permanent, and the app's own explanation of
            // itself was unreachable for the rest of its life on that Mac.
            MenuCommand(title: "Show Me Around") {
                Tutorial.start(store: Engine.shared.contextStore)
            }

            Divider()
                .padding(.vertical, 4)

            // `TerminationOrigin` first, and it has to be first: `NSApp.terminate` runs
            // `applicationWillTerminate` synchronously, and that is where the app decides whether to
            // reopen itself after a termination it did not ask for. This is the app asking. Without
            // the line, a Quit pressed during onboarding would be answered by the app coming
            // straight back — an app that cannot be quit, which is worse than one that needs
            // reopening.
            MenuCommand(title: "Quit", shortcut: "⌘Q") {
                TerminationOrigin.userAskedToQuit()
                NSApp.terminate(nil)
            }
            .keyboardShortcut("q")
        }
    }

    /// The chord to print beside **Open Activity**, or nil when there is none to promise.
    ///
    /// Read at render rather than cached: Accessibility is granted in System Settings while the app
    /// runs, and the popover's one-second tick is what brings this back the moment it lands.
    private var activityShortcut: String? {
        let shortcuts = GlobalShortcuts.shared
        guard shortcuts.readiness(for: .openActivity) == .armed else { return nil }
        return shortcuts.display(for: .openActivity)
    }

    /// Claude's two config files are edited by hand, by installers, and by Claude itself, so the
    /// connection line is re-read on open rather than cached for the life of the process. Once per
    /// open is enough — parsing `~/.claude.json` is not something to do on a one-second tick.
    ///
    /// **Off the main actor**, for the reason `SettingsAgentsPane.setRegistered` gives at length:
    /// `ClaudeRegistrar.status()` opens and JSON-decodes `~/.claude.json` — Claude Code's own state
    /// store, which grows with the user's history rather than with anything we write — and Claude
    /// Desktop's config. Doing that synchronously in `onAppear` froze the popover under the click
    /// that opened it, for however long those two files take on that Mac. The Agents pane already
    /// moved the identical call off; a second call site doing it the other way is the inconsistency,
    /// not a second opinion.
    private func refresh() {
        engine.refreshCapabilities()
        readAskLedger()
        claudeNote = nil
        Task {
            claude = await Task.detached(priority: .userInitiated) { ClaudeConnection.current() }.value
        }
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
