import UIKit
import Flutter
import UserNotifications
import app_links
import WatchConnectivity
import AVFoundation
import Speech
import WidgetKit
import BackgroundTasks

extension FlutterError: Error {}

// MARK: - Quick Actions Icon Patcher

/// Observes UIApplication.shortcutItems via KVO and replaces template-image icons
/// (set by the quick_actions Flutter plugin) with native SF Symbol icons.
final class QuickActionsIconPatcher: NSObject {

    static let shared = QuickActionsIconPatcher()
    private var isObserving = false

    private let symbolMap: [String: String] = [
        "add_task":        "checkmark.circle.fill",
        "ask_omi":         "message.fill",
        "voice_mode":      "waveform",
        "mute":            "mic.slash.fill",
        "unmute":          "mic.fill",
        "connect_device":  "cable.connector.horizontal",
        "device_settings": "slider.horizontal.3",
    ]

    func startObserving() {
        guard !isObserving else { return }
        UIApplication.shared.addObserver(
            self,
            forKeyPath: #keyPath(UIApplication.shortcutItems),
            options: [.new],
            context: nil
        )
        isObserving = true
    }

    func stopObserving() {
        guard isObserving else { return }
        UIApplication.shared.removeObserver(self, forKeyPath: #keyPath(UIApplication.shortcutItems))
        isObserving = false
    }

    override func observeValue(
        forKeyPath keyPath: String?,
        of object: Any?,
        change: [NSKeyValueChangeKey: Any]?,
        context: UnsafeMutableRawPointer?
    ) {
        guard keyPath == #keyPath(UIApplication.shortcutItems) else { return }
        DispatchQueue.main.async { self.patchIcons() }
    }

    private func patchIcons() {
        guard let items = UIApplication.shared.shortcutItems, !items.isEmpty else { return }

        let patched = items.map { item -> UIApplicationShortcutItem in
            guard let symbol = symbolMap[item.type] else { return item }
            let icon = UIApplicationShortcutIcon(systemImageName: symbol)
            return UIApplicationShortcutItem(
                type: item.type,
                localizedTitle: item.localizedTitle,
                localizedSubtitle: item.localizedSubtitle,
                icon: icon,
                userInfo: item.userInfo
            )
        }

        // Stop observing before setting to avoid infinite KVO loop.
        stopObserving()
        UIApplication.shared.shortcutItems = patched
        startObserving()
    }

    deinit { stopObserving() }
}

@main
@objc class AppDelegate: FlutterAppDelegate {
  private static let unusedForegroundTaskRefreshIdentifier = "com.pravera.flutter_foreground_task.refresh"
  private var methodChannel: FlutterMethodChannel?
  private var appleRemindersChannel: FlutterMethodChannel?
  private var appleHealthChannel: FlutterMethodChannel?
  private let appleRemindersService = AppleRemindersService()
  private let appleHealthService = AppleHealthService()
  private var phoneMicController: PhoneMicController?
  private var notificationTitleOnKill: String?
  private var notificationBodyOnKill: String?

  var session: WCSession?
    var flutterWatchAPI: WatchRecorderFlutterAPI?
    var rayBanMetaHostApi: RayBanMetaHostApiImpl?
  private var audioChunks: [Int: (Data, Double)] = [:] // (audioData, sampleRate)
  private var nextExpectedChunkIndex: Int = 0
  private var isRecordingActive: Bool = false // Track recording state to handle app restarts

