import AppKit
import ApplicationServices
import SwiftUI

//  The permission choreography: what we may draw, what we may only point at, and the one line
//  between the two that this file exists to hold.
//
//  **macOS draws the affordance, not us.** On macOS 26 the dashed row and the "Drag this row up
//  into the list" arrow inside Privacy & Security are System Settings' own UI. No application can
//  draw inside another application's window, and no application should pretend to: a replica of
//  someone else's control, presented where theirs would be, is a forgery whether or not it was
//  meant as one. So there is exactly one act, and it happens **over System Settings**:
//  `PermissionOverlay` finds the *real* area, the *real* row and the *real* control through the
//  Accessibility API, dashes the row and the slot it has to land in, glows the control, and drags a
//  token of this app along an arrow between them. It draws nothing that belongs to System Settings —
//  everything it draws is plainly ours, sitting outside their controls and pointing at them rather
//  than replacing them.
//
//  **There used to be a second act, on our own card**: `GhostRowReplica`, a small animation of a
//  ghost row rising into a list, behind a "Show me the row" button, so the real affordance was
//  recognised rather than met cold. It is gone, and the reason is worth keeping. A rehearsal of an
//  instruction is still a thing to read and dismiss before the instruction, and it sat in the one
//  place the user was already being asked to read four sentences and press a button. The real
//  overlay is now *automatic* — the pane opening is the trigger — so what the replica was preparing
//  people for arrives at the same moment they would have been reading about it.
//
//  And the rule that governs the whole of it: **a confident arrow aimed at nothing is worse than a
//  sentence.** The lookup fails for ordinary reasons — Accessibility itself is not granted yet, the
//  list is scrolled, the pane relaid out on a macOS we have not seen, the window dragged half off a
//  second display. Every one of those degrades to `PermissionGuidance.instruction`: words, no
//  boundary, no glow, no arrow, nothing aimed anywhere.
//
//  **The Accessibility step cannot be rescued by asking, and the measurement is written down here so
//  nobody spends another afternoon looking.** Measured on macOS 26.5.2 (build 25F84), from a
//  process with `AXIsProcessTrusted() == false`, against a live System Settings sitting on Privacy &
//  Security ▸ Accessibility with our row plainly in the list:
//
//  - `AXUIElementCopyAttributeValue(app, AXWindows)` → `kAXErrorAPIDisabled` (-25211).
//  - `AXUIElementCopyAttributeValue(app, AXRole)` → the same. So does `AXTitle`, and so does
//    `AXFocusedWindow`.
//  - `AXUIElementCopyAttributeNames(app)` → the same. Not one attribute is readable; the tree cannot
//    even be *enumerated*, so "read the list container instead of the row" is not a smaller ask, it
//    is the same forbidden ask.
//  - `AXUIElementCopyElementAtPosition(systemWide, x, y)` → the same. Hit-testing is not a side door.
//  - Asking **System Events** to do the read on our behalf — it is privileged, we are not — fails
//    with the same -25211 and the message *"… is not allowed assistive access"*. The gate is on the
//    sender, not on the reader.
//  - `CGWindowListCopyWindowInfo` lists exactly **one** ordinary System Settings window (723 × 948)
//    and four offscreen 1920 × 30 strips. There is no sub-window whose bounds are the content pane,
//    so the window server cannot narrow the rect either.
//
//  So during the Accessibility step the row is **structurally unreadable through the accessibility
//  API**, and every route through that API is closed by the same check. Inferring where the list
//  "ought to be" from the window rect would be the one thing the paragraph above forbids — a boundary
//  drawn round a rect nobody measured, correct on the machine it was written on and wrong on the
//  first resized window, wider sidebar or unfamiliar macOS. It is not done, and this is why.
//
//  **But "unreadable" was over-read, and that is the bug this file spent a release describing instead
//  of fixing.** Every measurement above is a measurement of one gate. It says nothing about the other
//  one: *this app is a screen recorder with OCR*, and Screen Recording lets us read the pixels of
//  another application's window with no accessibility check anywhere in the path. The row is on
//  screen with its name written on it. `SettingsRowSighting` is the second locator that follows from
//  that — same job, same `SettingsSpotlightTarget` out, no `AXUIElement` in — and the instant it can
//  see the pane, the Accessibility step stops being the one step that could never point at anything.
//  It is a fallback and not a replacement: the walk reads the switch's own frame and its own state,
//  where the sighting derives both, so the walk wins wherever it can answer.
//
//  It has a precondition of its own — Screen Recording, granted to a process that had it when it
//  connected to the window server — and that is why `PermissionInvitations.listed` asks for the
//  screen first. When the pixels are unavailable too, nothing changes from what this file already
//  did: the tier says so (`SettingsWindowFrame.Cause`), claims nothing about the pane's contents (it
//  draws no dashes — see `SettingsSpotlightScene.dashedRegions`), and watches for the grant closely
//  enough that the instant the user flips the switch the overlay stops degrading and rings the real
//  row.

// MARK: - What the choreography is allowed to say

/// The only two things the overlay can be. There is deliberately no third case that points
/// "approximately" — the type is what makes a mispositioned arrow unrepresentable.
enum PermissionGuidance: Equatable, Sendable {
    /// The target was located and is really on screen. Global CoreGraphics coordinates, top-left
    /// origin, the convention the Accessibility API and CoreGraphics both use.
    case pointing(SettingsSpotlightTarget)
    /// System Settings is on screen and we know exactly where its window is, and nothing about what
    /// is inside it.
    ///
    /// This used to be the **normal state of the Accessibility step**, because reading the row that
    /// grants Accessibility requires Accessibility and the old overlay spent that step asking the
    /// Accessibility API 24 times in 9 seconds for an answer it was structurally forbidden from
    /// getting. It is now the *floor* of that step rather than its ceiling: `SettingsRowSighting`
    /// reads the row out of the pane's pixels instead, and this is what is left when even that cannot
    /// — no Screen Recording grant yet, or a grant this process was not launched with.
    /// `CGWindowListCopyWindowInfo` needs no grant at all, so the window rect is still something
    /// measured — it is what the scrim opens a hole in, and what the sentence is placed beside.
    ///
    /// **It is not something to dash.** Knowing the window and nothing inside it is knowing that the
    /// answer is one of forty rows, and a dashed rectangle around forty rows says "somewhere in
    /// here", which is not an instruction — it is the same defect this overlay already fixed one
    /// level down, where the dashes used to go round a whole list instead of round the slot a row
    /// lands in. See `SettingsSpotlightScene.dashedRegions`.
    case framing(SettingsWindowFrame)
    /// Nothing could be located, or it was located somewhere the user cannot see. Words only.
    case instruction(String)

    /// True only for the case that draws an arrow. Reads better than a pattern match at call sites
    /// whose only question is whether anything is being aimed.
    var isPointing: Bool {
        if case .pointing = self { return true }
        return false
    }
}

/// System Settings' window, and what to do once you are looking at it.
struct SettingsWindowFrame: Equatable, Sendable {
    /// Global CoreGraphics coordinates, from the window server rather than from the Accessibility
    /// API — which is the whole point of it.
    var window: CGRect
    var instruction: String
    /// **Why the pane could not be read.**
    ///
    /// The rect is the same either way and the two causes are three orders of magnitude apart in
    /// what it costs to ask again, so the tracker cannot tell them apart from the rect alone and
    /// must be told. Defaults to the pessimistic one: a caller that has not thought about it gets
    /// the slow schedule, never the fast one.
    var cause: Cause = .unreadable

