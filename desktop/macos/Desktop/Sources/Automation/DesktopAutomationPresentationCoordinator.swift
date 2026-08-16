import Combine
import Foundation

enum DesktopAutomationPresentationRoute: String, CaseIterable, Sendable {
  case openExport = "/open-export"
  case openImport = "/open-import"

  var capability: String { "POST \(rawValue)" }
}

enum DesktopAutomationPresentationTarget: Equatable, Sendable {
  case importConnector(String)
  case exportDestination(String)
}

struct DesktopAutomationPresentationCommand: Equatable, Identifiable, Sendable {
  let generation: UInt64
  let target: DesktopAutomationPresentationTarget

  var id: UInt64 { generation }
}

/// Keeps automation-driven presentation work behind the same readiness
/// boundary that controls whether DesktopHomeView's real content is visible.
/// A command remains owned by the coordinator while loading and is returned,
/// unchanged, on the transition to interactive content.
struct DesktopAutomationPresentationReadinessGate: Equatable, Sendable {
  private(set) var isContentReady = false

  mutating func transition(
    to isContentReady: Bool,
    activeCommand: DesktopAutomationPresentationCommand?
  ) -> DesktopAutomationPresentationCommand? {
    let becameReady = !self.isContentReady && isContentReady
    self.isContentReady = isContentReady
    return becameReady ? activeCommand : nil
  }

  func commandForConsumption(
    _ activeCommand: DesktopAutomationPresentationCommand?
  ) -> DesktopAutomationPresentationCommand? {
    isContentReady ? activeCommand : nil
  }
}

enum DesktopAutomationPresentationGate: Equatable, Sendable {
  case ready
  case signedOut
  case onboardingIncomplete
  case presentationUnavailable
}

enum DesktopAutomationPresentationFailure: Error, Equatable, Sendable {
  case signedOut
  case onboardingIncomplete
  case presentationUnavailable
  case routeTimedOut
  case superseded
  case unknownConnector
  case unknownDestination

  var code: String {
    switch self {
    case .signedOut: return "signed_out"
    case .onboardingIncomplete: return "onboarding_incomplete"
    case .presentationUnavailable: return "sheet_not_visible"
    case .routeTimedOut: return "route_timed_out"
    case .superseded: return "route_superseded"
    case .unknownConnector: return "connector_unknown"
    case .unknownDestination: return "destination_unknown"
    }
  }

  var statusCode: Int {
    switch self {
    case .unknownConnector, .unknownDestination:
      return 400
    case .signedOut, .onboardingIncomplete, .superseded:
      return 409
    case .presentationUnavailable:
      return 503
    case .routeTimedOut:
      return 504
    }
  }
}

enum DesktopAutomationPresentationResolution: Equatable, Sendable {
  case presented(DesktopAutomationPresentationCommand)
  case failed(DesktopAutomationPresentationFailure)
}

protocol DesktopAutomationPresentationTimeoutWaiting: Sendable {
  func waitForTimeout() async
}

struct DesktopAutomationPresentationTimeoutWaiter: DesktopAutomationPresentationTimeoutWaiting {
  let timeout: Duration

  init(timeout: Duration = .seconds(5)) {
    self.timeout = timeout
  }

  func waitForTimeout() async {
    try? await Task.sleep(for: timeout)
  }
}

@MainActor
protocol DesktopAutomationPresentationCoordinating: AnyObject {
  func present(
    _ target: DesktopAutomationPresentationTarget,
    gate: DesktopAutomationPresentationGate
  ) async -> DesktopAutomationPresentationResolution
}

