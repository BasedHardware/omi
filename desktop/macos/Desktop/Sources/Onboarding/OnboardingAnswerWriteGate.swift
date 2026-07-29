import Foundation

/// Preserves a user's answer order when they revisit an onboarding question.
///
/// The UI advances optimistically, while name, acquisition source, and language
/// each write to the backend asynchronously. A second answer for the same field
/// must wait for its predecessor to finish before it begins, otherwise an older
/// request may finish last and overwrite the revision.
@MainActor
final class OnboardingAnswerWriteGate {
  enum Key: Hashable {
    case name
    case acquisitionSource
    case language
  }

  private var tails: [Key: Task<Void, Never>] = [:]

  func enqueue(_ key: Key, operation: @escaping @MainActor () async -> Void) {
    let predecessor = tails[key]
    let task = Task { @MainActor in
      _ = await predecessor?.result
      await operation()
    }
    tails[key] = task
  }

  func waitForIdle(_ key: Key) async {
    _ = await tails[key]?.result
  }
}