  override func application(
    _ application: UIApplication,
    didFinishLaunchingWithOptions launchOptions: [UIApplication.LaunchOptionsKey: Any]?
  ) -> Bool {
    // A debug build opened without Flutter tooling (Home Screen tap, or an iOS
    // background relaunch after `flutter run` disconnected) has no engine: iOS
    // refuses the JIT Dart VM, FlutterEngine init returns nil, and every
    // registrar below would be nil. Registering plugins anyway crashed in
    // SwiftAwesomeNotificationsPlugin.register; explain instead.
    let flutterController = window?.rootViewController as? FlutterViewController
    guard
      FlutterLaunchEngineGuard.canRegisterPlugins(
        hasFlutterRootViewController: flutterController != nil,
        hasEngine: flutterController?.engine != nil
      ), let controller = flutterController
    else {
      showFlutterEngineUnavailableNotice()
      return super.application(application, didFinishLaunchingWithOptions: launchOptions)
    }
    GeneratedPluginRegistrant.register(with: self)
    QuickActionsIconPatcher.shared.startObserving()
      
      
      if WCSession.isSupported() {
          session = WCSession.default
          session?.delegate = self
          session?.activate();

            flutterWatchAPI = WatchRecorderFlutterAPI(binaryMessenger: controller.binaryMessenger)
            let api: WatchRecorderHostAPI = RecorderHostApiImpl(session: session!, flutterWatchAPI: flutterWatchAPI)

            WatchRecorderHostAPISetup.setUp(binaryMessenger: controller.binaryMessenger, api: api)
      }

      // Native BLE module — register Pigeon APIs
      NSLog("[OmiBle] Registering BLE Pigeon APIs")
      do {
          let messenger = controller.binaryMessenger
          let bleFlutterApi = BleFlutterApi(binaryMessenger: messenger)
          OmiBleManager.shared.setFlutterApi(bleFlutterApi)
          let bleHostApi = BleHostApiImpl(bleManager: OmiBleManager.shared)
          BleHostApiSetup.setUp(binaryMessenger: messenger, api: bleHostApi)
          NSLog("[OmiBle] BLE Pigeon APIs registered successfully")
      }

      // Ray-Ban Meta (Meta Wearables DAT camera + Bluetooth HFP mic) — Pigeon APIs.
      // Registered unconditionally; the impl reports availability mode based on
      // whether the DAT SDK is linked into this build.
      do {
          let messenger = controller.binaryMessenger
          let rayBanFlutterApi = RayBanMetaFlutterAPI(binaryMessenger: messenger)
          let rayBanApi = RayBanMetaHostApiImpl(flutterAPI: rayBanFlutterApi)
          rayBanMetaHostApi = rayBanApi
          RayBanMetaHostAPISetup.setUp(binaryMessenger: messenger, api: rayBanApi)
      }

      // Native phone-mic capture (conversation recording) — Pigeon APIs.
      // Self-healing AVAudioEngine capture; interruption/route recovery is
      // handled natively, Dart only mirrors the state.
      do {
          let messenger = controller.binaryMessenger
          let phoneMicFlutterApi = PhoneMicFlutterApi(binaryMessenger: messenger)
          let micController = PhoneMicController(flutterApi: phoneMicFlutterApi)
          phoneMicController = micController
          PhoneMicHostApiSetup.setUp(binaryMessenger: messenger, api: PhoneMicHostApiImpl(controller: micController))
      }

      // Retrieve the link from parameters
    if let url = AppLinks.shared.getLink(launchOptions: launchOptions) {
      // We have a link, propagate it to your Flutter app or not
      AppLinks.shared.handleLink(url: url)
      return true // Returning true will stop the propagation to other packages
    }
    //Creates a method channel to handle notifications on kill
    methodChannel = FlutterMethodChannel(name: "com.friend.ios/notifyOnKill", binaryMessenger: controller.binaryMessenger)
    methodChannel?.setMethodCallHandler { [weak self] (call, result) in
      self?.handleMethodCall(call, result: result)
    }
    
    // Create Apple Reminders method channel
    appleRemindersChannel = FlutterMethodChannel(name: "com.omi.apple_reminders", binaryMessenger: controller.binaryMessenger)
    appleRemindersChannel?.setMethodCallHandler { [weak self] (call, result) in
      self?.handleAppleRemindersCall(call, result: result)
    }

    // Create Apple Health method channel
    appleHealthChannel = FlutterMethodChannel(name: "com.omi.apple_health", binaryMessenger: controller.binaryMessenger)
    appleHealthChannel?.setMethodCallHandler { [weak self] (call, result) in
      self?.handleAppleHealthCall(call, result: result)
    }

    // Create Speech Recognition method channel
    let speechChannel = FlutterMethodChannel(name: "com.omi.ios/speech", binaryMessenger: controller.binaryMessenger)
    let speechHandler = SpeechRecognitionHandler()
    speechChannel.setMethodCallHandler { (call, result) in
        speechHandler.handle(call, result: result)
    }

    // TestFlight environment detection
    let envChannel = FlutterMethodChannel(name: "com.omi/environment", binaryMessenger: controller.binaryMessenger)
    envChannel.setMethodCallHandler { (call, result) in
        if call.method == "isTestFlight" {
            let isTestFlight = Bundle.main.appStoreReceiptURL?.lastPathComponent == "sandboxReceipt"
            result(isTestFlight)
        } else {
            result(FlutterMethodNotImplemented)
        }
    }

    // Audio session configuration for Bluetooth microphone support
    let audioSessionChannel = FlutterMethodChannel(name: "com.omi.ios/audioSession", binaryMessenger: controller.binaryMessenger)
    audioSessionChannel.setMethodCallHandler { (call, result) in
        if call.method == "configureForBluetooth" {
            let audioSession = AVAudioSession.sharedInstance()
            do {
                try audioSession.setCategory(
                    .playAndRecord,
                    mode: .default,
                    options: [.allowBluetooth, .allowBluetoothA2DP, .defaultToSpeaker]
                )
                try audioSession.setActive(true)
                result(true)
            } catch {
                result(FlutterError(code: "AUDIO_SESSION_ERROR", message: error.localizedDescription, details: nil))
            }
        } else {
            result(FlutterMethodNotImplemented)
        }
    }

    // Battery widget channel — writes Omi device battery to the shared App Group
    // so the WidgetKit extension can read it.
    let batteryWidgetChannel = FlutterMethodChannel(name: "com.omi.battery_widget", binaryMessenger: controller.binaryMessenger)
    batteryWidgetChannel.setMethodCallHandler { (call, result) in
      let defaults = UserDefaults(suiteName: "group.com.friend-app-with-wearable.ios12")
      guard let args = call.arguments as? [String: Any] else {
        result(FlutterMethodNotImplemented)
        return
      }
      switch call.method {
      case "updateBatteryInfo":
        defaults?.set(args["deviceName"] as? String ?? "Omi", forKey: "widget_device_name")
        defaults?.set(args["batteryLevel"] as? Int ?? -1, forKey: "widget_battery_level")
        defaults?.set(args["deviceType"] as? String ?? "omi", forKey: "widget_device_type")
        defaults?.set(args["isConnected"] as? Bool ?? false, forKey: "widget_is_connected")
        defaults?.set(Date(), forKey: "widget_last_updated")
        // NOTE: isMuted is intentionally NOT written here — only updateMuteState controls it
        if #available(iOS 14.0, *) {
          WidgetCenter.shared.reloadTimelines(ofKind: "OmiBatteryWidget")
        }
      case "updateMuteState":
        let isMuted = (args["isMuted"] as? Bool) ?? (args["isMuted"] as? NSNumber)?.boolValue ?? false
        defaults?.set(isMuted, forKey: "widget_is_muted")
        if #available(iOS 14.0, *) {
          WidgetCenter.shared.reloadAllTimelines()
        }
      default:
        result(FlutterMethodNotImplemented)
        return
      }
      result(nil)
    }

