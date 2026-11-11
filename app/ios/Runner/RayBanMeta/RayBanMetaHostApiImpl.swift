import AVFoundation
import Flutter
import Foundation
import UIKit

#if canImport(MWDATCore)
    import MWDATCore
#endif
#if canImport(MWDATCamera)
    import MWDATCamera
#endif

/// Pigeon host API for Ray-Ban Meta glasses.
///
/// Two build modes, reported through getAvailabilityMode():
/// - "full": the Meta Wearables Device Access Toolkit (SPM package
///   meta-wearables-dat-ios) is linked — camera/photo capture plus HFP
///   microphone audio. Developer Mode must not include MetaAppID/ClientToken
///   credentials; those are distribution-only.
/// - "audio_only": no toolkit in this build — only the labeled Bluetooth HFP
///   microphone fallback. Camera calls report unavailable; nothing is faked.
///
/// Meta ordering constraint: HFP audio must be fully active before the DAT
/// camera stream starts, otherwise the audio route can fail silently. This is
/// why startCamera() waits for the audio engine when audio capture is running.
final class RayBanMetaHostApiImpl: NSObject, RayBanMetaHostAPI {
    private let flutterAPI: RayBanMetaFlutterAPI
    private let audioCapture = RayBanMetaAudioCapture()

    init(flutterAPI: RayBanMetaFlutterAPI) {
        self.flutterAPI = flutterAPI
        super.init()

        audioCapture.onFrame = { [weak self] data, sampleRate in
            DispatchQueue.main.async {
                self?.flutterAPI.onAudioFrame(
                    pcm16Frame: FlutterStandardTypedData(bytes: data),
                    sampleRate: sampleRate
                ) { _ in }
            }
        }
        audioCapture.onRouteChanged = { [weak self] active in
            DispatchQueue.main.async {
                self?.flutterAPI.onAudioRouteChanged(glassesRouteActive: active) { _ in }
            }
        }
        audioCapture.onError = { [weak self] code, message in
            self?.emitError(code: code, message: message)
        }
    }

    private func emitError(code: String, message: String) {
        DispatchQueue.main.async {
            self.flutterAPI.onError(code: code, message: message) { _ in }
        }
    }

    // MARK: - Availability

    // Full mode requires only the linked toolkit. Meta's Developer Center:
    // the MWDAT Info.plist credentials must NOT be set when testing via
    // glasses Developer Mode; they matter only for distribution builds.
    func getAvailabilityMode() throws -> String {
        #if canImport(MWDATCore)
            return "full"
        #else
            return "audio_only"
        #endif
    }

    // MARK: - Audio (HFP route — available in both modes)

    func startAudioCapture(inputUid: String?) throws {
        try audioCapture.start(targetUid: inputUid)
    }

    func stopAudioCapture() throws {
        audioCapture.stop()
    }

    func isGlassesAudioRouteActive() throws -> Bool {
        return audioCapture.isSelectedRouteActive
    }

    func getBluetoothHfpInputs() throws -> [BluetoothHfpInput] {
        // Enumerating Bluetooth inputs requires a record-capable session category.
        // This can run during discovery while another device records, so restore
        // the prior category instead of leaving the shared session mutated.
        let session = AVAudioSession.sharedInstance()
        let priorCategory = session.category
        let priorMode = session.mode
        let priorOptions = session.categoryOptions
        var mutated = false
        if priorCategory != .playAndRecord {
            try? session.setCategory(.playAndRecord, mode: .default, options: [.allowBluetoothHFP])
            mutated = true
        }
        let inputs = RayBanMetaAudioCapture.availableHfpInputs().map {
            BluetoothHfpInput(uid: $0.uid, name: $0.name)
        }
        if mutated {
            try? session.setCategory(priorCategory, mode: priorMode, options: priorOptions)
        }
        return inputs
    }

    #if canImport(MWDATCore)
        // =====================================================================
        // Full mode — Meta Wearables Device Access Toolkit
        // =====================================================================

        private var configured = false
        private var session: DeviceSession?
        private var connectionState = "disconnected"
        private var connectedDeviceId: String?
        private var latestGlasses: [(id: String, name: String)] = []
        private var observerTasks: [Task<Void, Never>] = []
        private var sessionObserverTask: Task<Void, Never>?

        deinit {
            observerTasks.forEach { $0.cancel() }
            sessionObserverTask?.cancel()
        }

        #if canImport(MWDATCamera)
            private var cameraStream: MWDATCamera.Stream?
            private var cameraListenerTokens: [Any] = []
        #endif

