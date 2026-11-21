import OmiDesign
import OmiService
import SwiftUI

/// The small status dot beside the pendant (Settings' Omi tile, My Omi): red while listening,
/// green while connected, none while away.
public struct OmiStatusDot: View {
    let dot: SettingsHub.OmiState.Dot
    let size: CGFloat
    let ring: Color
    /// Away reads as a gray dot instead of none (My Omi's status line).
    let showsOff: Bool

    public init(dot: SettingsHub.OmiState.Dot, size: CGFloat = 9, ring: Color = DS.Palette.card, showsOff: Bool = false) {
        self.dot = dot
        self.size = size
        self.ring = ring
        self.showsOff = showsOff
    }

    public var body: some View {
        if let color {
            Circle().fill(color).frame(width: size, height: size)
                .overlay { Circle().strokeBorder(ring, lineWidth: size / 6) }
                .accessibilityHidden(true)
        }
    }

    private var color: Color? {
        switch dot {
        case .live: DS.Palette.live
        case .connected: DS.Palette.success
        case .off: showsOff ? DS.Palette.inkTertiary : nil
        }
    }
}

/// The Omi's state in words ("76% · Listening", "Not connected", "Get an Omi").
public enum OmiStatusText {
    public static func short(_ state: SettingsHub.OmiState) -> String {
        switch state {
        case .none: return L("nativeGetAnOmi")
        case .notConnected: return L("nativeNotConnected")
        case .connecting: return L("nativeConnecting")
        case let .connected(battery, activity):
            let doing = switch activity {
            case .listening: L("nativeOmiListening")
            case .paused: L("nativePaused")
            case .idle: L("nativeConnected")
            }
            return [battery.map { "\($0)%" }, doing].compactMap(\.self).joined(separator: " · ")
        }
    }
}
