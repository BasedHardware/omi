import SwiftUI
import UIKit

/// Presents OmiFeedback's transient toasts above Flutter, its platform views, presented sheets and
/// activity overlays. Dart keeps every callback: a toast only reports how it ended. Nothing is
/// persisted or logged.
@available(iOS 16.0, *)
@MainActor
final class NativeToastPresenter: NSObject {
    private struct Active {
        let request: NativeToastRequest
        let completion: (Any?) -> Void
        let timer: Task<Void, Never>
    }

    private let announce: @MainActor (String) -> Void
    private var order = NativeToastOrder()
    private var active: Active?
    private var announced: Int?
    private var windows: [ObjectIdentifier: NativeToastWindow] = [:]
    private var releaseWindows: Task<Void, Never>?
    /// The keyboard's frame in screen coordinates, or null while it is hidden.
    private var keyboard = CGRect.null

    init(announce: @escaping @MainActor (String) -> Void = {
        UIAccessibility.post(notification: .announcement, argument: $0)
    }) {
        self.announce = announce
        super.init()
        let center = NotificationCenter.default
        center.addObserver(self, selector: #selector(keyboardChanged(_:)),
                           name: UIResponder.keyboardWillChangeFrameNotification, object: nil)
        center.addObserver(self, selector: #selector(keyboardHidden(_:)),
                           name: UIResponder.keyboardWillHideNotification, object: nil)
    }

    /// Shows the toast and calls [completion] with its outcome once it ends. A refused request throws,
    /// and the toast that is up stays.
    func show(_ input: Any?, completion: @escaping (Any?) -> Void) throws {
        guard let input else { throw NativeToastRequest.ContractError.invalidToast }
        let request = try NativeToastRequest.decode(input)
        let scenes = Self.visibleScenes()
        guard !scenes.isEmpty, order.accept(request) else { throw NativeToastRequest.ContractError.invalidToast }
        finish(outcome: "replaced")
        releaseWindows?.cancel()
        let id = request.requestId
        let timer = Task { [weak self] in
            try? await Task.sleep(nanoseconds: UInt64(request.durationMs) * 1_000_000)
            if !Task.isCancelled { self?.finish(id: id, outcome: "timeout") }
        }
        active = Active(request: request, completion: completion, timer: timer)
        let visible = Set(scenes.map { ObjectIdentifier($0) })
        for (key, window) in windows where !visible.contains(key) {
            window.isHidden = true
            windows[key] = nil
        }
        for scene in scenes {
            let window = windows[ObjectIdentifier(scene)] ?? makeWindow(scene)
            windows[ObjectIdentifier(scene)] = window
            window.show(request, keyboard: keyboard)
        }
    }

    /// Dart withdrew the toast (hide, a newer fallback or an account-session change).
    func dismiss() { finish(outcome: "invalidated") }

    private func finish(id: Int? = nil, outcome: String) {
        guard let ended = active, id == nil || ended.request.requestId == id else { return }
        active = nil
        ended.timer.cancel()
        for window in windows.values { window.hide() }
        releaseWindows?.cancel()
        // Idle windows are hidden and released once the exit transition finished.
        releaseWindows = Task { [weak self] in
            try? await Task.sleep(nanoseconds: 450_000_000)
            guard let self, !Task.isCancelled, self.active == nil else { return }
            for window in self.windows.values { window.isHidden = true }
            self.windows.removeAll()
        }
        ended.completion(outcome)
    }

    private func makeWindow(_ scene: UIWindowScene) -> NativeToastWindow {
        NativeToastWindow(scene: scene, model: NativeToastModel(finish: { [weak self] id, outcome in
            self?.finish(id: id, outcome: outcome)
        }, appeared: { [weak self] request in
            guard let self, self.active?.request.requestId == request.requestId,
                  self.announced != request.requestId else { return }
            self.announced = request.requestId
            self.announce(request.message)
        }))
    }

    @objc private func keyboardChanged(_ notification: Notification) {
        keyboard = (notification.userInfo?[UIResponder.keyboardFrameEndUserInfoKey] as? NSValue)?.cgRectValue ?? .null
        for window in windows.values { window.updateKeyboard(keyboard) }
    }

    @objc private func keyboardHidden(_ notification: Notification) {
        keyboard = .null
        for window in windows.values { window.updateKeyboard(keyboard) }
    }

    private static func visibleScenes() -> [UIWindowScene] {
        let scenes = UIApplication.shared.connectedScenes.compactMap { $0 as? UIWindowScene }
        let active = scenes.filter { $0.activationState == .foregroundActive }
        return active.isEmpty ? scenes.filter { $0.activationState == .foregroundInactive } : active
    }
}

