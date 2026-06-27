import Foundation

// MARK: - Fake-voice E2E test harness
//
// Injects a raw PCM16/16kHz-mono buffer through the real RealtimeOmniService
// (the exact STT path the floating bar uses) and returns the transcript — so the
// whole omni voice loop can be tested headlessly with synthetic speech, no mic,
// no TCC prompt, no human talking. Driven via the `omni_test_turn` automation
// action (see DesktopAutomationBridge.registerBuiltins).

@MainActor
final class RealtimeOmniTestHarness: NSObject, RealtimeOmniServiceDelegate {
    private let provider: RealtimeOmniProvider
    private let relayBaseURL: String
    private let authHeader: String
    private let pcm16k: Data

    private var service: RealtimeOmniService?
    private var feed = Data()
    private var sendIndex = 0
    private var interim = ""
    private var finalText = ""
    private var connected = false
    private var errorMsg: String?
    private var done = false
    private var continuation: CheckedContinuation<[String: String], Never>?

    init(provider: RealtimeOmniProvider, relayBaseURL: String, authHeader: String, pcm16k: Data) {
        self.provider = provider
        self.relayBaseURL = relayBaseURL
        self.authHeader = authHeader
        self.pcm16k = pcm16k
        super.init()
    }

    func run(timeoutSeconds: Double) async -> [String: String] {
        let svc = RealtimeOmniService(
            provider: provider, relayBaseURL: relayBaseURL, authHeader: authHeader, sttOnly: true, delegate: self)
        service = svc
        // Start streaming audio immediately — BEFORE the connection handshake
        // completes — exactly like PushToTalkManager (mic starts on key-down and
        // chunks flow during connect). This is what surfaces the Gemini
        // audio-before-activityStart 1007 bug; sending only after omniDidConnect
        // (as before) hid it. The service buffers until the session is open.
        let rate = svc.requiredInputSampleRate
        feed = rate == 16000 ? pcm16k : PushToTalkManager.resamplePCM16(pcm16k, from: 16000, to: rate)
        sendIndex = 0
        svc.start()
        pump()
        Task { [weak self] in
            try? await Task.sleep(nanoseconds: UInt64(timeoutSeconds * 1_000_000_000))
            self?.finish(reason: "timeout")
        }
        return await withCheckedContinuation { continuation = $0 }
    }

    // MARK: RealtimeOmniServiceDelegate

    func omniDidConnect() {
        connected = true
    }

    private func pump() {
        guard let svc = service, !done else { return }
        let chunkBytes = (svc.requiredInputSampleRate / 10) * 2  // ~100ms of PCM16
        if sendIndex >= feed.count {
            svc.commitInputTurn()  // OpenAI manual VAD; no-op for Gemini
            return
        }
        let end = min(sendIndex + chunkBytes, feed.count)
        svc.sendAudio(feed.subdata(in: sendIndex..<end))
        sendIndex = end
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.03) { [weak self] in self?.pump() }
    }

    func omniDidReceiveInputTranscript(_ text: String, isFinal: Bool) {
        if isFinal {
            if !text.isEmpty { finalText = text }
            finish(reason: "final_transcript")  // STT done — no need to wait for turn end
        } else {
            interim += text
        }
    }

    func omniDidReceiveAudio(_ pcm24k: Data) {}  // STT-only: model voice unused

    func omniDidFinishTurn() { finish(reason: "turn_complete") }

    func omniDidError(_ message: String) {
        errorMsg = message
        finish(reason: "error")
    }

    private func finish(reason: String) {
        guard !done else { return }
        done = true
        service?.stop()
        service = nil
        let transcript = finalText.isEmpty ? interim : finalText
        let result: [String: String] = [
            "provider": provider.displayName,
            "connected": connected ? "true" : "false",
            "transcript": transcript.trimmingCharacters(in: .whitespacesAndNewlines),
            "reason": reason,
            "error": errorMsg ?? "",
        ]
        log("RealtimeOmniTestHarness: \(result)")
        continuation?.resume(returning: result)
        continuation = nil
    }
}
