#if OMI_SIRI_PROBE
import Foundation
import FirebaseAuth
import FirebaseCore
import AppIntents
import CoreSpotlight
import app_links
import ObjectiveC.runtime

/// Simulator-only, opt-in probe for a Runner launch that has no Dart engine.
/// It accepts only loopback, and uses a fake token against a local stub.
enum SiriDebugProbe {
    /// Compiles from the iOS 16 API floor; a 26-only intent or provider breaks
    /// the opt-in probe build before it can reach the simulator.
    @available(iOS 16.0, *)
    private static func classicShortcutAvailability() -> Bool {
        let shortcuts = OmiAppShortcuts.appShortcuts
        _ = RememberIntent()
        _ = StartOmiListeningIntent()
        _ = StopOmiListeningIntent()
        return shortcuts.count == 3 && !RememberIntent.openAppWhenRun &&
            StartOmiListeningIntent.openAppWhenRun && StopOmiListeningIntent.openAppWhenRun
    }

    @available(iOS 26.0, *)
    static func runIfRequested() {
        guard ProcessInfo.processInfo.arguments.contains("-omi-siri-probe") else { return }
        Task {
            if FirebaseApp.app() == nil { FirebaseApp.configure() }
            NSLog("[SiriProbe] engine=absent firebaseUser=%@", Auth.auth().currentUser?.uid ?? "nil")
            NSLog("[SiriProbe] classicShortcuts=%@", classicShortcutAvailability() ? "PASS" : "FAIL")
            let backgroundModes = Bundle.main.object(forInfoDictionaryKey: "UIBackgroundModes") as? [String] ?? []
            NSLog("[SiriProbe] backgroundAudioBLEModes=%@",
                  backgroundModes.contains("audio") && backgroundModes.contains("bluetooth-central") ? "PASS" : "FAIL")
            let quickActionsClass = NSClassFromString("quick_actions_ios.QuickActionsPlugin")
            let sceneProtocol = NSProtocolFromString("FlutterSceneLifeCycleDelegate")
            NSLog("[SiriProbe] quickActionScenePlugin=%@",
                  quickActionsClass != nil && sceneProtocol != nil &&
                  class_conformsToProtocol(quickActionsClass!, sceneProtocol!) ? "PASS" : "FAIL")
            for (label, rawURL) in [
                ("scheme", "omi-dev://conversation/scene-probe"),
                ("universal", "https://h.omi.me/conversation/scene-probe"),
                ("oauth", "com.googleusercontent.apps.probe:/oauth-callback"),
            ] {
                let url = URL(string: rawURL)!
                if label == "universal" {
                    let activity = NSUserActivity(activityType: NSUserActivityTypeBrowsingWeb)
                    activity.webpageURL = url
                    OmiSceneLinkRouter.forward(urls: [], activities: [activity])
                } else {
                    OmiSceneLinkRouter.forward(urls: [url], activities: [])
                }
                let latest = Mirror(reflecting: AppLinks.shared).children
                    .first(where: { $0.label == "latestLink" })?.value as? String
                NSLog("[SiriProbe] sceneLink_%@=%@", label, latest == rawURL ? "PASS" : "FAIL")
            }
            SiriSession.shared.clear()
            do { _ = try await SiriSession.shared.token(); NSLog("[SiriProbe] signedOut=unexpected-token") }
            catch { NSLog("[SiriProbe] signedOut=auth") }
            guard let raw = ProcessInfo.processInfo.environment["OMI_SIRI_PROBE_URL"],
                  let url = URL(string: raw), url.scheme == "http",
                  ["127.0.0.1", "localhost"].contains(url.host ?? "") else {
                NSLog("[SiriProbe] loopback URL missing; signed-out path only")
                return
            }
            do {
              try await SiriSnapshotStore.shared.bind(uid: "siri-probe")
              let config = SiriSessionConfig(uid: "siri-probe",
                generation: SiriSnapshotStore.shared.generationForOwner("siri-probe") ?? 0,
                baseUrl: raw, profile: "local_dev",
                appVersion: "probe", appBuild: "0", deviceIdHash: "probe-device",
                token: "fake-siri-probe-token",
                tokenExpiresAtMs: Int64(Date().addingTimeInterval(300).timeIntervalSince1970 * 1000))
                try SiriSession.shared.publish(config)
                let resumedGeneration = SiriSnapshotStore.shared.generationForOwner(config.uid)
                NSLog("[SiriProbe] sameOwnerGeneration=%@ changedOwnerGeneration=%@",
                      resumedGeneration != nil ? "PASS" : "FAIL",
                      SiriSnapshotStore.shared.generationForOwner("another-uid") == nil ? "PASS" : "FAIL")
                var intent = RememberIntent()
                intent.content = "probe memory"
                let result = try await intent.perform()
                NSLog("[SiriProbe] rememberPerform=returned result=%@", String(reflecting: result))
                if #available(iOS 27.0, *) {
                    try await SiriSnapshotStore.shared.upsert([
                        SiriMemory(id: "stub-memory-1", content: "probe memory",
                                   createdAtMs: Int64(Date().timeIntervalSince1970 * 1000),
                                   expiresAtMs: nil)
                    ], uid: config.uid)
                    var open = OpenOmiIntent()
                    open.target = ConversationEntity(memoryId: "stub-memory-1", content: "",
                                                     creationDate: Date())
                    _ = try await open.perform()
                    NSLog("[SiriProbe] memoryNoteOpenRoute=%@",
                          SiriSnapshotStore.shared.pendingRoute() ?? "nil")
                    var invalidFolder = OpenOmiFolderIntent()
                    invalidFolder.target = OmiFolderEntity(id: "other", name: "Other")
                    do {
                        _ = try await invalidFolder.perform()
                        NSLog("[SiriProbe] invalidFolderOpen=FAIL success")
                    } catch {
                        NSLog("[SiriProbe] invalidFolderOpen=%@",
                              SiriSnapshotStore.shared.pendingRoute() == nil ? "PASS" : "FAIL routed")
                    }
                    var invalidList = OpenOmiListIntent()
                    invalidList.target = OmiListEntity(id: "other", name: "Other")
                    do {
                        _ = try await invalidList.perform()
                        NSLog("[SiriProbe] invalidListOpen=FAIL success")
                    } catch {
                        NSLog("[SiriProbe] invalidListOpen=%@",
                              SiriSnapshotStore.shared.pendingRoute() == nil ? "PASS" : "FAIL routed")
                    }
                    var staleMemory = OpenOmiMemoryIntent()
                    staleMemory.target = MemoryEntity(id: "missing-memory", content: "Private",
                                                      creationDate: Date())
                    do {
                        _ = try await staleMemory.perform()
                        NSLog("[SiriProbe] staleMemoryOpen=FAIL success")
                    } catch {
                        NSLog("[SiriProbe] staleMemoryOpen=%@",
                              SiriSnapshotStore.shared.pendingRoute() == nil ? "PASS" : "FAIL routed")
                    }
                    SiriBridge.shared.routeDeliveryProbe = { _, completion in completion(true) }
                    SiriBridge.shared.navigate("/task/live-delivery")
                    NSLog("[SiriProbe] liveRouteCleared=%@",
                          SiriSnapshotStore.shared.pendingRoute() == nil ? "PASS" : "FAIL")
                    SiriBridge.shared.routeDeliveryProbe = { _, completion in completion(false) }
                    SiriBridge.shared.navigate("/task/cold-fallback")
                    NSLog("[SiriProbe] failedRoutePreserved=%@",
                          SiriSnapshotStore.shared.pendingRoute() == "/task/cold-fallback" ? "PASS" : "FAIL")
                    SiriBridge.shared.routeDeliveryProbe = nil
                    let row = SiriMemory(id: "probe-memory", content: "probe-memory-native-index-2026", createdAtMs:
                        Int64(Date().timeIntervalSince1970 * 1000), expiresAtMs: nil)
                    try await SiriSnapshotStore.shared.upsert([row], uid: config.uid)
                    let fetched: Int = await withCheckedContinuation { continuation in
                        let query = CSSearchQuery(
                            queryString: "title == \"probe-memory-native-index-2026\"", queryContext: nil)
                        query.completionHandler = { error in
                            NSLog("[SiriProbe] spotlightQueryError=%@", String(describing: error))
                            continuation.resume(returning: query.foundItemCount)
                        }
                        query.start()
                    }
                    NSLog("[SiriProbe] spotlightFetch=%d", fetched)
                    for title in ["Conversations", "Memories", "Omi"] {
                        let count: Int = await withCheckedContinuation { continuation in
                            let query = CSSearchQuery(queryString: "title == \"\(title)\"", queryContext: nil)
                            query.completionHandler = { error in
                                NSLog("[SiriProbe] staticItem=%@ error=%@", title, String(describing: error))
                                continuation.resume(returning: query.foundItemCount)
                            }
                            query.start()
                        }
                        NSLog("[SiriProbe] staticItem=%@ count=%d", title, count)
                    }
                    let expiring = SiriMemory(id: "probe-expiring", content: "probe-expiring-native-index-2026",
                        createdAtMs: Int64(Date().timeIntervalSince1970 * 1000),
                        expiresAtMs: Int64(Date().addingTimeInterval(1.5).timeIntervalSince1970 * 1000))
                    try await SiriSnapshotStore.shared.upsert([expiring], uid: config.uid)
                    try await Task.sleep(nanoseconds: 2_000_000_000)
                    NSLog("[SiriProbe] expiredMemoryQuery=%d expiredNoteQuery=%d",
                          SiriSnapshotStore.shared.memories(ids: [expiring.id]).count,
                          SiriSnapshotStore.shared.memoryNotes(ids: [expiring.id]).count)
                    let expiredIndexCount: Int = await withCheckedContinuation { continuation in
                        let query = CSSearchQuery(
                            queryString: "title == \"probe-expiring-native-index-2026\"", queryContext: nil)
                        query.completionHandler = { error in
                            NSLog("[SiriProbe] expiredSpotlightError=%@", String(describing: error))
                            continuation.resume(returning: query.foundItemCount)
                        }
                        query.start()
                    }
                    NSLog("[SiriProbe] expiredSpotlightCount=%d", expiredIndexCount)
                    let coldExpired = SiriMemory(id: "probe-cold-expired", content: "probe-cold-expired-private-2026",
                        createdAtMs: Int64(Date().timeIntervalSince1970 * 1000),
                        expiresAtMs: Int64(Date().addingTimeInterval(1.5).timeIntervalSince1970 * 1000))
                    try await SiriSnapshotStore.shared.upsert([coldExpired], uid: config.uid)
                    SiriSnapshotStore.shared.simulateTerminatedExpiryTimer()
                    try await Task.sleep(nanoseconds: 2_000_000_000)
                    SiriBridge.shared.retryPendingWipeOnLaunch()
                    try await Task.sleep(nanoseconds: 1_000_000_000)
                    let coldExpiredCount: Int = await withCheckedContinuation { continuation in
                        let query = CSSearchQuery(queryString: "title == \"probe-cold-expired-private-2026\"",
                            queryContext: nil)
                        query.completionHandler = { _ in continuation.resume(returning: query.foundItemCount) }
                        query.start()
                    }
                    NSLog("[SiriProbe] coldLaunchExpiredSpotlight=%@ count=%d",
                          coldExpiredCount == 0 ? "PASS" : "FAIL", coldExpiredCount)
                    var donation = OmiUiActivityIntent()
                    donation.kind = "memory"
                    donation.id = row.id
                    do {
                        _ = try await donation.donate()
                        NSLog("[SiriProbe] donation=ok")
                    } catch {
                        NSLog("[SiriProbe] donation=failed type=%@", String(describing: error))
                    }
                    try await SiriSnapshotStore.shared.delete(type: "memory", ids: [row.id], uid: config.uid)
                    let deletedIndexCount: Int = await withCheckedContinuation { continuation in
                        let query = CSSearchQuery(
                            queryString: "title == \"probe-memory-native-index-2026\"", queryContext: nil)
                        query.completionHandler = { error in
                            NSLog("[SiriProbe] deletedSpotlightError=%@", String(describing: error))
                            continuation.resume(returning: query.foundItemCount)
                        }
                        query.start()
                    }
                    NSLog("[SiriProbe] deletedMemoryQuery=%d deletedSpotlightCount=%d",
                          SiriSnapshotStore.shared.memories(ids: [row.id]).count, deletedIndexCount)
                    let disabledRow = SiriMemory(id: "probe-disabled", content: "probe-disabled-index-2026",
                        createdAtMs: Int64(Date().timeIntervalSince1970 * 1000), expiresAtMs: nil)
                    try await SiriSnapshotStore.shared.upsert([disabledRow], uid: config.uid)
                    try await SiriSnapshotStore.shared.setEnabled(false)
                    do {
                        try await SiriSnapshotStore.shared.delete(type: "memory", ids: [disabledRow.id], uid: config.uid)
                        try await SiriSnapshotStore.shared.setEnabled(true)
                        NSLog("[SiriProbe] disabledDelete=%@",
                              SiriSnapshotStore.shared.memories(ids: [disabledRow.id]).isEmpty ? "PASS" : "FAIL")
                    } catch {
                        NSLog("[SiriProbe] disabledDelete=FAIL error=%@", String(describing: error))
                        try? await SiriSnapshotStore.shared.setEnabled(true)
                    }
                    let disableFailure = SiriMemory(id: "probe-disable-failure",
                        content: "probe-disable-failure-private-2026",
                        createdAtMs: Int64(Date().timeIntervalSince1970 * 1000), expiresAtMs: nil)
                    try await SiriSnapshotStore.shared.upsert([disableFailure], uid: config.uid)
                    SiriSnapshotStore.shared.simulateIndexDeleteFailure = true
                    do { try await SiriSnapshotStore.shared.setEnabled(false) }
                    catch { NSLog("[SiriProbe] injectedDisableFailure=observed") }
                    SiriSnapshotStore.shared.simulateIndexDeleteFailure = false
                    SiriBridge.shared.retryPendingWipeOnLaunch()
                    try await Task.sleep(nanoseconds: 1_000_000_000)
                    let disableFailureCount: Int = await withCheckedContinuation { continuation in
                        let query = CSSearchQuery(queryString: "title == \"probe-disable-failure-private-2026\"",
                            queryContext: nil)
                        query.completionHandler = { _ in continuation.resume(returning: query.foundItemCount) }
                        query.start()
                    }
                    NSLog("[SiriProbe] failedDisableRetriedOnLaunch=%@ count=%d",
                          disableFailureCount == 0 ? "PASS" : "FAIL", disableFailureCount)
                    try await SiriSnapshotStore.shared.setEnabled(true)
                    let removedByServer = SiriMemory(id: "probe-remote-deleted",
                        content: "probe-remote-deleted-private-2026",
                        createdAtMs: Int64(Date().timeIntervalSince1970 * 1000), expiresAtMs: nil)
                    try await SiriSnapshotStore.shared.upsert([removedByServer], uid: config.uid)
                    try await SiriSnapshotStore.shared.reconcile([SiriMemory](), uid: config.uid)
                    NSLog("[SiriProbe] authoritativeMemoryRemoval=%@",
                          SiriSnapshotStore.shared.memories(ids: [removedByServer.id]).isEmpty ? "PASS" : "FAIL")
                    let nowMs = Int64(Date().timeIntervalSince1970 * 1000)
                    let staleNew = SiriConversation(id: "probe-remote-deleted-conversation", title: "private",
                        summary: "private summary", startedAtMs: nowMs, updatedAtMs: nowMs)
                    let outsidePage = SiriConversation(id: "probe-outside-page", title: "older",
                        summary: "older summary", startedAtMs: nowMs - 100 * 86_400_000, updatedAtMs: nowMs)
                    try await SiriSnapshotStore.shared.upsert([staleNew, outsidePage], uid: config.uid)
                    try await SiriSnapshotStore.shared.reconcile([SiriConversation](), uid: config.uid,
                        coveredAfterMs: nowMs - 50 * 86_400_000)
                    NSLog("[SiriProbe] authoritativePageWindow=%@",
                          SiriSnapshotStore.shared.conversations(ids: [staleNew.id]).isEmpty &&
                          !SiriSnapshotStore.shared.conversations(ids: [outsidePage.id]).isEmpty ? "PASS" : "FAIL")
                    let activeTask = SiriTask(id: "probe-remote-deleted-task", title: "private active task",
                        completed: false, createdAtMs: nowMs, dueAtMs: nil, completedAtMs: nil)
                    let completedTask = SiriTask(id: "probe-preserved-completed-task", title: "recent done task",
                        completed: true, createdAtMs: nowMs, dueAtMs: nil, completedAtMs: nowMs)
                    try await SiriSnapshotStore.shared.upsert([activeTask, completedTask], uid: config.uid)
                    try await SiriSnapshotStore.shared.reconcile([SiriTask](), uid: config.uid,
                        includeCompleted: false)
                    NSLog("[SiriProbe] authoritativeActiveTasks=%@",
                          SiriSnapshotStore.shared.tasks(ids: [activeTask.id]).isEmpty &&
                          !SiriSnapshotStore.shared.tasks(ids: [completedTask.id]).isEmpty ? "PASS" : "FAIL")
                    let oldConversation = SiriConversation(id: "probe-too-old-conversation", title: "old",
                        summary: "old summary", startedAtMs: nowMs - 181 * 86_400_000, updatedAtMs: nowMs)
                    let oldTask = SiriTask(id: "probe-too-old-completion", title: "old task", completed: true,
                        createdAtMs: nowMs - 45 * 86_400_000, dueAtMs: nil,
                        completedAtMs: nowMs - 31 * 86_400_000)
                    try await SiriSnapshotStore.shared.upsert([oldConversation], uid: config.uid)
                    try await SiriSnapshotStore.shared.upsert([oldTask], uid: config.uid)
                    try await SiriSnapshotStore.shared.rebuildIndex()
                    NSLog("[SiriProbe] reindexScope=%@",
                          SiriSnapshotStore.shared.conversations(ids: [oldConversation.id]).isEmpty &&
                          SiriSnapshotStore.shared.tasks(ids: [oldTask.id]).isEmpty ? "PASS" : "FAIL")
                    NSLog("[SiriProbe] deviceListeningDialog=%@",
                          SiriListeningFailure(pigeonCode: "device_already_listening").spokenDialog ==
                          "Omi is already listening from your device." ? "PASS" : "FAIL")
                    let defaults = UserDefaults(suiteName: "group.com.friend-app-with-wearable.ios12")!
                    defaults.removeObject(forKey: "siri.snapshot.owner")
                    NSLog("[SiriProbe] ownerMissingVisible=%d", SiriSnapshotStore.shared.memories(ids: nil).count)
                    try await SiriSnapshotStore.shared.bind(uid: "siri-probe-next")
                    let next = SiriSessionConfig(uid: "siri-probe-next",
                        generation: SiriSnapshotStore.shared.generationForOwner("siri-probe-next") ?? 0,
                        baseUrl: raw, profile: "local_dev",
                        appVersion: "probe", appBuild: "0", deviceIdHash: "probe-device",
                        token: "fake-siri-probe-token",
                        tokenExpiresAtMs: Int64(Date().addingTimeInterval(300).timeIntervalSince1970 * 1000))
                    try SiriSession.shared.publish(next)
                    do {
                        try await SiriSnapshotStore.shared.upsert([row], uid: config.uid)
                        NSLog("[SiriProbe] staleUidWrite=unexpected-accepted")
                    } catch SiriSession.Failure.auth {
                        NSLog("[SiriProbe] staleUidWrite=rejected")
                    }
                    let sessionConfig = URLSessionConfiguration.ephemeral
                    sessionConfig.protocolClasses = [SiriProbeURLProtocol.self]
                    OmiNativeAPI.testSession = URLSession(configuration: sessionConfig)
                    let switched = SiriSessionConfig(uid: "siri-probe-switched", generation: 0,
                        baseUrl: raw, profile: "local_dev", appVersion: "probe", appBuild: "0",
                        deviceIdHash: "probe-device", token: "switched-account-token",
                        tokenExpiresAtMs: Int64(Date().addingTimeInterval(300).timeIntervalSince1970 * 1000))
                    let requestsBeforeSwitch = SiriProbeURLProtocol.requestCount
                    SiriSession.shared.beforeTokenLookup = { try? SiriSession.shared.publish(switched) }
                    do {
                        _ = try await OmiNativeAPI().request(method: "POST", path: "/v3/memories", body: [:])
                        NSLog("[SiriProbe] switchedOwnerRequest=FAIL success")
                    } catch SiriSession.Failure.auth {
                        NSLog("[SiriProbe] switchedOwnerRequest=%@",
                              SiriProbeURLProtocol.requestCount == requestsBeforeSwitch ? "PASS" : "FAIL sent")
                    } catch {
                        NSLog("[SiriProbe] switchedOwnerRequest=FAIL error=%@", String(describing: error))
                    }
                    SiriSession.shared.beforeTokenLookup = nil
                    try SiriSession.shared.publish(next)
                    SiriProbeURLProtocol.status = 200
                    let beforeUnsupported = SiriProbeURLProtocol.requestCount
                    var wrongFolder = OmiCreateNoteIntent()
                    wrongFolder.name = "private note"
                    wrongFolder.folder = .conversations
                    do {
                        _ = try await wrongFolder.perform()
                        NSLog("[SiriProbe] unsupportedNoteFolder=FAIL success")
                    } catch {
                        NSLog("[SiriProbe] unsupportedNoteFolder=%@ spoken=%@",
                              SiriProbeURLProtocol.requestCount == beforeUnsupported &&
                              (error as? LocalizedError)?.errorDescription ==
                              "Omi can only save note text to Memories." ? "PASS" : "FAIL",
                              (error as? LocalizedError)?.errorDescription ?? "nil")
                    }
                    var extraTask = CreateOmiTaskIntent()
                    extraTask.title = "private task"
                    extraTask.note = AttributedString("Don't drop this")
                    do {
                        _ = try await extraTask.perform()
                        NSLog("[SiriProbe] unsupportedTaskFields=FAIL success")
                    } catch {
                        NSLog("[SiriProbe] unsupportedTaskFields=%@ spoken=%@",
                              SiriProbeURLProtocol.requestCount == beforeUnsupported &&
                              (error as? LocalizedError)?.errorDescription ==
                              "Omi can only create tasks with a title, due date, and the Omi list." ? "PASS" : "FAIL",
                              (error as? LocalizedError)?.errorDescription ?? "nil")
                    }
                    for status in [401, 402, 429, 500, 200, 0] {
                        SiriProbeURLProtocol.status = status
                        do {
                            let failureResult = try await intent.perform()
                            let recorded = SiriTelemetry.take().last {
                                $0.kind == "intent" && $0.intent == "remember"
                            }?.outcome ?? "missing"
                            NSLog("[SiriProbe] httpStatus=%d result=%@", status,
                                  String(reflecting: failureResult))
                            NSLog("[SiriProbe] httpStatus=%d outcome=%@", status, recorded)
                        } catch {
                            NSLog("[SiriProbe] httpStatus=%d unexpectedThrow=%@", status,
                                  String(describing: error))
                        }
                        var note = OmiCreateNoteIntent()
                        note.name = "probe note"
                        do {
                            _ = try await note.perform()
                            NSLog("[SiriProbe] noteStatus=%d unexpectedSuccess", status)
                        } catch {
                            NSLog("[SiriProbe] noteStatus=%d spoken=%@", status,
                                  (error as? LocalizedError)?.errorDescription ?? "nil")
                        }
                        var create = CreateOmiTaskIntent()
                        create.title = "probe task"
                        do {
                            _ = try await create.perform()
                            NSLog("[SiriProbe] createTaskStatus=%d unexpectedSuccess", status)
                        } catch {
                            NSLog("[SiriProbe] createTaskStatus=%d spoken=%@", status,
                                  (error as? LocalizedError)?.errorDescription ?? "nil")
                        }
                        let task = TaskEntity(id: "probe-task", title: "probe task", isCompleted: false,
                                              creationDate: Date(), dueDate: nil, completionDate: nil)
                        var complete = CompleteOmiTaskIntent()
                        complete.target = task
                        complete.isCompleted = true
                        do {
                            _ = try await complete.perform()
                            NSLog("[SiriProbe] completeTaskStatus=%d unexpectedSuccess", status)
                        } catch {
                            NSLog("[SiriProbe] completeTaskStatus=%d spoken=%@", status,
                                  (error as? LocalizedError)?.errorDescription ?? "nil")
                        }
                    }
                    OmiNativeAPI.testSession = nil
                    SiriSnapshotStore.shared.simulateIndexDeleteFailure = true
                    do { try await SiriSnapshotStore.shared.wipe() }
                    catch { NSLog("[SiriProbe] injectedWipeFailure=observed") }
                    let pending = defaults.stringArray(forKey: "siri.pending.wipe.owners") ?? []
                    NSLog("[SiriProbe] failedWipeOwnerRecoverable=%@",
                          pending.contains(next.uid) ? "PASS" : "FAIL")
                    SiriSnapshotStore.shared.simulateIndexDeleteFailure = false
                    if ProcessInfo.processInfo.arguments.contains("-omi-siri-probe-leave-pending-wipe") {
                        NSLog("[SiriProbe] leavingPendingWipeForRelaunch=YES")
                        return
                    }
                    let staleAccepted = await withCheckedContinuation { (continuation: CheckedContinuation<Bool, Never>) in
                        SiriBridge.shared.wipe { _ in
                            SiriBridge.shared.publishSessionConfig(config: next) { result in
                                if case .success = result { continuation.resume(returning: true) }
                                else { continuation.resume(returning: false) }
                            }
                        }
                    }
                    NSLog("[SiriProbe] stalePublishAfterWipe=%@", staleAccepted ? "FAIL" : "PASS")
                }
            } catch {
                NSLog("[SiriProbe] request=failed type=%@", String(describing: error))
            }
            SiriSession.shared.clear()
            try? await SiriSnapshotStore.shared.wipe()
        }
    }
}

/// URLProtocol is local to the debug probe and never appears in release builds.
private final class SiriProbeURLProtocol: URLProtocol {
    static var status = 500
    static var requestCount = 0
    override class func canInit(with request: URLRequest) -> Bool { true }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }
    override func startLoading() {
        Self.requestCount += 1
        if Self.status == 0 {
            client?.urlProtocol(self, didFailWithError: URLError(.notConnectedToInternet))
            return
        }
        let response = HTTPURLResponse(url: request.url!, statusCode: Self.status,
                                       httpVersion: "HTTP/1.1", headerFields: ["Content-Type": "application/json"])!
        client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
        client?.urlProtocol(self, didLoad: Self.status == 200 ? Data("[]".utf8) : Data("{}".utf8))
        client?.urlProtocolDidFinishLoading(self)
    }
    override func stopLoading() {}
}
#endif
