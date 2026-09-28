import OmiKit
import SwiftUI

// Shared desktop chrome primitives: traffic lights (the 12/44 contract),
// the glass pressable, the house GlassToggle, segmented control, scroll
// fade, and the small row/text components from DesktopRows.tsx. Everything
// reads its palette from the desktop theme environment.

// MARK: - Traffic lights (DesktopTrafficLights.tsx)

/// Virtual traffic-light dots rendered inside the chrome row's window-controls
/// spacer at the exact geometry desktopChrome.ts reserves (14 pt dots, 8 pt
/// gaps, 16 pt trailing). The native host hides the system buttons and centers
/// the real hit areas on the 44 pt chrome row; these dots dispatch
/// close/minimize/zoom through `performDesktopWindowCommand`, which the host
/// maps to performClose:/performMiniaturize:/performZoom:. Hover glyphs are
/// hairline dark ink shown for the whole cluster at once, matching the macOS
/// behavior.
public struct DesktopTrafficLights: View {
    @State private var hovered = false
    @Environment(\.desktopTokens) private var tokens

    public init() {}

    public var body: some View {
        HStack(spacing: DesktopLayout.trafficLightSpacing) {
            TrafficDot(
                kind: .close, color: Color(red: 1.0, green: 0.373, blue: 0.341),
                hovered: hovered
            )
            TrafficDot(
                kind: .minimize, color: Color(red: 0.996, green: 0.737, blue: 0.18),
                hovered: hovered
            )
            TrafficDot(
                kind: .zoom, color: Color(red: 0.157, green: 0.784, blue: 0.251),
                hovered: hovered
            )
        }
        .frame(
            width: DesktopLayout.trafficLightClusterWidth,
            height: DesktopLayout.trafficLightButton,
            alignment: .center
        )
        // Hover glyphs are a macOS behavior; SkipUI has no onHover, so the
        // transpiled Android dots stay inert like the RN non-macOS surface.
        #if !SKIP
        .onHover { hovered in
            self.hovered = hovered
        }
        #endif
        .accessibilityLabel("Window controls")
    }
}

struct TrafficDot: View {
    let kind: DesktopWindowCommand
    let color: Color
    let hovered: Bool
    @State private var pressed = false

    var body: some View {
        Button {
            performDesktopWindowCommand(kind)
        } label: {
            ZStack {
                Circle().fill(color.opacity(pressed ? 0.72 : 1))
                if hovered {
                    glyph
                }
            }
            .frame(
                width: DesktopLayout.trafficLightButton,
                height: DesktopLayout.trafficLightButton
            )
        }
        .buttonStyle(.plain)
        .simultaneousGesture(
            DragGesture(minimumDistance: 0)
                .onChanged { _ in pressed = true }
                .onEnded { _ in pressed = false }
        )
        .accessibilityLabel(accessibilityName)
    }

    private var accessibilityName: String {
        switch kind {
        case .close: return "Close window"
        case .minimize: return "Minimize window"
        case .zoom: return "Zoom window"
        }
    }

    /// Hairline dark ink glyphs, 8 × 1.5 bars at ±45° for close, one bar for
    /// minimize, crossed bars for zoom (DesktopTrafficLights.tsx Glyph).
    @ViewBuilder
    private var glyph: some View {
        let bar = CGRect(x: 0, y: 0, width: 8, height: 1.5)
        ZStack {
            switch kind {
            case .close:
                GlyphBarShape(angleDegrees: 45).fill(.black.opacity(0.55))
                GlyphBarShape(angleDegrees: -45).fill(.black.opacity(0.55))
            case .minimize:
                GlyphBarShape(angleDegrees: 0).fill(.black.opacity(0.55))
            case .zoom:
                GlyphBarShape(angleDegrees: 0).fill(.black.opacity(0.55))
                GlyphBarShape(angleDegrees: 90).fill(.black.opacity(0.55))
            }
        }
        .frame(width: 8, height: 8)
    }
}

/// An 8 × 1.5 bar rotated about its center (RN transform rotate port).
struct GlyphBarShape: Shape {
    var angleDegrees: Double

