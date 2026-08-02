import AppKit
import ContextCore
import SwiftUI

/// Everything the timeline window knows: which day is loaded, where the playhead sits, how wide the
/// track's visible window is, and what has been decoded.
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

    /// Frames decoded ahead of the playhead in each direction.
    ///
    /// Five either side is ~30 seconds of capture at the 3 s tick, which is comfortably more than a
    /// drag covers between two frames being asked for, and eleven frames is a memory cost
    /// `FrameLoader.memoryBudgetBytes` is sized for.
    static let prefetchRadius = 5

    /// Frame-image zoom bounds. 1 is fit-to-window.
    static let minimumImageZoom: CGFloat = 1
    static let maximumImageZoom: CGFloat = 4

    private let store: ContextStore
    let loader = FrameLoader()

    /// The day currently loaded, as its local midnight.
    @Published private(set) var day: Date
    /// Every showable frame in `day`, ascending. The array the track binary-searches.
    @Published private(set) var frames: [RewindFrame] = []
    /// The day's shape, from `Queries.activity` — run-length-collapsed stretches of one app.
    @Published private(set) var blocks: [ActivityBlock] = []
    /// Index into `frames`. Nil only when the day holds nothing showable.
    @Published private(set) var playhead: Int?

    /// The leftmost instant the track shows, and how many seconds of it are visible.
    @Published private(set) var trackStart: Double = 0
    @Published private(set) var trackSpan: Double = RewindZoom.maximumSpan

    @Published var imageZoom: CGFloat = 1

    /// The decoded picture for the playhead frame, or nil while it is being decoded.
    @Published private(set) var image: NSImage?

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

    init(store: ContextStore, day: Date = Date()) {
        self.store = store
        self.day = Calendar.current.startOfDay(for: day)
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
            scrub(to: pending)
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

        liveText = nil
        showsLiveText = false
        imageZoom = 1
        playhead = frames.isEmpty ? nil : frames.count - 1
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
    /// Distinct from `scrub(to:)` in exactly one way, and it is the way that matters: `scrub` moves
    /// the playhead *within the loaded day* — it maps an instant onto the nearest frame in `frames`,
    /// which for an instant belonging to another day is the first or the last frame of this one. So
    /// a result from last Tuesday handed to `scrub` lands on midnight of whatever day is open, and
    /// looks for all the world like the timeline ignoring the click. This loads the right day first.
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
        scrub(to: instant)
    }

    /// Moves the playhead to the frame nearest `instant`. The scrub entry point.
    func scrub(to instant: Double) {
        guard let index = frames.nearestIndex(to: instant) else { return }
        setPlayhead(index)
    }

    func setPlayhead(_ index: Int) {
        guard frames.indices.contains(index), index != playhead else { return }
        playhead = index
        // A new frame invalidates the old boxes. Clearing rather than keeping them is the point: a
        // stale highlight layer over a different screenshot is the fake-highlight failure by another
        // route.
        liveText = nil
        refreshImage()
        keepPlayheadVisible()
        if showsLiveText { recognizeLiveText() }
    }

    func step(_ delta: Int) {
        guard let playhead else { return }
        setPlayhead(min(max(0, playhead + delta), frames.count - 1))
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
        scrub(to: target)
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

        if let at = currentFrame?.capturedAt, at < window.start || at > window.end {
            scrub(to: target.anchor)
        }
    }

    /// Halves or doubles the visible span, anchored on the playhead so the frame being looked at
    /// stays put. What the two magnifier buttons in the control cluster do.
    func zoomTrack(in zoomIn: Bool) {
        let anchor = currentFrame?.capturedAt ?? (trackStart + trackSpan / 2)
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
    /// The visible window still follows: `setPlayhead` calls `keepPlayheadVisible()`, which pans it
    /// when the playhead would leave, so a zoomed-in track scrolls as it always did.
    func travel(by seconds: Double) {
        guard let at = currentFrame?.capturedAt else { return }
        scrub(to: at + seconds)
    }

    /// Nudges the window so the playhead stays on screen after a jump.
    ///
    /// Expressed as a re-span to the span it already has, anchored on the playhead at the middle of
    /// the track, so the day clamp is stated once — in `RewindZoom` — rather than once here and once
    /// in the zoom. The recursion this looks like it might cause terminates immediately: the window
    /// it asks for is centred on the playhead, and `setTrackWindow` only moves the playhead when the
    /// playhead is *outside* the window it produced.
    private func keepPlayheadVisible() {
        guard let at = currentFrame?.capturedAt, at < trackStart || at > trackEnd else { return }
        setTrackWindow(RewindZoom.Target(span: trackSpan, anchor: at, fraction: 0.5))
    }

    // MARK: - Frame image (the *image* zoom)

    func zoomImage(in zoomIn: Bool) {
        let factor: CGFloat = zoomIn ? 1.25 : 1 / 1.25
        imageZoom = min(Self.maximumImageZoom, max(Self.minimumImageZoom, imageZoom * factor))
    }

    private func refreshImage() {
        guard let frame = currentFrame else {
            image = nil
            return
        }
        // Cached hit paints in the same turn of the run loop, so a scrub through already-decoded
        // frames never shows a gap.
        if let cached = loader.cached(frame) {
            image = cached
        } else if loader.hasFailed(frame) {
            image = nil
        } else {
            // Deliberately *not* cleared to nil while decoding: holding the previous frame for the
            // few milliseconds a decode takes reads as a smooth scrub, where blanking to empty and
            // back reads as a flicker on every step.
            let wanted = frame.id
            loader.load(frame) { [weak self] decoded in
                guard let self, self.currentFrame?.id == wanted else { return }
                self.image = decoded
            }
        }
        prefetchAroundPlayhead()
    }

    private func prefetchAroundPlayhead() {
        guard let playhead else { return }
        let low = max(0, playhead - Self.prefetchRadius)
        let high = min(frames.count - 1, playhead + Self.prefetchRadius)
        guard low <= high else { return }
        loader.prefetch(Array(frames[low...high]))
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
