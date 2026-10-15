import AppKit
import Combine
import Foundation

extension Notification.Name {
  static let assistantVoiceDidChange = Notification.Name("com.omi.desktop.assistantVoiceDidChange")
}

@MainActor
final class AssistantVoiceStore: ObservableObject {
  static let shared = AssistantVoiceStore()

  static let defaultVoiceID = "Charon"

  /// The backend-curated voices available from the voice picker.
  @Published private(set) var catalog: [AssistantVoiceEntry] = []
  /// Selected voice ID for floating-bar TTS replies and live Gemini sessions.
  @Published private(set) var selectedVoiceID: String = AssistantVoiceStore.defaultVoiceID
  @Published private(set) var defaultVoiceID: String = AssistantVoiceStore.defaultVoiceID
  @Published private(set) var isLoading = false
  @Published private(set) var isSaving = false
  @Published private(set) var lastError: String?

  private let fetchCatalog: (RuntimeOwnerAuthorizationSnapshot) async throws -> AssistantVoiceCatalogResponse
  private let fetchPreference: (RuntimeOwnerAuthorizationSnapshot) async throws -> AssistantVoicePreferenceResponse
  private let savePreference:
    (String, RuntimeOwnerAuthorizationSnapshot) async throws -> AssistantVoicePreferenceResponse
  private let captureOwner: () -> RuntimeOwnerAuthorizationSnapshot?
  private let isAuthorized: (RuntimeOwnerAuthorizationSnapshot) -> Bool
  private let ownerIDProvider: () -> String?
  private let defaults: UserDefaults
  private let notificationCenter: NotificationCenter

  private var epoch = 0
  private var selectionOwnerID: String?
  private var observers: [NSObjectProtocol] = []

  init(
    fetchCatalog: (
      (RuntimeOwnerAuthorizationSnapshot) async throws -> AssistantVoiceCatalogResponse
    )? = nil,
    fetchPreference: (
      (RuntimeOwnerAuthorizationSnapshot) async throws -> AssistantVoicePreferenceResponse
    )? = nil,
    savePreference: (
      (String, RuntimeOwnerAuthorizationSnapshot) async throws -> AssistantVoicePreferenceResponse
    )? = nil,
    captureOwner: @escaping () -> RuntimeOwnerAuthorizationSnapshot? = {
      RuntimeOwnerIdentity.captureAuthorizationSnapshot()
    },
    isAuthorized: @escaping (RuntimeOwnerAuthorizationSnapshot) -> Bool = {
      RuntimeOwnerIdentity.isAuthorizationCurrent($0)
    },
    ownerIDProvider: @escaping () -> String? = { RuntimeOwnerIdentity.currentOwnerId() },
    defaults: UserDefaults = .standard,
    notificationCenter: NotificationCenter = .default,
    observeOwnerChanges: Bool = true
  ) {
    self.fetchCatalog =
      fetchCatalog ?? { snapshot in
        try await APIClient.shared.getAssistantVoiceCatalog(
          expectedOwnerId: snapshot.ownerID, authorizationSnapshot: snapshot)
      }
    self.fetchPreference =
      fetchPreference ?? { snapshot in
        try await APIClient.shared.getAssistantVoicePreference(
          expectedOwnerId: snapshot.ownerID, authorizationSnapshot: snapshot)
      }
    self.savePreference =
      savePreference ?? { voiceID, snapshot in
        try await APIClient.shared.setAssistantVoicePreference(
          voiceId: voiceID, expectedOwnerId: snapshot.ownerID, authorizationSnapshot: snapshot)
      }
    self.captureOwner = captureOwner
    self.isAuthorized = isAuthorized
    self.ownerIDProvider = ownerIDProvider
    self.defaults = defaults
    self.notificationCenter = notificationCenter

    applyCachedSelection()
    if observeOwnerChanges {
      observers.append(
        notificationCenter.addObserver(
          forName: .runtimeOwnerDidChange, object: nil, queue: nil
        ) { [weak self] _ in
          Task { @MainActor [weak self] in
            await self?.handleRuntimeOwnerDidChange()
          }
        })
      observers.append(
        notificationCenter.addObserver(
          forName: NSApplication.didBecomeActiveNotification, object: nil, queue: nil
        ) { [weak self] _ in
          Task { @MainActor [weak self] in
            await self?.refresh()
          }
        })
    }
  }

