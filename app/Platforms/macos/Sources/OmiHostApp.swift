import AppKit
import AVFoundation
import CoreGraphics
import SwiftUI
#if DEBUG
import Inject
#endif

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

/// Applies the v5 window contract to the hosting NSWindow, per the RN
/// `applyOmiWindowPresentation` contract: two presentations over one
/// window. `.app` reserves chrome row 1 (the omnibar row); `.onboarding`
/// is a chrome-less centered card window — no header bar, no chrome
/// spacer, sized to the card. Idempotent: the SwiftUI lifecycle calls this
/// more than once per window and on every presentation change.
@MainActor
struct OmiWindowDresser {
    let window: NSWindow
    var onboarding: Bool = false

    private static let onboardingSize = NSSize(width: 640, height: 680)
    private static let onboardingMinSize = NSSize(width: 520, height: 620)
    private static let appSize = NSSize(width: 1_020, height: 720)

    func dress() {
        window.styleMask.insert(.fullSizeContentView)
        window.titlebarAppearsTransparent = true
        window.titleVisibility = .hidden
        window.isMovableByWindowBackground = true
        window.isReleasedWhenClosed = false

        // The app draws its own traffic lights on the chrome row; the system
        // buttons stay hidden behind the full-size content view. Onboarding
        // has no chrome row at all — the window is the card's stage.
        window.standardWindowButton(.closeButton)?.isHidden = true
        window.standardWindowButton(.miniaturizeButton)?.isHidden = true
        window.standardWindowButton(.zoomButton)?.isHidden = true

        let identifier = NSUserInterfaceItemIdentifier(
            onboarding ? "omi-onboarding" : "omi-app")
        let presentationChanged = window.identifier != identifier
        window.identifier = identifier

        if onboarding {
            // Frameless: no titlebar at all — the window is the card's
            // stage (Cmd-W still closes via the retained .closable mask).
            // Titlebar accessories are illegal once `.titled` is gone —
            // AppKit asserts in `titlebarAccessoryViewControllers`. Strip
            // the spacer first, and never touch it again on a borderless
            // window (SwiftUI re-dresses on every layout pass).
            if window.styleMask.contains(.titled) {
                removeChromeSpacer()
                window.styleMask.remove(.titled)
            }
            // The window is the stage, not a glass panel. A clear opaque
            // window still composites a blur; transparent + non-opaque is
            // what lets the desktop show around the card.
            window.isOpaque = false
            window.backgroundColor = .clear
            window.hasShadow = false
            window.titlebarAppearsTransparent = true
            if let content = window.contentView {
                content.wantsLayer = true
                content.layer?.backgroundColor = NSColor.clear.cgColor
                content.layer?.isOpaque = false
            }
            window.contentMinSize = OmiWindowDresser.onboardingMinSize
            if presentationChanged {
                window.setContentSize(OmiWindowDresser.onboardingSize)
                window.center()
            }
        } else {
            window.styleMask.insert(.titled)
            window.backgroundColor = nil
            window.isOpaque = true
            installChromeSpacer()
            window.contentMinSize = NSSize(width: 800, height: 680)
            if presentationChanged {
                window.setContentSize(OmiWindowDresser.appSize)
                window.center()
            }
        }
    }

    /// Reserve chrome row 1 the way AppDelegate.mm does: a titlebar
    /// accessory spacer of the full chrome height plus the window inset.
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

    private func removeChromeSpacer() {
        let spacerHeight = OmiChrome.chromeRowHeight + OmiChrome.windowInset
        for (index, accessory) in window.titlebarAccessoryViewControllers
            .enumerated().reversed()
        where accessory.layoutAttribute == .top
            && accessory.view.frame.height == spacerHeight
        {
            window.removeTitlebarAccessoryViewController(at: index)
        }
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

/// Bridges the SwiftUI hierarchy to the window dresser; re-dresses whenever
/// the session phase flips the onboarding presentation.
struct OmiWindowAccessor: NSViewRepresentable {
    var onboarding: Bool = false

    func makeNSView(context: Context) -> NSView {
        let view = NSView()
        DispatchQueue.main.async {
            guard let window = view.window else { return }
            OmiWindowDresser(window: window, onboarding: onboarding).dress()
        }
        return view
    }

    func updateNSView(_ view: NSView, context: Context) {
        if let window = view.window {
            OmiWindowDresser(window: window, onboarding: onboarding).dress()
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

    /// Single-window app (AppDelegate.mm contract): closing the window —
    /// Cmd-W, the native menu, or the virtual traffic light — ends the
    /// process. Without this a windowless process lingers and the next
    /// activation spawns a fresh window with fresh surface state.
    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool {
        true
    }

    /// Reopen (Dock click, second `open`) focuses the existing window and
    /// returns false so SwiftUI's WindowGroup never spawns a duplicate —
    /// two glass windows stack and their content composites into one
    /// unreadable overlap.
    func applicationShouldHandleReopen(_ sender: NSApplication, hasVisibleWindows flag: Bool) -> Bool {
        if flag {
            return false
        }
        let appWindow = NSApp.windows.first { window in
            !(window is NSPanel) && window.isVisible
        }
        appWindow?.makeKeyAndOrderFront(nil)
        return false
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
        #if DEBUG
        InjectConfiguration.animation = .easeOut(duration: 0.2)
        #endif
        _store = StateObject(wrappedValue: OmiBootstrap.makeStore())
    }

    var body: some Scene {
        WindowGroup {
            // The onboarding presentation is chrome-less: while the session
            // is signed out the window re-dresses into a centered card
            // stage (no header bar, no chrome spacer, no glass).
            let onboarding = store.authState != AuthUiState.signedIn
            RootView()
                .environmentObject(store)
                .background {
                    if onboarding {
                        Color.clear
                    } else {
                        OmiGlassBackground()
                    }
                }
                .background(OmiWindowAccessor(onboarding: onboarding))
                .onAppear { applyAppearance(store.preferences.appearance) }
                .onChange(of: store.preferences.appearance) { appearance in
                    applyAppearance(appearance)
                }
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

    /// The v5 window contract: dark preference drives the dark HUD glass.
    /// Without this the window follows the system appearance and the glass
    /// renders with the light material under the app's dark ink.
    private func applyAppearance(_ appearance: DesktopAppearance) {
        NSApp.appearance = appearance == .dark
            ? NSAppearance(named: .darkAqua) : nil
    }
}