        func initialize() throws {
            guard !configured else { return }
            try Wearables.configure()
            configured = true

            let wearables = Wearables.shared

            observerTasks.append(Task { [weak self] in
                for await state in wearables.registrationStateStream() {
                    guard let self = self else { return }
                    let normalized: String
                    switch state {
                    case .registered: normalized = "registered"
                    case .registering: normalized = "registering"
                    default: normalized = "unregistered"
                    }
                    DispatchQueue.main.async {
                        self.flutterAPI.onRegistrationStateChanged(state: normalized) { _ in }
                    }
                }
            })

            observerTasks.append(Task { [weak self] in
                for await identifiers in wearables.devicesStream() {
                    guard let self = self else { return }
                    let mapped = identifiers.map { identifier in
                        (id: identifier, name: wearables.deviceForIdentifier(identifier)?.nameOrId() ?? "Ray-Ban Meta")
                    }
                    DispatchQueue.main.async {
                        // Written on main: Pigeon reads (getAvailableGlasses) are
                        // main-thread, so publishing here avoids a cross-thread race.
                        self.latestGlasses = mapped
                    }
                    DispatchQueue.main.async {
                        for glasses in mapped {
                            self.flutterAPI.onGlassesDiscovered(
                                glasses: RayBanMetaGlasses(id: glasses.id, name: glasses.name)
                            ) { _ in }
                        }
                    }
                }
            })
        }

        func getRegistrationState() throws -> String {
            guard configured else { return "unregistered" }
            switch Wearables.shared.registrationState {
            case .registered: return "registered"
            case .registering: return "registering"
            default: return "unregistered"
            }
        }

        func startRegistration() throws {
            try initialize()
            Task { [weak self] in
                do {
                    try await Wearables.shared.startRegistration()
                } catch {
                    self?.emitError(code: "registration", message: String(describing: error))
                }
            }
        }

        func unregister() throws {
            guard configured else { return }
            Task { [weak self] in
                do {
                    try await Wearables.shared.startUnregistration()
                } catch {
                    self?.emitError(code: "unregistration", message: String(describing: error))
                }
            }
        }

        /// Forwarded from AppDelegate for the Meta AI app registration callback.
        /// Never blocks the main thread: claims the URL by scheme match and lets
        /// the SDK consume it asynchronously (registration state changes arrive
        /// via registrationStateStream either way).
        @discardableResult
        func handleUrl(_ url: URL) -> Bool {
            guard configured else { return false }
            let appLinkScheme = (Bundle.main.object(forInfoDictionaryKey: "MWDAT") as? [String: Any])?["AppLinkURLScheme"] as? String
            let expectedScheme = appLinkScheme?.replacingOccurrences(of: "://", with: "")
            guard let scheme = url.scheme, scheme == (expectedScheme ?? "omirayban") else { return false }
            Task { [weak self] in
                do {
                    _ = try await Wearables.shared.handleUrl(url)
                } catch {
                    self?.emitError(code: "registration_callback", message: String(describing: error))
                }
            }
            return true
        }

        func getAvailableGlasses(completion: @escaping (Result<[RayBanMetaGlasses], Error>) -> Void) {
            do {
                try initialize()
            } catch {
                completion(.failure(error))
                return
            }
            let snapshot = latestGlasses.map { RayBanMetaGlasses(id: $0.id, name: $0.name) }
            completion(.success(snapshot))
        }

        func connect(deviceId: String) throws {
            try initialize()
            guard session == nil else { return }

            connectedDeviceId = deviceId
            setConnectionState("connecting", deviceId: deviceId)

            let wearables = Wearables.shared
            let selector = AutoDeviceSelector(wearables: wearables)
            let newSession = try wearables.createSession(deviceSelector: selector)
            session = newSession
            try newSession.start()

            sessionObserverTask?.cancel()
            sessionObserverTask = Task { [weak self] in
                for await state in newSession.stateStream() {
                    guard let self = self, let deviceId = self.connectedDeviceId else { return }
                    switch state {
                    case .started:
                        self.setConnectionState("connected", deviceId: deviceId)
                    case .stopped:
                        self.setConnectionState("disconnected", deviceId: deviceId)
                    default:
                        break
                    }
                }
            }
        }

        func disconnect() throws {
            audioCapture.stop()
            try? stopCamera()
            sessionObserverTask?.cancel()
            sessionObserverTask = nil
            session?.stop()
            session = nil
            if let deviceId = connectedDeviceId {
                setConnectionState("disconnected", deviceId: deviceId)
            }
            connectedDeviceId = nil
        }

        func getConnectionState() throws -> String {
            return connectionState
        }

        private func setConnectionState(_ state: String, deviceId: String) {
            DispatchQueue.main.async {
                // Written on main for the same reason as latestGlasses.
                self.connectionState = state
            }
            DispatchQueue.main.async {
                self.flutterAPI.onConnectionStateChanged(deviceId: deviceId, state: state) { _ in }
            }
        }

        func requestCameraPermission(completion: @escaping (Result<String, Error>) -> Void) {
            do {
                try initialize()
            } catch {
                completion(.failure(error))
                return
            }
            Task { [weak self] in
                do {
                    let status = try await Wearables.shared.requestPermission(.camera)
                    let normalized = Self.normalizePermission(status)
                    DispatchQueue.main.async {
                        self?.flutterAPI.onCameraPermissionChanged(status: normalized) { _ in }
                        completion(.success(normalized))
                    }
                } catch {
                    DispatchQueue.main.async { completion(.failure(error)) }
                }
            }
        }

