import AppKit
import ContextCore
import QuartzCore
import SwiftUI

/// Everything the timeline window knows: which day is loaded, where the playhead sits, how wide the
/// track's visible window is, and what has been decoded.
///
/// **The playhead is a time, not an index.** `playheadAt` is where the user actually put it, to the
/// fraction of a second; `playhead` is only the capture nearest that position. It used to be the
/// other way round — the index was the state and the time was read back off whichever frame it landed
/// on — and three separate complaints all came from that one fact. There was no position *between*
/// two captures for a dissolve to be a fraction of, so every step was a hard cut (`RewindScrub`); the
/// handle on the track jumped in three-second quanta instead of following the pointer; and
/// `travel(by:)` re-derived its base from the snapped frame each time, so any scroll delta smaller
/// than half a capture interval rounded straight back to where it started and was lost. Zoomed in to
/// the two-minute floor that is *every ordinary scroll event*, which is what "the scrolling does not
/// feel smooth" looks like from the inside — and it is why a momentum tail, whose deltas decay
/// towards zero by definition, could never do anything at all.
///
/// The two zooms live here side by side and are deliberately separate fields, because the spec is
/// explicit that they are different features and must not be conflated: `trackSpan` is how much
/// *time* the track shows, and `imageZoom` is how large the *picture* is drawn. Conflating them is
/// the easy mistake — both are called "zoom" and both have a plus and a minus — and it produces a
/// control that appears to work while doing the wrong thing.
///
/// The track zoom has two drivers — the magnifier buttons and a trackpad pinch over the track — and
/// exactly one mutation point, `setTrackWindow(_:)`. Neither driver owns any span arithmetic of its
/// own, so they cannot end up disagreeing about the bounds or about what a zoom is anchored on; the
/// arithmetic itself lives in `RewindZoom`, where it is testable without a window.
@MainActor
final class RewindModel: ObservableObject {

    /// Frame-image zoom bounds. 1 is fit-to-window.
    static let minimumImageZoom: CGFloat = 1
    static let maximumImageZoom: CGFloat = 4

    /// Assumed spacing between scroll events when the real one cannot be used — the 120 Hz a trackpad
    /// delivers on this hardware.
    private static let nominalEventInterval: Double = 1.0 / 120

    /// A longer pause than this between two scroll events makes them two gestures rather than one
    /// fast one, and the second must not inherit the first's speed.
    private static let velocityGapLimit: Double = 0.2

    /// How much of each new sample the smoothed velocity takes. One stray event must not define the
    /// whole flick, and five events reach ~88% of the true rate, which is well inside one gesture.
    private static let velocitySmoothing: Double = 0.35

    /// The settle's tick rate, matching the 120 Hz the display and the trackpad both run at here.
    private static let glideTickInterval: Double = 1.0 / 120

    private let store: ContextStore
    let loader = FrameLoader()

    /// The day currently loaded, as its local midnight.
    @Published private(set) var day: Date
    /// Every showable frame in `day`, ascending. The array the track binary-searches.
    @Published private(set) var frames: [RewindFrame] = []
    /// The day's shape, from `Queries.activity` — run-length-collapsed stretches of one app.
    @Published private(set) var blocks: [ActivityBlock] = []
    /// **Where the playhead actually is**, in Unix epoch seconds, at whatever fraction of a second
    /// the gesture put it. The track draws its handle here, and the dissolve is a function of it.
    @Published private(set) var playheadAt: Double?

    /// The capture nearest `playheadAt`, which is the frame the timestamp, the border colour, Live
    /// Text and the segment chevrons all speak for. Derived, never set on its own.
    @Published private(set) var playhead: Int?

    /// The leftmost instant the track shows, and how many seconds of it are visible.
    @Published private(set) var trackStart: Double = 0
    @Published private(set) var trackSpan: Double = RewindZoom.maximumSpan

    @Published var imageZoom: CGFloat = 1

    /// The decoded picture the stage draws underneath, or nil while it is being decoded.
    @Published private(set) var image: NSImage?