    /// The two ways the contents of a window can be unknown.
    enum Cause: Equatable, Sendable {
        /// **We are not AX-trusted, so the pane is structurally unreadable** — see this file's
        /// header for the measurements, every one of which is `kAXErrorAPIDisabled`. Two things
        /// follow, and both matter to the tracker.
        ///
        /// Re-asking is nearly free: `liveGuidance` returns at the `AXElement.isTrusted` guard
        /// without touching the tree, and the whole pass measured **0.55 ms** on macOS 26.5.2 —
        /// `AXIsProcessTrusted` 0.008 ms, `CGWindowListCopyWindowInfo` 0.42 ms, the display list
        /// 0.011 ms, `runningApplications` 0.108 ms.
        ///
        /// And the answer is about to change: the one event this tier is waiting for is the user
        /// flipping the very switch the overlay was opened to talk about, and Accessibility takes
        /// effect live with no relaunch. Waiting out the expensive schedule before noticing is
        /// paying a 800 ms delay for a cost that is not being incurred.
        case awaitingTrust
        /// We are trusted and the walk still found nothing: a pane whose shape we have never seen,
        /// one that has not finished laying out, or a list we are simply not in. Re-asking costs the
        /// whole walk — 270–727 ms, measured live — and nothing the user is about to do makes it
        /// cheaper, so this keeps the slow schedule.
        case unreadable
    }
}

/// A located row in System Settings: what to ring, what the hand points at, and whether the switch
/// is already on.
struct LocatedSettingsRow: Equatable {
    /// The whole row — label through switch. What the ring goes around.
    var row: CGRect
    /// The switch itself. What the hand points at, because it is the thing to press.
    var toggle: CGRect
    /// The switch's current state, read from the same element. A row that is already on needs no
    /// hand, so the caller can stop rather than instruct someone to do what they have done.
    var isOn: Bool
}

// MARK: - The element the locator walks

/// The narrow view of an accessibility element the locator needs.
///
/// `AXElement` is the app's AX wrapper and is used here for the one question it can answer about
/// this problem — `AXElement.isTrusted`, the precondition for any of this working at all. It cannot
/// answer the rest: it is a *text capture* type by design ("makes no policy decisions … only
/// answers questions") and deliberately exposes no geometry and no `AXIdentifier`, and it keeps its
/// `AXUIElement` private so geometry cannot be recovered from one. Rather than widen a type three
/// other call sites depend on, the locator declares the shape it needs and `LiveSettingsElement`
/// implements it — which is also what lets the whole lookup be tested against a fake tree, with no
/// System Settings and no grant.
protocol SettingsElement {
    var elementRole: String? { get }
    /// System Settings' own `AXIdentifier`. Undocumented, and therefore never load-bearing on its
    /// own — see `SettingsRowLocator` for the fallback that runs when it is absent.
    var elementIdentifier: String? { get }
    var elementValue: String? { get }
    /// Screen coordinates, top-left origin. `nil` for an element that does not answer geometry.
    var elementFrame: CGRect? { get }
    /// `AXDescription`. The **+** and **−** buttons under a Privacy list carry no identifier, no
    /// title and no value — a description of `"Add"` is the only thing that distinguishes them, and
    /// it is what makes "click + and choose the app" pointable rather than merely sayable.
    var elementDescription: String? { get }
    var elementChildren: [any SettingsElement] { get }
}

extension SettingsElement {
    /// Defaulted so a fake element in a test can ignore it. Most of the tree has no description and
    /// nothing about the walk should depend on a fixture spelling that out.
    var elementDescription: String? { nil }
}

// MARK: - Finding the real row

/// Finds one application's row inside a Privacy & Security pane.
///
/// Measured against macOS 26.5.2 (build 25F84), where the two pane shapes are genuinely different
/// and a locator that assumed either one alone would miss half the time:
///
/// - **Microphone** is flat: `AXStaticText` and `AXCheckBox` as sibling leaves of one group.
/// - **Screen & System Audio Recording** and **Accessibility** are outlines:
///   `AXRow` → `AXCell` → (`AXStaticText`, `AXCheckBox`).
///
/// What both shapes share is System Settings' own identifiers on the two leaves —
/// `"<App Name>_Title"` and `"<App Name>_Toggle"` — so those are the primary handle, and matching
/// the label's *text* is the fallback for the day they change. Neither is trusted blindly: the
/// result is only ever returned with a frame that was really read off the element.
struct SettingsRowLocator {
    /// The name System Settings lists us under: `CFBundleName`, which is what builds the identifier.
    let appName: String
    var limits = Limits()

    /// Ceilings, for the same reason `AccessibilityTree` has them: an application can answer AX
    /// queries slowly and claim any number of children, and this runs while the user is waiting.
    struct Limits {
        var maxDepth = 18
        var maxNodes = 4_000
    }

    /// Where a row can be.
    ///
    /// `offscreen` is a separate case rather than folded into `notFound` because the two deserve
    /// different sentences: one asks the user to scroll, the other cannot say where to look at all.
    /// Both refuse to point.
    enum Location: Equatable {
        case visible(LocatedSettingsRow)
        /// Found in the tree, but clipped out of view by a scroll area or the window edge.
        case offscreen(LocatedSettingsRow)
        case notFound
    }

    /// Everything the overlay needs, which is strictly more than the row.
    ///
    /// The extra case is the one the row-only lookup could never express: the pane is right there
    /// and readable, and this application simply **is not in the list**. That is not a failure —
    /// it is a different instruction, with a different control to point at (**+**, or the list
    /// itself), and collapsing it into `notFound` is why the overlay used to give up and print a
    /// sentence on the exact screen where the user most needed showing.
    enum TargetLocation: Equatable {
        case visible(SettingsSpotlightTarget)
        case offscreen(SettingsSpotlightTarget)
        /// The pane was read, the list was found, and we are not in it.
        case notListed(NotListed)
        case notFound
    }

    /// The pane, minus us.
    struct NotListed: Equatable {
        /// The whole settings area, already clipped to what is on screen.
        var area: CGRect
        /// The list rows live in — the place something has to end up.
        var list: CGRect
        /// The **+** button, when the pane has one. `nil` for Microphone, which has no way to add
        /// an application by hand and therefore nothing to point at.
        var add: CGRect?
        /// A label of ours sitting outside the list: the row waiting to be dragged in. `nil` in the
        /// ordinary case, where we are simply absent.
        var strayRow: CGRect?
    }

    private var titleIdentifier: String { "\(appName)_Title" }
    private var toggleIdentifier: String { "\(appName)_Toggle" }

    /// Walks `root` for our row.
    ///
    /// `preferring` picks between the several sections a pane can have — the Screen Recording pane
    /// on macOS 26 lists us **twice**, once under "Screen & System Audio Recording" and again under
    /// "System Audio Recording Only", and pointing at the wrong one is exactly the mispositioned
    /// arrow this whole file is arranged to avoid. Ordinal, not by header text: the header is a
    /// sibling of the section rather than its ancestor, so there is no containment relation to
    /// search, and the order of the sections is stable where their wording is not.
    ///
    /// **It names a section, and an absent section is not a reason to point somewhere else.** See
    /// `Walk.hit(inSection:)`.
    func locate(in root: any SettingsElement, preferring occurrence: Int = 0) -> Location {
        let state = survey(root)
        guard let hit = state.hit(inSection: occurrence) else { return .notFound }
        return hit.isClipped ? .offscreen(hit.located) : .visible(hit.located)
    }

    /// The same walk, reporting the area and the gesture as well as the row.
    func locateTarget(
        in root: any SettingsElement, preferring occurrence: Int = 0, window: CGRect = .zero
    ) -> TargetLocation {
        let state = survey(root)

        if let hit = state.hit(inSection: occurrence) {
            let section = hit.section.map { state.sections[$0] }
            let target = SettingsSpotlightTarget(
                row: hit.located.row,
                toggle: hit.located.toggle,
                isOn: hit.located.isOn,
                // The switch is a 36 × 16 sliver. Glowing it exactly reads as a smudge on the row,
                // so the glow is given a floor — centred on the measured switch, never moved off it.
                focus: hit.located.toggle.atLeast(width: 56, height: 30),
                area: section?.clipped,
                list: section?.list,
                isListed: true,
                gesture: .click,
                window: window)
            return hit.isClipped ? .offscreen(target) : .visible(target)
        }

        // **The section asked for, or nothing.** Clamping here was the other half of the same defect:
        // a pane with one list, asked about the second, answered with the first list's **+** — so the
        // instruction under the arrow ("Click + and choose …") named a list the user was not looking
        // at. The two lists of the Screen Recording pane both exist whether or not we are in either,
        // so this only refuses on a pane that genuinely has no such section.
        guard occurrence >= 0, occurrence < state.sections.count else { return .notFound }
        let section = state.sections[occurrence]
        // A stray label of ours belongs to the section it sits nearest, which in every layout that
        // has one means the section it has to be dragged into.
        let stray = state.strayLabels.min { a, b in
            abs(a.midY - section.list.midY) < abs(b.midY - section.list.midY)
        }
        return .notListed(
            NotListed(area: section.clipped, list: section.list, add: section.add, strayRow: stray))
    }

