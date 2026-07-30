import Foundation

/// The tutorial's beats, in the order they are shown.
///
/// The order lives in `flow` rather than in `CaseIterable`'s declaration order so the two terminal
/// states can sit in the same enum without being reachable by advancing, and so a re-order is one
/// array literal rather than a scattered set of `case`s in a `next()` switch.
enum TutorialStep: String, CaseIterable, Sendable {
    /// G1 — "Learn how this works", Start / Skip.
    case invitation
    /// G2 — a real, text-dense page opens in the user's own default browser.
    case article
    /// G3 — Screen Recording, asked for here and only if it is genuinely missing.
    case screenAccess
    /// G4/G5 — "scroll around and collect your first frames", counted from the store.
    case collectFrames
    /// G6 — "it's time to open the timeline", showing the chord.
    case openTimeline
    /// G7 — the real timeline window is up.
    case timeline
    /// G8 — "scroll left to see what you did in the past".
    case scrollBack
    /// G9 — "find specific moments — click Search All".
    case findMoments
    /// G10/G11 — type a query, press Return.
    case query
    /// G12 — a real result, and tapping it goes back to that exact moment.
    case foundIt
    /// The handoff the first-run plan ends on: Claude reads its MCP config at startup, so it has to
    /// be restarted before it can answer from this store.
    case claudeHandoff
    /// The payoff, gated on `QueryStamp`: Claude has genuinely called one of our tools.
    case claudeProof
    /// G13 — "you're all set".
    case allSet
    /// G14 — "one more thing", with the menu bar spotlight.
    case menuBar

    /// Ran to the end.
    case finished
    /// Abandoned. Distinct from `finished` because the two leave the app in the same *visual* state
    /// (nothing on screen) and in different *product* states — only one of them has taught anything.
    case skipped

    /// Every step the user is walked through, in order. Terminal states are deliberately absent.
    static let flow: [TutorialStep] = [
        .invitation, .article, .screenAccess, .collectFrames, .openTimeline, .timeline,
        .scrollBack, .findMoments, .query, .foundIt, .claudeHandoff, .claudeProof, .allSet, .menuBar,
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
    /// time passing, and one whose gate is `genuineStamp` cannot be satisfied by this app at all.
    var gate: TutorialGate {
        switch self {
        case .screenAccess: return .screenRecordingGrant
        case .collectFrames: return .realFrames
        case .query: return .realSearchResult
        case .claudeProof: return .genuineToolCall
        case .invitation, .article, .openTimeline, .timeline, .scrollBack, .findMoments, .foundIt,
             .claudeHandoff, .allSet, .menuBar:
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
        case .collectFrames: return .browserWindow
        case .scrollBack: return .timelineTrack
        case .findMoments: return .searchAllButton
        case .query, .foundIt: return .timelineWindow
        default: return nil
        }
    }
}

/// What a step is waiting for. Only one of these can be satisfied by the user pressing a button.
enum TutorialGate: Equatable, Sendable {
    /// Pressing continue is the whole requirement.
    case userAction
    /// The real TCC grant. Waivable — the tutorial then says frames will not arrive.
    case screenRecordingGrant
    /// Frames genuinely in the capture store, counted from it. Waivable, loudly.
    case realFrames
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
        case .userAction, .screenRecordingGrant, .realFrames: return true
        case .realSearchResult, .genuineToolCall: return false
        }
    }
}

/// A real piece of UI a coach mark can be positioned against. Every case is something whose frame is
/// discoverable at runtime; nothing here is a constant.
enum TutorialTarget: Equatable, Sendable {
    /// The default browser's frontmost window, found through the window server.
    case browserWindow
    /// Our own timeline window, found through `NSApp.windows`.
    case timelineWindow
    /// The timeline's track, derived from the timeline window's actual frame.
    case timelineTrack
    /// The timeline's "Search All" pill, found by walking our own accessibility tree.
    case searchAllButton
}