  var currentVoiceID: String {
    guard let owner = selectionOwnerID, owner == ownerIDProvider() else {
      return Self.defaultVoiceID
    }
    return selectedVoiceID
  }

  private var cacheKey: ScopedDefaultsKey? {
    guard let ownerID = ownerIDProvider() else { return nil }
    return .assistantVoiceID(ownerID: ownerID)
  }

  private func applyCachedSelection() {
    guard let key = cacheKey, let cached = defaults.string(forKey: key), !cached.isEmpty else {
      selectedVoiceID = defaultVoiceID
      selectionOwnerID = nil
      return
    }
    selectedVoiceID = cached
    selectionOwnerID = ownerIDProvider()
  }

  func handleRuntimeOwnerDidChange() async {
    epoch += 1
    isLoading = false
    isSaving = false
    lastError = nil
    catalog = []
    defaultVoiceID = Self.defaultVoiceID
    applyCachedSelection()
    await refresh()
  }

  func refresh() async {
    guard !isSaving, let owner = captureOwner() else { return }
    epoch += 1
    let epochAtStart = epoch
    isLoading = true
    defer {
      if epoch == epochAtStart { isLoading = false }
    }
    do {
      let remoteCatalog = try await fetchCatalog(owner)
      guard epoch == epochAtStart, isAuthorized(owner) else { return }
      let remotePreference = try await fetchPreference(owner)
      guard epoch == epochAtStart, isAuthorized(owner) else { return }
      catalog = Self.deduped(remoteCatalog.voices)
      defaultVoiceID =
        remoteCatalog.defaultVoiceId.isEmpty ? Self.defaultVoiceID : remoteCatalog.defaultVoiceId
      let remoteSelection =
        catalog.contains { $0.id == remotePreference.voiceId }
        ? remotePreference.voiceId
        : defaultVoiceID
      applyPreference(remoteSelection)
      lastError = nil
    } catch {
      guard epoch == epochAtStart, isAuthorized(owner) else { return }
      lastError = error.localizedDescription
    }
  }

  func save(voiceID: String) async {
    guard !isSaving, let owner = captureOwner() else { return }
    epoch += 1
    let epochAtStart = epoch
    isSaving = true
    isLoading = false
    defer {
      if epoch == epochAtStart { isSaving = false }
    }
    do {
      let ack = try await savePreference(voiceID, owner)
      guard epoch == epochAtStart, isAuthorized(owner) else { return }
      applyPreference(ack.voiceId)
      lastError = nil
    } catch {
      guard epoch == epochAtStart, isAuthorized(owner) else { return }
      lastError = error.localizedDescription
    }
  }

  private static func deduped(_ voices: [AssistantVoiceEntry]) -> [AssistantVoiceEntry] {
    var order: [String] = []
    var byID: [String: AssistantVoiceEntry] = [:]
    for voice in voices {
      if byID[voice.id] == nil { order.append(voice.id) }
      byID[voice.id] = voice
    }
    return order.compactMap { byID[$0] }
  }

  private func applyPreference(_ voiceID: String) {
    let normalized = voiceID.isEmpty ? defaultVoiceID : voiceID
    guard normalized != selectedVoiceID || selectionOwnerID != ownerIDProvider() else { return }
    selectedVoiceID = normalized
    selectionOwnerID = ownerIDProvider()
    if let key = cacheKey {
      defaults.set(normalized, forKey: key)
    }
    notificationCenter.post(name: .assistantVoiceDidChange, object: nil)
  }
}
