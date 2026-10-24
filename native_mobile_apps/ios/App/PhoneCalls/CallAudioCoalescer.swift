import Foundation
import OmiService

/// Batches the audio device's ~20 ms buffers into ~100 ms per channel before they become transcript
/// frames (Flutter `OmiAudioEventCoalescer`). Appends hop to a serial queue; a starved queue drops new
/// audio at the enqueue cap, an overfull channel drops its oldest bytes, so the freshest audio flows.
final class CallAudioCoalescer: @unchecked Sendable {
    /// 100 ms of 48 kHz PCM16 mono.
    static let flushBytes = 9600
    static let maxPendingBytes = flushBytes * 4
    static let maxQueuedBytes = flushBytes * 16

    private let queue = DispatchQueue(label: "omi.phonecalls.audio")
    private let emit: @Sendable (PhoneCallAudio) -> Void
    private let lock = NSLock()
    private var queuedBytes = 0
    private var flushed = false
    /// Only touched on `queue`.
    private var pending: [PhoneCallAudioChannel: Data] = [:]

    init(emit: @escaping @Sendable (PhoneCallAudio) -> Void) {
        self.emit = emit
    }

    /// From the realtime audio thread.
    func append(_ pcm: Data, channel: PhoneCallAudioChannel) {
        let accepted = lock.withLock {
            guard !flushed, queuedBytes + pcm.count <= Self.maxQueuedBytes else { return false }
            queuedBytes += pcm.count
            return true
        }
        guard accepted else { return }
        queue.async { [self] in
            lock.withLock { queuedBytes -= pcm.count }
            var buffer = pending[channel] ?? Data()
            buffer.append(pcm)
            if buffer.count > Self.maxPendingBytes { buffer.removeFirst(buffer.count - Self.flushBytes) }
            if buffer.count >= Self.flushBytes {
                pending[channel] = nil
                emit(Self.audio(buffer, channel))
            } else {
                pending[channel] = buffer
            }
        }
    }

    /// The call is over: the last partial buffers go out (the final ~100 ms is not lost), nothing after.
    func flush() {
        lock.withLock { flushed = true }
        queue.async { [self] in
            for (channel, buffer) in pending where !buffer.isEmpty {
                emit(Self.audio(buffer, channel))
            }
            pending = [:]
        }
    }

    private static func audio(_ pcm: Data, _ channel: PhoneCallAudioChannel) -> PhoneCallAudio {
        PhoneCallAudio(channel: channel == .microphone ? .you : .them, pcm16: pcm)
    }
}
