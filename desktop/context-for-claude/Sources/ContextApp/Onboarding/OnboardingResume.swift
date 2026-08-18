import Foundation

/// **Where onboarding was when the process last went away.**
///
/// Onboarding is the one flow in this app that a *successful* step can end the process from the
/// middle of: Screen Recording only applies to a process that already had it when it connected to
/// the window server, so the card's own "Restart to finish" — and macOS's own "Quit & Reopen" on the
/// system dialog — both kill the app between the grant and the finish. Without a record of where the
/// user was, the replacement process sees `context.onboarded` still unset and starts over from the
/// top: the eight-second cinematic, the welcome card, the value card, sign-in.
///
/// Reported verbatim: *"when I open the app again, myself manually, it goes to the initial cinematic
/// intro and everything, and I have to go through everything again. Though the permissions that have
/// already been granted shows granted, but I have to see it again, which should not happen."*
///
/// That last clause is the precise diagnosis. Nothing was *lost* — the grants are TCC's and the card
/// read them back correctly — so the only thing the user had to redo was the walking. This type is
/// the missing memory, and nothing more: it records the card, never the answers. Every permission
/// state is still read live from macOS on arrival, because a record of a grant is a second copy of a
/// fact TCC already owns and would be wrong the moment a switch moved under it.
///
/// **Recorded on transition, not on arrival.** A user who quits during the cinematic or on the
/// welcome card has done nothing to preserve, and starting them over is not a loss — it is the first
/// run they never finished. Only `go(to:)` writes here, so a resume point exists exactly when the
/// user has moved off the first card under their own power.
struct OnboardingResume {

    /// Namespaced with the app's other `context.*` defaults. Not the same key as
    /// `context.onboarded`: that one is a terminal fact ("this install is set up") written in exactly
    /// one place (`OnboardingView.sealTheRun`) and cleared in exactly one other (`OnboardingReset`,
    /// which spends this record in the same breath), and overloading it to also mean "and here is
    /// where you were" is how a flag ends up unable to express the state between the two.
    static let key = "context.onboarding.step"

    /// **Stable tokens, deliberately not `rawValue`.**
    ///
    /// `OnboardingStep` is `Int`-backed and its raw values are positional — they are what
    /// `next(after:)` compares to decide ordering, so inserting a card in the middle renumbers every
    /// card after it. A persisted `2` would then resume a mid-upgrade user onto somebody else's
    /// screen, silently, once, on a build nobody could reproduce. A token table costs one line per
    /// case and makes the ordering free to change.
    private static let tokens: [OnboardingStep: String] = [
        .welcome: "welcome",
        .value: "value",
        .signIn: "signIn",
        .permissions: "permissions",
        .connector: "connector",
        .tutorial: "tutorial",
        .done: "done",
    ]

    private let defaults: UserDefaults

    init(defaults: UserDefaults = .standard) {
        self.defaults = defaults
    }

    /// The card to open on, or `nil` for a first run that has nothing to resume.
    ///
    /// An unrecognised token answers `nil` rather than guessing. That is the downgrade case — a
    /// build that wrote a card this one does not have — and starting over is a bad morning; starting
    /// on the wrong card is a bug report nobody can read.
    var step: OnboardingStep? {
        guard let token = defaults.string(forKey: Self.key) else { return nil }
        return Self.tokens.first { $0.value == token }?.key
    }

    func record(_ step: OnboardingStep) {
        guard let token = Self.tokens[step] else { return }
        defaults.set(token, forKey: Self.key)
    }

    /// Called when the flow finishes. The resume point is scaffolding for an unfinished run and has
    /// to go with it — a stale one would reopen the card over a user who is done.
    func clear() {
        defaults.removeObject(forKey: Self.key)
    }
}
