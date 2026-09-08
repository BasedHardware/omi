import SwiftUI

// The two things the tutorial has to *show* rather than describe: the way in, and the way across.
//
// Both beats used to be a picture of the answer — a chip with the chord printed on it, three
// capsules sliding under a double-headed arrow — and both were reported the same way: the card asks
// for an action and shows a still life of it. A still keycap says *which* keys; it does not say
// whether they are struck one after the other or held down at the same instant. A sliding bar says
// something moved; it does not say that the user's fingers are what moves it, and it certainly does
// not say *how many* fingers, or what surface they are on.
//
// That last gap is the one this file was opened for a second time. The timeline beat said "drag
// across it with two fingers" and drew a single `hand.draw.fill` glyph over a strip, and it was
// reported exactly as you would expect: *"it isn't clear that they have to swipe on the trackpad
// with two fingers."* Words counted the fingers; the picture did not. So the picture counts them
// now — a trackpad, with two fingertips on it, planting, gliding and lifting — and the words and the
// drawing say the same number for the first time.
//
// So each of these is a loop of the real thing, and each stops for the same reason: the card that
// hosts it is only rendered while the step is still waiting (`TutorialCardView.extras`), so the
// demonstration disappears the moment the user does the thing themselves. Nothing here polls the
// model and nothing here can satisfy a gate — an animation that could would be the one lie this
// whole flow is built to avoid.
//
// The timing lives in a value type, not in the view. `TutorialChordCycle`, `TutorialCommandPair` and
// `TutorialSweepPose` are pure, so the claims that actually matter — that the picture shows the same
// gesture the app listens for, that the two Command keys are never shown going down one at a time,
// and that the content moves *with* the fingers rather than against them — are assertions a headless
// test can make. What cannot be asserted headlessly is the drawing, and nothing about the drawing
// decides what is being demonstrated.

// MARK: - Which gesture opens the app

/// **Both Command keys, pressed together**: the app's own way in, and a gesture no keycap chip can
/// spell.
///
/// This is a *local* description of the gesture, held here and nowhere else on purpose. The shortcut
/// layer owns what the app listens for; this file owns what the card draws; and the only thing that
/// crosses between them is the printed shortcut string the tutorial already reads through
/// `TutorialEnvironment.activityChord`. Nothing here imports a case name, so a rename in
/// `Shortcuts/` cannot silently repoint the picture at a different gesture — it can only ever make
/// `matches` stop recognising the string, which falls back to the typed-chord drawing and is visible
/// in one look at the beat.
///
/// ## Why the spelling, and not the type, is the hinge
///
/// A Mac has two Command keys and one Command *modifier*: hold both and the flag mask goes down
/// once, exactly as if you had held one. That is why `⌘⌘` — two glyphs, adjacent, no separator —
/// has always meant the **repeated tap** in this product, and why it must keep meaning that here
/// (`TutorialChordCycle`, and the shipped `⌘⌘⇧` search default). The pair gesture therefore cannot
/// be spelled by adjacency; it has to be spelled with something *between* the two glyphs, and any
/// such separator will do — `⌘ + ⌘`, `⌘+⌘`, `⌘ ⌘`. That is the whole rule, and it is deliberately a
/// rule about the shape of the string rather than a list of one accepted spelling, so that the two
/// sides can disagree about punctuation without disagreeing about the gesture.
enum TutorialCommandPair {

    /// The characters that may sit between the two glyphs without being a third key.
    ///
    /// Whitespace and the three joiners a shortcut string plausibly uses. Anything else — another
    /// modifier glyph, a letter — is a real part of the chord and takes the string out of this
    /// gesture entirely.
    static let joiners: Set<Character> = [" ", "+", "·", "-", "&"]

    /// Whether a printed shortcut is this gesture.
    ///
    /// Two glyphs, both ⌘, with at least one joiner really removed. The second half of that is not
    /// decoration: without it `⌘⌘` matches, and `⌘⌘` is the double tap.
    static func matches(_ chord: String) -> Bool {
        let glyphs = chord.filter { !joiners.contains($0) && !$0.isWhitespace }
        guard glyphs == "⌘⌘" else { return false }
        return chord.count > glyphs.count
    }

    /// The gesture said out loud, for the one label a screen reader gets — and the same words the
    /// card's own aside uses, so the picture and the sentence cannot drift apart.
    static let spoken = "Press both Command keys together"

    // MARK: The loop

    /// How long one beat lasts. Slower than the chord demonstration's, because there is only one
    /// event in this loop and it needs room either side of it to read as a press rather than as a
    /// flicker.
    static let beat: Double = 0.26

    /// Beats the pair stays down. This is the moment the shortcut fires, so it is the only part of
    /// the loop that holds still long enough to look at.
    static let downBeats = 4

    /// Beats with both keys back up. Without this the loop has no beginning and the caps read as
    /// merely highlighted rather than as being pressed.
    static let restBeats = 3

    static var beats: Int { downBeats + restBeats }

