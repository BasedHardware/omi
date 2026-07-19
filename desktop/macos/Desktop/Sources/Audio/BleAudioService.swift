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
  @Published private(set) var isDecodeDegraded = false

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
    // Claim the slot synchronously, before the first await, so two overlapping
    // startProcessing calls cannot both pass the guard and double-create the
    // processor (the second would orphan the first's processor + stream task).
    isProcessing = true

    self.transcriptionService = transcriptionService
    self.audioDataHandler = audioDataHandler
    self.rawFrameHandler = rawFrameHandler

    // Get codec from device
    let codec = await connection.getAudioCodec()
    currentCodec = codec

    // Check if codec is supported
    if !AudioDecoderFactory.isSupported(codec) {
      logger.error("Unsupported audio codec: \(codec.name)")
      // Release the claimed slot and drop the handlers captured above.
      stopProcessing()
      return
    }

    // Warn if codec has partial support
    if !AudioDecoderFactory.hasFullSupport(codec) {
      logger.warning("Codec \(codec.name) has partial support - audio quality may be affected")
    }

    // Create processor
    processor = BleAudioProcessor(codec: codec)
    processor?.delegate = self
    isDecodeDegraded = false

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

      // The stream ended or errored. Run full cleanup (not just isProcessing =
      // false), otherwise the processor, Combine subscriptions, and handlers
      // dangle and the session cannot cleanly restart.
      await self?.handleAudioStreamEnded()
    }
  }

  /// Full teardown after the device audio stream ends or errors on its own.
  private func handleAudioStreamEnded() {
    guard isProcessing else { return }
    logger.info("Audio stream ended; tearing down processing")
    stopProcessing()
  }

  /// Stop processing audio. Idempotent: safe to call after the stream has
  /// already ended (the old `guard isProcessing` early-return skipped cleanup
  /// in exactly that case, leaving the session unrecoverable).
  func stopProcessing() {
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
      logger.info(
        "Stopped processing. Duration: \(String(format: "%.1f", duration))s, Frames: \(stats.frames), Bytes: \(stats.bytes), Lost: \(stats.lostPackets)"
      )
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

    // Send to transcription service (mono — Python backend handles diarization server-side)
    if let transcription = transcriptionService {
      transcription.sendAudio(pcmData)
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

// MARK: - BleAudioProcessorDelegate

extension BleAudioService: BleAudioProcessor.Delegate {
  nonisolated func bleAudioProcessor(_ processor: BleAudioProcessor, didDecodeSamples samples: [Int16]) {
    // PCM delivery uses pcmDataPublisher; delegate path is unused.
    // Reset the degraded flag on successful decode so it reflects the
    // current processor state rather than staying sticky.
    Task { @MainActor [weak self] in
      guard let self, self.isDecodeDegraded else { return }
      self.isDecodeDegraded = false
      self.logger.info("BLE decode recovered — clearing degraded flag")
    }
  }

  nonisolated func bleAudioProcessor(_ processor: BleAudioProcessor, didFailWithError error: Error) {
    Task { @MainActor [weak self] in
      guard let self else { return }
      self.isDecodeDegraded = true
      self.logger.error("BLE decode degraded: \(error.localizedDescription)")
    }
  }
}

// MARK: - Integration with DeviceProvider
