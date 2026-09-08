import AppKit
import ContextCore
import ImageIO
import UniformTypeIdentifiers

/// Decodes stored frame images off the main thread and keeps the recent ones in memory.
///
/// This is the whole reason scrubbing is smooth here without any change to how frames are stored.
/// The app this was ported from packs frames into 60-second HEVC chunks, so showing one frame means
/// constructing an `AVAssetReader` over the chunk and walking samples forward to the offset, with an
/// `ffmpeg` subprocess as the fallback when that fails — hundreds of milliseconds and a process
/// spawn to move the playhead one notch. **None of that is ported.** Our capture already writes one
/// independent HEIC per frame (`ScreenPipeline.writeFrameImage`, at the longest side and quality the
/// user's `CaptureQuality` tile names — 1024…2400 px, applied in `FrameImage.encoded`), so a frame is
/// a single file that decodes on its own. There is no video path, no chunk index, and no subprocess
/// to go wrong.
///
/// Measured over 507 real frames sampled across the whole frames directory on this machine, at the
/// default tile, through exactly the options `decode` passes: **median 14.4 ms, p95 19.9 ms, min
/// 8.3 ms, max 38.5 ms** per decode, from files averaging 55.6 KB. Combined with the prefetch, a
/// scrub that stays inside the prefetched window is a cache hit and costs nothing; only a jump beyond
/// it pays a decode, and that decode is off the main thread.
///
/// Three rules make it feel instant:
///
/// - **Decode is never on the main thread.** A synchronous decode inside a SwiftUI body is a dropped
///   frame per scrub step; every load lands through `Task.detached` and publishes back on the main
///   actor.
/// - **The cache is charged real bytes.** Theirs sets a 100 MB `totalCostLimit` and then charges a
///   flat 4 MB per frame regardless of the image, so the budget silently means "about 25 frames"
///   whatever the frames are. The cost here is the decoded bitmap's actual size —
///   `bytesPerRow * height` — measured at **5.95 MB** on average across those same 507 frames, and
///   correspondingly less for a small one. The limit then means what it says, and it means it at
///   every Capture Quality tile rather than only the one it was measured at: 192 MB holds ~32 frames
///   at the default tile and ~14 at Best Quality, in both cases more than the 11 a prefetch window
///   touches. A flat per-frame charge would have made the budget silently untrue the moment the
///   tiles started moving the stored size.
/// - **Decodes in flight are capped.** See `maximumConcurrentDecodes`.
@MainActor
final class FrameLoader {

    /// Decoded-bitmap bytes held in memory. Sized against what a scrub actually touches: the playhead
    /// frame and its prefetch window are `RewindScrub.prefetchWindowWidth` — eleven — images.
    ///
    /// **The frame size is the user's, so this budget has to be read at the largest tile and not the
    /// default one.** At `CaptureQuality.standard` a decoded frame measures 5.95 MB, so the window is
    /// ~65 MB and 192 MB keeps roughly a further 20 frames of trail behind a moving playhead. At
    /// **Best Quality** — 2400 px, which `maxPixelSize` now genuinely decodes rather than squashing —
    /// a frame is 13.7 MB, the same eleven-image window is ~151 MB, and the trail shrinks to about
    /// three frames. That is the case this ceiling has to survive and it does: the window a scrub is
    /// actually inside stays resident at every tile, which is the property the dissolve depends on.
    /// Raising the ceiling would buy back trail at that tile only, and 192 MB pinned by a background
    /// app is already the larger cost.
    static let memoryBudgetBytes = 192 * 1024 * 1024

    /// How many frames may be decoding at once.
    ///
    /// The cap is not about the steady state, it is about a fast scrub at a wide zoom. There, one
    /// pointer move crosses dozens of captures, so every event names an entirely different prefetch
    /// window: uncapped, sixty events a second would each launch eleven decodes, and several hundred
    /// concurrent tasks saturate the cores the UI needs and queue several hundred main-actor hops
    /// behind them — a stutter caused by the very work that exists to prevent one. Four is ~60 ms of
    /// decode in flight at the measured 14.4 ms median, which stays comfortably ahead of a 3 s
    /// capture tick. Dropping a prefetch beyond the cap costs nothing: the next pointer move asks
    /// again, and the frame the playhead is actually on never goes through the cap at all.
    static let maximumConcurrentDecodes = 4