    /// Which of the two keys are held at a beat.
    ///
    /// Two fields and not one `Bool`, and that is the entire point of the type. The defect this
    /// gesture is replacing was a picture of *two ⌘ caps lighting one after the other*, reported as
    /// "expressing both the command keys one by one. It's supposed to be both the command keys
    /// together." A pose that could only say "the pair is down" would make that defect
    /// unrepresentable in the drawing and also unassertable in a test; a pose with a left and a
    /// right can be checked, every beat, for having them agree.
    struct Pose: Equatable {
        let leftIsDown: Bool
        let rightIsDown: Bool

        var bothAreDown: Bool { leftIsDown && rightIsDown }

        /// How much of the tie between the two caps is drawn: 0 at rest, 1 while they are down.
        ///
        /// A tie rather than a third label, because "together" is a *relationship* between two keys
        /// and the one thing a static row of caps cannot express is that the two ends belong to one
        /// gesture. It grows from its middle outward (`TutorialCommandPairDemo`), which is the only
        /// direction that does not narrate one key reaching for the other.
        var tie: Double { bothAreDown ? 1 : 0 }
    }

    /// The pose at `tick`, which repeats every `beats`.
    ///
    /// **Reduce Motion holds the pair down rather than letting it go**, which is the opposite of what
    /// `TutorialChordDemo` does, and the difference is not an inconsistency. A chord at rest still
    /// says which keys to press — the caps are legible standing still. A *pair* at rest is precisely
    /// the ambiguous picture this gesture was reported for: two ⌘ caps side by side, saying nothing
    /// about whether they are struck in turn or held at once. So the still frame is the gesture at
    /// the instant it fires — both caps down, the tie complete — which is a legible drawing of
    /// "together" that never moves.
    static func pose(at tick: Int, reduceMotion: Bool) -> Pose {
        guard !reduceMotion else { return Pose(leftIsDown: true, rightIsDown: true) }
        let beat = ((tick % beats) + beats) % beats
        let isDown = beat < downBeats
        // Assigned from one value, deliberately. There is no arrangement of this loop in which one
        // Command key is down and the other is not, because there is no such gesture.
        return Pose(leftIsDown: isDown, rightIsDown: isDown)
    }
}

/// The bottom row of a Mac keyboard, as measurements.
///
/// The row is here rather than in the view because the tie has to start and end on the *centres of
/// two specific caps*, and a tie positioned by eye against a stack laid out by SwiftUI is a drawing
/// that comes apart the first time a cap changes width. One set of numbers produces both the row and
/// the tie's endpoints, so they cannot disagree.
///
/// **The space bar is the landmark and is why this is a row at all.** Two ⌘ caps floating on a board
/// are two badges; two ⌘ caps with a space bar between them are unmistakably the bottom row of the
/// keyboard the reader has their hands on, and "the two either side of the space bar" is an
/// instruction anybody can follow without looking down. Everything else on the row is context and is
/// drawn as context — see `contextOpacity`.
enum TutorialCommandRow {

    struct Cap: Equatable {
        let label: String
        let width: CGFloat
        /// Whether this is one of the two keys the beat is about.
        let isCommand: Bool
    }

    static let gap: CGFloat = 4
    static let height: CGFloat = 21

    /// How much of the row's ink the keys that are *not* the lesson get.
    ///
    /// Dimming rather than omitting: a row of ⌃ ⌥ ␣ ⌥ is what makes the two ⌘ caps read as being in
    /// their real places on a real keyboard, and a row where everything is equally bright makes the
    /// reader hunt for the subject before the press has even happened.
    static let contextOpacity: Double = 0.42

    /// Left to right, as macOS lays them out. `fn` and the arrow cluster are left off the ends: they
    /// are the two parts of the row nobody navigates by, and the row has to stay narrow enough to
    /// stand beside a sentence on a 470 pt card.
    static let caps: [Cap] = [
        Cap(label: "⌃", width: 21, isCommand: false),
        Cap(label: "⌥", width: 21, isCommand: false),
        Cap(label: "⌘", width: 27, isCommand: true),
        Cap(label: "", width: 76, isCommand: false),
        Cap(label: "⌘", width: 27, isCommand: true),
        Cap(label: "⌥", width: 21, isCommand: false),
    ]

    static var width: CGFloat {
        caps.reduce(CGFloat(0)) { $0 + $1.width } + gap * CGFloat(max(0, caps.count - 1))
    }

    /// The x of a cap's centre in the row's own coordinates.
    ///
    /// Zero for an index the row does not have, which is a stroke starting at the board's left edge
    /// — visibly wrong rather than a crash, which is the right failure for a drawing.
    static func centre(of index: Int) -> CGFloat {
        guard caps.indices.contains(index) else { return 0 }
        let before = caps[..<index].reduce(CGFloat(0)) { $0 + $1.width + gap }
        return before + caps[index].width / 2
    }

