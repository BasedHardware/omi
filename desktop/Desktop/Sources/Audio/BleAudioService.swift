import Combine
import Foundation
import os.log

// MARK: - BLE Audio Service

/// Service that coordinates BLE device audio processing and transcription
/// Connects device connections to the transcription pipeline
@MainActor
final class BleAudioService: ObservableObject {

    // MARK: - Singleton

    static let shared = BleAudioService()

    // MARK: - Published Properties

    @Published private(set) var isProcessing = false
    @Published private(set) var currentCodec: BleAudioCodec?
    @Published private(set) var audioLevel: Float = 0.0

    // MARK: - Properties

    private let logger = Logger(subsystem: "me.omi.desktop", category: "BleAudioService")
    private var processor: BleAudioProcessor?
    private var audioStreamTask: Task<Void, Never>?
    private var cancellables = Set<AnyCancellable>()

    // Audio delivery
    private var transcriptionService: TranscriptionService?
    private var audioDataHandler: ((Data) -> Void)?
    private var rawFrameHandler: ((Data) -> Void)?

    // Statistics
    private var totalSamplesProcessed: Int = 0
    private var startTime: Date?

    // MARK: - Initialization

    private init() {}

    // MARK: - Public Methods

    /// Start processing audio from a device connection
    /// - Parameters:
    ///   - connection: The device connection to get audio from
    ///   - transcriptionService: Optional transcription service to send audio to
    ///   - audioDataHandler: Optional handler for decoded PCM data (alternative to transcription)
    ///   - rawFrameHandler: Optional handler for raw encoded frames (for WAL recording)
    func startProcessing(
        from connection: DeviceConnection,
        transcriptionService: TranscriptionService? = nil,
        audioDataHandler: ((Data) -> Void)? = nil,
        rawFrameHandler: ((Data) -> Void)? = nil
    ) async {
        guard !isProcessing else {
            logger.warning("Already processing audio")
            return
        }

        self.transcriptionService = transcriptionService
        self.audioDataHandler = audioDataHandler
        self.rawFrameHandler = rawFrameHandler

        // Get codec from device
        let codec = await connection.getAudioCodec()
        currentCodec = codec

        // Check if codec is supported
        if !AudioDecoderFactory.isSupported(codec) {
            logger.error("Unsupported audio codec: \(codec.name)")
            return
        }

        // Warn if codec has partial support
        if !AudioDecoderFactory.hasFullSupport(codec) {
            logger.warning("Codec \(codec.name) has partial support - audio quality may be affected")
        }

        // Create processor
        processor = BleAudioProcessor(codec: codec)

        // Subscribe to decoded PCM data
        processor?.pcmDataPublisher
            .receive(on: DispatchQueue.main)
            .sink { [weak self] pcmData in
                self?.handleDecodedAudio(pcmData)
            }
            .store(in: &cancellables)

        // Start audio stream from device
        let audioStream = connection.getAudioStream()

        isProcessing = true
        startTime = Date()
        totalSamplesProcessed = 0

        logger.info("Started processing audio with codec: \(codec.name)")

        // Process audio stream
        audioStreamTask = Task { [weak self] in
            do {
                for try await audioData in audioStream {
                    guard let self = self, self.isProcessing else { break }

                    // Process based on device type
                    await self.processDeviceAudio(audioData, from: connection)
                }
            } catch {
                self?.logger.error("Audio stream error: \(error.localizedDescription)")
            }

            await MainActor.run {
                self?.isProcessing = false
            }
        }
    }

    /// Stop processing audio
    func stopProcessing() {
        guard isProcessing else { return }

        audioStreamTask?.cancel()
        audioStreamTask = nil
        processor?.reset()
        cancellables.removeAll()

        isProcessing = false
        transcriptionService = nil
        audioDataHandler = nil
        rawFrameHandler = nil

        // Log statistics
        if let start = startTime {
            let duration = Date().timeIntervalSince(start)
            let stats = processor?.getStatistics() ?? (frames: 0, bytes: 0, lostPackets: 0)
            logger.info("Stopped processing. Duration: \(String(format: "%.1f", duration))s, Frames: \(stats.frames), Bytes: \(stats.bytes), Lost: \(stats.lostPackets)")
        }

        startTime = nil
        processor = nil
        currentCodec = nil
    }

