import Flutter
import UIKit
import AVFoundation
import CallKit
import TwilioVoice

/// Flutter plugin for phone call functionality via Twilio Voice SDK.
/// ConnectOptions.uuid ties Twilio call to CallKit, audio session uses 20ms buffers.
class PhoneCallsPlugin: NSObject, FlutterPlugin {
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

    // CallKit
    fileprivate let callKitProvider: CXProvider
    private let callKitController = CXCallController()
    fileprivate var callKitUUID: UUID?

    // Pending call info (set before CallKit request, consumed after Twilio connect)
    private var pendingCallResult: FlutterResult?

    override init() {
        let configuration = CXProviderConfiguration()
        configuration.maximumCallGroups = 1
        configuration.maximumCallsPerCallGroup = 1
        configuration.supportsVideo = false
        configuration.supportedHandleTypes = [.phoneNumber]
        callKitProvider = CXProvider(configuration: configuration)
        super.init()
        callKitProvider.setDelegate(self, queue: nil)

        // Wire up audio data callback to stream to Flutter
        audioDevice.onAudioData = { [weak self] data, channel in
            self?.sendAudioDataEvent(data, channel: channel)
        }

        // Set Twilio's audio device (custom device captures both streams)
        TwilioVoiceSDK.audioDevice = audioDevice
    }

    static func register(with registrar: FlutterPluginRegistrar) {
        let instance = PhoneCallsPlugin()

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

        print("PhoneCallsPlugin: initialized with token (length=\(token.count))")
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

        // Step 1: Generate CallKit UUID
        let uuid = UUID()
        callKitUUID = uuid

        // Step 2: Report outgoing call to CallKit
        let handle = CXHandle(type: .phoneNumber, value: phoneNumber)
        let startCallAction = CXStartCallAction(call: uuid, handle: handle)
        startCallAction.isVideo = false
        startCallAction.contactIdentifier = contactName

        let transaction = CXTransaction(action: startCallAction)

        print("PhoneCallsPlugin: requesting CallKit start for \(phoneNumber)")

        callKitController.request(transaction) { [weak self] error in
            guard let self = self else { return }

            if let error = error {
                print("PhoneCallsPlugin: CallKit start error: \(error.localizedDescription)")
                self.sendCallStateEvent("failed")
                DispatchQueue.main.async { result(false) }
                return
            }

            print("PhoneCallsPlugin: CallKit approved, reporting connecting state")
            self.callKitProvider.reportOutgoingCall(with: uuid, startedConnectingAt: Date())
            self.sendCallStateEvent("connecting")

            // Step 3: Connect via Twilio Voice SDK on main thread
            // pass builder.uuid to tie Twilio call to CallKit call
            DispatchQueue.main.async {
                let delegate = TwilioCallDelegateHandler(plugin: self)
                self.callDelegate = delegate

                let connectOptions = ConnectOptions(accessToken: token) { builder in
                    builder.params = ["To": phoneNumber, "CallId": callId]
                    builder.uuid = uuid  // Ties Twilio call to CallKit UUID
                }

                print("PhoneCallsPlugin: connecting via Twilio SDK...")
                self.activeCall = TwilioVoiceSDK.connect(options: connectOptions, delegate: delegate)

                if self.activeCall != nil {
                    print("PhoneCallsPlugin: Twilio connect returned call object")
                    result(true)
                } else {
                    print("PhoneCallsPlugin: Twilio connect returned nil")
                    self.sendCallStateEvent("failed")
                    result(false)
                }
            }
        }
    }