    static var commandIndices: [Int] { caps.indices.filter { caps[$0].isCommand } }
    static var leftCommand: Int { commandIndices.first ?? 0 }
    static var rightCommand: Int { commandIndices.last ?? 0 }

    /// How far below the caps the tie hangs.
    static let tieDrop: CGFloat = 9
}

// MARK: - The chord, being typed

/// Which of a chord's keycaps are held down at each beat of a repeating press.
///
/// Two shapes, because this app ships both and they are not the same gesture:
///
/// - **A repeated tap** — `⌘⌘⇧`, the default for `openSearch`, which is one key pressed twice with
///   another held across both halves. Drawing that as "hold the first ⌘ while you press the second"
///   is not a thing a hand can do, and a user copying the picture would never fire the shortcut.
/// - **An ordinary chord** — `⌘⇧K`, what a rebind produces. Here the modifiers really are held while
///   the last key is struck, and drawing it as three separate taps teaches the wrong gesture.
///
/// The third shape the app ships — both Command keys at once — is not here and cannot be: it is not
/// a sequence of caps at all. It lives in `TutorialCommandPair`.
///
/// The split is by keycap, and a keycap is not a character: `Space`, `⌫` and the `Key 40` fallback
/// are single keys with multi-character labels, so the leading run of modifier glyphs is peeled off
/// and everything after it is one cap.
///
/// ## A repeated tap is one cap, and this is the correction
///
/// `displayString` writes a double tap as the glyph *twice* — `⌘⌘` — and the first version of this
/// type took that literally: two caps, drawn side by side, lit one after the other. The timing was
/// right and the picture was wrong, because **a Mac has two Command keys**. Two ⌘ caps lighting in
/// turn is a perfectly good drawing of "press the left one, then the right one", which is not the
/// gesture and is not something `ModifierDoubleTap` can ever see — it watches the `.command` mask go
/// down, up and down again, and holding one Command while adding the other produces no such
/// transition at all. It was reported exactly that way: *"expressing both the command keys one by
/// one. It's supposed to be both the command keys together."*
///
/// Neither reading of that report is the fix *for a double tap*. Lighting both caps together would
/// teach the gesture the detector genuinely cannot see; keeping two caps at all leaves "which two
/// keys?" on the card. So the *count of caps* is what changes: `keys` now carries the caps that are
/// actually **drawn**, which for a repeated tap is one, and `taps` carries how many times it is
/// struck. One ⌘, hit twice, is the whole gesture and there is no second key left to read into it.
struct TutorialChordCycle: Equatable {
    /// The modifier glyphs `SettingsShortcutChord.displayString` can put in front of a key. Listed
    /// here rather than shared with that type because this is a question about *rendering* a string
    /// somebody may have rebound, not about the chord model.
    static let modifierGlyphs: Set<Character> = ["⌘", "⌥", "⌃", "⇧"]

    /// How long one beat of the demonstration lasts. Slower than a real double tap — a real one is
    /// under 400 ms for both presses — because this is being read rather than performed, and the two
    /// taps have to be legible as two.
    static let beat: Double = 0.28

    /// Beats the completed chord stays down. This is the moment the shortcut fires, so it is the
    /// only part of the loop that holds still long enough to look at.
    static let holdBeats = 2

    /// Beats with everything back up before it starts again. Without this the loop reads as one
    /// continuous stutter rather than as a gesture with a beginning.
    static let restBeats = 2

    /// The caps that are **drawn**, one each, in the order they are typed.
    ///
    /// For a repeated tap the duplicate is collapsed away, so `⌘⌘` is `["⌘"]` and `⌘⌘⇧` — the search
    /// default, a double tap of ⌘ with Shift held across both halves — is `["⌘", "⇧"]`. Index 0 is
    /// then the key being struck and everything after it is held throughout.
    let keys: [String]

    /// How many times `keys.first` is struck: 2 for a double tap, 1 for an ordinary chord.
    let taps: Int

    init(chord: String) {
        var caps: [String] = []
        var rest = Substring(chord)
        while let first = rest.first, Self.modifierGlyphs.contains(first) {
            caps.append(String(first))
            rest = rest.dropFirst()
        }
        if !rest.isEmpty { caps.append(String(rest)) }

        // Two identical leading caps is the one thing a repeated tap can look like in a display
        // string, and the second of them is not a second key — see the type's note on why drawing it
        // as one was read as "both the command keys".
        if caps.count >= 2, caps[0] == caps[1] {
            caps.remove(at: 1)
            self.keys = caps
            self.taps = 2
        } else {
            self.keys = caps
            self.taps = 1
        }
    }

    /// Whether this chord is the *same key struck twice* rather than a set of keys held together.
    var isRepeatedTap: Bool { taps > 1 }

    /// The length of one loop, in beats. Never zero: a chord this app could not parse still has to
    /// divide by something.
    var beats: Int {
        // A repeated tap is three beats of movement whatever else is in the chord — down, up, down —
        // because the caps after the first one are modifiers held across both taps rather than
        // presses of their own.
        let movement = isRepeatedTap ? 3 : max(1, keys.count)
        return movement + Self.holdBeats + Self.restBeats
    }

