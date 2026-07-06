// `meta_wearables_dat_flutter` iOS plugin.
//
// Bridges Meta's MWDATCore / MWDATCamera (and optional MWDATMockDevice)
// frameworks to a Dart MethodChannel + EventChannel surface. Responsibilities:
//   * Configure `Wearables` once per process.
//   * Registration: startRegistration, startUnregistration, handleUrl,
//     plus EventChannels for registration_state and active_device.
//   * Streaming: startStreamSession (returns a Flutter TextureRegistry id),
//     stop/pause/resume, plus EventChannels for session_state,
//     session_errors and video_stream_size.
//   * Diagnostics: dumpDiagnostics returns a structured Info.plist + SDK
//     state snapshot for use in host-app debug UI.
//   * Optional: Mock Device Kit pass-throughs when MWDATMockDevice is linked.

import Flutter
import UIKit

#if !canImport(MWDATCore)
#error("Missing MWDATCore. Enable Flutter's Swift Package Manager support: `flutter config --enable-swift-package-manager` and use Xcode 15.4+.")
#endif

#if !canImport(MWDATCamera)
#error("Missing MWDATCamera. Enable Flutter's Swift Package Manager support: `flutter config --enable-swift-package-manager` and use Xcode 15.4+.")
#endif

import MWDATCore
import MWDATCamera
#if canImport(MWDATMockDevice)
import MWDATMockDevice
#endif

// MARK: - Plugin registration

public class MetaWearablesDatPlugin: NSObject, FlutterPlugin {
  // `Wearables.configure()` is global; ensure exactly-once across hot
  // restarts by tracking it in a static.
  private static var didConfigure = false

  // Stream handlers retained on the plugin instance so their cancellation
  // tokens survive past `register(with:)`.
  private let registrationStateHandler = RegistrationStateStreamHandler()
  private let activeDeviceHandler = ActiveDeviceStreamHandler()
  private let devicesHandler = DevicesStreamHandler()
  private let compatibilityHandler = CompatibilityStreamHandler()

  // Streaming. Manager is created lazily on first session start because we
  // need the texture registry from the registrar.
  private var sessionManager: MetaSessionManager?
  private let streamSessionStateHandler = PassthroughStreamHandler()
  private let streamSessionErrorHandler = PassthroughStreamHandler()
  private let deviceSessionStateHandler = PassthroughStreamHandler()
  private let deviceSessionErrorHandler = PassthroughStreamHandler()
  private let videoSizeHandler = PassthroughStreamHandler()
  private let videoFramesHandler = PassthroughStreamHandler()
  private weak var pluginRegistrar: FlutterPluginRegistrar?

  // Mock Device Kit. Lazily created on first use.
  private var mockManager: MetaMockDeviceManager?
  private let mockDevicesHandler = PassthroughStreamHandler()

  // Display (MWDATDisplay). Lazily created on first use.
  private var displayManager: MetaDisplayManager?
  private let displayStateHandler = PassthroughStreamHandler()
  private let displayEventsHandler = PassthroughStreamHandler()

