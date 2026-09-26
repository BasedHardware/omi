import ContextCore
import Foundation

/// Copy for the local Claude connector step. A written MCP entry means this Mac is configured to
/// launch our server; it does not prove that a Claude account, session, or conversation is active.
enum ClaudeSurface: CaseIterable {
    case claudeCode
    case claudeDesktop

    var name: String {
        switch self {
        case .claudeCode: return "Claude Code"
        case .claudeDesktop: return "Claude Desktop"
        }
    }
}

struct OnboardingConnectorCopy {
    let title: String
    let detail: String
    let action: String

    init(surfaces: Set<ClaudeSurface>) {
        let configured = ClaudeSurface.allCases.filter { surfaces.contains($0) }.map(\.name)
        guard !configured.isEmpty else {
            title = "Bring Claude in"
            detail = "Set up a local connector so Claude can ask about this Mac when you use it."
            action = "Set up Claude"
            return
        }

        let names = Self.list(configured)
        title = "\(names) \(configured.count == 1 ? "is" : "are") ready"
        detail = "The local connector is configured for \(names)."
        action = "Continue"
    }

    private static func list(_ names: [String]) -> String {
        guard names.count > 1 else { return names.first ?? "Claude" }
        return names.dropLast().joined(separator: ", ") + " and " + (names.last ?? "Claude")
    }
}

// MARK: - The capability rows

/// What one capability row in the popover is called.
///
/// **The row names the work that remains, not the group it belongs to.** `CapabilityGroup` deliberately
/// folds two TCC records into one idea — `screen` is Screen Recording *and* Accessibility, `microphone`
/// is the mic *and* the system-audio tap — and `Permissions.groupedReport` ANDs the members, so a group
/// with one half granted reads `Action required`. The four-word status vocabulary
/// (`Granted` / `Open` / `Checking` / `Action required`, `docs/design-system.md` § Permission row)
/// cannot say *which* half, and it should not be asked to: the status column answers "is there work",
/// and the noun answers "on what". So the noun moves instead, and the vocabulary is untouched.
///
/// The defect this fixes: with Screen Recording granted and Accessibility not, the popover read
/// **Screen — Action required** over a screen that was being captured perfectly well. A user who
/// opened Screen Recording in System Settings found this app already ticked, and had no way to learn
/// from the row that the missing grant was a different one in a different pane. The symmetrical case
/// is the microphone group, which said **Microphone — Action required** while the microphone worked
/// and only the system-audio tap was missing.
///
/// It is a value, not a computed property on a view, for the reason `AccountPresentation` is one: the
/// interesting claim is about a combination of live TCC answers, and injecting the `granted` closure
/// is the only way a test can drive the half-granted state that made the row lie.
struct MenuBarCapabilityRow: Equatable, Identifiable {
    let group: CapabilityGroup
    /// What the row is called. The group's own noun when the whole group is in or the whole group is
    /// out; the missing member's noun when only part of it is missing.
    let noun: String
    let granted: Bool
    /// Untouched from `CapabilityReport.detail` — one of the four words, decided by `Permissions`.
    let status: String

    var id: String { group.rawValue }

    /// - Parameter report: the grouped report the engine publishes. Its `granted` and `detail` are
    ///   passed through unchanged; only the noun is decided here.
    /// - Parameter isGranted: the per-record answers. Injectable so the half-granted row is testable.
    init(report: CapabilityReport, isGranted: (Capability) -> Bool) {
        let group = CapabilityGroup(rawValue: report.name)
        self.group = group ?? .screen
        self.granted = report.granted
        self.status = report.detail
        guard let group else {
            self.noun = report.name
            return
        }
        // `firstMissing` is the same member the row's tap acts on (`StatusView.handle`), so the noun
        // names the pane the press opens. Nil — nothing missing — keeps the group's own noun, which
        // is also right for a granted screen still waiting on a relaunch: the work is on the screen.
        self.noun = (group.firstMissing(isGranted) ?? group.namesake).noun
    }
}

