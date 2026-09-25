import AppKit
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

/// Synchronous, sendable view of the server control generation for delayed
/// owner-bound work. The manager remains the sole authority that updates this
/// value; the lock lets an actor recheck the same generation at its write
/// linearization point without reaching across isolation to read MainActor
/// state.
final class AccountCutoverGenerationAuthority: @unchecked Sendable {
  private let lock = NSLock()
  private var generation: Int

  init(generation: Int = AccountCutoverControl.legacyDefault.accountGeneration) {
    self.generation = generation
  }

  func update(_ generation: Int) {
    lock.withLock { self.generation = generation }
  }

  func isCurrent(_ expectedGeneration: Int) -> Bool {
    lock.withLock { generation == expectedGeneration }
  }
}

enum AccountCutoverGateDecision: Equatable, Sendable {
  case allowProductTraffic
  case forceUpgrade
  case migrationMaintenance
}

/// Bootstrap projection before the first authoritative control fetch for the bound owner.
enum AccountCutoverBootstrapPhase: Equatable, Sendable {
  /// No confirmed control for the current owner — product services stay blocked.
  case pending
  /// Server control has been applied for the current owner.
  case ready
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

/// Shared admission for every durable desktop outbox / WAL upload path.
enum AccountCutoverOfflineUploadAdmission {
  @MainActor
  static func allowsUpload(
    manager: AccountCutoverControlManager = .shared
  ) -> Bool {
    manager.allowsOfflineQueueUpload
  }

  static func allowsUploadOffMainActor() async -> Bool {
    await MainActor.run { allowsUpload() }
  }
}

@MainActor
final class AccountCutoverControlManager: ObservableObject {
  static let shared = AccountCutoverControlManager()

  @Published private(set) var bootstrapPhase: AccountCutoverBootstrapPhase = .pending
  @Published private(set) var control: AccountCutoverControl = .legacyDefault
  @Published private(set) var decision: AccountCutoverGateDecision = .migrationMaintenance

  private let gate = AccountCutoverGate()
  private let fetchControl: () async throws -> AccountCutoverControl
  private let currentOwnerID: () -> String?
  private var activationObserver: NSObjectProtocol?
  private var ownerChangeObserver: NSObjectProtocol?
  private var signOutObserver: NSObjectProtocol?
  private var lifecycleInstalled = false
  private var boundOwnerID: String?
  private var refreshGeneration: UInt64 = 0
  private var hasAuthoritativeControl = false
  let generationAuthority = AccountCutoverGenerationAuthority()

  init(
    fetchControl: @escaping () async throws -> AccountCutoverControl = AccountCutoverControlManager.defaultFetch,
    currentOwnerID: @escaping () -> String? = { RuntimeOwnerIdentity.currentOwnerId() }
  ) {
    self.fetchControl = fetchControl
    self.currentOwnerID = currentOwnerID
  }

  /// Token that changes whenever signed-in product services may start or must stop.
  var productShellAdmissionToken: String {
    "\(bootstrapPhase)-\(decision)-\(boundOwnerID ?? "none")"
  }

  var allowsOfflineQueueUpload: Bool {
    bootstrapPhase == .ready && gate.shouldUploadOfflineQueues(control)
  }

  var quarantinesOfflineQueues: Bool {
    bootstrapPhase == .ready && gate.shouldQuarantineOfflineQueues(control)
  }

  var blocksProductTraffic: Bool {
    bootstrapPhase != .ready || decision != .allowProductTraffic
  }

  var isProductShellAdmitted: Bool {
    bootstrapPhase == .ready && decision == .allowProductTraffic
  }

  /// A blocking overlay is user-facing evidence of an authoritative server decision.
  /// Bootstrap remains fail-closed for product traffic, but an unconfirmed pending
  /// state must not masquerade as a migration or intercept the shell while control loads.
  var overlayDecision: AccountCutoverGateDecision? {
    guard bootstrapPhase == .ready else { return nil }
    return decision == .allowProductTraffic ? nil : decision
  }

