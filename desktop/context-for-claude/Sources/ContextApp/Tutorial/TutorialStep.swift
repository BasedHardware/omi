import Foundation

/// The tutorial's beats, in the order they are shown.
///
/// The order lives in `flow` rather than in `CaseIterable`'s declaration order so the two terminal
/// states can sit in the same enum without being reachable by advancing, and so a re-order is one
/// array literal rather than a scattered set of `case`s in a `next()` switch.
///
/// There are eleven of them and there used to be fourteen. The cuts were beats that taught nothing:
/// one that opened *a stranger's* website — teaching this app on somebody else's content — and one
/// that only announced the next beat. "It's time to open the timeline" came back as `openTimeline`,
/// but inverted: it no longer announces a chord and then opens the window itself, it asks for the
/// chord and waits, and the window that appears is opened by the keypress. What is left is one idea
/// per card, and every card that asks for something waits for it.
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
    /// The chord, taught the only way a chord can be taught: the user presses it and the real window
    /// opens because they did. Gated on the real shortcut really firing.
    case openTimeline
    /// The real timeline window is up, and the drag that travels through it. Gated on a real gesture.
    case timeline
    /// "Find one moment" — the real Search All pill.
    case findMoments
    /// Type a query, press Return, and the real hit that comes back is tapped to travel to it.
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
        .invitation, .screenAccess, .collectFrames, .openTimeline, .timeline, .findMoments, .query,
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
        case .openTimeline: return .realHotkey
        case .timeline: return .realGesture
        case .query: return .realSearchResult
        case .claudeProof: return .genuineToolCall
        case .invitation, .findMoments, .claudeHandoff, .allSet, .menuBar:
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
        case .query: return .timelineWindow
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
    var takesFocusOnEntry: Bool {
        guard self != .claudeProof else { return false }
        // The query beat is a coach mark with a text field in it, so it has to be typable.
        return target == nil || self == .query
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
    /// machine with no Accessibility grant cannot fire it at all — and the waiver is explicit that
    /// the tutorial opened the window rather than the user.
    case realHotkey
    /// A real scroll gesture over one of this app's own windows, measured in points travelled.
    /// Waivable: a timeline that never opened has nothing to drag.
    case realGesture
    /// At least one real hit from a real search of the real store. Not waivable: a "found it" with
    /// nothing behind it is the one beat that would make everything else in the product suspect.
    case realSearchResult
    /// A `QueryStamp` written strictly after this run started watching. Not waivable, and not
    /// producible by this app — only Claude calling one of our MCP tools writes it.
    case genuineToolCall

    /// Whether the tutorial may move past this gate without it being met, given an explicit,
    /// labelled user action that says what did not happen.
    var isWaivable: Bool {
        switch self {
        case .userAction, .screenRecordingGrant, .realFrames, .realHotkey, .realGesture: return true
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
}