    func path(in rect: CGRect) -> Path {
        let radians = angleDegrees * Double.pi / 180
        let transform = CGAffineTransform(translationX: 4, y: 0.75)
            .rotated(by: radians)
            .translatedBy(x: -4, y: -0.75)
        let bar = Path(CGRect(x: 0, y: 0, width: 8, height: 1.5))
        var path = Path()
        path.addPath(bar.applying(transform))
        return path
    }
}

// MARK: - Glass pressable (ShippingPressable.tsx)

/// Press feedback of `styles.pressed` (opacity 0.78) with the press motion
/// duration; Reduce Motion collapses it.
struct GlassPressableStyle: ButtonStyle {
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .opacity(configuration.isPressed ? 0.78 : 1)
            .animation(
                DesktopMotion.pressAnimation(reduceMotion),
                value: configuration.isPressed
            )
    }
}

// MARK: - GlassToggle (DesktopSettings.tsx)

/// The house toggle: a glass pill with a sliding thumb, matching the nav pill
/// and segmented controls instead of the system switch.
struct GlassToggle: View {
    let label: String
    let value: Bool
    var disabled = false
    let onValueChange: (Bool) -> Void

    @Environment(\.desktopTokens) private var tokens
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    static let width: CGFloat = 44
    static let height: CGFloat = 26
    static let thumb: CGFloat = 20
    static let travel: CGFloat = width - thumb - 6

    var body: some View {
        Button {
            if !disabled {
                withAnimation(
                    DesktopMotion.smoothOut(
                        DesktopMotion.motionDuration(160, reduceMotion: reduceMotion)
                    )
                ) {
                    onValueChange(!value)
                }
            }
        } label: {
            ZStack(alignment: .leading) {
                Capsule()
                    .fill(value ? tokens.glassSelected : tokens.glassQuiet)
                Capsule()
                    .strokeBorder(tokens.line, lineWidth: 1)
                Circle()
                    .fill(tokens.ink)
                    .frame(width: Self.thumb, height: Self.thumb)
                    .offset(x: value ? Self.travel + 3 : 3)
            }
            .frame(width: Self.width, height: Self.height)
            .opacity(disabled ? 0.48 : 1)
        }
        .buttonStyle(GlassPressableStyle())
        .accessibilityLabel(label)
        .accessibilityAddTraits(value ? .isSelected : [])
        .disabled(disabled)
    }
}

// MARK: - Segmented control (group-by, software plane)

struct DesktopSegmented<Value: Equatable & Sendable>: View {
    let options: [Value]
    let label: (Value) -> String
    let selection: Value
    let onChange: (Value) -> Void

    @Environment(\.desktopTokens) private var tokens
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    var body: some View {
        HStack(spacing: 2) {
            ForEach(Array(options.enumerated()), id: \.offset) { _, option in
                let selected = option == selection
                Button {
                    onChange(option)
                } label: {
                    Text(label(option))
                        .font(.system(size: 12, weight: selected ? .semibold : .medium))
                        .foregroundStyle(selected ? tokens.ink : tokens.inkMuted)
                        .padding(.horizontal, 10)
                        .padding(.vertical, 5)
                        .background(
                            RoundedRectangle(cornerRadius: 10)
                                .fill(selected ? tokens.glassSelected : Color.clear)
                        )
                }
                .buttonStyle(GlassPressableStyle())
                .animation(
                    DesktopMotion.navAnimation(reduceMotion),
                    value: selection
                )
                .accessibilityLabel("Group by \(label(option))")
                .accessibilityAddTraits(selected ? .isSelected : [])
            }
        }
        .padding(2)
        .background(
            RoundedRectangle(cornerRadius: 12)
                .strokeBorder(tokens.line, lineWidth: 1)
        )
    }
}

// MARK: - Scroll fade (ScrollFade.tsx)

/// Bottom fade built from the ink color so it reads on both glass and paper.
struct BottomFade: View {
    @Environment(\.desktopTokens) private var tokens

