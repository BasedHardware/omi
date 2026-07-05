// iOS streaming bridge.
//
// Owns:
//   - One `StreamSession` per active stream (only one supported).
//   - One `FlutterTextureRegistry` entry that owns the latest decoded
//     `CVPixelBuffer`.
//   - Listener tokens for state / error / video-frame publishers.
//   - The three EventSinks (session_state, session_errors,
//     video_stream_size).
//
// Frame pump:
//   videoFramePublisher → CMSampleBuffer → CVImageBuffer (CVPixelBuffer)
//   → `latestPixelBuffer` (atomic-ish swap under `bufferLock`)
//   → `textureRegistry.textureFrameAvailable(id)`
//   → Flutter calls `copyPixelBuffer()` and we hand back the retained buffer.
//
// All Meta SDK calls run on the main actor because that's what
// `Wearables.shared` and the camera publishers expect; texture-buffer swaps
// run inside a tiny critical section under `bufferLock`.

import Flutter
import CoreImage
import CoreMedia
import CoreVideo
import UIKit
#if canImport(MWDATCore)
import MWDATCore
#endif
#if canImport(MWDATCamera)
import MWDATCamera
#endif

@MainActor
final class MetaSessionManager: NSObject {
  private weak var registry: FlutterTextureRegistry?

  // Buffer slot is read from `copyPixelBuffer()`, which Flutter calls on
  // a background raster thread. `bufferLock` guards every read/write so
  // the `nonisolated(unsafe)` here is sound: it only escapes the actor
  // through that lock.
  private let bufferLock = NSLock()
  nonisolated(unsafe) private var latestPixelBuffer: CVPixelBuffer?
  private var textureId: Int64?

  /// The DeviceSession we created via `Wearables.shared.createSession`.
  /// Owned by us; `stop()` is called from `stopSession()`.
  private var deviceSession: DeviceSession?
  private var session: MWDATCamera.Stream?
  private var stateToken: (any AnyListenerToken)?
  private var errorToken: (any AnyListenerToken)?
  private var frameToken: (any AnyListenerToken)?
  private var photoToken: (any AnyListenerToken)?
  private var deviceStateTask: Task<Void, Never>?
  private var deviceErrorTask: Task<Void, Never>?

  /// Continuation for an in-flight `capturePhoto`. Resumed when the next
  /// `PhotoData` arrives on the publisher. `nil` when no capture is in
  /// progress; only one capture can be outstanding at a time.
  private var pendingPhotoContinuation: CheckedContinuation<PhotoData, Error>?

  // EventSinks (set by the plugin when Dart subscribes).
  fileprivate var sessionStateSink: FlutterEventSink?
  fileprivate var sessionErrorSink: FlutterEventSink?
  fileprivate var deviceSessionStateSink: FlutterEventSink?
  fileprivate var deviceSessionErrorSink: FlutterEventSink?
  fileprivate var videoStreamSizeSink: FlutterEventSink?

  /// Per-frame video payload sink. Gated behind subscriber presence: at
  /// 720p the BGRA payload is ≈3.7 MB per frame, so we skip the
  /// `CVPixelBufferLockBaseAddress` + memcpy entirely when nobody is
  /// listening. See `doc/frame_processing.md` for the cost analysis.
  fileprivate var videoFramesSink: FlutterEventSink?

  /// Codec the caller asked for in `startStreamSession`. Drives whether
  /// `handleVideoFrame` extracts BGRA pixels (raw) or routes the sample
  /// buffer through `hevcPipeline` (hvc1).
  private var activeCodec: VideoCodec = .raw

  /// Lazily-built HEVC → BGRA decoder. Only constructed when the caller
  /// selects `.hvc1`; tears down in `stopSession()`.
  private var hevcPipeline: VTDecompressionPipeline?

  init(registry: FlutterTextureRegistry) {
    self.registry = registry
  }

  // MARK: - Session lifecycle

