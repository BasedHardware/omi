import Foundation

/// Mixes microphone and system audio into a combined stream for transcription.
/// Supports stereo (interleaved mic+system) or mono (averaged) output.
/// Channel 0 (left) = Microphone (user)
/// Channel 1 (right) = System audio (others)
class AudioMixer {

    // MARK: - Types

    enum OutputMode {
        case stereo  // Interleaved [mic0, sys0, mic1, sys1, ...] — for Deepgram multichannel
        case mono    // Averaged (mic + system) / 2 — for backend /v4/listen
    }

    /// Callback for receiving mixed audio chunks
    typealias StereoAudioHandler = (Data) -> Void

    // MARK: - Properties

    private var onStereoChunk: StereoAudioHandler?
    private var isRunning = false
    private(set) var outputMode: OutputMode = .stereo

    // Audio buffers (16kHz mono Int16 PCM)
    private var micBuffer = Data()
    private var systemBuffer = Data()
    private let bufferLock = NSLock()

    // Minimum samples before producing output (100ms at 16kHz = 1600 samples = 3200 bytes)
    private let minBufferBytes = 3200

    // Maximum buffer size to prevent unbounded growth (1 second = 32000 bytes)
    private let maxBufferBytes = 32000

    // MARK: - Public Methods

    /// Start the mixer
    /// - Parameters:
    ///   - outputMode: `.stereo` for interleaved multichannel, `.mono` for averaged single-channel
    ///   - onStereoChunk: Callback receiving mixed 16-bit PCM at 16kHz
    func start(outputMode: OutputMode = .stereo, onStereoChunk: @escaping StereoAudioHandler) {
        bufferLock.lock()
        self.outputMode = outputMode
        self.onStereoChunk = onStereoChunk
        self.isRunning = true
        micBuffer = Data()
        systemBuffer = Data()
        bufferLock.unlock()
        log("AudioMixer: Started (output=\(outputMode))")
    }

    /// Stop the mixer and flush remaining audio
    func stop() {
        bufferLock.lock()
        isRunning = false
        // Flush any remaining audio
        processBuffers(flush: true)
        micBuffer = Data()
        systemBuffer = Data()
        onStereoChunk = nil
        bufferLock.unlock()
        log("AudioMixer: Stopped")
    }

    /// Add microphone audio (16kHz mono Int16 PCM)
    func setMicAudio(_ data: Data) {
        bufferLock.lock()
        defer { bufferLock.unlock() }

        guard isRunning else { return }

        micBuffer.append(data)

        // Prevent unbounded buffer growth
        if micBuffer.count > maxBufferBytes {
            let excess = micBuffer.count - maxBufferBytes
            micBuffer.removeFirst(excess)
        }

        processBuffers()
    }

    /// Add system audio (16kHz mono Int16 PCM)
    func setSystemAudio(_ data: Data) {
        bufferLock.lock()
        defer { bufferLock.unlock() }

        guard isRunning else { return }

        systemBuffer.append(data)

        // Prevent unbounded buffer growth
        if systemBuffer.count > maxBufferBytes {
            let excess = systemBuffer.count - maxBufferBytes
            systemBuffer.removeFirst(excess)
        }

        processBuffers()
    }

    // MARK: - Private Methods