    // Register Phone Calls plugin
    OmiPhoneCallsPlugin.register(with: self.registrar(forPlugin: "OmiPhoneCallsPlugin")!)

    // here, Without this code the task will not work.
    SwiftFlutterForegroundTaskPlugin.setPluginRegistrantCallback { registry in
      GeneratedPluginRegistrant.register(with: registry)
    }
    if #available(iOS 10.0, *) {
      UNUserNotificationCenter.current().delegate = self as? UNUserNotificationCenterDelegate
    }

    let launched = super.application(application, didFinishLaunchingWithOptions: launchOptions)
    if #available(iOS 13.0, *) {
      // flutter_foreground_task registers an otherwise unused 25-second
      // refresh. Clear requests left by older releases after plugin dispatch.
      BGTaskScheduler.shared.cancel(
        taskRequestWithIdentifier: AppDelegate.unusedForegroundTaskRefreshIdentifier
      )
    }
    return launched
  }

  /// Swaps the engine-less storyboard controller for a plain notice before the
  /// window is shown, so nothing in this launch touches the missing engine.
  /// See FlutterLaunchEngineGuard for why the engine can be absent.
  private func showFlutterEngineUnavailableNotice() {
    #if DEBUG
    let debugBuild = true
    #else
    let debugBuild = false
    #endif
    let displayName =
      (Bundle.main.object(forInfoDictionaryKey: "CFBundleDisplayName") as? String) ?? "Omi"
    let message = FlutterLaunchEngineGuard.unavailableNotice(
      debugBuild: debugBuild,
      bundleDisplayName: displayName
    )
    NSLog("[OmiLaunch] Flutter engine unavailable at launch; skipping plugin registration.\n%@", message)

    let notice = UIViewController()
    notice.view.backgroundColor = .systemBackground
    let label = UILabel()
    label.numberOfLines = 0
    label.textAlignment = .center
    label.font = .preferredFont(forTextStyle: .body)
    label.textColor = .label
    label.text = message
    label.translatesAutoresizingMaskIntoConstraints = false
    notice.view.addSubview(label)
    NSLayoutConstraint.activate([
      label.leadingAnchor.constraint(equalTo: notice.view.layoutMarginsGuide.leadingAnchor, constant: 16),
      label.trailingAnchor.constraint(equalTo: notice.view.layoutMarginsGuide.trailingAnchor, constant: -16),
      label.centerYAnchor.constraint(equalTo: notice.view.centerYAnchor),
    ])
    // Also covers an iOS background relaunch (BLE/VoIP): nothing is drawn
    // until the user foregrounds the app, and this is what they see then.
    window?.rootViewController = notice
    window?.makeKeyAndVisible()
  }

  override func applicationDidEnterBackground(_ application: UIApplication) {
    super.applicationDidEnterBackground(application)
    OmiBleManager.shared.markBackgroundTelemetryStart()
    if #available(iOS 13.0, *) {
      // The plugin delegate schedules this request from the super call above;
      // cancel it after delegate dispatch so an idle app is not woken for an
      // empty 25-second operation.
      BGTaskScheduler.shared.cancel(
        taskRequestWithIdentifier: AppDelegate.unusedForegroundTaskRefreshIdentifier
      )
    }
  }

  override func applicationDidBecomeActive(_ application: UIApplication) {
    OmiBleManager.shared.markBackgroundTelemetryEnd()
    super.applicationDidBecomeActive(application)
  }

  // Meta AI app calls back into this app to finish Ray-Ban Meta registration
  // (AppLinkURLScheme in the MWDAT Info.plist dictionary).
  override func application(
    _ app: UIApplication,
    open url: URL,
    options: [UIApplication.OpenURLOptionsKey: Any] = [:]
  ) -> Bool {
    if rayBanMetaHostApi?.handleUrl(url) == true {
      return true
    }
    return super.application(app, open: url, options: options)
  }

  private func handleMethodCall(_ call: FlutterMethodCall, result: @escaping FlutterResult) {
    switch call.method {
      case "setNotificationOnKillService":
        handleSetNotificationOnKillService(call: call)
      default:
        result(FlutterMethodNotImplemented)
    }
  }

  private func handleSetNotificationOnKillService(call: FlutterMethodCall) {
    NSLog("handleMethodCall: setNotificationOnKillService")
    
    if let args = call.arguments as? Dictionary<String, Any> {
      notificationTitleOnKill = args["title"] as? String
      notificationBodyOnKill = args["description"] as? String
    }
    
  }
  
  private func handleAppleRemindersCall(_ call: FlutterMethodCall, result: @escaping FlutterResult) {
    appleRemindersService.handleMethodCall(call, result: result)
  }

  private func handleAppleHealthCall(_ call: FlutterMethodCall, result: @escaping FlutterResult) {
    appleHealthService.handleMethodCall(call, result: result)
  }

  // MARK: - Silent Push for Apple Reminders Auto-Sync

  override func application(
      _ application: UIApplication,
      didReceiveRemoteNotification userInfo: [AnyHashable: Any],
      fetchCompletionHandler completionHandler: @escaping (UIBackgroundFetchResult) -> Void
  ) {
      // Check if it's Apple Reminders sync
      if let type = userInfo["type"] as? String, type == "apple_reminders_sync" {
          handleAppleRemindersSync(userInfo: userInfo, completionHandler: completionHandler)
          return
      }

      // Also check nested under "data" key (some FCM configurations)
      if let data = userInfo["data"] as? [String: Any],
         let type = data["type"] as? String,
         type == "apple_reminders_sync" {
          handleAppleRemindersSync(userInfo: data, completionHandler: completionHandler)
          return
      }

      super.application(application, didReceiveRemoteNotification: userInfo, fetchCompletionHandler: completionHandler)
  }

  private func handleAppleRemindersSync(
      userInfo: [AnyHashable: Any],
      completionHandler: @escaping (UIBackgroundFetchResult) -> Void
  ) {
      guard let itemsJson = userInfo["items"] as? String else {
          completionHandler(.failed)
          return
      }

      let exportedMappings = appleRemindersService.syncBatchFromJSON(itemsJson)

      if !exportedMappings.isEmpty {
          DispatchQueue.main.async {
              self.appleRemindersChannel?.invokeMethod("markExportedBatch", arguments: ["mappings": exportedMappings])
          }
      }

      completionHandler(exportedMappings.isEmpty ? .noData : .newData)
  }

  override func applicationWillEnterForeground(_ application: UIApplication) {
    super.applicationWillEnterForeground(application)
    OmiBleManager.shared.reconnectStalePeripherals()
  }

  override func applicationWillTerminate(_ application: UIApplication) {
    QuickActionsIconPatcher.shared.stopObserving()
    OmiBleManager.shared.disconnectAllPeripherals()

    // If title and body are nil, then we don't need to show notification.
    if notificationTitleOnKill == nil || notificationBodyOnKill == nil {
      return
    }

    let content = UNMutableNotificationContent()
    content.title = notificationTitleOnKill!
    content.body = notificationBodyOnKill!
    let trigger = UNTimeIntervalNotificationTrigger(timeInterval: 1, repeats: false)
    let request = UNNotificationRequest(identifier: "notification on app kill", content: content, trigger: trigger)

    NSLog("Running applicationWillTerminate")

    UNUserNotificationCenter.current().add(request) { (error) in
      if let error = error {
        NSLog("Failed to show notification on kill service => error: \(error.localizedDescription)")
      } else {
        NSLog("Show notification on kill now")
      }
    }
    }

    private func handleAudioChunk(_ message: [String: Any]) {
        guard isRecordingActive else {
            print("Ignoring audio chunk - recording not active") // probably started recording with main omi app closed
            return
        }

        guard let audioChunk = message["audioChunk"] as? Data,
              let chunkIndex = message["chunkIndex"] as? Int,
              let isLast = message["isLast"] as? Bool,
              let sampleRate = message["sampleRate"] as? Double else {
            return
        }

        audioChunks[chunkIndex] = (audioChunk, sampleRate)

        if isLast {
            reassembleAndSendAudioData()
        } else {
            // Prepend 3 dummy bytes so downstream can uniformly strip headers
            var prefixedChunk = Data([0x00, 0x00, 0x00])
            prefixedChunk.append(audioChunk)
            let flutterData = FlutterStandardTypedData(bytes: prefixedChunk)
            self.flutterWatchAPI?.onAudioChunk(audioChunk: flutterData, chunkIndex: Int64(chunkIndex), isLast: isLast, sampleRate: sampleRate) { result in
                switch result {
                case .success:
                    break
                case .failure(let error):
                    print("Audio chunk \(chunkIndex) sent to Flutter - Error: \(error.message)")
                }
            }
        }
    }

    private func reassembleAndSendAudioData() {
        // Sort chunks by index and combine them
        let sortedChunks = audioChunks.sorted(by: { $0.key < $1.key })
        var combinedData = Data()
        var sampleRate: Double = 48000.0 // Default fallback

        for (_, chunkTuple) in sortedChunks {
            let (chunkData, chunkSampleRate) = chunkTuple
            combinedData.append(chunkData)
            sampleRate = chunkSampleRate
        }

        // Prepend 3 dummy bytes for full buffer as well
        var prefixed = Data([0x00, 0x00, 0x00])
        prefixed.append(combinedData)
        let flutterData = FlutterStandardTypedData(bytes: prefixed)
        self.flutterWatchAPI?.onAudioData(audioData: flutterData) { result in
            switch result {
            case .success:
                break
            case .failure(let error):
                print("Complete audio data sent to Flutter - Error: \(error.message)")
            }
        }

        audioChunks.removeAll()
        nextExpectedChunkIndex = 0
    }
}

