import Flutter
import UIKit
import AVFoundation
import TwilioVoice

/// Flutter plugin for phone call functionality via Twilio Voice SDK.
/// Delegates CallKit lifecycle to OmiCallCoordinator. Audio session uses 20ms buffers.
class OmiPhoneCallsPlugin: NSObject, FlutterPlugin {
    private var methodChannel: FlutterMethodChannel?
    private var eventChannel: FlutterEventChannel?
    private var eventSink: FlutterEventSink?

    // Twilio Voice
    private var accessToken: String?
    private var activeCall: Call?
    private var callDelegate: TwilioCallDelegateHandler?
    private var currentCallId: String?
    private var isMuted: Bool = false
    private var isSpeakerOn: Bool = false
    private var audioDevice = OmiRecordingAudioDevice()

    // Call coordinator (manages CallKit or direct audio, swappable via protocol)
    fileprivate let callCoordinator: OmiCallCoordinatorProtocol
    fileprivate var callUUID: UUID?

    // Proximity sensor — screen off when phone held to ear
    fileprivate let proximitySensor = OmiProximitySensor()

    override init() {
        // Select coordinator based on region
        if OmiRegionCheck.isCallKitRestricted {
            callCoordinator = OmiDirectCallCoordinator()
            print("OmiPhoneCallsPlugin: using DirectCallCoordinator (CallKit restricted)")
        } else {
            callCoordinator = OmiCallCoordinator()
            print("OmiPhoneCallsPlugin: using CallKitCoordinator")
        }
        super.init()

        // Wire coordinator callbacks
        callCoordinator.onAudioSessionActivated = { [weak self] in
            print("OmiPhoneCallsPlugin: audio session activated, starting audio device")
            _ = self?.audioDevice.start()
        }
        callCoordinator.onAudioSessionDeactivated = {
            print("OmiPhoneCallsPlugin: audio session deactivated")
        }
        callCoordinator.onSystemEndCall = { [weak self] in
            guard let self = self, self.activeCall != nil else { return }
            self.activeCall?.disconnect()
            self.sendCallStateEvent("ended")
            self.cleanup()
        }
        callCoordinator.onSystemToggleMute = { [weak self] muted in
            guard let self = self else { return }
            self.isMuted = muted
            self.activeCall?.isMuted = muted
            self.audioDevice.isMicStreamMuted = muted
            self.sendEvent(["type": "muteConfirmed", "muted": muted])
        }
        callCoordinator.onProviderReset = { [weak self] in
            guard let self = self, self.activeCall != nil else { return }
            print("OmiPhoneCallsPlugin: provider reset, disconnecting active call")
            self.activeCall?.disconnect()
            self.sendCallStateEvent("failed")
            self.sendErrorEvent(.callkitRejected("Call system was reset"))
            self.cleanup()
        }

        // Wire up audio data callback to stream to Flutter
        audioDevice.onAudioData = { [weak self] data, channel in
            self?.sendAudioDataEvent(data, channel: channel)
        }

        // Set Twilio's audio device (custom device captures both streams)
        TwilioVoiceSDK.audioDevice = audioDevice
    }

    static func register(with registrar: FlutterPluginRegistrar) {
        let instance = OmiPhoneCallsPlugin()

        instance.methodChannel = FlutterMethodChannel(
            name: "com.omi/phone_calls",
            binaryMessenger: registrar.messenger()
        )
        registrar.addMethodCallDelegate(instance, channel: instance.methodChannel!)

        instance.eventChannel = FlutterEventChannel(
            name: "com.omi/phone_calls/events",
            binaryMessenger: registrar.messenger()
        )
        instance.eventChannel?.setStreamHandler(instance)
    }

    func handle(_ call: FlutterMethodCall, result: @escaping FlutterResult) {
        switch call.method {
        case "initialize":
            handleInitialize(call, result: result)
        case "makeCall":
            handleMakeCall(call, result: result)
        case "endCall":
            handleEndCall(result: result)
        case "toggleMute":
            handleToggleMute(call, result: result)
        case "toggleSpeaker":
            handleToggleSpeaker(call, result: result)
        case "sendDtmf":
            handleSendDtmf(call, result: result)
        case "getAudioRoutes":
            handleGetAudioRoutes(result: result)
        case "selectAudioRoute":
            handleSelectAudioRoute(call, result: result)
        case "isCallKitAvailable":
            result(!OmiRegionCheck.isCallKitRestricted)
        default:
            result(FlutterMethodNotImplemented)
        }
    }

    // MARK: - Method Handlers

    private func handleInitialize(_ call: FlutterMethodCall, result: @escaping FlutterResult) {
        guard let args = call.arguments as? [String: Any],
              let token = args["accessToken"] as? String else {
            result(FlutterError(code: "INVALID_ARGS", message: "Missing accessToken", details: nil))
            return
        }

        accessToken = token

        print("OmiPhoneCallsPlugin: initialized with token (length=\(token.count))")
        result(true)
    }

