import Flutter
import UIKit
import BackgroundTasks

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
        super.scene(scene, willConnectTo: session, options: connectionOptions)
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
        if let app = UIApplication.shared.delegate as? AppDelegate {
            for context in URLContexts where app.rayBanMetaHostApi?.handleUrl(context.url) == true { return }
        }
        super.scene(scene, openURLContexts: URLContexts)
    }
}
