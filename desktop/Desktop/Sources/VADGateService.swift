import Foundation
import onnxruntime

// MARK: - Silero VAD Model (ONNX Runtime)

/// Wraps Silero VAD ONNX model for speech probability inference.
/// Input: 512 Float32 samples at 16kHz. Output: speech probability [0,1].
final class SileroVADModel {
    private let session: ORTSession
    private let env: ORTEnv
    private var state: [Float]  // [2, 1, 128] = 256 floats (combined h+c for v5)

    private let stateSize = 2 * 1 * 128  // 256

    init?() {
        guard let modelPath = Bundle.main.path(forResource: "silero_vad", ofType: "onnx") else {
            log("VADGateService: silero_vad.onnx not found in bundle")
            return nil
        }

        do {
            env = try ORTEnv(loggingLevel: .warning)
            let sessionOptions = try ORTSessionOptions()
            try sessionOptions.setIntraOpNumThreads(1)
            session = try ORTSession(env: env, modelPath: modelPath, sessionOptions: sessionOptions)
            state = [Float](repeating: 0.0, count: stateSize)
        } catch {
            logError("VADGateService: Failed to create ONNX session", error: error)
            return nil
        }
    }

    /// Run inference on 512 Float32 samples. Returns speech probability.
    func predict(_ samples: [Float]) -> Float {
        assert(samples.count == 512, "Silero VAD expects exactly 512 samples")

        do {
            // Input tensor: [1, 512]
            let inputData = NSMutableData(bytes: samples, length: samples.count * MemoryLayout<Float>.size)
            let inputTensor = try ORTValue(
                tensorData: inputData,
                elementType: .float,
                shape: [1, 512] as [NSNumber]
            )

            // State tensor: [2, 1, 128] — combined hidden state for Silero v5
            let stateData = NSMutableData(bytes: state, length: state.count * MemoryLayout<Float>.size)
            let stateTensor = try ORTValue(
                tensorData: stateData,
                elementType: .float,
                shape: [2, 1, 128] as [NSNumber]
            )

            // Sample rate: scalar Int64
            var sr: Int64 = 16000
            let srData = NSMutableData(bytes: &sr, length: MemoryLayout<Int64>.size)
            let srTensor = try ORTValue(
                tensorData: srData,
                elementType: .int64,
                shape: [] as [NSNumber]
            )

            // Run inference
            let outputs = try session.run(
                withInputs: ["input": inputTensor, "state": stateTensor, "sr": srTensor],
                outputNames: Set(["output", "stateN"]),
                runOptions: nil
            )

            // Extract output probability from [1, 1] tensor
            guard let outputValue = outputs["output"] else { return 0.0 }
            let outputData = try outputValue.tensorData() as Data
            let probability = outputData.withUnsafeBytes { $0.load(as: Float.self) }

            // Update combined state from stateN output
            if let stateNValue = outputs["stateN"] {
                let stateNData = try stateNValue.tensorData() as Data
                stateNData.withUnsafeBytes { ptr in
                    let floats = ptr.bindMemory(to: Float.self)
                    if floats.count >= stateSize {
                        for i in 0..<stateSize {
                            state[i] = floats[i]
                        }
                    }
                }
            }

            return probability
        } catch {
            logError("VADGateService: Inference error", error: error)
            return 0.0
        }
    }

    func resetStates() {
        state = [Float](repeating: 0.0, count: stateSize)
    }
}

// MARK: - Gate State Machine

enum GateState {
    case silence
    case speech
    case hangover
}

struct GateOutput {
    let audioToSend: Data
    let shouldFinalize: Bool
}

// MARK: - DG Wall-Clock Timestamp Mapper

/// Maps Deepgram audio-time timestamps to wall-clock-relative timestamps.
/// When silence is skipped, DG time compresses vs wall time. This mapper
/// tracks checkpoints at silence-to-speech transitions to remap.
final class DgWallMapper {
    private let lock = NSLock()
    private var checkpoints: [(dgSec: Double, wallSec: Double)] = []
    private var dgCursorSec: Double = 0.0
    private var sending: Bool = false

    private let maxCheckpoints = 500

    func onAudioSent(chunkDuration: Double, wallTime: Double) {
        lock.lock()
        defer { lock.unlock() }

        if !sending {
            var adjustedWall = wallTime
            if let last = checkpoints.last {
                let minWall = last.wallSec + (dgCursorSec - last.dgSec)
                adjustedWall = max(wallTime, minWall)
            }
            checkpoints.append((dgSec: dgCursorSec, wallSec: adjustedWall))
            if checkpoints.count > maxCheckpoints {
                checkpoints = [checkpoints[0]] + Array(checkpoints.suffix(maxCheckpoints - 1))
            }
            sending = true
        }
        dgCursorSec += chunkDuration
    }

    func onSilenceSkipped() {
        lock.lock()
        defer { lock.unlock() }
        sending = false
    }