    /// The next real capture, drawn over `image` at `blendWeight`, or nil when there is no dissolve.
    ///
    /// Both are genuine decoded captures. The weight comes straight from the playhead's position
    /// between them rather than from an animation with a duration of its own — which is what makes a
    /// fast scrub keep up with the pointer instead of trailing a fixed number of milliseconds behind
    /// it. See `RewindScrub`.
    @Published private(set) var blendImage: NSImage?
    @Published private(set) var blendWeight: Double = 0

    /// Live Text state. `nil` means no pass has run on this frame — which is precisely what makes the
    /// control dim, per the spec.
    @Published private(set) var liveText: LiveTextResult?
    @Published private(set) var isRecognizing = false
    @Published var showsLiveText = false

    /// The span the date picker may travel over, from the database.
    @Published private(set) var coverage: ClosedRange<Double>?

    /// Set when a day could not be read at all, so the window can say so instead of looking empty.
    @Published private(set) var loadError: String?

    /// True once a day has actually been read — i.e. `reload()` has run at least once.
    ///
    /// Not cosmetic: it is what tells `focus(on:)` whether the window is far enough along to be moved
    /// somewhere, or whether the instant has to wait for the first read (see `pendingFocus`).
    private(set) var hasLoaded = false

    /// An instant the window was asked to open at *before* it had read anything.
    ///
    /// The two entry points arrive in opposite orders. A timeline that is already up can be moved
    /// immediately; a timeline being opened *at* a moment is asked before its view exists, and
    /// `loadInitial()` — which runs from `RewindView.onAppear`, after `present(…)` has returned —
    /// picks the day itself. Scrubbing at request time would therefore be silently undone a moment
    /// later by the opening read. Holding the instant until that read consumes it is the only
    /// ordering that is correct for both.
    private var pendingFocus: Double?

    /// How fast the playhead is being driven, in timeline-seconds per second of wall clock, smoothed
    /// across the events of one gesture. Read once, when the fingers lift, to decide how far the
    /// scrub coasts.
    private var velocity: Double = 0
    private var lastTravelAt: Double?

    /// The direction of the last movement — +1 forward, −1 back, 0 at rest — which is what aims the
    /// prefetch window at the captures the playhead is heading for rather than the ones behind it.
    private(set) var scrubDirection = 0

    /// The settle in progress, or nil when the playhead is not moving on its own.
    private(set) var glide: RewindGlide?
    private var glideStartedAt: Double = 0
    private var glideTimer: Timer?

    /// Monotonic time, in seconds. Injectable because everything the coast and the settle do is a
    /// function of elapsed time, and a test that proved either by sleeping would be a test that fails
    /// on a loaded machine.
    var clock: () -> Double = { CACurrentMediaTime() }

    init(store: ContextStore, day: Date = Date()) {
        self.store = store
        self.day = Calendar.current.startOfDay(for: day)
        // One subscription rather than a completion per request. A decode that lands does not tell
        // the stage what to draw — the playhead may have moved while it ran, and with a dissolve the
        // two pictures' roles can have swapped — so the only correct response to *any* arrival is to
        // re-ask what the playhead needs now. `refreshImage` publishes nothing when the answer has
        // not changed, so a decode the stage does not care about costs three comparisons.
        loader.onDecode = { [weak self] in self?.refreshImage() }
    }

    // MARK: - Loading

    /// Reads the coverage window, then loads the newest day that actually holds frames.
    ///
    /// Opening on "today" would show an empty window every morning before the first capture, and on a
    /// machine that has not run for a week it would show an empty window indefinitely. The newest day
    /// with data is the only opening state that is never empty when the database is not.
    ///
    /// Unless the window was opened *at* a moment, in which case that moment's day is the one to
    /// read: a search result from last week that opened today's timeline would be the feature not
    /// working at all.
    func loadInitial() {
        coverage = (try? RewindQueries.coverage(store)) ?? nil
        if let pending = pendingFocus {
            day = Self.day(containing: pending)
        } else if let newest = coverage?.upperBound {
            day = Calendar.current.startOfDay(for: Date(timeIntervalSince1970: newest))
        }
        AppIconCache.shared.setBundleIds((try? RewindQueries.bundleIdsByApp(store)) ?? [:])
        reload()
        if let pending = pendingFocus {
            pendingFocus = nil
            park(at: pending)
        }
    }

