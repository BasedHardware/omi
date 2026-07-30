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
@MainActor
final class RewindModel: ObservableObject {

    /// Frames decoded ahead of the playhead in each direction.
    ///
    /// Five either side is ~30 seconds of capture at the 3 s tick, which is comfortably more than a
    /// drag covers between two frames being asked for, and eleven frames is a memory cost
    /// `FrameLoader.memoryBudgetBytes` is sized for.
    static let prefetchRadius = 5

    /// The narrowest and widest the track may be zoomed, in seconds.
    ///
    /// Two minutes is about forty frames — below that the track is mostly one segment and the zoom
    /// has nothing left to reveal. The ceiling is a full day, because the track is bounded by the day
    /// that is loaded; going wider is what the date picker is for.
    static let minimumTrackSpan: Double = 120
    static let maximumTrackSpan: Double = 24 * 3600

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
    @Published private(set) var trackSpan: Double = RewindModel.maximumTrackSpan

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
    func loadInitial() {
        coverage = (try? RewindQueries.coverage(store)) ?? nil
        if let newest = coverage?.upperBound {
            day = Calendar.current.startOfDay(for: Date(timeIntervalSince1970: newest))
        }
        AppIconCache.shared.setBundleIds((try? RewindQueries.bundleIdsByApp(store)) ?? [:])
        reload()
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
        trackSpan = min(Self.maximumTrackSpan, bounds.end - bounds.start)
    }

    var trackEnd: Double { trackStart + trackSpan }

    /// Halves or doubles the visible span, anchored on the playhead so the frame being looked at
    /// stays put under the cursor.
    func zoomTrack(in zoomIn: Bool) {
        let anchor = currentFrame?.capturedAt ?? (trackStart + trackSpan / 2)
        let factor: Double = zoomIn ? 0.5 : 2
        let span = min(Self.maximumTrackSpan, max(Self.minimumTrackSpan, trackSpan * factor))
        // The anchor keeps its fractional position in the window, which is what makes repeated
        // zooming feel like it is zooming on the frame rather than drifting away from it.
        let fraction = trackSpan > 0 ? (anchor - trackStart) / trackSpan : 0.5
        trackSpan = span
        trackStart = anchor - fraction * span
        clampTrackWindow()
    }

    var canZoomTrackIn: Bool { trackSpan > Self.minimumTrackSpan }
    var canZoomTrackOut: Bool { trackSpan < min(Self.maximumTrackSpan, dayBounds.end - dayBounds.start) }

    /// Scrolls the visible window. Positive `seconds` moves forward in time.
    func panTrack(by seconds: Double) {
        trackStart += seconds
        clampTrackWindow()
    }

    /// Keeps the window inside the loaded day, so the track can never show a stretch of time the
    /// loaded frames could not possibly cover.
    private func clampTrackWindow() {
        let bounds = dayBounds
        let dayLength = bounds.end - bounds.start
        trackSpan = min(trackSpan, dayLength)
        trackStart = min(max(bounds.start, trackStart), bounds.end - trackSpan)
    }

    /// Nudges the window so the playhead stays on screen after a jump.
    private func keepPlayheadVisible() {
        guard let at = currentFrame?.capturedAt else { return }
        if at < trackStart || at > trackEnd {
            trackStart = at - trackSpan / 2
            clampTrackWindow()
        }
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
