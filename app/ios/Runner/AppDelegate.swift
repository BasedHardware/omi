import UIKit
import Flutter
import UserNotifications
import app_links
import WatchConnectivity
import AVFoundation
import Speech
import EventKit

extension FlutterError: Error {}

@main
@objc class AppDelegate: FlutterAppDelegate {
  private var methodChannel: FlutterMethodChannel?
  private var appleRemindersChannel: FlutterMethodChannel?
  private let appleRemindersService = AppleRemindersService()
  private static let iso8601DateFormatter = ISO8601DateFormatter()

  private var notificationTitleOnKill: String?
  private var notificationBodyOnKill: String?

  var session: WCSession?
    var flutterWatchAPI: WatchRecorderFlutterAPI?
  private var audioChunks: [Int: (Data, Double)] = [:] // (audioData, sampleRate)
  private var nextExpectedChunkIndex: Int = 0
  private var isRecordingActive: Bool = false // Track recording state to handle app restarts

  override func application(
    _ application: UIApplication,
    didFinishLaunchingWithOptions launchOptions: [UIApplication.LaunchOptionsKey: Any]?
  ) -> Bool {
    GeneratedPluginRegistrant.register(with: self)
      
      
      if WCSession.isSupported() {
          session = WCSession.default
          session?.delegate = self
          session?.activate();

          let controller = window?.rootViewController as? FlutterViewController
            flutterWatchAPI = WatchRecorderFlutterAPI(binaryMessenger: controller!.binaryMessenger)
            let api: WatchRecorderHostAPI = RecorderHostApiImpl(session: session!, flutterWatchAPI: flutterWatchAPI)

            WatchRecorderHostAPISetup.setUp(binaryMessenger: controller!.binaryMessenger, api: api)
      }

      // Retrieve the link from parameters
    if let url = AppLinks.shared.getLink(launchOptions: launchOptions) {
      // We have a link, propagate it to your Flutter app or not
      AppLinks.shared.handleLink(url: url)
      return true // Returning true will stop the propagation to other packages
    }
    //Creates a method channel to handle notifications on kill
    let controller = window?.rootViewController as? FlutterViewController
    methodChannel = FlutterMethodChannel(name: "com.friend.ios/notifyOnKill", binaryMessenger: controller!.binaryMessenger)
    methodChannel?.setMethodCallHandler { [weak self] (call, result) in
      self?.handleMethodCall(call, result: result)
    }
    
    // Create Apple Reminders method channel
    appleRemindersChannel = FlutterMethodChannel(name: "com.omi.apple_reminders", binaryMessenger: controller!.binaryMessenger)
    appleRemindersChannel?.setMethodCallHandler { [weak self] (call, result) in
      self?.handleAppleRemindersCall(call, result: result)
    }

    // Create Speech Recognition method channel
    let speechChannel = FlutterMethodChannel(name: "com.omi.ios/speech", binaryMessenger: controller!.binaryMessenger)
    let speechHandler = SpeechRecognitionHandler()
    speechChannel.setMethodCallHandler { (call, result) in
        speechHandler.handle(call, result: result)
    }

    // Create WiFi Network plugin for device AP connection
    _ = WifiNetworkPlugin(messenger: controller!.binaryMessenger)

    // here, Without this code the task will not work.
    SwiftFlutterForegroundTaskPlugin.setPluginRegistrantCallback { registry in
      GeneratedPluginRegistrant.register(with: registry)
    }
    if #available(iOS 10.0, *) {
      UNUserNotificationCenter.current().delegate = self as? UNUserNotificationCenterDelegate
    }

    return super.application(application, didFinishLaunchingWithOptions: launchOptions)
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

  // MARK: - Silent Push for Apple Reminders Auto-Sync

  private let syncEventStore = EKEventStore()

