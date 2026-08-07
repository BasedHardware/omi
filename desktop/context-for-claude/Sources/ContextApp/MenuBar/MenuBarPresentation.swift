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
        } else {
            note = uploadNote
            noteIsError = uploadFailed
        }
        action = offeringProviders ? .dismissProviders : .signIn
        showsProviders = offeringProviders
    }

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
