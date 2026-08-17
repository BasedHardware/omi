import Foundation

/// Answers "has the user already connected this integration?" for both halves
/// of the catalog, so the nudge path has one question to ask instead of two
/// different subsystems to know about.
///
/// This reads the *persisted* answer rather than re-probing the provider. A
/// nudge is a marketing decision, not an access check: if the user connected
/// Gmail last month and the cookie has since expired, the right surface for
/// that is the Apps tab's reconnect affordance, not a banner that reads like
/// they never set it up.
@MainActor
enum IntegrationConnectionInspector {
  static func isConnected(_ route: IntegrationNudgeRoute) async -> Bool {
    switch route {
    case .importConnector(let connectorID):
      return ImportConnectorStatusStore(
        defaults: .standard,
        sessionUserID: RuntimeOwnerIdentity.currentOwnerId()
      ).hasEverSynced(connectorID: connectorID)

    case .exportDestination(let destinationID):
      guard let destination = MemoryExportDestination(rawValue: destinationID) else { return false }
      let statuses = await MemoryExportService.shared.allStatuses()
      return statuses[destination]?.hasConnection ?? false
    }
  }
}
