import UIKit
import Flutter
import UserNotifications
import app_links
import Speech

@main
@objc class AppDelegate: FlutterAppDelegate, SFSpeechRecognizerDelegate {
  private var methodChannel: FlutterMethodChannel?
  private var notificationTitleOnKill: String?
  private var notificationBodyOnKill: String?

  var speechRecognizer: SFSpeechRecognizer?
  var recognitionRequest: SFSpeechAudioBufferRecognitionRequest?
  var recognitionTask: SFSpeechRecognitionTask?
  let audioEngine = AVAudioEngine()
  private var transcriptionEventSink: FlutterEventSink?

  override func application(
    _ application: UIApplication,
    didFinishLaunchingWithOptions launchOptions: [UIApplication.LaunchOptionsKey: Any]?
  ) -> Bool {
    GeneratedPluginRegistrant.register(with: self)

      // Retrieve the link from parameters
    if let url = AppLinks.shared.getLink(launchOptions: launchOptions) {
      // We have a link, propagate it to your Flutter app or not
      AppLinks.shared.handleLink(url: url)
      return true // Returning true will stop the propagation to other packages
    }
    //Creates a method channel to handle notifications on kill
    let controller = window?.rootViewController as! FlutterViewController
    methodChannel = FlutterMethodChannel(name: "com.friend.ios/notifyOnKill", binaryMessenger: controller.binaryMessenger)
    methodChannel?.setMethodCallHandler { [weak self] (call, result) in
      self?.handleMethodCall(call, result: result)
    }

    // New local transcription channel with language parameter support.
    let localTranscriptionMethodChannel = FlutterMethodChannel(name: "local_speech_channel", binaryMessenger: controller.binaryMessenger)
    localTranscriptionMethodChannel.setMethodCallHandler { [weak self] (call, result) in
      guard let self = self else { return }
      if call.method == "startTranscription" {
        // Extract language parameter from call arguments. Default to "en-US" if none provided.
        var language = "en-US"
        if let args = call.arguments as? [String: Any], let lang = args["language"] as? String {
          language = lang
        }
        self.startSpeechRecognition(with: language)
        result("Transcription Started for language: \(language)")
      } else if call.method == "stopTranscription" {
        self.stopSpeechRecognition()
        result("Transcription Stopped")
      } else {
        result(FlutterMethodNotImplemented)
      }
    }

    // Set up event channel to stream transcription events back to Flutter
    let localTranscriptionEventChannel = FlutterEventChannel(name: "local_speech_events", binaryMessenger: controller.binaryMessenger)
    localTranscriptionEventChannel.setStreamHandler(self)

    // Request authorization for speech recognition
    SFSpeechRecognizer.requestAuthorization { authStatus in
      if authStatus != .authorized {
        NSLog("Speech recognition not authorized")
      }
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

    if let args = call.arguments as? [String: Any] {
      notificationTitleOnKill = args["title"] as? String
      notificationBodyOnKill = args["description"] as? String
    }
  }

  override func applicationWillTerminate(_ application: UIApplication) {
    // If title and body are nil, then we don't need to show notification.
    if notificationTitleOnKill == nil || notificationBodyOnKill == nil { return }

    let content = UNMutableNotificationContent()
    content.title = notificationTitleOnKill!
    content.body = notificationBodyOnKill!
    let trigger = UNTimeIntervalNotificationTrigger(timeInterval: 1, repeats: false)
    let request = UNNotificationRequest(identifier: "notification on app kill", content: content, trigger: trigger)

    NSLog("Running applicationWillTerminate")
    UNUserNotificationCenter.current().add(request) { error in
      if let error = error {
        NSLog("Failed to show notification on kill service => error: \(error.localizedDescription)")
      } else {
        NSLog("Show notification on kill now")
      }
    }
  }

  func startSpeechRecognition(with language: String) {
    // Cancel any existing task
    if recognitionTask != nil {
      recognitionTask?.cancel()
      recognitionTask = nil
    }

    let audioSession = AVAudioSession.sharedInstance()
    do {
      try audioSession.setCategory(.record, mode: .measurement, options: .duckOthers)
      try audioSession.setActive(true, options: .notifyOthersOnDeactivation)
    } catch {
      transcriptionEventSink?("Audio session error: \(error.localizedDescription)")
      return
    }

    recognitionRequest = SFSpeechAudioBufferRecognitionRequest()
    guard let recognitionRequest = recognitionRequest else {
      transcriptionEventSink?("Unable to create a recognition request")
      return
    }
    recognitionRequest.shouldReportPartialResults = true

    // Create the recognizer with the provided language identifier.
    speechRecognizer = SFSpeechRecognizer(locale: Locale(identifier: language))
    guard let recognizer = speechRecognizer, recognizer.isAvailable else {
      transcriptionEventSink?("Speech recognizer for language \(language) is not available")
      return
    }

    recognitionTask = recognizer.recognitionTask(with: recognitionRequest) { [weak self] (result, error) in
      guard let self = self else { return }
      if let result = result {
        let transcription = result.bestTranscription.formattedString
        self.transcriptionEventSink?(transcription)
      }
      if error != nil || (result?.isFinal ?? false) {
        self.audioEngine.stop()
        self.audioEngine.inputNode.removeTap(onBus: 0)
        self.recognitionRequest = nil
        self.recognitionTask = nil
      }
    }

    let recordingFormat = audioEngine.inputNode.outputFormat(forBus: 0)
    audioEngine.inputNode.installTap(onBus: 0, bufferSize: 1024, format: recordingFormat) { [weak self] (buffer, when) in
      self?.recognitionRequest?.append(buffer)
    }
    audioEngine.prepare()
    do {
      try audioEngine.start()
    } catch {
      transcriptionEventSink?("Audio engine couldn't start: \(error.localizedDescription)")
    }
  }

  func stopSpeechRecognition() {
    if audioEngine.isRunning {
      audioEngine.stop()
      recognitionRequest?.endAudio()
    }
  }
}

// MARK: - FlutterStreamHandler for Local Transcription Event Channel

extension AppDelegate: FlutterStreamHandler {
  func onListen(withArguments arguments: Any?, eventSink events: @escaping FlutterEventSink) -> FlutterError? {
    transcriptionEventSink = events
    return nil
  }

  func onCancel(withArguments arguments: Any?) -> FlutterError? {
    transcriptionEventSink = nil
    return nil
  }
}