    private func handleMakeCall(_ call: FlutterMethodCall, result: @escaping FlutterResult) {
        guard let args = call.arguments as? [String: Any],
              let phoneNumber = args["phoneNumber"] as? String,
              let callId = args["callId"] as? String else {
            result(FlutterError(code: "INVALID_ARGS", message: "Missing phoneNumber or callId", details: nil))
            return
        }

        guard let token = accessToken else {
            result(FlutterError(code: "NOT_INITIALIZED", message: "Call initialize first", details: nil))
            return
        }

        let contactName = args["contactName"] as? String
        currentCallId = callId

        let uuid = UUID()
        callUUID = uuid

        print("OmiPhoneCallsPlugin: requesting start call for \(phoneNumber)")

        callCoordinator.startCall(uuid: uuid, phoneNumber: phoneNumber, contactName: contactName) { [weak self] coordinatorResult in
            guard let self = self else { return }

            switch coordinatorResult {
            case .failure(let error):
                print("OmiPhoneCallsPlugin: coordinator start call failed: \(error.localizedDescription)")
                self.sendErrorEvent(.callkitRejected(error.localizedDescription))
                self.sendCallStateEvent("failed")
                DispatchQueue.main.async { result(false) }

            case .success:
                print("OmiPhoneCallsPlugin: coordinator approved, connecting Twilio")
                self.sendCallStateEvent("connecting")

                // Connect via Twilio Voice SDK on main thread
                DispatchQueue.main.async {
                    let delegate = TwilioCallDelegateHandler(plugin: self)
                    self.callDelegate = delegate

                    let connectOptions = ConnectOptions(accessToken: token) { builder in
                        builder.params = ["To": phoneNumber, "CallId": callId]
                        builder.uuid = uuid
                    }

                    print("OmiPhoneCallsPlugin: connecting via Twilio SDK...")
                    self.activeCall = TwilioVoiceSDK.connect(options: connectOptions, delegate: delegate)

                    if self.activeCall != nil {
                        print("OmiPhoneCallsPlugin: Twilio connect returned call object")
                        result(true)
                    } else {
                        print("OmiPhoneCallsPlugin: Twilio connect returned nil")
                        self.sendErrorEvent(.twilioError(code: -1, message: "Connect returned nil"))
                        self.sendCallStateEvent("failed")
                        result(false)
                    }
                }
            }
        }
    }

    private func handleEndCall(result: @escaping FlutterResult) {
        print("OmiPhoneCallsPlugin: ending call")

        // Disconnect Twilio first
        activeCall?.disconnect()

        // End via coordinator
        if let uuid = callUUID {
            callCoordinator.endCall(uuid: uuid) { endResult in
                if case .failure(let error) = endResult {
                    print("OmiPhoneCallsPlugin: coordinator end call error: \(error)")
                }
            }
        }

        sendCallStateEvent("ended")
        cleanup()
        result(nil)
    }

    private func handleToggleMute(_ call: FlutterMethodCall, result: @escaping FlutterResult) {
        guard let args = call.arguments as? [String: Any],
              let muted = args["muted"] as? Bool else {
            result(nil)
            return
        }
        isMuted = muted
        activeCall?.isMuted = muted
        audioDevice.isMicStreamMuted = muted

        // Confirm state change to Dart
        sendEvent(["type": "muteConfirmed", "muted": muted])
        result(nil)
    }

    private func handleToggleSpeaker(_ call: FlutterMethodCall, result: @escaping FlutterResult) {
        guard let args = call.arguments as? [String: Any],
              let speakerOn = args["speakerOn"] as? Bool else {
            result(nil)
            return
        }

        do {
            let session = AVAudioSession.sharedInstance()
            if speakerOn {
                try session.overrideOutputAudioPort(.speaker)
            } else {
                try session.overrideOutputAudioPort(.none)
            }
            isSpeakerOn = speakerOn
            sendEvent(["type": "speakerConfirmed", "speakerOn": speakerOn])
        } catch {
            print("OmiPhoneCallsPlugin: speaker toggle error: \(error)")
            sendErrorEvent(.audioSessionFailed(error.localizedDescription))
        }

        result(nil)
    }

    private func handleSendDtmf(_ call: FlutterMethodCall, result: @escaping FlutterResult) {
        guard let args = call.arguments as? [String: Any],
              let digits = args["digits"] as? String else {
            result(nil)
            return
        }
        activeCall?.sendDigits(digits)
        result(nil)
    }

    // MARK: - Audio Routes

