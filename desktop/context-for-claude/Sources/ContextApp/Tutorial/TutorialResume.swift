import Foundation

/// **Where the walkthrough was when the process last went away.**
///
/// The tutorial has the same problem onboarding has, one card later, and for the same reason:
/// `TutorialStep.screenAccess` calls `CGRequestScreenCaptureAccess`, and the dialog macOS puts up in
/// answer offers **"Quit & Reopen"**. Pressing it ends this process from the middle of the flow —
/// which is a *designed-for* event here rather than an accident, because a screen grant only reaches
/// a process that already held it when it connected to the window server.
///
/// What the replacement process used to find was worse than onboarding's version of the same bug.
/// `context.onboarded` is already `true` and `OnboardingResume` is already spent — the last card of
/// onboarding seals the run before it hands over (`OnboardingView.startTutorial`) — so the successor
/// opened straight onto the Activity panel with the walkthrough simply gone, and nothing anywhere in
/// `MenuBar/` or `Settings/` calls `Tutorial.start`. There was no way back into it at all.
///
/// This is the missing memory and nothing more. It records the beat, never the answers: every gate in
/// the flow is a fact about the world — a TCC grant, frames in the store, a panel on screen, a stamp
/// on disk — and a second copy of any of them would be wrong the moment the world moved under it. A
/// resumed run re-reads all of them (`TutorialModel.begin(resumingAt:)`).
///
/// **Recorded on transition, not on arrival**, exactly as `OnboardingResume` is: `TutorialModel.enter`
/// writes here before the beat does anything, because some of these beats end the process as their
/// next act and a record written afterwards is a record written by a process that is already gone.
struct TutorialResume {

    /// Namespaced with the app's other `context.*` defaults, and a sibling of
    /// `context.onboarding.step` rather than an overload of it. The two flows are consulted in order
    /// at launch (`ContextAppDelegate.landing`) and a single key could not say which of them a user
    /// was in the middle of.
    static let key = "context.tutorial.step"

    private let defaults: UserDefaults

    init(defaults: UserDefaults = .standard) {
        self.defaults = defaults
    }

    /// The beat to pick the run up on, or `nil` when there is nothing to resume.
    ///
    /// Two records answer `nil` rather than a guess:
    ///
    /// - **An unrecognised token**, which is the downgrade case — a later build wrote a beat this one
    ///   does not have. Starting the walkthrough over is a small cost; starting it on the wrong beat
    ///   is a bug report nobody can read.
    /// - **A terminal state.** `finished` and `skipped` are not places a user can stand, and a run
    ///   that reached one is over. Nothing writes them (`record` declines), and this refuses to read
    ///   one back in case something ever does.
    var step: TutorialStep? {
        guard let token = defaults.string(forKey: Self.key),
            let step = TutorialStep(rawValue: token),
            !step.isTerminal
        else { return nil }
        return step
    }

    /// **The raw value is the token here, and that is a difference from `OnboardingResume` rather
    /// than a shortcut.**
    ///
    /// That type keeps a hand-written token table because `OnboardingStep` is `Int`-backed and its
    /// raw values are *positional* — `next(after:)` compares them to decide ordering — so inserting a
    /// card renumbers every card after it and a persisted `2` would resume a mid-upgrade user onto
    /// somebody else's screen. `TutorialStep` is `String`-backed and its order lives in
    /// `TutorialStep.flow`, an array literal that no raw value takes part in. The raw values are
    /// already names, so a second table of names would be a copy to keep in step with nothing.
    func record(_ step: TutorialStep) {
        // A terminal state is the absence of a resume point, not a value of one. `tearDown` is what
        // spends the record; writing "skipped" here would be a resume point that resumes nothing.
        guard !step.isTerminal else { return }
        defaults.set(step.rawValue, forKey: Self.key)
    }

    /// Called when the run is over — finished, or ended by the user. The record is scaffolding for an
    /// unfinished run and has to go with it: left behind, it reopens the walkthrough over somebody
    /// who has already done it, on every launch, forever.
    ///
    /// Deliberately **not** called when the process is torn down under a run that is still going. See
    /// `TutorialModel.abandon()`.
    func clear() {
        defaults.removeObject(forKey: Self.key)
    }
}
