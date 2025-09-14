import UIKit
import Flutter
import UserNotifications
import app_links
import WatchConnectivity


extension FlutterError: Error {}


private class WatchCounterHostApiImpl: WatchCounterHostAPI {
    let session: WCSession

    init(session: WCSession = .default) {
        self.session = session
    }


    func increment() {
        session.sendMessage(["method": "increment"], replyHandler: nil, errorHandler: nil)
    }

    func decrement() {
        session.sendMessage(["method": "decrement"], replyHandler: nil, errorHandler: nil)
    }

    func startRecording() {
        session.sendMessage(["method": "startRecording"], replyHandler: nil, errorHandler: nil)
    }

    func stopRecording() {
        session.sendMessage(["method": "stopRecording"], replyHandler: nil, errorHandler: nil)
    }

    func sendAudioData(audioData: FlutterStandardTypedData) {
        let data = audioData.data as Data
        session.sendMessage(["method": "sendAudioData", "audioData": data], replyHandler: nil, errorHandler: nil)
    }

    func sendAudioChunk(audioChunk: FlutterStandardTypedData, chunkIndex: Int64, isLast: Bool, sampleRate: Double) {
        let data = audioChunk.data as Data
        session.sendMessage([
            "method": "sendAudioChunk",
            "audioChunk": data,
            "chunkIndex": chunkIndex,
            "isLast": isLast,
            "sampleRate": sampleRate
        ], replyHandler: nil, errorHandler: nil)
    }
}

@main
@objc class AppDelegate: FlutterAppDelegate {
  private var methodChannel: FlutterMethodChannel?
  private var appleRemindersChannel: FlutterMethodChannel?
  private let appleRemindersService = AppleRemindersService()

  private var notificationTitleOnKill: String?
  private var notificationBodyOnKill: String?

  var session: WCSession?
  var flutterWatchAPI: WatchCounterFlutterAPI?
  private var audioChunks: [Int: (Data, Double)] = [:] // (audioData, sampleRate)
  private var nextExpectedChunkIndex: Int = 0

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
          let api: WatchCounterHostAPI = WatchCounterHostApiImpl(session: session!)

          WatchCounterHostAPISetup.setUp(binaryMessenger: controller!.binaryMessenger, api: api)
          flutterWatchAPI = WatchCounterFlutterAPI(binaryMessenger: controller!.binaryMessenger)
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
    
    // Receive a message from watch
    func session(_ session: WCSession, didReceiveMessage message: [String : Any]) {
        Task {
            guard let method = message["method"] as? String else {
                return
            }

            switch method {
            case "increment":
                self.flutterWatchAPI?.increment() { result in
                    switch result {
                    case .success(_):
                        print("Increment on Flutter - Success")
                    case .failure(let error):
                        print("Increment on Flutter - Error: \(error.message)")
                    }
                }
            case "decrement":
                self.flutterWatchAPI?.decrement() { result in
                    switch result {
                    case .success(_):
                        print("Decrement on Flutter - Success")
                    case .failure(let error):
                        print("Decrement on Flutter - Error: \(error.message)")
                    }
                }
            case "startRecording":
                self.flutterWatchAPI?.onRecordingStarted() { result in
                    switch result {
                    case .success(_):
                        print("Recording started on Flutter - Success")
                    case .failure(let error):
                        print("Recording started on Flutter - Error: \(error.message)")
                    }
                }
            case "stopRecording":
                self.flutterWatchAPI?.onRecordingStopped() { result in
                    switch result {
                    case .success(_):
                        print("Recording stopped on Flutter - Success")
                    case .failure(let error):
                        print("Recording stopped on Flutter - Error: \(error.message)")
                    }
                }
            case "sendAudioData":
                print("Received sendAudioData message from watch")
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
                print("Received sendAudioChunk message from watch")
                self.handleAudioChunk(message)
            default:
                print("Unknown method: \(method)")
            }
        }
    }
}
