import AppIntents
import Foundation

/// Donations contain only stable entity IDs. The entity query resolves current
/// owner content when the system later invokes an action.
@available(macOS 27, *)
@MainActor
enum SiriDonations {
  private static func eligible(_ id: String) -> Bool {
    SiriIntegrationSettings.isEnabled && RuntimeOwnerIdentity.currentOwnerId() != nil && !id.hasPrefix("local_")
  }

  static func conversationOpened(_ id: String) {
    guard eligible(id) else { return }
    let intent = OmiOpenIntent()
    intent.target = ConversationEntity(donationID: id)
    Task { await donate(intent) }
  }

  static func memoryCreated(_ id: String) {
    guard eligible(id) else { return }
    let intent = OmiOpenMemoryIntent()
    intent.target = MemoryEntity(donationID: id)
    Task { await donate(intent) }
  }

  static func taskCompleted(_ id: String) {
    guard eligible(id) else { return }
    let intent = OmiOpenTaskIntent()
    intent.target = TaskEntity(donationID: id)
    Task { await donate(intent) }
  }

  private static func donate(_ intent: some AppIntent) async {
    do { try await IntentDonationManager.shared.donate(intent: intent) } catch {
      log("Siri action donation deferred: \(error.localizedDescription)")
    }
  }

  static func wipe() async {
    for intent in [OmiOpenIntent.self, OmiOpenMemoryIntent.self, OmiOpenTaskIntent.self] as [any AppIntent.Type] {
      do { try await IntentDonationManager.shared.deleteDonations(matching: .intentType(intent)) } catch {
        log("Siri donation wipe pending retry: \(error.localizedDescription)")
      }
    }
  }
}