  public static func register(with registrar: FlutterPluginRegistrar) {
    if !didConfigure {
      do {
        try Wearables.configure()
        didConfigure = true
      } catch {
        // Configuration may legitimately fail in unit-test bundles or when
        // the host app's Info.plist `MWDAT` dict is missing. We log instead
        // of crashing so the host app can still call non-DAT APIs.
        print("[meta_wearables_dat_flutter] Wearables.configure() failed: \(error)")
      }
    }

    let methodChannel = FlutterMethodChannel(
      name: "meta_wearables_dat_flutter",
      binaryMessenger: registrar.messenger()
    )

    let registrationStateChannel = FlutterEventChannel(
      name: "meta_wearables_dat_flutter/registration_state",
      binaryMessenger: registrar.messenger()
    )

    let activeDeviceChannel = FlutterEventChannel(
      name: "meta_wearables_dat_flutter/active_device",
      binaryMessenger: registrar.messenger()
    )

    let devicesChannel = FlutterEventChannel(
      name: "meta_wearables_dat_flutter/devices",
      binaryMessenger: registrar.messenger()
    )

    let compatibilityChannel = FlutterEventChannel(
      name: "meta_wearables_dat_flutter/compatibility",
      binaryMessenger: registrar.messenger()
    )

    let streamSessionStateChannel = FlutterEventChannel(
      name: "meta_wearables_dat_flutter/stream_session_state",
      binaryMessenger: registrar.messenger()
    )
    let streamSessionErrorChannel = FlutterEventChannel(
      name: "meta_wearables_dat_flutter/stream_session_errors",
      binaryMessenger: registrar.messenger()
    )
    let deviceSessionStateChannel = FlutterEventChannel(
      name: "meta_wearables_dat_flutter/device_session_state",
      binaryMessenger: registrar.messenger()
    )
    let deviceSessionErrorChannel = FlutterEventChannel(
      name: "meta_wearables_dat_flutter/device_session_errors",
      binaryMessenger: registrar.messenger()
    )
    let videoSizeChannel = FlutterEventChannel(
      name: "meta_wearables_dat_flutter/video_stream_size",
      binaryMessenger: registrar.messenger()
    )
    let videoFramesChannel = FlutterEventChannel(
      name: "meta_wearables_dat_flutter/video_frames",
      binaryMessenger: registrar.messenger()
    )
    let mockDevicesChannel = FlutterEventChannel(
      name: "meta_wearables_dat_flutter/mock_devices",
      binaryMessenger: registrar.messenger()
    )
    let displayStateChannel = FlutterEventChannel(
      name: "meta_wearables_dat_flutter/display_state",
      binaryMessenger: registrar.messenger()
    )
    let displayEventsChannel = FlutterEventChannel(
      name: "meta_wearables_dat_flutter/display_events",
      binaryMessenger: registrar.messenger()
    )

    let instance = MetaWearablesDatPlugin()
    instance.pluginRegistrar = registrar
    registrar.addMethodCallDelegate(instance, channel: methodChannel)
    // Register as a UIApplication delegate so we can auto-forward the
    // Meta AI registration callback URL to `Wearables.shared.handleUrl`.
    // Host apps that use the classic AppDelegate lifecycle (no
    // `UIApplicationSceneManifest` in Info.plist) need no extra wiring —
    // iOS delivers the URL to `application(_:open:options:)` below.
    registrar.addApplicationDelegate(instance)
    // Host apps that DO use a scene manifest need to forward URL events
    // themselves because iOS delivers them via the scene delegate, not
    // the app delegate. The example app's SceneDelegate posts
    // `MetaWearablesDatHandleURL` whenever a URL arrives; we observe it
    // here and feed it to the SDK. Decouples the example (and any host
    // app following the same convention) from `MWDATCore`.
    NotificationCenter.default.addObserver(
      instance,
      selector: #selector(handleURLNotification(_:)),
      name: Notification.Name("MetaWearablesDatHandleURL"),
      object: nil,
    )
    registrationStateChannel.setStreamHandler(instance.registrationStateHandler)
    activeDeviceChannel.setStreamHandler(instance.activeDeviceHandler)
    devicesChannel.setStreamHandler(instance.devicesHandler)
    compatibilityChannel.setStreamHandler(instance.compatibilityHandler)
    streamSessionStateChannel.setStreamHandler(instance.streamSessionStateHandler)
    streamSessionErrorChannel.setStreamHandler(instance.streamSessionErrorHandler)
    deviceSessionStateChannel.setStreamHandler(instance.deviceSessionStateHandler)
    deviceSessionErrorChannel.setStreamHandler(instance.deviceSessionErrorHandler)
    videoSizeChannel.setStreamHandler(instance.videoSizeHandler)
    videoFramesChannel.setStreamHandler(instance.videoFramesHandler)
    mockDevicesChannel.setStreamHandler(instance.mockDevicesHandler)
    instance.mockDevicesHandler.onSinkChange = { [weak instance] sink in
      Task { @MainActor in
        instance?.ensureMockManager().setMockDevicesSink(sink)
      }
    }
    displayStateChannel.setStreamHandler(instance.displayStateHandler)
    displayEventsChannel.setStreamHandler(instance.displayEventsHandler)
    instance.displayStateHandler.onSinkChange = { [weak instance] sink in
      Task { @MainActor in
        instance?.ensureDisplayManager().setDisplayStateSink(sink)
      }
    }
    instance.displayEventsHandler.onSinkChange = { [weak instance] sink in
      Task { @MainActor in
        instance?.ensureDisplayManager().setDisplayEventsSink(sink)
      }
    }
  }

  @MainActor
  private func ensureDisplayManager() -> MetaDisplayManager {
    if let manager = displayManager { return manager }
    let manager = MetaDisplayManager()
    displayManager = manager
    return manager
  }

  @MainActor
  private func ensureMockManager() -> MetaMockDeviceManager {
    if let manager = mockManager { return manager }
    let manager = MetaMockDeviceManager()
    mockManager = manager
    return manager
  }

  /// Lazily builds the session manager on first use and wires its EventSinks
  /// to the matching stream handlers.
  @MainActor
  private func ensureSessionManager() throws -> MetaSessionManager {
    if let manager = sessionManager { return manager }
    guard let registrar = pluginRegistrar else {
      throw NSError(
        domain: "meta_wearables_dat_flutter",
        code: -10,
        userInfo: [NSLocalizedDescriptionKey: "Plugin registrar is gone"]
      )
    }
    let manager = MetaSessionManager(registry: registrar.textures())
    streamSessionStateHandler.onSinkChange = { [weak manager] sink in
      manager?.setSessionStateSink(sink)
    }
    streamSessionErrorHandler.onSinkChange = { [weak manager] sink in
      manager?.setSessionErrorSink(sink)
    }
    deviceSessionStateHandler.onSinkChange = { [weak manager] sink in
      manager?.setDeviceSessionStateSink(sink)
    }
    deviceSessionErrorHandler.onSinkChange = { [weak manager] sink in
      manager?.setDeviceSessionErrorSink(sink)
    }
    videoSizeHandler.onSinkChange = { [weak manager] sink in
      manager?.setVideoSizeSink(sink)
    }
    videoFramesHandler.onSinkChange = { [weak manager] sink in
      manager?.setVideoFramesSink(sink)
    }
    sessionManager = manager
    return manager
  }

