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

// MARK: - Known limitation
//
// Export status is only partly owner-scoped today. The local-MCP half is keyed
// on the owner's current MCP key, but `memoryExportConnectedAt.<destination>`
// and the exported-count are machine-global in `MemoryExportService`. So on a
// Mac where two people sign in, the second person can have an export nudge
// suppressed by the first person's connection.
//
// This is not fixed here on purpose: those keys back the Apps tab's shipped
// status rows, and re-scoping them is a storage migration with its own
// review — larger than, and independent of, the nudge feature. The failure
// direction is the safe one for a nudge (a missed offer, never a wrong or
// duplicated one), which is the same way every other unknown in this feature
// resolves.
