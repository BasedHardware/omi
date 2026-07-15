import CryptoKit
import Foundation

enum AuthorizedRealtimeToolExecutionResult: Equatable, Sendable {
  case succeeded(String)
  case failed(String)

  var wireOutcome: String {
    switch self {
    case .succeeded: return "succeeded"
    case .failed: return "failed"
    }
  }

  var wireResult: String {
    switch self {
    case .succeeded(let result), .failed(let result): return result
    }
  }
}

/// A kernel-authorized physical tool command.
///
/// Authorization state never lives in Swift. The kernel persists and validates
/// the single-use invocation before emitting this immutable command; Swift only
/// validates the physical execution envelope and generated executor boundary.
struct AuthorizedToolExecution: @unchecked Sendable {
  enum EffectClass: String, Sendable {
    case readOnly = "read_only"
    case idempotentWrite = "idempotent_write"
    case nonIdempotentWrite = "non_idempotent_write"
  }

  enum RetryPolicy: String, Sendable {
    case safeRetry = "safe_retry"
    case neverAutoRetry = "never_auto_retry"
  }

  enum PolicyRecovery: String, Sendable {
    case permissionDelegationToNative = "permission_delegation_to_native"
  }

  enum Rejection: Error, Equatable, Sendable {
    case malformed
    case wrongOwner
    case staleManifest
    case unsupportedExecutor
    case invalidRetryPolicy
    case invalidPolicyRecovery
    case inputHashMismatch
    case invalidChatFirstCapability
    case ownerChangedDuringExecution

    var code: String {
      switch self {
      case .malformed: return "malformed_authorized_execution"
      case .wrongOwner: return "authorized_execution_owner_mismatch"
      case .staleManifest: return "authorized_execution_manifest_mismatch"
      case .unsupportedExecutor: return "unsupported_swift_executor"
      case .invalidRetryPolicy: return "invalid_execution_retry_policy"
      case .invalidPolicyRecovery: return "invalid_execution_policy_recovery"
      case .inputHashMismatch: return "authorized_execution_input_hash_mismatch"
      case .invalidChatFirstCapability: return "authorized_execution_chat_first_capability_mismatch"
      case .ownerChangedDuringExecution: return "authorized_execution_owner_changed"
      }
    }
  }

  let invocationID: String
  let ownerID: String
  let sessionID: String
  let runID: String
  let attemptID: String
  let profileGeneration: Int
  let manifestVersion: Int
  let manifestDigest: String
  let daemonBootEpoch: String
  let executionGeneration: Int
  let capabilityRef: String
  let canonicalToolName: String
  let input: [String: Any]
  let inputHash: String
  let effectClass: EffectClass
  let retryPolicy: RetryPolicy
  let policyRecovery: PolicyRecovery?
  let executor: GeneratedSwiftToolExecutor
  let surfaceKind: String
  let externalRefKind: String?
  let externalRefID: String?
  let originatingUserText: String
  let precedingAssistantText: String?
  let runMode: String
  let chatMode: String?
  let chatFirstControlGeneration: Int?

