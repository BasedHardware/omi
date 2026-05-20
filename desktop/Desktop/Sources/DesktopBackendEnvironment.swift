import Foundation

enum DesktopBackendEnvironment {
  enum BackendMode: Equatable {
    case cloud
    case localDaemon
    case customRemote
  }

  enum Capability: String, CaseIterable, Equatable {
    case localConversationData
    case firebaseSignIn
    case directSTT
    case directChat
    case directEmbeddings
    case localMemoryWiki
    case optionalCloudSTT
    case optionalCloudChat
    case managedAgentVM
    case omiBackendProviderProxy
    case publicSharing
    case cloudSync
    case payments
    case crispSupport
    case hostedTranscription
  }

  struct CapabilityState: Equatable {
    let capability: Capability
    let available: Bool
    let reason: String?
  }

  struct BackendTarget: Equatable {
    let mode: BackendMode
    let baseURL: String
    let requiresAuth: Bool
  }

  static let productionPythonAPIURL = "https://api.omi.me/"
  static let developmentPythonAPIURL = "https://api.omiapi.com/"
  static let developmentRustBackendURL = "https://desktop-backend-dt5lrfkkoa-uc.a.run.app/"
  static let defaultLocalDaemonURL = "http://127.0.0.1:8765/"

  static var selectedBackendTarget: BackendTarget {
    selectedBackendTarget(
      modeValue: currentEnvironmentValue("OMI_DESKTOP_BACKEND_MODE")
        ?? currentEnvironmentValue("OMI_BACKEND_MODE"),
      pythonEnvironmentValue: currentEnvironmentValue("OMI_PYTHON_API_URL"),
      localDaemonEnvironmentValue: currentEnvironmentValue("OMI_LOCAL_DAEMON_URL")
    )
  }

  static func selectedBackendTarget(
    modeValue: String?,
    pythonEnvironmentValue: String?,
    localDaemonEnvironmentValue: String?
  ) -> BackendTarget {
    switch normalizedMode(modeValue) {
    case "local", "local-daemon", "local_daemon", "daemon":
      return BackendTarget(
        mode: .localDaemon,
        baseURL: localDaemonBaseURL(environmentValue: localDaemonEnvironmentValue),
        requiresAuth: false
      )
    case "custom", "remote", "custom-remote", "custom_remote":
      return BackendTarget(
        mode: .customRemote,
        baseURL: pythonBaseURL(
          useDevelopmentBackends: false,
          environmentValue: pythonEnvironmentValue
        ),
        requiresAuth: true
      )
    default:
      return BackendTarget(
        mode: .cloud,
        baseURL: pythonBaseURL(environmentValue: pythonEnvironmentValue),
        requiresAuth: true
      )
    }
  }

  static var shouldUseDevelopmentBackends: Bool {
    shouldUseDevelopmentBackends(
      bundleIdentifier: AppBuild.bundleIdentifier,
      updateChannel: AppBuild.currentUpdateChannel,
      forceOverride: currentEnvironmentValue("OMI_FORCE_DEV_BACKENDS")
    )
  }

  static func shouldUseDevelopmentBackends(
    bundleIdentifier: String,
    updateChannel: String,
    forceOverride: String? = nil
  ) -> Bool {
    // Beta channel of the production bundle routes to the dev backend
    // (api.omiapi.com + dev Cloud Run desktop-backend). The dev backend is
    // configured to use prod Firebase (project_id=based-hardware, prod service
    // account, prod FIREBASE_API_KEY), so custom tokens it mints resolve to the
    // same UID a user has on prod — and reads/writes hit prod Firestore. Same
    // pattern as mobile TestFlight → staging.
    //
    // PR #7014 (April 2026) was reverted because at that time the dev backend
    // was wired to the based-hardware-dev Firebase project, so beta users
    // ended up signed in as fresh empty UIDs. The infra has since been moved
    // onto prod Firebase. Verify before any future revert: dev backend
    // /v1/auth/token must mint custom tokens whose UID matches prod.
    if isAffirmative(forceOverride) {
      return true
    }

    return bundleIdentifier == AppBuild.productionBundleIdentifier
      && normalizedChannel(updateChannel) == "beta"
  }