    /// Loads `day`, resets the track to span it, and parks the playhead on the newest frame.
    func load(day newDay: Date) {
        let normalised = Calendar.current.startOfDay(for: newDay)
        guard normalised != day else { return }
        day = normalised
        loader.purge()
        reload()
    }

    private func reload() {
        let bounds = dayBounds
        do {
            frames = try RewindQueries.frames(store, since: bounds.start, until: bounds.end)
            // Segments come from the existing activity query rather than a second implementation.
            // It run-length-collapses consecutive same-app frames, splits on a gap longer than two
            // minutes, and drops stretches under fifteen seconds — which is the day's shape, already
            // tested, and it counts image-less frames the frame array cannot show.
            blocks = try Queries.activity(store, since: bounds.start, until: bounds.end)
            loadError = nil
        } catch {
            frames = []
            blocks = []
            loadError = "Could not read this day: \(error.localizedDescription)"
        }

        // A day change is the end of every gesture that was in flight over the old one: a settle
        // still ticking towards yesterday's capture would land the playhead on an index that now
        // means a different moment entirely.
        endGlide()
        velocity = 0
        lastTravelAt = nil
        scrubDirection = 0

        liveText = nil
        showsLiveText = false
        imageZoom = 1
        playhead = frames.isEmpty ? nil : frames.count - 1
        playheadAt = frames.last?.capturedAt
        resetTrackWindow()
        refreshImage()
        // Last, and only here: this is the single place a day is actually read, so it is the single
        // place that can honestly say one has been.
        hasLoaded = true
    }

    /// The local day an instant belongs to, as its midnight.
    ///
    /// **The one statement of the instant→day rule**, so the window, the model and the tests cannot
    /// each hold their own. `nonisolated` with an injectable calendar because it is arithmetic, not
    /// state: a test can ask what day 23:59 belongs to without a store, a window or a wall clock.
    /// `Calendar` rather than dividing by 86,400 — a day is 23, 24 or 25 hours depending on what the
    /// clocks did, and a result from the hour either side of a DST change would land on the wrong
    /// day for exactly the users least able to explain why.
    nonisolated static func day(containing instant: Double, calendar: Calendar = .current) -> Date {
        calendar.startOfDay(for: Date(timeIntervalSince1970: instant))
    }

    /// The loaded day's local start and end instants.
    private var dayBounds: (start: Double, end: Double) {
        let start = day.timeIntervalSince1970
        let end = Calendar.current.date(byAdding: .day, value: 1, to: day)?.timeIntervalSince1970
            ?? start + 86_400
        // Half-open at the end so the last second of a day cannot also belong to the next one.
        return (start, end - 0.001)
    }

    // MARK: - Playhead

    /// The frame under the playhead, if any.
    var currentFrame: RewindFrame? {
        guard let playhead, frames.indices.contains(playhead) else { return nil }
        return frames[playhead]
    }

    /// The activity block the playhead sits inside, which keys the frame's border colour.
    ///
    /// Nil is an ordinary outcome, not an error: `Queries.activity` drops stretches under fifteen
    /// seconds and splits on gaps, so a frame can legitimately belong to no block. The border falls
    /// back to a neutral hairline rather than inventing a colour.
    var currentBlock: ActivityBlock? {
        guard let at = currentFrame?.capturedAt else { return nil }
        return blocks.first { at >= $0.startedAt && at <= $0.endedAt }
    }

