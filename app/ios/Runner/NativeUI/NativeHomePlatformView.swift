import Flutter
import SwiftUI
import UIKit

@MainActor
final class NativeHomeViewFactory: NSObject, @preconcurrency FlutterPlatformViewFactory {
    private let messenger: FlutterBinaryMessenger

    init(messenger: FlutterBinaryMessenger) { self.messenger = messenger }

    func createArgsCodec() -> FlutterMessageCodec & NSObjectProtocol { FlutterStandardMessageCodec.sharedInstance() }

    func create(withFrame frame: CGRect, viewIdentifier viewId: Int64, arguments args: Any?) -> FlutterPlatformView {
        guard #available(iOS 16.0, *), let args,
              let snapshot = try? NativeHomeSnapshot.decode(args) else {
            return UnavailableNativeHomeView()
        }
        return NativeHomePlatformView(frame: frame, viewId: viewId, snapshot: snapshot, messenger: messenger)
    }
}

private final class UnavailableNativeHomeView: NSObject, FlutterPlatformView {
    private let content = UIView()
    func view() -> UIView { content }
}

@available(iOS 16.0, *)
@MainActor
private final class NativeHomePlatformView: NSObject, @preconcurrency FlutterPlatformView {
    private let channel: FlutterMethodChannel
    private let state: NativeHomeState
    private let container: NativeHostingContainer

    init(frame: CGRect, viewId: Int64, snapshot: NativeHomeSnapshot, messenger: FlutterBinaryMessenger) {
        let channel = FlutterMethodChannel(name: "com.omi.native_ui/home/\(viewId)", binaryMessenger: messenger)
        self.channel = channel
        state = NativeHomeState(snapshot: snapshot) { method, id in
            try await withCheckedThrowingContinuation { continuation in
                channel.invokeMethod(method, arguments: id) { response in
                    if let error = response as? FlutterError {
                        continuation.resume(throwing: NativePresentationError.channel(error.code))
                    } else if (response as AnyObject?) === FlutterMethodNotImplemented {
                        continuation.resume(throwing: NativePresentationError.unsupportedAction)
                    } else if method == "detail", let response {
                        do {
                            let data = try SafeJSON.data(withJSONObject: response)
                            continuation.resume(returning: try JSONDecoder().decode(NativeConversation.self, from: data))
                        } catch {
                            continuation.resume(throwing: error)
                        }
                    } else {
                        continuation.resume(returning: nil)
                    }
                }
            }
        }
        container = NativeHostingContainer(frame: frame, rootView: NativeHomeView(state: state))
        super.init()
        channel.setMethodCallHandler { [weak state] call, result in
            guard let state else { result(nil); return }
            switch call.method {
            case "update":
                do {
                    guard let arguments = call.arguments else { throw NativeHomeSnapshot.ContractError.invalidSnapshot }
                    state.update(try NativeHomeSnapshot.decode(arguments))
                    result(nil)
                } catch {
                    result(FlutterError(code: "invalid_native_snapshot", message: nil, details: nil))
                }
            case "invalidate":
                state.invalidate()
                result(nil)
            default: result(FlutterMethodNotImplemented)
            }
        }
    }

    func view() -> UIView { container }

    deinit { channel.setMethodCallHandler(nil) }
}

private enum NativePresentationError: Error {
    case channel(String)
    case unsupportedAction
}

/// SwiftUI gets proper UIKit controller containment, including trait and safe-area changes.
@available(iOS 16.0, *)
@MainActor
private final class NativeHostingContainer: UIView {
    private let host: UIHostingController<NativeHomeView>

    init(frame: CGRect, rootView: NativeHomeView) {
        host = UIHostingController(rootView: rootView)
        super.init(frame: frame)
        host.view.backgroundColor = .clear
        host.view.translatesAutoresizingMaskIntoConstraints = false
        addSubview(host.view)
        NSLayoutConstraint.activate([
            host.view.leadingAnchor.constraint(equalTo: leadingAnchor),
            host.view.trailingAnchor.constraint(equalTo: trailingAnchor),
            host.view.topAnchor.constraint(equalTo: topAnchor),
            host.view.bottomAnchor.constraint(equalTo: bottomAnchor),
        ])
    }

    required init?(coder: NSCoder) { return nil }

    override func didMoveToWindow() {
        super.didMoveToWindow()
        if window == nil {
            detach()
            return
        }
        var responder: UIResponder? = superview
        while let current = responder {
            if let parent = current as? UIViewController {
                if host.parent !== parent {
                    detach()
                    parent.addChild(host)
                    host.didMove(toParent: parent)
                }
                return
            }
            responder = current.next
        }
    }

    private func detach() {
        guard host.parent != nil else { return }
        host.willMove(toParent: nil)
        host.removeFromParent()
    }
}
