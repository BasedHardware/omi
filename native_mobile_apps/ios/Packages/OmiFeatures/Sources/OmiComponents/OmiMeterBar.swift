import OmiDesign
import SwiftUI

/// A thin rounded meter (Plan & usage's limits, fair use, the Omi's storage): the used share in
/// `tint` on the quiet fill. Callers pick the tint: ink, amber near the limit, red at it.
public struct OmiMeterBar: View {
    let fraction: Double
    let tint: Color

    public init(fraction: Double, tint: Color = DS.Palette.ink) {
        self.fraction = fraction
        self.tint = tint
    }

    public var body: some View {
        GeometryReader { proxy in
            ZStack(alignment: .leading) {
                Capsule().fill(DS.Palette.fill)
                Capsule().fill(tint).frame(width: max(fraction > 0 ? 4 : 0, proxy.size.width * min(1, max(0, fraction))))
            }
        }
        .frame(height: 4)
        .accessibilityHidden(true)
    }
}