    /// **Go to a moment**, wherever in the capture it is. The seam a search result travels through.
    ///
    /// Distinct from `park(at:)` and `scrub(to:)` in exactly one way, and it is the way that matters:
    /// both of those move the playhead *within the loaded day* — they resolve an instant against
    /// `frames`, which for an instant belonging to another day is the first or the last frame of this
    /// one. So a result from last Tuesday handed to either lands on midnight of whatever day is open,
    /// and looks for all the world like the timeline ignoring the click. This loads the right day
    /// first, and then parks on a capture rather than between two, because a card names a moment and
    /// there is no gesture here to settle one.
    ///
    /// Loading is a no-op when the day is already open (`load(day:)` guards on it), so activating two
    /// results from the same afternoon does not re-read the day between them.
    ///
    /// A day with speech but no frames is a real outcome and stays honest rather than being
    /// corrected: the day loads, the playhead has nothing to sit on, and the stage says nothing was
    /// captured. Jumping to the nearest *other* day's picture would be a confident wrong answer about
    /// what the user asked to see.
    func focus(on instant: Double) {
        guard hasLoaded else {
            pendingFocus = instant
            return
        }
        load(day: Self.day(containing: instant))
        park(at: instant)
    }

    /// Moves the playhead to **exactly** `instant`, wherever between two captures that falls. The
    /// pointer's entry point: this is where the finger is, not where a capture is.
    ///
    /// Distinct from `park(at:)`, and the distinction is the reason both exist. A drag owns the
    /// playhead continuously and ends with `endScrub()`, which settles it onto a real capture.
    /// Anything arriving from *outside* the track — a search result, a segment chevron, a pinch —
    /// names a moment rather than a position, has no gesture to end, and would otherwise leave the
    /// stage holding a half-finished dissolve that nobody is driving.
    func scrub(to instant: Double) {
        endGlide()
        velocity = 0
        lastTravelAt = nil
        setPlayheadInstant(instant)
    }

    /// Moves the playhead onto the **capture** nearest `instant`, with no dissolve left showing.
    func park(at instant: Double) {
        guard let index = frames.nearestIndex(to: instant) else { return }
        setPlayhead(index)
    }

    func setPlayhead(_ index: Int) {
        guard frames.indices.contains(index) else { return }
        endGlide()
        velocity = 0
        lastTravelAt = nil
        setPlayheadInstant(frames[index].capturedAt)
    }

    func step(_ delta: Int) {
        guard let playhead else { return }
        setPlayhead(min(max(0, playhead + delta), frames.count - 1))
    }

    /// **The one place the playhead moves.** Everything above lands here.
    ///
    /// Clamped to the captured range rather than to the day: the track shows midnight to midnight,
    /// but travelling into the empty hours before the first capture would move the handle over blank
    /// track while the picture stayed frozen, which reads as the scroll having broken.
    private func setPlayheadInstant(_ instant: Double) {
        guard let first = frames.first?.capturedAt, let last = frames.last?.capturedAt else {
            playheadAt = nil
            playhead = nil
            refreshImage()
            return
        }
        let clamped = min(max(first, instant), last)
        guard let index = frames.nearestIndex(to: clamped) else { return }
        // Sub-frame moves are not no-ops any more — the dissolve is a function of the fraction — so
        // the guard is on the position, not on the index.
        guard clamped != playheadAt || index != playhead else { return }

        if let previous = playheadAt, clamped != previous {
            scrubDirection = clamped > previous ? 1 : -1
        }
        let frameChanged = index != playhead
        playheadAt = clamped
        playhead = index

        if frameChanged {
            // A new frame invalidates the old boxes. Clearing rather than keeping them is the point:
            // a stale highlight layer over a different screenshot is the fake-highlight failure by
            // another route.
            liveText = nil
        }
        refreshImage()
        keepPlayheadVisible()
        if frameChanged, showsLiveText { recognizeLiveText() }
    }

    // MARK: - The end of a gesture