func registerPlugins(registry: FlutterPluginRegistry) {
  GeneratedPluginRegistrant.register(with: registry)
}

extension AppDelegate: WCSessionDelegate {
    
    func session(_ session: WCSession, activationDidCompleteWith activationState: WCSessionActivationState, error: Error?) { }
    
    func sessionDidBecomeInactive(_ session: WCSession) {
        print("Session Watch Become Inactive")
    }
    
    func sessionDidDeactivate(_ session: WCSession) {
        print("Session Watch Deactivate")
    }
    
    // Receive a message from watch (foreground/active)
    func session(_ session: WCSession, didReceiveMessage message: [String : Any]) {
        Task {
            guard let method = message["method"] as? String else {
                return
            }

            switch method {
            case "startRecording":
                self.isRecordingActive = true
                self.audioChunks.removeAll()
                self.nextExpectedChunkIndex = 0
                
                DispatchQueue.main.async {
                    self.flutterWatchAPI?.onRecordingStarted() { result in
                        switch result {
                        case .success:
                            break
                        case .failure(let error):
                            print("iOS: Recording started notification sent to Flutter - Error: \(error.message)")
                        }
                    }
                }
            case "stopRecording":
                self.isRecordingActive = false
                self.flutterWatchAPI?.onRecordingStopped() { result in
                    switch result {
                    case .success:
                        break
                    case .failure(let error):
                        print("Recording stopped on Flutter - Error: \(error.message)")
                    }
                }
            case "sendAudioData":
                if let audioData = message["audioData"] as? Data {
                    // Prepend 3 dummy bytes for single-shot audio data
                    var prefixed = Data([0x00, 0x00, 0x00])
                    prefixed.append(audioData)
                    let flutterData = FlutterStandardTypedData(bytes: prefixed)
                    self.flutterWatchAPI?.onAudioData(audioData: flutterData) { result in
                        switch result {
                        case .success:
                            break
                        case .failure(let error):
                            print("Audio data sent to Flutter - Error: \(error.message)")
                        }
                    }
                } else {
                    print("Failed to cast audioData as Data - received type: \(type(of: message["audioData"]))")
                }
            case "sendAudioChunk":
                self.handleAudioChunk(message)
            case "recordingError":
                if let error = message["error"] as? String {
                    self.flutterWatchAPI?.onRecordingError(error: error) { result in
                        switch result {
                        case .success:
                            break
                        case .failure(let error):
                            print("Recording error sent to Flutter - Error: \(error.message)")
                        }
                    }
                }
            case "microphonePermissionResult":
                if let granted = message["granted"] as? Bool {
                    self.flutterWatchAPI?.onMicrophonePermissionResult(granted: granted) { result in
                        switch result {
                        case .success:
                            break
                        case .failure(let error):
                            print("Microphone permission result sent to Flutter - Error: \(error.message)")
                        }
                    }
                }
            case "batteryUpdate":
                if let batteryLevel = message["batteryLevel"] as? Double,
                   let batteryState = message["batteryState"] as? Int {
                    UserDefaults.standard.set(batteryLevel, forKey: "watch_battery_level")
                    UserDefaults.standard.set(batteryState, forKey: "watch_battery_state")
                    UserDefaults.standard.set(Date(), forKey: "watch_battery_last_updated")
                    
                    DispatchQueue.main.async {
                        self.flutterWatchAPI?.onWatchBatteryUpdate(batteryLevel: batteryLevel, batteryState: Int64(batteryState)) { result in
                            switch result {
                            case .success:
                                break
                            case .failure(let error):
                                print("iOS: Battery update sent to Flutter - Error: \(error.message)")
                            }
                        }
                    }
                }
            case "watchInfoUpdate":
                if let name = message["name"] as? String,
                   let model = message["model"] as? String,
                   let systemVersion = message["systemVersion"] as? String,
                   let localizedModel = message["localizedModel"] as? String {

                    UserDefaults.standard.set(name, forKey: "watch_device_name")
                    UserDefaults.standard.set(model, forKey: "watch_device_model")
                    UserDefaults.standard.set(systemVersion, forKey: "watch_system_version")
                    UserDefaults.standard.set(localizedModel, forKey: "watch_localized_model")
                    UserDefaults.standard.set(Date(), forKey: "watch_info_last_updated")
                }
            default:
                print("Unknown method: \(method)")
            }
        }
    }
    