extension CapabilityGroup {
    /// The member the group is named after. Naming it explicitly rather than taking `members[0]`,
    /// because "the first one to ask for" and "the one this group is called after" are two ideas that
    /// happen to coincide, and a reordering of `members` must not silently rename the row.
    var namesake: Capability {
        switch self {
        case .microphone: return .microphone
        case .screen: return .screen
        }
    }
}

extension Capability {
    /// The plain noun for a glance surface, where `Capability.title`'s first-person sentence would be
    /// a paragraph in a 22 pt menu row.
    ///
    /// `accessibility` is spelled the way **System Settings** spells it, not the way the app describes
    /// it ("read the text in your windows"), because the row's entire job in that state is to send the
    /// user to Privacy & Security ▸ Accessibility and have them recognise it when they arrive.
    var noun: String {
        switch self {
        case .microphone: return "Microphone"
        case .systemAudio: return "System audio"
        case .screen: return "Screen"
        case .accessibility: return "Accessibility"
        }
    }
}

// MARK: - The repair the popover can offer and must not perform

/// **The one screen state whose remedy the app can hand over but must not carry out.**
///
/// `Permissions.ScreenBlock.recordUnusable` is the state where this process started *holding* the
/// Screen Recording grant and macOS refused it anyway. Window-server capture rights are settled when
/// a process connects, so the next process starts from exactly the same place: reopening cannot fix
/// it, and by the time a user reaches this state the app has already told them to reopen. Proven
/// live across two consecutive processes, against a `tccd` requirement pinning an ad-hoc build's
/// certificate leaf while this build carries a Developer ID signature.
///
/// What actually works is deleting the record, and only the user can be allowed to do that:
///
/// - **The detection is an inference, not a reading of TCC's stored requirement.** A false positive
///   would silently destroy a working consent record — an outcome strictly worse than the state it
///   was trying to repair.
/// - **An app that resets its own TCC records to re-prompt is indistinguishable from consent-fatigue
///   farming**, and a screen-and-microphone recorder is the last piece of software that should
///   normalise the pattern.
///
/// So the app goes exactly as far as it honestly can: it puts the command on the clipboard. That
/// removes the one failure this instruction is most likely to meet — a bundle id mistyped out of a
/// popover — while the destructive step stays in the user's own Terminal, where they can read it
/// before they run it.
///
/// A value rather than three `if`s inside the popover, for the reason `AccountPresentation` is one:
/// "which states offer this" has a wrong answer available in four directions and every input is a
/// live TCC answer.
struct ScreenRepairControl: Equatable {
    /// The command, read from the one place that spells it. `Permissions` owns it because the sentence
    /// that tells the user to run it is rendered there; this control only copies it, and a clipboard
    /// that disagrees with the instruction on screen is worse than no button at all.
    static let resetCommand = Permissions.screenRecordResetCommand

    /// The short line above the control. Deliberately not `ScreenBlock.reason` — that sentence is
    /// already on this surface as the paused line, and the popover is 320 pt wide.
    var note: String
    /// The control's label, which is also its confirmation. The popover's own idiom: the connector
    /// line's button says "Connecting…" rather than growing a second colour or a toast, because on a
    /// surface this small a word is a better signal than a shade.
    var action: String
    /// What the press puts on the clipboard.
    var command: String { Self.resetCommand }

    /// - Parameters:
    ///   - block: the live screen state. **Only `.recordUnusable` gets this control**: `.notGranted`
    ///     wants the switch, `.grantLost` wants it off and back on, and `.needsRelaunch` wants a
    ///     reopen — all three are remedies that work, and replacing one with a Terminal command
    ///     would be the app sending somebody to a shell over a click.
    ///   - copied: whether the last press has landed and not yet faded.
    static func of(_ block: Permissions.ScreenBlock?, copied: Bool) -> ScreenRepairControl? {
        guard block == .recordUnusable else { return nil }
        return ScreenRepairControl(
            note: "Reopening can’t replace this permission. Run the reset command in Terminal, then "
                + "grant Screen Recording once more.",
            action: copied ? "Copied" : "Copy fix command")
    }
}

