import AppKit
import AVFoundation
import CoreGraphics
import SwiftUI

import OmiKit
import OmiUI

// macOS host shell. Bootstrap + injection + window/permission plumbing only;
// all product UI comes from OmiUI.RootView over the injected AppStore.
//
// Injection contract (see ../README.md):
//   - OmiKit.Policy.bridge defaults to DefaultPolicyBridge, which links the
//     real native-core C++ through CNativeCore — nothing to replace here.
//   - Services come from OmiBootstrap: keychain credentials, browser +
//     loopback auth (LoopbackAuthPortal), the authenticated HTTP transport,
//     UserDefaults-backed settings, the CoreBluetooth device transport, and
//     the ScreenCaptureKit rewind engine (OmiRewindEngine).
//   - `-omiDemoData` swaps in the labeled in-memory demo bundle for
//     screenshots and UI exploration (DemoServices.swift).
//
// Window contract (docs/desktop-app.md, values pinned in the RN tree's
// `AppDelegate.mm` / `desktopChrome.ts`):
//   - real behind-window NSVisualEffectView glass (HUDWindow material dark,
//     UnderWindowBackground light), never a full-bleed SwiftUI background;
//   - titlebar material hidden; a titlebar accessory spacer of
//     OmiChromeRowHeight + OmiWindowInset reserves chrome row 1;
//   - the app draws its own traffic-light row (OmiUI Desktop); the host maps
//     its windowCommand notifications onto the real AppKit button paths
//     (performClose:/performMiniaturize:/performZoom:) and publishes
//     Edit → Search (Cmd+K) as the searchCommand notification;
//   - dragging is AppKit's movableByWindowBackground path.

enum OmiChrome {
    /// Must equal `desktopWindowInset` in react-native/src/desktop/desktopChrome.ts.
    static let windowInset: CGFloat = 12.0
    /// Must equal `desktopOmnibarHeight` in react-native/src/desktop/desktopChrome.ts.
    static let chromeRowHeight: CGFloat = 44.0
}

// MARK: - Permissions

/// Permission probing for host-side capture availability. The capture state
/// machine itself lives in OmiUI (AppStore + RewindCaptureControlling).
@MainActor
enum OmiPermissions {
    static func screenRecordingAvailable() -> Bool {
        CGPreflightScreenCaptureAccess()
    }

    static func microphoneAuthorized() -> Bool {
        AVCaptureDevice.authorizationStatus(for: .audio) == .authorized
    }
}

// MARK: - Window dressing

/// Applies the v5 window contract to the hosting NSWindow. Idempotent: the
/// SwiftUI lifecycle calls this more than once per window.
@MainActor
struct OmiWindowDresser {
    let window: NSWindow

    func dress() {
        window.styleMask.insert(.fullSizeContentView)
        window.titlebarAppearsTransparent = true
        window.titleVisibility = .hidden
        window.isMovableByWindowBackground = true
        window.isReleasedWhenClosed = false

        // Reserve chrome row 1 the way AppDelegate.mm does: a titlebar
        // accessory spacer of the full chrome height plus the window inset.
        installChromeSpacer()

        // The app draws its own traffic lights on the chrome row; the system
        // buttons stay hidden behind the full-size content view.
        window.standardWindowButton(.closeButton)?.isHidden = true
        window.standardWindowButton(.miniaturizeButton)?.isHidden = true
        window.standardWindowButton(.zoomButton)?.isHidden = true
    }

    private func installChromeSpacer() {
        let spacerHeight = OmiChrome.chromeRowHeight + OmiChrome.windowInset
        let existing = window.titlebarAccessoryViewControllers.first {
            $0.layoutAttribute == .top && $0.view.frame.height == spacerHeight
        }
        guard existing == nil else { return }
        let spacer = NSTitlebarAccessoryViewController()
        let view = NSView(frame: NSRect(x: 0, y: 0, width: 0, height: spacerHeight))
        spacer.view = view
        spacer.layoutAttribute = .top
        window.addTitlebarAccessoryViewController(spacer)
    }
}

