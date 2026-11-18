import Foundation

/// The device tool approval frames and the capability declaration behind them,
/// kept beside the process owner so that file does not grow for a display-only
/// feature.
extension AgentRuntimeProcess {
  /// The client identity this app declares its wire capabilities under.
  nonisolated static let shellCapabilitiesClientID = "desktop-shell"
  /// Declared to the daemon right after the handshake: this app renders device
  /// tool approval cards, so the relay may park a sensitive call and ask instead
  /// of failing it at once. Interim gate; the daemon drops it once the card ships.
  nonisolated static let desktopToolApprovalCardsCapability = "desktop_tool_approval_cards"
  /// What a runtime advertises in `init` when it can park a call and send
  /// `approval_requested`. An older daemon without it still runs the chat; the
  /// app then keeps that daemon's immediate `approval_required` and shows no card.
  nonisolated static let runtimeToolApprovalRequestsCapability = "desktop_tool_approval_requests"

  nonisolated static func clientCapabilitiesWireMessage(
    requestId: String = UUID().uuidString
  ) -> [String: Any] {
    [
      "type": "client_capabilities",
      "protocolVersion": expectedProtocolVersion,
      "requestId": requestId,
      "clientId": shellCapabilitiesClientID,
      "capabilities": [desktopToolApprovalCardsCapability],
    ]
  }

  /// The declaration to send after this handshake, or nil for a runtime that
  /// cannot park calls: declaring cards to it would be meaningless, and the
  /// chat must keep working with an older daemon.
  nonisolated static func clientCapabilitiesWireMessage(
    for handshake: RuntimeHandshake, requestId: String = UUID().uuidString
  ) -> [String: Any]? {
    guard handshake.capabilities.contains(runtimeToolApprovalRequestsCapability) else { return nil }
    return clientCapabilitiesWireMessage(requestId: requestId)
  }

  /// `approval_requested` and `approval_resolved` are display-only: the card
  /// projects the kernel's dispatch, and the answer goes back through signed
  /// direct control. A frame for another owner is not shown.
  func routeToolApprovalFrame(_ message: RuntimeMessage) {
    guard messageOwnerIsCurrentlyAuthorized(message) else { return }
    Task { @MainActor in
      DesktopToolApprovalStore.shared.ingest(message: message)
    }
  }

  /// A card belongs to one daemon process and one owner. A new handshake, the
  /// process ending, or the owner being revoked makes every card stale: the
  /// kernel that would answer it is gone, so the thread must not keep showing
  /// buttons that can only fail.
  func clearToolApprovalCards() {
    Task { @MainActor in
      DesktopToolApprovalStore.shared.reset()
    }
  }
}