    /// Longest side requested from the decoder: **2400, deliberately larger than anything this app
    /// writes today.**
    ///
    /// It was the literal `1600`, documented as matching a capture constant that no longer exists;
    /// then it was derived from the Capture Quality tiles, taking the largest of the four,
    /// because on **Best Quality** every 2400 px frame was being re-sampled down to 1600 by the only
    /// UI that shows frames — the user paid for the pixels in disk and got them thrown away at the
    /// last step. The tiles are gone and capture now writes one size (`FrameImage.Quality`, 1600),
    /// so this is a literal again — but it is emphatically **not** `FrameImage.Quality.longestSide`.
    ///
    /// A frame on disk was written under whatever tile was selected when it was taken, and installs
    /// that ran on Best Quality have real 2400 px files. Tying this ceiling to what capture writes
    /// *now* would soften every one of those the day this shipped, which is the same defect as the
    /// original `1600` with a better-looking expression. The number is the widest frame this app has
    /// ever written and it can only move down when no such file can still exist.
    ///
    /// **Asking for more than the file holds costs nothing** — `kCGImageSourceThumbnailMaxPixelSize`
    /// is a ceiling and not a target, so a smaller stored frame comes back at its own size and is not
    /// interpolated up. (The comment this replaces claimed the opposite, which is what made the
    /// literal look safe.) Measured through exactly the options `decode` passes, on real HEIC files
    /// written at all four historical tile sizes: at cap 2400 the 1600/1280/1024 files decode to
    /// 1600×1000 (6.10 MB), 1280×800 (3.91 MB) and 1024×640 (2.50 MB) — byte-for-byte what they cost
    /// at cap 1600 — while a 2400 px file decodes to 2400×1500 instead of being squashed.
    ///
    /// What it does cost is memory on those legacy Best Quality frames alone, where a decoded frame
    /// is **13.7 MB** rather than 6.1 MB. `memoryBudgetBytes` still covers the window that matters:
    /// see its note.
    ///
    /// `nonisolated` because `decode` reads it on a detached task; a main-actor constant would be an
    /// error in the Swift 6 language mode.
    nonisolated static let maxPixelSize = 2400

    private var cache = FrameMemoryCache(budgetBytes: FrameLoader.memoryBudgetBytes)

    /// Frame ids with a decode in flight, so a scrub that passes over the same frame twice — or a
    /// prefetch that overlaps the playhead — does not start the work twice.
    private var inFlight: Set<Int64> = []

    /// Ids whose file could not be decoded. Remembered so a missing or corrupt image is attempted
    /// once rather than on every pass of the playhead: retrying forever would turn one bad file into
    /// a permanent stutter, and nothing about the file is going to change while the window is open.
    private var failed: Set<Int64> = []

    /// Frames the latest prefetch asked for and the cap has not reached yet.
    private var pendingPrefetch: [RewindFrame] = []

    /// Callers waiting on a decode that is already running, by frame id.
    ///
    /// **Without this there is a stall on exactly the frame you just scrubbed to.** A prefetch starts
    /// a decode with nothing to notify; the playhead then reaches that frame and asks for it; `load`
    /// sees the id already in flight, drops the new completion on the floor and returns. The decode
    /// lands in the cache a few milliseconds later and repaints nothing, so the stage keeps showing
    /// the *previous* picture until the user happens to move again. Joining the queue instead costs
    /// one array append.
    private var waiting: [Int64: [@MainActor (NSImage) -> Void]] = [:]

    /// Called after **any** decode lands, whoever asked for it.
    ///
    /// The timeline uses this instead of a per-request completion, because its question is "what
    /// should the stage be showing *now*" — which does not depend on which frame happened to arrive,
    /// and which it has to re-derive anyway since the playhead may have moved while the decode ran.
    /// A per-request completion would also compound: a completion that re-derives the stage asks for
    /// the next frame, whose completion re-derives it again, and the waiter lists grow with each
    /// hop. One broadcast cannot.
    var onDecode: (() -> Void)?

    /// The cached image for a frame, if it is already in memory. Never decodes — safe to call from a
    /// view body.
    ///
    /// Reading is what marks a frame recently used, which is exactly the property the dissolve needs:
    /// the two captures being blended are the two the stage read last, so they are the last two the
    /// cache would ever evict.
    func cached(_ frame: RewindFrame) -> NSImage? {
        cache.image(for: frame.id)
    }

    /// True when this frame has already failed to decode, so callers can show the reason rather than
    /// an indefinite spinner.
    func hasFailed(_ frame: RewindFrame) -> Bool { failed.contains(frame.id) }

