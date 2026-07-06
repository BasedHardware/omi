import AVFoundation
import Foundation

/// Captures the Ray-Ban Meta glasses microphone over the Bluetooth HFP route.
///
/// The Meta Wearables Device Access Toolkit has no microphone API; Meta's
/// documented input path is HFP through AVAudioSession. This engine prefers
/// the glasses' HFP input port, taps the input node, converts to PCM16 mono
/// 16 kHz, and hands frames to the caller. It has no DAT dependency, so the
/// labeled audio-only fallback works on builds without the SDK.
///
/// Ordering caveat from Meta's docs: when combining with DAT camera streaming,
/// HFP must be fully active before the camera stream starts or the audio route
/// can fail silently. RayBanMetaHostApiImpl sequences that.
final class RayBanMetaAudioCapture {
    static let targetSampleRate: Double = 16000.0

    private let engine = AVAudioEngine()
    private var converter: AVAudioConverter?
    private var isRunning = false

    /// PCM16 little-endian mono frames at targetSampleRate.
    var onFrame: ((Data, Double) -> Void)?
    /// Reports whether the active input route is a Bluetooth HFP port.
    var onRouteChanged: ((Bool) -> Void)?
    var onError: ((String, String) -> Void)?

    init() {
        NotificationCenter.default.addObserver(
            self,
            selector: #selector(handleRouteChange(_:)),
            name: AVAudioSession.routeChangeNotification,
            object: nil
        )
    }

    deinit {
        NotificationCenter.default.removeObserver(self)
    }

    /// Bluetooth HFP input port names currently available.
    static func availableHfpInputNames() -> [String] {
        let session = AVAudioSession.sharedInstance()
        return (session.availableInputs ?? [])
            .filter { $0.portType == .bluetoothHFP }
            .map { $0.portName }
    }

    /// True when the active input route is a Bluetooth HFP port.
    static func isHfpRouteActive() -> Bool {
        return AVAudioSession.sharedInstance().currentRoute.inputs.contains { $0.portType == .bluetoothHFP }
    }

    func start() throws {
        guard !isRunning else { return }

        let session = AVAudioSession.sharedInstance()
        try session.setCategory(.playAndRecord, mode: .default, options: [.allowBluetoothHFP])

        // Prefer the glasses' HFP mic over the built-in one.
        if let hfpInput = (session.availableInputs ?? []).first(where: { $0.portType == .bluetoothHFP }) {
            try session.setPreferredInput(hfpInput)
        }

        try session.setActive(true, options: .notifyOthersOnDeactivation)

        let input = engine.inputNode
        let inputFormat = input.inputFormat(forBus: 0)
        guard inputFormat.sampleRate > 0 else {
            throw NSError(
                domain: "RayBanMetaAudioCapture", code: 1,
                userInfo: [NSLocalizedDescriptionKey: "Audio input format unavailable"]
            )
        }

        guard
            let outputFormat = AVAudioFormat(
                commonFormat: .pcmFormatInt16,
                sampleRate: Self.targetSampleRate,
                channels: 1,
                interleaved: true
            ),
            let converter = AVAudioConverter(from: inputFormat, to: outputFormat)
        else {
            throw NSError(
                domain: "RayBanMetaAudioCapture", code: 2,
                userInfo: [NSLocalizedDescriptionKey: "Could not build PCM16/16kHz converter"]
            )
        }
        self.converter = converter

        input.installTap(onBus: 0, bufferSize: 4096, format: inputFormat) { [weak self] buffer, _ in
            self?.convertAndEmit(buffer: buffer, outputFormat: outputFormat)
        }

        engine.prepare()
        try engine.start()
        isRunning = true

        // Give the Bluetooth route a moment to settle, then report it. Meta's
        // guidance: the HFP route can take ~2s to stabilize after engine start.
        DispatchQueue.main.asyncAfter(deadline: .now() + 2.0) { [weak self] in
            self?.onRouteChanged?(Self.isHfpRouteActive())
        }
    }

    func stop() {
        guard isRunning else { return }
        engine.inputNode.removeTap(onBus: 0)
        engine.stop()
        converter = nil
        isRunning = false

        do {
            try AVAudioSession.sharedInstance().setActive(false, options: .notifyOthersOnDeactivation)
        } catch {
            // Deactivation failure is non-fatal; another component may hold the session.
        }
    }

    var running: Bool { isRunning }

    private func convertAndEmit(buffer: AVAudioPCMBuffer, outputFormat: AVAudioFormat) {
        guard let converter = converter else { return }

        let ratio = outputFormat.sampleRate / buffer.format.sampleRate
        let capacity = AVAudioFrameCount(Double(buffer.frameLength) * ratio) + 16
        guard let outBuffer = AVAudioPCMBuffer(pcmFormat: outputFormat, frameCapacity: capacity) else { return }

        var fed = false
        var conversionError: NSError?
        converter.convert(to: outBuffer, error: &conversionError) { _, outStatus in
            if fed {
                outStatus.pointee = .noDataNow
                return nil
            }
            fed = true
            outStatus.pointee = .haveData
            return buffer
        }

        if let conversionError = conversionError {
            onError?("audio_convert", conversionError.localizedDescription)
            return
        }

        guard outBuffer.frameLength > 0, let channel = outBuffer.int16ChannelData?[0] else { return }
        let data = Data(bytes: channel, count: Int(outBuffer.frameLength) * MemoryLayout<Int16>.size)
        onFrame?(data, Self.targetSampleRate)
    }

    @objc private func handleRouteChange(_ notification: Notification) {
        onRouteChanged?(Self.isHfpRouteActive())
    }
}
