import Foundation

/// The tutorial's beats, in the order they are shown.
///
/// The order lives in `flow` rather than in `CaseIterable`'s declaration order so the two terminal
/// states can sit in the same enum without being reachable by advancing, and so a re-order is one
/// array literal rather than a scattered set of `case`s in a `next()` switch.
///
/// There are eleven of them and there used to be fourteen. The cuts were beats that taught nothing:
/// one that opened *a stranger's* website — teaching this app on somebody else's content — and one
/// that only announced the next beat. "It's time to open the timeline" came back as `openActivity`,
/// but inverted: it no longer announces a chord and then opens the window itself, it asks for the
/// chord and waits, and the window that appears is opened by the keypress. What is left is one idea
/// per card, and every card that asks for something waits for it.
///
/// ## Which surface the chord beat teaches, and why the timeline beat stopped riding it
///
/// `openActivity` was `openTimeline`, and the beat taught ⌘ + ⌘ as the way to the timeline — which
/// it was, for as long as the timeline was this app's one real window. It is not: the chord opens
/// the Activity surface, which is the same dismissible search panel `.openSearch` toggles. The beat
/// follows the chord, because the one thing a tutorial may never do is teach a gesture the app no
/// longer has.
///
/// That left `timeline` with nothing to open it, and the honest repair is not to drop the beat: the
/// drag through a captured day is the moment the product becomes obvious, and the timeline is still
/// where it happens. So the tutorial **opens that window itself** and says so
/// (`TutorialModel.enter(.timeline)`), the way it already opens a page for the capture beat. The
/// coach-mark rule that governs everything else here is untouched — the beat still cannot be left
/// until the user really drags — and nothing here claims a keypress nobody made.
///
/// The chord putting the *search panel* on screen is also why the drag beat takes it back off again:
/// see `usesSearchPanel`, and `TutorialModel.enter`.
///
/// The page came back too, and the word that was doing the work in that objection was *stranger's*.
/// `collectFrames` opens `anthropic.com` — Claude's own home, and the one page this app can put on
/// screen without picking a third party's content for somebody. What it replaces is worse than a
/// borrowed page: the beat used to tell the user to go and find something to look at, which on the
/// machine this runs on first is an empty desktop and a card waiting for frames that cannot arrive.
enum TutorialStep: String, CaseIterable, Sendable {
    /// "Let me show you what I do", Start / Skip.
    case invitation
    /// Screen Recording, asked for here and only if it is genuinely missing.
    case screenAccess
    /// "Scroll for a bit" — on the page this beat opens for them, gated on real frames.
    case collectFrames
    /// The chord, taught the only way a chord can be taught: the user presses it and the real
    /// surface opens because they did. That surface is the Activity search panel. Gated on the real
    /// shortcut really firing.
    case openActivity
    /// The timeline, opened by the tutorial, and the drag that travels through it. Gated on a real
    /// gesture — the opening is the tutorial's, the travelling has to be the user's.
    case timeline
    /// "Find one moment" — the real Search All pill, which opens the real search panel. Gated on
    /// that panel really being on screen.
    case findMoments
    /// Type a query into **the real search bar** and click the real hit that comes back, to travel
    /// to it. Gated on a real answer to a real question — which the typing itself produces, since
    /// the results narrow live. Deliberately not Return: that key hands the question to Claude and
    /// closes this panel.
    case query
    /// The handoff the first-run plan ends on: Claude reads its MCP config at startup, so it has to
    /// be restarted before it can answer from this store.
    case claudeHandoff
    /// The payoff, gated on `QueryStamp`: Claude has genuinely called one of our tools.
    case claudeProof
    /// "That's everything", and the one sentence that says what the capture beat really achieved.
    case allSet
    /// "One more thing", with the menu bar spotlight.
    case menuBar

    /// Ran to the end.
    case finished
    /// Abandoned. Distinct from `finished` because the two leave the app in the same *visual* state
    /// (nothing on screen) and in different *product* states — only one of them has taught anything.
    case skipped

    /// Every step the user is walked through, in order. Terminal states are deliberately absent.
    static let flow: [TutorialStep] = [
        .invitation, .screenAccess, .collectFrames, .openActivity, .timeline, .findMoments, .query,
        .claudeHandoff, .claudeProof, .allSet, .menuBar,
    ]

