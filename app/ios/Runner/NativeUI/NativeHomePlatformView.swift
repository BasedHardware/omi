import Flutter
import SwiftUI
import UIKit

@MainActor
final class NativeHomeViewFactory: NSObject, @preconcurrency FlutterPlatformViewFactory {
    private let messenger: FlutterBinaryMessenger

    init(messenger: FlutterBinaryMessenger) { self.messenger = messenger }

    func createArgsCodec() -> FlutterMessageCodec & NSObjectProtocol { FlutterStandardMessageCodec.sharedInstance() }

    func create(withFrame frame: CGRect, viewIdentifier viewId: Int64, arguments args: Any?) -> FlutterPlatformView {
        guard #available(iOS 16.0, *) else { return UnavailableNativeHomeView() }
        guard let args, let snapshot = try? NativeHomeSnapshot.decode(args) else {
            return RejectedNativeHomeView(viewId: viewId, messenger: messenger)
        }
        return NativeHomePlatformView(frame: frame, viewId: viewId, snapshot: snapshot, messenger: messenger)
    }
}

private final class UnavailableNativeHomeView: NSObject, FlutterPlatformView {
    private let content = UIView()
    func view() -> UIView { content }
}

/// A refused creation snapshot never becomes a blank Home: every update reports the rejection,
/// so Dart restores the classic Flutter Home.
@MainActor
private final class RejectedNativeHomeView: NSObject, @preconcurrency FlutterPlatformView {
    private let content = UIView()
    private let channel: FlutterMethodChannel

    init(viewId: Int64, messenger: FlutterBinaryMessenger) {
        channel = FlutterMethodChannel(name: "com.omi.native_ui/home/\(viewId)", binaryMessenger: messenger)
        super.init()
        channel.setMethodCallHandler { call, result in
            switch call.method {
            case "update": result(FlutterError(code: "invalid_native_snapshot", message: nil, details: nil))
            case "invalidate": result(nil)
            default: result(FlutterMethodNotImplemented)
            }
        }
    }

    func view() -> UIView { content }
    deinit { channel.setMethodCallHandler(nil) }
}

@available(iOS 16.0, *)
@MainActor
private final class NativeHomePlatformView: NSObject, @preconcurrency FlutterPlatformView {
    private let channel: FlutterMethodChannel
    private let state: NativeHomeState
    private let container: NativeHostingContainer<NativeHomeView>

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
        container = NativeHostingContainer(frame: frame, rootView: NativeHomeView(state: state), appearance: snapshot.appearance)
        super.init()
        channel.setMethodCallHandler { [weak state, weak container] call, result in
            guard let state else { result(nil); return }
            switch call.method {
            case "update":
                do {
                    guard let arguments = call.arguments else { throw NativeHomeSnapshot.ContractError.invalidSnapshot }
                    state.update(try NativeHomeSnapshot.decode(arguments))
                    container?.updateAppearance(state.snapshot.appearance)
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
final class NativeHostingContainer<Content: View>: UIView {
    private let host: UIHostingController<Content>
    private var hostedConstraints: [NSLayoutConstraint] = []

    init(frame: CGRect, rootView: Content, appearance: String) {
        host = UIHostingController(rootView: rootView)
        super.init(frame: frame)
        updateAppearance(appearance)
        host.view.backgroundColor = .clear
        host.view.translatesAutoresizingMaskIntoConstraints = false
    }

    required init?(coder: NSCoder) { return nil }

    // A child hosting controller cannot reliably apply a preferredColorScheme
    // presentation preference through Flutter's parent controller. Set its UIKit
    // traits as well so native bars, lists and controls share the saved choice.
    func updateAppearance(_ appearance: String) {
        let style: UIUserInterfaceStyle = appearance == "dark" ? .dark : appearance == "light" ? .light : .unspecified
        overrideUserInterfaceStyle = style
        host.overrideUserInterfaceStyle = style
    }

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
                    // Establish ownership before the hosting view enters the
                    // window, so SwiftUI installs navigation during appearance.
                    parent.addChild(host)
                    addSubview(host.view)
                    hostedConstraints = [
                        host.view.leadingAnchor.constraint(equalTo: leadingAnchor),
                        host.view.trailingAnchor.constraint(equalTo: trailingAnchor),
                        host.view.topAnchor.constraint(equalTo: topAnchor),
                        host.view.bottomAnchor.constraint(equalTo: bottomAnchor),
                    ]
                    NSLayoutConstraint.activate(hostedConstraints)
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
        NSLayoutConstraint.deactivate(hostedConstraints)
        hostedConstraints.removeAll()
        host.view.removeFromSuperview()
        host.removeFromParent()
    }
}
