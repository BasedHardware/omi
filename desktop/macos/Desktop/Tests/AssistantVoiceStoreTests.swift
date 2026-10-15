import Foundation
import XCTest

@testable import Omi_Computer

@MainActor
final class AssistantVoiceStoreTests: XCTestCase {

  private nonisolated static let catalogResponse = AssistantVoiceCatalogResponse(
    voices: [
      AssistantVoiceEntry(id: "Charon", name: "Charon"),
      AssistantVoiceEntry(id: "Kore", name: "Kore"),
      AssistantVoiceEntry(id: "Puck", name: "Puck"),
    ],
    defaultVoiceId: "Charon")

  private let fixture = RuntimeOwnerAuthorityTestFixture()

  override func setUp() async throws {
    await fixture.establish(authOwnerID: "owner-1")
  }

  override func tearDown() async throws {
    await fixture.restore()
  }

  private func makeDefaults() throws -> UserDefaults {
    let name = "AssistantVoiceStoreTests.\(UUID().uuidString)"
    let defaults = try XCTUnwrap(UserDefaults(suiteName: name))
    addTeardownBlock { defaults.removePersistentDomain(forName: name) }
    return defaults
  }

  private func makeStore(
    catalog: AssistantVoiceCatalogResponse = AssistantVoiceStoreTests.catalogResponse,
    preference: String = "Kore",
    saveHandler: (@Sendable (String) async throws -> AssistantVoicePreferenceResponse)? = nil,
    defaults: UserDefaults? = nil,
    notificationCenter: NotificationCenter = NotificationCenter(),
    observeOwnerChanges: Bool = false
  ) throws -> AssistantVoiceStore {
    AssistantVoiceStore(
      fetchCatalog: { _ in catalog },
      fetchPreference: { _ in AssistantVoicePreferenceResponse(voiceId: preference) },
      savePreference: { voiceID, _ in
        try await (saveHandler ?? { AssistantVoicePreferenceResponse(voiceId: $0) })(voiceID)
      },
      defaults: try defaults ?? makeDefaults(),
      notificationCenter: notificationCenter,
      observeOwnerChanges: observeOwnerChanges)
  }

  func testRefreshAppliesRemoteSelectionAndCatalog() async throws {
    let store = try makeStore(preference: "Kore")
    await store.refresh()
    XCTAssertEqual(store.selectedVoiceID, "Kore")
    XCTAssertEqual(store.defaultVoiceID, "Charon")
    XCTAssertEqual(store.catalog.map(\.id), ["Charon", "Kore", "Puck"])
    XCTAssertNil(store.lastError)
  }

  func testSignedOutOwnerPerformsNoRequest() async throws {
    await fixture.establish(authOwnerID: nil)
    var requestCount = 0
    let store = AssistantVoiceStore(
      fetchCatalog: { _ in
        requestCount += 1
        return AssistantVoiceStoreTests.catalogResponse
      },
      fetchPreference: { _ in
        requestCount += 1
        return AssistantVoicePreferenceResponse(voiceId: "Kore")
      },
      savePreference: { _, _ in
        requestCount += 1
        return AssistantVoicePreferenceResponse(voiceId: "Kore")
      },
      defaults: try makeDefaults(),
      notificationCenter: NotificationCenter(),
      observeOwnerChanges: false)
    await store.refresh()
    await store.save(voiceID: "Puck")
    XCTAssertEqual(requestCount, 0)
    XCTAssertEqual(store.currentVoiceID, AssistantVoiceStore.defaultVoiceID)
  }

  func testSaveAppliesServerAckNotRequestedID() async throws {
    let store = try makeStore(
      saveHandler: { _ in AssistantVoicePreferenceResponse(voiceId: "Charon") })
    await store.save(voiceID: "MadeUpVoice")
    XCTAssertEqual(store.selectedVoiceID, "Charon")
    XCTAssertFalse(store.isSaving)
  }

  func testFailedSaveRetainsPreviousSelection() async throws {
    let store = try makeStore(
      preference: "Kore",
      saveHandler: { _ in throw APIError.unauthorized })
    await store.refresh()
    await store.save(voiceID: "Puck")
    XCTAssertEqual(store.selectedVoiceID, "Kore")
    XCTAssertFalse(store.isSaving)
    XCTAssertNotNil(store.lastError)
  }

  func testSelectionIsOwnerScopedInLocalCache() async throws {
    let defaults = try makeDefaults()
    let store = try makeStore(preference: "Kore", defaults: defaults)
    await store.refresh()
    XCTAssertEqual(defaults.string(forKey: ScopedDefaultsKey.assistantVoiceID(ownerID: "owner-1")), "Kore")
    XCTAssertNil(defaults.string(forKey: ScopedDefaultsKey.assistantVoiceID(ownerID: "owner-2")))
  }