    // MARK: The walk

    private struct Hit {
        var located: LocatedSettingsRow
        var isClipped: Bool
        /// Which section it was found in, when the walk was inside one.
        var section: Int?
    }

    /// One list and the chrome around it.
    ///
    /// Recognised by shape rather than by header text, because the headers are wording and the
    /// shape is structure. Measured on macOS 26.5.2 (build 25F84), where all three panes agree: the
    /// pane's content scroll area has one container per section directly beneath it, and everything
    /// belonging to that section — the caption, the list, the **+** and **−** — is inside it.
    ///
    /// - **Microphone**: `AXScrollArea` → `AXGroup` (caption + flat label/switch leaves). No **+**.
    /// - **Accessibility**: `AXScrollArea` → `AXGroup` (caption + `AXScrollArea`/`AXOutline` + **+**/**−**).
    /// - **Screen Recording**: `AXScrollArea` → two such `AXGroup`s, one per list.
    private struct Section {
        var area: CGRect
        var list: CGRect
        var add: CGRect?
        /// `area` with every enclosing scroll area and the window applied. What gets outlined — an
        /// unclipped area on the Accessibility pane runs 45 pt past the bottom of the window, and a
        /// dotted boundary drawn across the desktop below System Settings is a boundary around the
        /// wrong thing.
        var clipped: CGRect
        /// Whether anything inside this container is a control a person could switch.
        ///
        /// The filter that keeps the **sidebar** from being mistaken for the settings area. Measured
        /// live: `AXOutline` "Sidebar" is a container directly under a scroll area, exactly like the
        /// content list, and it comes *first* in document order — so the first version of this walk
        /// outlined the pane picker and reported the Accessibility pane as unreadable. The two are
        /// not told apart by role, position or depth; they are told apart by the fact that one holds
        /// switches and the other holds pane names.
        var hasControls = false
    }

    /// What is carried *down* the tree. Distinct from `Walk`, which is carried across it.
    private struct Descent {
        /// Every ancestor that can hide this element: the window, and each scroll area between.
        var clips: [CGRect] = []
        var parentRole: String?
        /// The section we are inside, once we are inside one.
        var section: Int?
    }

    private struct Walk {
        let limits: Limits
        var nodesRemaining: Int
        var hits: [Hit] = []
        var sections: [Section] = []
        /// Labels carrying our name that are **not** inside any list. See `NotListed.strayRow`.
        var strayLabels: [CGRect] = []

        init(limits: Limits) {
            self.limits = limits
            nodesRemaining = limits.maxNodes
        }

        /// **Our row in the section that was asked for, and never a different section's row.**
        ///
        /// This replaced `hits[clamp(occurrence, to: hits.count)]`, and the clamp is the whole of a
        /// live defect. On the Screen & System Audio Recording pane the *second* list — "System Audio
        /// Recording Only" — routinely holds no row for this application: macOS creates that TCC
        /// record lazily, on a CoreAudio process tap the app attempts, so until one has been tried
        /// the list does not mention us at all. Measured on macOS 26.5.2 (25F84): `tccutil reset
        /// AudioCapture com.omi.context-for-claude` left that list holding one other application and
        /// nothing of ours, which is the reported screenshot exactly.
        ///
        /// In that state there is **one** hit — the screen-recording row in the upper list — and
        /// `clamp(1, to: 1)` answered `0`. The overlay then rang the *Screen Recording* switch with
        /// total confidence while the card was asking for system audio. Measured live against the
        /// real pane in that state, through `guidance(for:appName:windows:windowFrame:space:)`: the
        /// walk answered a row at y 451.5 with its switch at (1233, 457.5) — the upper list's row for
        /// this app, whose label OCR put at y 458.5 — while the lower list's rows begin at y 1019.
        /// With the clamp gone the same call answers the **+** under the lower list at (819, 1056),
        /// inside that list's own area of (819, 1019.5, 460, 60.5).
        ///
        /// Reported verbatim: *"Even after I turned it on this still doesnt go away … this is only
        /// showing properly in accessibility and is not perfect for audio now"* — the switch the user
        /// turned on was the one the arrow pointed at, and it was the wrong one.
        ///
        /// An ordinal that names a section has to be matched against the section a hit was found in,
        /// which the walk already records. The one fallback is a pane the walk found no sections in at
        /// all — the flat Microphone layout on a macOS that does not wrap it, and every fixture that
        /// does not model one. There the pane *is* the single list, so ordinal 0 names it and any
        /// other ordinal names nothing.
        func hit(inSection occurrence: Int) -> Hit? {
            guard occurrence >= 0 else { return nil }
            if let inSection = hits.first(where: { $0.section == occurrence }) { return inSection }
            guard sections.isEmpty, occurrence == 0 else { return nil }
            return hits.first
        }
    }

    private func survey(_ root: any SettingsElement) -> Walk {
        var state = Walk(limits: limits)
        var descent = Descent()
        if let frame = root.elementFrame { descent.clips.append(frame) }
        walk(root, depth: 0, descent: descent, state: &state)

        // Drop the containers that turned out to hold no controls — the sidebar, and anything else
        // shaped like a list that is not one — and renumber the hits onto what is left. Done after
        // the walk rather than during it because "holds a switch" is only knowable once the subtree
        // has been seen.
        var remap: [Int: Int] = [:]
        var kept: [Section] = []
        for (index, section) in state.sections.enumerated() where section.hasControls {
            remap[index] = kept.count
            kept.append(section)
        }
        state.sections = kept
        state.hits = state.hits.map { hit in
            var hit = hit
            hit.section = hit.section.flatMap { remap[$0] }
            return hit
        }
        return state
    }

    /// One pass, carrying the clip stack and the current section down.
    ///
    /// The clip stack is why a scrolled row degrades instead of being pointed at: a row scrolled out
    /// of a list still answers with a perfectly plausible frame — one that is nowhere the user can
    /// see — and pointing at it is the exact failure mode that makes an overlay worse than a
    /// sentence.
    private func walk(_ element: any SettingsElement, depth: Int, descent: Descent, state: inout Walk) {
        guard depth <= limits.maxDepth, state.nodesRemaining > 0 else { return }
        state.nodesRemaining -= 1

        var descent = descent
        let role = element.elementRole
        if role == kAXScrollAreaRole, let frame = element.elementFrame {
            descent.clips.append(frame)
        }

        let children = element.elementChildren

        // The outermost container directly under a scroll area is the section. Outermost, not
        // nearest: on the Accessibility pane the nearest is the list's own outline, and outlining
        // the list alone leaves the **+** button — the thing an unlisted user has to press — outside
        // the boundary that is supposed to say "everything here".
        if descent.section == nil, role == kAXGroupRole || role == kAXOutlineRole,
            descent.parentRole == kAXScrollAreaRole, let frame = element.elementFrame
        {
            let clipped = descent.clips.reduce(frame) { $0.intersection($1) }
            let add = addButton(in: children)
            state.sections.append(
                Section(
                    area: frame, list: frame, add: add,
                    clipped: clipped.isNull ? frame : clipped, hasControls: add != nil))
            descent.section = state.sections.count - 1
        } else if let section = descent.section, role == kAXOutlineRole, let frame = element.elementFrame {
            // A list nested inside the section: the rows live here, and this is where something
            // being dragged in has to land.
            state.sections[section].list = frame
        }

        if let section = descent.section, role == kAXCheckBoxRole {
            state.sections[section].hasControls = true
        }

        if let hit = row(in: element, children: children, clips: descent.clips, section: descent.section) {
            state.hits.append(hit)
            // No descent past a match: the row's own subtree cannot contain a second row, and
            // stopping keeps a nested outline from reporting the same switch twice.
            return
        }

        if descent.section == nil, isOurLabel(element), let frame = element.elementFrame {
            // Our name, outside every section. On a pane that wants the row dragged into the list,
            // this is the row.
            state.strayLabels.append(frame)
        }

        descent.parentRole = role
        for child in children {
            walk(child, depth: depth + 1, descent: descent, state: &state)
        }
    }