    /// Whether the cap at `index` is down on `tick`, which repeats every `beats`.
    ///
    /// Total for both shapes rather than an optional "the one that is down": a chord is a *set* of
    /// keys held together, and a function that could only answer with one of them could not express
    /// the thing being taught.
    func isDown(_ index: Int, at tick: Int) -> Bool {
        guard keys.indices.contains(index) else { return false }
        let beat = ((tick % beats) + beats) % beats
        guard isRepeatedTap else {
            // Held together: each cap goes down in turn and none of them lifts until the whole chord
            // has fired and the hold is over.
            if beat < keys.count { return index < beat + 1 }
            return beat < keys.count + Self.holdBeats && index < keys.count
        }
        // The tapped cap is index 0 and lifts between the two strikes; anything after it is a
        // modifier held across both of them, which is why it never has a gap.
        let isHeldThroughout = index > 0
        switch beat {
        case 0, 2..<(3 + Self.holdBeats): return index == 0 || isHeldThroughout
        case 1: return isHeldThroughout
        default: return false
        }
    }

    /// The gesture said out loud, for the one label a screen reader gets.
    ///
    /// Spoken rather than spelled, because the drawing is the thing being described and "⌘ ⌘" read
    /// aloud has exactly the ambiguity this type exists to remove.
    var spoken: String {
        guard let struck = keys.first else { return "" }
        guard isRepeatedTap else { return "Press \(keys.joined(separator: " "))" }
        let held = keys.dropFirst()
        guard !held.isEmpty else { return "Tap \(struck) twice" }
        return "Tap \(struck) twice while holding \(held.joined(separator: " "))"
    }
}

/// The chord, on a small board, typing itself.
///
/// The board is there because two floating keycaps read as two badges; keys sit on something. It is
/// the app's own wash rather than a drawn keyboard — a photorealistic keyboard would be a picture of
/// *a* keyboard, and the point of the beat is the two keys on the user's own.
struct TutorialChordDemo: View {
    let chord: String

    /// Which beat of the loop is showing. A counter driven by a sleep loop rather than by a
    /// `repeatForever` animation, because the press is a *sequence of discrete states* and an
    /// interpolated `Bool` is not something SwiftUI can give us. The `.animation(_:value:)` below is
    /// what makes each of those states arrive as a press rather than as a jump.
    @State private var tick = 0

    private var cycle: TutorialChordCycle { TutorialChordCycle(chord: chord) }

    var body: some View {
        HStack(spacing: 5) {
            ForEach(cycle.keys.indices, id: \.self) { index in
                TutorialKeycap(label: cycle.keys[index], isDown: isDown(index))
            }
            // The count, in words, beside the one cap it belongs to. A second keycap said "there is
            // another key here" — see `TutorialChordCycle` — and a badge on the cap itself would be
            // read as part of the key's legend. This is the only thing on the board that is not a
            // key, so it is set in secondary ink rather than on a cap.
            if cycle.isRepeatedTap {
                Text("twice")
                    .font(.system(size: 11, weight: .medium, design: .rounded))
                    .foregroundStyle(Ink.secondary)
                    .padding(.trailing, 2)
            }
        }
        .padding(.horizontal, 6)
        .padding(.vertical, 5)
        .background(
            RoundedRectangle(cornerRadius: 10, style: .continuous)
                .fill(Ink.wash)
                .overlay(
                    RoundedRectangle(cornerRadius: 10, style: .continuous)
                        .strokeBorder(Ink.hairline, lineWidth: 1))
        )
        .animation(InkReduceMotion.animation(.easeOut(duration: InkMotion.press)), value: tick)
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(Text(cycle.spoken))
        // `.task` rather than a `Timer` publisher: it is tied to this view's lifetime, so it is
        // cancelled the instant the card stops rendering the demonstration — which is the instant
        // the user presses the chord for real — and, unlike a publisher built in `init`, it does not
        // restart every time the model republishes and the card is re-evaluated.
        .task {
            guard !InkReduceMotion.isEnabled else { return }
            while !Task.isCancelled {
                try? await Task.sleep(for: .seconds(TutorialChordCycle.beat))
                guard !Task.isCancelled else { return }
                tick &+= 1
            }
        }
    }

    /// Under Reduce Motion every cap is at rest. A repeating press is precisely the kind of movement
    /// that setting exists to stop, and the card still says which keys to press.
    private func isDown(_ index: Int) -> Bool {
        guard !InkReduceMotion.isEnabled else { return false }
        return cycle.isDown(index, at: tick)
    }
}

