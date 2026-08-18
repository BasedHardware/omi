import Foundation

/// Sums the microphone and the system tap into the single mono stream `/v4/listen` transcribes.
///
/// Two capture devices, one socket. The backend runs its own diarization and matches each voice
/// against the account's enrolled speech profiles, which is strictly better attribution than "the
/// mic is me and the system tap is everyone else": that heuristic mislabels anyone else speaking
/// into this Mac's microphone, and it can never put a *name* to a voice. Mixing discards a
/// distinction the server does not need, and keeps this to one socket and one transcription bill
/// instead of two.
///
/// The rule that shapes everything below: **a dead source must never block the live one.** The
/// system tap is the fragile half — a permission granted mid-session, an aggregate device the OS
/// tears down — and a mixer that waits for both buffers before emitting would silently take the
/// microphone down with it. So each source carries a liveness deadline, and a source that misses it
/// is padded with silence until it comes back.
///
/// Every method is safe to call from a CoreAudio IO thread; `lock` guards all mutable state and no
/// chunk handler is ever invoked while it is held.
final class AudioMixer: @unchecked Sendable {
    /// The one mixer both capture sources feed. It has to be shared: mixing is the act of joining
    /// two independently-owned devices, so an instance per source would have nothing to mix.
    static let shared = AudioMixer()

    /// Mixed 16 kHz mono Int16 little-endian PCM, in capture order.
    ///
    /// `@Sendable` on purpose. This is called from a CoreAudio IO thread, and letting it inherit the
    /// main actor from wherever `start` happened to be called would be a promise the mixer cannot
    /// keep — the compiler would stop warning about exactly the hop that has to happen.
    typealias ChunkHandler = @Sendable (Data) -> Void

    /// Seconds, from a monotonic source. Injectable so liveness can be tested without real sleeps.
    typealias Clock = @Sendable () -> Double

    /// 100 ms at 16 kHz mono Int16 — one `/v4/listen` frame. Emitting smaller frames would spend a
    /// WebSocket frame header per 20 ms of audio; emitting larger ones adds latency the live
    /// transcript is judged on.
    static let frameBytes = 3200

    /// One second per source. Past this the mixer is holding audio it should already have sent, so
    /// the excess is dropped oldest-first rather than grown — a stalled consumer must cost a moment
    /// of sound, never the machine's memory.
    private static let maxBufferBytes = 32_000

    /// How long a source may go quiet before the mixer stops waiting for it. Long enough that an
    /// ordinary scheduling hiccup does not trip it, short enough that a tap which never starts costs
    /// two seconds of microphone rather than the whole session.
    private static let sourceTimeout: Double = 2.0

    private static let logCategory = "mixer"

    private enum Source {
        case mic
        case system
    }

    private let clock: Clock
    private let lock = NSLock()

    private var onChunk: ChunkHandler?
    private var isRunning = false

    private var micBuffer = Data()
    private var systemBuffer = Data()

    private var startedAt: Double?
    private var lastMicAt: Double?
    private var lastSystemAt: Double?
    private var isMicStalled = false
    private var isSystemStalled = false

    /// `DispatchTime` is monotonic and does not tick while the Mac is asleep — both of which matter
    /// for a two-second deadline. Wall clock would let an NTP correction, or a lid closing over
    /// lunch, declare a perfectly healthy microphone dead.
    init(clock: @escaping Clock = { Double(DispatchTime.now().uptimeNanoseconds) / 1_000_000_000 }) {
        self.clock = clock
    }

    // MARK: - Lifecycle

    /// Begins mixing. Calling this again while running only replaces the sink: a source rebuilding
    /// itself underneath the mixer (the silent-mic watchdog does exactly that) must not reset the
    /// buffers or the liveness clock mid-stream.
    func start(onChunk: @escaping ChunkHandler) {
        lock.lock()
        if isRunning {
            self.onChunk = onChunk
            lock.unlock()
            return
        }
        self.onChunk = onChunk
        isRunning = true
        micBuffer = Data()
        systemBuffer = Data()
        startedAt = clock()
        lastMicAt = nil
        lastSystemAt = nil
        isMicStalled = false
        isSystemStalled = false
        lock.unlock()
        ContextLog.info("Mixer started", Self.logCategory)
    }

    /// Stops mixing and flushes whatever partial frame is left, so the last words spoken before a
    /// pause still reach the transcriber.
    func stop() {
        lock.lock()
        guard isRunning else {
            onChunk = nil
            lock.unlock()
            return
        }
        isRunning = false
        let handler = onChunk
        let remaining = drainLocked(flush: true)
        micBuffer = Data()
        systemBuffer = Data()
        onChunk = nil
        lock.unlock()

        for chunk in remaining { handler?(chunk) }
        ContextLog.info("Mixer stopped", Self.logCategory)
    }

    // MARK: - Input

    /// Adds microphone audio: 16 kHz mono Int16 little-endian PCM.
    func setMicAudio(_ data: Data) {
        accept(data, from: .mic)
    }

    /// Adds system-tap audio: 16 kHz mono Int16 little-endian PCM.
    func setSystemAudio(_ data: Data) {
        accept(data, from: .system)
    }