  /// Starts a session for `deviceUUID` (or the active device when nil) at
  /// the requested `fps` and `quality`. Returns the Flutter texture id.
  ///
  /// When `deviceKinds` is provided, only devices whose `DeviceType`
  /// matches one of the wire-name kinds (`rayBanMeta`, `rayBanDisplay`,
  /// `oakleyMeta`, `unknown`) is considered. iOS's
  /// `AutoDeviceSelector` does not expose a filter API, so we enumerate
  /// `Wearables.shared.devices` and pin the first matching id via
  /// `SpecificDeviceSelector`.
  func startSession(
    deviceUUID: String?,
    fps: Int,
    quality: StreamingResolution,
    deviceKinds: Set<String>? = nil,
    videoCodec: VideoCodec = .raw,
  ) async throws -> Int64 {
    if let existingId = textureId { return existingId }
    guard let registry = registry else {
      throw NSError(
        domain: "meta_wearables_dat_flutter",
        code: -1,
        userInfo: [NSLocalizedDescriptionKey: "Texture registry unavailable"]
      )
    }

    // Pick the best available DeviceSelector for the current SDK state.
    //
    // The DAT SDK's `DeviceSession.start()` is responsible for driving the
    // underlying BLE / accessory connection. As long as the glasses are
    // paired through Meta AI (i.e. they appear in
    // `Wearables.shared.devices`), `start()` will wait for them to become
    // reachable. Aborting up-front because `linkState != .connected` would
    // prevent the SDK from ever attempting to connect — so we only do that
    // as an explicit no-paired-device check.
    //
    // Strategy:
    //   1. If the caller passed a deviceUUID, pin `SpecificDeviceSelector`
    //      to that UUID.
    //   2. Otherwise, prefer a device in `linkState == .connected`, then
    //      `.connecting`, then any paired id — and pin
    //      `SpecificDeviceSelector` so the SDK doesn't reject us with
    //      `noEligibleDevice` when no don-sensor signal is available.
    //   3. Only error out when *no* paired device matches the request
    //      (either nothing paired, or nothing matching `deviceKinds`).
    let selector: any DeviceSelector
    let chosenIdSource: String

    let allIds = Wearables.shared.devices

    let filteredIds = MetaSessionManager.filterDevices(allIds, deviceKinds: deviceKinds)
    let pickedId = MetaSessionManager.pickBestDevice(from: filteredIds)

    if let requestedUuid = deviceUUID,
       let match = filteredIds.first(where: { $0 == requestedUuid }) {
      selector = SpecificDeviceSelector(device: match)
      chosenIdSource = "explicit deviceUuid (\(match))"
    } else if let pick = pickedId {
      selector = SpecificDeviceSelector(device: pick)
      chosenIdSource = "first paired device (\(pick))"
    } else if let kinds = deviceKinds, !kinds.isEmpty {
      print("[meta_wearables_dat_flutter] startSession aborting: " +
        "no devices matching kinds=\(kinds). devices=\(allIds.count)")
      throw NSError(
        domain: "meta_wearables_dat_flutter",
        code: -11,
        userInfo: [NSLocalizedDescriptionKey:
          "No glasses matching the requested kinds are currently paired."],
      )
    } else {
      print("[meta_wearables_dat_flutter] startSession aborting: " +
        "no paired devices. devices=\(allIds.count)")
      throw NSError(
        domain: "meta_wearables_dat_flutter",
        code: -10,
        userInfo: [NSLocalizedDescriptionKey:
          "No glasses are currently paired. Open Meta AI to pair " +
          "Ray-Ban Meta or Oakley Meta glasses, then try again."],
      )
    }
    print("[meta_wearables_dat_flutter] startSession selector=\(chosenIdSource)")

    // Create the DeviceSession via the real Wearables API and wait for
    // it to reach `.started` before adding any stream capability. The
    // SDK's `start()` is what actually drives the BLE/MFi handshake, so
    // we no longer pre-abort when `linkState != .connected`.
    let deviceSession = try Wearables.shared.createSession(
      deviceSelector: selector,
    )
    self.deviceSession = deviceSession

    // Wire DeviceSession-level state + error streams.
    observeDeviceSession(deviceSession)

    if deviceSession.state != .started {
      try deviceSession.start()
      try await Self.waitForDeviceSessionStarted(
        deviceSession,
        timeoutNs: 45_000_000_000,
      )
    }

    // Build the stream config. When the caller selected `.hvc1` we
    // ask the SDK for HEVC NAL units and route them through a
    // `VTDecompressionPipeline` for the texture preview (so the
    // existing `Texture(textureId:)` widget keeps working).
    let config = StreamConfiguration(
      videoCodec: videoCodec,
      resolution: quality,
      frameRate: UInt(fps)
    )
    self.activeCodec = videoCodec
    if videoCodec == .hvc1 {
      let pipeline = VTDecompressionPipeline()
      // If background streaming is already active, build the decoder in
      // software-only mode so it survives backgrounding from the start.
      pipeline.softwareOnly = BackgroundStreamingController.shared
        .useSoftwareDecoder
      self.hevcPipeline = pipeline
    } else {
      self.hevcPipeline = nil
    }

    guard let stream = try deviceSession.addStream(config: config) else {
      throw NSError(
        domain: "meta_wearables_dat_flutter",
        code: -3,
        userInfo: [NSLocalizedDescriptionKey: "addStream returned nil"]
      )
    }
    self.session = stream

    // Register a Flutter texture before frames start flowing.
    let id = registry.register(self)
    self.textureId = id

    // Wire publishers BEFORE starting so we don't miss the initial state
    // transition. Tokens are released in stopSession.
    stateToken = stream.statePublisher.listen { [weak self] state in
      Task { @MainActor in
        self?.sessionStateSink?(MetaSessionManager.encode(state))
      }
    }
    errorToken = stream.errorPublisher.listen { [weak self] error in
      Task { @MainActor in
        self?.sessionErrorSink?(MetaSessionManager.encode(error))
      }
    }
    frameToken = stream.videoFramePublisher.listen { [weak self] frame in
      Task { @MainActor in
        self?.handleVideoFrame(frame, textureId: id)
      }
    }
    photoToken = stream.photoDataPublisher.listen { [weak self] photo in
      Task { @MainActor in
        self?.deliverPhoto(.success(photo))
      }
    }

    await stream.start()
    return id
  }

