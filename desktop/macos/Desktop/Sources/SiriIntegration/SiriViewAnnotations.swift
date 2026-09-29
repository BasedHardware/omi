import AppIntents
import SwiftUI

extension View {
  @ViewBuilder
  func siriConversationIdentifier(_ id: String) -> some View {
    if #available(macOS 27, *), SiriIntegrationSettings.isEnabled, !id.hasPrefix("local_") {
      appEntityIdentifier(EntityIdentifier(for: ConversationEntity.self, identifier: id))
    } else {
      self
    }
  }

  @ViewBuilder
  func siriMemoryIdentifier(_ id: String) -> some View {
    if #available(macOS 27, *), SiriIntegrationSettings.isEnabled, !id.hasPrefix("local_") {
      appEntityIdentifier(EntityIdentifier(for: MemoryEntity.self, identifier: id))
    } else {
      self
    }
  }

  @ViewBuilder
  func siriTaskIdentifier(_ id: String) -> some View {
    if #available(macOS 27, *), SiriIntegrationSettings.isEnabled, !id.hasPrefix("local_") {
      appEntityIdentifier(EntityIdentifier(for: TaskEntity.self, identifier: id))
    } else {
      self
    }
  }
}