/// Root-owned command channel for automation-driven sheets.
///
/// A request is successful only after the exact command generation and target
/// are visible. A newer request supersedes an older unresolved request; late or
/// mismatched acknowledgements are ignored.
@MainActor
final class DesktopAutomationPresentationCoordinator: ObservableObject,
  DesktopAutomationPresentationCoordinating
{
  static let shared = DesktopAutomationPresentationCoordinator()

  @Published private(set) var activeCommand: DesktopAutomationPresentationCommand?

  private let timeoutWaiter: any DesktopAutomationPresentationTimeoutWaiting
  private var nextGeneration: UInt64 = 0
  private var resolutions: [UInt64: DesktopAutomationPresentationResolution] = [:]
  private var continuations: [UInt64: CheckedContinuation<DesktopAutomationPresentationResolution, Never>] = [:]
  private var timeoutTasks: [UInt64: Task<Void, Never>] = [:]

  init(
    timeoutWaiter: any DesktopAutomationPresentationTimeoutWaiting =
      DesktopAutomationPresentationTimeoutWaiter()
  ) {
    self.timeoutWaiter = timeoutWaiter
  }

  func present(
    _ target: DesktopAutomationPresentationTarget,
    gate: DesktopAutomationPresentationGate
  ) async -> DesktopAutomationPresentationResolution {
    switch gate {
    case .ready:
      break
    case .signedOut:
      return .failed(.signedOut)
    case .onboardingIncomplete:
      return .failed(.onboardingIncomplete)
    case .presentationUnavailable:
      return .failed(.presentationUnavailable)
    }

    let command = beginPresentation(target)
    return await waitForResolution(of: command)
  }

  @discardableResult
  func beginPresentation(
    _ target: DesktopAutomationPresentationTarget
  ) -> DesktopAutomationPresentationCommand {
    if let activeCommand {
      resolve(activeCommand, with: .failed(.superseded))
    }

    nextGeneration &+= 1
    let command = DesktopAutomationPresentationCommand(
      generation: nextGeneration,
      target: target
    )
    activeCommand = command
    return command
  }

  func waitForResolution(
    of command: DesktopAutomationPresentationCommand
  ) async -> DesktopAutomationPresentationResolution {
    if let resolution = resolutions.removeValue(forKey: command.generation) {
      return resolution
    }

    return await withCheckedContinuation { continuation in
      if let resolution = resolutions.removeValue(forKey: command.generation) {
        continuation.resume(returning: resolution)
        return
      }

      continuations[command.generation] = continuation
      let timeoutWaiter = timeoutWaiter
      timeoutTasks[command.generation] = Task { @MainActor [weak self] in
        await timeoutWaiter.waitForTimeout()
        guard !Task.isCancelled else { return }
        self?.resolve(command, with: .failed(.routeTimedOut))
      }
    }
  }

  @discardableResult
  func acknowledgeVisible(
    generation: UInt64,
    target: DesktopAutomationPresentationTarget
  ) -> Bool {
    guard let activeCommand,
      activeCommand.generation == generation,
      activeCommand.target == target
    else {
      return false
    }

    resolve(activeCommand, with: .presented(activeCommand))
    return true
  }

  @discardableResult
  func rejectUnavailable(
    generation: UInt64,
    target: DesktopAutomationPresentationTarget
  ) -> Bool {
    guard let activeCommand,
      activeCommand.generation == generation,
      activeCommand.target == target
    else {
      return false
    }

    resolve(activeCommand, with: .failed(.presentationUnavailable))
    return true
  }

  private func resolve(
    _ command: DesktopAutomationPresentationCommand,
    with resolution: DesktopAutomationPresentationResolution
  ) {
    timeoutTasks.removeValue(forKey: command.generation)?.cancel()
    if activeCommand?.generation == command.generation {
      activeCommand = nil
    }

    if let continuation = continuations.removeValue(forKey: command.generation) {
      continuation.resume(returning: resolution)
    } else {
      resolutions[command.generation] = resolution
      if resolutions.count > 8, let oldest = resolutions.keys.min() {
        resolutions.removeValue(forKey: oldest)
      }
    }
  }
}

enum DesktopAutomationPresentationRequestResult: Equatable, Sendable {
  case success(DesktopAutomationPresentationCommand)
  case failure(DesktopAutomationPresentationFailure)

  var command: DesktopAutomationPresentationCommand? {
    guard case .success(let command) = self else { return nil }
    return command
  }

  var failure: DesktopAutomationPresentationFailure? {
    guard case .failure(let failure) = self else { return nil }
    return failure
  }

  var statusCode: Int { failure?.statusCode ?? 200 }
  var errorCode: String? { failure?.code }
}

/// Pure route-facing policy around the presentation coordinator. The bridge and
/// behavioral tests use this same handler; HTTP encoding remains in the bridge.
@MainActor
final class DesktopAutomationPresentationRequestHandler {
  static let shared = DesktopAutomationPresentationRequestHandler(
    coordinator: DesktopAutomationPresentationCoordinator.shared
  )

  private let coordinator: any DesktopAutomationPresentationCoordinating

  init(coordinator: any DesktopAutomationPresentationCoordinating) {
    self.coordinator = coordinator
  }

  func openImport(
    identifier: String,
    knownIdentifiers: Set<String>,
    gate: DesktopAutomationPresentationGate
  ) async -> DesktopAutomationPresentationRequestResult {
    guard knownIdentifiers.contains(identifier) else {
      return .failure(.unknownConnector)
    }
    return await present(.importConnector(identifier), gate: gate)
  }

  func openExport(
    identifier: String,
    knownIdentifiers: Set<String>,
    gate: DesktopAutomationPresentationGate
  ) async -> DesktopAutomationPresentationRequestResult {
    guard knownIdentifiers.contains(identifier) else {
      return .failure(.unknownDestination)
    }
    return await present(.exportDestination(identifier), gate: gate)
  }

  private func present(
    _ target: DesktopAutomationPresentationTarget,
    gate: DesktopAutomationPresentationGate
  ) async -> DesktopAutomationPresentationRequestResult {
    switch await coordinator.present(target, gate: gate) {
    case .presented(let command):
      return .success(command)
    case .failed(let failure):
      return .failure(failure)
    }
  }
}
