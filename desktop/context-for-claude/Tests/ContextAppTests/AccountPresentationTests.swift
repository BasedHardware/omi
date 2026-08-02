import XCTest

@testable import ContextApp

/// The popover's account line.
///
/// Every claim here is about the state machine and not about the OAuth round trip: `OmiAuth` opens a
/// browser and talks to three servers, so nothing hermetic can drive it through a real sign-in. What
/// *can* be held is the thing that actually broke — which control the line offers for a given set of
/// flags — which is why that decision is a value (`AccountPresentation`) rather than four `if`s
/// inside `StatusView`.
final class AccountPresentationTests: XCTestCase {

    /// The convenience the rest of this file is written against. Signed out and idle is the default
    /// because it is the state the defect lived in.
    private func line(
        signedIn: Bool = false,
        signingIn: Bool = false,
        email: String? = nil,
        offeringProviders: Bool = false,
        signInError: String? = nil,
        uploadNote: String? = nil,
        uploadFailed: Bool = false
    ) -> AccountPresentation {
        AccountPresentation(
            signedIn: signedIn,
            signingIn: signingIn,
            email: email,
            offeringProviders: offeringProviders,
            signInError: signInError,
            uploadNote: uploadNote,
            uploadFailed: uploadFailed)
    }

    // MARK: - The defect

    /// **Signing out must not be a one-way door.**
    ///
    /// This is the whole bug. The popover carried `Sign out` and offered nothing to undo it, and
    /// there is nowhere else in the product to recover: onboarding does not run a second time, the
    /// app is `LSUIElement` so there is no Dock icon and no window menu, and there is no account
    /// pane. A user who signed out had no route back to an Omi account at all, and everything that
    /// needs one — the uploaders, cloud transcription, the MCP credential — stayed dark forever.
    ///
    /// Asserted over every combination of the two flags that are *not* about signing in, so the way
    /// back cannot be lost again to a backlog note or a stale error.
    func testASignedOutLineAlwaysOffersAWayBackIn() {
        for note: String? in [nil, "3 conversations waiting to upload"] {
            for failure: String? in [nil, "Sign-in didn't finish."] {
                let idle = line(signInError: failure, uploadNote: note, uploadFailed: note != nil)
                XCTAssertEqual(
                    idle.action, .signIn,
                    "a signed-out account line with note \(String(describing: note)) and error "
                        + "\(String(describing: failure)) offered no way back in")
                XCTAssertEqual(idle.action?.title, "Sign in")
            }
        }
    }

    /// …and the press really opens the choice, and the choice really closes again.
    ///
    /// The second half matters as much as the first: a disclosure with no way out is the same class
    /// of dead end one row further down, on a surface where the only other escape is closing the
    /// popover and hoping the state does not persist.
    func testTheSignInLinkOpensTheProvidersAndTheSameLinkPutsThemAway() {
        let closed = line()
        XCTAssertFalse(closed.showsProviders)

        let open = line(offeringProviders: true)
        XCTAssertTrue(open.showsProviders)
        XCTAssertEqual(open.action, .dismissProviders)
        XCTAssertEqual(open.action?.title, "Not now")

        XCTAssertEqual(
            AccountPresentation.providers.map(\.provider), [.google, .apple],
            "the popover has to offer the same providers, in the same order, as the onboarding card")
        XCTAssertEqual(
            AccountPresentation.providers.map(\.title),
            ["Continue with Google", "Continue with Apple"])
    }

    // MARK: - The round trip

    /// **Nothing is offered while the browser has it.**
    ///
    /// `OmiAuth.signIn` refuses a second concurrent round trip, so a live provider row during one is
    /// a control that does nothing — worse than no control, because the user presses it and
    /// concludes the app is broken. The disclosure flag is deliberately only a *request*: a stale
    /// `true` left over from before the popover was torn down must not survive into the open round
    /// trip, which is exactly what happens when the browser takes focus and the popover closes.
    func testNoControlIsOfferedWhileTheBrowserRoundTripIsOpen() {
        let waiting = line(signingIn: true, offeringProviders: true)

        XCTAssertNil(waiting.action, "no link at all is drawn while the browser has the round trip")
        XCTAssertFalse(
            waiting.showsProviders,
            "a stale disclosure survived into a live round trip; a second press cannot start a "
                + "second sign-in, so the row must not be there to press")
        XCTAssertEqual(
            waiting.summary, "Waiting for your browser…",
            "\"not signed in\" during a round trip is true and useless — the user needs to be told "
                + "where the app is waiting")
    }

    // MARK: - Signed in

    func testASettledLineNamesTheAccountAndOffersOnlyTheQuietWayOut() {
        let settled = line(signedIn: true, email: "someone@example.com")

        XCTAssertEqual(settled.summary, "Syncing to someone@example.com")
        XCTAssertEqual(settled.action, .signOut)
        XCTAssertFalse(settled.showsProviders)

        // A session restored from the Keychain carries no email claim until the first refresh, and
        // "Syncing to " with nothing after it is the shape of a bug.
        XCTAssertEqual(line(signedIn: true).summary, "Syncing to your Omi account")

        // A stale disclosure cannot outlive a sign-in either.
        XCTAssertFalse(line(signedIn: true, offeringProviders: true).showsProviders)
    }

    // MARK: - The one accent

    /// The popover spends `Ink.accent` on **repair links only** — the press that fixes a line the
    /// app has just said is broken. `Sign in` is one and so is the connector line's `Connect`;
    /// `Sign out` is not, because it is a link on a line that is already settled, and a settled line
    /// asking for attention is the popover crying wolf.
    func testOnlyTheRepairLinkSpendsTheAccent() {
        XCTAssertTrue(AccountPresentation.Action.signIn.isRepair)
        XCTAssertFalse(AccountPresentation.Action.signOut.isRepair)
        XCTAssertFalse(AccountPresentation.Action.dismissProviders.isRepair)
    }

    // MARK: - The second line

    /// A failed sign-in is *why* nothing is uploading, so it takes the one small line available.
    /// Showing the backlog instead would report the symptom and hide the cause.
    func testAFailedSignInDisplacesTheBacklogNote() {
        let failed = line(
            signInError: "Omi rejected the sign-in.",
            uploadNote: "3 conversations waiting to upload")

        XCTAssertEqual(failed.note, "Omi rejected the sign-in.")
        XCTAssertTrue(failed.noteIsError)

        // With no failure to report, the backlog gets the line back.
        let quiet = line(uploadNote: "3 conversations waiting to upload")
        XCTAssertEqual(quiet.note, "3 conversations waiting to upload")
        XCTAssertFalse(quiet.noteIsError, "a backlog is a fact, not a failure — it must not go red")

        // An empty string is not an error. `OmiAuth` clears the field rather than blanking it, but a
        // blank sentence in red is the worst of both.
        XCTAssertNil(line(signInError: "").note)
        XCTAssertFalse(line(signInError: "").noteIsError)
    }
}
