import Combine
import SwiftUI

@MainActor
final class MessagingRegistry: ObservableObject {
  static let shared = MessagingRegistry()

  let providers: [any MessagingProvider]
  @Published var selectedProviderId: String

  private init() {
    let whatsapp = WhatsAppMessagingProvider.shared
    providers = [whatsapp]
    selectedProviderId = whatsapp.id
  }

  var selectedProvider: (any MessagingProvider)? {
    providers.first { $0.id == selectedProviderId }
  }
}
