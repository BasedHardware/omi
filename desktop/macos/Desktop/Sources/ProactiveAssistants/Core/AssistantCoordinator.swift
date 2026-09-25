import Foundation

private struct AssistantEventDataBox: @unchecked Sendable {
  let value: [String: Any]
  init(_ value: [String: Any]) { self.value = value }
}

/// Serializes persisted context transitions while retaining the latest context
/// observed during an in-flight write. The queue is intentionally a small value
/// type so its coalescing behavior is deterministic and directly testable.
struct ContextTransitionRequest: Equatable, Sendable {
  let app: String
  let windowTitle: String?
}

struct ContextTransitionQueue: Sendable {
  private(set) var inFlight: ContextTransitionRequest?
  private var pending: ContextTransitionRequest?

  /// Starts a transition immediately when idle. While a transition is in
  /// flight, retain only the latest request; callers drain it after completion.
  @discardableResult
  mutating func begin(_ request: ContextTransitionRequest) -> Bool {
    guard inFlight == nil else {
      pending = request
      return false
    }
    inFlight = request
    return true
  }

  /// Completes the current request and returns the latest request observed
  /// while it was in flight, if any.
  mutating func finish(_ request: ContextTransitionRequest) -> ContextTransitionRequest? {
    guard inFlight == request else { return nil }
    inFlight = nil
    let next = pending
    pending = nil
    return next
  }
}

/// A frame candidate for grounding a director evaluation, paired with the
/// moment it entered the tracker. On the switch tick the next context's frame
/// is *captured* before the departing visit's `endedAt` is written, but only
/// *stored* here after the transition persisted the departure — so
/// `storedAt <= endedAt` holds exactly for frames belonging to the departed
/// visit's own context.
struct TrackedDirectorFrame: Sendable {
  let frame: CapturedFrame
  let storedAt: Date
}

/// Coordinates all proactive assistants, distributing frames and managing lifecycle
@MainActor
class AssistantCoordinator {
  static let shared = AssistantCoordinator()

  // MARK: - Properties

  private var assistants: [String: any ProactiveAssistant] = [:]
  private var lastAnalysisTime: [String: Date] = [:]
  private var eventCallback: ((String, [String: Any]) -> Void)?

  // MARK: - Context Tracking (for context switch detection)
  private var lastTrackedApp: String?
  private var lastTrackedWindowTitle: String?
  private var lastTrackedFrame: CapturedFrame?
  private var lastTrackedFrameStoredAt: Date?
  private var contextTransitionQueue = ContextTransitionQueue()

  /// Backpressure: track which assistants are currently analyzing a frame.
  /// Prevents Task closures from accumulating CapturedFrame JPEG data when analyze() is slow.
  private var isAnalyzing: Set<String> = []

  private init() {}

  // MARK: - Registration

  /// Register an assistant with the coordinator
  /// - Parameter assistant: The assistant to register
  func register<T: ProactiveAssistant>(_ assistant: T) {
    Task {
      let id = await assistant.identifier
      assistants[id] = assistant
      lastAnalysisTime[id] = .distantPast
      log("Registered assistant: \(id)")
    }
  }

  /// Unregister an assistant
  /// - Parameter identifier: The identifier of the assistant to remove
  func unregister(identifier: String) {
    assistants.removeValue(forKey: identifier)
    lastAnalysisTime.removeValue(forKey: identifier)
    log("Unregistered assistant: \(identifier)")
  }

  /// Get all registered assistant identifiers
  var registeredAssistants: [String] {
    Array(assistants.keys)
  }

  /// Get an assistant by identifier
  func assistant(withIdentifier id: String) -> (any ProactiveAssistant)? {
    assistants[id]
  }

  // MARK: - Event Callback

  /// Set the callback for sending events to Flutter
  /// - Parameter callback: Function that takes event type and data
  func setEventCallback(_ callback: @escaping (String, [String: Any]) -> Void) {
    self.eventCallback = callback
  }

