import OmiExtras
import SwiftUI
import UIKit

// The Live Activity's look, ported from the Flutter app's capture card
// (app/ios/BatteryWidget/OmiCaptureLiveActivity.swift). Its values come from the omi-ios-v2 design
// package: tokens/tokens.json, generator/s_system.py (LockScreen, Island) and
// specs/geometry/iphone16. Text and controls keep one size on every iPhone; only the pendant (hero
// art) scales with the device, as the in-app Live screen does on SE/mini/16/Max.
//
// These views know nothing about ActivityKit, so the app can render them for layout checks
// (`LiveActivityRenderer`, Debug only); `OmiLiveActivity` places them on the card and in the island.

/// Midnight Graphite tokens.
enum CapturePalette {
    static let label = Color(red: 0xEC / 255, green: 0xEE / 255, blue: 0xF2 / 255)
    static let secondary = Color(red: 0x9A / 255, green: 0xA1 / 255, blue: 0xAD / 255)
    static let ink = Color(red: 0x0A / 255, green: 0x0C / 255, blue: 0x10 / 255)
    static let led = Color(red: 0x4C / 255, green: 0x9B / 255, blue: 0xFF / 255)
    /// material.glassThick (dark): rgba(26,29,37,.88).
    static let card = Color(red: 26 / 255, green: 29 / 255, blue: 37 / 255).opacity(0.88)
    /// A finished or failed run (the system's dark green and orange).
    static let success = Color(red: 0x30 / 255, green: 0xD1 / 255, blue: 0x58 / 255)
    static let warning = Color(red: 0xFF / 255, green: 0x9F / 255, blue: 0x0A / 255)
}

/// Device scaling from tokens.json `layout.KH`.
enum CaptureLayout {
    /// clamp((height − safeTop − safeBottom) / 764, 0.8, 1.1). The extension has
    /// no window insets, so they come from the design's device profiles.
    @MainActor static var heroScale: CGFloat {
        let height = UIScreen.main.bounds.height
        let safeTop: CGFloat = height >= 874 ? 62 : height >= 852 ? 54 : height >= 812 ? 48 : 20
        let safeBottom: CGFloat = height >= 812 ? 34 : 0
        return min(1.1, max(0.8, (height - safeTop - safeBottom) / 764))
    }
}

extension Bundle {
    /// The widget extension's bundle: its pendant art and string catalog. In the extension that is
    /// the main bundle; the app (rendering the views for layout checks) finds it among its plug-ins.
    static let activity: Bundle = {
        if Bundle.main.bundleURL.pathExtension == "appex" { return .main }
        return Bundle.main.builtInPlugInsURL.flatMap { Bundle(url: $0.appendingPathComponent("OmiWidgets.appex")) } ?? .main
    }()
}

/// The glass-thick card both kinds sit on: a 16/10 inset and the top highlight
/// (rgba(255,255,255,.06) fading out by 50%).
struct ActivityCard: ViewModifier {
    func body(content: Content) -> some View {
        content
            .padding(.horizontal, 16)
            .padding(.vertical, 10)
            .foregroundStyle(CapturePalette.label)
            .background(LinearGradient(stops: [
                .init(color: .white.opacity(0.06), location: 0),
                .init(color: .clear, location: 0.5),
            ], startPoint: .top, endPoint: .bottom))
            .dynamicTypeSize(...DynamicTypeSize.xLarge)
    }
}

/// End settles the content before the system dismisses the card. Recording has
/// already finished; this transition never delays capture or processing.
struct CaptureEndTransition: ViewModifier {
    let ended: Bool
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @Environment(\.isLuminanceReduced) private var luminanceReduced

    func body(content: Content) -> some View {
        content
            .opacity(ended ? 0 : 1)
            .scaleEffect(ended && !reduceMotion && !luminanceReduced ? 0.98 : 1)
            .animation(reduceMotion || luminanceReduced ? nil :
                .timingCurve(0.42, 0, 0.58, 1, duration: 0.2), value: ended)
    }
}