    /// Decodes currently running. Bounded by `maximumConcurrentDecodes` for everything reached
    /// through `prefetch`; exposed so the cap is assertable rather than merely intended.
    var inFlightCount: Int { inFlight.count }

    /// Decoded bytes currently held. Never above `memoryBudgetBytes`.
    var heldBytes: Int { cache.bytes }

    /// Decodes `frame` unless it is cached or already known bad, and calls `completion` on the main
    /// actor when — and only when — an image was genuinely produced.
    ///
    /// A decode already in flight is joined rather than refused, so every caller that asked is told.
    /// `completion` is optional because a prefetch has nothing to be told: it only wants the work
    /// done, and registering a no-op per pointer move would build a list of them.
    func load(_ frame: RewindFrame, completion: (@MainActor (NSImage) -> Void)? = nil) {
        let id = frame.id
        if let image = cached(frame) {
            completion?(image)
            return
        }
        guard !failed.contains(id) else { return }
        if let completion { waiting[id, default: []].append(completion) }
        guard !inFlight.contains(id) else { return }
        inFlight.insert(id)

        let path = frame.imagePath
        Task.detached(priority: .userInitiated) {
            let decoded = FrameLoader.decode(path: path)
            await MainActor.run {
                self.inFlight.remove(id)
                let waiters = self.waiting.removeValue(forKey: id) ?? []
                // A finished decode is a slot the queue can use, whether or not it produced an image.
                // Without this the cap would be a one-shot limit rather than a rate: the first four
                // frames of a window would decode and the other seven would wait for a pointer move
                // that may never come.
                defer { self.pumpPrefetch() }
                guard let decoded else {
                    self.failed.insert(id)
                    return
                }
                self.cache.insert(decoded.image, id: id, bytes: decoded.bytes)
                for waiter in waiters { waiter(decoded.image) }
                self.onDecode?()
            }
        }
    }

    /// Warms the cache for frames the playhead is about to reach.
    ///
    /// Which frames those are — and how the window is aimed once the playhead is moving — is
    /// `RewindScrub.prefetchWindow`'s decision, not this one; the caller passes the answer in.
    /// Results are dropped on the floor: the point is only that the decode has already happened by
    /// the time the frame is asked for.
    ///
    /// Runs at `maximumConcurrentDecodes` and queues the rest. This is the *speculative* path, so
    /// waiting is not a failure, whereas `load` itself — how the frame under the playhead is
    /// fetched — is never capped.
    ///
    /// The queue is **replaced** rather than appended to. The caller re-issues a window on every
    /// playhead move, and the newest one is always the only one worth warming: an older window names
    /// captures the scrub has already gone past, and appending would make a fast drag build a backlog
    /// of stale work that outlives the gesture that asked for it.
    func prefetch(_ frames: [RewindFrame]) {
        pendingPrefetch = frames
        pumpPrefetch()
    }

    private func pumpPrefetch() {
        while inFlight.count < Self.maximumConcurrentDecodes, !pendingPrefetch.isEmpty {
            // Removed before the call, so a frame that is already cached or already known bad — both
            // of which `load` answers without starting anything — cannot spin this loop.
            load(pendingPrefetch.removeFirst())
        }
    }

    /// Drops everything. Called when the window loads a different day, so yesterday's images do not
    /// hold the budget against today's — including a queue of yesterday's frames still waiting for a
    /// decode slot, and anything still waiting to be told about one. A decode already running will
    /// finish and be cached; nobody is left holding a callback that would paint the old day.
    func purge() {
        cache.removeAll()
        failed.removeAll()
        pendingPrefetch.removeAll()
        waiting.removeAll()
    }

    // MARK: - Decode

    private struct Decoded {
        let image: NSImage
        /// The decoded bitmap's real size in memory, which is what the cache is charged.
        let bytes: Int
    }

