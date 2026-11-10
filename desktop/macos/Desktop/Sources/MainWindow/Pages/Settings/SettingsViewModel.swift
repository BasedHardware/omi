import Foundation

@MainActor
final class SettingsViewModel: ObservableObject {
  @Published var isLoadingBackendSettings = false
  @Published var isLoadingSubscription = false
  @Published var subscriptionError: String?
  /// Survives `loadSubscriptionInfo`, which clears `subscriptionError` on every refresh.
  @Published var subscriptionConfirmation: String?
  @Published var lastBackendSettingsLoadAt: Date?
  @Published var lastBillingRefreshAt: Date?
  @Published var lastIntegrationSyncAt: Date?

  func markBackendSettingsLoaded() {
    lastBackendSettingsLoadAt = Date()
  }

  func markBillingRefreshed() {
    lastBillingRefreshAt = Date()
  }

  func markIntegrationSynced() {
    lastIntegrationSyncAt = Date()
  }
}
