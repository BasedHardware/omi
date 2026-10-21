import Foundation

/// Batches 20 ms Core Audio buffers into bounded events before they cross to Flutter.
///
/// The realtime callbacks deliver ~100 buffers/sec across two channels; posting each
/// one onto the Flutter EventChannel as its own Map (with a main-queue hop) is what a
/// CallKit-active call at 48 kHz cannot keep up with, so the stream silently dries up.
/// This coalescer appends buffers on a dedicated serial queue and emits one event per
/// channel once `flushBytes` (~100 ms) have accumulated.
///
/// Bounding happens twice: an enqueue-time cap (`maxEnqueuedBytes`, checked on the
/// caller's thread BEFORE queueing, so a starved queue cannot accumulate unlimited
/// work items) and an in-flight cap (`maxPendingBytes`, oldest bytes dropped so the
/// freshest audio keeps flowing). A generation counter invalidates work queued by a
/// previous call after `flush()`/`reset()`, so a new call can never emit the last
/// call's tail.
final class OmiAudioEventCoalescer {
    private let queue: DispatchQueue
    private let flushBytes: Int
    private let maxPendingBytes: Int
    private let maxEnqueuedBytes: Int
    private let emit: (Data, Int) -> Void

    // Channel -> accumulated bytes; only touched on `queue`.
    private var pending: [Int: Data] = [:]
    private var trimmedBytes = 0

    // Enqueue bound + generation, touched from realtime threads and `queue`,
    // so they get their own short lock. Nothing audio-sized happens under it.
    private let stateLock = NSLock()
    private var enqueuedBytes = 0
    private var generation = 0
    private var enqueueDroppedBytes = 0

    /// - Parameters:
    ///   - flushBytes: emit once a channel accumulates this many bytes.
    ///   - maxPendingBytes: per-channel cap; oldest bytes are dropped beyond it.
    ///   - maxEnqueuedBytes: hard cap on bytes accepted but not yet processed.
    ///   - emit: called on `queue` with one channel's coalesced payload.
    init(
        flushBytes: Int = 10_240,
        maxPendingBytes: Int = 40_960,
        maxEnqueuedBytes: Int = 163_840,
        label: String = "com.omi.phonecalls.audioevents",
        emit: @escaping (Data, Int) -> Void
    ) {
        self.queue = DispatchQueue(label: label)
        self.flushBytes = max(1, flushBytes)
        self.maxPendingBytes = max(self.flushBytes, maxPendingBytes)
        self.maxEnqueuedBytes = max(self.maxPendingBytes, maxEnqueuedBytes)
        self.emit = emit
    }

    /// Called from the Core Audio realtime thread. Rejects the buffer before
    /// enqueueing when too much accepted work is still queued, then hands it to
    /// the serial queue tagged with the current generation.
    func append(_ data: Data, channel: Int) {
        stateLock.lock()
        let currentGeneration = generation
        if enqueuedBytes + data.count > maxEnqueuedBytes {
            enqueueDroppedBytes += data.count
            stateLock.unlock()
            return
        }
        enqueuedBytes += data.count
        stateLock.unlock()

        queue.async { [weak self] in
            guard let self = self else { return }
            defer {
                self.stateLock.lock()
                self.enqueuedBytes -= data.count
                self.stateLock.unlock()
            }
            self.stateLock.lock()
            let stale = currentGeneration != self.generation
            var enqueueDrops = 0
            if self.enqueueDroppedBytes >= 102_400 {
                enqueueDrops = self.enqueueDroppedBytes
                self.enqueueDroppedBytes = 0
            }
            self.stateLock.unlock()
            if enqueueDrops > 0 {
                print("OmiAudioEventCoalescer: rejected \(enqueueDrops) queued bytes at the enqueue cap")
            }
            if stale {
                return // queued by a previous call; flush()/reset() already ended it
            }
            var buffer = self.pending[channel] ?? Data()
            buffer.append(data)
            if buffer.count > self.maxPendingBytes {
                // Drop the oldest bytes down to one flush unit; count only the
                // drop so a saturated consumer is visible without dumping audio.
                self.trimmedBytes += buffer.count - self.flushBytes
                buffer.removeFirst(buffer.count - self.flushBytes)
                if self.trimmedBytes >= 102_400 {
                    print("OmiAudioEventCoalescer: trimmed \(self.trimmedBytes) pending bytes (channel \(channel))")
                    self.trimmedBytes = 0
                }
            }
            if buffer.count >= self.flushBytes {
                self.pending[channel] = nil
                self.emit(buffer, channel)
            } else {
                self.pending[channel] = buffer
            }
        }
    }

    /// Emit each channel's partial buffer now (call teardown must not lose the
    /// final ~100 ms), then invalidate everything still queued for this call.
    func flush() {
        queue.async { [weak self] in
            guard let self = self else { return }
            for (channel, buffer) in self.pending {
                self.emit(buffer, channel)
            }
            self.pending.removeAll()
            self.stateLock.lock()
            self.generation += 1
            self.stateLock.unlock()
        }
    }

    /// Drop any partial buffer (e.g. call teardown) without emitting.
    func reset() {
        queue.async { [weak self] in
            self?.pending.removeAll()
            self?.stateLock.lock()
            self?.generation += 1
            self?.stateLock.unlock()
        }
    }
}