  /// Triggers a high-res still capture and resolves once the next
  /// `PhotoData` arrives on the publisher. Throws when no session is
  /// active, when another capture is already in flight, or when the
  /// underlying SDK returns `false` from `capturePhoto`.
  func capturePhoto(format: PhotoCaptureFormat) async throws -> PhotoData {
    guard let stream = session else {
      throw NSError(
        domain: "meta_wearables_dat_flutter",
        code: -20,
        userInfo: [NSLocalizedDescriptionKey: "No active stream session"],
      )
    }
    if pendingPhotoContinuation != nil {
      throw NSError(
        domain: "meta_wearables_dat_flutter",
        code: -21,
        userInfo: [
          NSLocalizedDescriptionKey: "A photo capture is already in flight",
        ],
      )
    }
    return try await withCheckedThrowingContinuation { continuation in
      pendingPhotoContinuation = continuation
      let kickedOff = stream.capturePhoto(format: format)
      if !kickedOff {
        pendingPhotoContinuation = nil
        continuation.resume(throwing: NSError(
          domain: "meta_wearables_dat_flutter",
          code: -22,
          userInfo: [
            NSLocalizedDescriptionKey: "capturePhoto returned false",
          ],
        ))
      }
    }
  }

  private func deliverPhoto(_ result: Result<PhotoData, Error>) {
    guard let continuation = pendingPhotoContinuation else { return }
    pendingPhotoContinuation = nil
    continuation.resume(with: result)
  }

  func stopSession() async {
    if let session = session {
      try? await session.stop()
    }
    if let token = stateToken { await token.cancel() }
    if let token = errorToken { await token.cancel() }
    if let token = frameToken { await token.cancel() }
    if let token = photoToken { await token.cancel() }
    stateToken = nil
    errorToken = nil
    frameToken = nil
    photoToken = nil
    session = nil

    // Tear down DeviceSession-level listeners.
    deviceStateTask?.cancel()
    deviceStateTask = nil
    deviceErrorTask?.cancel()
    deviceErrorTask = nil

    // DeviceSession.stop() is synchronous in 0.6.x; once stopped a
    // new createSession() call is required to stream again.
    deviceSession?.stop()
    deviceSession = nil

    // Tear down the HEVC pipeline (if any) so the next session can
    // pick a different codec / resolution.
    hevcPipeline?.invalidate()
    hevcPipeline = nil
    activeCodec = .raw

    if pendingPhotoContinuation != nil {
      deliverPhoto(.failure(NSError(
        domain: "meta_wearables_dat_flutter",
        code: -23,
        userInfo: [NSLocalizedDescriptionKey: "Session stopped during capture"],
      )))
    }

    if let id = textureId {
      registry?.unregisterTexture(id)
      textureId = nil
    }
    bufferLock.lock()
    latestPixelBuffer = nil
    bufferLock.unlock()
  }