/// One key, up or down.
///
/// Pressed is four things at once, because one of them alone reads as a highlight rather than as a
/// press: the cap fills with the accent, its label inverts, it travels a point and a half *down* into
/// the board, and it takes a soft accent glow with it. Never purple — the accent is `Ink.accent`,
/// which is a named system blue this app picks (`INV-UI-1`).
///
/// Two sizing models, because the two boards this cap appears on measure it differently. A chord
/// chip hugs its legend, so a rebind to `Space` widens the cap rather than clipping the word. A
/// keyboard row is laid out from `TutorialCommandRow`'s numbers, because the tie underneath it has
/// to land on cap centres the drawing agrees with. `width`/`height` nil is the first; set is the
/// second.
struct TutorialKeycap: View {
    let label: String
    let isDown: Bool
    var width: CGFloat? = nil
    var height: CGFloat? = nil

    private var isMeasured: Bool { width != nil || height != nil }

    var body: some View {
        Text(label)
            .font(.system(size: 13, weight: .semibold, design: .rounded))
            .foregroundStyle(isDown ? Ink.glow : Ink.primary)
            .frame(minWidth: isMeasured ? nil : 18)
            .padding(.horizontal, isMeasured ? 0 : 8)
            .padding(.vertical, isMeasured ? 0 : 4)
            // Before the background and not after it, so a measured cap's *ground* is the size the
            // row asked for. Applied outside, the fill would keep hugging the legend and the row
            // would be a line of differently sized keys with correct gaps between them.
            .frame(width: width, height: height)
            .background(
                RoundedRectangle(cornerRadius: 7, style: .continuous)
                    .fill(isDown ? Ink.accent : Ink.rowFill)
                    .overlay(
                        RoundedRectangle(cornerRadius: 7, style: .continuous)
                            .strokeBorder(isDown ? Ink.accent : Ink.hairline, lineWidth: 1)
                    )
                    .shadow(color: Ink.accent.opacity(isDown ? 0.45 : 0), radius: isDown ? 7 : 0)
            )
            .offset(y: isDown ? 1.5 : 0)
            .scaleEffect(isDown ? 0.96 : 1)
    }
}

// MARK: - Both Command keys, being pressed together

/// The tie drawn under the two Command caps while they are down.
///
/// A bracket rather than a straight line: a rule under two keys reads as an underline of everything
/// between them, space bar included, and the thing being said is that the *ends* belong together. It
/// drops off the bottom of each cap, runs across, and comes back up — which is the shape a hand
/// makes reaching for both at once, and the shape a musician reads as "one gesture".
struct TutorialCommandTie: Shape {
    /// The two cap centres, in the same coordinates the row is laid out in.
    let from: CGFloat
    let to: CGFloat

    func path(in rect: CGRect) -> Path {
        let radius = min(4, max(0, (to - from) / 2))
        let underside = rect.maxY - 1
        var path = Path()
        path.move(to: CGPoint(x: from, y: rect.minY))
        path.addLine(to: CGPoint(x: from, y: underside - radius))
        path.addQuadCurve(
            to: CGPoint(x: from + radius, y: underside), control: CGPoint(x: from, y: underside))
        path.addLine(to: CGPoint(x: to - radius, y: underside))
        path.addQuadCurve(
            to: CGPoint(x: to, y: underside - radius), control: CGPoint(x: to, y: underside))
        path.addLine(to: CGPoint(x: to, y: rect.minY))
        return path
    }
}

/// The bottom row of the keyboard, with both Command keys going down at the same instant.
///
/// The one thing this drawing must never do is show one ⌘ before the other, which is what the
/// picture it replaces did and what got it reported. Simultaneity is not a matter of two animations
/// happening to line up here: `TutorialCommandPair.Pose` hands the row a single answer for both
/// caps, so there is no state in this view in which they disagree.
struct TutorialCommandPairDemo: View {

    /// Which beat of the loop is showing — the same sleep-loop counter `TutorialChordDemo` uses, and
    /// for the same reason: a press is a discrete state and `.animation(_:value:)` is what turns the
    /// jump between two of them into a press.
    @State private var tick = 0

    private var pose: TutorialCommandPair.Pose {
        TutorialCommandPair.pose(at: tick, reduceMotion: InkReduceMotion.isEnabled)
    }

    var body: some View {
        VStack(spacing: 2) {
            row
            tie
        }
        .padding(.horizontal, 6)
        .padding(.vertical, 5)
        .background(
            RoundedRectangle(cornerRadius: 10, style: .continuous)
                .fill(Ink.wash)
                .overlay(
                    RoundedRectangle(cornerRadius: 10, style: .continuous)
                        .strokeBorder(Ink.hairline, lineWidth: 1))
        )
        .animation(InkReduceMotion.animation(.easeOut(duration: InkMotion.press)), value: tick)
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(Text(TutorialCommandPair.spoken))
        .task {
            guard !InkReduceMotion.isEnabled else { return }
            while !Task.isCancelled {
                try? await Task.sleep(for: .seconds(TutorialCommandPair.beat))
                guard !Task.isCancelled else { return }
                tick &+= 1
            }
        }
    }