  public func handle(
    _ call: FlutterMethodCall,
    result: @escaping FlutterResult
  ) {
    switch call.method {
    case "getPlatformVersion":
      result("iOS \(UIDevice.current.systemVersion)")

    case "requestAndroidPermissions":
      // Documented no-op on iOS: iOS uses Info.plist usage strings, not
      // runtime permission grants. Lets host apps call the API
      // unconditionally.
      result(true)

    case "dumpDiagnostics":
      // FlutterPlugin's `handle` is invoked on the main thread by the
      // engine; assume isolation so we can call the @MainActor
      // dumpDiagnostics() synchronously without spawning a Task.
      result(MainActor.assumeIsolated { Self.dumpDiagnostics() })

    case "startRegistration":
      // Log the same diagnostics the `dumpDiagnostics` method returns so the
      // Xcode console always carries the preflight state when registration
      // fails. Cheap (single bundle read + canOpenURL). Use print() (stderr)
      // so the line surfaces in `flutter run`; NSLog goes to ASL and is
      // silently dropped by the device-log adapter on physical devices.
      let preflight = MainActor.assumeIsolated { Self.dumpDiagnostics() }
      print("[meta_wearables_dat_flutter] startRegistration preflight:\n" +
        Self.prettyPrint(preflight))

      Task { @MainActor in
        do {
          print("[meta_wearables_dat_flutter] startRegistration -> calling Wearables.shared.startRegistration()")
          try await Wearables.shared.startRegistration()
          print("[meta_wearables_dat_flutter] startRegistration -> SDK returned without throwing")
          result(nil)
        } catch let error as RegistrationError {
          let caseName = Self.registrationErrorCaseName(error)
          print("[meta_wearables_dat_flutter] startRegistration FAILED: " +
            "\(caseName) (raw=\(error.rawValue))")
          result(FlutterError(
            code: "REGISTRATION_ERROR",
            message: caseName,
            details: [
              "rawValue": error.rawValue,
              "case": caseName,
              "description": String(describing: error),
              "preflight": preflight,
            ]
          ))
        } catch {
          print("[meta_wearables_dat_flutter] startRegistration FAILED (non-RegistrationError): " +
            String(describing: error))
          result(FlutterError(
            code: "REGISTRATION_ERROR",
            message: error.localizedDescription,
            details: [
              "type": String(describing: type(of: error)),
              "description": String(describing: error),
              "preflight": preflight,
            ]
          ))
        }
      }

    case "startUnregistration":
      Task { @MainActor in
        do {
          try await Wearables.shared.startUnregistration()
          result(nil)
        } catch let error as UnregistrationError {
          let caseName = Self.unregistrationErrorCaseName(error)
          result(FlutterError(
            code: "UNREGISTRATION_ERROR",
            message: caseName,
            details: [
              "case": caseName,
              "rawValue": error.rawValue,
              "description": String(describing: error),
            ]
          ))
        } catch {
          result(FlutterError(
            code: "UNREGISTRATION_ERROR",
            message: error.localizedDescription,
            details: nil
          ))
        }
      }

    case "handleUrl":
      guard
        let args = call.arguments as? [String: Any?],
        let urlString = args["url"] as? String,
        let url = URL(string: urlString)
      else {
        result(FlutterError(
          code: "INVALID_ARGUMENT",
          message: "handleUrl requires { url: String }",
          details: nil
        ))
        return
      }
      print("[meta_wearables_dat_flutter] handleUrl <- received: \(urlString)")
      Task { @MainActor in
        do {
          let consumed = try await Wearables.shared.handleUrl(url)
          print("[meta_wearables_dat_flutter] handleUrl -> SDK consumed=\(consumed)")
          result(consumed)
        } catch let error as WearablesHandleURLError {
          let caseName = Self.handleUrlErrorCaseName(error)
          print("[meta_wearables_dat_flutter] handleUrl FAILED: \(caseName) (raw=\(error.rawValue))")
          result(FlutterError(
            code: "HANDLE_URL_ERROR",
            message: caseName,
            details: [
              "case": caseName,
              "rawValue": error.rawValue,
              "description": String(describing: error),
            ]
          ))
        } catch let error as RegistrationError {
          let caseName = Self.registrationErrorCaseName(error)
          print("[meta_wearables_dat_flutter] handleUrl FAILED: \(caseName) (raw=\(error.rawValue))")
          result(FlutterError(
            code: "REGISTRATION_ERROR",
            message: caseName,
            details: [
              "case": caseName,
              "rawValue": error.rawValue,
              "description": String(describing: error),
            ]
          ))
        } catch {
          print("[meta_wearables_dat_flutter] handleUrl FAILED (non-typed): \(error)")
          result(FlutterError(
            code: "HANDLE_URL_ERROR",
            message: error.localizedDescription,
            details: nil
          ))
        }
      }

    case "getRegistrationState":
      result(Wearables.shared.registrationState.rawValue)

    case "requestCameraPermission":
      Task { @MainActor in
        do {
          let status = try await Wearables.shared.requestPermission(.camera)
          result(status == .granted)
        } catch let error as PermissionError {
          result(FlutterError(
            code: "PERMISSION_ERROR",
            message: String(describing: error),
            details: nil
          ))
        } catch {
          result(FlutterError(
            code: "PERMISSION_ERROR",
            message: error.localizedDescription,
            details: nil
          ))
        }
      }

    case "getCameraPermissionStatus":
      Task { @MainActor in
        do {
          let status = try await Wearables.shared.checkPermissionStatus(.camera)
          result(status == .granted)
        } catch let error as PermissionError {
          result(FlutterError(
            code: "PERMISSION_ERROR",
            message: String(describing: error),
            details: nil
          ))
        } catch {
          result(FlutterError(
            code: "PERMISSION_ERROR",
            message: error.localizedDescription,
            details: nil
          ))
        }
      }

    case "startStreamSession":
      let args = call.arguments as? [String: Any?]
      let deviceUUID = args?["deviceUuid"] as? String
      let fps = (args?["fps"] as? Int) ?? 30
      let qualityRaw = (args?["quality"] as? String) ?? "high"
      let deviceKinds = (args?["deviceKinds"] as? [String]).map(Set.init)
      let videoCodecRaw = (args?["videoCodec"] as? String) ?? "raw"
      let videoCodec: VideoCodec =
        (videoCodecRaw == "hvc1") ? .hvc1 : .raw
      let quality: StreamingResolution = {
        switch qualityRaw {
        case "low": return .low
        case "medium": return .medium
        default: return .high
        }
      }()
      Task { @MainActor in
        let diag = Self.dumpDiagnostics()
        print("[meta_wearables_dat_flutter] startStreamSession " +
          "deviceUuid=\(deviceUUID ?? "<auto>") fps=\(fps) " +
          "quality=\(qualityRaw) kinds=\(deviceKinds ?? []) " +
          "codec=\(videoCodecRaw)")
        print("[meta_wearables_dat_flutter] startStreamSession devices=" +
          String(describing: diag["devices"] ?? [:]))
        do {
          let manager = try ensureSessionManager()
          let id = try await manager.startSession(
            deviceUUID: deviceUUID,
            fps: fps,
            quality: quality,
            deviceKinds: deviceKinds,
            videoCodec: videoCodec,
          )
          print("[meta_wearables_dat_flutter] startStreamSession -> textureId=\(id)")
          result(id)
        } catch let dse as DeviceSessionError {
          let caseName = Self.deviceSessionErrorCaseName(dse)
          print("[meta_wearables_dat_flutter] startStreamSession FAILED: " +
            "DeviceSessionError.\(caseName)")
          result(FlutterError(
            code: "SESSION_ERROR",
            message: caseName,
            details: [
              "case": caseName,
              "description": String(describing: dse),
              "errorDescription": dse.errorDescription ?? "",
              "devices": diag["devices"] ?? [:],
            ]
          ))
        } catch {
          print("[meta_wearables_dat_flutter] startStreamSession FAILED: \(error)")
          result(FlutterError(
            code: "SESSION_ERROR",
            message: error.localizedDescription,
            details: [
              "type": String(describing: type(of: error)),
              "description": String(describing: error),
              "devices": diag["devices"] ?? [:],
            ]
          ))
        }
      }

    case "getDevices":
      Task { @MainActor in
        result(Self.encodeAllDevices())
      }

    case "openFirmwareUpdate":
      Task { @MainActor in
        do {
          try await Wearables.shared.openFirmwareUpdate()
          result(nil)
        } catch {
          result(FlutterError(
            code: "FIRMWARE_UPDATE_ERROR",
            message: error.localizedDescription,
            details: nil
          ))
        }
      }

    case "openDATGlassesAppUpdate":
      Task { @MainActor in
        do {
          try await Wearables.shared.openDATGlassesAppUpdate()
          result(nil)
        } catch {
          result(FlutterError(
            code: "DAT_GLASSES_APP_UPDATE_ERROR",
            message: error.localizedDescription,
            details: nil
          ))
        }
      }

    case "stopStreamSession":
      Task { @MainActor in
        await sessionManager?.stopSession()
        result(nil)
      }

    case "pauseStreamSession":
      Task { @MainActor in
        await sessionManager?.pauseSession()
        result(nil)
      }

    case "resumeStreamSession":
      Task { @MainActor in
        await sessionManager?.resumeSession()
        result(nil)
      }

    case "startDisplaySession":
      let args = call.arguments as? [String: Any?]
      let deviceUUID = args?["deviceUuid"] as? String
      Task { @MainActor in
        do {
          try await ensureDisplayManager().startDisplaySession(
            deviceUUID: deviceUUID,
          )
          result(nil)
        } catch let dse as DeviceSessionError {
          result(FlutterError(
            code: "DEVICE_SESSION_ERROR",
            message: Self.deviceSessionErrorCaseName(dse),
            details: ["description": String(describing: dse)]
          ))
        } catch {
          result(FlutterError(
            code: "DEVICE_SESSION_ERROR",
            message: error.localizedDescription,
            details: ["description": String(describing: error)]
          ))
        }
      }

    case "sendDisplayView":
      let args = call.arguments as? [String: Any?]
      let view = (args?["view"] as? [String: Any]) ?? [:]
      Task { @MainActor in
        do {
          try await ensureDisplayManager().sendDisplayView(view)
          result(nil)
        } catch {
          result(FlutterError(
            code: "DEVICE_SESSION_ERROR",
            message: error.localizedDescription,
            details: ["description": String(describing: error)]
          ))
        }
      }

    case "stopDisplaySession":
      Task { @MainActor in
        await displayManager?.stopDisplaySession()
        result(nil)
      }

    case "enableMockDevice":
      let args = call.arguments as? [String: Any?]
      let initiallyRegistered = (args?["initiallyRegistered"] as? Bool) ?? true
      let initialPermissionsGranted =
        (args?["initialPermissionsGranted"] as? Bool) ?? true
      Task { @MainActor in
        ensureMockManager().enable(
          initiallyRegistered: initiallyRegistered,
          initialPermissionsGranted: initialPermissionsGranted,
        )
        result(nil)
      }

    case "disableMockDevice":
      Task { @MainActor in
        ensureMockManager().disable()
        result(nil)
      }

    case "isMockDeviceEnabled":
      Task { @MainActor in
        result(ensureMockManager().isEnabled())
      }

    case "pairMockRayBanMeta":
      Task { @MainActor in
        let uuid = ensureMockManager().pairRayBanMeta()
        result(uuid)
      }

    case "pairedMockDevices":
      Task { @MainActor in
        result(ensureMockManager().pairedDevices())
      }

    case "unpairMockDevice":
      let args = call.arguments as? [String: Any?]
      let uuid = args?["uuid"] as? String ?? ""
      Task { @MainActor in
        do {
          try ensureMockManager().unpair(uuid: uuid)
          result(nil)
        } catch {
          result(FlutterError(
            code: "MOCK_ERROR",
            message: error.localizedDescription,
            details: nil
          ))
        }
      }

    case "mockPowerOn", "mockPowerOff", "mockDon", "mockDoff", "mockFold", "mockUnfold":
      let args = call.arguments as? [String: Any?]
      let uuid = args?["uuid"] as? String ?? ""
      let methodName = call.method
      Task { @MainActor in
        do {
          let manager = ensureMockManager()
          switch methodName {
          case "mockPowerOn": try manager.powerOn(uuid: uuid)
          case "mockPowerOff": try manager.powerOff(uuid: uuid)
          case "mockDon": try manager.don(uuid: uuid)
          case "mockDoff": try manager.doff(uuid: uuid)
          case "mockFold": try manager.fold(uuid: uuid)
          case "mockUnfold": try manager.unfold(uuid: uuid)
          default: break
          }
          result(nil)
        } catch {
          result(FlutterError(
            code: "MOCK_ERROR",
            message: error.localizedDescription,
            details: nil
          ))
        }
      }

    case "setMockCameraFacing":
      let args = call.arguments as? [String: Any?]
      let uuid = args?["uuid"] as? String ?? ""
      let facingRaw = (args?["facing"] as? String) ?? "rear"
      let facing: CameraFacing = (facingRaw == "front") ? .front : .back
      Task { @MainActor in
        do {
          try await ensureMockManager().setCameraFacing(uuid: uuid, facing: facing)
          result(nil)
        } catch {
          result(FlutterError(
            code: "MOCK_ERROR",
            message: error.localizedDescription,
            details: nil
          ))
        }
      }

    case "setMockCameraFeed":
      let args = call.arguments as? [String: Any?]
      let uuid = args?["uuid"] as? String ?? ""
      let path = args?["filePath"] as? String
      Task { @MainActor in
        do {
          try await ensureMockManager().setCameraFeed(uuid: uuid, filePath: path)
          result(nil)
        } catch {
          result(FlutterError(
            code: "MOCK_ERROR",
            message: error.localizedDescription,
            details: nil
          ))
        }
      }

    case "setMockCapturedImage":
      let args = call.arguments as? [String: Any?]
      let uuid = args?["uuid"] as? String ?? ""
      let path = args?["filePath"] as? String
      Task { @MainActor in
        do {
          try await ensureMockManager().setCapturedImage(uuid: uuid, filePath: path)
          result(nil)
        } catch {
          result(FlutterError(
            code: "MOCK_ERROR",
            message: error.localizedDescription,
            details: nil
          ))
        }
      }

    case "setMockPermission", "setMockPermissionRequestResult":
      let args = call.arguments as? [String: Any?]
      let perm = args?["permission"] as? String ?? ""
      let status = args?["status"] as? String ?? ""
      let methodName = call.method
      Task { @MainActor in
        do {
          let manager = ensureMockManager()
          if methodName == "setMockPermission" {
            try manager.setPermission(permission: perm, status: status)
          } else {
            try manager.setPermissionRequestResult(
              permission: perm,
              status: status,
            )
          }
          result(nil)
        } catch {
          result(FlutterError(
            code: "MOCK_ERROR",
            message: error.localizedDescription,
            details: nil
          ))
        }
      }

    case "enableBackgroundStreaming":
      Task { @MainActor in
        do {
          try BackgroundStreamingController.shared.enable()
          // Hand the software-only flag to the session manager, if any.
          sessionManager?.setBackgroundStreamingEnabled(true)
          result(nil)
        } catch {
          result(FlutterError(
            code: "SESSION_ERROR",
            message: "Failed to enable background streaming: " +
              error.localizedDescription,
            details: nil,
          ))
        }
      }

    case "disableBackgroundStreaming":
      Task { @MainActor in
        BackgroundStreamingController.shared.disable()
        sessionManager?.setBackgroundStreamingEnabled(false)
        result(nil)
      }

    case "capturePhoto":
      let args = call.arguments as? [String: Any?]
      let formatRaw = (args?["format"] as? String) ?? "jpeg"
      let format: PhotoCaptureFormat = (formatRaw == "heic") ? .heic : .jpeg
      Task { @MainActor in
        do {
          guard let manager = sessionManager else {
            throw NSError(
              domain: "meta_wearables_dat_flutter",
              code: -30,
              userInfo: [
                NSLocalizedDescriptionKey:
                  "No stream session - call startStreamSession first",
              ],
            )
          }
          let photo = try await manager.capturePhoto(format: format)
          let outFormat = (photo.format == .heic) ? "heic" : "jpeg"
          result([
            "bytes": FlutterStandardTypedData(bytes: photo.data),
            "format": outFormat,
          ] as [String: Any])
        } catch {
          result(FlutterError(
            code: "CAPTURE_ERROR",
            message: error.localizedDescription,
            details: nil
          ))
        }
      }

    case "captureLatestFrame":
      let args = call.arguments as? [String: Any?]
      let quality = (args?["quality"] as? Double).map { CGFloat($0) } ?? 0.8
      Task { @MainActor in
        guard let manager = sessionManager else {
          print("[MetaGlassStreamDiag] captureLatestFrame: no session manager")
          result(nil)
          return
        }
        guard let data = manager.captureLatestFrameJpeg(quality: quality) else {
          print("[MetaGlassStreamDiag] captureLatestFrame: no buffer yet")
          result(nil)
          return
        }
        print("[MetaGlassStreamDiag] captureLatestFrame: jpeg \(data.count) bytes")
        result(FlutterStandardTypedData(bytes: data))
      }

    default:
      result(FlutterMethodNotImplemented)
    }
  }

