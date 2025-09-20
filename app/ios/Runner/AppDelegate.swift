import UIKit
import Flutter
import UserNotifications
import app_links
import WatchConnectivity
import AVFoundation


extension FlutterError: Error {}


@main
@objc class AppDelegate: FlutterAppDelegate {
  private var methodChannel: FlutterMethodChannel?
  private var appleRemindersChannel: FlutterMethodChannel?
  private let appleRemindersService = AppleRemindersService()

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
        // Only process audio chunks if recording is actually active
        guard isRecordingActive else {
            print("Ignoring audio chunk - recording not active (likely buffered message after app restart)")
            return
        }

        guard let audioChunk = message["audioChunk"] as? Data,
              let chunkIndex = message["chunkIndex"] as? Int,
              let isLast = message["isLast"] as? Bool,
              let sampleRate = message["sampleRate"] as? Double else {
            print("Invalid audio chunk message format")
            return
        }

        print("Received audio chunk \(chunkIndex), size: \(audioChunk.count) bytes, isLast: \(isLast), rate: \(sampleRate)Hz")

        // Store the chunk with sample rate
        audioChunks[chunkIndex] = (audioChunk, sampleRate)

        if isLast {
            // All chunks received, reassemble and send to Flutter
            reassembleAndSendAudioData()
        } else {
            // Send individual chunk to Flutter immediately
            let flutterData = FlutterStandardTypedData(bytes: audioChunk)
            self.flutterWatchAPI?.onAudioChunk(audioChunk: flutterData, chunkIndex: Int64(chunkIndex), isLast: isLast, sampleRate: sampleRate) { result in
                switch result {
                case .success(_):
                    if chunkIndex % 10 == 0 { // Only log every 10th chunk
                        print("Audio chunk \(chunkIndex) sent to Flutter - Success")
                    }
                case .failure(let error):
                    print("Audio chunk \(chunkIndex) sent to Flutter - Error: \(error.message)")
                }
            }
        }
    }

    private func reassembleAndSendAudioData() {
        print("Reassembling audio data from \(audioChunks.count) chunks")

        // Sort chunks by index and combine them
        let sortedChunks = audioChunks.sorted(by: { $0.key < $1.key })
        var combinedData = Data()
        var sampleRate: Double = 48000.0 // Default fallback

        for (_, chunkTuple) in sortedChunks {
            let (chunkData, chunkSampleRate) = chunkTuple
            combinedData.append(chunkData)
            sampleRate = chunkSampleRate // Use the sample rate from the last chunk
        }

        print("Combined audio data size: \(combinedData.count) bytes, sample rate: \(sampleRate)Hz")

        // Send the complete audio data to Flutter
        let flutterData = FlutterStandardTypedData(bytes: combinedData)
        self.flutterWatchAPI?.onAudioData(audioData: flutterData) { result in
            switch result {
            case .success(_):
                print("Complete audio data sent to Flutter - Success")
            case .failure(let error):
                print("Complete audio data sent to Flutter - Error: \(error.message)")
            }
        }

        // Clear the buffer for next recording
        audioChunks.removeAll()
        nextExpectedChunkIndex = 0
    }
}