    private var row: some View {
        HStack(spacing: TutorialCommandRow.gap) {
            ForEach(TutorialCommandRow.caps.indices, id: \.self) { index in
                let cap = TutorialCommandRow.caps[index]
                TutorialKeycap(
                    label: cap.label,
                    isDown: cap.isCommand && pose.bothAreDown,
                    width: cap.width,
                    height: TutorialCommandRow.height
                )
                .opacity(cap.isCommand ? 1 : TutorialCommandRow.contextOpacity)
            }
        }
        .frame(width: TutorialCommandRow.width)
    }

    /// The tie, grown from its own middle outward.
    ///
    /// `trim` centred on 0.5 rather than run from 0: a stroke that draws itself from the left cap to
    /// the right one is a picture of one key reaching for the other, which is the very reading — one
    /// then the other — this whole beat exists to stop. Growing outward reaches both ends at the
    /// same moment.
    private var tie: some View {
        TutorialCommandTie(
            from: TutorialCommandRow.centre(of: TutorialCommandRow.leftCommand),
            to: TutorialCommandRow.centre(of: TutorialCommandRow.rightCommand)
        )
        .trim(from: CGFloat(0.5 - pose.tie / 2), to: CGFloat(0.5 + pose.tie / 2))
        .stroke(Ink.accent, style: StrokeStyle(lineWidth: 1.5, lineCap: .round, lineJoin: .round))
        .frame(width: TutorialCommandRow.width, height: TutorialCommandRow.tieDrop)
    }
}

// MARK: - The gesture, being made

/// Where the fingers and everything under them sit at a point in the sweep.
///
/// `phase` runs −1 → +1 and back, which is why the loop demonstrates travel in **both** directions:
/// which way is "back" through the day depends on the user's own natural-scrolling setting, this app
/// does not get to read that off them, and the gate accepts either — so a picture committing to one
/// direction would disagree with the behaviour for half of everybody.
///
/// The one relationship worth stating as code is `content`: the panels move **with** the fingers, by
/// exactly as much. That is what direct manipulation is, and a demonstration that showed the content
/// travelling the other way would be teaching an inverted drag to a user who has never made this
/// gesture before.
enum TutorialScrollCycle {
    /// How far the fingers travel from the centre, each way.
    static let travel: CGFloat = 26

    /// One sweep, in seconds. Slow enough to follow with your eyes, which is slower than anyone
    /// actually scrolls.
    static let sweep: Double = 2.1

    static func hand(_ phase: CGFloat) -> CGFloat { phase * travel }

    /// The panels under the hand. Identical to the hand's travel on purpose — see the type's note.
    static func content(_ phase: CGFloat) -> CGFloat { hand(phase) }

    /// The hour ticks behind the panels, which travel less so the strip reads as having depth rather
    /// than as one flat sheet sliding.
    static func backdrop(_ phase: CGFloat) -> CGFloat { hand(phase) * 0.42 }

    // MARK: The trackpad

    /// The glass, at a size that reads as a trackpad and still leaves a card's worth of room for the
    /// strip beside it. Roughly the 1.6:1 of every MacBook trackpad since 2015 — get the proportion
    /// wrong and the rectangle reads as a window, which is the one other thing it could be mistaken
    /// for.
    static let trackpadWidth: CGFloat = 112
    static let trackpadHeight: CGFloat = 68

    /// One fingertip's contact patch. Taller than wide, because a fingertip pressed on glass is.
    static let padWidth: CGFloat = 13
    static let padHeight: CGFloat = 15

    /// Between the two contact patches, centre to centre. An index and a middle finger resting on a
    /// trackpad sit about 20 mm apart; at this drawing's scale that is this.
    static let padSpread: CGFloat = 18

    /// A finger, tip to where it leaves the drawing. Longer than the pad is tall on purpose: it has
    /// to run off the near edge, because a finger that ends inside the rectangle is a stub and a
    /// stub is what makes two of them read as two floating dots.
    static let fingerLength: CGFloat = 54

    /// How far down from the trackpad's *far* edge the fingertips rest.
    ///
    /// Measured from the far edge rather than from the centre because that is the edge the reader
    /// uses to size the pad, and because the fingers must come from the **near** side — the one the
    /// hand is on. A trackpad drawn with fingers entering from the top is a picture of somebody
    /// else's hands reaching over the machine.
    static let padDrop: CGFloat = 24

    /// What to offset a finger by so its *tip* lands at `padDrop`.
    ///
    /// A finger is laid out as a box `fingerLength` tall with the tip at its top, and SwiftUI centres
    /// that box in the pad — which puts the tip half a finger *above* the far edge, outside the clip,
    /// and draws nothing at all. This is the correction, and it is arithmetic rather than a nudge so
    /// that changing either measurement above keeps the tip where it is supposed to be.
    static var fingerOffset: CGFloat { padDrop - trackpadHeight / 2 + fingerLength / 2 }