@available(iOS 16.0, *)
@MainActor
final class NativeToastModel: ObservableObject {
    @Published private(set) var request: NativeToastRequest?
    @Published private(set) var clearance: CGFloat = 0
    /// How far the keyboard reaches above the safe area.
    @Published var keyboard: CGFloat = 0
    @Published var safeBottom: CGFloat = 0
    /// Each toast's frame in window coordinates, by request id, including one still leaving.
    var frames: [Int: CGRect] = [:]
    let finish: (Int, String) -> Void
    let appeared: (NativeToastRequest) -> Void

    init(finish: @escaping (Int, String) -> Void, appeared: @escaping (NativeToastRequest) -> Void) {
        self.finish = finish
        self.appeared = appeared
    }

    var bottomOffset: CGFloat { max(keyboard, clearance) + safeBottom + 12 }

    /// The current toast's frame; every touch outside it passes through.
    var frame: CGRect { request.flatMap { frames[$0.requestId] } ?? .zero }

    func show(_ request: NativeToastRequest) {
        clearance = CGFloat(request.bottomClearance)
        self.request = request
    }

    func hide() { request = nil }
}

/// Sits above the app's own window at `.normal + 1` and passes every touch outside the toast through.
@available(iOS 16.0, *)
@MainActor
private final class NativeToastWindow: UIWindow {
    let model: NativeToastModel
    private let host: NativeToastHostingController

    init(scene: UIWindowScene, model: NativeToastModel) {
        self.model = model
        host = NativeToastHostingController(rootView: NativeToastView(model: model))
        super.init(windowScene: scene)
        windowLevel = .normal + 1
        backgroundColor = .clear
        host.view.backgroundColor = .clear
        rootViewController = host
    }

    required init?(coder: NSCoder) { return nil }

    /// The toast never keeps the key window, so a focused field below keeps its keyboard.
    override func becomeKey() {
        super.becomeKey()
        host.appWindow?.makeKey()
    }

    override func hitTest(_ point: CGPoint, with event: UIEvent?) -> UIView? {
        guard model.frame.contains(point) else { return nil }
        return super.hitTest(point, with: event)
    }

    /// The keyboard's last screen frame, kept so a safe-area change recomputes its overlap.
    private var keyboardFrame = CGRect.null

    override func safeAreaInsetsDidChange() {
        super.safeAreaInsetsDidChange()
        model.safeBottom = safeAreaInsets.bottom
        updateKeyboard(keyboardFrame)
    }

    func show(_ request: NativeToastRequest, keyboard: CGRect) {
        let appWindows = windowScene?.windows.filter { !($0 is NativeToastWindow) } ?? []
        host.appWindow = appWindows.first(where: \.isKeyWindow) ?? appWindows.first
        overrideUserInterfaceStyle = request.appearance == "dark" ? .dark
            : request.appearance == "light" ? .light : .unspecified
        isHidden = false
        model.safeBottom = safeAreaInsets.bottom
        updateKeyboard(keyboard)
        model.show(request)
    }

    func hide() { model.hide() }

    func updateKeyboard(_ frame: CGRect) {
        keyboardFrame = frame
        guard !frame.isNull, let screen = windowScene?.screen else { model.keyboard = 0; return }
        let local = convert(frame, from: screen.coordinateSpace)
        model.keyboard = max(0, bounds.maxY - local.minY - safeAreaInsets.bottom)
    }
}

/// The app's own window keeps deciding the status bar and orientation while a toast is up.
@available(iOS 16.0, *)
private final class NativeToastHostingController: UIHostingController<NativeToastView> {
    weak var appWindow: UIWindow?
    private var source: UIViewController? { appWindow?.rootViewController }
    override var preferredStatusBarStyle: UIStatusBarStyle {
        source?.preferredStatusBarStyle ?? super.preferredStatusBarStyle
    }
    override var prefersStatusBarHidden: Bool { source?.prefersStatusBarHidden ?? super.prefersStatusBarHidden }
    override var supportedInterfaceOrientations: UIInterfaceOrientationMask {
        source?.supportedInterfaceOrientations ?? super.supportedInterfaceOrientations
    }
}

@available(iOS 16.0, *)
struct NativeToastView: View {
    @ObservedObject var model: NativeToastModel
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    var body: some View {
        ZStack(alignment: .bottom) {
            Color.clear
            if let request = model.request {
                NativeToastCapsule(request: request, model: model)
                    .id(request.requestId)
                    .padding(.horizontal, 16)
                    .padding(.bottom, model.bottomOffset)
                    .transition(reduceMotion ? AnyTransition.opacity
                        : AnyTransition.move(edge: .bottom).combined(with: .opacity))
            }
        }
        .animation(reduceMotion ? Animation.easeInOut(duration: 0.2)
                       : Animation.spring(response: 0.35, dampingFraction: 0.86),
                   value: model.request?.requestId)
        .animation(reduceMotion ? nil : Animation.easeOut(duration: 0.25), value: model.bottomOffset)
        .onPreferenceChange(NativeToastFramePreference.self) { frames in model.frames = frames }
        .ignoresSafeArea(.all, edges: .bottom)
    }
}

