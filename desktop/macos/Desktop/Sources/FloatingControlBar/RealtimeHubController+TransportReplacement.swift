import Foundation

@MainActor
extension RealtimeHubController {
  var isTransportReady: Bool {
    guard
      RealtimeHubOwnerFence.canReuseWarmSession(
        sessionOwner: sessionOwnerScope,
        currentOwnerID: RuntimeOwnerIdentity.currentOwnerId())
    else {
      if session != nil {
        log("RealtimeHub: refusing warm socket owned by a previous authenticated user")
        discardSessionAfterOwnerChange()
      }
      return false
    }
    return hubConnected
      && (sessionProvider == RealtimeHubSettings.shared.provider
        || sessionProvider == fallbackProvider)
  }

  func replaceSessionAfterDrain(
    preservingReconnectAudio: Bool = false,
    preservingBargeInReplacement: Bool = false,
    reconnectDelayNanoseconds: UInt64 = 0,
    rewarmAfterDrain: Bool = true
  ) {
    guard !sessionReplacementGate.isPending else {
      log("RealtimeHub: coalescing physical replacement while transport drain is pending")
      return
    }
    let detachedSession = detachPhysicalSessionForTeardown(
      preservingReconnectAudio: preservingReconnectAudio,
      preservingBargeInReplacement: preservingBargeInReplacement)
    let ownerGeneration = ownerBoundaryGeneration
    let detachedSessionID = detachedSession.map(ObjectIdentifier.init)
    if let detachedSession, let detachedSessionID {
      detachedSessionsAwaitingDrain[detachedSessionID] = detachedSession
    }
    sessionReplacementGate.replace(
      reconnectDelayNanoseconds: reconnectDelayNanoseconds,
      stop: { [weak self, weak detachedSession] in
        guard let self else { return }
        if let detachedSession {
          await detachedSession.stopAndWait()
        }
        if let detachedSessionID {
          self.detachedSessionsAwaitingDrain.removeValue(forKey: detachedSessionID)
        }
      },
      start: { [weak self] in
        guard let self, self.ownerBoundaryGeneration == ownerGeneration else { return }
        self.reconnectPending = false
        let abandonedBargeInReplacement =
          preservingBargeInReplacement && self.pendingBargeInOwnerScope == nil
        if rewarmAfterDrain || abandonedBargeInReplacement, self.session == nil {
          #if DEBUG
            if let testingWarmAfterDrain = self.testingWarmAfterDrain {
              testingWarmAfterDrain()
              return
            }
          #endif
          self.ensureWarm()
        }
      })
  }

  func schedulePhysicalSessionTeardown(_ detachedSession: RealtimeHubSession) {
    let sessionID = ObjectIdentifier(detachedSession)
    guard detachedSessionsAwaitingDrain[sessionID] == nil else { return }
    detachedSessionsAwaitingDrain[sessionID] = detachedSession
    Task { @MainActor [weak self, weak detachedSession] in
      guard let detachedSession else { return }
      await detachedSession.stopAndWait()
      self?.detachedSessionsAwaitingDrain.removeValue(forKey: sessionID)
    }
  }
}