/// The Omi pendant, as the app shows it: its photo with the light on while audio is captured
/// (a soft blue glow behind it), and its lights-off photo otherwise.
struct CapturePendant: View {
    let active: Bool
    let size: CGFloat
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @Environment(\.isLuminanceReduced) private var luminanceReduced

    var body: some View {
        // Keep the photo's identity and geometry stable; only its LED fades.
        ZStack {
            Image("device-omi-off", bundle: .activity).resizable().scaledToFit()
            Image("device-omi", bundle: .activity).resizable().scaledToFit().opacity(active ? 1 : 0)
        }
        .frame(width: size, height: size)
        .shadow(color: CapturePalette.led.opacity(active ? 0.45 : 0), radius: size * 0.18)
        .contentTransition(.identity)
        .animation(reduceMotion || luminanceReduced ? nil :
            .timingCurve(0.42, 0, 0.58, 1, duration: 0.25), value: active)
        .accessibilityHidden(true)
    }
}

/// What a clock shows: running from `startedAt` (its range ends at `clockEnd`), frozen at
/// `frozen` seconds, or a dash when its value is not known.
struct ActivityClockValue: Sendable {
    enum Kind: Sendable {
        case recording
        case run
    }

    let kind: Kind
    let startedAt: Date
    let clockEnd: Date
    let frozen: Int?
    var unknown = false

    /// A live timer's ideal width is unbounded, so the clock always gets a
    /// fixed slot, in ems of its font size: the design's 30 pt "02:16" is
    /// 95.5 pt wide (3.2 em); h:mm:ss after the first hour needs 4.3 em.
    var ems: CGFloat {
        if let frozen { return frozen >= 3600 ? 4.3 : 3.2 }
        return clockEnd.timeIntervalSince(startedAt) > 3600 ? 4.3 : 3.2
    }

    var label: LocalizedStringKey {
        switch kind {
        case .recording: "Recording duration"
        case .run: "Time working"
        }
    }
}

/// The 30 pt / 600 clock, flush right in a slot sized for its longest value.
struct CaptureClock: View {
    let value: ActivityClockValue
    @ScaledMetric private var size: CGFloat

    init(value: ActivityClockValue, size: CGFloat) {
        self.value = value
        _size = ScaledMetric(wrappedValue: size, relativeTo: .title)
    }

    var body: some View {
        CaptureClockText(value: value)
            .font(.system(size: size, weight: .semibold))
            .frame(width: size * value.ems, alignment: .trailing)
    }
}

/// HomeScreen.json: 15 pt / 600 clock, 14 pt from the island's trailing edge.
struct CaptureCompactClock: View {
    let value: ActivityClockValue

    var body: some View {
        CaptureClockText(value: value)
            .font(.system(size: 15, weight: .semibold))
            .frame(width: 15 * value.ems, alignment: .trailing)
            .padding(.trailing, 4)
    }
}

struct CaptureClockText: View {
    let value: ActivityClockValue

    var body: some View {
        Group {
            if value.unknown {
                Text(verbatim: "—")
            } else if let seconds = value.frozen.map({ max(0, $0) }) {
                // Frozen value in the same format the live timer uses.
                Text(verbatim: seconds >= 3600
                    ? String(format: "%d:%02d:%02d", seconds / 3600, seconds / 60 % 60, seconds % 60)
                    : String(format: "%d:%02d", seconds / 60, seconds % 60))
            } else {
                // A live timer reserves width for its range's longest value, so the range ends at
                // the next hour; the app republishes at each hour to extend it.
                Text(timerInterval: value.startedAt ... max(value.startedAt, value.clockEnd), countsDown: false)
            }
        }
        .monospacedDigit()
        .contentTransition(.identity)
        .transition(.identity)
        .multilineTextAlignment(.trailing)
        .foregroundStyle(CapturePalette.label)
        .lineLimit(1)
        .accessibilityLabel(Text(value.label, bundle: .activity))
    }
}