    func dgToWall(_ dgSec: Double) -> Double {
        lock.lock()
        let cps = checkpoints
        lock.unlock()

        guard !cps.isEmpty else { return dgSec }

        // Binary search for the right checkpoint
        var lo = 0, hi = cps.count - 1
        while lo < hi {
            let mid = (lo + hi + 1) / 2
            if cps[mid].dgSec <= dgSec {
                lo = mid
            } else {
                hi = mid - 1
            }
        }

        let cp = cps[lo]
        return cp.wallSec + (dgSec - cp.dgSec)
    }
}

// MARK: - VAD Gate Service

/// On-device VAD gate that skips silence to reduce Deepgram API usage.
/// Runs Silero VAD on each channel independently (deinterleaved from stereo).
/// Audio is gated when BOTH channels are silent.
final class VADGateService {
    // Constants matching backend vad_gate.py
    private let preRollMs: Double = 300
    private let hangoverMs: Double = 4000
    private let speechThreshold: Float = 0.65
    private let finalizeSilenceMs: Double = 300
    private let keepaliveSec: Double = 20
    private let vadWindowSamples = 512
    private let sampleRate = 16000

    // Two VAD models: one per channel (mic and system)
    private var micVAD: SileroVADModel?
    private var sysVAD: SileroVADModel?

    // VAD sample buffers (accumulate until >= 512 samples)
    private var micVADBuffer: [Float] = []
    private var sysVADBuffer: [Float] = []

    // State machine
    private var state: GateState = .silence
    private var audioCursorMs: Double = 0.0
    private var lastSpeechMs: Double = 0.0
    private var hangoverFinalized = false

    // Pre-roll buffer
    private var preRollChunks: [Data] = []
    private var preRollTotalMs: Double = 0.0

    // Timestamp mapper
    let dgWallMapper = DgWallMapper()

    // Timing
    private var firstAudioWallTime: Double?
    private var lastSendWallTime: Double?

    // Thread safety
    private let lock = NSLock()

    // Fail-open flag
    private let modelAvailable: Bool

    init() {
        let mic = SileroVADModel()
        let sys = SileroVADModel()
        micVAD = mic
        sysVAD = sys
        modelAvailable = mic != nil && sys != nil
        if modelAvailable {
            log("VADGateService: Initialized with Silero VAD models")
        } else {
            log("VADGateService: Model load failed — running in pass-through mode")
        }
    }

    /// Process stereo Int16 audio through the VAD gate.
    /// Returns audio to send (may be empty) and whether to finalize.
    func processAudio(_ stereoData: Data) -> GateOutput {
        // Fail-open: if models didn't load, pass everything through
        guard modelAvailable else {
            return GateOutput(audioToSend: stereoData, shouldFinalize: false)
        }

        lock.lock()
        defer { lock.unlock() }

        let wallTime = CACurrentMediaTime()
        if firstAudioWallTime == nil {
            firstAudioWallTime = wallTime
        }
        let wallRel = wallTime - (firstAudioWallTime ?? wallTime)

        // Calculate chunk duration
        // Stereo Int16: 2 channels * 2 bytes/sample = 4 bytes per frame
        let bytesPerFrame = 4
        let numFrames = stereoData.count / bytesPerFrame
        let chunkMs = Double(numFrames) * 1000.0 / Double(sampleRate)
        let chunkDurationSec = Double(numFrames) / Double(sampleRate)
        audioCursorMs += chunkMs

        // Deinterleave stereo into mic (even) and system (odd) channels
        let (micSamples, sysSamples) = deinterleave(stereoData)

        // Accumulate in VAD buffers
        micVADBuffer.append(contentsOf: micSamples)
        sysVADBuffer.append(contentsOf: sysSamples)

        // Run VAD when buffers have enough samples
        var micSpeech = false
        var sysSpeech = false

        if micVADBuffer.count >= vadWindowSamples, let vad = micVAD {
            while micVADBuffer.count >= vadWindowSamples {
                let window = Array(micVADBuffer.prefix(vadWindowSamples))
                micVADBuffer.removeFirst(vadWindowSamples)
                let prob = vad.predict(window)
                if prob > speechThreshold {
                    micSpeech = true
                }
            }
        }

        if sysVADBuffer.count >= vadWindowSamples, let vad = sysVAD {
            while sysVADBuffer.count >= vadWindowSamples {
                let window = Array(sysVADBuffer.prefix(vadWindowSamples))
                sysVADBuffer.removeFirst(vadWindowSamples)
                let prob = vad.predict(window)
                if prob > speechThreshold {
                    sysSpeech = true
                }
            }
        }

        // Keep buffers bounded
        if micVADBuffer.count > vadWindowSamples {
            micVADBuffer = Array(micVADBuffer.suffix(vadWindowSamples))
        }
        if sysVADBuffer.count > vadWindowSamples {
            sysVADBuffer = Array(sysVADBuffer.suffix(vadWindowSamples))
        }

        let isSpeech = micSpeech || sysSpeech

        if isSpeech {
            lastSpeechMs = audioCursorMs
        }

        // State machine
        return updateState(stereoData, isSpeech: isSpeech, wallRel: wallRel, chunkDurationSec: chunkDurationSec, chunkMs: chunkMs, wallTime: wallTime)
    }