  /// Send an event to Flutter
  func sendEvent(type: String, data: [String: Any]) {
    eventCallback?(type, data)
  }

  // MARK: - Context Switch Detection

  /// Check if the user's context changed (app or normalized window title) and fire
  /// `onContextSwitch` on all assistants if so. Called by the plugin for both app switches
  /// and window title changes — one unified path with one delay mechanism.
  /// - Returns: `true` if a context switch was detected and fired.
  @discardableResult
  func checkContextSwitch(
    newApp: String,
    newWindowTitle: String?,
    bucketsEnabled: Bool? = nil
  ) async -> Bool {
    // Injectable for tests only; production always reads the live flag.
    let bucketsEnabled = bucketsEnabled ?? ContextBucketsFeature.isEnabled
    let transitionRequest = ContextTransitionRequest(app: newApp, windowTitle: newWindowTitle)
    guard lastTrackedApp != nil else {
      if bucketsEnabled {
        guard contextTransitionQueue.begin(transitionRequest) else { return false }
        defer { finishContextTransition(transitionRequest) }
        guard !RewindSettings.shared.isAppExcluded(newApp) else {
          lastTrackedApp = newApp
          lastTrackedWindowTitle = newWindowTitle
          return false
        }
        do {
          let transition = try await ContextVisitCoordinator.shared.transition(
            toApp: newApp, windowTitle: newWindowTitle, departingFrame: nil)
          Task { await ContextProactivityEngine.shared.contextEntered(transition.arrivingFence) }
        } catch {
          logError("Context buckets: failed to persist initial visit", error: error)
        }
        // Context tracking must not depend on bucket-visit persistence: an unprimed
        // tracker means no context switch is ever detected and every assistant starves.
        lastTrackedApp = newApp
        lastTrackedWindowTitle = newWindowTitle
      } else {
        lastTrackedApp = newApp
        lastTrackedWindowTitle = newWindowTitle
      }
      return false
    }

    let changed = ContextDetection.didContextChange(
      fromApp: lastTrackedApp,
      fromWindowTitle: lastTrackedWindowTitle,
      toApp: newApp,
      toWindowTitle: newWindowTitle
    )
    guard changed else { return false }

    let departingFrame = lastTrackedFrame
    log(
      "Context switch detected: \(lastTrackedApp ?? "nil") (\(ContextDetection.normalizeWindowTitle(lastTrackedWindowTitle) ?? "nil")) -> \(newApp) (\(ContextDetection.normalizeWindowTitle(newWindowTitle) ?? "nil"))"
    )

    // Context is an input to canonical re-evaluation, never permission to
    // notify. Privacy-excluded apps do not even produce a normalized hash.
    if !bucketsEnabled, AuthService.shared.isSignedIn,
      !RewindSettings.shared.isAppExcluded(newApp),
      let event = TaskLocalContextEvent.appWindow(
        appName: newApp,
        windowTitle: newWindowTitle
      )
    {
      lastTrackedApp = newApp
      lastTrackedWindowTitle = newWindowTitle
      let matched = await ContextSubjectBindingService.shared.resolve(event)
      Task { await TaskContextualResurfacingService.shared.observe(matched) }
    }
    if !bucketsEnabled {
      lastTrackedApp = newApp
      lastTrackedWindowTitle = newWindowTitle
    }

    if bucketsEnabled {
      guard contextTransitionQueue.begin(transitionRequest) else { return false }
      defer { finishContextTransition(transitionRequest) }
      if RewindSettings.shared.isAppExcluded(newApp) {
        do {
          let departure = try await ContextVisitCoordinator.shared.leaveForExcludedContext(
            departingFrame: departingFrame)
          if departure.qualified, let fence = departure.fence, let departingFrame {
            Task { await ContextBucketRollupWriter.shared.extract(frame: departingFrame, fence: fence) }
          }
        } catch {
          logError("Context buckets: failed to close visit before excluded context", error: error)
        }
        lastTrackedApp = newApp
        lastTrackedWindowTitle = newWindowTitle
        await fireContextSwitchOnAllAssistants(
          departingFrame: departingFrame, newApp: newApp, newWindowTitle: newWindowTitle)
        return true
      }
      do {
        let transition = try await ContextVisitCoordinator.shared.transition(
          toApp: newApp,
          windowTitle: newWindowTitle,
          departingFrame: departingFrame)
        if transition.departingQualified, let departingFence = transition.departingFence, let departingFrame {
          Task { await ContextBucketRollupWriter.shared.extract(frame: departingFrame, fence: departingFence) }
        }
        Task { await ContextProactivityEngine.shared.contextEntered(transition.arrivingFence) }
      } catch {
        logError("Context buckets: context transition failed", error: error)
      }
      lastTrackedApp = newApp
      lastTrackedWindowTitle = newWindowTitle
      await fireContextSwitchOnAllAssistants(
        departingFrame: departingFrame, newApp: newApp, newWindowTitle: newWindowTitle)
      return true
    }

    // Flag-off rollback path: fire today's independent assistants unchanged.
    await fireContextSwitchOnAllAssistants(
      departingFrame: departingFrame, newApp: newApp, newWindowTitle: newWindowTitle)
    return true
  }