/// Backgrounds the hosting view with real behind-window glass, mirroring
/// `OmiGlassPanelView.mm` (NSVisualEffectMaterialHUDWindow dark /
/// UnderWindowBackground light). Content above it stays transparent so the
/// desktop shows through; light mode paints its opaque paper background in
/// the OmiUI desktop surface.
struct OmiGlassBackground: NSViewRepresentable {
    func makeNSView(context: Context) -> NSVisualEffectView {
        let view = NSVisualEffectView()
        view.material = .hudWindow
        view.blendingMode = .behindWindow
        view.state = .active
        view.wantsLayer = true
        view.autoresizingMask = [.width, .height]
        return view
    }

    func updateNSView(_ view: NSVisualEffectView, context: Context) {
        view.material = view.effectiveAppearance.bestMatch(from: [.aqua, .darkAqua]) == .darkAqua
            ? .hudWindow
            : .underWindowBackground
    }
}

/// Bridges the SwiftUI hierarchy to the window dresser.
struct OmiWindowAccessor: NSViewRepresentable {
    func makeNSView(context: Context) -> NSView {
        let view = NSView()
        DispatchQueue.main.async {
            guard let window = view.window else { return }
            OmiWindowDresser(window: window).dress()
        }
        return view
    }

    func updateNSView(_ view: NSView, context: Context) {
        if let window = view.window {
            OmiWindowDresser(window: window).dress()
        }
    }
}

// MARK: - App delegate (window commands)

/// Maps the OmiUI desktop surface's traffic-light commands onto the real
/// AppKit window paths, and labels the demo run in the window title.
final class OmiAppDelegate: NSObject, NSApplicationDelegate {
    private var windowCommandObserver: NSObjectProtocol?

    func applicationDidFinishLaunching(_ notification: Notification) {
        windowCommandObserver = NotificationCenter.default.addObserver(
            forName: Notification.Name(DesktopWindowSignals.windowCommand),
            object: nil, queue: .main
        ) { [weak self] note in
            self?.performWindowCommand(from: note)
        }
        if OmiBootstrap.demoMode {
            NSApp.mainWindow?.title = "Omi — Demo Data"
        }
    }

    private func performWindowCommand(from note: Notification) {
        guard let raw = note.userInfo?["command"] as? String,
            let command = DesktopWindowCommand(rawValue: raw),
            let window = NSApp.keyWindow ?? NSApp.mainWindow
        else { return }
        switch command {
        case .close: window.performClose(nil)
        case .minimize: window.performMiniaturize(nil)
        case .zoom: window.performZoom(nil)
        }
    }

    func applicationWillTerminate(_ notification: Notification) {
        if let windowCommandObserver {
            NotificationCenter.default.removeObserver(windowCommandObserver)
        }
    }
}

// MARK: - App

@main
struct OmiHostApp: App {
    @NSApplicationDelegateAdaptor(OmiAppDelegate.self) private var delegate
    @StateObject private var store: AppStore

    init() {
        _store = StateObject(wrappedValue: OmiBootstrap.makeStore())
    }

    var body: some Scene {
        WindowGroup {
            RootView()
                .environmentObject(store)
                .background(OmiGlassBackground())
                .background(OmiWindowAccessor())
        }
        .windowStyle(.automatic)
        .defaultSize(width: 1_020, height: 720)
        .commands {
            // Edit → Search (Cmd+K): the desktop surface consumes the
            // searchCommand notification (Search mode, Home, omnibar focus).
            CommandGroup(after: .textEditing) {
                Button("Find in Omi…") {
                    NotificationCenter.default.post(
                        name: Notification.Name(DesktopWindowSignals.searchCommand),
                        object: nil)
                }
                .keyboardShortcut("k", modifiers: .command)
            }
        }
    }
}