    /// Check if a keepalive should be sent to prevent Deepgram timeout.
    func needsKeepalive() -> Bool {
        lock.lock()
        defer { lock.unlock() }

        guard let firstTime = firstAudioWallTime else { return false }
        let refTime = lastSendWallTime ?? firstTime
        return (CACurrentMediaTime() - refTime) >= keepaliveSec
    }

    /// Remap Deepgram timestamps to wall-clock-relative timestamps.
    func remapTimestamp(start: Double, end: Double) -> (Double, Double) {
        return (dgWallMapper.dgToWall(start), dgWallMapper.dgToWall(end))
    }

    // MARK: - Private

    private func updateState(_ pcmData: Data, isSpeech: Bool, wallRel: Double, chunkDurationSec: Double, chunkMs: Double, wallTime: Double) -> GateOutput {
        switch state {
        case .silence:
            // Buffer for pre-roll
            preRollChunks.append(pcmData)
            preRollTotalMs += chunkMs
            while preRollTotalMs > preRollMs && preRollChunks.count > 1 {
                let evicted = preRollChunks.removeFirst()
                let evictedMs = Double(evicted.count / 4) * 1000.0 / Double(sampleRate)
                preRollTotalMs -= evictedMs
            }

            if isSpeech {
                // SILENCE -> SPEECH
                state = .speech

                // Emit pre-roll + current chunk
                var preRollAudio = Data()
                for chunk in preRollChunks {
                    preRollAudio.append(chunk)
                }
                let preRollDuration = Double(preRollAudio.count / 4) / Double(sampleRate)
                let preRollWallRel = max(0.0, wallRel - preRollDuration + chunkDurationSec)

                preRollChunks.removeAll()
                preRollTotalMs = 0.0

                dgWallMapper.onAudioSent(chunkDuration: preRollDuration, wallTime: preRollWallRel)
                lastSendWallTime = wallTime

                return GateOutput(audioToSend: preRollAudio, shouldFinalize: false)
            } else {
                // Stay in SILENCE
                dgWallMapper.onSilenceSkipped()
                return GateOutput(audioToSend: Data(), shouldFinalize: false)
            }

        case .speech:
            // Send audio
            dgWallMapper.onAudioSent(chunkDuration: chunkDurationSec, wallTime: wallRel)
            lastSendWallTime = wallTime

            if !isSpeech {
                // SPEECH -> HANGOVER
                state = .hangover
                hangoverFinalized = false
            }

            return GateOutput(audioToSend: pcmData, shouldFinalize: false)

        case .hangover:
            let timeSinceSpeechMs = audioCursorMs - lastSpeechMs

            if isSpeech {
                // HANGOVER -> SPEECH
                state = .speech
                hangoverFinalized = false
                dgWallMapper.onAudioSent(chunkDuration: chunkDurationSec, wallTime: wallRel)
                lastSendWallTime = wallTime
                return GateOutput(audioToSend: pcmData, shouldFinalize: false)
            }

            if timeSinceSpeechMs > hangoverMs {
                // HANGOVER -> SILENCE
                state = .silence
                let needFinalize = !hangoverFinalized
                hangoverFinalized = false
                preRollChunks.removeAll()
                preRollTotalMs = 0.0
                preRollChunks.append(pcmData)
                preRollTotalMs = chunkMs
                dgWallMapper.onSilenceSkipped()
                return GateOutput(audioToSend: Data(), shouldFinalize: needFinalize)
            }

            // Mid-hangover finalize
            var shouldFinalizeNow = false
            if !hangoverFinalized && timeSinceSpeechMs >= finalizeSilenceMs {
                shouldFinalizeNow = true
                hangoverFinalized = true
            }

            // Still in hangover: send audio
            dgWallMapper.onAudioSent(chunkDuration: chunkDurationSec, wallTime: wallRel)
            lastSendWallTime = wallTime
            return GateOutput(audioToSend: pcmData, shouldFinalize: shouldFinalizeNow)
        }
    }

    /// Deinterleave stereo Int16 data into two Float32 arrays normalized to [-1.0, 1.0].
    private func deinterleave(_ stereoData: Data) -> ([Float], [Float]) {
        let sampleCount = stereoData.count / 2  // Int16 = 2 bytes
        let frameCount = sampleCount / 2  // 2 channels

        var mic = [Float]()
        mic.reserveCapacity(frameCount)
        var sys = [Float]()
        sys.reserveCapacity(frameCount)

        stereoData.withUnsafeBytes { ptr in
            let samples = ptr.bindMemory(to: Int16.self)
            for i in 0..<frameCount {
                mic.append(Float(samples[i * 2]) / 32768.0)
                sys.append(Float(samples[i * 2 + 1]) / 32768.0)
            }
        }

        return (mic, sys)
    }
}
