import Flutter
import UIKit
import BackgroundTasks
import app_links
import UserNotifications
#if compiler(>=6.4)
import CoreSpotlight
import AppIntents
#endif

/// Flutter owns the scene's implicit engine; process services remain in AppDelegate.
final class OmiSceneDelegate: FlutterSceneDelegate {
    override func scene(_ scene: UIScene, willConnectTo session: UISceneSession,
                        options connectionOptions: UIScene.ConnectionOptions) {
        #if OMI_SIRI_PROBE && compiler(>=6.4)
        for activity in connectionOptions.userActivities { logSpotlightProbe(activity, phase: "cold") }
        #endif
        #if compiler(>=6.4)
        if #available(iOS 27.0, *) {
            connectionOptions.userActivities.forEach(OmiSpotlightActivityRoute.handle)
        }
        #endif
        #if OMI_SIRI_PROBE && compiler(>=6.4)
        if SiriDebugProbe.spotlightModeActive ||
           ProcessInfo.processInfo.arguments.contains(where: { $0.hasPrefix("-omi-siri-probe") }),
           let windowScene = scene as? UIWindowScene, #available(iOS 26.0, *) {
            window = UIWindow(windowScene: windowScene)
            SiriDebugProbe.runIfRequested() // No Flutter scene or engine has been created.
            (UIApplication.shared.delegate as? AppDelegate)?.showFlutterEngineUnavailableNotice(in: window)
            return
        }
        #endif
        OmiSceneLinkRouter.forward(
            urls: connectionOptions.urlContexts.map(\.url),
            activities: Array(connectionOptions.userActivities))
        #if OMI_SIRI_PROBE && compiler(>=6.4)
        let firstLink = Mirror(reflecting: AppLinks.shared).children
            .first(where: { $0.label == "initialLink" })?.value as? String
        NSLog("[SiriSceneProbe] coldURL=%@ coldActivity=%@ appLinksInitial=%@",
              connectionOptions.urlContexts.first?.url.absoluteString ?? "nil",
              connectionOptions.userActivities.first?.webpageURL?.absoluteString ?? "nil",
              firstLink ?? "nil")
        #endif
        super.scene(scene, willConnectTo: session, options: connectionOptions)
        #if OMI_SIRI_PROBE && compiler(>=6.4)
        NSLog("[SiriSceneProbe] notificationDelegateAfterRegistration=%@",
              String(describing: type(of: UNUserNotificationCenter.current().delegate)))
        #endif
        for context in connectionOptions.urlContexts { forwardOAuthCallback(context.url) }
        let controller = window?.rootViewController as? FlutterViewController
        guard FlutterLaunchEngineGuard.canRegisterPlugins(
            hasFlutterRootViewController: controller != nil, hasEngine: controller?.engine != nil
        ) else {
            #if OMI_SIRI_PROBE && compiler(>=6.4)
            if #available(iOS 26.0, *) { SiriDebugProbe.runIfRequested() }
            #endif
            (UIApplication.shared.delegate as? AppDelegate)?.showFlutterEngineUnavailableNotice(in: window)
            return
        }
    }

    override func sceneDidEnterBackground(_ scene: UIScene) {
        super.sceneDidEnterBackground(scene)
        OmiBleManager.shared.markBackgroundTelemetryStart()
        BGTaskScheduler.shared.cancel(taskRequestWithIdentifier: "com.pravera.flutter_foreground_task.refresh")
    }

    override func sceneDidBecomeActive(_ scene: UIScene) {
        OmiBleManager.shared.markBackgroundTelemetryEnd()
        super.sceneDidBecomeActive(scene)
    }

    override func sceneWillEnterForeground(_ scene: UIScene) {
        super.sceneWillEnterForeground(scene)
        OmiBleManager.shared.reconnectStalePeripherals()
    }

    override func scene(_ scene: UIScene, openURLContexts URLContexts: Set<UIOpenURLContext>) {
        for context in URLContexts {
            if (UIApplication.shared.delegate as? AppDelegate)?.rayBanMetaHostApi?.handleUrl(context.url) == true {
                continue
            }
            OmiSceneLinkRouter.forward(context.url)
            forwardOAuthCallback(context.url)
        }
        super.scene(scene, openURLContexts: URLContexts)
    }

    override func scene(_ scene: UIScene, continue userActivity: NSUserActivity) {
        #if OMI_SIRI_PROBE && compiler(>=6.4)
        logSpotlightProbe(userActivity, phase: "warm")
        #endif
        #if compiler(>=6.4)
        if #available(iOS 27.0, *) { OmiSpotlightActivityRoute.handle(userActivity) }
        #endif
        if let url = userActivity.webpageURL { OmiSceneLinkRouter.forward(url) }
        super.scene(scene, continue: userActivity)
    }

    #if OMI_SIRI_PROBE && compiler(>=6.4)
    private func logSpotlightProbe(_ activity: NSUserActivity, phase: String) {
        let entityType: String
        let entityID: String
        if #available(iOS 18.2, *) {
            let entity = activity.appEntityIdentifier
            entityType = entity.map { String(describing: $0.entityType) } ?? "nil"
            entityID = entity?.identifier ?? "nil"
        } else {
            entityType = "unavailable"
            entityID = "unavailable"
        }
        NSLog("[SiriSceneProbe] phase=%@ type=%@ itemID=%@ entityType=%@ entityID=%@ userInfo=%@",
              phase, activity.activityType,
              activity.userInfo?[CSSearchableItemActivityIdentifier] as? String ?? "nil",
              entityType, entityID, String(describing: activity.userInfo ?? [:]))
    }
    #endif

    private func forwardOAuthCallback(_ url: URL) {
        guard url.scheme?.hasPrefix("com.googleusercontent.apps.") == true,
              let app = UIApplication.shared.delegate as? AppDelegate else { return }
        _ = app.application(UIApplication.shared, open: url, options: [:])
    }
}

