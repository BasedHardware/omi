import Flutter
import UIKit
import BackgroundTasks
import app_links
import UserNotifications

/// Flutter owns the scene's implicit engine; process services remain in AppDelegate.
final class OmiSceneDelegate: FlutterSceneDelegate {
    override func scene(_ scene: UIScene, willConnectTo session: UISceneSession,
                        options connectionOptions: UIScene.ConnectionOptions) {
        #if OMI_SIRI_PROBE
        if ProcessInfo.processInfo.arguments.contains("-omi-siri-probe"),
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
        #if OMI_SIRI_PROBE
        let firstLink = Mirror(reflecting: AppLinks.shared).children
            .first(where: { $0.label == "initialLink" })?.value as? String
        NSLog("[SiriSceneProbe] coldURL=%@ coldActivity=%@ appLinksInitial=%@",
              connectionOptions.urlContexts.first?.url.absoluteString ?? "nil",
              connectionOptions.userActivities.first?.webpageURL?.absoluteString ?? "nil",
              firstLink ?? "nil")
        #endif
        super.scene(scene, willConnectTo: session, options: connectionOptions)
        #if OMI_SIRI_PROBE
        NSLog("[SiriSceneProbe] notificationDelegateAfterRegistration=%@",
              String(describing: type(of: UNUserNotificationCenter.current().delegate)))
        #endif
        for context in connectionOptions.urlContexts { forwardOAuthCallback(context.url) }
        let controller = window?.rootViewController as? FlutterViewController
        guard FlutterLaunchEngineGuard.canRegisterPlugins(
            hasFlutterRootViewController: controller != nil, hasEngine: controller?.engine != nil
        ) else {
            #if OMI_SIRI_PROBE
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
        if let url = userActivity.webpageURL { OmiSceneLinkRouter.forward(url) }
        super.scene(scene, continue: userActivity)
    }

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