    /// Process buffers and produce stereo output when enough data is available
    /// Must be called with bufferLock held
    private func processBuffers(flush: Bool = false) {
        guard isRunning || flush else { return }

        // Check if we have enough data (or flushing)
        let minRequired = flush ? 2 : minBufferBytes  // At least 1 sample (2 bytes) when flushing
        guard micBuffer.count >= minRequired || systemBuffer.count >= minRequired else { return }

        // Determine how many bytes to process (match the shorter buffer, aligned to sample boundary)
        let bytesToProcess: Int
        if flush {
            // When flushing, process whatever is available
            bytesToProcess = max(micBuffer.count, systemBuffer.count)
        } else if micBuffer.count >= minBufferBytes && systemBuffer.count >= minBufferBytes {
            // Both buffers have data — use shorter to stay in sync
            bytesToProcess = (min(micBuffer.count, systemBuffer.count) / 2) * 2
        } else if micBuffer.count >= minBufferBytes {
            // Only mic has data (system audio disabled/unavailable) — pad system with silence
            bytesToProcess = (micBuffer.count / 2) * 2
        } else if systemBuffer.count >= minBufferBytes {
            // Only system has data — pad mic with silence
            bytesToProcess = (systemBuffer.count / 2) * 2
        } else {
            return
        }

        guard bytesToProcess >= 2 else { return }

        // Extract data from buffers
        let micData: Data
        let sysData: Data

        if micBuffer.count >= bytesToProcess {
            micData = micBuffer.prefix(bytesToProcess)
            micBuffer.removeFirst(bytesToProcess)
        } else {
            // Pad mic buffer with silence
            micData = micBuffer + Data(repeating: 0, count: bytesToProcess - micBuffer.count)
            micBuffer = Data()
        }

        if systemBuffer.count >= bytesToProcess {
            sysData = systemBuffer.prefix(bytesToProcess)
            systemBuffer.removeFirst(bytesToProcess)
        } else {
            // Pad system buffer with silence
            sysData = systemBuffer + Data(repeating: 0, count: bytesToProcess - systemBuffer.count)
            systemBuffer = Data()
        }

        // Mix according to output mode
        let mixedData: Data
        switch outputMode {
        case .stereo:
            mixedData = interleave(mic: micData, system: sysData)
        case .mono:
            mixedData = mixToMono(mic: micData, system: sysData)
        }

        // Send to callback
        onStereoChunk?(mixedData)
    }

    /// Interleave two mono Int16 streams into stereo
    /// Output format: [mic0, sys0, mic1, sys1, ...]
    private func interleave(mic: Data, system: Data) -> Data {
        let sampleCount = mic.count / 2  // Each Int16 sample is 2 bytes

        // Pre-allocate output (2 channels * sampleCount samples * 2 bytes per sample)
        var stereoSamples = [Int16]()
        stereoSamples.reserveCapacity(sampleCount * 2)

        mic.withUnsafeBytes { micPtr in
            system.withUnsafeBytes { sysPtr in
                let micSamples = micPtr.bindMemory(to: Int16.self)
                let sysSamples = sysPtr.bindMemory(to: Int16.self)

                for i in 0..<sampleCount {
                    // Channel 0 (left) = mic = user
                    let micSample = i < micSamples.count ? micSamples[i] : 0
                    stereoSamples.append(micSample)

                    // Channel 1 (right) = system = others
                    let sysSample = i < sysSamples.count ? sysSamples[i] : 0
                    stereoSamples.append(sysSample)
                }
            }
        }

        return stereoSamples.withUnsafeBufferPointer { buffer in
            Data(buffer: buffer)
        }
    }

    /// Average two mono Int16 streams into a single mono stream
    /// Output format: [(mic0+sys0)/2, (mic1+sys1)/2, ...]
    private func mixToMono(mic: Data, system: Data) -> Data {
        let sampleCount = mic.count / 2

        var monoSamples = [Int16]()
        monoSamples.reserveCapacity(sampleCount)

        mic.withUnsafeBytes { micPtr in
            system.withUnsafeBytes { sysPtr in
                let micSamples = micPtr.bindMemory(to: Int16.self)
                let sysSamples = sysPtr.bindMemory(to: Int16.self)

                for i in 0..<sampleCount {
                    let micSample = Int32(i < micSamples.count ? micSamples[i] : 0)
                    let sysSample = Int32(i < sysSamples.count ? sysSamples[i] : 0)
                    // Average and clamp to Int16 range
                    let mixed = (micSample + sysSample) / 2
                    monoSamples.append(Int16(clamping: mixed))
                }
            }
        }

        return monoSamples.withUnsafeBufferPointer { buffer in
            Data(buffer: buffer)
        }
    }
}
