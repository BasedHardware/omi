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
    private var targetInputUid: String?

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
        // A phone call (or Siri) interruption stops the engine out from under us;
        // without observing it, isRunning stays true and capture dies silently.
        NotificationCenter.default.addObserver(
            self,
            selector: #selector(handleInterruption(_:)),
            name: AVAudioSession.interruptionNotification,
            object: nil
        )
        // The engine rebuilds its I/O when the hardware format changes (e.g. the
        // HFP route drops to the built-in mic); the tap installed at start() is
        // frozen at the old format, so continuing would emit garbage or silence.
        NotificationCenter.default.addObserver(
            self,
            selector: #selector(handleEngineConfigurationChange(_:)),
            name: .AVAudioEngineConfigurationChange,
            object: engine
        )
    }

    deinit {
        NotificationCenter.default.removeObserver(self)
    }

    /// Bluetooth HFP input ports currently available. AVAudioSession's UID is
    /// stable when the user renames the device; portName is not.
    static func availableHfpInputs() -> [(uid: String, name: String)] {
        let session = AVAudioSession.sharedInstance()
        return (session.availableInputs ?? [])
            .filter { $0.portType == .bluetoothHFP }
            .map { (uid: $0.uid, name: $0.portName) }
    }

    /// True when the active input route is a Bluetooth HFP port.
    static func isHfpRouteActive(inputUid: String? = nil) -> Bool {
        return AVAudioSession.sharedInstance().currentRoute.inputs.contains {
            $0.portType == .bluetoothHFP && (inputUid == nil || $0.uid == inputUid)
        }
    }

    var isSelectedRouteActive: Bool { Self.isHfpRouteActive(inputUid: targetInputUid) }

    func start(targetUid: String?) throws {
        guard !isRunning else { return }

        let session = AVAudioSession.sharedInstance()
        try session.setCategory(.playAndRecord, mode: .default, options: [.allowBluetoothHFP])

        let hfpInputs = (session.availableInputs ?? []).filter { $0.portType == .bluetoothHFP }
        let selectedInput: AVAudioSessionPortDescription?
        if let targetUid {
            selectedInput = hfpInputs.first { $0.uid == targetUid }
            guard selectedInput != nil else {
                throw NSError(
                    domain: "RayBanMetaAudioCapture", code: 3,
                    userInfo: [NSLocalizedDescriptionKey: "Selected Bluetooth microphone is unavailable"]
                )
            }
        } else {
            // DAT mode does not expose a mapping from its device ID to the HFP
            // port UID, so preserve its existing first-HFP behavior.
            selectedInput = hfpInputs.first
        }

        if let hfpInput = selectedInput {
            try session.setPreferredInput(hfpInput)
        }
        targetInputUid = targetUid

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
            guard let self else { return }
            self.onRouteChanged?(self.isSelectedRouteActive)
        }
    }

    func stop() {
        guard isRunning else { return }
        engine.inputNode.removeTap(onBus: 0)
        engine.stop()
        converter = nil
        isRunning = false
        targetInputUid = nil

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
        let hfpActive = isSelectedRouteActive
        onRouteChanged?(hfpActive)
        // Losing the glasses' HFP input mid-capture means the tap is now fed by
        // whatever input took over (usually the phone mic) at a stale format.
        // Stop and surface it instead of silently recording the wrong source.
        if isRunning && !hfpActive {
            DispatchQueue.main.async { [weak self] in
                guard let self = self, self.isRunning, !self.isSelectedRouteActive else { return }
                self.stop()
                self.onError?("audio_route_lost", "Glasses microphone route was lost during capture")
            }
        }
    }

    @objc private func handleInterruption(_ notification: Notification) {
        guard
            let info = notification.userInfo,
            let typeValue = info[AVAudioSessionInterruptionTypeKey] as? UInt,
            let type = AVAudioSession.InterruptionType(rawValue: typeValue)
        else { return }
        if type == .began && isRunning {
            DispatchQueue.main.async { [weak self] in
                guard let self = self, self.isRunning else { return }
                self.stop()
                self.onError?("audio_interrupted", "Audio capture was interrupted (phone call or another app)")
            }
        }
    }

    @objc private func handleEngineConfigurationChange(_ notification: Notification) {
        guard isRunning else { return }
        DispatchQueue.main.async { [weak self] in
            guard let self = self, self.isRunning else { return }
            self.stop()
            self.onError?("audio_config_changed", "Audio input configuration changed during capture")
        }
    }
}