    var isTerminal: Bool { self == .finished || self == .skipped }

    /// The step after this one, or `.finished` at the end of the flow. Nil for a terminal state,
    /// which has no successor — asking for one is a bug rather than a no-op, and nil says so.
    var next: TutorialStep? {
        guard !isTerminal else { return nil }
        guard let index = Self.flow.firstIndex(of: self) else { return .finished }
        let following = index + 1
        return following < Self.flow.count ? Self.flow[following] : .finished
    }

    /// **The beat a *new process* may honestly pick this run up on.**
    ///
    /// Itself, for all but one of them — every beat re-reads the world on the way in, so a resumed
    /// `screenAccess` asks TCC again, a resumed `timeline` opens its own window again, and a resumed
    /// `findMoments` asks whether a panel is on screen right now.
    ///
    /// `claudeProof` is the exception, and it is a correctness one rather than a nicety. Its gate is
    /// a `QueryStamp` written **strictly after** an instant, and that instant is snapshotted by the
    /// beat before it (`TutorialModel.enter(.claudeHandoff)` sets `proofSince`). A process that woke
    /// straight onto the proof would be watching from instant zero, so a stamp Claude wrote at any
    /// point in the past — including during the run that just ended — would satisfy the one gate in
    /// this flow that this app cannot produce. The payoff would be a claim about something that did
    /// not happen, which is the failure the whole file is arranged around. Landing on the handoff
    /// starts the watch, and costs the user one card they have already seen.
    ///
    /// A property rather than an `if` at the resume site, for the same reason `placement` and
    /// `usesSearchPanel` are: a beat added later has to answer the question, and a test can read the
    /// answer.
    var resumeLanding: TutorialStep {
        self == .claudeProof ? .claudeHandoff : self
    }

    /// What has to be true before this step may be left behind.
    ///
    /// This is the honesty contract, written where the machine can be tested against it rather than
    /// left implicit in a pile of `if`s: a step whose gate is `realFrames` cannot be satisfied by
    /// time passing, and one whose gate is `genuineToolCall` cannot be satisfied by this app at all.
    ///
    /// Hiding the *mechanism* from the copy changed none of this. The card no longer counts frames
    /// out loud; the step still cannot be left until they are really there.
    var gate: TutorialGate {
        switch self {
        case .screenAccess: return .screenRecordingGrant
        case .collectFrames: return .realFrames
        case .openActivity: return .realHotkey
        case .timeline: return .realGesture
        case .findMoments: return .realSearchPanel
        case .query: return .realSearchResult
        case .claudeProof: return .genuineToolCall
        case .invitation, .claudeHandoff, .allSet, .menuBar:
            return .userAction
        case .finished, .skipped:
            return .userAction
        }
    }

    /// Which real surface this step's coach mark points at, if any. `nil` means the step is a card
    /// with nothing to point at, and a card is also what a step *becomes* when its target cannot be
    /// located — an arrow aimed at a guess is worse than a sentence.
    var target: TutorialTarget? {
        switch self {
        case .timeline: return .timelineTrack
        case .findMoments: return .searchAllButton
        // The real search panel, not the timeline the pill was pressed in: this beat is asking for a
        // question to be typed, and the field to type it into is in the panel floating above. The
        // card stands under it rather than over it — see `TutorialOverlay.under`.
        case .query: return .searchPanel
        default: return nil
        }
    }

    /// Where the card goes when it has no target to sit beside.
    ///
    /// "The middle of the screen" is only the right answer for a card whose whole job is to be read.
    /// Two beats put something else on screen and then ask the user to work in it:
    ///
    /// - `collectFrames` opens a page and asks them to scroll it. A card parked over the page is the
    ///   tutorial getting in the way of its own lesson.
    /// - The two Claude beats open **another application's window** and then ask the user to read it
    ///   and press Return in it. A centred card lands squarely on the column Claude's answer arrives
    ///   in and on the composer under it — which is the "it blocks the view" report — so those two
    ///   stand beside the real window rather than on it.
    var placement: TutorialPlacement {
        switch self {
        case .collectFrames: return .outOfTheWay
        case .claudeHandoff, .claudeProof: return .clearOfClaude
        default: return .centred
        }
    }