    /// `nonisolated` and `static`: this runs on a detached task and must touch no actor state.
    ///
    /// `CGImageSourceCreateThumbnailAtIndex` rather than `NSImage(contentsOfFile:)`: `NSImage` is lazy
    /// and would defer the actual decode to the first draw, which puts it back on the main thread at
    /// exactly the moment this class exists to protect. Asking ImageIO for the thumbnail forces the
    /// work here, on this thread, and hands back something already rasterised.
    private nonisolated static func decode(path: String) -> Decoded? {
        let url = URL(fileURLWithPath: path)
        // Checked rather than assumed: retention unlinks files, and a window left open across a
        // prune holds ids whose images are gone. That is an ordinary outcome, not an error.
        guard let source = CGImageSourceCreateWithURL(url as CFURL, nil) else { return nil }

        let options: [CFString: Any] = [
            kCGImageSourceCreateThumbnailFromImageAlways: true,
            kCGImageSourceThumbnailMaxPixelSize: maxPixelSize,
            // Without this the thumbnail comes back unrotated and any frame with EXIF orientation
            // draws sideways.
            kCGImageSourceCreateThumbnailWithTransform: true,
            kCGImageSourceShouldCacheImmediately: true,
        ]
        guard
            let cgImage = CGImageSourceCreateThumbnailAtIndex(
                source, 0, options as CFDictionary)
        else { return nil }

        let image = NSImage(
            cgImage: cgImage, size: NSSize(width: cgImage.width, height: cgImage.height))
        // The honest cost: what the bitmap occupies, not a per-image constant. `bytesPerRow`
        // includes the decoder's row padding, so this is the real allocation.
        let bytes = max(1, cgImage.bytesPerRow * cgImage.height)
        return Decoded(image: image, bytes: bytes)
    }
}

/// A byte-bounded, least-recently-read store of decoded frames.
///
/// **It replaces an `NSCache`, and the crossfade is why.** `NSCache` leaves both properties this
/// needs unspecified. Its eviction *order* is undocumented — it is free to drop the capture the
/// playhead is sitting on and keep one from an hour ago — and its `totalCostLimit` is advisory, which
/// the comment this supersedes said out loud: "a budget rather than a guarantee". Neither was
/// testable, and with a dissolve on the stage both started to matter:
///
/// - The two captures being blended are the two the stage read most recently, so **least recently
///   read goes first** is exactly the rule that keeps them resident. Losing one mid-fade is a visible
///   flash, and an unspecified order cannot promise it will not happen.
/// - A window a user leaves open all day needs a ceiling that is a ceiling. This one cannot be
///   exceeded, by construction, and `FrameLoaderTests` asserts it over a long insert sequence.
///
/// What it gives up is `NSCache`'s automatic eviction under system memory pressure. The trade is
/// deliberate: a hard 192 MB ceiling is a stronger guarantee than an advisory one that also
/// discards unpredictably, and 192 MB is a bound the machine can carry.
///
/// The order list is a plain array. It holds ~32 ids at this budget, so the linear removals are
/// cheaper than the bookkeeping a linked list would need to avoid them.
struct FrameMemoryCache {

    let budgetBytes: Int
    /// Decoded bytes currently held. Never above `budgetBytes`.
    private(set) var bytes = 0

    private struct Entry {
        let image: NSImage
        let bytes: Int
    }

    private var entries: [Int64: Entry] = [:]
    /// Frame ids in read order, least recently read first.
    private var order: [Int64] = []

    init(budgetBytes: Int) {
        self.budgetBytes = max(0, budgetBytes)
    }

    var count: Int { entries.count }

    /// The image for `id`, marking it most recently used. `mutating` for that reason alone.
    mutating func image(for id: Int64) -> NSImage? {
        guard let entry = entries[id] else { return nil }
        touch(id)
        return entry.image
    }

    /// Whether `id` is resident, without disturbing the order.
    func holds(_ id: Int64) -> Bool { entries[id] != nil }

    mutating func insert(_ image: NSImage, id: Int64, bytes: Int) {
        let cost = max(1, bytes)
        // A single frame larger than the whole budget is not cached at all. At 192 MB against ~6 MB
        // captures this cannot happen; if it ever did, decoding it twice is better than admitting an
        // entry the ceiling cannot hold — which is precisely how a bound stops being one.
        guard cost <= budgetBytes else { return }
        remove(id)
        entries[id] = Entry(image: image, bytes: cost)
        order.append(id)
        self.bytes += cost
        while self.bytes > budgetBytes, let oldest = order.first { remove(oldest) }
    }

    mutating func removeAll() {
        entries.removeAll()
        order.removeAll()
        bytes = 0
    }

    private mutating func remove(_ id: Int64) {
        guard let entry = entries.removeValue(forKey: id) else { return }
        bytes -= entry.bytes
        order.removeAll { $0 == id }
    }

    private mutating func touch(_ id: Int64) {
        guard let index = order.firstIndex(of: id) else { return }
        order.remove(at: index)
        order.append(id)
    }
}
