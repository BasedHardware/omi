// speech-helper — speaks text via AVSpeechSynthesizer and reports events on
// stdout as line-delimited JSON.
//
// Communication protocol (stdin → stdout):
//   stdin  — one JSON command per line:
//     {"action":"speak","id":"<request-id>","text":"<string>","voice":"<voice-id>","rate":<0..1>}
//     {"action":"stop"}
//     {"action":"voices"}
//     Any other action  → emits {"event":"error","message":"unknown action: ..."}
//
//   stdout — one JSON event per line:
//     {"event":"didStart",  "id":"<request-id>"}
//     {"event":"willSpeakRange","id":"<request-id>","range":{"location":N,"length":M}}
//     {"event":"didFinish", "id":"<request-id>"}
//     {"event":"didCancel", "id":"<request-id>"}
//     {"event":"voices",    "voices":[{"id":...,"name":...,"lang":...,"quality":...}]}
//     {"event":"error",     "id":"<request-id>","message":"..."}
//
// Modelled after swift-helpers/sys-audio-capture/main.swift (same sidecar
// pattern: stdin/stdout JSON, RunLoop.main.run() for delegate callbacks).

import AVFoundation
import Foundation

// MARK: - Logging

func log(_ msg: String) {
    FileHandle.standardError.write("[speech-helper] \(msg)\n".data(using: .utf8)!)
}

// MARK: - Stdout write helper

private let stdoutHandle = FileHandle.standardOutput

func emitEvent(_ dict: [String: Any]) {
    guard let data = try? JSONSerialization.data(withJSONObject: dict, options: [.sortedKeys]) else {
        log("WARN: failed to serialize event: \(dict)")
        return
    }
    var line = data
    line.append(contentsOf: "\n".utf8)
    stdoutHandle.write(line)
}

// MARK: - Synthesizer delegate

final class SpeechDelegate: NSObject, AVSpeechSynthesizerDelegate {
    var currentId: String = ""

    func speechSynthesizer(_ synthesizer: AVSpeechSynthesizer, didStart utterance: AVSpeechUtterance) {
        emitEvent(["event": "didStart", "id": currentId])
    }

    func speechSynthesizer(
        _ synthesizer: AVSpeechSynthesizer,
        willSpeakRangeOfSpeechString characterRange: NSRange,
        utterance: AVSpeechUtterance
    ) {
        emitEvent([
            "event": "willSpeakRange",
            "id": currentId,
            "range": ["location": characterRange.location, "length": characterRange.length],
        ])
    }

    func speechSynthesizer(_ synthesizer: AVSpeechSynthesizer, didFinish utterance: AVSpeechUtterance) {
        emitEvent(["event": "didFinish", "id": currentId])
    }

    func speechSynthesizer(_ synthesizer: AVSpeechSynthesizer, didCancel utterance: AVSpeechUtterance) {
        emitEvent(["event": "didCancel", "id": currentId])
    }
}

// MARK: - Command processor

let delegate = SpeechDelegate()
let synthesizer: AVSpeechSynthesizer = {
    let s = AVSpeechSynthesizer()
    s.delegate = delegate
    return s
}()

func processCommand(_ dict: [String: Any]) {
    guard let action = dict["action"] as? String else {
        emitEvent(["event": "error", "id": dict["id"] as? String ?? "", "message": "missing 'action' key"])
        return
    }

    switch action {
    case "speak":
        let requestId = dict["id"] as? String ?? ""
        let text = dict["text"] as? String ?? ""
        let voiceId = dict["voice"] as? String
        let rate = dict["rate"] as? Double

        // Interrupt any in-flight speech immediately.
        if synthesizer.isSpeaking {
            synthesizer.stopSpeaking(at: .immediate)
        }

        delegate.currentId = requestId

        let utterance = AVSpeechUtterance(string: text)
        utterance.rate = Float(rate ?? Double(AVSpeechUtteranceDefaultSpeechRate))

        if let voiceId = voiceId, let voice = AVSpeechSynthesisVoice(identifier: voiceId) {
            utterance.voice = voice
        }
        // If voiceId is nil or not found, AVSpeechSynthesizer picks the system default.

        synthesizer.speak(utterance)

    case "stop":
        if synthesizer.isSpeaking {
            synthesizer.stopSpeaking(at: .immediate)
        }
        // No event emitted — didCancel fires via the delegate if something was playing.

    case "voices":
        let voices: [[String: Any]] = AVSpeechSynthesisVoice.speechVoices().map { voice in
            var quality: String
            switch voice.quality {
            case .enhanced: quality = "enhanced"
            case .premium: quality = "premium"
            default: quality = "default"
            }
            return [
                "id": voice.identifier,
                "name": voice.name,
                "lang": voice.language,
                "quality": quality,
            ]
        }
        emitEvent(["event": "voices", "voices": voices])

    default:
        let requestId = dict["id"] as? String ?? ""
        emitEvent(["event": "error", "id": requestId, "message": "unknown action: \(action)"])
    }
}

// MARK: - Stdin reader task

// We read stdin on a background thread so we don't block the RunLoop that
// AVSpeechSynthesizer delegates dispatch onto.
DispatchQueue.global(qos: .userInitiated).async {
    let stdinHandle = FileHandle.standardInput
    var lineBuffer = Data()

    while true {
        // Read one byte at a time — simple and correct; speech-helper is not
        // hot-path so the syscall overhead is irrelevant.
        let byte = stdinHandle.readData(ofLength: 1)
        if byte.isEmpty {
            // EOF — parent process closed stdin; exit cleanly.
            log("stdin EOF — exiting")
            exit(0)
        }

        if byte.first == UInt8(ascii: "\n") {
            if !lineBuffer.isEmpty {
                let line = lineBuffer
                lineBuffer = Data()

                guard let jsonObj = try? JSONSerialization.jsonObject(with: line) as? [String: Any] else {
                    log("WARN: could not parse JSON line: \(String(data: line, encoding: .utf8) ?? "(non-utf8)")")
                    continue
                }

                // Dispatch onto main thread so the delegate callback and the
                // synthesizer API are both called from the same thread (required
                // by AVSpeechSynthesizer).
                DispatchQueue.main.async {
                    processCommand(jsonObj)
                }
            }
        } else {
            lineBuffer.append(byte)
        }
    }
}

// MARK: - Entry point

log("speech-helper started")
signal(SIGTERM) { _ in exit(0) }
signal(SIGINT, SIG_IGN)
signal(SIGPIPE, SIG_IGN)

RunLoop.main.run()