    /// **The fingers left the track.** Coast the last of the flick's speed, then come to rest on a
    /// real capture.
    ///
    /// Called for a released drag, for a scroll whose inertia has run out, and for every notch of a
    /// wheel mouse — see `RewindTrackView.handleScroll`. Landing on a capture is not cosmetic: it is
    /// what keeps the stage at rest a photograph rather than a permanent 50/50 composite of two
    /// screens, which is the one thing a dissolve must never be allowed to become. See `RewindGlide`.
    func endScrub() {
        endGlide()
        guard let at = playheadAt, !frames.isEmpty else { return }

        let rest = RewindGlide.projectedRest(from: at, velocity: velocity)
        velocity = 0
        lastTravelAt = nil

        guard let index = frames.nearestIndex(to: rest) else { return }
        let target = frames[index].capturedAt
        guard let glide = RewindGlide(from: at, to: target, visibleSpan: trackSpan) else {
            // Already there, to within a rounding error. Animating nothing would still cost a timer.
            setPlayheadInstant(target)
            return
        }
        startGlide(glide)
    }

    var isSettling: Bool { glide != nil }

    private func startGlide(_ glide: RewindGlide) {
        endGlide()
        self.glide = glide
        glideStartedAt = clock()
        let timer = Timer(timeInterval: Self.glideTickInterval, repeats: true) { [weak self] timer in
            // The timer fires on the run loop that scheduled it, which is the main one.
            MainActor.assumeIsolated {
                guard let self else {
                    // Self-cancelling rather than leaning on a `deinit` that cannot run while the
                    // run loop holds a reference: a window torn down mid-settle must not leave a
                    // timer firing for the life of the process.
                    timer.invalidate()
                    return
                }
                self.tickGlide()
            }
        }
        // `.common` so the settle keeps running while the run loop is in a tracking mode — which it
        // is for the whole of the mouse-up that starts it.
        RunLoop.main.add(timer, forMode: .common)
        glideTimer = timer
    }

    /// One step of the settle, and **the seam the tests drive**. Internal rather than private for
    /// that reason: a timer-driven ease asserted by sleeping is a flaky test, and this is the
    /// arithmetic the timer itself runs, called the same way.
    func tickGlide() {
        guard let glide else { return }
        let elapsed = clock() - glideStartedAt
        if glide.isFinished(atElapsed: elapsed) {
            endGlide()
            // Landed *exactly* on the capture rather than a rounding error short of it, so what is on
            // the stage at rest is one real photograph at full weight and not a 99/1 composite.
            setPlayheadInstant(glide.to)
            return
        }
        setPlayheadInstant(glide.instant(atElapsed: elapsed))
    }

    private func endGlide() {
        glideTimer?.invalidate()
        glideTimer = nil
        glide = nil
    }

    // MARK: - Segment navigation

    /// The chevrons on the frame's edges: jump to the previous or next activity block.
    ///
    /// Jumps to the block's **first frame** rather than to its start instant, because a block's
    /// boundary can fall in a gap where no frame exists and landing there would show whichever frame
    /// happened to be nearest, which reads as the chevron overshooting.
    func goToAdjacentSegment(forward: Bool) {
        guard let at = currentFrame?.capturedAt else { return }
        let candidates = forward
            ? blocks.filter { $0.startedAt > at }.map(\.startedAt)
            : blocks.filter { $0.endedAt < at }.map(\.startedAt).reversed().map { $0 }
        guard let target = candidates.first else { return }
        park(at: target)
    }

    var hasPreviousSegment: Bool {
        guard let at = currentFrame?.capturedAt else { return false }
        return blocks.contains { $0.endedAt < at }
    }

    var hasNextSegment: Bool {
        guard let at = currentFrame?.capturedAt else { return false }
        return blocks.contains { $0.startedAt > at }
    }

    // MARK: - Track window (the *track* zoom)

    private func resetTrackWindow() {
        let bounds = dayBounds
        trackStart = bounds.start
        trackSpan = min(RewindZoom.maximumSpan, bounds.end - bounds.start)
    }

    var trackEnd: Double { trackStart + trackSpan }

    /// The window the track is currently showing, in the shape the zoom arithmetic speaks.
    var trackWindow: RewindZoom.Window { RewindZoom.Window(start: trackStart, span: trackSpan) }