  /// Content-refresh transition for a long dwell whose on-screen content
  /// changed (see `ContextDwellRefreshPolicy`): closes and reopens the ACTIVE
  /// context through the ordinary visit machinery, so the departing frame —
  /// which now contains what the user typed — gets extraction, departure
  /// evaluation, and the fresh visit gets its normal entry evaluation. Every
  /// quota, cooldown, dedup, and budget gate applies unchanged.
  /// Returns the arriving visit's fence so the caller can capture a
  /// post-entry frame BEFORE engaging the director: the entry evaluation only
  /// grounds on frames captured at or after the visit began, and the
  /// preview-skip path may not produce another full frame for a static screen.
  func refreshActiveContextForDwell(
    expectedApp: String, expectedWindowTitle: String?
  ) async -> ContextVisitFence? {
    guard ContextBucketsFeature.isEnabled else { return nil }
    guard let app = lastTrackedApp, let frame = lastTrackedFrame else { return nil }
    // The dwell task is detached from its tick: if the user switched contexts
    // while it awaited, refreshing would close the just-opened visit and
    // extract the OLD context's frame into the NEW context's bucket.
    guard app == expectedApp,
      ContextDetection.normalizeWindowTitle(lastTrackedWindowTitle)
        == ContextDetection.normalizeWindowTitle(expectedWindowTitle)
    else { return nil }
    guard !RewindSettings.shared.isAppExcluded(app) else { return nil }
    // A refused same-context refresh must be DROPPED, not queued: begin()
    // stores a refused request as pending, and finishContextTransition would
    // replay it as a phantom switch back to this context after the in-flight
    // real transition completes.
    guard contextTransitionQueue.inFlight == nil else { return nil }
    let request = ContextTransitionRequest(app: app, windowTitle: lastTrackedWindowTitle)
    guard contextTransitionQueue.begin(request) else { return nil }
    defer { finishContextTransition(request) }
    do {
      let transition = try await ContextVisitCoordinator.shared.transition(
        toApp: app,
        windowTitle: lastTrackedWindowTitle,
        departingFrame: frame)
      if transition.departingQualified, let departingFence = transition.departingFence {
        Task { await ContextBucketRollupWriter.shared.extract(frame: frame, fence: departingFence) }
      }
      return transition.arrivingFence
    } catch {
      logError("Context buckets: content-refresh transition failed", error: error)
      return nil
    }
  }