    /// Up to this distance from the middle of the sweep the fingers are fully planted.
    static let plantedBelow: CGFloat = 0.72

    /// At and beyond this distance they are clear of the glass.
    ///
    /// Both thresholds sit near the ends deliberately. The sweep is eased, so the fingers have all
    /// but stopped by the time they lift — which is what keeps `content(_:)` honestly equal to
    /// `hand(_:)` while still showing a lift: the travel that happens during the lift is under three
    /// points and is not something a viewer can see the panels doing on their own.
    static let liftedAbove: CGFloat = 0.94

    /// How firmly the two fingertips are on the glass at `phase`: 1 planted, 0 clear of it.
    static func contact(_ phase: CGFloat) -> Double {
        let distance = min(abs(phase), 1)
        guard distance > plantedBelow else { return 1 }
        guard distance < liftedAbove else { return 0 }
        return Double(1 - (distance - plantedBelow) / (liftedAbove - plantedBelow))
    }
}

/// Everything the drag demonstration draws, at one moment, including under Reduce Motion.
///
/// A pose rather than four calls in the view, because Reduce Motion changes *what the picture is*
/// and not merely how fast it gets there. A parked sweep is a pair of fingers sitting on a trackpad,
/// which is a picture of resting a hand — the exact opposite of the instruction. So the still frame
/// grows something the moving one does not need: a double-headed arrow across the pad, saying in a
/// glyph the thing the motion was saying in motion. That substitution is a claim, and a claim
/// belongs somewhere a headless test can read it.
struct TutorialSweepPose: Equatable {
    /// Where the two fingertips are, relative to the middle of the trackpad.
    let fingers: CGFloat
    /// Where the panels are. Equal to `fingers`, always — see `TutorialScrollCycle`.
    let content: CGFloat
    /// Where the hour ticks are: the same direction, less far.
    let backdrop: CGFloat
    /// 1 planted on the glass, 0 lifted clear of it.
    let contact: Double
    /// Whether the still picture has to say "both ways" in a glyph, because nothing is moving.
    let showsTravelArrow: Bool

    init(phase: CGFloat, reduceMotion: Bool) {
        let pose: CGFloat = reduceMotion ? 0 : phase
        self.fingers = TutorialScrollCycle.hand(pose)
        self.content = TutorialScrollCycle.content(pose)
        self.backdrop = TutorialScrollCycle.backdrop(pose)
        // Planted, when nothing moves. A still frame of a half-lifted finger is a smudge.
        self.contact = reduceMotion ? 1 : TutorialScrollCycle.contact(pose)
        self.showsTravelArrow = reduceMotion
    }
}

/// Two fingers sweeping across a trackpad, with a strip of the timeline travelling under them.
///
/// Replaces a single `hand.draw.fill` glyph sliding over that strip. That picture had the direction
/// argument right and the *count* wrong: the card's words asked for two fingers and the drawing
/// showed one undifferentiated hand on no particular surface, which was reported as not making it
/// clear that this is a trackpad gesture at all. Four things now carry that, and no one of them
/// would on its own:
///
/// 1. **The trackpad**, drawn at a trackpad's proportion with a trackpad's corner — not a window.
/// 2. **Two fingers**, entering from the near edge, splayed the way an index and a middle finger
///    are, running off the bottom of the pad rather than floating on it as two disembodied dots.
/// 3. **Two contact patches** that darken and settle as they plant and fade as they come off, which
///    is the difference between a swipe and a hover.
/// 4. **The strip beside it moving with them**, left to right in the reading order of cause and
///    effect, so the gesture and its consequence are one picture rather than two.
///
/// What is deliberately *not* drawn is a click. No tap, no press ripple, no button: the timeline
/// does not want one, and a trackpad diagram that flashed would teach one.
struct TutorialScrollDemo: View {
    /// −1 at one end of the sweep, +1 at the other. One value drives the fingers, the panels and the
    /// ticks, so "the panels move because the fingers did" is true by construction rather than by
    /// three animations happening to agree.
    @State private var phase: CGFloat = -1

    private var pose: TutorialSweepPose {
        TutorialSweepPose(phase: phase, reduceMotion: InkReduceMotion.isEnabled)
    }

    var body: some View {
        HStack(spacing: 12) {
            trackpad
            strip
        }
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(Text("Swipe two fingers across the trackpad"))
        .onAppear {
            guard !InkReduceMotion.isEnabled else { return }
            withAnimation(.easeInOut(duration: TutorialScrollCycle.sweep).repeatForever()) {
                phase = 1
            }
        }
    }

    // MARK: The trackpad