  func testRemoteSelectionOutsideCatalogResolvesDefault() async throws {
    let store = try makeStore(preference: "GhostVoice")
    await store.refresh()
    XCTAssertEqual(store.selectedVoiceID, "Charon")
    XCTAssertEqual(store.currentVoiceID, "Charon")
  }

  func testCatalogDuplicateIDsAreDedupedForStableListKeys() async throws {
    let store = try makeStore(
      catalog: AssistantVoiceCatalogResponse(
        voices: [
          AssistantVoiceEntry(id: "Charon", name: "Charon"),
          AssistantVoiceEntry(id: "Kore", name: "Kore"),
          AssistantVoiceEntry(id: "Kore", name: "Kore Renamed"),
        ],
        defaultVoiceId: "Charon"))
    await store.refresh()
    XCTAssertEqual(store.catalog.map(\.id), ["Charon", "Kore"])
    XCTAssertEqual(store.catalog.last?.name, "Kore Renamed")
  }

  func testCurrentVoiceIDDropsPreviousOwnerDuringAuthTransition() async throws {
    let store = try makeStore(preference: "Kore")
    await store.refresh()
    XCTAssertEqual(store.currentVoiceID, "Kore")
    await fixture.establish(authOwnerID: nil)
    XCTAssertEqual(store.currentVoiceID, AssistantVoiceStore.defaultVoiceID)
  }

  func testStaleFetchCallbackCannotOverwriteNewerSelection() async throws {
    let gate = AsyncGate()
    let store = AssistantVoiceStore(
      fetchCatalog: { _ in
        await gate.wait()
        return AssistantVoiceStoreTests.catalogResponse
      },
      fetchPreference: { _ in AssistantVoicePreferenceResponse(voiceId: "Kore") },
      savePreference: { voiceID, _ in AssistantVoicePreferenceResponse(voiceId: voiceID) },
      defaults: try makeDefaults(),
      notificationCenter: NotificationCenter(),
      observeOwnerChanges: false)

    let staleRefresh = Task { await store.refresh() }
    await gate.untilEntered()
    await store.save(voiceID: "Puck")
    await gate.open()
    await staleRefresh.value
    XCTAssertEqual(store.selectedVoiceID, "Puck")
  }

  func testSaveDuringRefreshClearsLoadingFlag() async throws {
    let gate = AsyncGate()
    let store = AssistantVoiceStore(
      fetchCatalog: { _ in
        await gate.wait()
        return AssistantVoiceStoreTests.catalogResponse
      },
      fetchPreference: { _ in AssistantVoicePreferenceResponse(voiceId: "Kore") },
      savePreference: { voiceID, _ in AssistantVoicePreferenceResponse(voiceId: voiceID) },
      defaults: try makeDefaults(),
      notificationCenter: NotificationCenter(),
      observeOwnerChanges: false)

    let staleRefresh = Task { await store.refresh() }
    await gate.untilEntered()
    await store.save(voiceID: "Puck")
    XCTAssertFalse(store.isLoading)
    XCTAssertFalse(store.isSaving)
    await gate.open()
    await staleRefresh.value
    XCTAssertFalse(store.isLoading)
  }

  func testRefreshDuringSaveDoesNotSupersedeOrStrandFlags() async throws {
    let gate = AsyncGate()
    let store = AssistantVoiceStore(
      fetchCatalog: { _ in
        await gate.wait()
        return AssistantVoiceStoreTests.catalogResponse
      },
      fetchPreference: { _ in AssistantVoicePreferenceResponse(voiceId: "Kore") },
      savePreference: { voiceID, _ in
        await gate.wait()
        return AssistantVoicePreferenceResponse(voiceId: voiceID)
      },
      defaults: try makeDefaults(),
      notificationCenter: NotificationCenter(),
      observeOwnerChanges: false)

    let pendingSave = Task { await store.save(voiceID: "Puck") }
    await gate.untilEntered()
    await store.refresh()
    XCTAssertTrue(store.isSaving)
    await gate.open()
    _ = await pendingSave.value
    XCTAssertFalse(store.isSaving)
    XCTAssertEqual(store.selectedVoiceID, "Puck")
    await store.save(voiceID: "Kore")
    XCTAssertEqual(store.selectedVoiceID, "Kore")
  }

