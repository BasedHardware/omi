import Speech
import Flutter

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
