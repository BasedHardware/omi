import Foundation
@testable import OmiNetwork
import Testing

/// The wire shapes of the user's own speech-to-text providers (Flutter `buildRequestConfig`).
struct CustomSTTTests {
    private func body(_ request: URLRequest) -> String {
        String(bytes: request.httpBody ?? Data(), encoding: .utf8) ?? ""
    }

    @Test func openAIUploadsAWavWithBearerAuthAndSegmentTimes() throws {
        let config = CustomSTTConfig(provider: .openai, apiKey: "sk-test", language: "de")
        let request = try CustomSTTRequests.upload(config, wav: Data("WAV".utf8), boundary: "B")
        #expect(request.url?.absoluteString == "https://api.openai.com/v1/audio/transcriptions")
        #expect(request.value(forHTTPHeaderField: "Authorization") == "Bearer sk-test")
        #expect(request.value(forHTTPHeaderField: "Content-Type") == "multipart/form-data; boundary=B")
        let text = body(request)
        #expect(text.contains("name=\"model\"\r\n\r\nwhisper-1\r\n"))
        #expect(text.contains("name=\"response_format\"\r\n\r\nverbose_json\r\n"))
        #expect(text.contains("name=\"language\"\r\n\r\nde\r\n"))
        #expect(text.contains("filename=\"audio.wav\"\r\nContent-Type: audio/wav\r\n\r\nWAV\r\n--B--"))
    }

    @Test func detectSendsNoLanguageAndLocalWhisperNoKey() throws {
        let url = "http://192.0.2.5:8080/inference"
        let config = CustomSTTConfig(provider: .localWhisper, apiKey: "ignored", language: "multi", url: url)
        let request = try CustomSTTRequests.upload(config, wav: Data(), boundary: "B")
        #expect(request.url?.absoluteString == "http://192.0.2.5:8080/inference")
        #expect(request.value(forHTTPHeaderField: "Authorization") == nil)
        #expect(!body(request).contains("name=\"language\""))
        #expect(body(request).contains("name=\"temperature\"\r\n\r\n0.0"))
    }

    @Test func incompleteSetupsAreRefused() {
        #expect(!CustomSTTConfig(provider: .openai, apiKey: " ").isComplete)
        #expect(!CustomSTTConfig(provider: .custom, url: "ftp://x").isComplete)
        #expect(CustomSTTConfig(provider: .custom).isComplete) // the default local endpoint
        let live = CustomSTTConfig(provider: .deepgramLive, apiKey: "k")
        #expect(throws: CustomSTTError.incomplete) { try CustomSTTRequests.upload(live, wav: Data()) }
    }

    @Test func answersBecomeSegments() throws {
        let openAI = Data(#"{"text":"Hi there","segments":[{"start":0.2,"end":1.4,"text":" Hi "},"#.utf8)
            + Data(#"{"start":1.5,"end":2,"text":"there"}]}"#.utf8)
        #expect(try CustomSTTRequests.segments(from: openAI, duration: 3) == [
            CustomSTTSegment(text: "Hi", start: 0.2, end: 1.4), CustomSTTSegment(text: "there", start: 1.5, end: 2),
        ])
        let diarized = Data(#"{"segments":[{"start":0,"end":1,"text":"A1","speaker":"A"},"#.utf8)
            + Data(#"{"start":1,"end":2,"text":"B1","speaker":"B"}]}"#.utf8)
        #expect(try CustomSTTRequests.segments(from: diarized, duration: 2).map(\.speaker) == [0, 1])
        let plain = Data(#"{"text":" only text "}"#.utf8)
        #expect(try CustomSTTRequests.segments(from: plain, duration: 3) == [CustomSTTSegment(text: "only text", start: 0, end: 3)])
        #expect(throws: CustomSTTError.undecodable) { try CustomSTTRequests.segments(from: Data("nope".utf8), duration: 1) }
    }

    @Test func deepgramStreamsLinear16AndGroupsWordsBySpeaker() throws {
        let request = try CustomSTTRequests.deepgramSocket(CustomSTTConfig(provider: .deepgramLive, apiKey: "dg"))
        let items = URLComponents(url: try #require(request.url), resolvingAgainstBaseURL: false)?.queryItems ?? []
        #expect(request.url?.host == "api.deepgram.com")
        #expect(request.value(forHTTPHeaderField: "Authorization") == "Token dg")
        #expect(items.contains(URLQueryItem(name: "encoding", value: "linear16")))
        #expect(items.contains(URLQueryItem(name: "model", value: "nova-3")))
        #expect(items.contains(URLQueryItem(name: "language", value: "multi")))
        let message = #"""
        {"type":"Results","is_final":true,"channel":{"alternatives":[{"transcript":"hi you there","words":[
        {"punctuated_word":"Hi","start":0.1,"end":0.3,"speaker":0},{"punctuated_word":"you","start":0.4,"end":0.5,"speaker":0},
        {"punctuated_word":"there.","start":0.6,"end":0.9,"speaker":1}]}]}}
        """#
        #expect(CustomSTTRequests.deepgramSegments(from: message) == [
            CustomSTTSegment(text: "Hi you", start: 0.1, end: 0.5, speaker: 0),
            CustomSTTSegment(text: "there.", start: 0.6, end: 0.9, speaker: 1),
        ])
        #expect(CustomSTTRequests.deepgramSegments(from: #"{"type":"Metadata"}"#) == nil)
        let interim = #"{"type":"Results","is_final":false,"channel":{"alternatives":[{"transcript":"x"}]}}"#
        #expect(CustomSTTRequests.deepgramSegments(from: interim) == nil)
    }

    @Test func wavHeaderDescribes16kMonoPCM() {
        let wav = PCMWave.wav(pcm16: Data(count: 320))
        #expect(wav.count == 44 + 320)
        #expect(wav.prefix(4) == Data("RIFF".utf8))
        #expect(wav[24 ..< 28] == Data([0x80, 0x3E, 0, 0])) // 16000
    }

    @Test func listenEventsCarryTranslationsAndTheFreemiumThreshold() {
        let translating = #"{"type":"translating","segments":[{"id":"s1","text":"Hola","start":0,"end":1,"#
            + #""translations":[{"lang":"en","text":"Hello"}]}]}"#
        guard case let .translated(segments) = ListenEvent.parse(translating) else {
            Issue.record("not a translation")
            return
        }
        #expect(segments.first?.translations == [LiveSegment.Translation(lang: "en", text: "Hello")])
        let low = #"{"type":"freemium_threshold_reached","remaining_seconds":180,"action":"setup_on_device_stt"}"#
        #expect(ListenEvent.parse(low)
            == .freemiumThreshold(remainingSeconds: 180, requiresOnDevice: true))
        let legacy = #"{"type":"service_status","status":"freemium_threshold_reached","remaining_seconds":0,"action":"none"}"#
        #expect(ListenEvent.parse(legacy)
            == .freemiumThreshold(remainingSeconds: 0, requiresOnDevice: false))
    }
}