  static func pythonBaseURL(
    environmentValue: String? = currentEnvironmentValue("OMI_PYTHON_API_URL")
  ) -> String {
    pythonBaseURL(
      useDevelopmentBackends: shouldUseDevelopmentBackends,
      environmentValue: environmentValue
    )
  }

  static func pythonBaseURL(useDevelopmentBackends: Bool, environmentValue: String?) -> String {
    if useDevelopmentBackends {
      return developmentPythonAPIURL
    }

    if let url = normalizedURL(environmentValue) {
      return url
    }

    return productionPythonAPIURL
  }

  static func rustBackendURL(
    environmentValue: String? = currentEnvironmentValue("OMI_DESKTOP_API_URL"),
    launchEnvironmentValue: String? = ProcessInfo.processInfo.environment["OMI_DESKTOP_API_URL"]
  ) -> String {
    rustBackendURL(
      useDevelopmentBackends: shouldUseDevelopmentBackends,
      environmentValue: environmentValue,
      launchEnvironmentValue: launchEnvironmentValue
    )
  }

  static func rustBackendURL(
    useDevelopmentBackends: Bool,
    environmentValue: String?,
    launchEnvironmentValue: String?
  ) -> String {
    if useDevelopmentBackends {
      return developmentRustBackendURL
    }

    if let url = normalizedURL(environmentValue) {
      return url
    }

    if let url = normalizedURL(launchEnvironmentValue) {
      return url
    }

    return ""
  }

  static func localDaemonBaseURL(
    environmentValue: String? = currentEnvironmentValue("OMI_LOCAL_DAEMON_URL")
  ) -> String {
    normalizedURL(environmentValue) ?? defaultLocalDaemonURL
  }

  static func capabilities(for mode: BackendMode) -> [CapabilityState] {
    Capability.allCases.map { capability in
      CapabilityState(
        capability: capability,
        available: isCapability(capability, availableIn: mode),
        reason: unavailableReason(for: capability, in: mode)
      )
    }
  }

  static func isCapability(_ capability: Capability, availableIn mode: BackendMode) -> Bool {
    guard mode == .localDaemon else {
      return true
    }

    switch capability {
    case .localConversationData, .firebaseSignIn:
      return true
    case .directSTT:
      if hybridDirectSTTExplicitlyDisabled() {
        return false
      }
      if isAffirmative(currentEnvironmentValue("OMI_HYBRID_DIRECT_STT_ENABLED")) {
        return true
      }
      return LocalSpeechTranscriptionAdapter.isRecognitionEngineAvailableForPreferredSystemLanguages()
    case .directChat:
      return isAffirmative(currentEnvironmentValue("OMI_HYBRID_DIRECT_CHAT_ENABLED"))
    case .directEmbeddings:
      return isAffirmative(currentEnvironmentValue("OMI_HYBRID_DIRECT_EMBEDDINGS_ENABLED"))
    case .localMemoryWiki:
      return CodexAuthService.isActive || !MemorySearchMode.usesVectorEmbeddings
    case .optionalCloudSTT:
      return isAffirmative(currentEnvironmentValue("OMI_HYBRID_OPTIONAL_CLOUD_STT"))
    case .optionalCloudChat:
      return isAffirmative(currentEnvironmentValue("OMI_HYBRID_OPTIONAL_CLOUD_CHAT"))
    case .managedAgentVM,
         .omiBackendProviderProxy,
         .publicSharing,
         .cloudSync,
         .payments,
         .crispSupport,
         .hostedTranscription:
      return false
    }
  }