    // Receive user info from watch (background/offline)
    // Used for 1.5 second audio chunks when screen is off or app is backgrounded
    func session(_ session: WCSession, didReceiveUserInfo userInfo: [String : Any]) {
        
        Task {
            guard let method = userInfo["method"] as? String else {
                return
            }
            
            switch method {
            case "sendAudioChunk":
                self.handleAudioChunk(userInfo)
            case "stopRecording":
                self.isRecordingActive = false
                    self.flutterWatchAPI?.onRecordingStopped() { result in
                    switch result {
                    case .success:
                        break
                    case .failure(let error):
                        print("Stop recording (background) sent to Flutter - Error: \(error.message)")
                    }
                }
            case "recordingError":
                if let error = userInfo["error"] as? String {
                    self.flutterWatchAPI?.onRecordingError(error: error) { result in
                        switch result {
                        case .success:
                            break
                        case .failure(let error):
                            print("Recording error (background) sent to Flutter - Error: \(error.message)")
                        }
                    }
                }
            case "batteryUpdate":
                if let batteryLevel = userInfo["batteryLevel"] as? Double,
                   let batteryState = userInfo["batteryState"] as? Int {
                    UserDefaults.standard.set(batteryLevel, forKey: "watch_battery_level")
                    UserDefaults.standard.set(batteryState, forKey: "watch_battery_state")
                    UserDefaults.standard.set(Date(), forKey: "watch_battery_last_updated")
                    
                    DispatchQueue.main.async {
                        self.flutterWatchAPI?.onWatchBatteryUpdate(batteryLevel: batteryLevel, batteryState: Int64(batteryState)) { result in
                            switch result {
                            case .success:
                                break
                            case .failure(let error):
                                print("iOS: Background battery update sent to Flutter - Error: \(error.message)")
                            }
                        }
                    }
                }
            case "watchInfoUpdate":
                if let name = userInfo["name"] as? String,
                   let model = userInfo["model"] as? String,
                   let systemVersion = userInfo["systemVersion"] as? String,
                   let localizedModel = userInfo["localizedModel"] as? String {
                    UserDefaults.standard.set(name, forKey: "watch_device_name")
                    UserDefaults.standard.set(model, forKey: "watch_device_model")
                    UserDefaults.standard.set(systemVersion, forKey: "watch_system_version")
                    UserDefaults.standard.set(localizedModel, forKey: "watch_localized_model")
                    UserDefaults.standard.set(Date(), forKey: "watch_info_last_updated")
                }
            default:
                print("Unknown background method: \(method)")
            }
        }
    }
}

