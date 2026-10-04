import Flutter
import SwiftUI
import UIKit

@MainActor
final class NativeSurfaceViewFactory: NSObject, @preconcurrency FlutterPlatformViewFactory {
    private let messenger: FlutterBinaryMessenger
    init(messenger: FlutterBinaryMessenger) { self.messenger = messenger }
    func createArgsCodec() -> FlutterMessageCodec & NSObjectProtocol { FlutterStandardMessageCodec.sharedInstance() }
    func create(withFrame frame: CGRect, viewIdentifier viewId: Int64, arguments args: Any?) -> FlutterPlatformView {
        guard #available(iOS 16.0, *), let args,
              let snapshot = try? NativeSurfaceSnapshot.decode(args) else { return UnavailableNativeSurface() }
        return NativeSurfacePlatformView(frame: frame, id: viewId, snapshot: snapshot, messenger: messenger)
    }
}

private final class UnavailableNativeSurface: NSObject, FlutterPlatformView {
    private let content = UIView()
    func view() -> UIView { content }
}

@available(iOS 16.0, *)
@MainActor
private final class NativeSurfacePlatformView: NSObject, @preconcurrency FlutterPlatformView {
    private let channel: FlutterMethodChannel
    private let container: NativeHostingContainer<NativeSurfaceView>
    private let state: NativeSurfaceState

    init(frame: CGRect, id: Int64, snapshot: NativeSurfaceSnapshot, messenger: FlutterBinaryMessenger) {
        let channel = FlutterMethodChannel(name: "com.omi.native_ui/surface/\(id)", binaryMessenger: messenger)
        self.channel = channel
        state = NativeSurfaceState(snapshot: snapshot) { id, value in
            try await withCheckedThrowingContinuation { (continuation: CheckedContinuation<Void, Error>) in
                var arguments: [String: Any] = ["id": id]
                if let value { arguments["value"] = value }
                channel.invokeMethod("action", arguments: arguments) { response in
                    if let error = response as? FlutterError {
                        continuation.resume(throwing: NativeSurfaceError.channel(error.code))
                    } else if (response as AnyObject?) === FlutterMethodNotImplemented {
                        continuation.resume(throwing: NativeSurfaceError.channel("unsupported_action"))
                    } else { continuation.resume() }
                }
            }
        }
        container = NativeHostingContainer(frame: frame, rootView: NativeSurfaceView(state: state), appearance: snapshot.appearance)
        super.init()
        channel.setMethodCallHandler { [weak state, weak container] call, result in
            guard let state else { result(nil); return }
            do {
                switch call.method {
                case "update":
                    guard let args = call.arguments else { throw NativeSurfaceSnapshot.ContractError.invalidSnapshot }
                    state.update(try NativeSurfaceSnapshot.decode(args))
                    container?.updateAppearance(state.snapshot.appearance)
                    result(nil)
                case "invalidate": state.invalidate(); result(nil)
                case "captureImage":
                    guard state.valid, let container, container.window != nil else { result(nil); return }
                    let bounds = container.bounds
                    let scale = container.traitCollection.displayScale
                    guard bounds.width > 0, bounds.height > 0, scale > 0,
                          bounds.width * bounds.height * scale * scale <= 16_000_000 else { result(nil); return }
                    let format = UIGraphicsImageRendererFormat()
                    format.scale = scale
                    let image = UIGraphicsImageRenderer(bounds: bounds, format: format).image { _ in
                        container.drawHierarchy(in: bounds, afterScreenUpdates: true)
                    }
                    guard let data = image.pngData(), data.count <= 16 * 1024 * 1024 else { result(nil); return }
                    result(FlutterStandardTypedData(bytes: data))
                #if targetEnvironment(simulator)
                // Hermetic host tests inspect the received projection, without private text.
                case "debugPresentation":
                    result(["revision": state.snapshot.revision,
                            "toolbar": state.snapshot.toolbar.map { ["id": $0.id, "enabled": $0.enabled] }])
                #endif
                default: result(FlutterMethodNotImplemented)
                }
            } catch { result(FlutterError(code: "invalid_native_snapshot", message: nil, details: nil)) }
        }
    }
    func view() -> UIView { container }
    deinit { channel.setMethodCallHandler(nil) }
}

private enum NativeSurfaceError: Error { case channel(String) }
