import Foundation
import VoiceTurnDomain

/// Physical PCM held while a replacement socket authenticates. Logical turn
/// state remains in `VoiceTurnCoordinator`.
struct RealtimeReplacementAudioBuffer {
  static let maxBufferedAudioBytes = 3_840_000  // 120 s @ 16 kHz s16le

  let turnID: VoiceTurnID
  let responseID: VoiceResponseID
  let identity: VoiceEffectIdentity
  private(set) var audioBuffer: [Data] = []
  private(set) var bufferedAudioBytes = 0

  @discardableResult
  mutating func appendAudio(_ pcm16k: Data) -> Bool {
    let remaining = Self.maxBufferedAudioBytes - bufferedAudioBytes
    guard remaining > 0 else { return false }
    let accepted = pcm16k.count <= remaining ? pcm16k : Data(pcm16k.prefix(remaining))
    guard !accepted.isEmpty else { return false }
    audioBuffer.append(accepted)
    bufferedAudioBytes += accepted.count
    return accepted.count == pcm16k.count
  }
}

/// Captures one PTT turn while a non-barge-in realtime session is reconnecting
/// or its kernel context is being refreshed. Keeping it separate from the
/// barge-in buffer prevents a fresh turn from being accidentally coalesced with
/// a replaced response's input.
struct RealtimeReconnectAudioBuffer {
  static let maxBufferedAudioBytes = 3_840_000  // 120 s @ 16 kHz s16le
  static let maximumRebindAttempts = 1

  let turnID: VoiceTurnID
  let responseID: VoiceResponseID
  let identity: VoiceEffectIdentity
  let interrupting: Bool
  /// Opaque canonical identity that this logical input must observe. Audio may
  /// not leave this buffer until the physical provider binding carries it.
  private(set) var requiredContextFreshnessIdentity: String? = nil
  private(set) var audioBuffer: [Data] = []
  private(set) var bufferedAudioBytes = 0
  /// A captured turn gets one transparent physical-session rebind. The second
  /// concrete transport failure takes the existing transcription fallback; it
  /// must never make the user manually repeat the turn.
  private(set) var rebindAttempts = 0

  @discardableResult
  mutating func appendAudio(_ pcm16k: Data) -> Bool {
    let remaining = Self.maxBufferedAudioBytes - bufferedAudioBytes
    guard remaining > 0 else { return false }
    let accepted = pcm16k.count <= remaining ? pcm16k : Data(pcm16k.prefix(remaining))
    guard !accepted.isEmpty else { return false }
    audioBuffer.append(accepted)
    bufferedAudioBytes += accepted.count
    return accepted.count == pcm16k.count
  }

  mutating func bindRequiredContextFreshnessIdentity(_ identity: String) -> Bool {
    guard !identity.isEmpty else { return false }
    if let existing = requiredContextFreshnessIdentity, existing != identity {
      return false
    }
    requiredContextFreshnessIdentity = identity
    return true
  }

  /// A key-down snapshot can produce a newer canonical requirement before this
  /// turn has replayed to a physical provider. Preserve the logical turn and
  /// its PCM, while retargeting that one replay to the newest binding.
  mutating func replaceRequiredContextFreshnessIdentity(_ identity: String) -> Bool {
    guard !identity.isEmpty else { return false }
    requiredContextFreshnessIdentity = identity
    return true
  }

  @discardableResult
  mutating func beginRebindAttempt() -> Bool {
    guard rebindAttempts < Self.maximumRebindAttempts else { return false }
    rebindAttempts += 1
    return true
  }
}

/// The physical realtime transport is intentionally narrower than logical PTT
/// state. A connected socket is only an optimization; input may be admitted
/// immediately only when its immutable context binding still matches the
/// kernel's current requirement.
enum RealtimePTTAdmission: Equatable {
  case immediate
  case captureAndBuffer
}

enum RealtimePTTAdmissionPolicy {
  static func decide(
    requirementIsResolved: Bool,
    transportIsReady: Bool,
    bindingMatchesRequirement: Bool
  ) -> RealtimePTTAdmission {
    requirementIsResolved && transportIsReady && bindingMatchesRequirement
      ? .immediate
      : .captureAndBuffer
  }
}

/// Every ordinary maintenance cause shares this one handoff vocabulary. Keeping
/// it typed prevents a key-down prefetch, a post-turn refresh, and a cancelled
/// turn from independently deciding to tear down the physical session.
enum RealtimeHubSessionHandoffReason: String, Equatable {
  case voiceContextFreshness = "voice_context_freshness"
  case directedProviderSchema = "directed_provider_schema"
  case persistedVoiceContext = "voice_context_changed"
  case cancelledTurnContinuity = "cancelled_turn_continuity"
  case providerSettings = "provider_settings"
  case systemWake = "system_wake"
  case voiceLanguages = "voice_languages_changed"
  case transportFailure = "transport_failure"
}

enum RealtimeHubSessionHandoffDecision: Equatable {
  case keepActive
  case deferUntilIdle
  case replacePreservingBufferedTurn
  case fallbackToTranscription
}

/// Pure lifecycle oracle for the controller's single physical-session handoff
/// owner. The reducer remains the lifecycle owner of the logical voice turn.
enum RealtimeHubSessionHandoffPolicy {
  static func decide(
    bindingMatchesRequirement: Bool,
    canReplaceIdleSession: Bool,
    hasBufferedTurn: Bool,
    rebindAttempts: Int = 0
  ) -> RealtimeHubSessionHandoffDecision {
    if bindingMatchesRequirement { return .keepActive }
    if hasBufferedTurn {
      return rebindAttempts <= RealtimeReconnectAudioBuffer.maximumRebindAttempts
        ? .replacePreservingBufferedTurn
        : .fallbackToTranscription
    }
    return canReplaceIdleSession ? .replacePreservingBufferedTurn : .deferUntilIdle
  }
}

enum RealtimeInputPreparationResult: Equatable {
  case accepted
  case rejected
}

enum RealtimeInputAdmissionDecision: Equatable {
  case admit
  case rejectSupersededTurn
  case rejectMissingContextIdentity
  case rejectStaleProviderContext
}

/// Pure fail-closed oracle used by production replay and deterministic race
/// tests. Physical transport readiness alone can never return `.admit`.
enum RealtimeInputAdmissionPolicy {
  static func decide(
    pending: RealtimeReconnectAudioBuffer,
    activeTurnID: VoiceTurnID?,
    sessionContextFreshnessIdentity: String
  ) -> RealtimeInputAdmissionDecision {
    guard pending.turnID == activeTurnID else { return .rejectSupersededTurn }
    guard let required = pending.requiredContextFreshnessIdentity, !required.isEmpty else {
      return .rejectMissingContextIdentity
    }
    guard required == sessionContextFreshnessIdentity else {
      return .rejectStaleProviderContext
    }
    return .admit
  }
}

enum RealtimeVoiceContextRefreshPolicy {
  static func requiresRefresh(
    currentSnapshotIdentity: String,
    sessionSnapshotIdentity: String
  ) -> Bool {
    currentSnapshotIdentity != sessionSnapshotIdentity
  }
}