  func testStaleOwnerCallbackIsDropped() async throws {
    let gate = AsyncGate()
    let store = AssistantVoiceStore(
      fetchCatalog: { _ in
        await gate.wait()
        return AssistantVoiceStoreTests.catalogResponse
      },
      fetchPreference: { _ in AssistantVoicePreferenceResponse(voiceId: "Kore") },
      defaults: try makeDefaults(),
      notificationCenter: NotificationCenter(),
      observeOwnerChanges: false)

    let staleRefresh = Task { await store.refresh() }
    await gate.untilEntered()
    await fixture.establish(authOwnerID: "owner-2")
    await gate.open()
    await staleRefresh.value
    XCTAssertEqual(store.selectedVoiceID, AssistantVoiceStore.defaultVoiceID)
    XCTAssertTrue(store.catalog.isEmpty)
  }

  func testSameUIDSignOutSignInRejectsTheOldAck() async throws {
    let gate = AsyncGate()
    var capturedSnapshots: [RuntimeOwnerAuthorizationSnapshot] = []
    let store = AssistantVoiceStore(
      fetchCatalog: { snapshot in
        capturedSnapshots.append(snapshot)
        await gate.wait()
        return AssistantVoiceStoreTests.catalogResponse
      },
      fetchPreference: { _ in AssistantVoicePreferenceResponse(voiceId: "Kore") },
      defaults: try makeDefaults(),
      notificationCenter: NotificationCenter(),
      observeOwnerChanges: false)

    let staleRefresh = Task { await store.refresh() }
    await gate.untilEntered()
    await fixture.establish(authOwnerID: nil)
    await fixture.establish(authOwnerID: "owner-1")
    await gate.open()
    await staleRefresh.value
    XCTAssertEqual(store.selectedVoiceID, AssistantVoiceStore.defaultVoiceID)
    XCTAssertTrue(store.catalog.isEmpty)
    XCTAssertEqual(capturedSnapshots.map(\.ownerID), ["owner-1"])
  }

  func testEmptyRemotePreferenceResolvesDefault() async throws {
    let store = try makeStore(preference: "")
    await store.refresh()
    XCTAssertEqual(store.selectedVoiceID, "Charon")
  }

  func testSelectionChangePostsHandoffNotificationOnce() async throws {
    let center = NotificationCenter()
    let posts = MutableBox(0)
    let observer = center.addObserver(forName: .assistantVoiceDidChange, object: nil, queue: nil) { _ in
      posts.value += 1
    }
    defer { center.removeObserver(observer) }

    let store = try makeStore(preference: "Kore", notificationCenter: center)
    await store.refresh()
    XCTAssertEqual(posts.value, 1)
    await store.refresh()
    XCTAssertEqual(posts.value, 1)
  }

  func testOwnerChangeResetsAndRefreshesForNewAccount() async throws {
    let defaults = try makeDefaults()
    let currentOwner = MutableBox("owner-1")
    let store = AssistantVoiceStore(
      fetchCatalog: { _ in AssistantVoiceStoreTests.catalogResponse },
      fetchPreference: { _ in
        AssistantVoicePreferenceResponse(voiceId: currentOwner.value == "owner-2" ? "Puck" : "Kore")
      },
      savePreference: { voiceID, _ in AssistantVoicePreferenceResponse(voiceId: voiceID) },
      captureOwner: { RuntimeOwnerIdentity.captureAuthorizationSnapshot() },
      ownerIDProvider: { currentOwner.value },
      defaults: defaults,
      notificationCenter: NotificationCenter(),
      observeOwnerChanges: false)
    await store.refresh()
    XCTAssertEqual(store.selectedVoiceID, "Kore")
    XCTAssertEqual(defaults.string(forKey: ScopedDefaultsKey.assistantVoiceID(ownerID: "owner-1")), "Kore")

    await fixture.establish(authOwnerID: "owner-2")
    currentOwner.value = "owner-2"
    await store.handleRuntimeOwnerDidChange()
    XCTAssertEqual(store.selectedVoiceID, "Puck")
    XCTAssertEqual(defaults.string(forKey: ScopedDefaultsKey.assistantVoiceID(ownerID: "owner-2")), "Puck")
    XCTAssertEqual(defaults.string(forKey: ScopedDefaultsKey.assistantVoiceID(ownerID: "owner-1")), "Kore")
  }
}

private final class MutableBox<Value>: @unchecked Sendable {
  var value: Value
  init(_ value: Value) { self.value = value }
}

private actor AsyncGate {
  private var enteredContinuation: CheckedContinuation<Void, Never>?
  private var openContinuation: CheckedContinuation<Void, Never>?
  private var isOpen = false

  func wait() async {
    if isOpen { return }
    await withCheckedContinuation { continuation in
      openContinuation = continuation
      enteredContinuation?.resume()
      enteredContinuation = nil
    }
  }

  func untilEntered() async {
    if openContinuation != nil { return }
    await withCheckedContinuation { continuation in enteredContinuation = continuation }
  }

  func open() {
    isOpen = true
    openContinuation?.resume()
    openContinuation = nil
  }
}