    /// The range the track's span may move within, given the day that is loaded.
    ///
    /// Computed rather than constant because the ceiling is the day itself, and a day is 23, 24 or 25
    /// hours depending on what the clocks did. Both ends are derived so the range is always
    /// well-formed: a `ClosedRange` built with its bounds the wrong way round traps rather than
    /// misbehaving, and the zoom bounds are exactly the place a degenerate day would produce one.
    var trackSpanBounds: ClosedRange<Double> {
        let bounds = dayBounds
        let upper = max(1, min(RewindZoom.maximumSpan, bounds.end - bounds.start))
        return min(RewindZoom.minimumSpan, upper)...upper
    }

    /// **The one place the visible window changes after a day is loaded.** Both zoom drivers land
    /// here, which is what stops the buttons and a pinch from disagreeing: there is nowhere else for
    /// them to disagree.
    ///
    /// The second half is what makes zoom compose with scrolling instead of fighting it. Scrolling the
    /// track moves the *playhead* (see `travel(by:)`) and the window follows the playhead, so a zoom
    /// that left the playhead outside the visible window would be undone by the very next scroll —
    /// the track would snap back to wherever the picture was and the stretch the user had just zoomed
    /// in on would vanish. Moving the playhead to the anchored moment instead makes the next scroll
    /// continue from where the fingers were, and shows the frame from the stretch being looked at
    /// rather than one from somewhere else in the day. It lands on the nearest capture to the anchor,
    /// which is inside the new window whenever that window contains any capture at all — zoom into a
    /// gap far enough and there is no frame in view to land on, and `keepPlayheadVisible` then pulls
    /// the window back to the nearest real one.
    ///
    /// It never fires for the buttons: their anchor *is* the playhead, and an anchor always lands
    /// inside the window this produces.
    func setTrackWindow(_ target: RewindZoom.Target) {
        let bounds = dayBounds
        let window = RewindZoom.window(
            for: target,
            spanBounds: trackSpanBounds,
            within: bounds.start...bounds.end)
        trackStart = window.start
        trackSpan = window.span

        // Tested against the playhead's own position rather than its frame's, so that the one caller
        // that centres the playhead here (`keepPlayheadVisible`) can never satisfy this and recurse:
        // a window centred on `playheadAt` always contains `playheadAt`. Using the *frame's* instant
        // left a sliver — up to half a capture interval — where the two disagreed, and a settle that
        // crossed it would have been cancelled halfway by the pan meant to keep it in view.
        if let at = playheadAt, at < window.start || at > window.end {
            park(at: target.anchor)
        }
    }

    /// Halves or doubles the visible span, anchored on the playhead so the frame being looked at
    /// stays put. What the two magnifier buttons in the control cluster do.
    func zoomTrack(in zoomIn: Bool) {
        let anchor = playheadAt ?? (trackStart + trackSpan / 2)
        // The anchor keeps the fractional position it already has, which is what makes repeated
        // presses feel like zooming on the frame rather than drifting away from it.
        setTrackWindow(
            RewindZoom.Target(
                span: trackSpan * (zoomIn ? 0.5 : 2),
                anchor: anchor,
                fraction: RewindZoom.fraction(of: anchor, in: trackWindow)))
    }

    var canZoomTrackIn: Bool { trackSpan > trackSpanBounds.lowerBound }
    var canZoomTrackOut: Bool { trackSpan < trackSpanBounds.upperBound }