// MARK: - The connector line

/// What the popover's Claude line says and offers, as a value.
///
/// A value for the reason `AccountPresentation` is one, and for one more: this line is the tallest
/// thing on the surface. `Connected to Claude Code and Claude Desktop` does not fit the popover's
/// text column on one line, so the sentence naming *both* surfaces is the state that makes the
/// connection/account block outgrow whatever room the popover reserves for it — and it is decided by
/// two booleans read off two config files this process does not own, which nothing hermetic can
/// arrange on disk. Reducing it to a function of those booleans is what puts the multi-line state,
/// and the note that can appear under it, inside reach of a measurement.
struct ClaudeConnectorLine: Equatable {
    var summary: String
    /// `ClaudeRegistrar`'s sentence from the last press, when there was one.
    var note: String?
    var isConnected: Bool
    /// The one press, or `nil` once there is nothing left to connect. It carries the in-flight state
    /// rather than a second control, which is what stops a second press starting a second write.
    var action: String?

    init(connection: ClaudeConnection, note: String?, isConnecting: Bool) {
        // **`desktopIsReachable`, not `claudeDesktop`.** The line reports what Claude can do, and a
        // Claude Desktop that has not read the registration yet cannot do anything — saying
        // "Connected to Claude Desktop" over a connector that fails to answer is the exact claim
        // `ClaudeConnection` exists to stop this surface making.
        switch (connection.claudeCode, connection.desktopIsReachable) {
        case (true, true): summary = "Connected to Claude Code and Claude Desktop"
        case (true, false): summary = "Connected to Claude Code"
        case (false, true): summary = "Connected to Claude Desktop"
        case (false, false): summary = "Not connected to Claude"
        }
        isConnected = connection.claudeCode || connection.desktopIsReachable
        // The remedy takes the note slot only when there is no fresher one: a sentence describing
        // the write the user just asked for is about the press they just made, and outranks a
        // standing condition they can act on whenever they like.
        self.note = note ?? connection.restartNotice
        // **Offered only when nothing is registered at all.** `Connect` writes the config files, so
        // in the needs-restart state it would rewrite two files that are already correct and change
        // nothing the user can see — a control that answers a real complaint with a no-op is worse
        // than no control. The sentence in `note` names what actually works.
        let hasNothingRegistered = !connection.claudeCode && !connection.claudeDesktop
        action = hasNothingRegistered ? (isConnecting ? "Connecting…" : "Connect") : nil
    }
}

// MARK: - The account line

/// Everything the popover's account line says and offers, as a value rather than as four `if`s
/// inside a view.
///
/// It is a value for the reason `InkGlass`'s settings are: the claim worth asserting is *"there is
/// always a way back to an account"*, and that claim is about a combination of three flags on a
/// `@MainActor` singleton that performs a browser round trip. Nothing hermetic can drive `OmiAuth`
/// through a real sign-in; reducing the decision to a function of the flags puts it inside reach of
/// a test, and leaves the view with no judgement of its own.
///
/// The defect it exists to make unrepeatable: the popover shipped with `Sign out` and nothing to
/// undo it. Onboarding does not run twice, the app is `LSUIElement` — no Dock icon, no window menu —
/// and there is no account pane, so signing out took the user somewhere the app could not leave.
struct AccountPresentation: Equatable {

    /// The single press on the account line. There is never more than one, and `action` is `nil`
    /// while the browser round trip is open: a second press cannot start a second sign-in, and a
    /// live control that does nothing is worse than no control.
    enum Action: Equatable {
        case signOut
        /// Reveal the provider rows.
        case signIn
        /// Put them away again. Same press, so the row cannot become a one-way door either.
        case dismissProviders

        var title: String {
            switch self {
            case .signOut: return "Sign out"
            case .signIn: return "Sign in"
            case .dismissProviders: return "Not now"
            }
        }

