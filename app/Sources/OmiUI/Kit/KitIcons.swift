import SwiftUI

// Glyph set ported from `react-native/src/ui/MaterialIcon.tsx` usage. SF
// Symbols failed in this toolchain, so every glyph is drawn with SwiftUI
// shapes/paths at a consistent optical size (stroke width 2 from tokens).

public enum KitIconName: Sendable, Hashable {
    case home
    case chatBubble
    case checklist
    case settings
    case search
    case chevronLeft
    case chevronRight
    case close
    case arrowUp
    case stop
    case check
    case edit
    case puzzle
    case mic
    case plus
}

public struct KitIconShape: Shape {
    public let name: KitIconName

    public init(_ name: KitIconName) {
        self.name = name
    }

    public func path(in rect: CGRect) -> Path {
        let w = rect.width
        let h = rect.height
        func point(_ x: CGFloat, _ y: CGFloat) -> CGPoint {
            CGPoint(x: x * w, y: y * h)
        }
        var path = Path()
        switch name {
        case .home:
            path.move(to: point(0.12, 0.52))
            path.addLine(to: point(0.5, 0.14))
            path.addLine(to: point(0.88, 0.52))
            path.move(to: point(0.24, 0.44))
            path.addLine(to: point(0.24, 0.86))
            path.addLine(to: point(0.76, 0.86))
            path.addLine(to: point(0.76, 0.44))
        case .chatBubble:
            path.addRoundedRect(
                in: CGRect(x: 0.1 * w, y: 0.14 * h, width: 0.8 * w, height: 0.58 * h),
                cornerSize: CGSize(width: 0.16 * w, height: 0.16 * h)
            )
            path.move(to: point(0.3, 0.72))
            path.addLine(to: point(0.3, 0.88))
            path.addLine(to: point(0.48, 0.72))
        case .checklist:
            path.move(to: point(0.4, 0.26))
            path.addLine(to: point(0.88, 0.26))
            path.move(to: point(0.4, 0.52))
            path.addLine(to: point(0.88, 0.52))
            path.move(to: point(0.4, 0.78))
            path.addLine(to: point(0.88, 0.78))
            path.move(to: point(0.1, 0.24))
            path.addLine(to: point(0.2, 0.34))
            path.addLine(to: point(0.32, 0.16))
            path.move(to: point(0.1, 0.5))
            path.addLine(to: point(0.2, 0.6))
            path.addLine(to: point(0.32, 0.42))
        case .settings:
            path.addEllipse(
                in: CGRect(x: 0.34 * w, y: 0.34 * h, width: 0.32 * w, height: 0.32 * h)
            )
            for index in 0..<8 {
                let angle = Double(index) * Double.pi / 4.0
                let center = CGPoint(x: 0.5 * w, y: 0.5 * h)
                let inner = 0.26
                let outer = 0.4
                path.move(
                    to: CGPoint(
                        x: center.x + CGFloat(inner * cos(angle)) * w,
                        y: center.y + CGFloat(inner * sin(angle)) * h
                    )
                )
                path.addLine(
                    to: CGPoint(
                        x: center.x + CGFloat(outer * cos(angle)) * w,
                        y: center.y + CGFloat(outer * sin(angle)) * h
                    )
                )
            }
        case .search:
            path.addEllipse(
                in: CGRect(x: 0.14 * w, y: 0.14 * h, width: 0.5 * w, height: 0.5 * h)
            )
            path.move(to: point(0.58, 0.58))
            path.addLine(to: point(0.88, 0.88))
        case .chevronLeft:
            path.move(to: point(0.62, 0.16))
            path.addLine(to: point(0.3, 0.5))
            path.addLine(to: point(0.62, 0.84))
        case .chevronRight:
            path.move(to: point(0.38, 0.16))
            path.addLine(to: point(0.7, 0.5))
            path.addLine(to: point(0.38, 0.84))
        case .close:
            path.move(to: point(0.2, 0.2))
            path.addLine(to: point(0.8, 0.8))
            path.move(to: point(0.8, 0.2))
            path.addLine(to: point(0.2, 0.8))
        case .arrowUp:
            path.move(to: point(0.5, 0.84))
            path.addLine(to: point(0.5, 0.18))
            path.move(to: point(0.2, 0.48))
            path.addLine(to: point(0.5, 0.18))
            path.addLine(to: point(0.8, 0.48))
        case .stop:
            path.addRoundedRect(
                in: CGRect(x: 0.24 * w, y: 0.24 * h, width: 0.52 * w, height: 0.52 * h),
                cornerSize: CGSize(width: 0.08 * w, height: 0.08 * h)
            )
        case .check:
            path.move(to: point(0.16, 0.52))
            path.addLine(to: point(0.42, 0.78))
            path.addLine(to: point(0.86, 0.24))
        case .edit:
            path.move(to: point(0.22, 0.82))
            path.addLine(to: point(0.26, 0.66))
            path.addLine(to: point(0.72, 0.2))
            path.addLine(to: point(0.84, 0.32))
            path.addLine(to: point(0.38, 0.78))
            path.addLine(to: point(0.22, 0.82))
        case .puzzle:
            path.addRoundedRect(
                in: CGRect(x: 0.14 * w, y: 0.26 * h, width: 0.72 * w, height: 0.6 * h),
                cornerSize: CGSize(width: 0.14 * w, height: 0.14 * h)
            )
            path.addEllipse(
                in: CGRect(x: 0.38 * w, y: 0.08 * h, width: 0.24 * w, height: 0.24 * h)
            )
        case .mic:
            path.addRoundedRect(
                in: CGRect(x: 0.36 * w, y: 0.1 * h, width: 0.28 * w, height: 0.46 * h),
                cornerSize: CGSize(width: 0.14 * w, height: 0.23 * h)
            )
            path.move(to: point(0.22, 0.5))
            path.addQuadCurve(
                to: point(0.78, 0.5),
                control: point(0.5, 0.86)
            )
            path.move(to: point(0.5, 0.78))
            path.addLine(to: point(0.5, 0.92))
        case .plus:
            path.move(to: point(0.5, 0.16))
            path.addLine(to: point(0.5, 0.84))
            path.move(to: point(0.16, 0.5))
            path.addLine(to: point(0.84, 0.5))
        }
        return path
    }
}

/// The single glyph view. `filled == true` renders a solid glyph (stop, mic
/// capsule); everything else strokes at the token stroke width.
public struct KitIcon: View {
    public let name: KitIconName
    public let size: CGFloat
    public let color: Color
    public var filled: Bool

    public init(
        _ name: KitIconName, size: CGFloat, color: Color, filled: Bool = false
    ) {
        self.name = name
        self.size = size
        self.color = color
        self.filled = filled
    }

    public var body: some View {
        if filled {
            KitIconShape(name)
                .fill(color)
                .frame(width: size, height: size)
        } else {
            KitIconShape(name)
                .stroke(
                    color,
                    style: StrokeStyle(
                        lineWidth: max(IconWeight.strokeWidth, size * 0.11),
                        lineCap: .round,
                        lineJoin: .round
                    )
                )
                .frame(width: size, height: size)
        }
    }
}