    /// Travels through the day by `seconds`, which is what a scroll on the track means. Positive is
    /// forward in time.
    ///
    /// It moves the **playhead**, and that is the substantive fix. This used to pan the visible
    /// window instead — `trackStart += seconds`, then clamp it back inside the day — and at the zoom
    /// the window opens on, that is arithmetically a no-op: `resetTrackWindow` sets `trackSpan` to the
    /// whole loaded day, so the clamp's own bound `bounds.end - trackSpan` *is* `bounds.start` and
    /// `trackStart` cannot move by any number of seconds. Every scroll on a freshly opened timeline
    /// resolved to nothing at all, which is exactly what "the two finger dragging didn't work" looks
    /// like from the outside. Moving the playhead is also what the tutorial's card promises — you
    /// travel through your day — and it is visible, because the picture changes.
    ///
    /// The visible window still follows: every playhead move calls `keepPlayheadVisible()`, which
    /// pans it when the playhead would leave, so a zoomed-in track scrolls as it always did.
    ///
    /// **It travels from where the playhead is, not from the frame it is nearest**, and that is the
    /// second substantive fix. Re-deriving the base from the snapped frame each time meant a delta
    /// smaller than half a capture interval rounded straight back to its own starting point: it did
    /// not move the playhead a little, it moved it not at all, and nothing accumulated across events.
    /// Zoomed in to the two-minute floor, one ordinary trackpad event is about a second of timeline
    /// against a 1.5 s rounding threshold — so *scrolling did nothing whatsoever* at the zoom where
    /// precision is the entire point, and a momentum tail, whose deltas decay towards zero, could
    /// never do anything at any zoom. Seconds now land where they are aimed.
    ///
    /// How far a scroll travels is proportional to `trackSpan` (`RewindTrackView.handleScroll` does
    /// the pixels-to-seconds conversion), so zooming in is what makes the control finer — and now
    /// that fine deltas survive, that is finally true rather than merely intended.
    func travel(by seconds: Double) {
        guard let at = playheadAt else { return }
        endGlide()
        recordVelocity(seconds)
        setPlayheadInstant(at + seconds)
    }

    /// Folds one scroll event into the smoothed speed the coast is computed from.
    ///
    /// The first event of a gesture has no elapsed time to divide by, so it has no measurable speed,
    /// and zero is the honest answer rather than a guess scaled by an assumed frame rate. It costs
    /// nothing: a flick is many events, and by the time the fingers lift the smoothing has seen all
    /// of them. It is also what stops a single wheel-mouse notch — one event, no gesture — from
    /// coasting somewhere the user did not ask for.
    private func recordVelocity(_ seconds: Double) {
        let now = clock()
        let previous = lastTravelAt
        lastTravelAt = now
        guard let previous else {
            velocity = 0
            return
        }
        let gap = now - previous
        // A longer pause than this is a new gesture; it must not inherit the old one's speed.
        guard gap > 0, gap <= Self.velocityGapLimit else {
            velocity = 0
            return
        }
        let sample = seconds / max(gap, Self.nominalEventInterval)
        velocity = velocity * (1 - Self.velocitySmoothing) + sample * Self.velocitySmoothing
    }

    /// Nudges the window so the playhead stays on screen after a jump.
    ///
    /// Expressed as a re-span to the span it already has, anchored on the playhead at the middle of
    /// the track, so the day clamp is stated once — in `RewindZoom` — rather than once here and once
    /// in the zoom. The recursion this looks like it might cause terminates immediately: the window
    /// it asks for is centred on the playhead, and `setTrackWindow` only moves the playhead when the
    /// playhead is *outside* the window it produced.
    private func keepPlayheadVisible() {
        guard let at = playheadAt, at < trackStart || at > trackEnd else { return }
        setTrackWindow(RewindZoom.Target(span: trackSpan, anchor: at, fraction: 0.5))
    }

    // MARK: - Frame image (the *image* zoom)

    func zoomImage(in zoomIn: Bool) {
        let factor: CGFloat = zoomIn ? 1.25 : 1 / 1.25
        imageZoom = min(Self.maximumImageZoom, max(Self.minimumImageZoom, imageZoom * factor))
    }

    /// Where the playhead sits between two real captures, and how far the dissolve between them has
    /// travelled. Nil only when the day holds nothing showable.
    var currentBlend: RewindScrub.Blend? {
        guard let playheadAt else { return nil }
        return RewindScrub.blend(at: playheadAt, in: frames)
    }

