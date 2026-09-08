//
//  ActivityAccountLocalNote.swift — the line that keeps the local memory column honest.
//
//  `ActivityLocalMemories` gives the spine a third state, and it is the one that has to be said out
//  loud. The panel could already tell **empty** from **unreachable**, and both of those are visible
//  as a change in the list: there are no rows, and `ActivityEmptyCopy` explains why. A column filled
//  from this Mac is invisible in exactly that way — those are the account's real memories, drawn the
//  way live ones are drawn, under a panel that says nothing. Unmarked, an eight-hour outage looks
//  like an ordinary Tuesday.
//
//  **The shipping Omi app says nothing here at all** — it renders its cache, the fetch fails, and no
//  error UI appears; that is why the 503s ran for eight hours without a single failure line in its
//  log. That silence is defensible for an app whose job is to show you your memories. It is not
//  defensible for this one, whose whole character is telling you what it does and does not know, and
//  which spends the rest of this surface carefully distinguishing "nothing was captured" from
//  "nothing could be read". One quiet accurate line is the version of main's behaviour that belongs
//  here.
//
//  The register is `ActivityEmptyCopy`'s: name the state, name what the reader can do about it if
//  anything, and never imply something the surface is about to contradict.
//
//  Brand: `Ink` semantics only (INV-UI-1).
//

import SwiftUI

// MARK: - The copy

/// The line shown above the stream when a column on it was read from this Mac instead of the account.
///
/// A resolved value rather than a string built in a `body`, for the reason `ActivityEmptyCopy` is
/// one: the interesting part is *when it is allowed to appear*, and that is worth driving directly
/// rather than through a rendered view.
struct ActivityAccountLocalNote: Equatable, Sendable {
    let sentence: String

    /// Whether anything on screen came from this Mac rather than from the account, and what to say.
    ///
    /// - Parameters:
    ///   - locallySourced: `ActivityAccountFeed.locallySourced` — which columns had local rows merged
    ///     into them.
    ///   - answered: which sources the account actually answered for. **A source in both is not
    ///     worth a note**: the account answered, these are its rows, and a handful of not-yet-synced
    ///     memories merged alongside them is the normal healthy state — main does exactly the same
    ///     thing on every launch. The note is for the other case, where the account said nothing and
    ///     the column is standing on this Mac alone.
    ///   - kind: which chip is lit, and therefore **what is on screen to be mislabelled**. Under a
    ///     soloed `Rewind` or `Tasks` no memory is on screen at all, and a note about the memory
    ///     column there is a caveat on rows that are not there — the same mistake the empty copy made
    ///     when it blamed the account for an empty `Rewind`.
    ///   - reason: why the account did not answer, when the reader knows — which decides **whether
    ///     the note may promise a refresh**. `ActivityStore.scheduleAccountReread` only re-reads the
    ///     failures that time can fix, so telling an airgapped or signed-out user this "will refresh
    ///     itself" is a promise the surface has already decided not to keep. `nil` covers the partial
    ///     outage — some sources answered, so no whole-feed reason was recorded — and that one *is*
    ///     re-read, on the same ladder.
    /// - Returns: nil when nothing on screen is standing in for the account.
    static func resolve(
        locallySourced: Set<ActivityAccountSource>,
        answered: Set<ActivityAccountSource>,
        kind: ActivityKind,
        reason: ActivityAccountUnreachableReason? = nil
    ) -> ActivityAccountLocalNote? {
        // Declaration order, not set order, so the sentence reads the same way twice.
        let standingIn = ActivityAccountSource.allCases.filter { source in
            guard locallySourced.contains(source), !answered.contains(source) else { return false }
            return kind == .all || kind == source.kind
        }
        guard !standingIn.isEmpty else { return nil }

        return ActivityAccountLocalNote(
            sentence: "\(subject(standingIn, kind: kind)) come from the Omi app on this Mac — "
                + "your Omi account couldn't be read just now. " + repair(reason))
    }

    /// What the sentence is about. Under a soloed chip the reader already knows which kind they are
    /// looking at, so restating it would open the sentence by telling them what they just pressed.
    private static func subject(_ sources: [ActivityAccountSource], kind: ActivityKind) -> String {
        guard kind == .all else { return "These" }
        let names = sources.map { $0.kind.title.lowercased() }
        switch names.count {
        case 1: return "These \(names[0])"
        case 2: return "These \(names[0]) and \(names[1])"
        default: return "These \(names[0]), \(names[1]) and \(names[2])"
        }
    }

    /// The half of the sentence that says what happens next — and it may only say what is actually
    /// going to happen. Every branch is the repair `ActivityEmptyCopy` offers for the same state, in
    /// the same words, because the two lines can appear a few points apart on one screen and a
    /// reader meeting two different remedies for one problem has been given neither.
    private static func repair(_ reason: ActivityAccountUnreachableReason?) -> String {
        switch reason {
        case .airgapped:
            return "Airgap Mode is on, so your account isn't being read — turn it off in Settings "
                + "to bring it up to date."
        case .signedOut:
            return "Nothing is signed in, so sign in to Omi to bring it up to date."
        case .keyRejected, .keyUnavailable:
            return "Omi couldn't authenticate this Mac — sign out and back in from the menu bar to "
                + "reconnect it."
        // The failures time fixes, plus the partial outage, which the store schedules on the same
        // ladder. This is the only branch entitled to say that waiting is the answer.
        case .rateLimited, .noAnswer, .none:
            return "I'll ask it again shortly."
        }
    }
}

// MARK: - The strip

/// The note, drawn between the chips and the stream.
///
/// **Above the list rather than inside it**, because it is true of rows scattered all the way down
/// the stream and there is no single row to hang it on. It sits under the chips so that pressing one
/// changes the note and the list in the same frame — the note's subject is the chip's selection, and
/// two controls' worth of distance between them would read as a coincidence.
///
/// Not a colour. INV-UI-1 forbids the obvious one and the honest one is weight anyway: this is a
/// caveat on the list, not an alarm, and the surface reserves its only filled shapes for the
/// selected chip.
struct ActivityAccountLocalStrip: View {
    let note: ActivityAccountLocalNote

    var body: some View {
        HStack(alignment: .firstTextBaseline, spacing: 6) {
            Image(systemName: "internaldrive")
                .inkStyle(.statusLabel, color: Ink.secondary)
            Text(note.sentence)
                .inkStyle(.statusLabel, color: Ink.secondary)
                .fixedSize(horizontal: false, vertical: true)
            Spacer(minLength: 0)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .accessibilityElement(children: .combine)
        .accessibilityIdentifier("activity-account-local")
    }
}
