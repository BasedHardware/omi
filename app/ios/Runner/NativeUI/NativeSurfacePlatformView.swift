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
        container = NativeHostingContainer(frame: frame, rootView: NativeSurfaceView(state: state))
        super.init()
        channel.setMethodCallHandler { [weak state] call, result in
            guard let state else { result(nil); return }
            do {
                switch call.method {
                case "update":
                    guard let args = call.arguments else { throw NativeSurfaceSnapshot.ContractError.invalidSnapshot }
                    state.update(try NativeSurfaceSnapshot.decode(args))
                    result(nil)
                case "invalidate": state.invalidate(); result(nil)
                default: result(FlutterMethodNotImplemented)
                }
            } catch { result(FlutterError(code: "invalid_native_snapshot", message: nil, details: nil)) }
        }
    }
    func view() -> UIView { container }
    deinit { channel.setMethodCallHandler(nil) }
}

private enum NativeSurfaceError: Error { case channel(String) }
