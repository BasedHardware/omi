import Foundation
import OmiNetwork

/// The VoIP leg of a call (Twilio Voice + CallKit in the app; a fake in tests). The call itself is
/// placed by Twilio from the app (`TwilioVoiceSDK.connect`), Twilio's TwiML webhook dials the number
/// with the user's verified caller ID (backend `/v1/phone/twiml`); there is no bridging to the
/// phone's own dialer. Flutter: `ios/Runner/PhoneCalls/OmiPhoneCallsPlugin.swift`.
@MainActor
public protocol PhoneCallEngine: AnyObject {
    func requestMicrophonePermission() async -> Bool
    /// Asks the system for the call (CallKit) and connects it; events and audio follow on the streams.
    func start(_ request: PhoneCallRequest) async throws -> PhoneCallStreams
    func end()
    func setMuted(_ muted: Bool)
    func setSpeaker(_ on: Bool)
    /// DTMF tones (menus, extensions).
    func sendDigits(_ digits: String)
}

public struct PhoneCallRequest: Sendable, Equatable {
    public let accessToken: String
    /// E.164 destination (`To` of the TwiML request).
    public let phoneNumber: String
    /// Carried as `CallId` to the TwiML webhook and as `call_id` to the transcription socket.
    public let callID: String
    public let contactName: String?

    public init(accessToken: String, phoneNumber: String, callID: String, contactName: String?) {
        self.accessToken = accessToken
        self.phoneNumber = phoneNumber
        self.callID = callID
        self.contactName = contactName
    }
}

public enum PhoneCallEngineEvent: Sendable, Equatable {
    case ringing
    case connected
    /// Hung up (either side, or from the system call UI).
    case ended
    case failed(String)
    /// Confirmed by the engine, including mute from the system call UI.
    case muted(Bool)
    case speaker(Bool)
}

/// About 100 ms of one side of the call: PCM16 mono at 48 kHz.
public struct PhoneCallAudio: Sendable, Equatable {
    public enum Channel: UInt8, Sendable { case you = 1, them = 2 }
    public let channel: Channel
    public let pcm16: Data

    public init(channel: Channel, pcm16: Data) {
        self.channel = channel
        self.pcm16 = pcm16
    }
}

public struct PhoneCallStreams: Sendable {
    public let events: AsyncStream<PhoneCallEngineEvent>
    public let audio: AsyncStream<PhoneCallAudio>

    public init(events: AsyncStream<PhoneCallEngineEvent>, audio: AsyncStream<PhoneCallAudio>) {
        self.events = events
        self.audio = audio
    }
}

/// Why a call did not start or ended early; the screens word it.
public enum PhoneCallFailure: Error, Equatable, Sendable {
    case alreadyInProgress
    case microphonePermission
    case noVerifiedNumber
    /// The backend refused (no verified number, plan without calls, quota reached …).
    case server(PhoneCallErrorDetail?)
    /// The call system or Twilio failed; the message is theirs.
    case engine(String)
}