/// Shared by cold and warm scene callbacks; the simulator probe exercises it
/// without depending on a live OAuth account or a Flutter engine.
enum OmiSceneLinkRouter {
    static func forward(_ url: URL) { AppLinks.shared.handleLink(url: url) }
    static func forward(urls: [URL], activities: [NSUserActivity]) {
        urls.forEach(forward)
        activities.compactMap(\.webpageURL).forEach(forward)
    }
}

#if compiler(>=6.4)
/// The Spotlight activity contains an App Entity identifier, not an Omi URL.
/// Only an entity still present in the current owner's snapshot may navigate.
@available(iOS 27.0, *)
enum OmiSpotlightActivityRoute {
    struct Target: Equatable {
        let kinds: [String]
        let id: String
    }

    static func target(_ activity: NSUserActivity) -> Target? {
        guard activity.activityType == CSSearchableItemActionType else { return nil }
        let raw = activity.userInfo?[CSSearchableItemActivityIdentifier] as? String
        let entity = activity.appEntityIdentifier ?? raw.flatMap(EntityIdentifier.init(activityIdentifier:))
        if let entity, !entity.identifier.isEmpty {
            switch ObjectIdentifier(entity.entityType) {
            case ObjectIdentifier(ConversationEntity.self):
                if let explicit = urlTarget(raw), explicit.id == entity.identifier,
                   explicit.kinds.first == "conversation" || explicit.kinds.first == "memory" {
                    return explicit
                }
                return Target(kinds: ["conversation", "memory"], id: entity.identifier)
            case ObjectIdentifier(MemoryEntity.self):
                return Target(kinds: ["memory"], id: entity.identifier)
            case ObjectIdentifier(TaskEntity.self):
                return Target(kinds: ["task"], id: entity.identifier)
            default: break
            }
        }
        // Old iOS indexes included a URL as relatedUniqueIdentifier. Accept
        // one if Spotlight supplies it as its activity identifier, but never
        // trust it without the same current-owner snapshot check below.
        return urlTarget(raw)
    }

    private static func urlTarget(_ raw: String?) -> Target? {
        guard let raw, let url = URLComponents(string: raw), url.scheme == "omi",
              let kind = url.host, ["conversation", "memory", "task"].contains(kind),
              let id = url.path.split(separator: "/").first.map(String.init),
              url.path.split(separator: "/").count == 1, !id.isEmpty else { return nil }
        return Target(kinds: [kind], id: id)
    }

    static func handle(_ activity: NSUserActivity) {
        guard activity.activityType == CSSearchableItemActionType else { return }
        let started = Date()
        guard let target = target(activity) else {
            SiriTelemetry.intent("open", outcome: "server", started: started, entryPath: "user_activity")
            return
        }
        let matches = target.kinds.filter {
            SiriSnapshotStore.shared.containsCurrentEntity(type: $0, id: target.id)
        }
        guard matches.count == 1, let kind = matches.first else {
            SiriTelemetry.intent("open", outcome: "auth", started: started, entryPath: "user_activity")
            return
        }
        _ = SiriBridge.shared.navigate(SiriBridge.entityRoute(kind: kind, id: target.id),
                                       entryPath: "user_activity")
    }
}
#endif
