import Combine
import Foundation

/// Server-authoritative whole-account cutover control projection.
///
/// LIFECYCLE: permanent
enum AccountCutoverState: String, Codable, Sendable {
  case legacy
  case migrating
  case newState = "new"
  case rolledBackStranded = "rolled_back_stranded"
}

enum AccountCutoverClientAction: String, Codable, Sendable {
  case none
  case forceUpgrade = "force_upgrade"
  case migrationMaintenance = "migration_maintenance"
}

enum OfflineQueueInstruction: String, Codable, Sendable {
  case none
  case drain
  case quarantine
}

struct AccountCutoverControl: Codable, Equatable, Sendable {
  var schemaVersion: Int
  var state: AccountCutoverState
  var accountGeneration: Int
  var uiGeneration: Int
  var apiGeneration: Int
  var clientAction: AccountCutoverClientAction
  var offlineQueueInstruction: OfflineQueueInstruction
  var strandedNewData: Bool
  var legacyWritesAllowed: Bool
  var productTrafficAllowed: Bool
  var authBootstrapReachable: Bool

  enum CodingKeys: String, CodingKey {
    case schemaVersion = "schema_version"
    case state
    case accountGeneration = "account_generation"
    case uiGeneration = "ui_generation"
    case apiGeneration = "api_generation"
    case clientAction = "client_action"
    case offlineQueueInstruction = "offline_queue_instruction"
    case strandedNewData = "stranded_new_data"
    case legacyWritesAllowed = "legacy_writes_allowed"
    case productTrafficAllowed = "product_traffic_allowed"
    case authBootstrapReachable = "auth_bootstrap_reachable"
  }

  static let legacyDefault = AccountCutoverControl(
    schemaVersion: 1,
    state: .legacy,
    accountGeneration: 0,
    uiGeneration: 0,
    apiGeneration: 0,
    clientAction: .none,
    offlineQueueInstruction: .none,
    strandedNewData: false,
    legacyWritesAllowed: true,
    productTrafficAllowed: true,
    authBootstrapReachable: true
  )
}

enum AccountCutoverGateDecision: Equatable, Sendable {
  case allowProductTraffic
  case forceUpgrade
  case migrationMaintenance
}

struct AccountCutoverGate: Sendable {
  func decide(_ control: AccountCutoverControl) -> AccountCutoverGateDecision {
    switch control.clientAction {
    case .forceUpgrade:
      return .forceUpgrade
    case .migrationMaintenance:
      return .migrationMaintenance
    case .none:
      return control.productTrafficAllowed ? .allowProductTraffic : .migrationMaintenance
    }
  }

  func shouldUploadOfflineQueues(_ control: AccountCutoverControl) -> Bool {
    if control.offlineQueueInstruction == .quarantine {
      return false
    }
    // Drain is only honest before the migration fence (product traffic still allowed).
    return decide(control) == .allowProductTraffic
  }

  func shouldQuarantineOfflineQueues(_ control: AccountCutoverControl) -> Bool {
    control.offlineQueueInstruction == .quarantine
  }
}

@MainActor
final class AccountCutoverControlManager: ObservableObject {
  static let shared = AccountCutoverControlManager()

  @Published private(set) var control: AccountCutoverControl = .legacyDefault
  @Published private(set) var decision: AccountCutoverGateDecision = .allowProductTraffic

  private let gate = AccountCutoverGate()
  private let fetchControl: () async throws -> AccountCutoverControl

  init(fetchControl: @escaping () async throws -> AccountCutoverControl = AccountCutoverControlManager.defaultFetch) {
    self.fetchControl = fetchControl
  }

  var allowsOfflineQueueUpload: Bool { gate.shouldUploadOfflineQueues(control) }
  var quarantinesOfflineQueues: Bool { gate.shouldQuarantineOfflineQueues(control) }
  var blocksProductTraffic: Bool { decision != .allowProductTraffic }

  func refresh() async {
    do {
      let fetched = try await fetchControl()
      apply(fetched)
    } catch {
      // Keep legacy-compatible defaults until enforcement + bridge floors are live.
      apply(.legacyDefault)
      log("AccountCutoverControl: fetch failed error_type=\(String(reflecting: type(of: error)))")
    }
  }

  func apply(_ control: AccountCutoverControl) {
    self.control = control
    decision = gate.decide(control)
  }

  private static func defaultFetch() async throws -> AccountCutoverControl {
    try await APIClient.shared.getAccountCutoverControl()
  }
}
