import AppKit
import AVFoundation
import CoreGraphics
import SwiftUI

import OmiKit
import OmiUI

// macOS host shell. Bootstrap + injection + window/permission plumbing only;
// all product UI comes from OmiUI.RootView over OmiUI.AppModel.
//
// Injection contract (see ../README.md):
//   - OmiKit.Policy.bridge defaults to DefaultPolicyBridge, which links the
//     real native-core C++ through CNativeCore — nothing to replace on macOS.
//   - Auth uses the browser + loopback callback flow (docs/auth-and-sessions.md);
//     the native session module owns the exchange and calls
//     AppModel.updateSignedIn(_:) when it lands.
//
// Window contract (docs/desktop-app.md, values pinned in the RN tree's
// `AppDelegate.mm` / `desktopChrome.ts` and asserted by
// `react-native/__tests__/macOSNativeBoundary.test.ts`):
//   - real behind-window NSVisualEffectView glass (HUDWindow material dark,
//     UnderWindowBackground light), never a full-bleed SwiftUI background;
//   - titlebar material hidden; a titlebar accessory spacer of
//     OmiChromeRowHeight + OmiWindowInset reserves chrome row 1;
//   - traffic lights are positioned by shifting the whole titlebar container
//     (never individual buttons) so they center on the chrome row;
//   - dragging is AppKit's movableByWindowBackground path;
//   - the capture toggle hides when Screen Recording permission is
//     unavailable (probe in OmiPermissions below);
//   - every rebuild resets the Screen Recording TCC grant.

enum OmiChrome {
    /// Must equal `desktopWindowInset` in react-native/src/desktop/desktopChrome.ts.
    static let windowInset: CGFloat = 12.0
    /// Must equal `desktopOmnibarHeight` in react-native/src/desktop/desktopChrome.ts.
    static let chromeRowHeight: CGFloat = 44.0
}

// MARK: - Permissions

/// Permission probing for the chrome's capture toggle. The full chrome
/// contract (toggle state, permission guide) is asserted by the RN boundary
/// test suite; this host only supplies the availability signal.
@MainActor
enum OmiPermissions {
    /// Capture is offerable only with Screen Recording granted. Rebuilds
    /// reset the TCC grant, so this is re-probed per launch (and would be
    /// re-probed on window focus once the capture session seam lands).
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

        // Center the traffic lights on the chrome row by shifting the whole
        // titlebar container — never individual buttons (hover glyphs desync).
        if let container = window.standardWindowButton(.closeButton)?.superview?.superview {
            container.frame.origin.y = chromeRowCenterOffset(in: container)
        }
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

    /// Distance to move the titlebar container down so the light centers sit
    /// on the middle of the chrome row (the row begins `windowInset` below
    /// the window's top edge and is `chromeRowHeight` tall).
    private func chromeRowCenterOffset(in container: NSView) -> CGFloat {
        let windowTopInContainerY = container.superview.map { $0.bounds.height - container.frame.maxY } ?? 0
        let rowCenterFromWindowTop = OmiChrome.windowInset + OmiChrome.chromeRowHeight / 2
        let lightCenterInContainer = container.bounds.height / 2
        return windowTopInContainerY + rowCenterFromWindowTop - lightCenterInContainer
    }
}

/// Backgrounds the hosting view with real behind-window glass, mirroring
/// `OmiGlassPanelView.mm` (NSVisualEffectMaterialHUDWindow dark /
/// UnderWindowBackground light). Content above it stays transparent so the
/// desktop shows through; light mode will paint its opaque paper background
/// in the OmiUI surface once the desktop theme lands there.
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

// MARK: - App

@main
struct OmiHostApp: App {
    @State private var model = AppModel()

    var body: some Scene {
        WindowGroup {
            RootView(model: model)
                .background(OmiGlassBackground())
                .background(OmiWindowAccessor())
        }
        .windowStyle(.automatic)
        .defaultSize(width: 900, height: 700)
    }
}