  // MARK: - UIApplicationDelegate (deep-link forwarding)

  /// Auto-forwards the Meta AI registration-callback URL to the SDK.
  ///
  /// When the host app calls `MetaWearablesDat.startRegistration()`, Meta
  /// AI opens its permission UI and (on approval) redirects back to the
  /// host app via its declared URL scheme (e.g.
  /// `metawearablesdatexample://...`). Without this hook the host app
  /// would have to wire its own deep-link plumbing to call
  /// `MetaWearablesDat.handleUrl(url)`. Because the plugin already owns
  /// `Wearables.shared`, we can do it transparently — the existing
  /// `registrationStateStream` and `activeDeviceStream` observers pick
  /// up the resulting state change and surface it to Dart without any
  /// host-app code.
  ///
  /// Returns `true` when the SDK consumed the URL so the system stops
  /// the AppDelegate chain; otherwise `false` so other plugins / the
  /// host app's own AppDelegate get a shot.
  public func application(
    _ application: UIApplication,
    open url: URL,
    options: [UIApplication.OpenURLOptionsKey: Any] = [:]
  ) -> Bool {
    print("[meta_wearables_dat_flutter] application(open:) <- \(url)")
    consumeUrl(url, source: "application(open:)")
    return true
  }

  /// Notification-based URL bridge used by host apps with a
  /// `UISceneDelegate`. They post `MetaWearablesDatHandleURL` from
  /// `scene(_:openURLContexts:)` with a `url: URL` in `userInfo`.
  @objc private func handleURLNotification(_ notification: Notification) {
    guard let url = notification.userInfo?["url"] as? URL else {
      print("[meta_wearables_dat_flutter] handleURLNotification missing url")
      return
    }
    print("[meta_wearables_dat_flutter] handleURLNotification <- \(url)")
    consumeUrl(url, source: "handleURLNotification")
  }

