import Foundation

// MARK: - Realtime Hub E2E test harness (headless)
//
// Drives the REAL RealtimeHubSession client-direct against the provider (with the
// user's BYOK key), feeding a synthetic PCM16/16kHz-mono buffer instead of the
// mic — so the whole hub voice loop can be exercised with no microphone, no TCC
// prompt, and no human talking. Mirrors RealtimeOmniTestHarness; driven via the
// `hub_test_turn` automation action (registered in RealtimeHubController.setup()).
//
// Returns the normalized stream it observed: transcript_in, text_out / audio_out,
// the tool calls the model chose (routing!), and whether the turn completed.

@MainActor
final class RealtimeHubTestHarness: NSObject, RealtimeHubSessionDelegate {
  private let provider: RealtimeHubProvider
  private let auth: HubAuth
  private let pcm16k: Data

  private var session: RealtimeHubSession?
  private var connected = false
  private var transcriptIn = ""
  private var textOut = ""
  private var audioBytes = 0
  private var toolCalls: [String] = []
  private var errorMsg: String?
  private var done = false
  private var continuation: CheckedContinuation<[String: String], Never>?

  init(provider: RealtimeHubProvider, auth: HubAuth, pcm16k: Data) {
    self.provider = provider
    self.auth = auth
    self.pcm16k = pcm16k
    super.init()
  }

  func run(timeoutSeconds: Double) async -> [String: String] {
    let s = RealtimeHubSession(provider: provider, auth: auth, delegate: self)
    session = s
    let rate = s.requiredInputSampleRate
    let audio = rate == 16000 ? pcm16k : PushToTalkManager.resamplePCM16(pcm16k, from: 16000, to: rate)
    s.start()
    s.beginInputTurn()  // open the per-turn speech window (Gemini) before audio
    // Stream audio immediately (buffers until the session opens), in ~100ms frames.
    let frame = (rate / 10) * 2  // samples/100ms * 2 bytes
    var i = 0
    while i < audio.count {
      let end = Swift.min(i + frame, audio.count)
      s.sendAudio(audio.subdata(in: i..<end))
      i = end
    }
    s.commitInputTurn()

    let timeoutTask = Task { [weak self] in
      try? await Task.sleep(nanoseconds: UInt64(timeoutSeconds * 1_000_000_000))
      await MainActor.run { self?.finish(timedOut: true) }
    }
    let result = await withCheckedContinuation { (c: CheckedContinuation<[String: String], Never>) in
      continuation = c
    }
    timeoutTask.cancel()
    s.stop()
    return result
  }

  private func finish(timedOut: Bool) {
    guard !done else { return }
    done = true
    let result: [String: String] = [
      "provider": provider.displayName,
      "connected": connected ? "true" : "false",
      "transcript_in": transcriptIn,
      "text_out": textOut.trimmingCharacters(in: .whitespacesAndNewlines),
      "audio_out_bytes": String(audioBytes),
      "tool_calls": toolCalls.isEmpty ? "(none)" : toolCalls.joined(separator: " | "),
      "timed_out": timedOut ? "true" : "false",
      "error": errorMsg ?? "",
    ]
    log("RealtimeHubTestHarness: result \(result)")
    continuation?.resume(returning: result)
    continuation = nil
  }

  // MARK: RealtimeHubSessionDelegate

  func hubDidConnect() { connected = true }

  func hubDidReceiveInputTranscript(_ text: String, isFinal: Bool) {
    if isFinal { if !text.isEmpty { transcriptIn = text } } else { transcriptIn += text }
  }

  func hubDidReceiveAudio(_ pcm24k: Data) { audioBytes += pcm24k.count }

  func hubDidEmitText(_ text: String, isFinal: Bool) { textOut += text }

  func hubDidRequestTool(name: String, callId: String, argumentsJSON: String) {
    toolCalls.append("\(name)(\(argumentsJSON))")
    // Return a stub result so the turn completes and we observe the full loop —
    // without spawning real agents / network calls inside the test.
    let stub: String
    switch HubTool(rawValue: name) {
    case .askHigherModel: stub = "Paris is the capital of France."
    case .getTasks: stub = "Due today (1):\n- Example task"
    case .spawnAgent: stub = "Started a background agent."
    case .screenshot: stub = "Screen captured."
    case .pointClick: stub = "Clicked."
    case .none: stub = "ok"
    }
    session?.sendToolResult(callId: callId, name: name, output: stub)
  }

  func hubDidFinishTurn() { finish(timedOut: false) }

  func hubDidError(_ message: String) {
    if errorMsg == nil { errorMsg = message }
    finish(timedOut: false)
  }

  // MARK: - Automation action registration

  /// Registers the `hub_test_turn` action so omi-ctl can drive a real hub turn
  /// headlessly: `omi-ctl action hub_test_turn pcm=/tmp/q.pcm provider=openai`.
  static func registerAutomationAction() {
    DesktopAutomationActionRegistry.shared.register(
      name: "hub_test_turn",
      summary: "Drive the realtime hub with a PCM16/16k file; returns the normalized turn. "
        + "auth=byok (default, uses BYOK key) | ephemeral (mints a server token, Phase 2)",
      params: ["pcm", "provider", "timeout", "auth"]
    ) { params in
      guard let path = params["pcm"],
        let data = try? Data(contentsOf: URL(fileURLWithPath: path)), !data.isEmpty
      else { return ["error": "missing or unreadable 'pcm' file (expected raw s16le 16k mono)"] }
      let provider =
        params["provider"].flatMap(RealtimeHubProvider.init(rawValue:))
        ?? RealtimeHubSettings.shared.provider
      // Phase 2: if asked for ephemeral, or no BYOK key exists (managed user),
      // mint a server-side ephemeral token via the backend; else use the BYOK key.
      let wantEphemeral = params["auth"] == "ephemeral"
      let byok = APIKeyService.byokKey(provider.byokProvider)
      let auth: HubAuth
      if !wantEphemeral, let key = byok {
        auth = .byokKey(key)
      } else {
        let p = provider == .openai ? "openai" : "gemini"
        guard let token = await APIClient.shared.mintRealtimeToken(provider: p) else {
          return ["error": "ephemeral mint failed for \(p) (check backend route + entitlement)"]
        }
        auth = .ephemeral(token)
      }
      let timeout = Double(params["timeout"] ?? "") ?? 25
      let harness = RealtimeHubTestHarness(provider: provider, auth: auth, pcm16k: data)
      var result = await harness.run(timeoutSeconds: timeout)
      result["auth_mode"] = auth.isEphemeral ? "ephemeral" : "byok"
      return result
    }
  }
}