  /// Install activation / owner observers once and bind+refresh the current owner.
  func installLifecycleObserversIfNeeded() {
    if !lifecycleInstalled {
      lifecycleInstalled = true
      activationObserver = NotificationCenter.default.addObserver(
        forName: NSApplication.didBecomeActiveNotification,
        object: nil,
        queue: .main
      ) { [weak self] _ in
        Task { @MainActor in
          await self?.refresh()
        }
      }
      ownerChangeObserver = NotificationCenter.default.addObserver(
        forName: .runtimeOwnerDidChange,
        object: nil,
        queue: .main
      ) { [weak self] _ in
        Task { @MainActor in
          await self?.bindCurrentOwnerAndRefresh()
        }
      }
      signOutObserver = NotificationCenter.default.addObserver(
        forName: .userDidSignOut,
        object: nil,
        queue: .main
      ) { [weak self] _ in
        Task { @MainActor in
          self?.resetForSignedOutOwner()
        }
      }
    }
    Task { await bindCurrentOwnerAndRefresh() }
  }

  /// Awaited by the signed-in home shell before product services start.
  func prepareSignedInShell() async {
    installLifecycleObserversIfNeeded()
    await bindCurrentOwnerAndRefresh()
  }

  func bindCurrentOwnerAndRefresh() async {
    let ownerID = currentOwnerID()
    if ownerID == nil {
      resetForSignedOutOwner()
      return
    }
    if ownerID != boundOwnerID {
      resetForOwnerChange(newOwnerID: ownerID)
    }
    await refresh()
  }

  func refresh() async {
    let ownerID = boundOwnerID ?? currentOwnerID()
    guard let ownerID else {
      resetForSignedOutOwner()
      return
    }
    if boundOwnerID != ownerID {
      resetForOwnerChange(newOwnerID: ownerID)
    }
    refreshGeneration &+= 1
    let generation = refreshGeneration
    let refreshOwnerID = ownerID
    do {
      let fetched = try await fetchControl()
      guard generation == refreshGeneration, boundOwnerID == refreshOwnerID else { return }
      applyAuthoritative(fetched)
    } catch {
      guard generation == refreshGeneration, boundOwnerID == refreshOwnerID else { return }
      // Keep the last confirmed control; never reopen the gate from a blip.
      // Before the first confirmation, stay pending / blocked.
      log(
        "AccountCutoverControl: fetch failed retained_authoritative=\(hasAuthoritativeControl) "
          + "error_type=\(String(reflecting: type(of: error)))"
      )
      if hasAuthoritativeControl {
        // Correctness-preserving degraded path: continue with last confirmed
        // projection instead of failing open to legacyDefault.
        DesktopDiagnosticsManager.shared.recordFallback(
          area: "account_cutover",
          from: "live_control",
          to: "retained_control",
          reason: "other",
          outcome: .degraded,
          extra: [
            "failure_class": "control_refresh_failed",
            "recovery_action": "retain_last_confirmed",
            "recovery_result": "degraded",
            "bootstrap_phase": bootstrapPhase == .ready ? "ready" : "pending",
          ]
        )
      }
    }
  }

  func apply(_ control: AccountCutoverControl) {
    applyAuthoritative(control)
  }

  /// Test seam: force pending bootstrap without a network round-trip.
  func resetForTesting() {
    refreshGeneration &+= 1
    boundOwnerID = nil
    hasAuthoritativeControl = false
    bootstrapPhase = .pending
    control = .legacyDefault
    decision = .migrationMaintenance
    generationAuthority.update(control.accountGeneration)
  }

  private func applyAuthoritative(_ control: AccountCutoverControl) {
    self.control = control
    generationAuthority.update(control.accountGeneration)
    decision = gate.decide(control)
    hasAuthoritativeControl = true
    bootstrapPhase = .ready
  }

  private func resetForOwnerChange(newOwnerID: String?) {
    refreshGeneration &+= 1
    boundOwnerID = newOwnerID
    hasAuthoritativeControl = false
    bootstrapPhase = .pending
    control = .legacyDefault
    decision = .migrationMaintenance
    generationAuthority.update(control.accountGeneration)
  }

  private func resetForSignedOutOwner() {
    resetForOwnerChange(newOwnerID: nil)
  }

  private static func defaultFetch() async throws -> AccountCutoverControl {
    try await APIClient.shared.getAccountCutoverControl()
  }
}