  /// Forwards the URL to the SDK in a `Task` so we can return synchronously
  /// to the UIApplication / scene delegate callers.
  private func consumeUrl(_ url: URL, source: String) {
    Task { @MainActor in
      do {
        let consumed = try await Wearables.shared.handleUrl(url)
        print("[meta_wearables_dat_flutter] \(source) consumed=\(consumed)")
      } catch {
        print("[meta_wearables_dat_flutter] \(source) handleUrl FAILED: \(error)")
      }
    }
  }

  // MARK: - Diagnostics

  /// Returns a structured snapshot of everything the iOS DAT SDK validates
  /// at `startRegistration()` time. Surfaced through the `dumpDiagnostics`
  /// method channel call so host apps can show it in their UI when a
  /// registration error happens, and also `print`-ed on every
  /// `startRegistration` call. Pure read; no side effects.
  ///
  /// Marked `@MainActor` because `Wearables.shared.devices` /
  /// `deviceForIdentifier` / `Device.linkState` are all main-actor
  /// isolated by the SDK.
  @MainActor
  static func dumpDiagnostics() -> [String: Any] {
    let info = Bundle.main.infoDictionary ?? [:]
    let mwdat = info["MWDAT"] as? [String: Any] ?? [:]
    let queries = info["LSApplicationQueriesSchemes"] as? [String] ?? []
    let urlTypes = info["CFBundleURLTypes"] as? [[String: Any]] ?? []
    let urlSchemes = urlTypes
      .compactMap { $0["CFBundleURLSchemes"] as? [String] }
      .flatMap { $0 }

    let fbViewappURL = URL(string: "fb-viewapp://")!
    let canOpenFbViewapp = UIApplication.shared.canOpenURL(fbViewappURL)
    // `fb-viewapp` is the scheme the SDK preflights when opening Meta AI.
    // If `canOpenURL` returns false, the most common cause is a missing
    // `LSApplicationQueriesSchemes` entry, but it can also mean Meta AI
    // is not installed.

    let regState = Wearables.shared.registrationState
    let regStateName: String
    switch regState {
    case .unavailable: regStateName = "unavailable"
    case .available: regStateName = "available"
    case .registering: regStateName = "registering"
    case .registered: regStateName = "registered"
    @unknown default: regStateName = "unknown(\(regState.rawValue))"
    }

    // Devices the SDK currently knows about and the state of their
    // BLE link. `noEligibleDevice` from `startStreamSession` almost
    // always means every device here has `linkState != connected`.
    // Surface enough info that the app UI can tell the user what to
    // do (turn glasses on, take them out of the case, don them).
    let deviceIds = Wearables.shared.devices
    var deviceDumps: [[String: Any]] = []
    for id in deviceIds {
      let device = Wearables.shared.deviceForIdentifier(id)
      let linkStateName: String
      switch device?.linkState {
      case .disconnected?: linkStateName = "disconnected"
      case .connecting?: linkStateName = "connecting"
      case .connected?: linkStateName = "connected"
      case nil: linkStateName = "unknown"
      @unknown default: linkStateName = "unknown"
      }
      let kindName: String
      switch device?.deviceType() {
      case .rayBanMeta?, .rayBanMetaOptics?: kindName = "rayBanMeta"
      case .metaRayBanDisplay?: kindName = "rayBanDisplay"
      case .oakleyMetaHSTN?, .oakleyMetaVanguard?: kindName = "oakleyMeta"
      case .unknown?, .none: kindName = "unknown"
      @unknown default: kindName = "unknown"
      }
      deviceDumps.append([
        "id": id,
        "name": device?.nameOrId() ?? id,
        "kind": kindName,
        "linkState": linkStateName,
      ])
    }

    return [
      "platform": "iOS",
      "iosVersion": UIDevice.current.systemVersion,
      "bundleId": Bundle.main.bundleIdentifier ?? "<unknown>",
      "bundleVersion": (info["CFBundleShortVersionString"] as? String) ?? "",
      "wearablesConfigured": Self.didConfigure,
      "registrationState": [
        "raw": regState.rawValue,
        "name": regStateName,
      ],
      "devices": [
        "count": deviceDumps.count,
        "list": deviceDumps,
        "anyConnected": deviceDumps.contains { ($0["linkState"] as? String) == "connected" },
      ] as [String: Any],
      "infoPlist": [
        "MWDAT": mwdat,
        "LSApplicationQueriesSchemes": queries,
        "CFBundleURLSchemes": urlSchemes,
      ],
      "preflight": [
        "canOpenFbViewapp": canOpenFbViewapp,
        "fbViewappInQueriesSchemes": queries.contains("fb-viewapp"),
        "mwdatHasMetaAppID":
          (mwdat["MetaAppID"] as? String).map { !$0.isEmpty } ?? false,
        "mwdatHasAppLinkURLScheme":
          (mwdat["AppLinkURLScheme"] as? String).map { !$0.isEmpty } ?? false,
        "mwdatHasEmptyClientToken":
          (mwdat["ClientToken"] as? String) == "",
        "mwdatHasEmptyTeamID":
          (mwdat["TeamID"] as? String) == "",
      ],
    ]
  }

