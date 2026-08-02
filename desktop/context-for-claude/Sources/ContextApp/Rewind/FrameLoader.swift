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
/// independent HEIC per frame (`ScreenPipeline.writeFrameImage`, 1600 px longest side at quality
/// 0.20), so a frame is a single file that decodes on its own. There is no video path, no chunk
/// index, and no subprocess to go wrong.
///
/// Measured over 507 real frames sampled across the whole frames directory on this machine, through
/// exactly the options `decode` passes: **median 14.4 ms, p95 19.9 ms, min 8.3 ms, max 38.5 ms** per
/// decode, from files averaging 55.6 KB. Combined with the prefetch, a scrub that stays inside the
/// prefetched window is a cache hit and costs nothing; only a jump beyond it pays a decode, and that
/// decode is off the main thread.
///
/// Two rules make it feel instant:
///
/// - **Decode is never on the main thread.** A synchronous decode inside a SwiftUI body is a dropped
///   frame per scrub step; every load lands through `Task.detached` and publishes back on the main
///   actor.
/// - **The cache is charged real bytes.** Theirs sets a 100 MB `totalCostLimit` and then charges a
///   flat 4 MB per frame regardless of the image, so the budget silently means "about 25 frames"
///   whatever the frames are. `NSCache` only balances a cost that tracks reality, so the cost here is
///   the decoded bitmap's actual size — `bytesPerRow * height` — measured at **5.95 MB** on average
///   across those same 507 frames, and correspondingly less for a small one. The limit then means
///   what it says: 192 MB holds ~32 frames of this size, comfortably more than the 11 a prefetch
///   window touches.
@MainActor
final class FrameLoader {

    /// Decoded-bitmap bytes held in memory. Sized against what a scrub actually touches: the
    /// playhead frame plus `RewindModel.prefetchRadius` either side is 11 images, measured at
    /// 5.95 MB each and so ~65 MB, and 192 MB keeps roughly a further 20 frames of trail behind a
    /// moving playhead without letting an all-day drag pin an unbounded amount of memory. `NSCache`
    /// evicts under real system pressure regardless, which is why this is a budget rather than a
    /// guarantee.
    static let memoryBudgetBytes = 192 * 1024 * 1024

    /// Longest side requested from the decoder.
    ///
    /// Matches `ScreenPipeline.maxPixelSize`, the size the file was written at, so the thumbnail path
    /// returns the stored image rather than an upscale of it. Asking for more would make
    /// `CGImageSourceCreateThumbnailAtIndex` interpolate; asking for much less would make the frame
    /// soft on a Retina display, which is the one thing a timeline of screenshots cannot afford.
    /// `nonisolated` because `decode` reads it on a detached task; a main-actor constant would be an
    /// error in the Swift 6 language mode.
    nonisolated static let maxPixelSize = 1600

    private let cache: NSCache<NSNumber, NSImage> = {
        let cache = NSCache<NSNumber, NSImage>()
        cache.totalCostLimit = FrameLoader.memoryBudgetBytes
        return cache
    }()

    /// Frame ids with a decode in flight, so a scrub that passes over the same frame twice — or a
    /// prefetch that overlaps the playhead — does not start the work twice.
    private var inFlight: Set<Int64> = []

    /// Ids whose file could not be decoded. Remembered so a missing or corrupt image is attempted
    /// once rather than on every pass of the playhead: retrying forever would turn one bad file into
    /// a permanent stutter, and nothing about the file is going to change while the window is open.
    private var failed: Set<Int64> = []

    /// The cached image for a frame, if it is already in memory. Never decodes — safe to call from a
    /// view body.
    func cached(_ frame: RewindFrame) -> NSImage? {
        cache.object(forKey: NSNumber(value: frame.id))
    }

    /// True when this frame has already failed to decode, so callers can show the reason rather than
    /// an indefinite spinner.
    func hasFailed(_ frame: RewindFrame) -> Bool { failed.contains(frame.id) }

    /// Decodes `frame` unless it is cached, in flight, or already known bad. `completion` runs on the
    /// main actor, and only when an image was genuinely produced.
    func load(_ frame: RewindFrame, completion: @escaping @MainActor (NSImage) -> Void) {
        let id = frame.id
        if let image = cached(frame) {
            completion(image)
            return
        }
        guard !inFlight.contains(id), !failed.contains(id) else { return }
        inFlight.insert(id)

        let path = frame.imagePath
        Task.detached(priority: .userInitiated) {
            let decoded = FrameLoader.decode(path: path)
            await MainActor.run {
                self.inFlight.remove(id)
                guard let decoded else {
                    self.failed.insert(id)
                    return
                }
                self.cache.setObject(
                    decoded.image, forKey: NSNumber(value: id), cost: decoded.bytes)
                completion(decoded.image)
            }
        }
    }

    /// Warms the cache for frames the playhead is about to reach, in both directions.
    ///
    /// Both directions because a scrub reverses constantly — the user overshoots and comes back — and
    /// a one-sided prefetch makes going backwards feel broken while going forwards feels fine.
    /// Results are dropped on the floor: the point is only that the decode has already happened by
    /// the time the frame is asked for.
    func prefetch(_ frames: [RewindFrame]) {
        for frame in frames { load(frame) { _ in } }
    }

    /// Drops everything. Called when the window loads a different day, so yesterday's images do not
    /// hold the budget against today's.
    func purge() {
        cache.removeAllObjects()
        failed.removeAll()
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
