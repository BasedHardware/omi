import OmiDesign
import OmiNetwork
import OmiService
import SwiftUI

/// The memory graph drawn natively: lines between linked things, a dot and label per node, the
/// user in the middle. Tap a node to light up what it connects to; drag and pinch to look around.
/// Used by Memories › Memory graph and Settings › What I know about you.
public struct KnowledgeGraphView: View {
    let store: KnowledgeGraphStore
    let interactive: Bool
    @State private var selected: String?
    @State private var zoom: CGFloat = 1
    @State private var settledZoom: CGFloat = 1
    @State private var offset: CGSize = .zero
    @State private var settledOffset: CGSize = .zero

    public init(store: KnowledgeGraphStore, interactive: Bool = true) {
        self.store = store
        self.interactive = interactive
    }

    public var body: some View {
        GeometryReader { proxy in
            let layout = Layout(size: proxy.size, zoom: zoom, offset: offset)
            ZStack {
                Canvas { context, _ in draw(in: &context, layout: layout) }
                ForEach(store.nodes) { node in
                    label(node).position(layout.point(node))
                }
            }
            .contentShape(Rectangle())
            .gesture(gestures, including: interactive ? .all : .subviews)
            .onTapGesture { location in tap(at: location, layout: layout) }
        }
        .accessibilityElement(children: .contain)
        .accessibilityLabel(L("memoryGraph"))
    }

    public static func color(for kind: String) -> Color {
        switch kind {
        case "user": DS.Palette.agent
        case "person": .cyan
        case "place": .green
        case "organization": .orange
        case "thing": .yellow
        default: .blue
        }
    }

    private var lit: Set<String> {
        guard let selected else { return [] }
        return store.neighbors(of: selected).union([selected])
    }

    private func draw(in context: inout GraphicsContext, layout: Layout) {
        let lit = lit
        let points = Dictionary(store.nodes.map { ($0.id, layout.point($0)) }, uniquingKeysWith: { first, _ in first })
        for edge in store.edges {
            guard let from = points[edge.source], let to = points[edge.target] else { continue }
            var path = Path()
            path.move(to: from)
            path.addLine(to: to)
            let highlighted = lit.contains(edge.source) && lit.contains(edge.target)
            context.stroke(path, with: .color(DS.Palette.ink.opacity(highlighted ? 0.5 : lit.isEmpty ? 0.14 : 0.05)), lineWidth: 1)
        }
        for node in store.nodes {
            let center = points[node.id] ?? .zero
            let radius: CGFloat = node.isUser ? 11 : 6
            let dimmed = !lit.isEmpty && !lit.contains(node.id)
            context.fill(
                Path(ellipseIn: CGRect(x: center.x - radius, y: center.y - radius, width: radius * 2, height: radius * 2)),
                with: .color(Self.color(for: node.node.kind).opacity(dimmed ? 0.25 : 1))
            )
        }
    }

    private func label(_ node: KnowledgeGraphStore.PlacedNode) -> some View {
        let dimmed = !lit.isEmpty && !lit.contains(node.id)
        return Text(node.node.label)
            .font(node.isUser ? DS.Typography.callout.weight(.semibold) : DS.Typography.micro)
            .foregroundStyle(DS.Palette.ink.opacity(dimmed ? 0.3 : 0.9))
            .lineLimit(1)
            .frame(maxWidth: 110)
            .offset(y: node.isUser ? 20 : 14)
            .allowsHitTesting(false)
    }

    private var gestures: some Gesture {
        SimultaneousGesture(
            DragGesture()
                .onChanged {
                    offset = CGSize(width: settledOffset.width + $0.translation.width, height: settledOffset.height + $0.translation.height)
                }
                .onEnded { _ in settledOffset = offset },
            MagnifyGesture()
                .onChanged { zoom = min(max(settledZoom * $0.magnification, 0.5), 4) }
                .onEnded { _ in settledZoom = zoom }
        )
    }

    private func tap(at location: CGPoint, layout: Layout) {
        let nearest = store.nodes.min { distance(layout.point($0), location) < distance(layout.point($1), location) }
        guard let nearest, distance(layout.point(nearest), location) < 28 else {
            selected = nil
            return
        }
        DSHaptics.selection()
        selected = selected == nearest.id ? nil : nearest.id
    }

    private func distance(_ a: CGPoint, _ b: CGPoint) -> CGFloat {
        hypot(a.x - b.x, a.y - b.y)
    }

    private struct Layout {
        let size: CGSize
        let zoom: CGFloat
        let offset: CGSize

        func point(_ node: KnowledgeGraphStore.PlacedNode) -> CGPoint {
            let reach = min(size.width, size.height) / 2 - 36
            return CGPoint(
                x: size.width / 2 + offset.width + CGFloat(node.x) * reach * zoom,
                y: size.height / 2 + offset.height + CGFloat(node.y) * reach * zoom
            )
        }
    }
}