  /// Releases a completed transition and schedules the latest context observed
  /// during its persistence await. The follow-up runs on the main actor, so it
  /// cannot race the coordinator's tracked state or start a second write in
  /// parallel with the completed request.
  /// Every registered assistant hears every context switch, in buckets mode and out of it.
  ///
  /// The context-buckets rollout forwarded switches only to the task assistant, which
  /// silently starved the suggestion and memory assistants: `SuggestionAssistant.analyze`
  /// returns nil before any logging when no context switch ever armed its dwell anchor,
  /// so focus nudges stopped fleet-wide for everyone in the flag cohort with no error
  /// anywhere (Aug 13–14 2026). Buckets mode changes who WRITES bucket exits, never who
  /// HEARS switches — and hearing a switch must not depend on bucket-visit persistence,
  /// so this fires outside the transition do/catch.
  func fireContextSwitchOnAllAssistants(
    departingFrame: CapturedFrame?,
    newApp: String,
    newWindowTitle: String?
  ) async {
    // Capture the arriving context before any assistant's awaited work so the
    // reminder observation below cannot pair a pre-await title with a
    // post-await frontmost app when the user switches windows mid-loop.
    let arrivingContext = ContextReminderCoordinator.frontmostSnapshotContext()
    for (_, assistant) in assistants {
      await assistant.onContextSwitch(
        departingFrame: departingFrame,
        newApp: newApp,
        newWindowTitle: newWindowTitle
      )
    }
    await ContextReminderCoordinator.shared.observeFrontmostChange(
      arriving: arrivingContext, appName: newApp, windowTitle: newWindowTitle)
  }

  private func finishContextTransition(_ request: ContextTransitionRequest) {
    guard let next = contextTransitionQueue.finish(request) else { return }
    Task { @MainActor [weak self] in
      guard let self else { return }
      _ = await self.checkContextSwitch(newApp: next.app, newWindowTitle: next.windowTitle)
    }
  }

  // MARK: - Frame Tracking & Distribution

  /// The app of the context currently tracked for switches; the dwell task
  /// uses it to drop stale captures after an app switch.
  var currentTrackedApp: String? { lastTrackedApp }

  /// Whether the tracker still points at this exact context. The dwell task
  /// guards every capture with it: an app-only check let a same-app tab/title
  /// switch during the async capture overwrite the tracked frame with the
  /// departed window's pixels, contaminating the active bucket.
  func isTracking(app: String, windowTitle: String?) -> Bool {
    lastTrackedApp == app
      && ContextDetection.normalizeWindowTitle(lastTrackedWindowTitle)
        == ContextDetection.normalizeWindowTitle(windowTitle)
  }

  /// Keep the latest frame reference fresh (call on every capture, even during delay).
  func trackFrame(_ frame: CapturedFrame) {
    lastTrackedFrame = frame
    lastTrackedFrameStoredAt = Date()
  }

  /// The latest tracked frame as a director grounding candidate. Only frames
  /// captured at or after the visit began qualify here; the departed-visit
  /// bound is applied by the caller with `frameMayGroundDirector` AFTER
  /// re-reading visit freshness, because a bound computed from a pre-lookup
  /// freshness read races the context switch — the switch can land between
  /// that read and this lookup, leaving the lookup unbounded exactly when it
  /// must not be.
  func trackedFrameForDirector(startedAt: Date) -> TrackedDirectorFrame? {
    guard
      let frame = lastTrackedFrame,
      let storedAt = lastTrackedFrameStoredAt,
      frame.captureTime >= startedAt
    else { return nil }
    return TrackedDirectorFrame(frame: frame, storedAt: storedAt)
  }

  /// Whether a sampled frame may ground a director evaluation for a visit
  /// whose freshness was read AFTER the frame was sampled.
  ///
  /// Active visit (`endedAt == nil`): any frame captured at or after
  /// `startedAt`, today's behavior. Departed visit: the frame must also have
  /// entered the tracker no later than the departure (`storedAt <= endedAt`).
  /// Capture time alone cannot exclude the next context's screen on the switch
  /// tick — that frame is *captured* before the transition writes `endedAt` —
  /// but it is only *stored* after `checkContextSwitch` (which persists the
  /// departure) returns, so the stored-at bound separates the two exactly. The
  /// capture-time epsilon additionally keeps the frame near the visit's own
  /// window under clock skew.
  nonisolated static func frameMayGroundDirector(
    captureTime: Date, storedAt: Date, startedAt: Date, endedAt: Date?
  ) -> Bool {
    guard captureTime >= startedAt else { return false }
    guard let endedAt else { return true }
    return storedAt <= endedAt
      && captureTime
        <= endedAt.addingTimeInterval(ContextDeliveryBudget.departedFrameCaptureEpsilonSeconds)
  }

