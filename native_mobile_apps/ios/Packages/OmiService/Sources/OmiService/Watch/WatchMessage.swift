import Foundation

// The WatchConnectivity contract between the iPhone app and the Omi watch app. Same dictionary keys
// and values as the Flutter app (`ios/Runner/AppDelegate.swift`, `ios/omiWatchApp`), so either
// side keeps working with the other. Compiled into OmiService and, as a plain source file, into the
// watch target: Foundation only.

/// 1.5 s of 16 kHz mono PCM16 from the watch microphone; the last one of a recording is empty.
public struct WatchAudioChunk: Equatable, Sendable {
    public var data: Data
    public var index: Int
    public var isLast: Bool
    public var sampleRate: Double

    public init(data: Data, index: Int, isLast: Bool, sampleRate: Double = WatchAudioChunk.sampleRate) {
        self.data = data
        self.index = index
        self.isLast = isLast
        self.sampleRate = sampleRate
    }

    public static let sampleRate: Double = 16000
    /// 1.5 s of PCM16 at 16 kHz, small enough for one `sendMessage` (64 KB limit).
    public static let bytesPerChunk = 48000
}

public struct WatchInfo: Equatable, Sendable {
    public var name: String
    public var model: String
    public var systemVersion: String
    public var localizedModel: String

    public init(name: String, model: String, systemVersion: String, localizedModel: String) {
        self.name = name
        self.model = model
        self.systemVersion = systemVersion
        self.localizedModel = localizedModel
    }
}

/// Why the iPhone ended (or refused) a watch recording; shown on the watch. Native addition.
public enum WatchStopReason: String, Equatable, Sendable {
    /// Something else (the iPhone mic, the Omi) is already recording.
    case busy
    /// Nobody is signed in to Omi on the iPhone.
    case signedOut
    /// The iPhone could not open the live transcription.
    case failed
}

/// What the iPhone is doing, as the watch shows it (application context; native addition).
public struct WatchPhoneState: Equatable, Sendable {
    public enum Capture: String, Equatable, Sendable { case idle, watch, phone, omi }

    public var capture: Capture
    /// The Omi wearable's battery while it is connected to the iPhone.
    public var omiBattery: Int?

    public init(capture: Capture, omiBattery: Int?) {
        self.capture = capture
        self.omiBattery = omiBattery
    }

    public var payload: [String: Any] {
        var payload: [String: Any] = ["method": "phoneState", "capture": capture.rawValue]
        if let omiBattery { payload["omiBattery"] = omiBattery }
        return payload
    }

    public init?(payload: [String: Any]) {
        guard payload["method"] as? String == "phoneState",
              let capture = (payload["capture"] as? String).flatMap(Capture.init(rawValue:)) else { return nil }
        self.capture = capture
        omiBattery = WatchMessage.number(payload["omiBattery"]).map { Int($0) }
    }
}

/// One WatchConnectivity message. `startRecording`/`stopRecording` travel both ways: from the
/// watch they report what it did, from the iPhone they ask the watch to do it.
public enum WatchMessage: Equatable, Sendable {
    case startRecording
    case stopRecording(reason: WatchStopReason?)
    case audioChunk(WatchAudioChunk)
    case recordingError(String)
    case requestMicrophonePermission
    case microphonePermissionResult(granted: Bool)
    case requestBattery
    /// Watch battery, 0–100, and `WKInterfaceDeviceBatteryState.rawValue`.
    case batteryUpdate(level: Double, state: Int)
    case requestWatchInfo
    case watchInfoUpdate(WatchInfo)

    public var payload: [String: Any] {
        switch self {
        case .startRecording: return ["method": "startRecording"]
        case let .stopRecording(reason):
            var payload: [String: Any] = ["method": "stopRecording"]
            if let reason { payload["reason"] = reason.rawValue }
            return payload
        case let .audioChunk(chunk):
            return ["method": "sendAudioChunk", "audioChunk": chunk.data, "chunkIndex": chunk.index,
                    "isLast": chunk.isLast, "sampleRate": chunk.sampleRate]
        case let .recordingError(error): return ["method": "recordingError", "error": error]
        case .requestMicrophonePermission: return ["method": "requestMicrophonePermission"]
        case let .microphonePermissionResult(granted): return ["method": "microphonePermissionResult", "granted": granted]
        case .requestBattery: return ["method": "requestBattery"]
        case let .batteryUpdate(level, state): return ["method": "batteryUpdate", "batteryLevel": level, "batteryState": state]
        case .requestWatchInfo: return ["method": "requestWatchInfo"]
        case let .watchInfoUpdate(info):
            return ["method": "watchInfoUpdate", "name": info.name, "model": info.model,
                    "systemVersion": info.systemVersion, "localizedModel": info.localizedModel]
        }
    }

    /// Nil for an unknown method or a payload missing a required field.
    public init?(payload: [String: Any]) {
        guard let method = payload["method"] as? String else { return nil }
        switch method {
        case "startRecording": self = .startRecording
        case "stopRecording": self = .stopRecording(reason: (payload["reason"] as? String).flatMap(WatchStopReason.init(rawValue:)))
        case "sendAudioChunk":
            guard let data = payload["audioChunk"] as? Data,
                  let index = Self.number(payload["chunkIndex"]) else { return nil }
            self = .audioChunk(WatchAudioChunk(
                data: data, index: Int(index), isLast: payload["isLast"] as? Bool ?? false,
                sampleRate: Self.number(payload["sampleRate"]) ?? WatchAudioChunk.sampleRate
            ))
        case "recordingError": self = .recordingError(payload["error"] as? String ?? "")
        case "requestMicrophonePermission": self = .requestMicrophonePermission
        case "microphonePermissionResult":
            guard let granted = payload["granted"] as? Bool else { return nil }
            self = .microphonePermissionResult(granted: granted)
        case "requestBattery": self = .requestBattery
        case "batteryUpdate":
            guard let level = Self.number(payload["batteryLevel"]) else { return nil }
            self = .batteryUpdate(level: level, state: Self.number(payload["batteryState"]).map { Int($0) } ?? 0)
        case "requestWatchInfo": self = .requestWatchInfo
        case "watchInfoUpdate":
            guard let name = payload["name"] as? String else { return nil }
            self = .watchInfoUpdate(WatchInfo(
                name: name, model: payload["model"] as? String ?? "",
                systemVersion: payload["systemVersion"] as? String ?? "",
                localizedModel: payload["localizedModel"] as? String ?? ""
            ))
        default: return nil
        }
    }

    /// WatchConnectivity hands numbers over as NSNumber; the watch sends its battery as a Float.
    static func number(_ value: Any?) -> Double? {
        switch value {
        case let value as Double: value
        case let value as Float: Double(value)
        case let value as Int: Double(value)
        case let value as NSNumber: value.doubleValue
        default: nil
        }
    }
}