/// iOS 26 on-device transcription through SpeechAnalyzer. Unlike
/// SFSpeechRecognizer's on-device mode, it does not depend on Siri or
/// Dictation being enabled in Settings: the language model is an asset the
/// app installs itself through AssetInventory. Used first on iOS 26; the
/// SFSpeechRecognizer path below remains for older systems and as a fallback.
@available(iOS 26, *)
@MainActor
enum SpeechAnalyzerTranscription {
    enum TranscriptionError: Error {
        case unsupportedLanguage(String)
        case timedOut
    }

    /// In-flight model downloads keyed by BCP-47 locale, so the pre-flight
    /// probe and the first transcribe() share one download.
    private static var installTasks: [String: Task<Void, Error>] = [:]

    static func requestedLanguage(_ language: String) -> String {
        let requested = language.isEmpty || language == "multi" ? "en" : language
        return Locale(identifier: requested).language.languageCode?.identifier ?? requested
    }

    /// Best locale for the app's (bare) language code: an installed model
    /// first, then any supported one, preferring the device locale in each.
    static func locale(for language: String) async -> Locale? {
        let wanted = requestedLanguage(language)
        let current = Locale.current.identifier(.bcp47)
        func pick(_ locales: [Locale]) -> Locale? {
            let matching = locales.filter { $0.language.languageCode?.identifier == wanted }
            return matching.first { $0.identifier(.bcp47) == current }
                ?? matching.sorted { $0.identifier(.bcp47) < $1.identifier(.bcp47) }.first
        }
        if let installed = pick(await SpeechTranscriber.installedLocales) { return installed }
        return pick(await SpeechTranscriber.supportedLocales)
    }

    static func isInstalled(_ locale: Locale) async -> Bool {
        await SpeechTranscriber.installedLocales.contains { $0.identifier(.bcp47) == locale.identifier(.bcp47) }
    }

    /// Installs the model for `locale` if it is not already on the device.
    /// Concurrent callers wait on the same download.
    static func ensureModel(for locale: Locale) async throws {
        if await isInstalled(locale) { return }
        let key = locale.identifier(.bcp47)
        let task: Task<Void, Error>
        if let existing = installTasks[key] {
            task = existing
        } else {
            task = Task {
                let transcriber = SpeechTranscriber(locale: locale, preset: .transcription)
                if let request = try await AssetInventory.assetInstallationRequest(supporting: [transcriber]) {
                    NSLog("[SpeechAnalyzer] downloading speech model for %@", key)
                    try await request.downloadAndInstall()
                    NSLog("[SpeechAnalyzer] speech model installed for %@", key)
                }
            }
            installTasks[key] = task
        }
        defer {
            if installTasks[key] == task { installTasks[key] = nil }
        }
        try await task.value
    }

    /// Whether transcription can run for `language`: the locale is supported
    /// and its model is installed, or finishes installing within
    /// `installWait`. A download still running after that counts as available
    /// too; it continues in the background and transcribe() waits for it.
    /// Only a failed download (no network, unsupported locale) reports false.
    static func isAvailable(language: String, installWait: Double = 8) async -> Bool {
        guard let locale = await locale(for: language) else {
            NSLog("[SpeechAnalyzer] no supported locale for language %@", language)
            return false
        }
        if await isInstalled(locale) { return true }
        return await SpeechDeadline.run(seconds: installWait, operation: {
            do {
                try await ensureModel(for: locale)
                return true
            } catch {
                NSLog("[SpeechAnalyzer] model install failed for %@: %@", locale.identifier(.bcp47), error.localizedDescription)
                return false
            }
        }, onTimeout: {
            // The shared download keeps running; only this availability waiter
            // has a deadline. A later transcription shares the same download.
            true
        })
    }

