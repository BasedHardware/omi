import Foundation

extension RealtimeHubSession {

  // MARK: - Voice-bearing payload fragments (production seams)
  //
  // These are the exact fragments the session builders embed, exposed so a
  // regression test asserts the payload a real session is configured with —
  // a per-call-site voice string drifting back in (marin) fails the test.

  /// The OpenAI `session.update` output-audio block. cedar: the deep, calm
  /// male voice of the gpt-realtime family, Charon's counterpart, so a
  /// provider failover does not change who Omi sounds like mid-conversation.
  static func openAIOutputAudioConfig() -> [String: Any] {
    [
      "format": ["type": "audio/pcm", "rate": 24000],
      "voice": RealtimeHubVoicePolicy.voiceName(for: .openai),
    ]
  }

  /// The Gemini `setup.generationConfig.speechConfig` block. Pin the spoken
  /// voice — with no speechConfig Gemini picks its own default, which differs
  /// from the OpenAI hub voice and can change across model revisions.
  static func geminiSpeechConfig() -> [String: Any] {
    ["voiceConfig": ["prebuiltVoiceConfig": ["voiceName": RealtimeHubVoicePolicy.voiceName(for: .gemini)]]]
  }
}