    /// The **+** under a list. No identifier, no title — the description is all there is.
    private func addButton(in children: [any SettingsElement]) -> CGRect? {
        guard
            let button = children.first(where: {
                $0.elementRole == kAXButtonRole && $0.elementDescription == "Add"
            }), let frame = button.elementFrame
        else { return nil }
        // System Settings answers 9 × 9 for a button that is drawn about 24 × 24 — the frame it
        // reports is the glyph, not the control. The **centre** is measured and is trusted; the size
        // is floored so the glow covers the button the user actually has to hit. Growing around a
        // measured centre can only ever be generous, never wrong about where.
        return frame.atLeast(width: 24, height: 24)
    }

    /// Whether `element` is the container of our row, and if so where.
    ///
    /// Reads the label and the switch out of the *same* container so the two halves can never come
    /// from different rows — a union of one app's label with the next app's switch would produce a
    /// highlight that looks right and is wrong.
    private func row(
        in element: any SettingsElement, children: [any SettingsElement], clips: [CGRect], section: Int?
    ) -> Hit? {
        guard let toggle = children.first(where: isOurToggle), let toggleFrame = toggle.elementFrame
        else { return nil }

        let label = children.first(where: isOurLabel)?.elementFrame
        // The row is the label through the switch when the label answered, and the container's own
        // frame when it did not. Never the switch alone: a 36 × 16 highlight on a 460 pt row reads
        // as a dot beside the thing instead of around it.
        let band = label.map { $0.union(toggleFrame) } ?? element.elementFrame ?? toggleFrame

        let located = LocatedSettingsRow(row: band, toggle: toggleFrame, isOn: isOn(toggle))
        let clipped = !clips.allSatisfy { $0.contains(toggleFrame) }
        return Hit(located: located, isClipped: clipped, section: section)
    }

    private func isOurToggle(_ element: any SettingsElement) -> Bool {
        guard element.elementRole == kAXCheckBoxRole else { return false }
        // The identifier when System Settings offers one. When it does not, any switch sitting
        // beside our label is ours — which is why this is only ever asked of a container that
        // already matched `isOurLabel`, never of the pane at large.
        return element.elementIdentifier == toggleIdentifier || element.elementIdentifier == nil
    }

    private func isOurLabel(_ element: any SettingsElement) -> Bool {
        guard element.elementRole == kAXStaticTextRole else { return false }
        return element.elementIdentifier == titleIdentifier || element.elementValue == appName
    }

    /// System Settings answers a switch's state as `"1"` / `"0"`, or as a bridged number.
    private func isOn(_ element: any SettingsElement) -> Bool {
        guard let value = element.elementValue else { return false }
        return value == "1" || value.lowercased() == "true"
    }
}

// MARK: - The real accessibility tree

/// `SettingsElement` over a live `AXUIElement`.
///
/// Every property is one synchronous message to System Settings, which is why the locator above is
/// bounded on depth and node count rather than trusting the tree to be small.
struct LiveSettingsElement: SettingsElement {
    private let element: AXUIElement

    init(_ element: AXUIElement) {
        self.element = element
    }

    /// System Settings' windows, or an empty array when it is not running, is not readable, or this
    /// process is not trusted. An empty array is what makes the locator degrade instead of throw.
    static func systemSettingsWindows(bundleID: String = "com.apple.systempreferences") -> [LiveSettingsElement] {
        guard AXElement.isTrusted else { return [] }
        guard let app = NSRunningApplication.runningApplications(withBundleIdentifier: bundleID).first
        else { return [] }
        let axApp = AXUIElementCreateApplication(app.processIdentifier)
        // Every read below is a synchronous message into another process, and the default ceiling
        // is six seconds. System Settings does hang — mid pane switch, mid login-item scan — and
        // without this a single stuck reply stalls the solver for longer than the whole step lasts.
        AXUIElementSetMessagingTimeout(axApp, 0.35)
        guard let raw = copy(kAXWindowsAttribute, from: axApp),
            CFGetTypeID(raw) == CFArrayGetTypeID(),
            let array = raw as? [AnyObject]
        else { return [] }
        return array.compactMap { window in
            guard CFGetTypeID(window) == AXUIElementGetTypeID() else { return nil }
            let element = LiveSettingsElement(window as! AXUIElement)
            // `AXWindows` is not promised to contain windows, and on macOS 26.5.2 it demonstrably
            // does not: measured live, System Settings answered its **own application element**,
            // whose children are the application again and the menu bar. Walking that costs the
            // locator's entire 4,000-node budget on 3,925 menu items and finds nothing — 593 ms to
            // learn what one role read says immediately. Checking the role is also what turns a
            // degenerate answer into the honest `framing` fallback instead of a slow `notFound`.
            guard element.elementRole == kAXWindowRole else { return nil }
            return element
        }
    }

    var elementRole: String? { string(kAXRoleAttribute) }
    var elementIdentifier: String? { string("AXIdentifier") }
    var elementDescription: String? { string(kAXDescriptionAttribute) }

    /// A switch answers `AXValue` as a number, not a string, so this cannot use the string-only read
    /// `AXElement` uses for text capture — there, a slider's position getting into the text index is
    /// the bug; here, the number *is* the answer.
    var elementValue: String? {
        guard let value = Self.copy(kAXValueAttribute, from: element) else { return nil }
        if CFGetTypeID(value) == CFStringGetTypeID() { return value as? String }
        if let number = value as? NSNumber { return number.intValue == 0 ? "0" : "1" }
        return nil
    }

    var elementFrame: CGRect? {
        guard let position = Self.copy(kAXPositionAttribute, from: element),
            let size = Self.copy(kAXSizeAttribute, from: element),
            CFGetTypeID(position) == AXValueGetTypeID(),
            CFGetTypeID(size) == AXValueGetTypeID()
        else { return nil }
        var origin = CGPoint.zero
        var extent = CGSize.zero
        guard AXValueGetValue(position as! AXValue, .cgPoint, &origin),
            AXValueGetValue(size as! AXValue, .cgSize, &extent)
        else { return nil }
        return CGRect(origin: origin, size: extent)
    }

    var elementChildren: [any SettingsElement] {
        guard let raw = Self.copy(kAXChildrenAttribute, from: element),
            CFGetTypeID(raw) == CFArrayGetTypeID(),
            let array = raw as? [AnyObject]
        else { return [] }
        return array.compactMap { child in
            guard CFGetTypeID(child) == AXUIElementGetTypeID() else { return nil }
            return LiveSettingsElement(child as! AXUIElement)
        }
    }

    private func string(_ attribute: String) -> String? {
        guard let value = Self.copy(attribute, from: element),
            CFGetTypeID(value) == CFStringGetTypeID()
        else { return nil }
        return value as? String
    }

    private static func copy(_ attribute: String, from element: AXUIElement) -> AnyObject? {
        var value: AnyObject?
        // Any error means "this element does not answer that", which is ordinary: not every element
        // has an identifier, and an application mid-relayout answers nothing at all.
        guard AXUIElementCopyAttributeValue(element, attribute as CFString, &value) == .success
        else { return nil }
        return value
    }
}

// MARK: - Deciding what to say