    private func handleEndCall(result: @escaping FlutterResult) {
        print("PhoneCallsPlugin: ending call")

        // Disconnect the Twilio call
        activeCall?.disconnect()

        // End via CallKit
        if let uuid = callKitUUID {
            let endCallAction = CXEndCallAction(call: uuid)
            let transaction = CXTransaction(action: endCallAction)
            callKitController.request(transaction) { error in
                if let error = error {
                    print("PhoneCallsPlugin: CallKit end error: \(error)")
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
        result(nil)
    }

    private func handleToggleSpeaker(_ call: FlutterMethodCall, result: @escaping FlutterResult) {
        guard let args = call.arguments as? [String: Any],
              let speakerOn = args["speakerOn"] as? Bool else {
            result(nil)
            return
        }
        isSpeakerOn = speakerOn

        do {
            let session = AVAudioSession.sharedInstance()
            if speakerOn {
                try session.overrideOutputAudioPort(.speaker)
            } else {
                try session.overrideOutputAudioPort(.none)
            }
        } catch {
            print("PhoneCallsPlugin: speaker toggle error: \(error)")
        }

        result(nil)
    }

    // MARK: - Cleanup

    fileprivate func cleanup() {
        activeCall = nil
        callDelegate = nil
        callKitUUID = nil
        currentCallId = nil
    }

    // MARK: - Event Sending

    func sendCallStateEvent(_ state: String) {
        DispatchQueue.main.async { [weak self] in
            self?.eventSink?(["type": "callStateChanged", "state": state])
        }
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
}

// MARK: - FlutterStreamHandler

extension PhoneCallsPlugin: FlutterStreamHandler {
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
    private weak var plugin: PhoneCallsPlugin?

    init(plugin: PhoneCallsPlugin) {
        self.plugin = plugin
        super.init()
    }

    func callDidStartRinging(call: Call) {
        print("PhoneCallsPlugin: call ringing (sid: \(call.sid))")
        plugin?.sendCallStateEvent("ringing")
    }

    func callDidConnect(call: Call) {
        print("PhoneCallsPlugin: call connected (sid: \(call.sid))")
        // Report connected to CallKit
        if let uuid = plugin?.callKitUUID {
            plugin?.callKitProvider.reportOutgoingCall(with: uuid, connectedAt: Date())
        }
        plugin?.sendCallStateEvent("active")
    }

    func callDidDisconnect(call: Call, error: Error?) {
        if let error = error {
            print("PhoneCallsPlugin: call disconnected with error: \(error.localizedDescription)")
            plugin?.sendCallStateEvent("failed")
        } else {
            print("PhoneCallsPlugin: call disconnected normally")
            plugin?.sendCallStateEvent("ended")
        }

        // Report end to CallKit
        if let uuid = plugin?.callKitUUID {
            let reason: CXCallEndedReason = error != nil ? .failed : .remoteEnded
            plugin?.callKitProvider.reportCall(with: uuid, endedAt: Date(), reason: reason)
        }

        plugin?.cleanup()
    }

    func callDidFailToConnect(call: Call, error: Error) {
        print("PhoneCallsPlugin: call failed to connect: \(error.localizedDescription)")
        plugin?.sendCallStateEvent("failed")

        if let uuid = plugin?.callKitUUID {
            plugin?.callKitProvider.reportCall(with: uuid, endedAt: Date(), reason: .failed)
        }

        plugin?.cleanup()
    }
}

// MARK: - CXProviderDelegate (CallKit)

extension PhoneCallsPlugin: CXProviderDelegate {
    func providerDidReset(_ provider: CXProvider) {
        print("PhoneCallsPlugin: CallKit provider reset")
        activeCall?.disconnect()
        cleanup()
    }

    func provider(_ provider: CXProvider, perform action: CXStartCallAction) {
        print("PhoneCallsPlugin: CallKit CXStartCallAction")
        action.fulfill()
    }

    func provider(_ provider: CXProvider, perform action: CXEndCallAction) {
        print("PhoneCallsPlugin: CallKit CXEndCallAction")
        activeCall?.disconnect()
        sendCallStateEvent("ended")
        action.fulfill()
    }

    func provider(_ provider: CXProvider, perform action: CXSetMutedCallAction) {
        isMuted = action.isMuted
        activeCall?.isMuted = action.isMuted
        audioDevice.isMicStreamMuted = action.isMuted
        action.fulfill()
    }

    func provider(_ provider: CXProvider, didActivate audioSession: AVAudioSession) {
        // 48kHz sample rate, 20ms buffer
        do {
            try audioSession.setCategory(
                .playAndRecord,
                mode: .voiceChat,
                options: [.allowBluetoothHFP, .allowBluetoothA2DP, .defaultToSpeaker]
            )
            try audioSession.setPreferredSampleRate(48000)
            try audioSession.setPreferredIOBufferDuration(0.020)
        } catch {
            print("PhoneCallsPlugin: audio session config error: \(error)")
        }

        print("PhoneCallsPlugin: audio session activated (rate: \(audioSession.sampleRate)Hz, buffer: \(audioSession.ioBufferDuration * 1000)ms)")
        _ = audioDevice.start()
    }

    func provider(_ provider: CXProvider, didDeactivate audioSession: AVAudioSession) {
        print("PhoneCallsPlugin: audio session deactivated")
        _ = audioDevice.stop()
    }
}