  /// Distribute a captured frame to all enabled assistants
  /// - Parameter frame: The captured frame to analyze
  func distributeFrame(_ frame: CapturedFrame) {
    for (identifier, assistant) in assistants {
      // Backpressure: skip if this assistant is still analyzing a previous frame
      guard !isAnalyzing.contains(identifier) else { continue }

      let timeSinceLastAnalysis = Date().timeIntervalSince(lastAnalysisTime[identifier] ?? .distantPast)
      isAnalyzing.insert(identifier)

      Task { [weak self] in
        defer {
          Task { @MainActor in
            self?.isAnalyzing.remove(identifier)
          }
        }

        // Check if assistant is enabled
        guard await assistant.isEnabled else { return }

        // Check if assistant wants to analyze this frame
        guard
          await assistant.shouldAnalyze(frameNumber: frame.frameNumber, timeSinceLastAnalysis: timeSinceLastAnalysis)
        else {
          return
        }

        // Update last analysis time
        await MainActor.run {
          self?.lastAnalysisTime[identifier] = Date()
        }

        // Analyze and handle result
        if let result = await assistant.analyze(frame: frame) {
          await assistant.handleResult(result) { [weak self] type, data in
            let dataBox = AssistantEventDataBox(data)
            Task { @MainActor in
              self?.sendEvent(type: type, data: dataBox.value)
            }
          }
        }
      }
    }
  }

  /// Distribute a frame only to assistants that opted into receiving frames during the delay period.
  /// Used for time-sensitive detections like refocus tracking.
  func distributeFrameDuringDelay(_ frame: CapturedFrame) {
    for (identifier, assistant) in assistants {
      // Backpressure: skip if this assistant is still analyzing a previous frame
      guard !isAnalyzing.contains(identifier) else { continue }

      let timeSinceLastAnalysis = Date().timeIntervalSince(lastAnalysisTime[identifier] ?? .distantPast)
      isAnalyzing.insert(identifier)

      Task { [weak self] in
        defer {
          Task { @MainActor in
            self?.isAnalyzing.remove(identifier)
          }
        }

        guard await assistant.isEnabled else { return }
        guard await assistant.needsFrameDuringDelay else { return }
        guard
          await assistant.shouldAnalyze(frameNumber: frame.frameNumber, timeSinceLastAnalysis: timeSinceLastAnalysis)
        else {
          return
        }

        await MainActor.run {
          self?.lastAnalysisTime[identifier] = Date()
        }

        if let result = await assistant.analyze(frame: frame) {
          await assistant.handleResult(result) { [weak self] type, data in
            let dataBox = AssistantEventDataBox(data)
            Task { @MainActor in
              self?.sendEvent(type: type, data: dataBox.value)
            }
          }
        }
      }
    }
  }

  // MARK: - App Switch Handling

  /// Notify all assistants of an app switch (legacy onAppSwitch callback).
  /// Context switch detection is handled separately via `checkContextSwitch`.
  func notifyAppSwitch(newApp: String) {
    for (_, assistant) in assistants {
      Task {
        await assistant.onAppSwitch(newApp: newApp)
      }
    }
  }

  /// Clear pending work for all assistants
  func clearAllPendingWork() {
    for (_, assistant) in assistants {
      Task {
        await assistant.clearPendingWork()
      }
    }
  }

  // MARK: - Lifecycle

  /// Stop all assistants
  func stopAll() {
    for (_, assistant) in assistants {
      Task {
        await assistant.stop()
      }
    }
  }

  /// Register the default set of assistants
  func registerDefaultAssistants() throws {
    // These will be added as we create the assistants
    // try register(TaskAssistant())
  }
}
