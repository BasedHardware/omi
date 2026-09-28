import SwiftUI

// SwiftUI-drawn replacement for MaterialIcon on the desktop surface (SF
// Symbols are unavailable in this toolchain and SkipUI transpiles to
// Android, so glyphs are simple Shape/Canvas drawings). Sizes and weights
// match the RN usage (14–22 pt strokes of ~1.8).

/// One glyph drawing closure per icon, stroked in the given color.
public enum DesktopIcon: View {
    case chatBubble
    case search
    case gear
    case monitor
    case checklist
    case history
    case timeline
    case arrowUp
    case stop
    case close
    case check
    case chevronDown
    case sparkles
    case home
    case arrowOutward
    case cursor

    var nominalSize: CGFloat {
        switch self {
        case .sparkles: return 13
        default: return 16
        }
    }

    public var body: some View {
        GeometryReader { proxy in
            let side = min(proxy.size.width, proxy.size.height)
            iconBody(side: side)
        }
        .frame(width: nominalSize, height: nominalSize)
        .accessibilityHidden(true)
    }

    @ViewBuilder
    private func iconBody(side: CGFloat) -> some View {
        switch self {
        case .chatBubble:
            ChatBubbleShape()
                .stroke(style: StrokeStyle(lineWidth: stroke(side), lineCap: .round, lineJoin: .round))
        case DesktopIcon.search:
            ZStack {
                Circle()
                    .inset(by: side * 0.14)
                    .stroke(lineWidth: stroke(side))
                HandleShape()
                    .stroke(style: StrokeStyle(lineWidth: stroke(side), lineCap: .round))
            }
        case .gear:
            GearShape()
                .stroke(style: StrokeStyle(lineWidth: stroke(side), lineCap: .round, lineJoin: .round))
        case .monitor:
            ZStack {
                RoundedRectangle(cornerRadius: side * 0.12)
                    .inset(by: side * 0.1)
                    .stroke(lineWidth: stroke(side))
                HandleShape(horizontal: true)
                    .stroke(style: StrokeStyle(lineWidth: stroke(side), lineCap: .round))
            }
        case .checklist:
            VStack(alignment: .leading, spacing: side * 0.16) {
                checklistLine(side, true)
                checklistLine(side, true)
                checklistLine(side, false)
            }
            .frame(width: side, height: side, alignment: .leading)
        case .history:
            ZStack {
                Circle()
                    .inset(by: side * 0.14)
                    .trim(from: 0.08, to: 0.92)
                    .stroke(style: StrokeStyle(lineWidth: stroke(side), lineCap: .round))
                ClockHandsShape()
                    .stroke(style: StrokeStyle(lineWidth: stroke(side), lineCap: .round))
            }
        case .timeline:
            VStack(alignment: .leading, spacing: side * 0.14) {
                timelineRow(side, width: 1.0)
                timelineRow(side, width: 0.62)
                timelineRow(side, width: 0.82)
            }
            .frame(width: side, height: side, alignment: .leading)
        case .arrowUp:
            ArrowUpShape()
                .stroke(style: StrokeStyle(lineWidth: side * 0.13, lineCap: .round, lineJoin: .round))
        case .stop:
            RoundedRectangle(cornerRadius: side * 0.18)
                .inset(by: side * 0.2)
                .fill()
        case .close:
            CrossShape()
                .stroke(style: StrokeStyle(lineWidth: side * 0.13, lineCap: .round))
        case .check:
            CheckShape()
                .stroke(style: StrokeStyle(lineWidth: side * 0.16, lineCap: .round, lineJoin: .round))
        case .chevronDown:
            ChevronShape()
                .stroke(style: StrokeStyle(lineWidth: side * 0.13, lineCap: .round, lineJoin: .round))
        case .sparkles:
            SparkleShape()
                .fill(style: FillStyle(eoFill: false))
        case DesktopIcon.home:
            HomeShape()
                .stroke(style: StrokeStyle(lineWidth: stroke(side), lineJoin: .round))
        case .arrowOutward:
            ArrowOutwardShape()
                .stroke(style: StrokeStyle(lineWidth: side * 0.12, lineCap: .round, lineJoin: .round))
        case .cursor:
            CursorShape()
                .fill()
        }
    }

    private func stroke(_ side: CGFloat) -> CGFloat {
        side * 0.12
    }