    private func refreshImage() {
        guard let blend = currentBlend else {
            image = nil
            blendImage = nil
            blendWeight = 0
            return
        }
        let baseFrame = frames[blend.base]
        let nextFrame = blend.next.map { frames[$0] }

        // Both read through the cache, so both count as recently used: the two captures being
        // dissolved are exactly the two that must survive eviction, and `FrameMemoryCache` orders by
        // read. A cached hit paints in the same turn of the run loop, so a scrub through
        // already-decoded frames never shows a gap.
        let baseImage = loader.cached(baseFrame)
        let nextImage = nextFrame.flatMap { loader.cached($0) }
        let layers = RewindScrub.layers(
            for: blend, baseIsDecoded: baseImage != nil, nextIsDecoded: nextImage != nil)

        let drawnImage: NSImage?
        if let drawn = layers.base {
            drawnImage = drawn == blend.base ? baseImage : nextImage
        } else if loader.hasFailed(baseFrame) {
            drawnImage = nil
        } else {
            // The picture already on the stage stays there while the decode runs. Deliberately *not*
            // cleared to nil: holding the previous frame for the few milliseconds a decode takes
            // reads as a smooth scrub, where blanking to empty and back is a flicker on every step.
            drawnImage = image
        }
        let drawnOver = layers.over.flatMap { $0 == blend.base ? baseImage : nextImage }
        let drawnWeight = drawnOver == nil ? 0 : layers.weight

        // Assigned only when they actually differ. `refreshImage` runs on every pointer move *and*
        // on every decode that lands anywhere in the prefetch window — several hundred a second
        // during a fast scrub — and a `@Published` write is an invalidation whether or not it changed
        // anything. Comparing three values is far cheaper than the render it saves.
        if image !== drawnImage { image = drawnImage }
        if blendImage !== drawnOver { blendImage = drawnOver }
        if blendWeight != drawnWeight { blendWeight = drawnWeight }

        // Uncapped, unlike the prefetch below: these two are what the stage is drawing *now*, and a
        // speculative-decode limit must never be allowed to hold them up.
        loader.load(baseFrame)
        if let nextFrame { loader.load(nextFrame) }
        prefetchAroundPlayhead()
    }

    private func prefetchAroundPlayhead() {
        guard let playhead,
            let window = RewindScrub.prefetchWindow(
                around: playhead, direction: scrubDirection, count: frames.count)
        else { return }
        loader.prefetch(Array(frames[window]))
    }

    /// True when the playhead frame's image could not be decoded — a file retention removed, or a
    /// truncated write. Distinct from "still decoding", which shows nothing rather than a message.
    var imageIsMissing: Bool {
        guard let frame = currentFrame else { return false }
        return loader.hasFailed(frame)
    }

    // MARK: - Live Text

    func toggleLiveText() {
        showsLiveText.toggle()
        if showsLiveText, liveText == nil { recognizeLiveText() }
    }

    private func recognizeLiveText() {
        guard let frame = currentFrame, !isRecognizing else { return }
        isRecognizing = true
        let wanted = frame.id
        let path = frame.imagePath
        Task { [weak self] in
            let result = await LiveTextRecognizer.recognize(path: path)
            guard let self else { return }
            self.isRecognizing = false
            // The playhead may have moved while Vision ran; boxes measured on another frame must
            // never be drawn over this one.
            guard self.currentFrame?.id == wanted else { return }
            self.liveText = result ?? LiveTextResult(imageSize: .zero, blocks: [])
        }
    }

    /// Whether the Live Text control should read as available.
    ///
    /// Dim until a pass has produced something, which is the spec's "dims when no text has been
    /// detected yet" read literally: before a pass runs nothing *has* been detected, and after one
    /// that found nothing there is still nothing to show.
    var liveTextIsAvailable: Bool {
        guard let liveText else { return false }
        return !liveText.isEmpty
    }

    // MARK: - Display strings

    /// The date/time pill, e.g. `Jul 29, 2026 at 10:21 PM`.
    var timestampLabel: String {
        guard let at = currentFrame?.capturedAt else {
            return RewindModel.pillFormatter.string(from: day)
        }
        return RewindModel.pillFormatter.string(from: Date(timeIntervalSince1970: at))
    }

    private static let pillFormatter: DateFormatter = {
        let formatter = DateFormatter()
        formatter.dateFormat = "MMM d, yyyy 'at' h:mm a"
        return formatter
    }()
}