  /// Pretty-prints a `[String: Any]` (one level deep is enough for our
  /// needs) for `NSLog`. Avoids JSONSerialization because some values
  /// (Bool, NSDictionary) round-trip oddly through it; we just want a
  /// readable string in the Xcode console.
  static func prettyPrint(_ dict: [String: Any]) -> String {
    return dict
      .sorted { $0.key < $1.key }
      .map { (k, v) in "\n  \(k) = \(v)" }
      .joined()
  }

  /// String name of a `RegistrationError` enum case. Mirrored on the Dart
  /// side as `details["case"]`. We don't rely on `String(describing:)`
  /// directly because it can include the enum's namespace prefix on some
  /// builds.
  /// String name of a `DeviceSessionError` case. Mirrored on the Dart
  /// side as `details["case"]`. Keeps the unexpectedError payload in the
  /// caseName so downstream UI can show the SDK's free-form reason
  /// without parsing `errorDescription`.
  static func deviceSessionErrorCaseName(_ error: DeviceSessionError) -> String {
    // Derived from `String(describing:)` so this keeps compiling across SDK
    // releases that add cases (DAT 0.7.0 added
    // `datAppOnTheGlassesUpdateRequired`). The raw value is already a readable
    // case label, e.g. `noEligibleDevice` or `unexpectedError(...)`.
    return String(describing: error)
  }

