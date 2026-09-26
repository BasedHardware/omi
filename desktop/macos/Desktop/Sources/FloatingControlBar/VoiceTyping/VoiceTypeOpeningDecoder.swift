import Foundation

/// Shares a wake-word decode only when the audio is byte-for-byte identical.
/// A shorter mid-hold prefix cannot authorize the longer, released utterance.
/// One entry bounds retained PCM and coalesces a release with an in-flight probe.
@MainActor
final class VoiceTypeOpeningDecoder {
  private struct Entry {
    let id: UUID
    let audio: Data
    let task: Task<String?, Never>
  }

  private var entry: Entry?

  func decode(
    _ audio: Data,
    using transcribe: @escaping @Sendable (Data) async -> String?
  ) async -> String? {
    let current: Entry
    if let entry, entry.audio == audio {
      current = entry
    } else {
      entry?.task.cancel()
      current = Entry(id: UUID(), audio: audio, task: Task { await transcribe(audio) })
      entry = current
    }
    let text = await current.task.value
    // reset() revokes a previous turn, even if its physical decoder ignores cancellation.
    guard entry?.id == current.id else { return nil }
    if text == nil { entry = nil }  // A failed decode is retryable, not a cached rejection.
    return text
  }

  func reset() {
    entry?.task.cancel()
    entry = nil
  }
}
