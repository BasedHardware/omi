import AVFoundation
import OmiService
@preconcurrency import TwilioVoice
import UIKit

/// The VoIP leg of a phone call: Twilio Voice places it from the app (`TwilioVoiceSDK.connect` with
/// `To` and `CallId`; the backend's TwiML webhook dials with the verified caller ID), CallKit shows it
/// as a system call, and a custom audio device taps both sides for the transcript.
/// Port of Flutter's `ios/Runner/PhoneCalls/OmiPhoneCallsPlugin.swift`. Outgoing only: Flutter has no
/// PushKit / incoming calls, so neither does this.
@MainActor
final class TwilioPhoneCallEngine: NSObject, PhoneCallEngine {
    private var prepared: (coordinator: any CallSystemCoordinator, audioDevice: CallRecordingAudioDevice)?
    private var call: Call?
    private var callUUID: UUID?
    private var events: AsyncStream<PhoneCallEngineEvent>.Continuation?
    private var audio: AsyncStream<PhoneCallAudio>.Continuation?
    private var coalescer: CallAudioCoalescer?

    func requestMicrophonePermission() async -> Bool {
        await AVAudioApplication.requestRecordPermission()
    }

    func start(_ request: PhoneCallRequest) async throws -> PhoneCallStreams {
        cleanup()
        let (coordinator, audioDevice) = prepare()
        let (eventStream, events) = AsyncStream.makeStream(of: PhoneCallEngineEvent.self)
        let (audioStream, audio) = AsyncStream.makeStream(of: PhoneCallAudio.self, bufferingPolicy: .bufferingNewest(64))
        self.events = events
        self.audio = audio
        let coalescer = CallAudioCoalescer { audio.yield($0) }
        self.coalescer = coalescer
        audioDevice.setTap { pcm, channel in coalescer.append(pcm, channel: channel) }
        audioDevice.setMicMuted(false)

        let uuid = UUID()
        callUUID = uuid
        try await coordinator.startCall(uuid: uuid, phoneNumber: request.phoneNumber, contactName: request.contactName)
        guard callUUID == uuid else { throw CancellationError() }
        let options = ConnectOptions(accessToken: request.accessToken) { builder in
            builder.params = ["To": request.phoneNumber, "CallId": request.callID]
            builder.uuid = uuid
        }
        call = TwilioVoiceSDK.connect(options: options, delegate: self)
        UIApplication.shared.isIdleTimerDisabled = true
        return PhoneCallStreams(events: eventStream, audio: audioStream)
    }

    func end() {
        let ending = call
        call = nil
        ending?.disconnect()
        if let uuid = callUUID { prepared?.coordinator.endCall(uuid: uuid) }
        events?.yield(.ended)
        cleanup()
    }

    func setMuted(_ muted: Bool) {
        call?.isMuted = muted
        prepared?.audioDevice.setMicMuted(muted)
        events?.yield(.muted(muted))
    }

    func setSpeaker(_ on: Bool) {
        do {
            try AVAudioSession.sharedInstance().overrideOutputAudioPort(on ? .speaker : .none)
            events?.yield(.speaker(on))
        } catch {
            // The route stays as it was; the button keeps showing it.
        }
    }

    func sendDigits(_ digits: String) {
        call?.sendDigits(digits)
    }

    // MARK: Setup and teardown

    /// CallKit and Twilio's audio device are set up with the first call, not at launch.
    private func prepare() -> (any CallSystemCoordinator, CallRecordingAudioDevice) {
        if let prepared { return prepared }
        let audioDevice = CallRecordingAudioDevice()
        let coordinator: any CallSystemCoordinator = CallRegion.isCallKitRestricted ? DirectCallCoordinator() : CallKitCoordinator()
        coordinator.onAudioSessionActivated = { _ = audioDevice.start() }
        coordinator.onSystemEndCall = { [weak self] in self?.systemEnded() }
        coordinator.onSystemMute = { [weak self] muted in self?.setMuted(muted) }
        coordinator.onReset = { [weak self] in self?.systemReset() }
        TwilioVoiceSDK.audioDevice = audioDevice
        prepared = (coordinator, audioDevice)
        return (coordinator, audioDevice)
    }

    /// Hung up from the lock screen or the system call UI.
    private func systemEnded() {
        guard let ending = call else { return }
        call = nil
        ending.disconnect()
        events?.yield(.ended)
        cleanup()
    }

    private func systemReset() {
        guard let ending = call else { return }
        call = nil
        ending.disconnect()
        events?.yield(.failed("Call system was reset"))
        cleanup()
    }

    private func cleanup() {
        call = nil
        callUUID = nil
        prepared?.audioDevice.setTap(nil)
        coalescer?.flush()
        coalescer = nil
        events?.finish()
        events = nil
        // The flushed tail is queued on the coalescer's queue; finish the audio stream after it.
        let audio = audio
        self.audio = nil
        Task {
            try? await Task.sleep(for: .milliseconds(200))
            audio?.finish()
        }
        UIDevice.current.isProximityMonitoringEnabled = false
        UIApplication.shared.isIdleTimerDisabled = false
    }

    fileprivate func report(_ event: PhoneCallEngineEvent, endedUUID: UUID? = nil, failed: Bool = false) {
        events?.yield(event)
        if let endedUUID {
            prepared?.coordinator.reportEnded(uuid: endedUUID, failed: failed)
            cleanup()
        }
    }
}

// Twilio delivers these on the main queue (ConnectOptions' default `delegateQueue`).
extension TwilioPhoneCallEngine: @preconcurrency CallDelegate {
    func callDidStartRinging(call _: Call) {
        // The phone at the ear turns the screen off.
        UIDevice.current.isProximityMonitoringEnabled = true
        report(.ringing)
    }

    func callDidConnect(call _: Call) {
        if let uuid = callUUID { prepared?.coordinator.reportConnected(uuid: uuid) }
        report(.connected)
    }

    func callDidFailToConnect(call: Call, error: any Error) {
        guard self.call === call, let uuid = callUUID else { return }
        report(.failed(error.localizedDescription), endedUUID: uuid, failed: true)
    }

    func callDidDisconnect(call: Call, error: (any Error)?) {
        guard self.call === call, let uuid = callUUID else { return }
        report(error.map { .failed($0.localizedDescription) } ?? .ended, endedUUID: uuid, failed: error != nil)
    }
}

/// Apple requires CallKit to be off for apps offered in China (Flutter `OmiRegionCheck`; the carrier
/// MCC fallback is gone, `CTCarrier` reports placeholders since iOS 16).
enum CallRegion {
    static var isCallKitRestricted: Bool {
        Locale.current.region?.identifier == "CN"
    }
}