  static func registrationErrorCaseName(_ error: RegistrationError) -> String {
    switch error {
    case .alreadyRegistered: return "alreadyRegistered"
    case .configurationInvalid: return "configurationInvalid"
    case .metaAINotInstalled: return "metaAINotInstalled"
    case .networkUnavailable: return "networkUnavailable"
    case .unknown: return "unknown"
    @unknown default: return "unknown(\(error.rawValue))"
    }
  }

  /// String name of an `UnregistrationError` case, used as the typed
  /// sub-code on the Dart side.
  static func unregistrationErrorCaseName(_ error: UnregistrationError) -> String {
    switch error {
    case .alreadyUnregistered: return "alreadyUnregistered"
    case .configurationInvalid: return "configurationInvalid"
    case .metaAINotInstalled: return "metaAINotInstalled"
    case .unknown: return "unknown"
    @unknown default: return "unknown(\(error.rawValue))"
    }
  }

  /// String name of a `WearablesHandleURLError` case, used as the typed
  /// sub-code on the Dart side.
  static func handleUrlErrorCaseName(_ error: WearablesHandleURLError) -> String {
    switch error {
    case .registrationError: return "registrationError"
    case .unregistrationError: return "unregistrationError"
    @unknown default: return "unknown(\(error.rawValue))"
    }
  }

  /// Returns a list of `DeviceInfo` maps for every paired device the SDK
  /// currently knows about. Shape matches `DeviceInfo.fromMap` on Dart.
  @MainActor
  static func encodeAllDevices() -> [[String: Any]] {
    return Wearables.shared.devices.map { id in
      let device = Wearables.shared.deviceForIdentifier(id)
      let name = device?.nameOrId() ?? id
      return [
        "uuid": id,
        "name": name,
        "kind": Self.kindName(for: device?.deviceType()),
        "linkState": Self.linkStateName(for: device?.linkState),
      ]
    }
  }

  @MainActor
  static func linkStateName(for linkState: LinkState?) -> String {
    switch linkState {
    case .connected?: return "connected"
    case .connecting?: return "connecting"
    case .disconnected?: return "disconnected"
    case nil: return "unknown"
    }
  }

  @MainActor
  static func kindName(for deviceType: DeviceType?) -> String {
    switch deviceType {
    case .rayBanMeta?, .rayBanMetaOptics?: return "rayBanMeta"
    case .metaRayBanDisplay?: return "rayBanDisplay"
    case .oakleyMetaHSTN?, .oakleyMetaVanguard?: return "oakleyMeta"
    case .unknown?, .none: return "unknown"
    @unknown default: return "unknown"
    }
  }
}

// MARK: - Passthrough stream handler

/// Tiny `FlutterStreamHandler` that simply hands its EventSink to a callback.
/// Used by the streaming pipeline so the session manager - rather than this
/// handler - owns when to emit values.
///
/// Re-fires `onSinkChange` whenever the callback is re-assigned so the
/// session manager catches up on listeners that subscribed before it was
/// lazily built.
private final class PassthroughStreamHandler: NSObject, FlutterStreamHandler {
  var onSinkChange: ((FlutterEventSink?) -> Void)? {
    didSet { onSinkChange?(sink) }
  }
  private var sink: FlutterEventSink?

  func onListen(
    withArguments arguments: Any?,
    eventSink events: @escaping FlutterEventSink
  ) -> FlutterError? {
    sink = events
    onSinkChange?(events)
    return nil
  }

  func onCancel(withArguments arguments: Any?) -> FlutterError? {
    sink = nil
    onSinkChange?(nil)
    return nil
  }
}

// MARK: - Stream handlers

/// Forwards `Wearables.shared.registrationStateStream()` events to a Flutter
/// EventSink as `Int` values matching `RegistrationState.fromInt` on the
/// Dart side. Seeds the initial value so a brand-new listener does not need
/// to wait for the next state change.
private final class RegistrationStateStreamHandler: NSObject, FlutterStreamHandler {
  private var task: Task<Void, Never>?

  func onListen(
    withArguments arguments: Any?,
    eventSink events: @escaping FlutterEventSink
  ) -> FlutterError? {
    task?.cancel()
    task = Task { @MainActor in
      // Seed the current value first so UI built on `StreamBuilder` shows
      // the correct state on initial subscribe.
      events(Wearables.shared.registrationState.rawValue)
      for await state in Wearables.shared.registrationStateStream() {
        if Task.isCancelled { break }
        events(state.rawValue)
      }
    }
    return nil
  }