/// Turns a capability into either a ring around the real row or a sentence, and never into a guess.
///
/// Split out from the overlay so the decision — the part with a wrong answer available — is testable
/// with no window server, no System Settings and no grant.
enum PermissionChoreography {
    /// Which of the pane's sections holds the row for this capability.
    ///
    /// This exists because the Screen Recording pane on macOS 26.5 lists an app **twice** — under
    /// "Screen & System Audio Recording" and again under "System Audio Recording Only" — so "the row
    /// for this app" is ambiguous there and ringing the wrong one is the mispositioned overlay
    /// arriving by an entirely plausible route. Every capability is 0 today, which is the point: the
    /// section is chosen by construction rather than by whichever match the walk happened to reach
    /// first.
    ///
    /// `systemAudio` is **1**: its switch is the one in "System Audio Recording Only", the second
    /// list. This said 0, and justified it by noting that `Capability.settingsPane` sent system audio
    /// to the Microphone pane — a pane with a single list, where section 1 does not exist.
    ///
    /// Both halves of that were wrong, and being wrong *together* is what made them look right. Live
    /// on macOS 26.5.2 (25F84): Privacy & Security ▸ **Screen & System Audio Recording** carries both
    /// lists, and the Microphone pane carries neither — it does not list the tap at all. So the old
    /// pairing opened a pane the row was not on and then rang section 0 of it. `settingsPane` now
    /// sends system audio to the Screen Recording pane and this picks the list within it. The two
    /// have to move together, or the overlay rings the *screen recording* row while the card is
    /// asking for system audio — the confident-arrow-at-the-wrong-control failure this file exists to
    /// prevent.
    ///
    /// **And that failure happened anyway, by a route the ordinal alone could not prevent.** The row
    /// this names is created lazily, on a tap the app attempts, and is simply not in the list before
    /// then (measured — `Permissions.materialiseSettingsRow(for:)`) — so the pane routinely held
    /// **one** row for this app, in the *other* list, and `SettingsRowLocator` clamped the ordinal
    /// onto it. Two things follow, and both live elsewhere because neither belongs to this number:
    /// the walk no longer clamps (`SettingsRowLocator.Walk.hit(inSection:)`), and the tap is
    /// attempted before the pane is opened (`PermissionGate.waitInSettings`), which usually answers
    /// the question outright and otherwise gets the row drawn before anybody looks for it.
    static func sectionOccurrence(for capability: Capability) -> Int {
        switch capability {
        case .microphone, .screen, .accessibility: return 0
        case .systemAudio: return 1
        }
    }

    /// What the user has to do in their own terms, for the case where we cannot show them.
    ///
    /// Names the pane and the row, because that is the whole of the instruction once the pointing
    /// is off the table.
    static func instruction(for capability: Capability, appName: String, scrolled: Bool) -> String {
        let place = paneName(for: capability)
        if scrolled {
            return "Scroll down to \(appName) in \(place) and switch it on."
        }
        return "In System Settings, open \(place) and switch on \(appName)."
    }

    static func paneName(for capability: Capability) -> String {
        switch capability {
        case .microphone: return "Privacy & Security ▸ Microphone"
        case .systemAudio: return "Privacy & Security ▸ Screen & System Audio Recording"
        case .screen: return "Privacy & Security ▸ Screen & System Audio Recording"
        case .accessibility: return "Privacy & Security ▸ Accessibility"
        }
    }

    /// The sentence that goes *on* the overlay, beside the arrow. Different from `instruction`,
    /// which has to work with nothing drawn: this one is read next to a glowing control, so it says
    /// what to do to it and nothing else. Long captions over another application do not get read.
    static func caption(for gesture: SettingsGesture, appName: String, isOn: Bool, listed: Bool) -> String {
        switch gesture {
        case .drag:
            // "up into the list" and not "into the list": the direction is the half of this
            // instruction a user cannot infer from the pane, and naming it is what the overlay's
            // arrow and hand are both saying anyway.
            return "Drag \(appName) up into the list"
        case .click where !listed:
            return "Click + and choose \(appName)"
        case .click:
            return isOn ? "Already on" : "Click this switch to turn on \(appName)"
        }
    }

    /// The decision, in one place.
    ///
    /// `windows` is passed in rather than read here so the whole thing runs against a fake tree.
    /// Every failure — not trusted, not running, not found, scrolled away — comes out as an
    /// `instruction`, and only something really on screen comes out as `pointing`.
    static func guidance(
        for capability: Capability,
        appName: String,
        windows: [any SettingsElement],
        windowFrame: CGRect = .zero,
        space: ScreenSpace? = nil
    ) -> PermissionGuidance {
        let locator = SettingsRowLocator(appName: appName)
        let occurrence = sectionOccurrence(for: capability)

        var sawScrolledRow = false
        var fallback: SettingsSpotlightTarget?
        for window in windows {
            switch locator.locateTarget(in: window, preferring: occurrence, window: windowFrame) {
            case .visible(let target):
                guard let clamped = clamped(target, to: windowFrame) else {
                    // The row is measured, and outside the window. Measured on macOS 26.5.2: after a
                    // resize System Settings answers stale inner frames for a second or so — an
                    // `AXScrollArea` 880 pt tall inside a 470 pt window — so an inner frame is never
                    // trusted as its own bound. The window rect is, and it comes from the window
                    // server rather than from the application being measured.
                    sawScrolledRow = true
                    continue
                }
                if let onScreen = vetted(clamped, space: space) { return .pointing(onScreen) }
                // Measured, and nowhere a person can look. A window dragged off the side of a
                // display that was then unplugged reads exactly like this, and drawing "roughly
                // there" is the failure the whole file is arranged around.
                sawScrolledRow = true
            case .offscreen:
                sawScrolledRow = true
            case .notListed(let pane):
                // The pane is right there and we are not in it. Different instruction, different
                // control — and the first one is only kept if nothing better turns up in a later
                // window, because a real row always beats an add button.
                if fallback == nil, let target = notListedTarget(pane, window: windowFrame),
                    let clamped = clamped(target, to: windowFrame)
                {
                    fallback = vetted(clamped, space: space)
                }
            case .notFound:
                continue
            }
        }
        if let fallback { return .pointing(fallback) }
        return .instruction(instruction(for: capability, appName: appName, scrolled: sawScrolledRow))
    }

    /// The target for a pane this application is not listed in.
    ///
    /// Two shapes, in order of how much they claim. A stray row of ours outside the list is
    /// something to **drag** into it, and both ends of that arrow were measured. Otherwise the **+**
    /// button is a **click** — the only other route a Privacy list offers. A pane with neither (the
    /// Microphone list, which cannot be added to by hand) yields nothing, and the caller falls
    /// through to words.
    static func notListedTarget(_ pane: SettingsRowLocator.NotListed, window: CGRect) -> SettingsSpotlightTarget? {
        if let stray = pane.strayRow {
            return SettingsSpotlightTarget(
                row: stray, toggle: stray, isOn: false,
                focus: pane.list, area: pane.area, list: pane.list, isListed: false,
                gesture: .drag(source: stray), window: window)
        }
        guard let add = pane.add else { return nil }
        return SettingsSpotlightTarget(
            row: add, toggle: add, isOn: false,
            focus: add, area: pane.area, list: pane.list, isListed: false,
            gesture: .click, window: window)
    }

    /// The last check before anything is drawn: is what we found somewhere a person can look?
    ///
    /// `nil` for a `space` means "not asked" — the pure decision tests do not model displays and
    /// must not be made to. Live callers always pass one.
    private static func vetted(_ target: SettingsSpotlightTarget, space: ScreenSpace?) -> SettingsSpotlightTarget? {
        guard let space else { return target }
        return space.isOnScreen(target.focus) ? target : nil
    }

    /// Trims everything the Accessibility API said against the window the *window server* said.
    ///
    /// One authority per question. The application being measured is authoritative about what its
    /// controls are and unreliable about where they are during a relayout; the window server is
    /// authoritative about the window. So every derived rect is clipped to the window, and a focus
    /// that falls outside it entirely — the row scrolled away, or a stale frame — returns `nil` and
    /// takes the arrow with it. There is no `AXScrollToVisible` on these rows, so a scrolled-away
    /// row cannot be brought back for the user and must not be drawn over whatever took its place.
    ///
    /// `window == .zero` means the caller did not supply one, which is how the pure decision tests
    /// run; nothing is clamped then.
    static func clamped(_ target: SettingsSpotlightTarget, to window: CGRect) -> SettingsSpotlightTarget? {
        guard window != .zero else { return target }
        guard window.intersects(target.focus) else { return nil }
        if case .drag(let source) = target.gesture, !window.intersects(source) { return nil }

        var trimmed = target
        trimmed.area = target.area.map { $0.intersection(window) }.flatMap { $0.isNull ? nil : $0 }
        trimmed.list = target.list.map { $0.intersection(window) }.flatMap { $0.isNull ? nil : $0 }
        if case .drag = target.gesture, let list = trimmed.list { trimmed.focus = list }
        return trimmed
    }