    /// Whether this beat has put **another application's window** in front of the user.
    ///
    /// True for exactly three: the browser at `collectFrames`, and Claude at the handoff and the
    /// proof. The timeline is ours and does not count.
    ///
    /// **What it decides is where the cinematic bed ends** (`TutorialModel`). `Sound.music` is a
    /// 24-second loop, started once at `begin()`, and the only thing that used to stop it was the
    /// tutorial ending — but the tutorial does not end on a schedule. `claudeProof` waits on Claude
    /// calling one of our tools and cannot be waived, so a run left sitting there looped the same bar
    /// at somebody for as long as they left it open. Reported from that beat as "you should really
    /// stop the noise after a while", and the honest reading is not *quieter*: the bed was never
    /// given a last beat. The first of these three is it. Music is ours; the window now in front of
    /// the user is not, and a loop running under somebody else's page is noise rather than
    /// atmosphere.
    ///
    /// Derived from `placement` rather than listed again, because it is the same fact: a card leaves
    /// the middle of the screen precisely when the user has been asked to work somewhere that is not
    /// this app. One answer, so the two cannot drift — and a beat added later has to answer the
    /// placement question anyway.
    var handsOverToAnotherApp: Bool { placement != .centred }

    /// Whether this beat is conducted **in the real search panel**.
    ///
    /// Two beats are: pressing the pill that opens it, and asking it a question. Everything else in
    /// the flow happens somewhere the panel would only be in the way — which is what this decides.
    /// `TutorialModel.enter` closes the panel on the way into any step that answers false, so a
    /// floating slab is never carried into a beat that is about something underneath it.
    ///
    /// **The beat this now matters most for is `timeline`, and it did not used to.** ⌘ + ⌘ opened a
    /// timeline once; it opens this panel. So the ordinary run reaches the drag beat with the panel
    /// the user just summoned sitting over the very window they are about to be asked to drag — and
    /// reaches the pill beat with the surface that beat teaches already on screen. One rule fixes
    /// both: the panel goes back where it came from on the way into any beat that does not use it.
    ///
    /// It only ever closes a panel this run watched come up (`TutorialModel.searchPanelIsOurs`); a
    /// panel the user already dismissed is not dismissed a second time.
    ///
    /// A property on the step rather than an `if` in the transition, for the same reason `placement`
    /// is one: a beat added later has to answer the question, and a test can read the answer.
    var usesSearchPanel: Bool { self == .findMoments || self == .query }

    /// Whether the card takes the keyboard when it appears.
    ///
    /// A card is a thing to press, so most of them do: this app is an accessory and is almost never
    /// frontmost, and a SwiftUI button in an inactive window spends the first click on activation.
    /// A coach mark does not, because the user is being asked to work in another window and taking
    /// focus off it mid-gesture takes the lesson away from them.
    ///
    /// **`claudeProof` is a card that must not**, and it is the reason this is a property rather
    /// than the `target == nil` test it grew out of. That beat is waiting for Claude to call one of
    /// our tools, which happens when the user presses Return in Claude's composer — so an app that
    /// activates over Claude the moment the beat begins eats the one keystroke the whole beat exists
    /// to wait for. The cost is that the Continue this card grows *afterwards* may need a click to
    /// activate first, which is the trade every coach-mark step in the flow already makes.
    ///
    /// **`query` used to be the exception and is now the rule.** It carried its own text field, so it
    /// had to be typable and took focus to be so. The typing happens in the real search bar now, and
    /// that bar is a non-activating panel whose whole trick is holding the first responder while this
    /// app is not frontmost — a coach mark that activated over it would take the field away from the
    /// user at the exact moment the card is asking them to type into it.
    var takesFocusOnEntry: Bool {
        guard self != .claudeProof else { return false }
        return target == nil
    }
}

/// Where a card with nothing to point at sits.
enum TutorialPlacement: Equatable, Sendable {
    /// The middle of the screen, a little above centre. What a card to be read wants.
    case centred
    /// The bottom trailing corner, clear of whatever the user was asked to go and do.
    case outOfTheWay
    /// Beside Claude's own window, in whichever band around it has the room. The only placement that
    /// is a function of something outside this app, because it is the only one that has to hold two
    /// things on screen at once: Claude, and the card coaching the user through it.
    case clearOfClaude
}