  func pauseSession() async {
    if let stream = session {
      try? await stream.stop()
    }
  }

  func resumeSession() async {
    if let stream = session {
      await stream.start()
    }
  }

  // MARK: - Frame plumbing

  private func handleVideoFrame(_ frame: VideoFrame, textureId: Int64) {
    let sampleBuffer = frame.sampleBuffer

    // Path A: raw / BGRA. `CMSampleBufferGetImageBuffer` returns the
    // already-decoded `CVPixelBuffer` directly.
    // Path B: hvc1. The image buffer is nil (sample carries compressed
    // NAL units); route through the VTDecompressionSession to get a
    // BGRA `CVPixelBuffer` for the texture and emit the compressed
    // bytes to `videoFramesStream` when subscribed.
    let imageBuffer: CVPixelBuffer? = {
      if activeCodec == .hvc1 {
        return hevcPipeline?.decode(sampleBuffer)
      }
      return CMSampleBufferGetImageBuffer(sampleBuffer)
    }()
    guard let imageBuffer = imageBuffer else {
      // Even when decoding fails, still emit the compressed payload so
      // host apps recording to disk don't miss frames.
      if activeCodec == .hvc1, let sink = videoFramesSink {
        emitHevcFrame(sampleBuffer: sampleBuffer, sink: sink)
      }
      return
    }

    bufferLock.lock()
    latestPixelBuffer = imageBuffer
    bufferLock.unlock()

    let width = CVPixelBufferGetWidth(imageBuffer)
    let height = CVPixelBufferGetHeight(imageBuffer)

    // Emit size update lazily so the host can rebuild AspectRatio without
    // every frame triggering a Flutter rebuild.
    if let sink = videoStreamSizeSink {
      sink(["width": width, "height": height])
    }

    // Forward the frame to the videoFramesStream sink, but only when at
    // least one Dart subscriber is attached. Skipping when not needed
    // keeps the per-frame cost free for host apps that only care about
    // the texture preview.
    if let sink = videoFramesSink {
      if activeCodec == .hvc1 {
        emitHevcFrame(sampleBuffer: sampleBuffer, sink: sink)
      } else {
        emitVideoFrame(
          sampleBuffer: sampleBuffer,
          pixelBuffer: imageBuffer,
          width: width,
          height: height,
          sink: sink,
        )
      }
    }

    registry?.textureFrameAvailable(textureId)
  }

  /// Serialises an HEVC `CMSampleBuffer` to an Annex-B encoded byte
  /// payload and emits it on the videoFramesStream sink. On keyframes
  /// the VPS/SPS/PPS parameter sets are prepended so downstream muxers
  /// (e.g. an mp4 writer) can decode the stream without out-of-band
  /// state. Both bytes and parameter sets use 4-byte start codes
  /// (`00 00 00 01`).
  private func emitHevcFrame(
    sampleBuffer: CMSampleBuffer,
    sink: @escaping FlutterEventSink,
  ) {
    let isKeyframe = VTDecompressionPipeline.isKeyframe(sampleBuffer)
    guard let nalBytes = VTDecompressionPipeline.annexBNalBytes(
      from: sampleBuffer,
    ) else {
      return
    }
    var bytes = Data()
    if isKeyframe,
       let desc = CMSampleBufferGetFormatDescription(sampleBuffer),
       let params = VTDecompressionPipeline.annexBParameterSets(from: desc) {
      bytes.append(params)
    }
    bytes.append(nalBytes)

    let pts = CMSampleBufferGetPresentationTimeStamp(sampleBuffer)
    let ptsUs: Int = pts.isValid
      ? Int(CMTimeGetSeconds(pts) * 1_000_000.0)
      : 0

    let dims = CMSampleBufferGetFormatDescription(sampleBuffer)
      .map(CMVideoFormatDescriptionGetDimensions) ?? CMVideoDimensions(width: 0, height: 0)
    sink([
      "codec": "hvc1",
      "bytes": FlutterStandardTypedData(bytes: bytes),
      "width": Int(dims.width),
      "height": Int(dims.height),
      "ptsUs": ptsUs,
      "isKeyframe": isKeyframe,
    ] as [String: Any])
  }

