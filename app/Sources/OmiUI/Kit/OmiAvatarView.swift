import SwiftUI

// The Omi avatar: the canonical eight-dot mark ring, ported from
// `react-native/src/ui/OmiAvatar.tsx` / `omiMarkGeometry`. On this surface the
// identity tone (per-identity hue hashing) is not used; both surfaces render
// the ink tone (white dots). `arrive` places dots with a staggered ease,
// `breathe` pulses opacity, and the resting mark is static.

public enum OmiAvatarMotion {
    case resting
    case arrive
    case breathe
}

public struct OmiAvatarView: View {
    public let size: CGFloat
    public let inkColor: Color
    public let motion: OmiAvatarMotion
    public let reduceMotion: Bool

    public init(
        size: CGFloat = 40,
        inkColor: Color = Color.white,
        motion: OmiAvatarMotion = .resting,
        reduceMotion: Bool = false
    ) {
        self.size = size
        self.inkColor = inkColor
        self.motion = motion
        self.reduceMotion = reduceMotion
    }

    /// `omiMarkGeometry`: axis dots sit on r=86.71/130, diagonal dots on
    /// r=91.92/130 of a 260-unit canvas.
    private func center(index: Int, side: CGFloat) -> CGPoint {
        let theta = Double(index) * Double.pi / 4.0
        let axis = 86.71 / 130.0
        let diagonal = 91.92 / 130.0
        let radius = index % 2 == 0 ? axis : diagonal
        let centre = 0.5
        return CGPoint(
            x: side * CGFloat(centre + radius * sin(theta)),
            y: side * CGFloat(centre - radius * cos(theta))
        )
    }

    private var dotSize: CGFloat {
        size * (17.2 * 2.0 / 260.0)
    }

    public var body: some View {
        ZStack {
            ForEach(0..<8, id: \.self) { index in
                Circle()
                    .fill(inkColor)
                    .frame(width: dotSize, height: dotSize)
                    .position(center(index: index, side: size))
                    .opacity(dotOpacity(index))
                    .scaleEffect(dotScale(index))
            }
        }
        .frame(width: size, height: size)
        .animation(reduceMotion ? nil : breatheAnimation, value: motion)
        .accessibilityLabel("Omi")
    }

    private var breatheAnimation: Animation? {
        switch motion {
        case .resting: return nil
        case .arrive: return KitMotion.slide
        case .breathe: return KitMotion.breathe.repeatForever(autoreverses: true)
        }
    }

    private func dotOpacity(_ index: Int) -> Double {
        switch motion {
        case .resting: return 1
        case .arrive: return 0.15 + 0.85 * placedFraction(index)
        case .breathe: return 0.75 + 0.25 * breath(index)
        }
    }

    private func dotScale(_ index: Int) -> CGFloat {
        switch motion {
        case .resting: return 1
        case .arrive: return 0.6 + 0.4 * placedFraction(index)
        case .breathe: return 1 + 0.056 * CGFloat(breath(index))
        }
    }

    /// The `arrive` stagger: dot `index` trails the ring head by 0.045.
    private func placedFraction(_ index: Int) -> Double {
        let t = (0.685 - Double(index) * 0.045) / 0.685
        let clamped = max(0, min(1, t))
        return 1 - pow(1 - clamped, 3)
    }

    private func breath(_ index: Int) -> Double {
        0.5 - 0.5 * cos(2 * Double.pi * Double(index) / 24.0)
    }
}