        /// Whether the link is the *repair* for a line the app has just said is broken.
        ///
        /// This is the popover's one use of `Ink.accent`, and it is now shared with the connector
        /// line's `Connect` — the two are the same affordance and would read as different urgencies
        /// if only one of them were accented. `Sign out` is not one: it is a link on a line that is
        /// already settled, and it stays a quiet `Ink.tertiary`.
        var isRepair: Bool { self == .signIn }
    }

    var summary: String
    /// The small second line: why the last sign-in failed, or what is stuck on the way up.
    var note: String?
    var noteIsError: Bool
    /// `nil` when there is nothing to press.
    var action: Action?
    /// Whether the two provider rows are drawn under the line.
    var showsProviders: Bool

    /// - Parameters:
    ///   - offeringProviders: the view's disclosure state. Deliberately only a *request* — the
    ///     rows are never shown unless the account is genuinely signed out and idle, so a stale
    ///     disclosure cannot survive into a live round trip.
    ///   - signInError: the last failed attempt's sentence, from `OmiAuth.lastSignInError`.
    ///   - uploadNote / uploadFailed: the backlog, from `ConversationUploader`.
    init(
        signedIn: Bool,
        signingIn: Bool,
        email: String?,
        offeringProviders: Bool,
        signInError: String?,
        uploadNote: String?,
        uploadFailed: Bool
    ) {
        if signedIn {
            summary = "Syncing to \(email ?? "your Omi account")"
            note = uploadNote
            noteIsError = uploadFailed
            action = .signOut
            showsProviders = false
            return
        }

        if signingIn {
            // The round trip is open and the browser has it. Saying "not signed in" here would be
            // true and useless; this is the sentence that tells the user where to look.
            summary = "Waiting for your browser…"
            note = uploadNote
            noteIsError = uploadFailed
            action = nil
            showsProviders = false
            return
        }

        summary = "Not signed in — nothing is reaching your Omi account"
        // A failed sign-in is *why* the backlog is not moving, so it wins the one line available:
        // the cause is actionable and the symptom is noise.
        if let signInError, !signInError.isEmpty {
            note = signInError
            noteIsError = true
        } else if let uploadNote {
            note = uploadNote
            noteIsError = uploadFailed
        } else {
            // Nothing has gone wrong, so the line is free to say what this state *costs* — and it
            // has to, because the cost is invisible and was never disclosed anywhere.
            note = Self.signedOutCost
            noteIsError = false
        }
        action = offeringProviders ? .dismissProviders : .signIn
        showsProviders = offeringProviders
    }

    /// What signing out actually costs, on the line that is otherwise blank.
    ///
    /// `OmiAuth.signOut()` calls `MCPKeyProvisioner.shared.removeKey()`, which deletes this Mac's
    /// `omi_mcp_…` credential. That is not only "uploads stop": `/v1/mcp/*` is the one endpoint
    /// family a Firebase session token cannot open, so with the key gone Claude can no longer reach
    /// the account half of this product at all — months of Omi history — while the local capture on
    /// this Mac keeps working and keeps answering. The two halves failing separately is exactly the
    /// state a user cannot diagnose from the outside, and until this line existed nothing in the app
    /// said the press had done it or that signing back in undoes it. `MCPKeyProvisioner.ensureKey()`
    /// runs on the next successful sign-in, which is what makes the second sentence true.
    static let signedOutCost =
        "Signing out removed this Mac's Omi key, so Claude can only see what was captured here — not "
        + "your account history. Signing in restores it."

    /// One provider row. A named type rather than a tuple because `ForEach` identifies its elements
    /// by key path and Swift has no key paths into tuples.
    struct ProviderChoice: Identifiable, Equatable {
        let title: String
        let provider: OmiAuthProvider
        var id: String { title }
    }

    /// The providers, in the order the onboarding card offers them, so the two surfaces cannot
    /// disagree about which one is the default-looking choice.
    static let providers: [ProviderChoice] = [
        ProviderChoice(title: "Continue with Google", provider: .google),
        ProviderChoice(title: "Continue with Apple", provider: .apple),
    ]
}