    private func handleGetAudioRoutes(result: @escaping FlutterResult) {
        let session = AVAudioSession.sharedInstance()
        var routes: [[String: String]] = []

        // Always include iPhone earpiece and Speaker
        routes.append(["id": "iPhone", "name": "iPhone", "type": "iPhone"])
        routes.append(["id": "speaker", "name": "Speaker", "type": "speaker"])

        // Add available Bluetooth/wired inputs
        if let inputs = session.availableInputs {
            for input in inputs {
                let routeType: String
                switch input.portType {
                case .bluetoothHFP, .bluetoothLE:
                    routeType = "bluetoothHeadset"
                case .bluetoothA2DP:
                    // AirPods show up as bluetoothA2DP or bluetoothHFP
                    let name = input.portName.lowercased()
                    routeType = name.contains("airpod") ? "airPods" : "bluetoothHeadset"
                case .headphones, .headsetMic:
                    routeType = "headphones"
                default:
                    continue
                }
                routes.append([
                    "id": input.uid,
                    "name": input.portName,
                    "type": routeType,
                ])
            }
        }

        result(routes)
    }

    private func handleSelectAudioRoute(_ call: FlutterMethodCall, result: @escaping FlutterResult) {
        guard let args = call.arguments as? [String: Any],
              let routeId = args["routeId"] as? String else {
            result(nil)
            return
        }

        do {
            let session = AVAudioSession.sharedInstance()
            if routeId == "speaker" {
                try session.overrideOutputAudioPort(.speaker)
                isSpeakerOn = true
            } else if routeId == "iPhone" {
                try session.overrideOutputAudioPort(.none)
                try session.setPreferredInput(nil)
                isSpeakerOn = false
            } else {
                // Bluetooth / wired device — find by UID
                try session.overrideOutputAudioPort(.none)
                if let inputs = session.availableInputs,
                   let target = inputs.first(where: { $0.uid == routeId }) {
                    try session.setPreferredInput(target)
                }
                isSpeakerOn = false
            }
            result(true)
        } catch {
            print("OmiPhoneCallsPlugin: selectAudioRoute error: \(error)")
            sendErrorEvent(.audioSessionFailed(error.localizedDescription))
            result(false)
        }
    }

    // MARK: - Cleanup

    fileprivate func cleanup() {
        activeCall = nil
        callDelegate = nil
        callUUID = nil
        currentCallId = nil
        proximitySensor.disable()
    }

    // MARK: - Event Sending

    func sendCallStateEvent(_ state: String) {
        sendEvent(["type": "callStateChanged", "state": state])
    }

    func sendErrorEvent(_ error: OmiCallError) {
        sendEvent(error.toEventData())
    }

    func sendAudioDataEvent(_ data: Data, channel: Int) {
        DispatchQueue.main.async { [weak self] in
            self?.eventSink?([
                "type": "audioData",
                "data": FlutterStandardTypedData(bytes: data),
                "channel": channel,
            ])
        }
    }

    private func sendEvent(_ event: [String: Any]) {
        DispatchQueue.main.async { [weak self] in
            self?.eventSink?(event)
        }
    }
}

// MARK: - FlutterStreamHandler

extension OmiPhoneCallsPlugin: FlutterStreamHandler {
    func onListen(withArguments arguments: Any?, eventSink events: @escaping FlutterEventSink) -> FlutterError? {
        eventSink = events
        return nil
    }

    func onCancel(withArguments arguments: Any?) -> FlutterError? {
        eventSink = nil
        return nil
    }
}

// MARK: - Twilio Call Delegate

private class TwilioCallDelegateHandler: NSObject, CallDelegate {
    private weak var plugin: OmiPhoneCallsPlugin?

    init(plugin: OmiPhoneCallsPlugin) {
        self.plugin = plugin
        super.init()
    }

    func callDidStartRinging(call: Call) {
        print("OmiPhoneCallsPlugin: call ringing (sid: \(call.sid))")
        plugin?.proximitySensor.enable()
        plugin?.sendCallStateEvent("ringing")
    }

    func callDidConnect(call: Call) {
        print("OmiPhoneCallsPlugin: call connected (sid: \(call.sid))")
        if let uuid = plugin?.callUUID {
            plugin?.callCoordinator.reportCallConnected(uuid: uuid)
        }
        plugin?.sendCallStateEvent("active")
    }

    func callDidDisconnect(call: Call, error: Error?) {
        if let error = error {
            print("OmiPhoneCallsPlugin: call disconnected with error: \(error.localizedDescription)")
            plugin?.sendErrorEvent(.twilioError(code: (error as NSError).code, message: error.localizedDescription))
            plugin?.sendCallStateEvent("failed")
        } else {
            print("OmiPhoneCallsPlugin: call disconnected normally")
            plugin?.sendCallStateEvent("ended")
        }

        if let uuid = plugin?.callUUID {
            plugin?.callCoordinator.reportCallEnded(uuid: uuid, failed: error != nil)
        }

        plugin?.cleanup()
    }

    func callDidFailToConnect(call: Call, error: Error) {
        print("OmiPhoneCallsPlugin: call failed to connect: \(error.localizedDescription)")
        plugin?.sendErrorEvent(.twilioError(code: (error as NSError).code, message: error.localizedDescription))
        plugin?.sendCallStateEvent("failed")

        if let uuid = plugin?.callUUID {
            plugin?.callCoordinator.reportCallEnded(uuid: uuid, failed: true)
        }

        plugin?.cleanup()
    }
}