    @ViewBuilder
    private func checklistLine(_ side: CGFloat, _ box: Bool) -> some View {
        HStack(spacing: side * 0.12) {
            if box {
                RoundedRectangle(cornerRadius: side * 0.08)
                    .inset(by: side * 0.02)
                    .stroke(lineWidth: stroke(side))
                    .frame(width: side * 0.2, height: side * 0.2)
            } else {
                CheckShape()
                    .stroke(lineWidth: stroke(side))
                    .frame(width: side * 0.2, height: side * 0.2)
            }
            Capsule()
                .frame(width: side * 0.58, height: max(1.2, side * 0.08))
        }
    }

    private func timelineRow(_ side: CGFloat, width fraction: CGFloat) -> some View {
        HStack(alignment: .center, spacing: side * 0.1) {
            Circle()
                .frame(width: max(1.5, side * 0.12))
            Capsule()
                .frame(width: side * fraction * 0.82, height: max(1.2, side * 0.09))
        }
    }
}

// MARK: - Shapes

struct ChatBubbleShape: Shape {
    func path(in rect: CGRect) -> Path {
        var path = Path()
        let w = rect.width
        let h = rect.height
        let r = min(w, h) * 0.28
        let bubble = CGRect(x: 0.04 * w, y: 0.1 * h, width: 0.92 * w, height: 0.68 * h)
        path.addRoundedRect(in: bubble, cornerSize: CGSize(width: r, height: r))
        var tail = Path()
        tail.move(to: CGPoint(x: 0.28 * w, y: 0.76 * h))
        tail.addLine(to: CGPoint(x: 0.2 * w, y: 0.94 * h))
        tail.addLine(to: CGPoint(x: 0.44 * w, y: 0.78 * h))
        path.addPath(tail)
        return path
    }
}

struct HandleShape: Shape {
    /// A diagonal search handle by default; horizontal for the monitor stand.
    var horizontal = false

    func path(in rect: CGRect) -> Path {
        var path = Path()
        if horizontal {
            path.move(to: CGPoint(x: rect.midX, y: rect.height * 0.84))
            path.addLine(to: CGPoint(x: rect.midX, y: rect.height * 0.96))
            path.move(to: CGPoint(x: rect.width * 0.3, y: rect.height * 0.94))
            path.addLine(to: CGPoint(x: rect.width * 0.7, y: rect.height * 0.94))
        } else {
            path.move(to: CGPoint(x: rect.width * 0.72, y: rect.height * 0.72))
            path.addLine(to: CGPoint(x: rect.width * 0.92, y: rect.height * 0.92))
        }
        return path
    }
}

struct GearShape: Shape {
    func path(in rect: CGRect) -> Path {
        var path = Path()
        let center = CGPoint(x: rect.midX, y: rect.midY)
        let outer = rect.width * 0.42
        let inner = rect.width * 0.28
        let teeth = 8
        let step = (2 * Double.pi) / Double(teeth * 2)
        var angle = -Double.pi / 2
        for index in 0..<(teeth * 2) {
            let radius = index.isMultiple(of: 2) ? outer : outer * 0.86
            let point = CGPoint(
                x: center.x + CGFloat(cos(angle)) * radius,
                y: center.y + CGFloat(sin(angle)) * radius
            )
            if index == 0 {
                path.move(to: point)
            } else {
                path.addLine(to: point)
            }
            angle += step
        }
        path.closeSubpath()
        path.addEllipse(in: CGRect(
            x: center.x - inner, y: center.y - inner,
            width: inner * 2, height: inner * 2
        ))
        return path
    }
}

struct ClockHandsShape: Shape {
    func path(in rect: CGRect) -> Path {
        var path = Path()
        path.move(to: CGPoint(x: rect.midX, y: rect.midY))
        path.addLine(to: CGPoint(x: rect.midX, y: rect.height * 0.26))
        path.move(to: CGPoint(x: rect.midX, y: rect.midY))
        path.addLine(to: CGPoint(x: rect.width * 0.66, y: rect.midY + rect.height * 0.1))
        return path
    }
}

struct ArrowUpShape: Shape {
    func path(in rect: CGRect) -> Path {
        var path = Path()
        path.move(to: CGPoint(x: rect.midX, y: rect.height * 0.14))
        path.addLine(to: CGPoint(x: rect.midX, y: rect.height * 0.86))
        path.move(to: CGPoint(x: rect.width * 0.2, y: rect.height * 0.48))
        path.addLine(to: CGPoint(x: rect.midX, y: rect.height * 0.14))
        path.addLine(to: CGPoint(x: rect.width * 0.8, y: rect.height * 0.48))
        return path
    }
}