  static func unavailableReason(for capability: Capability, in mode: BackendMode) -> String? {
    guard !isCapability(capability, availableIn: mode) else {
      return nil
    }

    switch capability {
    case .directSTT:
      if hybridDirectSTTExplicitlyDisabled() {
        return "Direct local speech-to-text is disabled (OMI_HYBRID_DIRECT_STT_ENABLED is off)."
      }
      return
        "Apple Speech is not available for this Mac’s preferred languages (or Speech Recognition is off in System Settings). Set OMI_HYBRID_DIRECT_STT_ENABLED=1 to opt in when the engine is available."
    case .directChat:
      return
        "Direct local chat requires OMI_HYBRID_DIRECT_CHAT_ENABLED=1 and a resolved chat slot in local provider policy."
    case .directEmbeddings:
      return
        "Direct local embeddings require OMI_HYBRID_DIRECT_EMBEDDINGS_ENABLED=1 and an embedding_provider in hybrid settings."
    case .localMemoryWiki:
      return "Local memory wiki (FTS) is off while vector embeddings mode is enabled."
    case .optionalCloudSTT:
      return "Optional cloud speech-to-text is off. Set OMI_HYBRID_OPTIONAL_CLOUD_STT=1 to allow hosted Listen."
    case .optionalCloudChat:
      return "Optional cloud chat is off. Set OMI_HYBRID_OPTIONAL_CLOUD_CHAT=1 to allow Omi-hosted chat."
    case .managedAgentVM:
      return "Managed agent VMs are cloud-only and are disabled in local daemon mode."
    case .omiBackendProviderProxy:
      return "Omi backend provider proxies are not used in local daemon mode. Configure direct local provider settings instead."
    case .publicSharing:
      return "Public sharing requires Omi cloud-hosted URLs and is unavailable in local daemon mode."
    case .cloudSync:
      return "Cloud sync is intentionally disabled while local data is the source of truth."
    case .payments:
      return "Subscription and payment-gated features require Omi cloud services."
    case .crispSupport:
      return "Crisp support messaging is cloud-bound and is disabled in local daemon mode."
    case .hostedTranscription:
      return "Hosted transcription endpoints are disabled in local daemon mode; local transcripts are stored through the local daemon."
    case .localConversationData, .firebaseSignIn:
      return nil
    }
  }

  static func applyReleaseChannelDefaults() {
    guard shouldUseDevelopmentBackends else { return }

    setenv("OMI_PYTHON_API_URL", developmentPythonAPIURL, 1)
    setenv("OMI_DESKTOP_API_URL", developmentRustBackendURL, 1)
    log("BackendEnvironment: beta channel using development backends with production data stores")
  }

  private static func normalizedChannel(_ channel: String) -> String {
    let normalized = channel.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
    return normalized == "staging" ? "beta" : normalized
  }

  private static func normalizedURL(_ raw: String?) -> String? {
    guard let raw else { return nil }
    let trimmed = raw.trimmingCharacters(in: .whitespacesAndNewlines)
    guard !trimmed.isEmpty else { return nil }
    return trimmed.hasSuffix("/") ? trimmed : trimmed + "/"
  }

  private static func normalizedMode(_ raw: String?) -> String {
    raw?.trimmingCharacters(in: .whitespacesAndNewlines).lowercased() ?? "cloud"
  }

  private static func currentEnvironmentValue(_ key: String) -> String? {
    guard let value = getenv(key), let string = String(validatingUTF8: value) else {
      return nil
    }
    return string
  }

  private static func isAffirmative(_ value: String?) -> Bool {
    guard let value else { return false }
    let normalized = value.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
    return normalized == "1" || normalized == "true" || normalized == "yes"
  }

  /// Treats `OMI_HYBRID_DIRECT_STT_ENABLED=0|false|no|off` as an explicit hybrid direct-STT kill switch.
  private static func hybridDirectSTTExplicitlyDisabled() -> Bool {
    guard let raw = currentEnvironmentValue("OMI_HYBRID_DIRECT_STT_ENABLED") else { return false }
    let n = raw.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
    return n == "0" || n == "false" || n == "no" || n == "off"
  }
}