    /// The live call. Reads System Settings' real windows and hands them to the decision above.
    ///
    /// **Never call this on the main actor.** Every property read inside the walk is one synchronous
    /// cross-process message to System Settings; a live trace measured one pass at 727 ms, taken on
    /// the main actor at 2.5 Hz, which is most of the reason the overlay was described as glitching.
    /// `PermissionOverlay` runs it on a utility queue and hops back only to draw.
    ///
    /// Refuses to walk at all when this process is not trusted, because the walk cannot answer:
    /// `systemSettingsWindows` returns nothing without the Accessibility grant, so 24 consecutive
    /// futile passes is what the old loop actually did while guiding the user to *give* that grant.
    /// That case falls to `framing`, which needs no permission at all.
    nonisolated static func liveGuidance(for capability: Capability, space snapshot: ScreenSpace)
        -> PermissionGuidance
    {
        // The caller's snapshot, taken from `NSScreen` on the main actor, is the authority. The
        // CoreGraphics list is the fallback for a caller that had none, and it is a fallback and not
        // the default because it was measured returning **zero displays** on a machine with a
        // display plainly attached — `CGGetActiveDisplayList` answers per window-server connection
        // and a process that has not drawn yet can get an empty one. An empty display list means
        // every rect is "on no display" and the overlay degrades to words for no reason at all.
        var space = snapshot
        if space.displays.isEmpty {
            space = ScreenSpace(displays: SettingsWindowProbe.displays())
            ContextTelemetry.recordFallback(
                area: .settings, from: "nsscreen-displays", to: "coregraphics-displays",
                reason: "empty-display-snapshot", outcome: .degraded)
        }
        let frame = SettingsWindowProbe.windowFrame()

        guard AXElement.isTrusted else {
            // The bootstrap case, and the one the user meets first: reading the Accessibility row
            // through the accessibility API requires Accessibility. Reading it off the screen does
            // not, so that is tried before giving up — and only then does the boundary fall back to
            // the window rather than the row.
            if let sighted = liveSighting(for: capability, frame: frame, space: space, trusted: false) {
                return sighted
            }
            return framingOrWords(
                for: capability, frame: frame, space: space, trusted: false, windows: 0)
        }

        let windows = LiveSettingsElement.systemSettingsWindows()
        let decision = guidance(
            for: capability, appName: appDisplayName, windows: windows, windowFrame: frame ?? .zero,
            space: space)
        if case .instruction = decision {
            // We could read the tree and still not find the row — a pane we have never seen, one
            // that has not finished laying out, or a list we are simply not in. The pixels are a
            // second opinion on all three, and none of those failures affects them: the sighting
            // does not care what shape the pane is, only that our name is drawn in it.
            if let sighted = liveSighting(for: capability, frame: frame, space: space, trusted: true) {
                return sighted
            }
            // The window is real either way, so the boundary still goes around something measured.
            return framingOrWords(for: capability, frame: frame, space: space, trusted: true, windows: windows.count)
        }
        log(decision, capability: capability, trusted: true, windows: windows.count)
        return decision
    }

    /// **The pixel route**: the row, read out of the pane's own screenshot.
    ///
    /// Deliberately the last thing tried and never the first. The accessibility walk measures the
    /// switch and reads its state off the switch; this derives both from one label and the window's
    /// right edge, so it is strictly the weaker answer wherever the stronger one is available.
    ///
    /// It goes through exactly the same two gates a walked target does — `clamped` against the frame
    /// the *window server* reported, then `vetted` against the displays — so a sighting cannot reach
    /// the screen by a shorter path than a walk. The measurement is a different provider; the standard
    /// for drawing an arrow is not.
    ///
    /// `SettingsPaneSightings` never blocks: this returns `nil` on the ticks before the first pass
    /// lands, and the overlay shows the written instruction in the meantime, which is what it would
    /// have shown anyway.
    ///
    /// **`labels` is a parameter for the same reason `windows` is one on `guidance(for:appName:…)`.**
    /// Everything with a wrong answer available — the section ordinal, the clamp, the display vet — is
    /// on this side of the seam and runs against a fixture with no System Settings, no window server
    /// and no grant. Only the reading itself is live.
    static func sighting(
        for capability: Capability, appName: String = appDisplayName, labels: [RecognizedLabel],
        frame: CGRect, space: ScreenSpace?
    ) -> PermissionGuidance? {
        guard !labels.isEmpty else { return nil }
        let sighting = SettingsRowSighting(appName: appName)
        guard case .sighted(let target) = sighting.locate(
            in: labels, window: frame, preferring: sectionOccurrence(for: capability))
        else { return nil }
        guard let clamped = clamped(target, to: frame), let onScreen = vetted(clamped, space: space)
        else { return nil }
        return .pointing(onScreen)
    }

    /// The live half: take the most recent reading of the pane and hand it to the decision above.
    private static func liveSighting(
        for capability: Capability, frame: CGRect?, space: ScreenSpace, trusted: Bool
    ) -> PermissionGuidance? {
        guard let frame else { return nil }
        let labels = SettingsPaneSightings.shared.labels(for: capability, of: frame)
        guard let decision = sighting(for: capability, labels: labels, frame: frame, space: space)
        else { return nil }
        log(decision, capability: capability, trusted: trusted, windows: 0)
        return decision
    }

    /// The window, when we know where it is; words, when we do not. The overlay's floor.
    ///
    /// Internal rather than private because `trusted` is the one input that decides how the tier
    /// behaves afterwards and it is not reachable from a unit test any other way: the live call
    /// reads it from `AXIsProcessTrusted()`, and a test that has to revoke a real grant to reach a
    /// branch is a test nobody runs. `PermissionGuidanceTests` drives this directly.
    static func framingOrWords(
        for capability: Capability, frame: CGRect?, space: ScreenSpace, trusted: Bool, windows: Int
    ) -> PermissionGuidance {
        let words = instruction(for: capability, appName: appDisplayName, scrolled: false)
        let decision: PermissionGuidance
        if let frame, space.isOnScreen(frame) {
            decision = .framing(
                SettingsWindowFrame(
                    window: frame, instruction: words,
                    // The bootstrap case carries *why* it is degraded, because that is what tells
                    // the tracker the answer is cheap to re-take and about to change.
                    cause: trusted ? .unreadable : .awaitingTrust))
        } else {
            decision = .instruction(words)
        }
        log(decision, capability: capability, trusted: trusted, windows: windows)
        return decision
    }

    /// Logs which way it went, because the hit rate of the lookup is the only honest measure of
    /// whether the overlay is worth showing — and it cannot be measured from a unit test, whose tree
    /// is a fixture by construction.
    private static func log(_ decision: PermissionGuidance, capability: Capability, trusted: Bool, windows: Int) {
        switch decision {
        case .pointing(let target):
            ContextLog.info(
                "choreography: pointing at the \(capability.rawValue) target at "
                    + "\(Int(target.focus.minX)),\(Int(target.focus.minY)) "
                    + "\(Int(target.focus.width))x\(Int(target.focus.height)), gesture "
                    + "\(target.gesture), switch is " + (target.isOn ? "on" : "off"),
                "permissions")
        case .framing(let framed):
            ContextLog.info(
                "choreography: could not read the \(capability.rawValue) pane "
                    + "(trusted: \(trusted)); outlining the System Settings window at "
                    + "\(Int(framed.window.minX)),\(Int(framed.window.minY))",
                "permissions")
        case .instruction:
            ContextLog.info(
                "choreography: could not locate the \(capability.rawValue) row "
                    + "(trusted: \(trusted), settings windows: \(windows)); "
                    + "showing the written instruction instead",
                "permissions")
        }
    }

    /// Forces the choreography onto one capability, for a self-test that must not revoke a real
    /// grant to reach the code path.
    ///
    /// Read from the environment rather than compiled behind `#if DEBUG`, because the build worth
    /// testing is the signed release bundle. It changes nothing for anyone who does not set it, and
    /// it can only ever *show* the overlay — the grant still has to be given by hand in System
    /// Settings, exactly as it would be otherwise. `CONTEXT_CHOREOGRAPHY_PROBE=accessibility`.
    static var probedCapability: Capability? {
        guard let raw = ProcessInfo.processInfo.environment["CONTEXT_CHOREOGRAPHY_PROBE"] else { return nil }
        return Capability(rawValue: raw)
    }