    var body: some View {
        LinearGradient(
            colors: [tokens.isLight ? tokens.surfaceInk.opacity(0) : tokens.surfaceInk.opacity(0), tokens.isLight ? tokens.surfaceInk.opacity(0.9) : Color.black.opacity(0.28)],
            startPoint: .top,
            endPoint: .bottom
        )
        .frame(height: 26)
        .allowsHitTesting(false)
    }
}

/// Tracks whether a scroll view still has content below the fold and renders
/// the fade into the glass when it does.
struct FadedScrollView<Content: View>: View {
    @ViewBuilder let content: () -> Content

    @State private var contentHeight: CGFloat = 0

    var body: some View {
        GeometryReader { outer in
            ScrollView {
                content()
                    .background(
                        GeometryReader { inner in
                            Color.clear.preference(
                                key: ScrollContentHeightKey.self,
                                value: inner.size.height
                            )
                        }
                    )
            }
            .onPreferenceChange(ScrollContentHeightKey.self) { contentHeight = $0 }
            .overlay(alignment: .bottom) {
                if contentHeight > outer.size.height + 8 {
                    BottomFade()
                }
            }
        }
    }
}

struct ScrollContentHeightKey: PreferenceKey {
    static let defaultValue: CGFloat = 0
    static func reduce(value: inout CGFloat, nextValue: () -> CGFloat) {
        value = max(value, nextValue())
    }
}

// MARK: - Text + row primitives (DesktopRows.tsx)

struct SectionTitle: View {
    let text: String
    @Environment(\.desktopTokens) private var tokens

    init(_ text: String) {
        self.text = text
    }

    var body: some View {
        Text(text.uppercased())
            .font(.system(size: 12, weight: .semibold))
            .foregroundStyle(tokens.inkMuted)
    }
}

struct EmptyCopy: View {
    let text: String
    @Environment(\.desktopTokens) private var tokens

    init(_ text: String) {
        self.text = text
    }

    var body: some View {
        Text(text)
            .font(.system(size: 12))
            .foregroundStyle(tokens.inkMuted)
            .lineSpacing(3)
            .padding(.top, 6)
    }
}

struct PageHeading: View {
    let title: String
    let subtitle: String
    var eyebrow: String?

    @Environment(\.desktopTokens) private var tokens

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            if let eyebrow {
                Text(eyebrow.uppercased())
                    .font(.system(size: 10, weight: .semibold))
                    .foregroundStyle(tokens.inkMuted)
            }
            Text(title)
                .font(.system(size: 29, weight: .medium))
                .foregroundStyle(tokens.ink)
            Text(subtitle)
                .font(.system(size: 14))
                .foregroundStyle(tokens.inkMuted)
        }
        .padding(.bottom, 24)
        .frame(maxWidth: .infinity, alignment: .leading)
    }
}

struct DesktopEmptyStateView: View {
    let title: String
    let detail: String
    var icon: DesktopIcon = .chatBubble
    var error = false

    @Environment(\.desktopTokens) private var tokens

    var body: some View {
        VStack(spacing: 12) {
            icon
                .frame(width: 24, height: 24)
                .foregroundStyle(tokens.inkMuted)
                .padding(14)
                .background(
                    RoundedRectangle(cornerRadius: 18).fill(tokens.glassQuiet)
                )
            Text(title)
                .font(.system(size: 19, weight: .medium))
                .foregroundStyle(tokens.ink)
                .multilineTextAlignment(.center)
            Text(detail)
                .font(.system(size: 13))
                .foregroundStyle(tokens.inkMuted)
                .multilineTextAlignment(.center)
                .frame(maxWidth: 380)
        }
        .padding(32)
        .frame(maxWidth: .infinity, minHeight: 240)
        .background(
            RoundedRectangle(cornerRadius: 18)
                .fill(tokens.glassStrong)
                .overlay(
                    RoundedRectangle(cornerRadius: 18)
                        .strokeBorder(tokens.line, lineWidth: 1)
                )
        )
        .accessibilityHint(error ? "Error" : "")
    }
}

// MARK: - Read rows (DesktopRows.tsx ReadRow / TaskRow / MemoryRow)

extension ConversationProjection {
    var displayTitle: String {
        if !title.isEmpty { return title }
        return status == "processing" ? "Processing conversation…" : "Conversation title unavailable"
    }
}