  /// Serialises a single `CVPixelBuffer` BGRA frame into a Flutter
  /// platform-channel payload and emits it on the `videoFramesStream`
  /// sink. The pixel-buffer is locked with `.readOnly`, copied into a
  /// `Data` and unlocked synchronously; no buffer references escape this
  /// scope.
  ///
  /// The payload shape matches `VideoFrame.fromMap` on Dart:
  ///   `{ codec, bytes, width, height, ptsUs, isKeyframe, bytesPerRow }`.
  private func emitVideoFrame(
    sampleBuffer: CMSampleBuffer,
    pixelBuffer: CVPixelBuffer,
    width: Int,
    height: Int,
    sink: @escaping FlutterEventSink,
  ) {
    CVPixelBufferLockBaseAddress(pixelBuffer, .readOnly)
    defer { CVPixelBufferUnlockBaseAddress(pixelBuffer, .readOnly) }
    guard let base = CVPixelBufferGetBaseAddress(pixelBuffer) else { return }
    let bytesPerRow = CVPixelBufferGetBytesPerRow(pixelBuffer)
    let size = bytesPerRow * height

    let pts = CMSampleBufferGetPresentationTimeStamp(sampleBuffer)
    let ptsUs: Int = pts.isValid
      ? Int(CMTimeGetSeconds(pts) * 1_000_000.0)
      : 0

    let bytes = Data(bytes: base, count: size)
    sink([
      "codec": "raw",
      "bytes": FlutterStandardTypedData(bytes: bytes),
      "width": width,
      "height": height,
      "ptsUs": ptsUs,
      "isKeyframe": true,
      "bytesPerRow": bytesPerRow,
    ] as [String: Any])
  }

  // MARK: - Encoding helpers

  /// Maps an iOS `DeviceType` to the wire-string name Dart uses (`DeviceKind`).
  /// Mirrors `MetaWearablesDatPlugin.kindName(for:)`.
  static func wireKindName(for deviceType: DeviceType?) -> String {
    switch deviceType {
    case .rayBanMeta?, .rayBanMetaOptics?: return "rayBanMeta"
    case .metaRayBanDisplay?: return "rayBanDisplay"
    case .oakleyMetaHSTN?, .oakleyMetaVanguard?: return "oakleyMeta"
    case .unknown?, .none: return "unknown"
    @unknown default: return "unknown"
    }
  }

  private static func encode(_ state: StreamState) -> Int {
    switch state {
    case .stopped: return 0
    case .waitingForDevice: return 1
    case .starting: return 2
    case .streaming: return 3
    case .paused: return 4
    case .stopping: return 5
    @unknown default: return 0
    }
  }

  /// Maps a `StreamError` (DAT 0.7.0 renamed `StreamSessionError`) to a
  /// typed sub-code that Dart's `SessionError.is*` getters key on.
  ///
  /// We derive the code from `String(describing:)` rather than switching on
  /// concrete enum cases so the bridge keeps compiling if Meta adds or
  /// renames cases between SDK releases.
  private static func encode(_ error: StreamError) -> [String: Any] {
    let raw = String(describing: error)
    let token = raw.split(separator: "(").first.map(String.init) ?? raw
    let code: String
    switch token {
    case "permissionDenied": code = "permissionDenied"
    case "hingesClosed", "hingeClosed": code = "hingesClosed"
    case "thermalCritical": code = "thermalCritical"
    case "videoStreamingError", "streamError": code = "videoStreamingError"
    case "timeout": code = "timeout"
    case "deviceNotFound", "deviceNotConnected", "deviceDisconnected":
      code = "deviceDisconnected"
    case "internalError": code = "internalError"
    default: code = "sessionError"
    }
    return ["code": code, "message": raw]
  }