/// What a step is waiting for. Only one of these can be satisfied by the user pressing a button.
enum TutorialGate: Equatable, Sendable {
    /// Pressing continue is the whole requirement.
    case userAction
    /// The real TCC grant. Waivable — the tutorial then says frames will not arrive.
    case screenRecordingGrant
    /// Frames genuinely in the capture store, counted from it. Waivable, loudly.
    case realFrames
    /// The real global shortcut really fired, after this step began watching for it. Waivable — a
    /// machine with no Accessibility grant cannot fire it at all.
    ///
    /// **The waiver records nothing, and that is a change rather than an omission.** It used to set
    /// `didWaiveHotkey`, because the beat after it described a timeline that the chord had opened and
    /// had to say so when the tutorial had opened it instead. The chord opens Activity now and the
    /// timeline beat opens its own window on every run, so there is no downstream claim about this
    /// keypress left to qualify — and a flag set and never read is the defect `TutorialModel`'s rule
    /// 4 was written about.
    case realHotkey
    /// A real scroll gesture over one of this app's own windows, measured in points travelled.
    /// Waivable: a timeline that never opened has nothing to drag.
    case realGesture
    /// The **real search panel** is really on screen, reported by the panel itself
    /// (`SearchPanelEvent.opened` / `.closed`) rather than by the press that asked for it.
    ///
    /// Observed and not intercepted, which is the fix this case is named for: the tutorial used to
    /// swallow the "Search All" press and draw its own results on a coach card, so what the user
    /// learned to press opened a surface that only existed during the tutorial. Now the press falls
    /// through to the shell, the real bar opens because they pressed it, and this is how the beat
    /// finds out — the same shape as `realHotkey`, for the same reason.
    ///
    /// **A fact about the display, and it is one again.** This was briefly gated on the *ask* rather
    /// than the panel, because a search surface that had been promoted to a permanent window was up
    /// before the tutorial started and "is it on screen" said nothing about anybody. A dismissible
    /// panel is not: it closes on Escape, it closes when a result hands off to the timeline, and the
    /// tutorial takes it back off screen on the way into every beat that is not about it
    /// (`TutorialStep.usesSearchPanel`). So by the time this beat begins there is nothing up, and a
    /// panel appearing is once more the user having done something.
    ///
    /// Waivable, and the waiver opens the panel rather than skipping past it: the beat after this one
    /// has nothing to be asked without it.
    case realSearchPanel
    /// At least one real hit from a real search of the real store, reported by the real panel that
    /// ran it. Not waivable: a "found it" with nothing behind it is the one beat that would make
    /// everything else in the product suspect.
    case realSearchResult
    /// A `QueryStamp` written strictly after this run started watching. Not waivable, and not
    /// producible by this app — only Claude calling one of our MCP tools writes it.
    case genuineToolCall

    /// Whether the tutorial may move past this gate without it being met, given an explicit,
    /// labelled user action that says what did not happen.
    var isWaivable: Bool {
        switch self {
        case .userAction, .screenRecordingGrant, .realFrames, .realHotkey, .realGesture,
            .realSearchPanel:
            return true
        case .realSearchResult, .genuineToolCall: return false
        }
    }
}

/// A real piece of UI a coach mark can be positioned against. Every case is something whose frame is
/// discoverable at runtime; nothing here is a constant.
enum TutorialTarget: Equatable, Sendable {
    /// Our own timeline window, found through `NSApp.windows`.
    case timelineWindow
    /// The timeline's track, derived from the timeline window's actual frame.
    case timelineTrack
    /// The timeline's "Search All" pill, found by walking our own accessibility tree.
    case searchAllButton
    /// The real search panel, from `SearchBarWindow`'s own frame. Nil whenever it is not up, which is
    /// most of the time — the coach mark degrades to a card, the way every target here can.
    ///
    /// Asked of the window rather than reassembled from `SearchLayout`: the panel sizes itself to its
    /// own content, so a rectangle built out of layout constants is a guess that is wrong the moment
    /// a result row lands. Nothing in the tutorial computes this shape.
    case searchPanel
}