        func getCameraPermissionStatus(completion: @escaping (Result<String, Error>) -> Void) {
            guard configured else {
                completion(.success("not_determined"))
                return
            }
            Task {
                let normalized: String
                if let status = try? await Wearables.shared.checkPermissionStatus(.camera) {
                    normalized = Self.normalizePermission(status)
                } else {
                    normalized = "not_determined"
                }
                DispatchQueue.main.async { completion(.success(normalized)) }
            }
        }

        private static func normalizePermission(_ status: PermissionStatus) -> String {
            switch status {
            case .granted: return "granted"
            case .denied: return "denied"
            default: return "not_determined"
            }
        }

        func startCamera() throws {
            try initialize()
            guard let session = session else {
                throw PigeonError(code: "not_connected", message: "Connect to the glasses first", details: nil)
            }

            #if canImport(MWDATCamera)
                guard cameraStream == nil else { return }

                // Meta's ordering rule: if HFP audio is in use, it must be fully
                // configured before the DAT stream starts or the route fails
                // silently. The audio engine start already waited its 2s settle.
                DispatchQueue.main.async { self.flutterAPI.onCameraStateChanged(state: "starting") { _ in } }

                // Lowest frame rate: the stream session exists to arm photo
                // capture (and the hardware privacy LED), not to ship video.
                let config = StreamConfiguration(
                    videoCodec: VideoCodec.raw,
                    resolution: StreamingResolution.low,
                    frameRate: 2
                )
                guard let stream = try? session.addStream(config: config) else {
                    throw PigeonError(code: "camera_stream", message: "Could not add DAT camera stream", details: nil)
                }
                cameraStream = stream

                cameraListenerTokens.append(stream.statePublisher.listen { [weak self] state in
                    guard let self = self else { return }
                    let normalized = String(describing: state)
                    DispatchQueue.main.async {
                        self.flutterAPI.onCameraStateChanged(state: normalized) { _ in }
                    }
                })

                cameraListenerTokens.append(stream.photoDataPublisher.listen { [weak self] photoData in
                    guard let self = self else { return }
                    let data = photoData.data
                    DispatchQueue.main.async {
                        self.flutterAPI.onPhotoCaptured(
                            jpegBytes: FlutterStandardTypedData(bytes: data),
                            // DAT 0.8 exposes no orientation metadata; photos always
                            // decode as orientation0 downstream. Kept for framing parity.
                            orientationDegrees: 0
                        ) { _ in }
                    }
                })

                stream.start()
            #else
                throw PigeonError(code: "camera_unavailable", message: "MWDATCamera not linked", details: nil)
            #endif
        }

        func stopCamera() throws {
            #if canImport(MWDATCamera)
                cameraStream?.stop()
                cameraStream = nil
                cameraListenerTokens.removeAll()
                DispatchQueue.main.async { self.flutterAPI.onCameraStateChanged(state: "stopped") { _ in } }
            #endif
        }

        func capturePhoto() throws {
            #if canImport(MWDATCamera)
                guard let stream = cameraStream else {
                    throw PigeonError(
                        code: "camera_not_started",
                        message: "Start the camera before capturing a photo",
                        details: nil
                    )
                }
                guard stream.capturePhoto(format: .jpeg) else {
                    throw PigeonError(
                        code: "capture_failed",
                        message: "The camera stream is not ready to capture yet",
                        details: nil
                    )
                }
            #else
                throw PigeonError(code: "camera_unavailable", message: "MWDATCamera not linked", details: nil)
            #endif
        }

    #else
        // =====================================================================
        // Audio-only mode — no Meta Wearables toolkit in this build
        // =====================================================================

        func initialize() throws {}

        func getRegistrationState() throws -> String { return "unavailable" }

        func startRegistration() throws {
            throw PigeonError(
                code: "dat_unavailable",
                message: "This build does not include the Meta Wearables toolkit",
                details: nil
            )
        }

        func unregister() throws {}

        func handleUrl(_ url: URL) -> Bool { return false }

        func getAvailableGlasses(completion: @escaping (Result<[RayBanMetaGlasses], Error>) -> Void) {
            completion(.success([]))
        }

        func connect(deviceId: String) throws {}

        func disconnect() throws {
            audioCapture.stop()
        }

        func getConnectionState() throws -> String {
            return RayBanMetaAudioCapture.isHfpRouteActive() ? "connected" : "disconnected"
        }

        func requestCameraPermission(completion: @escaping (Result<String, Error>) -> Void) {
            completion(.success("unavailable"))
        }

        func getCameraPermissionStatus(completion: @escaping (Result<String, Error>) -> Void) {
            completion(.success("unavailable"))
        }

        func startCamera() throws {
            throw PigeonError(
                code: "camera_unavailable",
                message: "Image capture requires the Meta Wearables toolkit build",
                details: nil
            )
        }

        func stopCamera() throws {}

        func capturePhoto() throws {
            throw PigeonError(
                code: "camera_unavailable",
                message: "Image capture requires the Meta Wearables toolkit build",
                details: nil
            )
        }
    #endif
}