    /// Transcribes a whole audio file (the Dart side writes 16 kHz mono WAV
    /// clips) and returns the text, empty when no speech was recognized.
    static func transcribe(fileURL: URL, language: String) async throws -> String {
        guard let locale = await locale(for: language) else {
            throw TranscriptionError.unsupportedLanguage(language)
        }
        let installed: Result<Void, Error> = await SpeechDeadline.run(seconds: 20, operation: {
            do {
                try await ensureModel(for: locale)
                return .success(())
            } catch {
                return .failure(error)
            }
        }, onTimeout: { .failure(TranscriptionError.timedOut) })
        try installed.get()

        let transcriber = SpeechTranscriber(locale: locale, preset: .transcription)
        let analyzer = SpeechAnalyzer(modules: [transcriber])
        let collector = Task { () throws -> String in
            var finalText = ""
            var volatileText = ""
            for try await result in transcriber.results {
                let text = String(result.text.characters)
                if result.isFinal {
                    finalText += text
                } else {
                    volatileText = text
                }
            }
            return finalText.isEmpty ? volatileText : finalText
        }
        let outcome: Result<String, Error> = await SpeechDeadline.run(seconds: 20, operation: {
            do {
                let file = try AVAudioFile(forReading: fileURL)
                if let lastSample = try await analyzer.analyzeSequence(from: file) {
                    try await analyzer.finalizeAndFinish(through: lastSample)
                } else {
                    await analyzer.cancelAndFinishNow()
                }
                return .success(try await collector.value.trimmingCharacters(in: .whitespacesAndNewlines))
            } catch {
                await analyzer.cancelAndFinishNow()
                collector.cancel()
                return .failure(error)
            }
        }, onTimeout: {
            collector.cancel()
            await analyzer.cancelAndFinishNow()
            return .failure(TranscriptionError.timedOut)
        })
        return try outcome.get()
    }
}

class SpeechRecognitionHandler: NSObject {
    
