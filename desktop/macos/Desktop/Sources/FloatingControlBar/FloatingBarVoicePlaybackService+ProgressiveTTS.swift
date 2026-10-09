import Foundation

extension FloatingBarVoicePlaybackService {
  /// Progressive counterpart to buffered one-shot/sample synthesis. Credential
  /// admission and terminal failure recording remain identical; only successful
  /// response delivery changes from one `Data` value to bounded chunks.
  nonisolated static func synthesizeCloudSpeechStream(
    text: String,
    voiceID: String,
    instructions: String
  ) async throws -> AsyncThrowingStream<Data, Error> {
    let byokKey = APIKeyService.selectedBYOKLLMProvider == .openai ? APIKeyService.byokKey(.openai) : nil
    let fingerprint = byokKey.map(APIKeyService.byokFingerprint)

    let upstream = try await APIClient.shared.synthesizeSpeechStream(
      request: APIClient.TtsSynthesizeRequest(
        text: text,
        voiceId: voiceID,
        instructions: instructions.isEmpty ? nil : instructions
      ))
    return AsyncThrowingStream { continuation in
      let task = Task {
        do {
          for try await data in upstream {
            try Task.checkCancellation()
            continuation.yield(data)
          }
          continuation.finish()
        } catch let error as CredentialHealthError {
          await MainActor.run {
            if case .providerAuth(let provider, let mode, _) = error {
              CredentialHealthManager.shared.recordProviderFailure(
                error.failureClass,
                provider: provider,
                authMode: mode,
                fingerprint: fingerprint,
                context: "openai_tts"
              )
            } else {
              CredentialHealthManager.shared.record(error, context: "openai_tts")
            }
          }
          continuation.finish(throwing: error)
        } catch {
          continuation.finish(throwing: error)
        }
      }
      continuation.onTermination = { @Sendable _ in task.cancel() }
    }
  }
}
