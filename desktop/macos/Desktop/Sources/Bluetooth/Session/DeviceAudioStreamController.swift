import Foundation

/// Owns the device-side lifetime behind a multicast audio stream.
///
/// The first subscriber starts the physical recording session. Every subscriber
/// receives every active-session frame; setup and teardown frames are dropped.
/// The last subscriber leaving cancels and joins in-flight setup before the stop
/// action runs. This closes the race where a consumer could disappear during
/// setup and recording would start afterward without an owner.
@MainActor
final class DeviceAudioStreamController {
  typealias Continuation = AsyncThrowingStream<Data, Error>.Continuation
  typealias StartAction = @MainActor @Sendable () async throws -> Void
  typealias StopAction = @MainActor @Sendable () async throws -> Void

  private enum Phase: Equatable {
    case idle
    case starting(UInt64)
    case active(UInt64)
    case stopping(UInt64)
  }

  private let startAction: StartAction
  private let stopAction: StopAction
  private var phase = Phase.idle
  private var generation: UInt64 = 0
  private var subscribers: [UUID: Continuation] = [:]
  private var setupTask: Task<Void, Never>?
  private var cleanupTask: Task<Void, Never>?
  private var isClosed = false
  private var terminalError: Error?

  init(
    start: @escaping StartAction,
    stop: @escaping StopAction
  ) {
    self.startAction = start
    self.stopAction = stop
  }

  func makeStream() -> AsyncThrowingStream<Data, Error> {
    guard !isClosed else {
      return AsyncThrowingStream { continuation in
        if let terminalError {
          continuation.finish(throwing: terminalError)
        } else {
          continuation.finish()
        }
      }
    }

    let subscriberID = UUID()
    return AsyncThrowingStream { continuation in
      subscribers[subscriberID] = continuation
      continuation.onTermination = { @Sendable [weak self] _ in
        Task { @MainActor [weak self] in
          self?.removeSubscriber(subscriberID)
        }
      }
      startIfNeeded()
    }
  }

  func yield(_ data: Data) {
    guard case .active = phase else { return }

    var terminatedSubscribers: [UUID] = []
    for (subscriberID, continuation) in subscribers {
      if case .terminated = continuation.yield(data) {
        terminatedSubscribers.append(subscriberID)
      }
    }
    for subscriberID in terminatedSubscribers {
      removeSubscriber(subscriberID)
    }
  }

  func finish(throwing error: Error? = nil) async {
    if !isClosed {
      isClosed = true
      terminalError = error
      finishSubscribers(throwing: error)
    }
    let cleanup = stopIfNeeded()
    await cleanup?.value
  }

  private func startIfNeeded() {
    guard !isClosed, !subscribers.isEmpty, phase == .idle else { return }

    generation &+= 1
    let setupGeneration = generation
    phase = .starting(setupGeneration)
    let task = Task { @MainActor [weak self] in
      guard let self else { return }
      do {
        try Task.checkCancellation()
        try await self.startAction()
        self.completeStart(generation: setupGeneration, error: nil)
      } catch {
        self.completeStart(generation: setupGeneration, error: error)
      }
    }
    setupTask = task
  }

  private func completeStart(generation setupGeneration: UInt64, error: Error?) {
    guard phase == .starting(setupGeneration) else { return }
    setupTask = nil

    if let error {
      // Setup may have completed some physical steps before failing.
      // Treat it as active until the stop action has unwound them.
      phase = .active(setupGeneration)
      finishSubscribers(throwing: error)
      _ = stopIfNeeded()
      return
    }

    phase = .active(setupGeneration)
  }

  private func removeSubscriber(_ subscriberID: UUID) {
    subscribers.removeValue(forKey: subscriberID)
    if subscribers.isEmpty {
      _ = stopIfNeeded()
    }
  }

  @discardableResult
  private func stopIfNeeded() -> Task<Void, Never>? {
    switch phase {
    case .idle:
      return cleanupTask
    case .stopping:
      return cleanupTask
    case .starting, .active:
      generation &+= 1
      let cleanupGeneration = generation
      phase = .stopping(cleanupGeneration)

      let setup = setupTask
      setupTask = nil
      setup?.cancel()
      let task = Task { @MainActor [weak self] in
        await setup?.value
        guard let self else { return }
        do {
          try await self.stopAction()
          self.completeStop(generation: cleanupGeneration, error: nil)
        } catch {
          self.completeStop(generation: cleanupGeneration, error: error)
        }
      }
      cleanupTask = task
      return task
    }
  }

  private func completeStop(generation cleanupGeneration: UInt64, error: Error?) {
    guard phase == .stopping(cleanupGeneration) else { return }
    cleanupTask = nil
    phase = .idle

    if let error {
      terminalError = error
      isClosed = true
      finishSubscribers(throwing: error)
      return
    }
    startIfNeeded()
  }

  private func finishSubscribers(throwing error: Error?) {
    let currentSubscribers = Array(subscribers.values)
    subscribers.removeAll()
    for continuation in currentSubscribers {
      if let error {
        continuation.finish(throwing: error)
      } else {
        continuation.finish()
      }
    }
  }
}
