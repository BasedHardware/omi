import Combine
import Foundation

/// One marketplace decision and its exact committed installation. Connection
/// setup is a separate step; saving a URL or command is not authentication.
@MainActor
final class ExtensionInstallSession: ObservableObject {
  enum Phase: Equatable {
    case ready
    case installing
    case failed(String)
    case serverSetup(LocalMcpStore.Entry)
    case skillInstalled
    case closed
  }

  typealias InstallOperation =
    @MainActor (ExtensionCatalog.Entry, [String: String]) async throws -> ExtensionCatalogService.InstallReceipt
  typealias RefreshOperation = @MainActor () async -> Void

  @Published private(set) var phase: Phase = .ready
  private let installOperation: InstallOperation
  private let refreshOperation: RefreshOperation
  private var generation: UInt64 = 0

  init(
    install: @escaping InstallOperation = { try await ExtensionCatalogService.install($0, secrets: $1) },
    refresh: @escaping RefreshOperation = {}
  ) {
    installOperation = install
    refreshOperation = refresh
  }

  var isInstalling: Bool { phase == .installing }

  var canInstall: Bool {
    switch phase {
    case .ready, .failed: return true
    case .installing, .serverSetup, .skillInstalled, .closed: return false
    }
  }

  var errorText: String? {
    if case .failed(let message) = phase { return message }
    return nil
  }

  var installedServer: LocalMcpStore.Entry? {
    if case .serverSetup(let server) = phase { return server }
    return nil
  }

  /// Repeated presses cannot create suffixed duplicates. A successful receipt
  /// is installation authority; reloading a derived list never installs again.
  func install(_ entry: ExtensionCatalog.Entry, secrets: [String: String]) async {
    switch phase {
    case .ready, .failed: break
    case .installing, .serverSetup, .skillInstalled, .closed: return
    }
    guard !Task.isCancelled else { return }
    generation &+= 1
    let lease = generation
    phase = .installing
    do {
      let receipt = try await installOperation(entry, secrets)
      // A receipt means configuration already committed. Refresh the underlying
      // Apps projection even if closing/cancellation revoked this sheet's lease.
      // Otherwise that mounted list can still offer the same entry for install.
      await refreshOperation()
      guard isCurrent(lease) else { return }
      switch receipt {
      case .mcpServer(let server): phase = .serverSetup(server)
      case .skill: phase = .skillInstalled
      }
    } catch {
      guard isCurrent(lease) else { return }
      phase = error is CancellationError || Task.isCancelled ? .ready : .failed(error.localizedDescription)
    }
  }

  /// Dismissal abandons work and publication, not committed user configuration.
  /// Cancel, Escape, and disappearance can all arrive for the same close.
  func close() {
    guard phase != .closed else { return }
    generation &+= 1
    phase = .closed
  }

  private func isCurrent(_ lease: UInt64) -> Bool {
    generation == lease && phase == .installing
  }
}