    private var trackpad: some View {
        ZStack {
            RoundedRectangle(cornerRadius: 9, style: .continuous)
                .fill(Ink.wash)

            // Only when nothing moves — see `TutorialSweepPose`. Set above the fingertips, on the far
            // half of the pad, because the fingers occupy everything below them.
            if pose.showsTravelArrow {
                Image(systemName: "arrow.left.and.right")
                    .font(.system(size: 11, weight: .semibold))
                    .foregroundStyle(Ink.secondary)
                    .offset(y: -TutorialScrollCycle.trackpadHeight * 0.32)
            }

            fingers
        }
        .frame(
            width: TutorialScrollCycle.trackpadWidth, height: TutorialScrollCycle.trackpadHeight
        )
        // Clipped, so the fingers run *off* the near edge instead of ending in mid-air. A finger
        // that stops inside the rectangle is a stub; one that leaves it belongs to a hand.
        .clipShape(RoundedRectangle(cornerRadius: 9, style: .continuous))
        .overlay(
            RoundedRectangle(cornerRadius: 9, style: .continuous)
                .strokeBorder(Ink.hairline, lineWidth: 1))
    }

    private var fingers: some View {
        ZStack {
            finger(side: -1)
            finger(side: 1)
        }
        .offset(x: pose.fingers, y: TutorialScrollCycle.fingerOffset)
    }

    /// One finger, anchored at its tip.
    ///
    /// Everything about this shape is measured from the contact patch and not from the finger's
    /// body, because the patch is the part that has to be in the right place: it is what the sweep
    /// moves, what the strip follows, and what a viewer is actually reading. The body is set behind
    /// it, rotated about the tip so the two fingers splay apart the way a hand's do without their
    /// tips wandering off the line they are travelling along.
    private func finger(side: CGFloat) -> some View {
        ZStack(alignment: .top) {
            // The finger, fading out as it leaves the pad so the clip is a horizon rather than a
            // cut. Its ink is tied to `contact`, so a lifted finger is a lighter one — which is what
            // "off the glass" looks like from directly above, where nothing can move upward.
            Capsule(style: .continuous)
                .fill(
                    LinearGradient(
                        colors: [
                            Ink.primary.opacity(0.19 * (0.5 + 0.5 * pose.contact)),
                            Ink.primary.opacity(0.02),
                        ],
                        startPoint: .top,
                        endPoint: .bottom)
                )
                .frame(
                    width: TutorialScrollCycle.padWidth + 3,
                    height: TutorialScrollCycle.fingerLength)

            // The contact patch. Darkens, spreads a little and takes a soft shadow as it plants —
            // the same four-things-at-once rule the keycap presses by, for the same reason: one of
            // them alone reads as a highlight.
            Ellipse()
                .fill(Ink.primary.opacity(0.20 + 0.40 * pose.contact))
                .frame(
                    width: TutorialScrollCycle.padWidth,
                    height: TutorialScrollCycle.padHeight * CGFloat(0.88 + 0.12 * pose.contact)
                )
                .shadow(color: Ink.primary.opacity(0.26 * pose.contact), radius: 3, y: 1)
                .offset(y: 1.5)
        }
        // Positive degrees swings the body left of the tip, so the sign is flipped to splay each
        // finger away from the other.
        .rotationEffect(.degrees(Double(-side * 8)), anchor: .top)
        .scaleEffect(CGFloat(1 + 0.06 * (1 - pose.contact)), anchor: .top)
        .offset(x: side * TutorialScrollCycle.padSpread / 2)
    }

    // MARK: The strip

    private var strip: some View {
        ZStack {
            RoundedRectangle(cornerRadius: 8, style: .continuous)
                .fill(Ink.wash)

            ticks.offset(x: pose.backdrop)
            panels.offset(x: pose.content)
        }
        .frame(height: 56)
        // Clipped, so the panels travel *through* the strip rather than sliding out over the card's
        // own copy — which is what makes it read as a window onto a longer day.
        .clipShape(RoundedRectangle(cornerRadius: 8, style: .continuous))
        .overlay(
            RoundedRectangle(cornerRadius: 8, style: .continuous)
                .strokeBorder(Ink.hairline, lineWidth: 1))
    }

    /// The hour marks. Deliberately featureless: this is a diagram of a gesture, and anything here
    /// that looked like captured content would be a picture of somebody's screen that never existed.
    private var ticks: some View {
        HStack(spacing: 13) {
            ForEach(0..<17, id: \.self) { index in
                Capsule()
                    .fill(Ink.hairline)
                    .frame(width: 1, height: index.isMultiple(of: 3) ? 14 : 8)
            }
        }
    }

    /// Five panes of what the timeline holds, the middle one accented as the moment you are on.
    ///
    /// The accent's alpha is 0.85 and is not a free choice: it is the value `InkAccentTests` has
    /// measured this hint's composited hue against, and moving it moves the number that test compares
    /// to the token.
    private var panels: some View {
        HStack(spacing: 7) {
            ForEach(0..<5, id: \.self) { index in
                let isNow = index == 2
                RoundedRectangle(cornerRadius: 4, style: .continuous)
                    .fill(isNow ? Ink.accent.opacity(0.85) : Ink.rowFillHover)
                    .frame(width: isNow ? 34 : 26, height: isNow ? 28 : 21)
            }
        }
    }
}