  override func application(
      _ application: UIApplication,
      didReceiveRemoteNotification userInfo: [AnyHashable: Any],
      fetchCompletionHandler completionHandler: @escaping (UIBackgroundFetchResult) -> Void
  ) {
      print("AppDelegate: Received remote notification: \(userInfo)")

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
      guard let actionItemId = userInfo["action_item_id"] as? String,
            let description = userInfo["description"] as? String else {
          completionHandler(.failed)
          return
      }

      // Check permission - handle iOS 17+ new authorization states
      let status = EKEventStore.authorizationStatus(for: .reminder)

      // iOS 17+ uses .fullAccess and .writeOnly, older iOS uses .authorized
      var hasAccess = false
      if #available(iOS 17.0, *) {
          hasAccess = status == .fullAccess || status == .writeOnly
      } else {
          hasAccess = status == .authorized
      }

      guard hasAccess else {
          completionHandler(.failed)
          return
      }

      // Parse due date
      let dueDate: Date? = {
          if let dueDateStr = userInfo["due_at"] as? String, !dueDateStr.isEmpty {
              return AppDelegate.iso8601DateFormatter.date(from: dueDateStr)
          }
          return nil
      }()

      // Create reminder
      let reminder = EKReminder(eventStore: syncEventStore)
      reminder.title = description
      reminder.notes = "From Omi"
      reminder.calendar = syncEventStore.defaultCalendarForNewReminders()

      if let due = dueDate {
          reminder.dueDateComponents = Calendar.current.dateComponents(
              [.year, .month, .day, .hour, .minute], from: due
          )
      }

      do {
          try syncEventStore.save(reminder, commit: true)

          // Notify Flutter to mark as exported via API
          DispatchQueue.main.async {
              self.appleRemindersChannel?.invokeMethod("markExported", arguments: ["action_item_id": actionItemId])
          }

          completionHandler(.newData)
      } catch {
          completionHandler(.failed)
      }
  }

  override func applicationWillTerminate(_ application: UIApplication) {
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

class SpeechRecognitionHandler: NSObject {
    
    func handle(_ call: FlutterMethodCall, result: @escaping FlutterResult) {
        if call.method == "transcribe" {
            guard let args = call.arguments as? [String: Any],
                  let path = args["filePath"] as? String else {
                result(FlutterError(code: "INVALID_ARGS", message: "Missing arguments", details: nil))
                return
            }
            
            let language = args["language"] as? String ?? "en-US"
            transcribe(filePath: path, language: language, result: result)
        } else {
            result(FlutterMethodNotImplemented)
        }
    }
    
    private func transcribe(filePath: String, language: String, result: @escaping FlutterResult) {
        // Request authorization first
        SFSpeechRecognizer.requestAuthorization { authStatus in
            if authStatus != .authorized {
                result(FlutterError(code: "UNAUTHORIZED", message: "Speech recognition not authorized", details: nil))
                return
            }
            
            let fileUrl = URL(fileURLWithPath: filePath)
            let localeIdentifier = language.isEmpty ? "en-US" : language
            let locale = Locale(identifier: localeIdentifier)
            
            guard let recognizer = SFSpeechRecognizer(locale: locale) else {
                result(FlutterError(code: "UNAVAILABLE", message: "Speech recognizer not available for locale \(localeIdentifier)", details: nil))
                return
            }
            
            if !recognizer.isAvailable {
                result(FlutterError(code: "UNAVAILABLE", message: "Speech recognizer service is currently unavailable", details: nil))
                return
            }
            
            let request = SFSpeechURLRecognitionRequest(url: fileUrl)
            request.shouldReportPartialResults = false
            request.requiresOnDeviceRecognition = true // Force on-device
            
            let task = recognizer.recognitionTask(with: request) { (recognitionResult, error) in
                if let error = error {
                    // Check if it's just "No speech identified" which might happen with silence
                    let nsError = error as NSError
                    if nsError.domain == "kAFAssistantErrorDomain" && nsError.code == 1110 {
                         result("") // Treat as empty
                    } else {
                         result(FlutterError(code: "RECOGNITION_ERROR", message: error.localizedDescription, details: nil))
                    }
                    return
                }
                
                if let recognitionResult = recognitionResult, recognitionResult.isFinal {
                    let text = recognitionResult.bestTranscription.formattedString
                    result(text)
                }
            }
        }
    }
}