// here
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
                self.audioChunks.removeAll() // Clear any buffered chunks from previous sessions
                self.nextExpectedChunkIndex = 0
                
                // Notify Flutter app that recording is starting (this helps prevent crash)
                DispatchQueue.main.async {
                    self.flutterWatchAPI?.onRecordingStarted() { result in
                        switch result {
                        case .success(_):
                            print("iOS: Recording started notification sent to Flutter - Success")
                        case .failure(let error):
                            print("iOS: Recording started notification sent to Flutter - Error: \(error.message)")
                        }
                    }
                }
            case "stopRecording":
                self.isRecordingActive = false
                self.flutterWatchAPI?.onRecordingStopped() { result in
                    switch result {
                    case .success(_):
                        print("Recording stopped on Flutter - Success")
                    case .failure(let error):
                        print("Recording stopped on Flutter - Error: \(error.message)")
                    }
                }
            case "sendAudioData":
                if let audioData = message["audioData"] as? Data {
                    print("Audio data received, size: \(audioData.count) bytes")
                    let flutterData = FlutterStandardTypedData(bytes: audioData)
                    print("Converted to FlutterStandardTypedData")
                    self.flutterWatchAPI?.onAudioData(audioData: flutterData) { result in
                        switch result {
                        case .success(_):
                            print("Audio data sent to Flutter - Success")
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
                print("Received recording error from watch")
                if let error = message["error"] as? String {
                    print("Recording error: \(error)")
                    // Forward error to Flutter
                    self.flutterWatchAPI?.onRecordingError(error: error) { result in
                        switch result {
                        case .success(_):
                            print("Recording error sent to Flutter - Success")
                        case .failure(let error):
                            print("Recording error sent to Flutter - Error: \(error.message)")
                        }
                    }
                }
            case "microphonePermissionResult":
                if let granted = message["granted"] as? Bool {
                    print("Microphone permission granted: \(granted)")
                    // Forward result to Flutter
                    self.flutterWatchAPI?.onMicrophonePermissionResult(granted: granted) { result in
                        switch result {
                        case .success(_):
                            print("Microphone permission result sent to Flutter - Success")
                        case .failure(let error):
                            print("Microphone permission result sent to Flutter - Error: \(error.message)")
                        }
                    }
                }
            case "batteryUpdate":
                if let batteryLevel = message["batteryLevel"] as? Double,
                   let batteryState = message["batteryState"] as? Int {
                    print("iOS: Watch battery - Level: \(batteryLevel)%, State: \(batteryState)")
                    // Store battery info for Flutter to access
                    UserDefaults.standard.set(batteryLevel, forKey: "watch_battery_level")
                    UserDefaults.standard.set(batteryState, forKey: "watch_battery_state")
                    UserDefaults.standard.set(Date(), forKey: "watch_battery_last_updated")
                    
                    // Forward to Flutter
                    DispatchQueue.main.async {
                        self.flutterWatchAPI?.onWatchBatteryUpdate(batteryLevel: batteryLevel, batteryState: Int64(batteryState)) { result in
                            switch result {
                            case .success(_):
                                print("iOS: Battery update sent to Flutter - Success")
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
    
    // Receive user info from watch (background/offline reliable transfer)
    // Now used for 1-second audio chunks when screen is off or app is backgrounded
    func session(_ session: WCSession, didReceiveUserInfo userInfo: [String : Any]) {
        
        Task {
            guard let method = userInfo["method"] as? String else {
                print("No method in userInfo")
                return
            }
            
            print("Processing background userInfo method: \(method)")
            
            switch method {
            case "sendAudioChunk":
                print("Processing background 1-second audio chunk")
                self.handleAudioChunk(userInfo)
            case "stopRecording":
                print("Processing background stop recording")
                self.isRecordingActive = false
                self.flutterWatchAPI?.onRecordingStopped() { result in
                    switch result {
                    case .success(_):
                        print("Stop recording (background) sent to Flutter - Success")
                    case .failure(let error):
                        print("Stop recording (background) sent to Flutter - Error: \(error.message)")
                    }
                }
            case "recordingError":
                print("Processing background recording error")
                if let error = userInfo["error"] as? String {
                    print("Background recording error: \(error)")
                    self.flutterWatchAPI?.onRecordingError(error: error) { result in
                        switch result {
                        case .success(_):
                            print("Recording error (background) sent to Flutter - Success")
                        case .failure(let error):
                            print("Recording error (background) sent to Flutter - Error: \(error.message)")
                        }
                    }
                }
            case "batteryUpdate":
                print("Processing background battery update")
                if let batteryLevel = userInfo["batteryLevel"] as? Double,
                   let batteryState = userInfo["batteryState"] as? Int {
                    print("Background watch battery - Level: \(batteryLevel)%, State: \(batteryState)")
                    // Store battery info for Flutter to access
                    UserDefaults.standard.set(batteryLevel, forKey: "watch_battery_level")
                    UserDefaults.standard.set(batteryState, forKey: "watch_battery_state")
                    UserDefaults.standard.set(Date(), forKey: "watch_battery_last_updated")
                    
                    // Forward to Flutter
                    DispatchQueue.main.async {
                        self.flutterWatchAPI?.onWatchBatteryUpdate(batteryLevel: batteryLevel, batteryState: Int64(batteryState)) { result in
                            switch result {
                            case .success(_):
                                print("iOS: Background battery update sent to Flutter - Success")
                            case .failure(let error):
                                print("iOS: Background battery update sent to Flutter - Error: \(error.message)")
                            }
                        }
                    }
                }
            case "watchInfoUpdate":
                print("Processing background watch info update")
                if let name = userInfo["name"] as? String,
                   let model = userInfo["model"] as? String,
                   let systemVersion = userInfo["systemVersion"] as? String,
                   let localizedModel = userInfo["localizedModel"] as? String {
                    print("Background watch info - Name: \(name), Model: \(model), System: \(systemVersion)")
                    // Store watch info for Flutter to access
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