struct ReadRowView: View {
    let entry: TimelineEntry
    @Environment(\.desktopTokens) private var tokens

    var body: some View {
        HStack(spacing: 10) {
            RowGlyph(kind: entry.kind)
            VStack(alignment: .leading, spacing: 2) {
                Text(entry.title)
                    .font(.system(size: 14, weight: .medium))
                    .foregroundStyle(tokens.ink)
                    .lineLimit(1)
                Text(metaText)
                    .font(.system(size: 12))
                    .foregroundStyle(tokens.inkMuted)
                    .lineLimit(2)
            }
        }
        .padding(.vertical, 8)
        .frame(minHeight: 64, alignment: .center)
    }

    private var metaText: String {
        let parts: [String]
        switch entry.kind {
        case .conversation:
            parts = [timelineTimeLabel(atMs: entry.atMs), entry.detail]
        case .memory:
            parts = [timelineTimeLabel(atMs: entry.atMs), "Memory"]
        default:
            parts = [timelineTimeLabel(atMs: entry.atMs)]
        }
        return parts.filter { !$0.isEmpty }.joined(separator: " · ")
    }
}

struct RowGlyph: View {
    let kind: TimelineEntryKind
    @Environment(\.desktopTokens) private var tokens

    var body: some View {
        ZStack {
            RoundedRectangle(cornerRadius: 12).fill(tokens.glassQuiet)
            glyph
                .frame(width: 16, height: 16)
                .foregroundStyle(tokens.ink)
        }
        .frame(width: 30, height: 30)
    }

    @ViewBuilder
    private var glyph: some View {
        switch kind {
        case .conversation: DesktopIcon.chatBubble
        case .memory: DesktopIcon.sparkles
        case .task: CheckCircleGlyph()
        case .capture: DesktopIcon.monitor
        }
    }
}

struct CheckCircleGlyph: View {
    var body: some View {
        ZStack {
            Circle().inset(by: 1.4).stroke(style: .init(lineWidth: 1.8, lineCap: .round))
            CheckShape()
                .stroke(style: .init(lineWidth: 1.8, lineCap: .round, lineJoin: .round))
                .padding(4.5)
        }
    }
}

struct TaskRowView: View {
    let task: TaskProjection
    let onToggle: () -> Void
    @Environment(\.desktopTokens) private var tokens

    var body: some View {
        Button(action: onToggle) {
            HStack(spacing: 12) {
                ZStack {
                    Circle()
                        .strokeBorder(tokens.inkMuted, lineWidth: 1.5)
                    if task.completed {
                        Circle().fill(tokens.ink)
                    }
                }
                .frame(width: 22, height: 22)
                Text(task.title)
                    .font(.system(size: 14))
                    .foregroundStyle(task.completed ? tokens.inkFaint : tokens.ink)
                    .strikethrough(task.completed)
                    .lineLimit(2)
                Spacer(minLength: 0)
            }
        }
        .buttonStyle(GlassPressableStyle())
        .frame(minHeight: 44)
        .accessibilityLabel(task.title)
        .accessibilityAddTraits(task.completed ? .isSelected : [])
    }
}

struct MemoryCardView: View {
    let memory: MemoryProjection
    @Environment(\.desktopTokens) private var tokens

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(memory.summary)
                .font(.system(size: 14))
                .foregroundStyle(tokens.ink)
                .lineLimit(3)
            Text(dateText)
                .font(.system(size: 12))
                .foregroundStyle(tokens.inkMuted)
        }
        .padding(14)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(RoundedRectangle(cornerRadius: 16).fill(tokens.glassQuiet))
        .padding(.bottom, 10)
    }

    private var dateText: String {
        guard let timestamp = memory.timestamp else { return "Date unavailable" }
        let ms = timestamp > 1_000_000_000_000 ? timestamp : timestamp * 1000
        let formatter = DateFormatter()
        formatter.dateStyle = DateFormatter.Style.medium
        formatter.timeStyle = .none
        return formatter.string(from: Date(timeIntervalSince1970: Double(ms) / 1000.0))
    }
}
