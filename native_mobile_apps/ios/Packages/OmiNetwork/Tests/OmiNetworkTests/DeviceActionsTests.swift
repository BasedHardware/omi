import Foundation
import OmiCore
@testable import OmiNetwork
import Testing

struct VoiceMessageParsingTests {
    /// `v2/voice-messages` frames: the transcribed question, then ordinary chat frames.
    @Test func parsesQuestionAnswerAndNoSpeech() {
        let json = #"{"id":"h1","text":"What is on today?","sender":"human","created_at":"2026-10-07T09:00:00Z"}"#
        guard case let .question(message) = VoiceMessageEvent.parse("message: " + Data(json.utf8).base64EncodedString()) else {
            Issue.record("expected the question")
            return
        }
        #expect(message.text == "What is on today?")
        #expect(message.sender == .user)
        #expect(VoiceMessageEvent.parse("data: Two calls") == .chat(.delta("Two calls")))
        let noSpeech = #"error: {"error":"no_speech","outcome":"expected_silence","retryable":true,"message":"No speech was detected."}"#
        #expect(VoiceMessageEvent.parse(noSpeech) == .noSpeech)
        #expect(VoiceMessageEvent.parse(#"error: {"error":"stt_failed","message":"Try again"}"#) == .chat(.failed("Try again")))
        #expect(VoiceMessageEvent.parse("error:402:Out of questions") == .chat(.failed("Out of questions")))
        #expect(VoiceMessageEvent.parse("message: not-base64") == nil)
    }

    /// Flutter `FileUtils.saveAudioBytesToTempFile`: `[u32 LE length][frame]…`; the backend reads `_fs<n>`.
    @Test func buildsTheUploadFile() {
        let file = VoiceMessageEvent.file(
            frames: [Data([0x01, 0x02, 0x03]), Data([0xFF])], codec: "opus", sampleRate: 16000, frameSamples: 160,
            startedAt: Date(timeIntervalSince1970: 1_790_000_000)
        )
        #expect(file.name == "audio_omi_opus_16000_1_fs160_1790000000.bin")
        #expect(file.data == Data([3, 0, 0, 0, 0x01, 0x02, 0x03, 1, 0, 0, 0, 0xFF]))
    }

    @Test func listenURLCarriesConversationTimeout() throws {
        let options = ListenSocket.Options(codec: .opusFS320, source: .omi, conversationTimeout: -1)
        let base = try #require(URL(string: "https://api.omi.me/"))
        let url = ListenSocket.url(base: base, uid: "u1", options: options)
        let items = URLComponents(url: url, resolvingAgainstBaseURL: false)?.queryItems ?? []
        #expect(items.first { $0.name == "conversation_timeout" }?.value == "-1")
    }

    /// A reopened socket names the same recording, so the backend resumes its conversation.
    @Test func listenURLCarriesTheRecordingID() throws {
        let options = ListenSocket.Options(codec: .opusFS320, source: .omi)
        let base = try #require(URL(string: "https://api.omi.me/"))
        let ids = [options, options, ListenSocket.Options(codec: .opusFS320, source: .omi)].map { options in
            URLComponents(url: ListenSocket.url(base: base, uid: "u1", options: options), resolvingAgainstBaseURL: false)?
                .queryItems?.first { $0.name == "client_conversation_id" }?.value
        }
        #expect(ids[0] == options.clientConversationID)
        #expect(ids[1] == ids[0])
        #expect(ids[2] != ids[0])
    }
}

struct DeviceDiagnosticsUploadTests {
    /// `POST v1/mobile/device-diagnostics` answers {"ticket": ...}; anything else is a decoding error.
    @Test func readsTheSupportTicket() throws {
        #expect(try APIClient.diagnosticsTicket(from: Data(#"{"ticket":"0A1B2C3D4E5F"}"#.utf8)) == "0A1B2C3D4E5F")
        #expect(throws: APIError.self) { try APIClient.diagnosticsTicket(from: Data(#"{"ok":true}"#.utf8)) }
    }
}