  private static func encodeDeviceSessionState(_ state: DeviceSessionState) -> Int {
    switch state {
    case .idle: return 0
    case .starting: return 1
    case .started: return 2
    case .paused: return 3
    case .stopping: return 4
    case .stopped: return 5
    @unknown default: return 0
    }
  }

  /// Maps `DeviceSessionError` cases to typed sub-codes for the Dart
  /// `DeviceSessionError.is*` getters.
  ///
  /// Derived from `String(describing:)` so the bridge keeps compiling across
  /// SDK releases that add cases (DAT 0.7.0 added
  /// `datAppOnTheGlassesUpdateRequired`). The `.unexpectedError` associated
  /// description is preserved for the message when present.
  private static func encodeDeviceSessionError(_ error: DeviceSessionError) -> [String: Any] {
    let raw = String(describing: error)
    let token = raw.split(separator: "(").first.map(String.init) ?? raw
    let code: String
    switch token {
    case "noEligibleDevice": code = "noEligibleDevice"
    case "sessionAlreadyStopped": code = "sessionAlreadyStopped"
    case "sessionAlreadyExists": code = "sessionAlreadyExists"
    case "sessionIdle": code = "sessionIdle"
    case "capabilityAlreadyActive": code = "capabilityAlreadyActive"
    case "capabilityNotFound": code = "capabilityNotFound"
    case "datAppOnTheGlassesUpdateRequired": code = "datAppUpdateRequired"
    default: code = "unexpectedError"
    }
    let message: String
    if case let .unexpectedError(description) = error {
      message = description
    } else {
      message = raw
    }
    return ["code": code, "message": message]
  }

  /// Wires DeviceSession-level state and error publishers to the matching
  /// Flutter event sinks. Called from `startSession` once a session has
  /// been created. Tokens are torn down in `stopSession`.
  private func observeDeviceSession(_ session: DeviceSession) {
    // The DeviceSession's `stateStream()` is an AsyncSequence; iterate in a
    // detached Task so we don't block the main caller.
    deviceStateTask?.cancel()
    deviceStateTask = Task { @MainActor [weak self] in
      // Seed the current state for late subscribers.
      self?.deviceSessionStateSink?(
        MetaSessionManager.encodeDeviceSessionState(session.state)
      )
      for await state in session.stateStream() {
        if Task.isCancelled { break }
        self?.deviceSessionStateSink?(
          MetaSessionManager.encodeDeviceSessionState(state)
        )
      }
    }
    deviceErrorTask?.cancel()
    deviceErrorTask = Task { @MainActor [weak self] in
      for await error in session.errorStream() {
        if Task.isCancelled { break }
        self?.deviceSessionErrorSink?(
          MetaSessionManager.encodeDeviceSessionError(error)
        )
      }
    }
  }

  /// Polls `session.state` until it reaches `.started`, or throws once
  /// `timeoutNs` elapses or the session transitions straight to
  /// `.stopped`. Implemented as a simple polling loop rather than a
  /// task-group race against `session.stateStream()` because the SDK
  /// `DeviceSession` is not `Sendable`, and crossing it into a child
  /// task tripped the Swift compiler's SILGen pass on Xcode 16+.
  /// 250 ms polling at 30 fps is essentially free.
  private static func waitForDeviceSessionStarted(
    _ session: DeviceSession,
    timeoutNs: UInt64,
  ) async throws {
    let pollIntervalNs: UInt64 = 250_000_000
    let maxIterations = max(1, Int(timeoutNs / pollIntervalNs))
    for _ in 0..<maxIterations {
      if session.state == .started { return }
      if session.state == .stopped {
        throw NSError(
          domain: "meta_wearables_dat_flutter",
          code: -2,
          userInfo: [
            NSLocalizedDescriptionKey:
              "DeviceSession stopped before reaching .started",
          ],
        )
      }
      try? await Task.sleep(nanoseconds: pollIntervalNs)
    }
    // Timeout. Stop the half-built session so the next call starts clean.
    session.stop()
    throw NSError(
      domain: "meta_wearables_dat_flutter",
      code: -12,
      userInfo: [
        NSLocalizedDescriptionKey:
          "Glasses did not connect in time. Take them out of the case " +
          "and put them on, then try again.",
      ],
    )
  }