    private func accept(_ data: Data, from source: Source) {
        lock.lock()
        guard isRunning else {
            lock.unlock()
            return
        }

        switch source {
        case .mic:
            micBuffer.append(data)
            // Only non-empty data proves the source is alive. A capture path that has broken down
            // can keep delivering empty callbacks, and counting those as liveness is how a dead tap
            // holds the microphone hostage forever.
            if !data.isEmpty {
                lastMicAt = clock()
                if isMicStalled {
                    isMicStalled = false
                    ContextLog.info("Microphone recovered", Self.logCategory)
                }
            }
            trimLocked(&micBuffer, label: "microphone")
        case .system:
            systemBuffer.append(data)
            if !data.isEmpty {
                lastSystemAt = clock()
                if isSystemStalled {
                    isSystemStalled = false
                    ContextLog.info("System audio recovered", Self.logCategory)
                }
            }
            trimLocked(&systemBuffer, label: "system audio")
        }

        let handler = onChunk
        let produced = drainLocked(flush: false)
        lock.unlock()

        // Outside the lock on purpose: the handler ends up on the WebSocket, and nothing that far
        // downstream should be able to deadlock a CoreAudio IO thread by calling back in here.
        for chunk in produced { handler?(chunk) }
    }

    private func trimLocked(_ buffer: inout Data, label: String) {
        guard buffer.count > Self.maxBufferBytes else { return }
        let excess = buffer.count - Self.maxBufferBytes
        buffer.removeFirst(excess)
        ContextLog.error(
            "Dropped \(Self.describeSeconds(excess)) of \(label) — the mixer is running behind",
            Self.logCategory)
    }

    // MARK: - Mixing

    /// Produces as many whole frames as the current buffers allow. Must be called with `lock` held.
    ///
    /// Normally both sources have to have data, which is what keeps them time-aligned. When one has
    /// missed its deadline the mixer switches to single-source mode and pads the absent side with
    /// silence — the live source keeps flowing at the right rate, and the alignment repairs itself
    /// the moment the other side returns.
    private func drainLocked(flush: Bool) -> [Data] {
        var produced: [Data] = []
        while true {
            guard let bytes = nextFrameSizeLocked(flush: flush) else { break }
            produced.append(mixLocked(bytes: bytes))
            // A flush empties the buffers in one pass; looping would spin on two empty Datas.
            if flush { break }
        }
        return produced
    }

    /// How many bytes to take from each buffer for the next frame, or nil when there is not enough.
    private func nextFrameSizeLocked(flush: Bool) -> Int? {
        if flush {
            let available = max(micBuffer.count, systemBuffer.count)
            let aligned = (available / 2) * 2
            return aligned >= 2 ? aligned : nil
        }

        let now = clock()
        let micStalled = hasStalled(lastAt: lastMicAt, now: now)
        let systemStalled = hasStalled(lastAt: lastSystemAt, now: now)

        if micStalled != isMicStalled {
            isMicStalled = micStalled
            if micStalled { ContextLog.error("Microphone stalled — sending system audio alone", Self.logCategory) }
        }
        if systemStalled != isSystemStalled {
            isSystemStalled = systemStalled
            if systemStalled { ContextLog.error("System audio stalled — sending microphone alone", Self.logCategory) }
        }

        let available = micStalled || systemStalled
            ? max(micBuffer.count, systemBuffer.count)
            : min(micBuffer.count, systemBuffer.count)
        guard available >= Self.frameBytes else { return nil }
        return (available / 2) * 2
    }

    /// A source that has never delivered anything is judged from when the mixer started, so a tap
    /// that fails to open is detected on the same deadline as one that dies mid-call.
    private func hasStalled(lastAt: Double?, now: Double) -> Bool {
        guard let reference = lastAt ?? startedAt else { return false }
        return now - reference > Self.sourceTimeout
    }

    /// Takes `bytes` from each buffer (padding a short one with silence) and sums them to mono.
    private func mixLocked(bytes: Int) -> Data {
        let mic = takeLocked(&micBuffer, bytes: bytes)
        let system = takeLocked(&systemBuffer, bytes: bytes)
        return Self.sumToMono(mic: mic, system: system)
    }

    private func takeLocked(_ buffer: inout Data, bytes: Int) -> Data {
        guard buffer.count >= bytes else {
            let padded = buffer + Data(repeating: 0, count: bytes - buffer.count)
            buffer = Data()
            return padded
        }
        let taken = buffer.prefix(bytes)
        buffer.removeFirst(bytes)
        return Data(taken)
    }

    /// Sums two mono Int16 streams, clamping instead of wrapping.
    ///
    /// A straight sum, not an average: both sides keep their natural loudness, and two people
    /// talking over each other saturates cleanly rather than halving into something no transcriber
    /// can read. Wrap-around is the failure to avoid — an overflowed Int16 is a full-scale click,
    /// which the speech model hears as a consonant that was never said.
    private static func sumToMono(mic: Data, system: Data) -> Data {
        let sampleCount = min(mic.count, system.count) / 2
        guard sampleCount > 0 else { return Data() }

        var mixed = [Int16]()
        mixed.reserveCapacity(sampleCount)
        mic.withUnsafeBytes { micRaw in
            system.withUnsafeBytes { systemRaw in
                let micSamples = micRaw.bindMemory(to: Int16.self)
                let systemSamples = systemRaw.bindMemory(to: Int16.self)
                for index in 0..<sampleCount {
                    let summed = Int32(micSamples[index]) + Int32(systemSamples[index])
                    mixed.append(Int16(max(Int32(Int16.min), min(Int32(Int16.max), summed))))
                }
            }
        }
        return mixed.withUnsafeBufferPointer { Data(buffer: $0) }
    }

    // MARK: - Reporting

    /// Bytes of 16 kHz mono Int16 as a duration — the only thing worth putting in a log line about
    /// audio, and the only thing that carries none of it.
    static func describeSeconds(_ bytes: Int) -> String {
        String(format: "%.1fs", Double(bytes) / 32_000)
    }
}