    /// The name System Settings lists us under. `CFBundleName` and not a literal, so a rename cannot
    /// leave the locator hunting for a row that no longer carries that name.
    static var appDisplayName: String {
        (Bundle.main.object(forInfoDictionaryKey: "CFBundleName") as? String)
            ?? (Bundle.main.object(forInfoDictionaryKey: "CFBundleDisplayName") as? String)
            ?? "Context for Claude"
    }
}

// MARK: - Tracking

/// What one tick of the tracker should do.
///
/// A separate, pure decision because the polling policy is where the old overlay actually went
/// wrong. It walked System Settings' whole accessibility tree — a thousand-odd synchronous
/// cross-process messages — **on the main actor, 2.5 times a second**, and a live trace caught one
/// pass taking 727 ms. That is not a subtle cost: it is most of a second of a frozen card, and it
/// is the "glitches a lot" the user reported. Being a value with a test on it is what keeps the
/// interval and the escape hatches from drifting back.
enum SpotlightTick: Equatable, Sendable {
    /// Read the tree again. Expensive, and off the main actor.
    case solve
    /// The window moved and did not resize, so the last answer is still right about everything
    /// except where. Free.
    case translate(CGVector)
    /// Nothing has changed. By far the most common answer, and the whole point.
    case hold
}

struct SpotlightTrackPolicy: Equatable, Sendable {
    /// How often the tree is re-read. Slow on purpose: a full solve only has to catch a scroll, a
    /// pane change or a grant landing, and every one of those is something a person did with their
    /// hands. Window drags are caught by `translate` at tick rate instead.
    var fullSolve: Duration = .milliseconds(800)
    /// How often the answer is re-taken while the only reason it is degraded is that we are **not
    /// trusted yet** — `SettingsWindowFrame.Cause.awaitingTrust`.
    ///
    /// The tick, deliberately: that tier's whole pass costs 0.55 ms against a 40 ms budget, and the
    /// tracker is already paying 0.42 ms of it every tick to read the window frame. `fullSolve` is
    /// 800 ms because the *walk* costs up to 727 ms, and on this tier there is no walk — so a step
    /// that cannot read the tree at all was waiting out a schedule built for the cost of reading it,
    /// and staying degraded for up to 800 ms after the user had already flipped the switch.
    var trustWatch: Duration = .milliseconds(40)
    /// How often the *window frame* is read. Cheap — one `CGWindowListCopyWindowInfo`, no
    /// Accessibility grant, no walk — so it can run fast enough that a dragged window does not
    /// leave the overlay behind.
    var tick: Duration = .milliseconds(40)

    /// How long `showing` is worth keeping before it is worth re-taking. One schedule per *cost*,
    /// not one per tier: what makes a re-solve expensive is the tree walk, and only the tiers that
    /// perform one have to be rationed.
    func interval(after showing: PermissionGuidance?) -> Duration {
        guard case .framing(let framed) = showing, framed.cause == .awaitingTrust else {
            return fullSolve
        }
        return trustWatch
    }

    func decide(
        sinceLastSolve: Duration, windowThen: CGRect?, windowNow: CGRect?, showing: PermissionGuidance?
    ) -> SpotlightTick {
        let due = sinceLastSolve >= interval(after: showing)
        guard let then = windowThen, let now = windowNow else {
            // Either we never had a window or it has gone. Only a solve can say which, and it is
            // the solve that degrades to words.
            return due ? .solve : .hold
        }
        // A resize relays the pane out: every row moves relative to the window, so nothing can be
        // carried over and the tree has to be read again.
        if then.size != now.size { return .solve }
        // **A due solve is never traded away for the cheap answer.** This used to answer `translate`
        // before it consulted the schedule, and the tracker does not reset its clock on a
        // translation — so a window whose origin changed on consecutive ticks starved the solve
        // outright. Dragging System Settings does that for as long as the mouse is down, which is
        // exactly when a user hunting for a row is most likely to be moving the window, and a grant
        // landing during it was never noticed. Translation is the cheap answer for the ticks
        // *between* solves; it is not a way to skip one.
        if due { return .solve }
        if then.origin != now.origin {
            return .translate(CGVector(dx: now.minX - then.minX, dy: now.minY - then.minY))
        }
        return .hold
    }
}

/// Keeps a good answer on screen through a transient failure.
///
/// Measured on macOS 26.5.2: System Settings routinely answers with **zero** accessibility windows
/// while the process is alive and its window is on screen — during launch, during a pane switch,
/// during a relayout. It stays that way for a tick or two. Treating the first empty answer as "it
/// has gone" makes the overlay flap between an arrow and a sentence while nothing the user can see
/// has changed at all, and flapping is indistinguishable from being broken.
///
/// So a worse answer has to arrive `tolerance` times in a row before it is believed. A *better*
/// answer is believed immediately: there is no reason to make somebody wait for guidance that has
/// become available.
struct SpotlightHysteresis: Sendable {
    var tolerance: Int
    private var misses = 0
    private var last: PermissionGuidance?

    init(tolerance: Int = 3) {
        self.tolerance = tolerance
    }

    /// How much a given answer claims. Only a drop in rank is doubted.
    private static func rank(_ guidance: PermissionGuidance) -> Int {
        switch guidance {
        case .pointing: return 2
        case .framing: return 1
        case .instruction: return 0
        }
    }

    mutating func settle(_ fresh: PermissionGuidance) -> PermissionGuidance {
        guard let previous = last else {
            last = fresh
            return fresh
        }
        if Self.rank(fresh) >= Self.rank(previous) {
            misses = 0
            last = fresh
            return fresh
        }
        misses += 1
        guard misses > tolerance else { return previous }
        misses = 0
        last = fresh
        ContextTelemetry.recordFallback(
            area: .settings, from: "spotlight-pointing", to: "spotlight-\(fresh.telemetryMode)",
            reason: "settings-target-lost", outcome: .degraded)
        return fresh
    }
}

extension PermissionGuidance {
    var telemetryMode: String {
        switch self {
        case .pointing: return "pointing"
        case .framing: return "framing"
        case .instruction: return "instruction"
        }
    }

    /// The System Settings window this answer was measured against, when there was one. The
    /// tracker's anchor.
    var anchorWindow: CGRect? {
        switch self {
        case .pointing(let target): return target.window == .zero ? nil : target.window
        case .framing(let framed): return framed.window
        case .instruction: return nil
        }
    }

    /// The same answer with the window somewhere else. A window drag translates its whole contents
    /// and nothing inside it moves relative to anything else, so this is exact rather than an
    /// approximation of a solve.
    func translated(by delta: CGVector) -> PermissionGuidance {
        switch self {
        case .pointing(let target):
            return .pointing(target.translated(by: delta))
        case .framing(var framed):
            framed.window = framed.window.offsetBy(dx: delta.dx, dy: delta.dy)
            return .framing(framed)
        case .instruction:
            return self
        }
    }
}

// MARK: - The overlay

/// A dotted boundary around the settings area, a glow on the control, and an arrow into it — or a
/// boundary and a sentence when the pane cannot be read, or a sentence alone when even the window
/// cannot be found.
///
/// Built the same way `MenuBarSpotlight` is — a borderless, click-through window above the app being
/// pointed at — for the same reason: the user has to be able to press the thing we are pointing at,
/// so the overlay must never be in the way of it. `SpotlightWindow.configure` owns those settings so
/// there is one place to assert them.
///
/// The window covers a whole display rather than the thing being pointed at. That is the change that
/// made this tractable: the frame is `NSScreen.frame` verbatim, so it needs no coordinate conversion,
/// and everything drawn inside it is a plain translation of what the Accessibility API answered. The
/// overlay this replaced resized and re-flipped its window on every tick, which is two chances a tick
/// to be wrong on a path nothing covered.
@MainActor
enum PermissionOverlay {
    private static var window: NSWindow?
    private static var host: NSHostingView<SettingsSpotlightView>?
    private static var tracker: Task<Void, Never>?
    private static var current: PermissionGuidance?
    private static var shownOn: CGRect?
    /// Once the grant lands the overlay stops taking updates: a tracker that solved one more time
    /// would replace "Switched on." with an arrow at the switch the user has just flipped.
    private static var confirming = false