  /// Filters paired device ids by the optional kinds set. Hoisted out
  /// of `startSession` so the type checker has less work to do inside
  /// the async function body (Xcode 16's SILGen pass crashes on some
  /// nested-closure shapes inside large async functions).
  private static func filterDevices(
    _ allIds: [DeviceIdentifier],
    deviceKinds: Set<String>?,
  ) -> [DeviceIdentifier] {
    guard let kinds = deviceKinds, !kinds.isEmpty else { return allIds }
    return allIds.filter { id in
      let kindName = MetaSessionManager.wireKindName(
        for: Wearables.shared.deviceForIdentifier(id)?.deviceType(),
      )
      return kinds.contains(kindName)
    }
  }

  /// Picks the best paired device from `ids`, preferring `.connected`,
  /// then `.connecting`, then any paired id. Returns `nil` when `ids`
  /// is empty.
  private static func pickBestDevice(
    from ids: [DeviceIdentifier],
  ) -> DeviceIdentifier? {
    if let connected = ids.first(where: { id in
      Wearables.shared.deviceForIdentifier(id)?.linkState == .connected
    }) { return connected }
    if let connecting = ids.first(where: { id in
      Wearables.shared.deviceForIdentifier(id)?.linkState == .connecting
    }) { return connecting }
    return ids.first
  }

  // MARK: - EventSink wiring (called from the plugin)

  func setSessionStateSink(_ sink: FlutterEventSink?) { sessionStateSink = sink }
  func setSessionErrorSink(_ sink: FlutterEventSink?) { sessionErrorSink = sink }
  func setDeviceSessionStateSink(_ sink: FlutterEventSink?) {
    deviceSessionStateSink = sink
  }
  func setDeviceSessionErrorSink(_ sink: FlutterEventSink?) {
    deviceSessionErrorSink = sink
  }
  func setVideoSizeSink(_ sink: FlutterEventSink?) { videoStreamSizeSink = sink }
  func setVideoFramesSink(_ sink: FlutterEventSink?) { videoFramesSink = sink }

  /// Tells the manager whether background streaming is currently
  /// enabled. When `true`, the next session that selects `.hvc1` will
  /// build its `VTDecompressionSession` in software-only mode so the
  /// decoder survives backgrounding. Live sessions are rebuilt lazily;
  /// in-flight decoders are invalidated so the next frame triggers a
  /// rebuild with the new flag.
  func setBackgroundStreamingEnabled(_ enabled: Bool) {
    hevcPipeline?.softwareOnly = enabled
  }

  // MARK: - Still capture (background-safe)

  /// Software (CPU) CoreImage context reused across still captures. Software
  /// rendering is required so encoding survives app backgrounding, when the
  /// GPU/Metal render path is unavailable.
  private static let stillEncodeContext =
    CIContext(options: [.useSoftwareRenderer: true])

  /// Encodes the most recent decoded frame (`latestPixelBuffer`) to JPEG on
  /// the CPU.
  ///
  /// Unlike the Flutter texture rasterizer (`ui.Scene.toImage(textureId)`),
  /// this does **not** depend on the app being foregrounded or on the GPU
  /// raster pipeline, so it keeps producing viewable frames while the app is
  /// backgrounded (the SDK's native frame callback keeps `latestPixelBuffer`
  /// fresh). Reads the buffer under `bufferLock`; encodes it via a software
  /// CoreImage context.
  func captureLatestFrameJpeg(quality: CGFloat) -> Data? {
    bufferLock.lock()
    let buffer = latestPixelBuffer
    bufferLock.unlock()
    guard let pixelBuffer = buffer else { return nil }

    let ciImage = CIImage(cvPixelBuffer: pixelBuffer)
    let extent = ciImage.extent
    guard extent.width > 0, extent.height > 0 else { return nil }
    guard let cgImage = MetaSessionManager.stillEncodeContext.createCGImage(
      ciImage,
      from: extent,
    ) else { return nil }
    return UIImage(cgImage: cgImage).jpegData(compressionQuality: quality)
  }
}

extension MetaSessionManager: FlutterTexture {
  nonisolated func copyPixelBuffer() -> Unmanaged<CVPixelBuffer>? {
    bufferLock.lock()
    defer { bufferLock.unlock() }
    guard let buffer = latestPixelBuffer else { return nil }
    return Unmanaged.passRetained(buffer)
  }
}
