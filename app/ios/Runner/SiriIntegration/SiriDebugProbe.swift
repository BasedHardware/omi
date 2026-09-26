#if OMI_SIRI_PROBE
import Foundation
import FirebaseAuth
import FirebaseCore
import AppIntents
import CoreSpotlight

/// Simulator-only, opt-in probe for a Runner launch that has no Dart engine.
/// It accepts only loopback, and uses a fake token against a local stub.
enum SiriDebugProbe {
    @available(iOS 26.0, *)
    static func runIfRequested() {
        guard ProcessInfo.processInfo.arguments.contains("-omi-siri-probe") else { return }
        Task {
            if FirebaseApp.app() == nil { FirebaseApp.configure() }
            NSLog("[SiriProbe] engine=absent firebaseUser=%@", Auth.auth().currentUser?.uid ?? "nil")
            SiriSession.shared.clear()
            do { _ = try await SiriSession.shared.token(); NSLog("[SiriProbe] signedOut=unexpected-token") }
            catch { NSLog("[SiriProbe] signedOut=auth") }
            guard let raw = ProcessInfo.processInfo.environment["OMI_SIRI_PROBE_URL"],
                  let url = URL(string: raw), url.scheme == "http",
                  ["127.0.0.1", "localhost"].contains(url.host ?? "") else {
                NSLog("[SiriProbe] loopback URL missing; signed-out path only")
                return
            }
            let config = SiriSessionConfig(uid: "siri-probe", baseUrl: raw, profile: "local_dev",
                appVersion: "probe", appBuild: "0", deviceIdHash: "probe-device",
                token: "fake-siri-probe-token",
                tokenExpiresAtMs: Int64(Date().addingTimeInterval(300).timeIntervalSince1970 * 1000))
            do {
                try await SiriSnapshotStore.shared.bind(uid: config.uid)
                try SiriSession.shared.publish(config)
                var intent = RememberIntent()
                intent.content = "probe memory"
                let result = try await intent.perform()
                NSLog("[SiriProbe] rememberPerform=returned result=%@", String(reflecting: result))
                if #available(iOS 27.0, *) {
                    var open = OpenOmiIntent()
                    open.target = ConversationEntity(memoryId: "stub-memory-1", content: "",
                                                     creationDate: Date())
                    _ = try await open.perform()
                    NSLog("[SiriProbe] memoryNoteOpenRoute=%@",
                          SiriSnapshotStore.shared.pendingRoute() ?? "nil")
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
                    let defaults = UserDefaults(suiteName: "group.com.friend-app-with-wearable.ios12")!
                    defaults.removeObject(forKey: "siri.snapshot.owner")
                    NSLog("[SiriProbe] ownerMissingVisible=%d", SiriSnapshotStore.shared.memories(ids: nil).count)
                    try await SiriSnapshotStore.shared.bind(uid: "siri-probe-next")
                    let next = SiriSessionConfig(uid: "siri-probe-next", baseUrl: raw, profile: "local_dev",
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
    override class func canInit(with request: URLRequest) -> Bool { true }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }
    override func startLoading() {
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
