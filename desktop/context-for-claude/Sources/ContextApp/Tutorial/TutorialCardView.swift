import AppKit
import SwiftUI

/// The tutorial's card: one surface, whatever the step.
///
/// Every card is the same three things in the same order — **the mark saying one line**, whatever
/// that line needs the user to touch, and the controls. Nothing else. The words are not written here:
/// they come from `TutorialModel.speech`, which is where a claim can be tested, and this file only
/// decides how they are delivered.
///
/// Two things are deliberately absent, and both were here before:
///
/// - **A step counter.** A number that says how much of this is left is a number people read as a
///   reason to leave. The user is told what to do next and nothing about the length of the queue.
/// - **A frame readout.** The capture beat used to show five dots filling and "3 of 5 frames", which
///   is this app's plumbing narrated at someone who has been using it for ninety seconds. The gate is
///   unchanged — the step still cannot be left until the frames are genuinely in the store — but the
///   card says "Scroll through it for a bit" and then "Got it", which is the same fact in a human's
///   words. Nothing here is on a timer; see `TutorialModel.outcome`.
///
/// The two beats that ask for a *physical action* draw it rather than describe it: the chord types
/// itself and the gesture is made by a hand. Both live in `TutorialDemonstrations.swift`, both are
/// rendered only while their step is still waiting, and neither can move the flow along.
///
/// Every colour is an `Ink` token — a named system colour or an alpha on one — so it reads correctly
/// in both appearances and carries no borrowed brand. Nothing here is purple, and nothing here reads
/// a hue off the machine, which is the only way that can be true on every machine (`INV-UI-1`).
struct TutorialCardView: View {
    @ObservedObject var model: TutorialModel
    @ObservedObject var chrome: TutorialOverlayChrome

    /// The air either side of everything on the card. A constant rather than a literal in the
    /// modifier, because the results grid has to lay itself out inside what is left of the card's
    /// width and a second copy of this number is a grid that overflows the day somebody moves one.
    static let horizontalPadding: CGFloat = 22

    /// The card's outer width. A coach mark with an arrow is drawn a little narrower so the arrow has
    /// room to sit outside the panel without leaving the window.
    private var cardWidth: CGFloat {
        TutorialOverlay.width - (chrome.arrow == nil ? 0 : 18)
    }

    /// Fixed, and the same for every step: the window is sized from this card's ideal height at this
    /// width (`TutorialOverlay.fittingHeight()`), so the width must not depend on anything the window
    /// does.
    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            // The mark says the card's own words — the same component and the same call-site shape
            // onboarding uses, because it is the same character and this is the screen straight
            // after those.
            TalkingMark(
                lead: model.speech.runs,
                leadStyle: InkType.stepHeadline,
                aside: model.speech.aside)

