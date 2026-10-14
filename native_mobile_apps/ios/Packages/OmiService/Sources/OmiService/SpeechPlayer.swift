@preconcurrency import AVFoundation
import Foundation

/// Plays spoken answers. `play` and `speak` return when the audio ends or `stop` is called.
@MainActor
public protocol SpeechAudioPlaying: AnyObject {
    /// An MP3 from the backend voice.
    func play(_ audio: Data) async throws
    /// The system voice, when the backend voice is unavailable.
    func speak(_ text: String) async
    func stop()
}

/// `AVAudioPlayer` for backend audio, `AVSpeechSynthesizer` as the stand-in. Ducks other audio while
/// it talks, and leaves the audio session alone while the phone records (it already plays and records).
@MainActor
public final class SystemSpeechPlayer: NSObject, SpeechAudioPlaying {
    private var player: AVAudioPlayer?
    private let synthesizer = AVSpeechSynthesizer()
    private var finished: CheckedContinuation<Void, Never>?
    private var ownsSession = false
    /// The player or utterance now sounding: a late "finished" from an earlier one is ignored.
    private var current: ObjectIdentifier?

    override public init() {
        super.init()
        synthesizer.delegate = self
    }

    public func play(_ audio: Data) async throws {
        endCurrent()
        let player = try AVAudioPlayer(data: audio)
        player.delegate = self
        self.player = player
        current = ObjectIdentifier(player)
        activateSession()
        await withCheckedContinuation { continuation in
            finished = continuation
            if !player.play() { endCurrent() }
        }
    }

    public func speak(_ text: String) async {
        endCurrent()
        activateSession()
        await withCheckedContinuation { continuation in
            finished = continuation
            let utterance = AVSpeechUtterance(string: text)
            current = ObjectIdentifier(utterance)
            synthesizer.speak(utterance)
        }
    }

    public func stop() {
        player?.stop()
        if synthesizer.isSpeaking { synthesizer.stopSpeaking(at: .immediate) }
        endCurrent()
        deactivateSession()
    }

    private func endCurrent() {
        player = nil
        current = nil
        finished?.resume()
        finished = nil
    }

    fileprivate func ended(_ source: ObjectIdentifier) {
        guard source == current else { return }
        endCurrent()
        deactivateSession()
    }

    private func activateSession() {
        #if os(iOS)
            let session = AVAudioSession.sharedInstance()
            guard session.category != .playAndRecord else { return }
            try? session.setCategory(.playback, mode: .spokenAudio, options: [.duckOthers])
            try? session.setActive(true)
            ownsSession = true
        #endif
    }

    private func deactivateSession() {
        #if os(iOS)
            guard ownsSession else { return }
            ownsSession = false
            try? AVAudioSession.sharedInstance().setActive(false, options: .notifyOthersOnDeactivation)
        #endif
    }
}

extension SystemSpeechPlayer: AVAudioPlayerDelegate {
    public nonisolated func audioPlayerDidFinishPlaying(_ player: AVAudioPlayer, successfully _: Bool) {
        let source = ObjectIdentifier(player)
        Task { @MainActor in self.ended(source) }
    }

    public nonisolated func audioPlayerDecodeErrorDidOccur(_ player: AVAudioPlayer, error _: (any Error)?) {
        let source = ObjectIdentifier(player)
        Task { @MainActor in self.ended(source) }
    }
}

extension SystemSpeechPlayer: AVSpeechSynthesizerDelegate {
    public nonisolated func speechSynthesizer(_: AVSpeechSynthesizer, didFinish utterance: AVSpeechUtterance) {
        let source = ObjectIdentifier(utterance)
        Task { @MainActor in self.ended(source) }
    }

    public nonisolated func speechSynthesizer(_: AVSpeechSynthesizer, didCancel utterance: AVSpeechUtterance) {
        let source = ObjectIdentifier(utterance)
        Task { @MainActor in self.ended(source) }
    }
}

/// Where audio comes out of the phone.
public enum AudioRoute {
    /// Headphones of any kind (wired, AirPods and other Bluetooth, USB, AirPlay, line out): private
    /// listening. The built-in speaker and car audio are not.
    @MainActor
    public static var isPrivate: Bool {
        if case .headphones = current { return true }
        return false
    }

    /// Where spoken answers would play right now.
    public enum Output: Equatable, Sendable {
        /// Private listening; the name of the headphones when iOS gives one ("Ada's AirPods").
        case headphones(name: String?)
        /// The phone speaker, or car audio.
        case speaker
    }

    @MainActor
    public static var current: Output {
        #if os(iOS)
            let privatePorts: Set<AVAudioSession.Port> = [
                .headphones, .bluetoothA2DP, .bluetoothLE, .bluetoothHFP, .usbAudio, .airPlay, .lineOut,
            ]
            let output = AVAudioSession.sharedInstance().currentRoute.outputs.first { privatePorts.contains($0.portType) }
            return output.map { .headphones(name: $0.portName.isEmpty ? nil : $0.portName) } ?? .speaker
        #else
            return .speaker
        #endif
    }
}