  func onCancel(withArguments arguments: Any?) -> FlutterError? {
    task?.cancel()
    task = nil
    return nil
  }
}

/// Forwards `AutoDeviceSelector` events to a Flutter EventSink as either
/// a serialised `DeviceInfo` map or `nil` when no device is active.
/// Long-lived: created once and held by the plugin instance.
private final class ActiveDeviceStreamHandler: NSObject, FlutterStreamHandler {
  private var task: Task<Void, Never>?
  private var selector: AutoDeviceSelector?

  func onListen(
    withArguments arguments: Any?,
    eventSink events: @escaping FlutterEventSink
  ) -> FlutterError? {
    task?.cancel()
    let auto = AutoDeviceSelector(wearables: Wearables.shared)
    selector = auto

    task = Task { @MainActor in
      // Seed the current value to avoid the "stuck waiting for first event"
      // case when a device is already attached at subscribe time.
      events(Self.encode(auto.activeDevice))
      for await deviceId in auto.activeDeviceStream() {
        if Task.isCancelled { break }
        events(Self.encode(deviceId))
      }
    }
    return nil
  }

  func onCancel(withArguments arguments: Any?) -> FlutterError? {
    task?.cancel()
    task = nil
    selector = nil
    return nil
  }

  /// Serialises a `DeviceIdentifier` (typealias for `String`) to the map
  /// shape that `DeviceInfo.fromMap` expects on the Dart side. Returns
  /// `NSNull` so the Flutter codec emits a Dart `null` when no device is
  /// active.
  @MainActor
  private static func encode(_ id: DeviceIdentifier?) -> Any {
    guard let id else { return NSNull() }
    let device = Wearables.shared.deviceForIdentifier(id)
    let name = device?.nameOrId() ?? id
    return [
      "uuid": id,
      "name": name,
      "kind": MetaWearablesDatPlugin.kindName(for: device?.deviceType()),
      "linkState": MetaWearablesDatPlugin.linkStateName(for: device?.linkState),
    ] as [String: Any]
  }
}

/// Forwards `Wearables.shared.devicesStream()` events as the full list of
/// paired devices (active or not) on the
/// `meta_wearables_dat_flutter/devices` channel. Seeds the current value so
/// fresh subscribers do not need to wait for the next change.
private final class DevicesStreamHandler: NSObject, FlutterStreamHandler {
  private var task: Task<Void, Never>?

  func onListen(
    withArguments arguments: Any?,
    eventSink events: @escaping FlutterEventSink
  ) -> FlutterError? {
    task?.cancel()
    task = Task { @MainActor in
      events(MetaWearablesDatPlugin.encodeAllDevices())
      for await _ in Wearables.shared.devicesStream() {
        if Task.isCancelled { break }
        events(MetaWearablesDatPlugin.encodeAllDevices())
      }
    }
    return nil
  }

  func onCancel(withArguments arguments: Any?) -> FlutterError? {
    task?.cancel()
    task = nil
    return nil
  }
}

/// Forwards per-device `Compatibility` updates on the
/// `meta_wearables_dat_flutter/compatibility` channel. Listens to
/// `Wearables.shared.devicesStream()` for the paired-device set and attaches
/// `Device.addCompatibilityListener` to each new device, dropping the
/// listener when a device disappears. Seeds the current verdict for every
/// already-paired device.
private final class CompatibilityStreamHandler: NSObject, FlutterStreamHandler {
  private var task: Task<Void, Never>?
  private var tokens: [DeviceIdentifier: any AnyListenerToken] = [:]

  func onListen(
    withArguments arguments: Any?,
    eventSink events: @escaping FlutterEventSink
  ) -> FlutterError? {
    task?.cancel()
    task = Task { @MainActor [weak self] in
      // Seed for every currently-known device.
      self?.refreshListeners(events: events)
      for await _ in Wearables.shared.devicesStream() {
        if Task.isCancelled { break }
        self?.refreshListeners(events: events)
      }
    }
    return nil
  }

  func onCancel(withArguments arguments: Any?) -> FlutterError? {
    task?.cancel()
    task = nil
    Task { @MainActor [tokens] in
      for token in tokens.values { await token.cancel() }
    }
    tokens = [:]
    return nil
  }

  @MainActor
  private func refreshListeners(events: @escaping FlutterEventSink) {
    let live = Set(Wearables.shared.devices)
    // Drop listeners for devices that are no longer paired.
    for id in tokens.keys where !live.contains(id) {
      if let token = tokens.removeValue(forKey: id) {
        Task { await token.cancel() }
      }
    }
    // Attach a listener for each new device, seeding its current verdict.
    for id in live where tokens[id] == nil {
      guard let device = Wearables.shared.deviceForIdentifier(id) else { continue }
      events(CompatibilityStreamHandler.encode(
        deviceUuid: id,
        compatibility: device.compatibility(),
      ))
      tokens[id] = device.addCompatibilityListener { [weak self] compat in
        Task { @MainActor in
          _ = self
          events(CompatibilityStreamHandler.encode(
            deviceUuid: id,
            compatibility: compat,
          ))
        }
      }
    }
  }

  private static func encode(
    deviceUuid: String,
    compatibility: Compatibility,
  ) -> [String: Any] {
    let name: String
    switch compatibility {
    case .compatible: name = "compatible"
    case .deviceUpdateRequired: name = "deviceUpdateRequired"
    case .sdkUpdateRequired: name = "sdkUpdateRequired"
    case .undefined: name = "unknown"
    @unknown default: name = "unknown"
    }
    return [
      "deviceUuid": deviceUuid,
      "compatibility": name,
    ]
  }
}