    // MARK: - Private Methods

    /// Process audio data from a device
    private func processDeviceAudio(_ data: Data, from connection: DeviceConnection) async {
        guard let processor = processor else { return }

        // Capture raw frame for WAL recording
        rawFrameHandler?(data)

        // Different devices need different handling
        let deviceType = connection.device.type

        switch deviceType {
        case .fieldy:
            // Fieldy sends pre-framed 40-byte Opus frames
            processor.processAudioData(data)

        case .friendPendant:
            // Friend Pendant sends 30-byte LC3 frames (already extracted by connection)
            processor.processAudioData(data)

        case .bee:
            // Bee sends ADTS-framed AAC (already parsed by connection)
            processor.processFrame(data)

        case .limitless:
            // Limitless sends Opus frames extracted from protobuf
            processor.processFrame(data)

        case .plaud:
            // PLAUD sends chunked Opus data
            processor.processAudioData(data)

        case .omi, .openglass:
            // Omi devices send packet-framed audio
            processor.processAudioData(data)

        default:
            // Default: treat as raw frames
            processor.processAudioData(data)
        }
    }

    /// Handle decoded PCM audio
    private func handleDecodedAudio(_ pcmData: Data) {
        guard !pcmData.isEmpty else { return }

        totalSamplesProcessed += pcmData.count / 2

        // Calculate audio level
        updateAudioLevel(from: pcmData)

        // Send to transcription service (mono channel)
        if let transcription = transcriptionService {
            // TranscriptionService expects stereo (2 channels) for multichannel transcription
            // For BLE device audio, we duplicate to both channels (device is the "user")
            let stereoData = convertToStereo(pcmData)
            transcription.sendAudio(stereoData)
        }

        // Send to custom handler
        audioDataHandler?(pcmData)
    }

    /// Convert mono PCM to stereo (duplicate to both channels)
    private func convertToStereo(_ monoData: Data) -> Data {
        // Mono: [S0, S1, S2, ...]
        // Stereo: [S0, S0, S1, S1, S2, S2, ...] (interleaved)
        var stereoData = Data(capacity: monoData.count * 2)

        monoData.withUnsafeBytes { bytes in
            let samples = bytes.bindMemory(to: Int16.self)
            for i in 0..<samples.count {
                var sample = samples[i]
                // Write same sample to both channels
                stereoData.append(Data(bytes: &sample, count: 2))
                stereoData.append(Data(bytes: &sample, count: 2))
            }
        }

        return stereoData
    }

    /// Calculate RMS audio level from PCM data
    private func updateAudioLevel(from data: Data) {
        var sumSquares: Float = 0
        let sampleCount = data.count / 2

        data.withUnsafeBytes { bytes in
            let samples = bytes.bindMemory(to: Int16.self)
            for i in 0..<samples.count {
                let sample = Float(samples[i]) / 32768.0
                sumSquares += sample * sample
            }
        }

        let rms = sqrt(sumSquares / Float(max(sampleCount, 1)))
        // Smooth the level
        audioLevel = audioLevel * 0.7 + rms * 0.3
    }
}

// MARK: - Convenience Extensions

extension BleAudioService {

    /// Check if a device's audio codec is supported
    func isCodecSupported(for connection: DeviceConnection) async -> Bool {
        let codec = await connection.getAudioCodec()
        return AudioDecoderFactory.isSupported(codec)
    }

    /// Get codec information for a device
    func getCodecInfo(for connection: DeviceConnection) async -> (codec: BleAudioCodec, supported: Bool, name: String) {
        let codec = await connection.getAudioCodec()
        let supported = AudioDecoderFactory.isSupported(codec)
        return (codec, supported, codec.name)
    }
}

// MARK: - Integration with DeviceProvider