struct CrossShape: Shape {
    func path(in rect: CGRect) -> Path {
        var path = Path()
        path.move(to: CGPoint(x: rect.width * 0.2, y: rect.height * 0.2))
        path.addLine(to: CGPoint(x: rect.width * 0.8, y: rect.height * 0.8))
        path.move(to: CGPoint(x: rect.width * 0.8, y: rect.height * 0.2))
        path.addLine(to: CGPoint(x: rect.width * 0.2, y: rect.height * 0.8))
        return path
    }
}

struct CheckShape: Shape {
    func path(in rect: CGRect) -> Path {
        var path = Path()
        path.move(to: CGPoint(x: rect.width * 0.14, y: rect.height * 0.54))
        path.addLine(to: CGPoint(x: rect.width * 0.42, y: rect.height * 0.8))
        path.addLine(to: CGPoint(x: rect.width * 0.88, y: rect.height * 0.22))
        return path
    }
}

struct ChevronShape: Shape {
    /// Points down by default (the collapse chevron).
    func path(in rect: CGRect) -> Path {
        var path = Path()
        path.move(to: CGPoint(x: rect.width * 0.18, y: rect.height * 0.32))
        path.addLine(to: CGPoint(x: rect.midX, y: rect.height * 0.68))
        path.addLine(to: CGPoint(x: rect.width * 0.82, y: rect.height * 0.32))
        return path
    }
}

struct SparkleShape: Shape {
    func path(in rect: CGRect) -> Path {
        var path = Path()
        let cx = rect.midX
        let cy = rect.midY
        let long = rect.height * 0.48
        let short = rect.width * 0.16
        path.move(to: CGPoint(x: cx, y: cy - long))
        path.addQuadCurve(
            to: CGPoint(x: cx + long, y: cy),
            control: CGPoint(x: cx + short, y: cy - short)
        )
        path.addQuadCurve(
            to: CGPoint(x: cx, y: cy + long),
            control: CGPoint(x: cx + short, y: cy + short)
        )
        path.addQuadCurve(
            to: CGPoint(x: cx - long, y: cy),
            control: CGPoint(x: cx - short, y: cy + short)
        )
        path.addQuadCurve(
            to: CGPoint(x: cx, y: cy - long),
            control: CGPoint(x: cx - short, y: cy - short)
        )
        path.closeSubpath()
        return path
    }
}

struct HomeShape: Shape {
    func path(in rect: CGRect) -> Path {
        var path = Path()
        path.move(to: CGPoint(x: rect.width * 0.12, y: rect.height * 0.5))
        path.addLine(to: CGPoint(x: rect.midX, y: rect.height * 0.14))
        path.addLine(to: CGPoint(x: rect.width * 0.88, y: rect.height * 0.5))
        path.move(to: CGPoint(x: rect.width * 0.24, y: rect.height * 0.44))
        path.addLine(to: CGPoint(x: rect.width * 0.24, y: rect.height * 0.86))
        path.addLine(to: CGPoint(x: rect.width * 0.76, y: rect.height * 0.86))
        path.addLine(to: CGPoint(x: rect.width * 0.76, y: rect.height * 0.44))
        return path
    }
}

struct ArrowOutwardShape: Shape {
    func path(in rect: CGRect) -> Path {
        var path = Path()
        path.move(to: CGPoint(x: rect.width * 0.3, y: rect.height * 0.7))
        path.addLine(to: CGPoint(x: rect.width * 0.74, y: rect.height * 0.26))
        path.move(to: CGPoint(x: rect.width * 0.42, y: rect.height * 0.26))
        path.addLine(to: CGPoint(x: rect.width * 0.74, y: rect.height * 0.26))
        path.addLine(to: CGPoint(x: rect.width * 0.74, y: rect.height * 0.58))
        return path
    }
}

struct CursorShape: Shape {
    func path(in rect: CGRect) -> Path {
        var path = Path()
        path.move(to: CGPoint(x: rect.width * 0.24, y: rect.height * 0.1))
        path.addLine(to: CGPoint(x: rect.width * 0.24, y: rect.height * 0.78))
        path.addLine(to: CGPoint(x: rect.width * 0.44, y: rect.height * 0.6))
        path.addLine(to: CGPoint(x: rect.width * 0.58, y: rect.height * 0.92))
        path.addLine(to: CGPoint(x: rect.width * 0.7, y: rect.height * 0.86))
        path.addLine(to: CGPoint(x: rect.width * 0.56, y: rect.height * 0.56))
        path.addLine(to: CGPoint(x: rect.width * 0.8, y: rect.height * 0.52))
        path.closeSubpath()
        return path
    }
}
