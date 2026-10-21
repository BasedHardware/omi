import Combine
import Foundation

/// Retired lifecycle boundary. Opening Chat or finishing a meeting cannot
/// start an agent turn; rich blocks belong to replies to a user message.
@MainActor
final class ChatFirstPromptMaterializationCoordinator: ObservableObject {
  static let shared = ChatFirstPromptMaterializationCoordinator()

  init(now: @escaping () -> Date = Date.init, logger: @escaping (String) -> Void = log) {}
  func activate(using chatProvider: ChatProvider) {}
  func activate(driver: any ChatFirstPromptMaterializationDriving) {}
  func chatTranscriptFirstPageDidLoad() {}
  func chatTranscriptDidDisappear() {}
  @discardableResult func mainWindowDidBecomeForeground() -> Bool { false }
  @discardableResult func meetingConversationDidComplete(windowForeground: Bool) -> Bool { false }
}
