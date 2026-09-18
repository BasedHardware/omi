import Foundation

/// **Putting this install back to the state it launched in on the day it was installed** — and the
/// one place in the product that knows what that sentence covers.
///
/// Three defaults hold "this person has been through setup", and they are deliberately three rather
/// than one: `context.onboarded` is the terminal fact, `OnboardingResume` is the card an unfinished
/// run was on, and `TutorialResume` is the beat an unfinished walkthrough was on. Each is documented
/// beside the flow that owns it and none of them can be inferred from the others — which is exactly
/// why a reset that lived at its call site would be a reset that forgot one of them the first time a
/// fourth record appeared. The clearing is here so that a fourth record is a one-line change in one
/// file rather than a search for every place that thought it knew the whole list.
///
/// **What it deliberately does not do.** This resets a walkthrough, not an install. It does not sign
/// the user out, does not revoke or re-ask for any TCC grant (the permission cards read those live
/// from macOS on arrival and always did), does not touch the capture database, and does not clear a
/// single `context.settings.*` preference. A user who presses this keeps everything they have
/// captured, everything they have configured, and every permission they have granted; what they get
/// back is the eight-second intro and the cards.
///
/// **The login item is left registered on purpose.** `OnboardingView.sealTheRun` registers it and the
/// flow will register it again on the way out, so clearing it here would only produce a window in
/// which an app that has been launching at login for months quietly stops — a side effect of a button
/// whose copy promises a walkthrough.
struct OnboardingReset {

    private let defaults: UserDefaults

    init(defaults: UserDefaults = .standard) {
        self.defaults = defaults
    }

    /// Spends all three records.
    ///
    /// **`removeObject` rather than `set(false)`** for the terminal flag. `bool(forKey:)` answers
    /// `false` either way, so nothing reads differently today — but a first run is the *absence* of
    /// the key, and every future reader that distinguishes "never set" from "set to false" (a
    /// migration, a diagnostic, a defaults dump in a bug report) should see the same thing here that
    /// it sees on a machine the app has just been installed on.
    ///
    /// **The second writer of `context.onboarded`, and the only one that clears it.**
    /// `OnboardingView.sealTheRun()` is the only thing that ever sets it true, which is what
    /// `OnboardingSealsTheRunOnEveryExitTests` holds; this is the counterpart, and the doc comments on
    /// `CinematicGate` and `OnboardingResume` name it so no reader is left with a comment the code
    /// contradicts.
    ///
    /// The key is `CinematicGate`'s spelling rather than a fourth literal in a fourth file: a reset
    /// that cleared a key nobody reads would be a button that appears to do nothing, and the cheapest
    /// guarantee that this clears the flag the gate consults is to name the same constant it does.
    func clear() {
        defaults.removeObject(forKey: CinematicGate.onboardedKey)
        OnboardingResume(defaults: defaults).clear()
        TutorialResume(defaults: defaults).clear()
    }
}

// MARK: - Doing it now

extension OnboardingReset {

    /// **The reset as the user experiences it**: the records spent, and then the app doing exactly
    /// what it does at launch on a machine that has never been set up.
    ///
    /// It runs immediately and never on the next launch. A settings row that quietly arms something
    /// for a relaunch is a row that appears to do nothing, and this app spends most of its copy
    /// budget avoiding precisely that.
    ///
    /// The three steps, and why each is where it is:
    ///
    /// 1. **A walkthrough already on screen is a run of the flow being reset**, so it is torn down
    ///    first — coach marks, spotlight, watchers and all (`TutorialModel.tearDown`). Before the
    ///    clear rather than after, so the machine that owns those overlays is stopped while its own
    ///    record still describes it; abandoning writes nothing, so the clear that follows is still
    ///    what spends the record. A no-op when nothing is running.
    /// 2. **Settings closes.** It is the window the press came from and it is the wrong window to be
    ///    left holding: onboarding is a floating card that activates the app and takes focus, its
    ///    permissions step steps aside for System Settings, and its screen-recording step can end this
    ///    process outright — a settings window sitting under all of that is furniture from a task the
    ///    user has just left. The confirmation says so before it happens.
    /// 3. **`surfaceSomethingForTheUser()`**, which is the launch path itself rather than a second one
    ///    that has to agree with it. With the records spent it answers `.onboarding` — the same answer
    ///    a first launch gets — and `OnboardingWindow.present()` asks `CinematicGate`, which now plays
    ///    the eight-second intro because both halves of its question have been cleared. A reset that
    ///    called `OnboardingWindow.present()` directly would work today and would be the thing that
    ///    disagreed with launch the first time a fourth flow earned a place in `landing`.
    @MainActor
    static func restart() {
        Tutorial.abandon()
        OnboardingReset().clear()
        SettingsWindow.dismiss()
        ContextLog.info("onboarding reset from Settings; the first-run flow starts again", "onboarding")
        ContextAppDelegate.surfaceSomethingForTheUser()
    }
}
