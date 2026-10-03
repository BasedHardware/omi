import Foundation

private struct AssistantEventDataBox: @unchecked Sendable {
  let value: [String: Any]
  init(_ value: [String: Any]) { self.value = value }
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
  func checkContextSwitch(newApp: String, newWindowTitle: String?) async -> Bool {
    guard lastTrackedApp != nil else {
      lastTrackedApp = newApp
      lastTrackedWindowTitle = newWindowTitle
      return false
    }
    guard
      ContextDetection.didContextChange(
        fromApp: lastTrackedApp, fromWindowTitle: lastTrackedWindowTitle,
        toApp: newApp, toWindowTitle: newWindowTitle
      )
    else { return false }
    let departingFrame = lastTrackedFrame
    lastTrackedApp = newApp
    lastTrackedWindowTitle = newWindowTitle
    if AuthService.shared.isSignedIn, !RewindSettings.shared.isAppExcluded(newApp),
      let event = TaskLocalContextEvent.appWindow(appName: newApp, windowTitle: newWindowTitle)
    {
      let matched = await ContextSubjectBindingService.shared.resolve(event)
      Task { await TaskContextualResurfacingService.shared.observe(matched) }
    }
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
  }

  /// The latest tracked frame as a director grounding candidate. Only frames
  /// captured at or after the visit began qualify here; the departed-visit
  /// bound is applied by the caller with `frameMayGroundDirector` AFTER
  /// re-reading visit freshness, because a bound computed from a pre-lookup
  /// freshness read races the context switch — the switch can land between
  /// that read and this lookup, leaving the lookup unbounded exactly when it
  /// must not be.

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