    func handle(_ call: FlutterMethodCall, result: @escaping FlutterResult) {
        if call.method == "transcribe" {
            guard let args = call.arguments as? [String: Any],
                  let path = args["filePath"] as? String else {
                result(FlutterError(code: "INVALID_ARGS", message: "Missing arguments", details: nil))
                return
            }
            
            let language = args["language"] as? String ?? "en-US"
            if #available(iOS 26, *) {
                // SpeechAnalyzer needs no Dictation setting; fall back to
                // SFSpeechRecognizer only if it cannot handle this clip.
                Task {
                    do {
                        let text = try await SpeechAnalyzerTranscription.transcribe(
                            fileURL: URL(fileURLWithPath: path), language: language)
                        DispatchQueue.main.async { result(text) }
                    } catch {
                        NSLog("[SpeechAnalyzer] transcribe failed, falling back to SFSpeechRecognizer: %@", error.localizedDescription)
                        DispatchQueue.main.async {
                            self.transcribe(filePath: path, language: language, result: result)
                        }
                    }
                }
                return
            }
            transcribe(filePath: path, language: language, result: result)
        } else if call.method == "onDeviceAvailable" {
            let args = call.arguments as? [String: Any]
            let language = args?["language"] as? String ?? "en-US"
            if #available(iOS 26, *) {
                Task {
                    if await SpeechAnalyzerTranscription.isAvailable(language: language) {
                        DispatchQueue.main.async { result(true) }
                    } else {
                        DispatchQueue.main.async {
                            self.probeOnDeviceRecognition(language: language, result: result)
                        }
                    }
                }
                return
            }
            probeOnDeviceRecognition(language: language, result: result)
        } else {
            result(FlutterMethodNotImplemented)
        }
    }

    /// Resolve the app's language setting to a locale whose recognizer can run
    /// on-device. The app passes bare language codes ("en"); on-device assets
    /// are installed per full locale ("en-US"), and a recognizer built from a
    /// bare code fails every request with kAFAssistantErrorDomain 1101 once
    /// `requiresOnDeviceRecognition` is set. Prefer the device's own locale
    /// when it matches the language (that is the model most likely to be
    /// installed), then any supported locale for that language.
    static func onDeviceRecognizer(for language: String) -> SFSpeechRecognizer? {
        let requested = language.isEmpty || language == "multi" ? "en" : language
        let requestedLocale = Locale(identifier: requested)
        let requestedLanguage = requestedLocale.languageCode ?? requested

        var candidates: [Locale] = []
        if requested.contains("-") || requested.contains("_") {
            candidates.append(requestedLocale)
        }
        if Locale.current.languageCode == requestedLanguage {
            candidates.append(Locale.current)
        }
        candidates.append(contentsOf: SFSpeechRecognizer.supportedLocales()
            .filter { $0.languageCode == requestedLanguage }
            .sorted { $0.identifier < $1.identifier })
        candidates.append(requestedLocale)

        var seen = Set<String>()
        for locale in candidates {
            guard seen.insert(locale.identifier).inserted else { continue }
            guard let recognizer = SFSpeechRecognizer(locale: locale) else { continue }
            if recognizer.isAvailable && recognizer.supportsOnDeviceRecognition {
                return recognizer
            }
        }
        return nil
    }

    /// Whether on-device recognition can actually run right now, checked by
    /// recognizing a short silent clip. `supportsOnDeviceRecognition` alone is
    /// not enough: with Siri and Dictation disabled in iOS Settings every
    /// request fails at run time with kLSRErrorDomain 201 while the recognizer
    /// still advertises on-device support. Reports true on "no speech" (1110,
    /// the expected outcome for silence) and false on any other error, so a
    /// caller never falls back onto a recognizer that cannot work.
    private func probeOnDeviceRecognition(language: String, result: @escaping FlutterResult) {
        guard let recognizer = SpeechRecognitionHandler.onDeviceRecognizer(for: language) else {
            result(false)
            return
        }
        guard let silence = SpeechRecognitionHandler.writeSilentWav(seconds: 0.6) else {
            result(true) // Could not build a probe clip; do not block the fallback on that.
            return
        }

        var finished = false
        var task: SFSpeechRecognitionTask?
        let finish: (Bool) -> Void = { value in
            guard !finished else { return }
            finished = true
            task?.cancel()
            try? FileManager.default.removeItem(at: silence)
            result(value)
        }

        let request = SFSpeechURLRecognitionRequest(url: silence)
        request.shouldReportPartialResults = false
        request.requiresOnDeviceRecognition = true
        task = recognizer.recognitionTask(with: request) { recognitionResult, error in
            DispatchQueue.main.async {
                if let error = error {
                    let nsError = error as NSError
                    let noSpeech = nsError.domain == "kAFAssistantErrorDomain" && nsError.code == 1110
                    if !noSpeech {
                        NSLog("[SpeechRecognition] on-device probe failed: %@ %ld %@", nsError.domain, nsError.code, error.localizedDescription)
                    }
                    finish(noSpeech)
                    return
                }
                if recognitionResult?.isFinal == true {
                    finish(true)
                }
            }
        }
        DispatchQueue.main.asyncAfter(deadline: .now() + 5) {
            guard !finished else { return }
            finish(true) // Slow but not failing; let the real request decide.
        }
    }

    /// 16 kHz mono 16-bit PCM WAV of silence, for probing the recognizer.
    static func writeSilentWav(seconds: Double) -> URL? {
        let sampleRate = 16000
        let sampleCount = Int(Double(sampleRate) * seconds)
        let dataSize = sampleCount * 2
        var data = Data(capacity: 44 + dataSize)
        func append<T: FixedWidthInteger>(_ value: T) {
            var little = value.littleEndian
            data.append(Data(bytes: &little, count: MemoryLayout<T>.size))
        }
        data.append(contentsOf: Array("RIFF".utf8)); append(UInt32(36 + dataSize))
        data.append(contentsOf: Array("WAVE".utf8))
        data.append(contentsOf: Array("fmt ".utf8)); append(UInt32(16)); append(UInt16(1)); append(UInt16(1))
        append(UInt32(sampleRate)); append(UInt32(sampleRate * 2)); append(UInt16(2)); append(UInt16(16))
        data.append(contentsOf: Array("data".utf8)); append(UInt32(dataSize))
        data.append(Data(count: dataSize))
        let url = FileManager.default.temporaryDirectory.appendingPathComponent("omi_speech_probe_\(UUID().uuidString).wav")
        do {
            try data.write(to: url)
            return url
        } catch {
            return nil
        }
    }

    private func transcribe(filePath: String, language: String, result: @escaping FlutterResult) {
        // Request authorization first
        SFSpeechRecognizer.requestAuthorization { authStatus in
            DispatchQueue.main.async {
                if authStatus != .authorized {
                    result(FlutterError(code: "UNAUTHORIZED", message: "Speech recognition not authorized", details: nil))
                    return
                }

                let fileUrl = URL(fileURLWithPath: filePath)

                guard let recognizer = SpeechRecognitionHandler.onDeviceRecognizer(for: language) else {
                    result(FlutterError(code: "UNAVAILABLE", message: "No on-device speech recognizer available for language \(language)", details: nil))
                    return
                }

                let request = SFSpeechURLRecognitionRequest(url: fileUrl)
                // Partial results are kept so a task that never reports `isFinal`
                // (observed with on-device recognition on short clips) still
                // yields its best transcription instead of hanging the caller.
                request.shouldReportPartialResults = true
                request.requiresOnDeviceRecognition = true // Force on-device
                request.taskHint = .dictation
                if #available(iOS 16, *) {
                    request.addsPunctuation = true
                }

                // The Dart caller awaits exactly one reply per clip, and its polling
                // loop stays busy until that reply arrives — a task that never
                // completes would silently stop all further transcription. Reply
                // once, on the first of: final result, error, or timeout.
                var finished = false
                var latestText = ""
                var task: SFSpeechRecognitionTask?
                let finish: (Any?) -> Void = { value in
                    guard !finished else { return }
                    finished = true
                    task?.cancel()
                    result(value)
                }

                task = recognizer.recognitionTask(with: request) { (recognitionResult, error) in
                    DispatchQueue.main.async {
                        if let recognitionResult = recognitionResult {
                            latestText = recognitionResult.bestTranscription.formattedString
                            if recognitionResult.isFinal {
                                finish(latestText)
                                return
                            }
                        }
                        if let error = error {
                            let nsError = error as NSError
                            // 1110 = no speech in the clip; a partial transcription before the
                            // error is still the best answer for that clip. Only a failure that
                            // produced nothing is reported as an error.
                            if !latestText.isEmpty || (nsError.domain == "kAFAssistantErrorDomain" && nsError.code == 1110) {
                                finish(latestText)
                            } else {
                                finish(FlutterError(
                                    code: "RECOGNITION_ERROR",
                                    message: "\(nsError.domain) \(nsError.code): \(error.localizedDescription) (locale \(recognizer.locale.identifier))",
                                    details: nil))
                            }
                        }
                    }
                }

                DispatchQueue.main.asyncAfter(deadline: .now() + 20) {
                    guard !finished else { return }
                    if latestText.isEmpty {
                        finish(FlutterError(code: "RECOGNITION_TIMEOUT", message: "On-device recognition timed out", details: nil))
                    } else {
                        finish(latestText)
                    }
                }
            }
        }
    }
}