    static var policy = SpotlightTrackPolicy()

    /// Shows the overlay for `capability` and keeps it correct until `hide()`.
    ///
    /// `resolve` is injectable only so this can be driven from a test or a probe; production passes
    /// the live lookup. It is `@Sendable` and not `@MainActor` because it is run **off** the main
    /// actor — see `SpotlightTick`.
    static func show(
        for capability: Capability,
        caption: String,
        resolve: @escaping @Sendable (Capability, ScreenSpace) -> PermissionGuidance = {
            PermissionChoreography.liveGuidance(for: $0, space: $1)
        }
    ) {
        tracker?.cancel()
        confirming = false
        // A new episode is a new pane, and System Settings changes pane without changing window — so
        // the pixels read for the last capability describe rows that are no longer there. The reading
        // is keyed by capability and would refuse them anyway; this is what keeps the refusal from
        // depending on two consecutive episodes being about different capabilities.
        SettingsPaneSightings.shared.forget()
        tracker = Task { @MainActor in
            var steadying = SpotlightHysteresis()
            // Snapshotted here, on the main actor, and handed to the solver. `NSScreen` is main-actor
            // state and the solver runs off it; reading the display list from the solver's thread is
            // what produced an empty one.
            let first = ScreenSpace.live
            var guidance = steadying.settle(await offMain { resolve(capability, first) })
            var lastSolve = ContinuousClock.now
            apply(guidance, caption: caption)

            while !Task.isCancelled {
                try? await Task.sleep(for: policy.tick)
                if Task.isCancelled || confirming { return }

                let displays = ScreenSpace.live
                let seen = await offMain { SettingsWindowProbe.windowFrame() }
                switch policy.decide(
                    sinceLastSolve: lastSolve.duration(to: .now),
                    windowThen: guidance.anchorWindow, windowNow: seen,
                    // What is on screen decides how soon it is worth asking again: a boundary that
                    // is only a boundary because we are not trusted yet is watched at tick rate, so
                    // the grant is seen the moment it lands.
                    showing: guidance)
                {
                case .hold:
                    continue
                case .translate(let delta):
                    guidance = guidance.translated(by: delta)
                    apply(guidance, caption: caption)
                case .solve:
                    let fresh = await offMain { resolve(capability, displays) }
                    lastSolve = .now
                    if Task.isCancelled || confirming { return }
                    guidance = steadying.settle(fresh)
                    apply(guidance, caption: caption)
                }
            }
        }
    }

    /// Confirms the grant on the overlay before it goes, so the user sees the thing they just did
    /// land. A confirmation nobody witnesses is the same as none.
    static func confirmGranted(_ text: String = "Switched on.") {
        tracker?.cancel()
        tracker = nil
        confirming = true
        guard let host else {
            hide()
            return
        }
        var scene = host.rootView.scene
        scene.caption = text
        scene.confirmed = true
        host.rootView = SettingsSpotlightView(scene: scene)
        Task { @MainActor in
            try? await Task.sleep(for: .milliseconds(1_400))
            hide()
        }
    }

    static func hide() {
        tracker?.cancel()
        tracker = nil
        current = nil
        shownOn = nil
        confirming = false
        SettingsPaneSightings.shared.forget()
        window?.orderOut(nil)
        window = nil
        host = nil
    }

    /// The guidance currently on screen. Exposed for the self-test probe, which reports the hit rate.
    static var showing: PermissionGuidance? { current }

    // MARK: Drawing

    private static func apply(_ guidance: PermissionGuidance, caption: String) {
        current = guidance
        let space = ScreenSpace.live

        switch guidance {
        case .pointing(let target):
            guard let display = space.display(holding: target.focus),
                let scene = SettingsSpotlightScene.make(
                    target: target,
                    caption: PermissionChoreography.caption(
                        for: target.gesture, appName: PermissionChoreography.appDisplayName,
                        isOn: target.isOn, listed: target.isListed),
                    display: display, space: space, exclusions: ourWindows(space: space))
            else {
                // Measured, and on no display. The last gate before drawing, and it refuses.
                return present(words: caption, space: space)
            }
            present(scene, on: display)

        case .framing(let framed):
            guard let display = space.display(holding: framed.window),
                let scene = SettingsSpotlightScene.make(
                    framing: framed, display: display, space: space,
                    exclusions: ourWindows(space: space))
            else { return present(words: framed.instruction, space: space) }
            present(scene, on: display)

        case .instruction(let words):
            present(words: words, space: space)
        }
    }

    /// Words alone, on the display the pointer is on — anchored to nothing, so a sentence can never
    /// read as a label on the wrong control.
    ///
    /// The one thing it is still worth measuring here is the display's *usable* area. This tier is
    /// reached precisely because System Settings could not be located — `framingOrWords` only gets
    /// this far when there is no window rect, or the rect is on no display — so there is nothing in
    /// the pane to place the sentence against. `visibleFrame` is a real measurement of the two
    /// pieces of chrome that are always somewhere: the menu bar, and the Dock wherever the user
    /// keeps it. `SettingsSpotlightScene.captionPlacement` pins the plate to the foot of it.
    private static func present(words: String, space: ScreenSpace) {
        let pointer = NSEvent.mouseLocation
        let screen =
            NSScreen.screens.first(where: { NSMouseInRect(pointer, $0.frame, false) })
            ?? NSScreen.main ?? NSScreen.screens.first
        guard let screen else { return }
        let display = DisplayGeometry(screen)
        guard let displayGlobal = space.globalFrame(of: display) else { return }
        let visible = space.global(from: screen.visibleFrame)
            .map { $0.offsetBy(dx: -displayGlobal.minX, dy: -displayGlobal.minY) }
        present(
            SettingsSpotlightScene(
                bounds: CGRect(origin: .zero, size: displayGlobal.size),
                visibleBounds: visible,
                area: nil, focus: nil, source: nil, arrow: nil, caption: words,
                backingScaleFactor: display.backingScaleFactor),
            on: display)
    }

    private static func present(_ scene: SettingsSpotlightScene, on display: DisplayGeometry) {
        let view = SettingsSpotlightView(scene: scene)
        if let window, let host {
            if shownOn != display.appKitFrame {
                window.setFrame(display.appKitFrame, display: false)
                shownOn = display.appKitFrame
            }
            host.rootView = view
            window.orderFrontRegardless()
            return
        }

        let created = SpotlightWindow.make(covering: display)
        let hosting = NSHostingView(rootView: view)
        hosting.frame = CGRect(origin: .zero, size: display.appKitFrame.size)
        hosting.autoresizingMask = [.width, .height]
        created.contentView = hosting
        window = created
        host = hosting
        shownOn = display.appKitFrame
        created.orderFrontRegardless()
    }

    /// Our own visible windows, in global CoreGraphics coordinates, so the scrim does not dim the
    /// card that is talking the user through this.
    private static func ourWindows(space: ScreenSpace) -> [CGRect] {
        // `NSApp` is an implicitly-unwrapped optional and really is nil outside a running
        // application — in a test host, in a tool. Nothing here is worth a crash: an empty list
        // means the scrim dims one of our own windows, which is a cosmetic loss.
        guard let app = NSApp else { return [] }
        return app.windows
            .filter { $0.isVisible && $0 !== window && $0.alphaValue > 0.01 }
            .compactMap { space.global(from: $0.frame) }
    }

    /// Runs `work` off the main actor and comes back with the answer.
    ///
    /// The single most important line in this file. Everything `resolve` touches — the accessibility
    /// walk, `CGWindowListCopyWindowInfo`, `CGGetActiveDisplayList` — is a synchronous call into
    /// another process or the window server, and all of it used to happen here, on the main thread,
    /// while a SwiftUI card was on screen.
    private static func offMain<T: Sendable>(_ work: @escaping @Sendable () -> T) async -> T {
        await withCheckedContinuation { continuation in
            DispatchQueue.global(qos: .userInitiated).async {
                continuation.resume(returning: work())
            }
        }
    }
}