  static func parse(
    _ payload: [String: Any],
    currentOwnerID: String?
  ) throws -> AuthorizedToolExecution {
    func requiredString(_ key: String) throws -> String {
      guard
        let value = payload[key] as? String,
        !value.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
      else {
        throw Rejection.malformed
      }
      return value
    }

    let ownerID = try requiredString("ownerId")
    guard currentOwnerID == ownerID else {
      throw Rejection.wrongOwner
    }
    let requestedToolName = try requiredString("toolName")
    guard let resolvedTool = GeneratedToolExecutors.resolve(requestedToolName),
      let executor = GeneratedToolExecutors.executorByTool[resolvedTool]
    else {
      throw Rejection.unsupportedExecutor
    }
    let manifestVersion = payload["manifestVersion"] as? Int ?? 0
    guard manifestVersion == GeneratedToolExecutors.manifestVersion else {
      throw Rejection.staleManifest
    }
    let manifestDigest = try requiredString("manifestDigest")
    let expectedManifestDigest = resolvedTool == .renderChatBlocks
      ? GeneratedToolExecutors.chatFirstManifestDigest
      : GeneratedToolExecutors.manifestDigest
    guard manifestDigest == expectedManifestDigest else {
      throw Rejection.staleManifest
    }
    guard
      let effectClass = EffectClass(rawValue: try requiredString("effectClass")),
      let retryPolicy = RetryPolicy(rawValue: try requiredString("retryPolicy"))
    else {
      throw Rejection.malformed
    }
    guard effectClass != .nonIdempotentWrite || retryPolicy == .neverAutoRetry else {
      throw Rejection.invalidRetryPolicy
    }
    let policyRecovery: PolicyRecovery?
    if let rawPolicyRecovery = payload["policyRecovery"] as? String {
      guard let parsed = PolicyRecovery(rawValue: rawPolicyRecovery),
        ["request_permission", "check_permission_status"].contains(resolvedTool.rawValue)
      else {
        throw Rejection.invalidPolicyRecovery
      }
      policyRecovery = parsed
    } else if payload["policyRecovery"] == nil || payload["policyRecovery"] is NSNull {
      policyRecovery = nil
    } else {
      throw Rejection.invalidPolicyRecovery
    }
    let profileGeneration = payload["profileGeneration"] as? Int ?? 0
    let executionGeneration = payload["executionGeneration"] as? Int ?? 0
    guard profileGeneration > 0, executionGeneration > 0 else {
      throw Rejection.malformed
    }
    let runMode = try requiredString("runMode")
    guard ["ask", "act"].contains(runMode) else {
      throw Rejection.malformed
    }

    let input = payload["input"] as? [String: Any] ?? [:]
    let expectedInputHash = try requiredString("inputHash")
    guard try inputHash(for: input) == expectedInputHash else {
      throw Rejection.inputHashMismatch
    }
    let surfaceKind = try requiredString("surfaceKind")
    let chatFirstControlGeneration = payload["chatFirstControlGeneration"] as? Int
    if resolvedTool == .renderChatBlocks {
      guard surfaceKind == "main_chat",
        let chatFirstControlGeneration,
        chatFirstControlGeneration >= 0
      else {
        throw Rejection.invalidChatFirstCapability
      }
    } else if chatFirstControlGeneration != nil {
      throw Rejection.invalidChatFirstCapability
    }

    return AuthorizedToolExecution(
      invocationID: try requiredString("invocationId"),
      ownerID: ownerID,
      sessionID: try requiredString("sessionId"),
      runID: try requiredString("runId"),
      attemptID: try requiredString("attemptId"),
      profileGeneration: profileGeneration,
      manifestVersion: manifestVersion,
      manifestDigest: manifestDigest,
      daemonBootEpoch: try requiredString("daemonBootEpoch"),
      executionGeneration: executionGeneration,
      capabilityRef: try requiredString("capabilityRef"),
      canonicalToolName: resolvedTool.rawValue,
      input: input,
      inputHash: expectedInputHash,
      effectClass: effectClass,
      retryPolicy: retryPolicy,
      policyRecovery: policyRecovery,
      executor: executor,
      surfaceKind: surfaceKind,
      externalRefKind: payload["externalRefKind"] as? String,
      externalRefID: payload["externalRefId"] as? String,
      originatingUserText: payload["originatingUserText"] as? String ?? "",
      precedingAssistantText: payload["precedingAssistantText"] as? String,
      runMode: runMode,
      chatMode: payload["chatMode"] as? String,
      chatFirstControlGeneration: chatFirstControlGeneration)
  }

  static func inputHash(for input: [String: Any]) throws -> String {
    guard JSONSerialization.isValidJSONObject(input) else {
      throw Rejection.malformed
    }
    let canonical = try JSONSerialization.data(
      withJSONObject: input,
      options: [.sortedKeys])
    let digest = SHA256.hash(data: canonical)
      .map { String(format: "%02x", $0) }
      .joined()
    return "sha256:\(digest)"
  }

  static func isOwnerCurrent(
    _ expectedOwnerID: String,
    defaults: UserDefaults = .standard,
    allowAutomationOverride: Bool = AppBuild.isNonProduction
  ) -> Bool {
    let normalized = expectedOwnerID.trimmingCharacters(in: .whitespacesAndNewlines)
    guard !normalized.isEmpty else { return false }
    let authenticatedOwnerID = defaults.string(forKey: .authUserId)?
      .trimmingCharacters(in: .whitespacesAndNewlines)
    return RuntimeOwnerIdentity.currentOwnerId(
      defaults: defaults,
      allowAutomationOverride: allowAutomationOverride) == normalized
      && authenticatedOwnerID == normalized
  }
}