@available(iOS 16.0, *)
private struct NativeToastCapsule: View {
    let request: NativeToastRequest
    @ObservedObject var model: NativeToastModel
    @Environment(\.dynamicTypeSize) private var dynamicTypeSize
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @State private var drag: CGFloat = 0

    var body: some View {
        content
            .padding(.leading, 16)
            .padding(.trailing, request.closeLabel == nil ? 16 : 4)
            .padding(.vertical, 6)
            .frame(maxWidth: 600)
            // A capsule would clip the corners of tall accessibility-size content.
            .modifier(NativeToastBackground(shape: dynamicTypeSize.isAccessibilitySize
                ? AnyShape(RoundedRectangle(cornerRadius: 24, style: .continuous)) : AnyShape(Capsule())))
            .background(GeometryReader { geometry in
                Color.clear.preference(key: NativeToastFramePreference.self,
                                       value: [request.requestId: geometry.frame(in: .global)])
            })
            .offset(y: drag)
            .gesture(DragGesture(minimumDistance: 8)
                .onChanged { value in drag = max(0, value.translation.height) }
                .onEnded { value in
                    if value.translation.height > 24 {
                        model.finish(request.requestId, "swiped")
                    } else {
                        withAnimation(reduceMotion ? nil : Animation.spring(response: 0.3, dampingFraction: 0.8)) {
                            drag = 0
                        }
                    }
                })
            .accessibilityElement(children: .contain)
            .accessibilityIdentifier("native-toast")
            .environment(\.locale, Locale(identifier: request.locale))
            .environment(\.layoutDirection, request.direction == "rtl" ? .rightToLeft : .leftToRight)
            .onAppear { model.appeared(request) }
    }

    @ViewBuilder private var content: some View {
        if dynamicTypeSize.isAccessibilitySize {
            VStack(alignment: .leading, spacing: 4) {
                HStack(alignment: .firstTextBaseline, spacing: 12) {
                    icon
                    message
                }.padding(.top, 8)
                HStack(spacing: 4) {
                    Spacer(minLength: 0)
                    controls
                }
            }
        } else {
            HStack(spacing: 12) {
                icon
                message
                controls
            }.frame(minHeight: 44)
        }
    }

    @ViewBuilder private var icon: some View {
        if request.symbol == "progress" {
            ProgressView().controlSize(.small)
        } else {
            Image(systemName: request.symbol)
                .foregroundStyle(request.kind == "confirm" ? Color.green : request.kind == "error" ? Color.red : Color.secondary)
                .accessibilityHidden(true)
        }
    }

    private var message: some View {
        Text(request.message)
            .font(.subheadline)
            .lineLimit(4)
            .frame(maxWidth: .infinity, alignment: .leading)
            .accessibilityIdentifier("native-toast-message")
    }

    @ViewBuilder private var controls: some View {
        if let action = request.actionLabel {
            Button(action) { model.finish(request.requestId, "action") }
                .font(.subheadline.weight(.semibold))
                .buttonStyle(.borderless)
                .tint(.primary)
                .frame(minHeight: 44)
                .accessibilityIdentifier("native-toast-action")
        }
        if let close = request.closeLabel {
            Button { model.finish(request.requestId, "closed") } label: {
                Image(systemName: "xmark")
                    .font(.subheadline.weight(.semibold))
                    .frame(minWidth: 44, minHeight: 44)
                    .contentShape(Rectangle())
            }
            .buttonStyle(.borderless)
            .tint(Color.secondary)
            .accessibilityLabel(close)
            .accessibilityIdentifier("native-toast-close")
        }
    }
}

@available(iOS 16.0, *)
private struct NativeToastBackground: ViewModifier {
    let shape: AnyShape
    func body(content: Content) -> some View {
        if #available(iOS 26.0, *) {
            content.glassEffect(.regular.interactive(), in: shape)
        } else {
            content.background(.regularMaterial, in: shape)
        }
    }
}

private struct NativeToastFramePreference: PreferenceKey {
    static var defaultValue: [Int: CGRect] { [:] }
    static func reduce(value: inout [Int: CGRect], nextValue: () -> [Int: CGRect]) {
        value.merge(nextValue(), uniquingKeysWith: { _, latest in latest })
    }
}