            extras
            footer
        }
        .padding(.horizontal, Self.horizontalPadding)
        .padding(.vertical, 20)
        .frame(width: cardWidth, alignment: .leading)
        .fixedSize(horizontal: false, vertical: true)
        // The app's shared glass, not a fill of its own: a coach mark floats over the desktop beside
        // the very windows it points at, and it has to be made of the same thing they are.
        //
        // **`InkGlassSurface` and not `.inkGlassPanel()`, because the modifier draws the specular top
        // edge outside its own clip.**
        //
        // The modifier assembles the panel in SwiftUI — an `InkGlassBackdrop` and the scrim in a
        // `ZStack`, cut with `.clipShape` — and then hangs the sheen on as an `.overlay` *after* that
        // cut. The material and the scrim come out rounded (the clip really does become a
        // `masksToBounds` layer at 22 pt continuous — checked by walking the hosted tree, not
        // assumed); the sheen does not. It is a 1 pt white line at 50%, laid across the card's full
        // width at its very top — and the top corners are exactly where the panel is curving away
        // from it, so the line carries straight on past both of them into transparent space and
        // squares the card off.
        //
        // Which is why one look at this card produced two complaints: "above it, there's a weird line
        // showing up", and "I can see like weird like boxy edges and it's not completely rounded".
        // One defect; the second is what the first looks like from a step back.
        //
        // `InkGlassSurface` is the app's real `InkGlassView`, where the sheen is a *subview of the
        // panel* and is therefore cut by the same corner as everything else on it — the highlight
        // stops where the glass does, which is what makes it read as light caught on a face rather
        // than as a hairline drawn over one. Two things the modifier also carried do not come with it
        // and are therefore stated here: the ambient shadow, and the light appearance that makes
        // `Ink`'s dynamic colours resolve dark on the panel.
        //
        // The modifier itself still has the defect and `SearchSurface` still wears it. Fixing it
        // there is moving one `.overlay` inside the `.clipShape` in `InkGlass.swift`.
        .environment(\.colorScheme, .light)
        .background {
            InkGlassSurface()
                .shadow(
                    color: .black.opacity(Double(InkGlassShadow.ambient.opacity)),
                    // SwiftUI's blur radius is half Core Animation's for the same visual spread.
                    radius: InkGlassShadow.ambient.radius / 2,
                    y: -InkGlassShadow.ambient.offsetY)
        }
        .overlay(alignment: .top) { arrow(.top) }
        .overlay(alignment: .bottom) { arrow(.bottom) }
        .padding(chrome.arrow == nil ? 0 : 9)
        .animation(InkReduceMotion.animation(.easeOut(duration: InkMotion.settle)), value: model.step)
    }

    /// The pointer, drawn only on the edge the placement asked for and offset to track the target.
    ///
    /// The same glass as the card, clipped to the triangle rather than filled with a flat colour: a
    /// solid tab on a translucent card is visible as a tab on every wallpaper that is not the one it
    /// was picked against.
    @ViewBuilder
    private func arrow(_ edge: TutorialArrow.Edge) -> some View {
        if let arrow = chrome.arrow, arrow.edge == edge {
            InkGlassSurface(cornerRadius: 0)
                .clipShape(TutorialArrowShape(pointsUp: edge == .top))
                .frame(width: 20, height: 10)
                .offset(x: arrow.offset, y: edge == .top ? -9 : 9)
        }
    }

    // MARK: - What the step needs the user to touch

    /// Only the steps that ask for something have anything here. A card whose whole content is one
    /// spoken line and a button is the shape most of them want.
    @ViewBuilder
    private var extras: some View {
        switch model.step {
        case .screenAccess where !model.screenIsGranted:
            HStack(spacing: 10) {
                InkButton(model.isRequestingScreenAccess ? "Waiting…" : "Allow") {
                    model.requestScreenAccess()
                }
                .disabled(model.isRequestingScreenAccess)
                // Only after the ask, and only as a button. The model no longer opens the pane on
                // the user's behalf — `Permissions.request(.screen)` already does when there is one
                // to open, and doing it twice opened two windows on one press.
                if model.didAskForScreenAccess {
                    InkButton("Open Settings", kind: .secondary) { model.openScreenSettings() }
                } else {
                    // Only before the ask. Afterwards the mark's own line says it, and three things
                    // on this row wrapped the sentence under the buttons.
                    Text("I will notice the moment you do.")
                        .inkStyle(InkType.statusLabel, color: Ink.secondary)
                        .fixedSize(horizontal: false, vertical: true)
                }
            }

        // Only while something could still arrive. A spinner over "nothing will arrive until Screen
        // Recording is on" would be the card miming work it knows is not happening.
        case .collectFrames where model.outcome == .waiting:
            listening

        // The chord, typing itself. Shown only when it is genuinely registered: a tutorial that
        // taught keys this machine does not listen for would be teaching a surface that is not
        // there, and this beat cannot be earned on such a machine at all.
        //
        // It moves because the app's own default chord is a *double tap* of ⌘, and a still picture
        // of two ⌘ symbols side by side says the opposite of that. Drawing the tap as two caps did
        // too: a Mac has two Command keys, so two ⌘ caps lighting in turn was read — and reported —
        // as "both the command keys, one by one". One cap, struck twice. See `TutorialChordCycle`.
        case .openTimeline where model.timelineChordIsArmed:
            HStack(spacing: 10) {
                TutorialChordDemo(chord: model.timelineChord)
                Text("opens it from anywhere.")
                    .inkStyle(InkType.statusLabel, color: Ink.secondary)
                    .fixedSize(horizontal: false, vertical: true)
            }

        // The gesture, being made, and only until they have made it. Leaving a loop running under
        // "there you go" would be the card still asking for something it has already been given —
        // which is also what stops it: this branch is the only thing rendering it.
        case .timeline where model.timelineIsOpen && !model.didDrag:
            TutorialScrollDemo()

        case .claudeHandoff:
            VStack(alignment: .leading, spacing: 12) {
                Text("“\(TutorialModel.suggestedQuestion)”")
                    .inkStyle(InkType.rowCopy, color: Ink.primary)
                    .fixedSize(horizontal: false, vertical: true)
                if model.isAskingClaude {
                    listening
                } else if model.claudeAsk == nil, model.claudeNeedsRestart {
                    // The consent row, and the only place anything in this app offers to quit
                    // another one. Both choices are real: declining still hands the question over,
                    // to the Claude they already have, and the card then says the reach may be
                    // stale rather than quietly taking their session to force a gate.
                    HStack(spacing: 10) {
                        InkButton("Restart it and ask") { model.askClaude(restartingFirst: true) }
                        InkButton("Keep it open", kind: .secondary) {
                            model.askClaude(restartingFirst: false)
                        }
                    }
                } else if model.claudeAsk != nil {
                    // A retry rather than the old "Restart Claude": the handoff has already run, and
                    // the only thing left worth offering is doing it again if it did not land.
                    InkButton("Ask Claude again", kind: .secondary) { model.askClaude() }
                }
            }

        case .query:
            query

        case .claudeProof where model.proof == nil:
            listening

        default:
            EmptyView()
        }
    }

    /// The one thing the card shows while it is waiting on something real: that it is awake.
    ///
    /// Indeterminate on purpose. Both waits — frames landing, Claude calling a tool — used to be
    /// narrated with counts and machinery, and neither number ever helped: there is nothing the user
    /// can do with "3 of 5" that they cannot do with "not yet". What it must never become is a bar
    /// that fills on a clock, which would be the one lie this whole flow is built to avoid.
    private var listening: some View {
        ProgressView()
            .controlSize(.small)
            .accessibilityLabel(Text("Waiting"))
    }

    /// The search beat: type, press Return, and the real hits come back into the same card. The mark
    /// changes its line to "There it is" — which it can only do because there was really a hit.
    ///
    /// **The hits come back as a grid of pictures, not as a list of sentences.** Every result here is
    /// a moment that was on somebody's screen and has a frame on disk to prove it, and the first
    /// version of this beat drew all of that as two text rows: a generic document glyph, a run of the
    /// window's accessibility dump, and an MCP-format timestamp. Reported, exactly: *"this after
    /// search after onboarding needs to show results in tabular form with screen if any. This list
    /// with only text looks so bland."* Both halves of that are one defect — a person recognises the
    /// moment they were just in from the *picture* of it, and a column of type gives them nothing to
    /// recognise, so the beat that is supposed to land as "there it is" landed as a database dump.
    ///
    /// **What went with the list is the larger preview that used to hang under it.** Tapping a result
    /// drew the chosen frame again at 140 pt, which was the only picture on the card when the rows
    /// above it were type — and is now a second, larger copy of a card the user can already see, on a
    /// surface that has to stay short enough to float over the timeline it is talking about. It was
    /// kept for one case and that case is what killed it: a spoken line has no picture of its own, so
    /// the preview appeared exactly when the card was least able to afford 150 pt, and the render
    /// showed it pushing the mark's own line off the top of the display. What answers "tap it to go
    /// back to that moment" is not a thumbnail on this card at all — it is the timeline underneath,
    /// which `choose` has genuinely scrubbed to that instant.
    @ViewBuilder
    private var query: some View {
        VStack(alignment: .leading, spacing: 10) {
            if model.results.isEmpty {
                TutorialQueryField(model: model)
                if let message = model.searchMessage {
                    Text(message)
                        .inkStyle(InkType.statusLabel, color: Ink.errorRed)
                        .fixedSize(horizontal: false, vertical: true)
                }
            } else {
                TutorialResultsGrid(
                    model: model,
                    contentWidth: cardWidth - Self.horizontalPadding * 2)
            }
        }
    }

    // MARK: - Footer

    /// The waiver sits on its own row above the controls rather than inside them. Its label is a whole
    /// sentence — it has to be, because it is the one control that says what did *not* happen — and on
    /// a live walkthrough it squeezed the primary button down to "Con ti…".
    private var footer: some View {
        VStack(alignment: .leading, spacing: 10) {
            if model.waiverIsOffered {
                Button(waiverLabel) { model.waive() }
                    .buttonStyle(.plain)
                    .inkStyle(InkType.statusLabel, color: Ink.secondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
            HStack(spacing: 12) {
                if let title = primaryTitle {
                    InkButton(title) { model.advance() }
                        // One condition, and it is the model's. This used to add "or the handoff is
                        // running" here, which covered the state where Claude had been asked and
                        // left uncovered the state before it — the consent question, whose two
                        // answers are on this very card. `gateIsSatisfied` now holds both
                        // (`TutorialModel.isAwaitingAnAnswer`), so the button and `advance()` cannot
                        // disagree about what this beat is waiting for.
                        .disabled(!model.gateIsSatisfied)
                        .fixedSize()
                }
                Spacer(minLength: 8)
                // Every step is skippable, and skipping tears the whole thing down.
                if model.step != .menuBar {
                    Button("Skip") { model.skip() }
                        .buttonStyle(.plain)
                        .inkStyle(InkType.statusLabel, color: Ink.secondary)
                        .fixedSize()
                }
            }
        }
    }

    /// The primary action's label, or nil for the one step no button can move: the proof beat, which
    /// needs Claude. Everywhere else the button is present and *disabled* until the gate is met, so
    /// the way forward is always visible and never a lie about being ready.
    private var primaryTitle: String? {
        switch model.step {
        case .invitation: return "Start"
        case .screenAccess: return model.screenIsGranted ? "Continue" : nil
        case .collectFrames: return "Continue"
        // No button can move these two: one needs a keypress the tutorial must not fake, the other a
        // gesture it must not mime. Both have a labelled way out that says what did not happen.
        case .openTimeline: return nil
        case .timeline: return model.didDrag ? "Continue" : nil
        case .findMoments, .query, .claudeHandoff: return "Continue"
        case .claudeProof: return model.proof == nil ? nil : "Continue"
        case .allSet: return "Continue"
        case .menuBar: return "Done"
        case .finished, .skipped: return nil
        }
    }

    private var waiverLabel: String {
        switch model.step.gate {
        case .realFrames: return "Nothing is arriving — carry on anyway"
        case .screenRecordingGrant: return "Carry on without it"
        case .realHotkey: return "That shortcut isn't working — open it for me"
        case .realGesture: return "I can't drag it — carry on anyway"
        case .userAction, .realSearchResult, .genuineToolCall: return ""
        }
    }
}

// MARK: - The arrow

struct TutorialArrowShape: Shape {
    let pointsUp: Bool

    func path(in rect: CGRect) -> Path {
        var path = Path()
        if pointsUp {
            path.move(to: CGPoint(x: rect.midX, y: rect.minY))
            path.addLine(to: CGPoint(x: rect.maxX, y: rect.maxY))
            path.addLine(to: CGPoint(x: rect.minX, y: rect.maxY))
        } else {
            path.move(to: CGPoint(x: rect.midX, y: rect.maxY))
            path.addLine(to: CGPoint(x: rect.maxX, y: rect.minY))
            path.addLine(to: CGPoint(x: rect.minX, y: rect.minY))
        }
        path.closeSubpath()
        return path
    }
}

// MARK: - The query field

/// Submits on Return and never pretends: the search it runs is the real one.
struct TutorialQueryField: View {
    @ObservedObject var model: TutorialModel
    @State private var draft = ""
    @FocusState private var isFocused: Bool

    var body: some View {
        HStack(spacing: 8) {
            Image(systemName: "magnifyingglass")
                .font(.system(size: 11, weight: .semibold))
                .foregroundStyle(Ink.secondary)
            // Not "a word you saw". A word is a thing to recall; something you just looked at is a
            // thing you already have — and recall is the one thing this beat must not ask for,
            // because the store only holds the last few minutes and a half-remembered word finds
            // nothing. Reported as: "dont say search a word off the screen, say search something you
            // just looked at."
            TextField("", text: $draft, prompt: Text("something you just looked at"))
                .textFieldStyle(.plain)
                .font(.system(size: 13))
                .foregroundStyle(Ink.primary)
                .focused($isFocused)
                .onSubmit { model.search(draft) }
        }
        .padding(.horizontal, 10)
        .padding(.vertical, 7)
        .background(
            RoundedRectangle(cornerRadius: 8, style: .continuous)
                .fill(Ink.rowFill)
                .overlay(
                    RoundedRectangle(cornerRadius: 8, style: .continuous)
                        .strokeBorder(Ink.hairline, lineWidth: 1)))
        .onAppear { isFocused = true }
    }
}

// MARK: - The results, as a grid of real moments

/// Every number the found-it grid is laid out from.
///
/// Stated here rather than measured off the view for the same reason `SearchLayout` states the search
/// panel's: the card is a **known width**, so the width of one result card is arithmetic, and
/// arithmetic is something a test can hold against the picture it is supposed to produce. An
/// `.adaptive` grid would quietly become one or three across after a padding change and nothing would
/// say so.
enum TutorialResultGrid {

    /// **Two across, and three does not fit.**
    ///
    /// The real search panel is 760 pt wide and puts three cards in it (`SearchLayout.resultColumns`).
    /// This card is 470 — it is a coach mark that floats over the timeline it is talking about, not a
    /// panel — which leaves 426 pt of content. Three across is 133 pt a card, well under
    /// `SearchLayout.minimumCardWidth`, the width that file names as the point where a thumbnail stops
    /// being recognisable as a screen and a title has no room to say anything. Two across is 207,
    /// which is inside the band the real cards live in.
    static let columns = 2

    /// A shade tighter than the panel's `SearchLayout.cardGutter` (14). The same gutter on a card two
    /// thirds the width reads as a wider gap than it is, and the pictures are what should be carrying
    /// the eye across the row.
    static let gutter: CGFloat = 12

    /// One result card's width, from the room the card has left after its own padding.
    static func cardWidth(contentWidth: CGFloat) -> CGFloat {
        max(0, (contentWidth - gutter * CGFloat(columns - 1)) / CGFloat(columns))
    }

    /// Fixed columns at that width. `.topLeading` so a row whose two titles wrap differently still
    /// hangs its pictures off one line.
    static func columnItems(contentWidth: CGFloat) -> [GridItem] {
        Array(
            repeating: GridItem(
                .fixed(cardWidth(contentWidth: contentWidth)), spacing: gutter,
                alignment: .topLeading),
            count: columns)
    }
}

/// The hits, two across, each one a picture of the moment it came from.
struct TutorialResultsGrid: View {
    @ObservedObject var model: TutorialModel
    /// The room inside the card's own horizontal padding.
    let contentWidth: CGFloat

    var body: some View {
        LazyVGrid(
            columns: TutorialResultGrid.columnItems(contentWidth: contentWidth),
            alignment: .leading,
            spacing: TutorialResultGrid.gutter
        ) {
            ForEach(model.results) { memory in
                TutorialResultCard(
                    memory: memory,
                    loader: model.loader,
                    width: TutorialResultGrid.cardWidth(contentWidth: contentWidth),
                    isChosen: model.chosenMemory == memory,
                    action: { model.choose(memory) })
            }
        }
        .frame(width: contentWidth, alignment: .leading)
    }
}

/// One thing the tutorial's search found: the screen it was captured from, a short title, and where
/// and when it happened.
///
/// **This is `SearchResultCard` at this card's width, and the copy is not a preference.** The two are
/// deliberately the same object to look at — same 4:3 well through the same `SearchThumbnail` and the
/// same `FrameLoader`, same `SearchSpokenWell` for a spoken line, same app icon, same
/// `SearchTime.describe` under it — because the beat directly after this one hands the user to the
/// real search panel, and a tutorial that taught a different-looking result is a tutorial teaching a
/// surface that does not exist.
///
/// What could not be reused is the *frame*: `SearchResultCard.content` ends in
/// `.frame(width: SearchLayout.cardWidth())`, which is arithmetic on the 760 pt search panel and
/// comes out at 241 pt. Two of those plus a gutter is 495 pt inside a 426 pt card. The card takes its
/// width as a parameter instead; everything the width does not decide is drawn by the same types the
/// panel draws it with, so there is one place to change the look of a result and it is not this file.
struct TutorialResultCard: View {
    let memory: TutorialMemory
    let loader: FrameLoader
    let width: CGFloat
    /// Whether this is the one the user tapped. The tutorial's own state — the card that was chosen
    /// is the moment the timeline behind has travelled to.
    let isChosen: Bool
    let action: () -> Void

    @State private var isHovering = false

    var body: some View {
        Button(action: action) {
            VStack(alignment: .leading, spacing: 6) {
                well
                Text(memory.title)
                    // One line, always, and `.tail` rather than the default middle truncation: the
                    // front of a window title is the part that says what it is.
                    .inkStyle(InkType.rowCopy, color: Ink.primary)
                    .lineLimit(1)
                    .truncationMode(.tail)
                HStack(spacing: 5) {
                    glyph
                    Text(memory.source)
                        .inkStyle(InkType.statusLabel, color: Ink.secondary)
                        .lineLimit(1)
                        .truncationMode(.tail)
                        .layoutPriority(1)
                    // `.fixedSize`, which the panel's own card does not need and this one does: at
                    // 207 pt a long source and a timestamp fill the row, and a separator that is
                    // allowed to compress is a separator SwiftUI truncates to nothing — leaving two
                    // labels butted together with a space between them. Seen in the render.
                    Text("•").inkStyle(InkType.statusLabel, color: Ink.secondary).fixedSize()
                    // `SearchTime.describe` — "Today, 11:40 AM" — and not `memory.when`, which is
                    // `ContextTime.describe`: the MCP wire format ("Sun 2 Aug 2026 at 11:40 AM"),
                    // deliberately unfriendly because a model reasons better about a full date than
                    // about "today". It was on this card, and it is one of the things that made the
                    // beat read as a database dump.
                    Text(SearchTime.describe(memory.at))
                        .inkStyle(InkType.statusLabel, color: Ink.secondary)
                        .lineLimit(1)
                        .fixedSize()
                }
            }
            .frame(width: width, alignment: .leading)
        }
        .buttonStyle(TutorialResultCardStyle(isHovering: isHovering, isChosen: isChosen))
        .onHover { isHovering = $0 }
        .animation(InkReduceMotion.animation(.easeOut(duration: InkMotion.press)), value: isHovering)
        // The matched text, whole, for the two readers a 207 pt card cannot serve: somebody hovering
        // to check *why* this moment came back, and somebody who cannot see the picture at all.
        .help(memory.text)
        .accessibilityLabel(Text(readAloud))
        .accessibilityHint(Text(Self.activationHint))
        .accessibilityAddTraits(isChosen ? [.isSelected] : [])
    }

    /// What pressing it does, said once. The label is already a sentence about *when* and *where*; the
    /// hint is the only place the card can say that it is a door.
    static let activationHint = "Goes back to this moment in the timeline"

    /// The picture, or the words.
    @ViewBuilder
    private var well: some View {
        if memory.isScreen {
            // `fallbackText` is the honest substitute and only ever drawn when the picture is
            // genuinely gone: retention unlinks files, and a frame can have had no image at all.
            SearchThumbnail(frame: memory.frame, loader: loader, fallbackText: memory.text)
        } else {
            SearchSpokenWell(line: memory.text)
        }
    }

    /// What owned the window, or that this was speech at all.
    @ViewBuilder
    private var glyph: some View {
        if memory.isScreen, let app = memory.app, !app.isEmpty {
            RewindAppIcon(appName: app, bundleId: nil, size: 12)
        } else {
            // A waveform for speech, and the same fallback for a frame that recorded no app:
            // `RewindAppIcon` given an empty name draws a coloured disc with a "?" in it, which is a
            // confident picture of nothing.
            Image(systemName: memory.isScreen ? "rectangle.on.rectangle" : "waveform")
                .font(.system(size: 11, weight: .semibold))
                .foregroundStyle(Ink.secondary)
                .frame(width: 12, height: 12)
                .accessibilityHidden(true)
        }
    }

    /// The card read aloud. The matched words are included for a spoken line because the words *are*
    /// the card, and left out for a screen because the title and source already name it — a page of
    /// accessibility text read out after every card would make the grid unusable with VoiceOver.
    private var readAloud: String {
        let when = SearchTime.describe(memory.at)
        guard memory.isScreen else { return "\(memory.title): \(memory.text), \(when)" }
        return "\(memory.title), \(memory.source), \(when)"
    }
}

/// How a result card answers the pointer: a wash behind it on hover, a stronger one with an edge when
/// it is the one that was tapped, and a dip in opacity while it is held.
///
/// A mirror of `SearchResultsView`'s own `SearchResultCardStyle`, which is `private` to that file. The
/// reasoning it carries is the reasoning this needs, so it is restated rather than reinvented: the
/// affordance is drawn **outside** the card's bounds, because a card is a picture, a title and a
/// source line with no padding of its own — insetting them to make room for a highlight would change
/// the card's height, which the grid's layout and the tests on the card's fitting size are stated in
/// terms of. A `background` is layout-neutral, and the negative padding lets the wash spread into the
/// gutter the grid already leaves.
///
/// Weight and never hue. Selection here used to be a blue ring; a second meaning-bearing colour is one
/// more thing to learn and one more chance to be off-brand (INV-UI-1).
private struct TutorialResultCardStyle: ButtonStyle {
    let isHovering: Bool
    let isChosen: Bool

    /// A shade larger than the card's own corner, because the wash sits outside it: two concentric
    /// rounded rectangles with the *same* radius read as a rendering seam rather than as one object.
    private static let cornerRadius = SearchLayout.cardCornerRadius + 4
    /// How far the wash spreads past the card. Half the grid's gutter, so two chosen neighbours could
    /// never touch.
    private static let outset = TutorialResultGrid.gutter / 2

    func makeBody(configuration: Configuration) -> some View {
        let shape = RoundedRectangle(cornerRadius: Self.cornerRadius, style: .continuous)
        let fill: Color = {
            if isChosen { return SearchInk.chipFillSelected }
            return isHovering || configuration.isPressed ? SearchInk.chipFillHover : .clear
        }()
        return
            configuration.label
            // Pressed drops opacity rather than scaling: a card is a picture of something real, and a
            // photograph that shrinks under the finger reads as a toy.
            .opacity(configuration.isPressed ? 0.72 : 1)
            .background(
                shape
                    .fill(fill)
                    .overlay(shape.strokeBorder(isChosen ? Ink.hairline : Color.clear, lineWidth: 1))
                    .padding(-Self.outset)
            )
            // The whole card is the target, including the air between the picture and the caption — a
            // control with holes in it is a control that ignores half its clicks.
            .contentShape(Rectangle())
            .animation(
                InkReduceMotion.animation(.easeOut(duration: InkMotion.press)),
                value: configuration.isPressed)
    }
}

// `TutorialMomentPreview` and its `ContextTimeLabel` formatter stood here. Both went with the text
// list — see `query` above for why the larger preview is now the card saying the same thing twice,
// and `TutorialResultCard` for the timestamp the grid uses instead (`SearchTime.describe`, the one a
// person reads, rather than a second local formatter). `TutorialModel.chosenMoment` is unaffected and
// still carries the whole claim: it is what the two asides on this beat are chosen between, and what
// the timeline was scrubbed to.
