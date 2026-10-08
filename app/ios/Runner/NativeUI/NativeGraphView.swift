import SwiftUI
import UIKit

/// The native camera of one graph row. It lives only in NativeSurfaceState and never crosses back
/// to Dart; the existing simulation owner supplies positions and receives node selections only.
struct NativeGraphCamera: Equatable {
    var rotationX = 0.0
    var rotationY = 0.0
    var panX = 0.0
    var panY = 0.0
    var zoom = 1.0

    static let zoomRange = 0.05...5.0
}

/// GraphPainter3D's projection: rotate about Y, then about X, and project from a camera at z = 1500.
enum NativeGraphProjection {
    struct Point {
        let x: Double
        let y: Double
        let z: Double
        let scale: Double
        /// Depth fade before selection dimming.
        let alpha: Double
    }

    static let cameraZ = 1500.0
    static let nodeRadius = 12.0

    /// One entry per node, in node order; nil for a node at or behind the camera.
    static func project(_ graph: NativeSurfaceRow.Graph, camera: NativeGraphCamera, size: CGSize) -> [Point?] {
        let cosY = cos(camera.rotationY), sinY = sin(camera.rotationY)
        let cosX = cos(camera.rotationX), sinX = sin(camera.rotationX)
        let centerX = Double(size.width) / 2, centerY = Double(size.height) / 2
        return graph.nodes.map { node in
            let x1 = node.x * cosY - node.z * sinY
            let z1 = node.x * sinY + node.z * cosY
            let y2 = node.y * cosX - z1 * sinX
            let z2 = node.y * sinX + z1 * cosX
            guard cameraZ - z2 > 0 else { return nil }
            let perspective = cameraZ / (cameraZ - z2) * camera.zoom
            let x = centerX + x1 * perspective + camera.panX
            let y = centerY + y2 * perspective + camera.panY
            guard perspective.isFinite, x.isFinite, y.isFinite else { return nil }
            return Point(x: x, y: y, z: z2, scale: perspective, alpha: min(max(1 + z2 / 2500, 0), 1))
        }
    }

    /// The nearest projected node within max(radius * 1.5, 20) points, capped at 30; nil for the background.
    static func hit(_ graph: NativeSurfaceRow.Graph, camera: NativeGraphCamera, size: CGSize, at location: CGPoint) -> String? {
        var nearest: (distance: Double, id: String)?
        for (node, point) in zip(graph.nodes, project(graph, camera: camera, size: size)) {
            guard let point else { continue }
            let distance = hypot(point.x - Double(location.x), point.y - Double(location.y))
            let threshold = min(max(nodeRadius * point.scale * 1.5, 20), 30)
            if distance < threshold, distance < (nearest?.distance ?? .infinity) { nearest = (distance, node.id) }
        }
        return nearest?.id
    }
}

/// Draws a graph exactly as the Flutter GraphPainter3D does: edges first, then nodes back to front,
/// with halo rings, a radial fill, depth fade and 15% dimming outside the current selection.
@available(iOS 16.0, *)
struct NativeGraphCanvas: View {
    let graph: NativeSurfaceRow.Graph
    let camera: NativeGraphCamera
    @Environment(\.colorScheme) private var colorScheme

    var body: some View {
        Canvas { context, size in
            Self.draw(graph, camera: camera, light: colorScheme == .light, size: size, in: &context)
        }
    }

    private struct RGB {
        let red: Double, green: Double, blue: Double
        static let white = RGB(red: 1, green: 1, blue: 1)
        init(red: Double, green: Double, blue: Double) { self.red = red; self.green = green; self.blue = blue }
        init(hex: String) {
            let value = UInt32(hex.dropFirst(), radix: 16) ?? 0
            self.init(red: Double((value >> 16) & 255) / 255, green: Double((value >> 8) & 255) / 255,
                      blue: Double(value & 255) / 255)
        }
        func mixed(with other: RGB) -> RGB {
            RGB(red: (red + other.red) / 2, green: (green + other.green) / 2, blue: (blue + other.blue) / 2)
        }
        func color(_ opacity: Double) -> Color { Color(red: red, green: green, blue: blue, opacity: min(max(opacity, 0), 1)) }
    }

    private static let palette: [String: RGB] = [
        "person": RGB(hex: "#18FFFF"), "place": RGB(hex: "#00FF9D"), "organization": RGB(hex: "#FFAB40"),
        "thing": RGB(hex: "#FFFF00"), "concept": RGB(hex: "#448AFF"),
    ]
    // OmiPalette.light's border, surface1 and textPrimary; the dark scheme draws in white.
    private static let lightBorder = RGB(hex: "#C6C6C8")
    private static let lightSurface = RGB(hex: "#FFFFFF")
    private static let lightText = RGB(hex: "#000000")

    /// In the light scheme a label sits on a rounded surface1 background, as in Flutter.
    private static func drawLabel(_ text: GraphicsContext.ResolvedText, at origin: CGPoint, light: Bool,
                                  padding: CGSize, in context: inout GraphicsContext) {
        let size = text.measure(in: CGSize(width: 10_000, height: 10_000))
        if light {
            let background = CGRect(x: origin.x - padding.width, y: origin.y - padding.height,
                                    width: size.width + padding.width * 2, height: size.height + padding.height * 2)
            context.fill(Path(roundedRect: background, cornerRadius: 4), with: .color(lightSurface.color(0.88)))
        }
        context.draw(text, in: CGRect(origin: origin, size: size))
    }

    static func draw(_ graph: NativeSurfaceRow.Graph, camera: NativeGraphCamera, light: Bool, size: CGSize,
                     in context: inout GraphicsContext) {
        let ink = light ? lightText : RGB.white
        let accent = RGB(hex: graph.accent)
        let highlighted = Set(graph.highlighted)
        var points: [String: (point: NativeGraphProjection.Point, alpha: Double)] = [:]
        var order: [(node: NativeSurfaceRow.Graph.Node, point: NativeGraphProjection.Point, alpha: Double)] = []
        for (node, projected) in zip(graph.nodes, NativeGraphProjection.project(graph, camera: camera, size: size)) {
            guard let projected else { continue }
            let alpha = highlighted.isEmpty || highlighted.contains(node.id) ? projected.alpha : projected.alpha * 0.15
            points[node.id] = (projected, alpha)
            order.append((node, projected, alpha))
        }

        for edge in graph.edges {
            guard let first = points[edge.source], let second = points[edge.target] else { continue }
            let alpha = min(max((first.alpha + second.alpha) / 2 * 0.10, 0), 1)
            guard alpha >= 0.05 else { continue }
            let scale = (first.point.scale + second.point.scale) / 2
            let highlightedEdge = highlighted.contains(edge.source) && highlighted.contains(edge.target)
            let dimmed = !highlighted.isEmpty && !highlightedEdge
            let line = light ? lightBorder : RGB.white
            var color = line.color(alpha)
            if dimmed {
                color = line.color(alpha * 0.1)
            } else if highlightedEdge {
                color = (light ? accent : RGB.white).color(max(alpha, 0.8))
            }
            var path = Path()
            path.move(to: CGPoint(x: first.point.x, y: first.point.y))
            path.addLine(to: CGPoint(x: second.point.x, y: second.point.y))
            context.stroke(path, with: .color(color), style: StrokeStyle(lineWidth: CGFloat(0.8 * scale), lineCap: .round))
            // Flutter also asks for an edge alpha above 0.1, which its 0.1 multiplier never reaches;
            // the label keeps Flutter's colour (alpha * 2) and is hidden only on a dimmed edge.
            guard !edge.label.isEmpty, scale > 0.6, !dimmed else { continue }
            let text = context.resolve(Text(edge.label)
                .font(.system(size: CGFloat(min(max(9 * scale, 7), 11))))
                .foregroundColor(ink.color(alpha * 2)))
            let measured = text.measure(in: CGSize(width: 10_000, height: 10_000))
            let middle = CGPoint(x: (first.point.x + second.point.x) / 2 - Double(measured.width) / 2,
                                 y: (first.point.y + second.point.y) / 2 - Double(measured.height) / 2 - 8)
            drawLabel(text, at: middle, light: light, padding: CGSize(width: 4, height: 2), in: &context)
        }

        for (node, point, alpha) in order.sorted(by: { $0.point.z < $1.point.z }) {
            let radius = NativeGraphProjection.nodeRadius * point.scale
            guard radius >= 0.5 else { continue }
            let base = node.type == "user" ? accent : palette[node.type] ?? RGB(hex: "#448AFF")
            func circle(_ radius: Double) -> Path {
                Path(ellipseIn: CGRect(x: point.x - radius, y: point.y - radius, width: radius * 2, height: radius * 2))
            }
            if radius > 3 {
                context.stroke(circle(radius * 1.8), with: .color(base.color(alpha * 0.3)), lineWidth: CGFloat(1.5 * point.scale))
                context.stroke(circle(radius * 2.5), with: .color(base.color(alpha * 0.15)), lineWidth: CGFloat(point.scale))
            }
            let highlight = light ? base : RGB.white
            let gradient = Gradient(stops: [
                .init(color: highlight.color(alpha * 0.9), location: 0),
                .init(color: highlight.mixed(with: base).color(alpha), location: 0.3),
                .init(color: base.color(alpha), location: 1),
            ])
            context.fill(circle(radius), with: .radialGradient(
                gradient, center: CGPoint(x: point.x - radius * 0.25, y: point.y - radius * 0.25),
                startRadius: 0, endRadius: CGFloat(radius * 1.2)))
            guard point.scale > 0.7, alpha > 0.5, radius > 4, !node.label.isEmpty else { continue }
            let text = context.resolve(Text(node.label)
                .font(.system(size: CGFloat(min(max(10 * point.scale, 8), 14)), weight: .semibold))
                .foregroundColor(ink.color(alpha * 0.9)))
            let measured = text.measure(in: CGSize(width: 10_000, height: 10_000))
            drawLabel(text, at: CGPoint(x: point.x - Double(measured.width) / 2, y: point.y + radius + 3), light: light,
                      padding: CGSize(width: 4, height: 3), in: &context)
        }
    }
}

/// The loading skeleton: a hub with a few clusters that pulses six times, then rests. It stays
/// static under Reduce Motion.
@available(iOS 16.0, *)
struct NativeGraphPlaceholder: View {
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @Environment(\.nativeGraphReduceMotion) private var forcedReduceMotion
    @State private var dimmed = false

    // Positions as fractions of the frame, and radii in points.
    private static let nodes: [(x: Double, y: Double, radius: Double)] = [
        (0.50, 0.50, 9), (0.30, 0.32, 6), (0.68, 0.28, 6), (0.72, 0.68, 7), (0.32, 0.72, 5),
        (0.16, 0.50, 4), (0.86, 0.46, 4), (0.52, 0.16, 4), (0.55, 0.84, 4),
    ]
    private static let edges = [(0, 1), (0, 2), (0, 3), (0, 4), (1, 5), (2, 7), (3, 6), (3, 8), (4, 5), (1, 7)]

    var body: some View {
        Canvas { context, size in
            func point(_ index: Int) -> CGPoint {
                CGPoint(x: Self.nodes[index].x * Double(size.width), y: Self.nodes[index].y * Double(size.height))
            }
            var lines = Path()
            for (first, second) in Self.edges {
                lines.move(to: point(first))
                lines.addLine(to: point(second))
            }
            context.stroke(lines, with: .color(Color(uiColor: .separator)), lineWidth: 1.2)
            for (index, node) in Self.nodes.enumerated() {
                let center = point(index)
                context.fill(Path(ellipseIn: CGRect(x: Double(center.x) - node.radius, y: Double(center.y) - node.radius,
                                                    width: node.radius * 2, height: node.radius * 2)),
                             with: .color(Color(uiColor: .systemGray3)))
            }
        }
        .opacity(dimmed ? 0.55 : 1)
        .accessibilityHidden(true)
        .task(id: reduceMotion || forcedReduceMotion) {
            dimmed = false
            guard !reduceMotion && !forcedReduceMotion else { return }
            // Six pulses, each a dim and a return, so it rests at full opacity.
            for _ in 0..<12 {
                withAnimation(.easeInOut(duration: 0.6)) { dimmed.toggle() }
                try? await Task.sleep(nanoseconds: 600_000_000)
                guard !Task.isCancelled else { return }
            }
        }
    }
}

/// Stands in for the system Reduce Motion setting in the Preview fixture, which a UI test cannot
/// toggle. Production never sets it.
private struct NativeGraphReduceMotionKey: EnvironmentKey {
    static let defaultValue = false
}

extension EnvironmentValues {
    var nativeGraphReduceMotion: Bool {
        get { self[NativeGraphReduceMotionKey.self] }
        set { self[NativeGraphReduceMotionKey.self] = newValue }
    }
}

/// A graph row's canvas. On the fill stage it adds the camera gestures, node selection and one
/// accessibility element per node; a card draws the same canvas without either.
@available(iOS 16.0, *)
struct NativeGraphView: View {
    let row: NativeSurfaceRow
    let graph: NativeSurfaceRow.Graph
    @Binding var camera: NativeGraphCamera
    var stage = false
    /// Receives a node id, or "" for the background. Nil when this graph sends nothing.
    var select: ((String) -> Void)?
    var resized: (CGSize) -> Void = { _ in }

    var body: some View {
        GeometryReader { proxy in
            Group {
                if graph.placeholder {
                    NativeGraphPlaceholder()
                } else {
                    NativeGraphCanvas(graph: graph, camera: camera)
                        .overlay {
                            if stage {
                                NativeGraphGestures(camera: $camera) { location, size in
                                    select?(NativeGraphProjection.hit(graph, camera: camera, size: size, at: location) ?? "")
                                }
                            }
                        }
                }
            }
            .onAppear { resized(proxy.size) }
            .onChange(of: proxy.size) { size in resized(size) }
            .modifier(NativeGraphAccessibility(row: row, graph: graph, camera: $camera, stage: stage,
                                               select: select, size: proxy.size))
        }
    }
}

/// VoiceOver lists one element per node (its label, selected when highlighted) whose default action
/// selects it, and the adjustable action zooms the native camera.
@available(iOS 16.0, *)
private struct NativeGraphAccessibility: ViewModifier {
    let row: NativeSurfaceRow
    let graph: NativeSurfaceRow.Graph
    @Binding var camera: NativeGraphCamera
    let stage: Bool
    let select: ((String) -> Void)?
    let size: CGSize

    func body(content: Content) -> some View {
        if stage && !graph.placeholder {
            content
                .accessibilityElement(children: .contain)
                .accessibilityLabel(row.title)
                .accessibilityValue(zoomText)
                .accessibilityChildren { nodes }
                .accessibilityIdentifier(row.id)
        } else if stage {
            content.accessibilityElement(children: .ignore).accessibilityLabel(row.title)
                .accessibilityIdentifier(row.id)
        } else {
            // A card's Button carries the row's identifier and label.
            content.accessibilityElement(children: .ignore).accessibilityLabel(row.title)
        }
    }

    private var zoomText: String { camera.zoom.formatted(.percent.precision(.fractionLength(0))) }

    /// A container with adjustable traits would hide its children from VoiceOver, so the zoom is its
    /// own element, first and spanning the graph. Each node element sits on its projected node, so
    /// its frame is where the node is drawn.
    private var nodes: some View {
        let points = NativeGraphProjection.project(graph, camera: camera, size: size)
        let highlighted = Set(graph.highlighted)
        return ZStack {
            Text(row.title)
                .frame(width: size.width, height: size.height)
                .accessibilityValue(zoomText)
                .accessibilityAdjustableAction { direction in
                    switch direction {
                    case .increment: camera.zoom = min(camera.zoom * 1.25, NativeGraphCamera.zoomRange.upperBound)
                    case .decrement: camera.zoom = max(camera.zoom / 1.25, NativeGraphCamera.zoomRange.lowerBound)
                    @unknown default: break
                    }
                }
                .accessibilityIdentifier("\(row.id)_zoom")
            ForEach(graph.nodes.indices, id: \.self) { index in
                nodeElement(graph.nodes[index], at: points[index], selected: highlighted.contains(graph.nodes[index].id))
            }
        }.frame(width: size.width, height: size.height)
    }

    private func nodeElement(_ node: NativeSurfaceRow.Graph.Node, at point: NativeGraphProjection.Point?,
                             selected: Bool) -> some View {
        let diameter = CGFloat(max(NativeGraphProjection.nodeRadius * (point?.scale ?? 1) * 2, 44))
        let x = point?.x ?? Double(size.width) / 2
        let y = point?.y ?? Double(size.height) / 2
        let traits: AccessibilityTraits = select == nil ? [] : [.isButton]
        return Text(node.label)
            .frame(width: diameter, height: diameter)
            .position(x: CGFloat(x), y: CGFloat(y))
            .accessibilityAddTraits(selected ? traits.union(.isSelected) : traits)
            .accessibilityAction { select?(node.id) }
            .accessibilityIdentifier("\(row.id)_node_\(node.id)")
    }
}

/// UIKit recognisers over the canvas: one finger rotates at 0.005 rad/pt, two fingers pan, a pinch
/// zooms within 0.05...5, and a tap reports its location. Only the tap can send anything.
@available(iOS 16.0, *)
private struct NativeGraphGestures: UIViewRepresentable {
    @Binding var camera: NativeGraphCamera
    let tap: (CGPoint, CGSize) -> Void

    func makeCoordinator() -> Coordinator { Coordinator(self) }

    func makeUIView(context: Context) -> UIView {
        let view = UIView()
        view.backgroundColor = .clear
        view.isAccessibilityElement = false
        let coordinator = context.coordinator
        let rotate = UIPanGestureRecognizer(target: coordinator, action: #selector(Coordinator.rotate(_:)))
        rotate.maximumNumberOfTouches = 1
        let pan = UIPanGestureRecognizer(target: coordinator, action: #selector(Coordinator.pan(_:)))
        pan.minimumNumberOfTouches = 2
        pan.maximumNumberOfTouches = 2
        let pinch = UIPinchGestureRecognizer(target: coordinator, action: #selector(Coordinator.pinch(_:)))
        let tap = UITapGestureRecognizer(target: coordinator, action: #selector(Coordinator.tap(_:)))
        for recognizer in [rotate, pan, pinch, tap] as [UIGestureRecognizer] {
            recognizer.delegate = coordinator
            view.addGestureRecognizer(recognizer)
        }
        return view
    }

    func updateUIView(_ view: UIView, context: Context) { context.coordinator.parent = self }

    final class Coordinator: NSObject, UIGestureRecognizerDelegate {
        var parent: NativeGraphGestures
        private var baseZoom = 1.0

        init(_ parent: NativeGraphGestures) { self.parent = parent }

        @objc func rotate(_ recognizer: UIPanGestureRecognizer) {
            let delta = recognizer.translation(in: recognizer.view)
            recognizer.setTranslation(.zero, in: recognizer.view)
            // Once a second finger lands, the camera pans instead, as Flutter's pointer count decides.
            guard recognizer.numberOfTouches == 1 else { return }
            var camera = parent.camera
            camera.rotationY -= Double(delta.x) * 0.005
            camera.rotationX += Double(delta.y) * 0.005
            parent.camera = camera
        }

        @objc func pan(_ recognizer: UIPanGestureRecognizer) {
            let delta = recognizer.translation(in: recognizer.view)
            recognizer.setTranslation(.zero, in: recognizer.view)
            var camera = parent.camera
            camera.panX += Double(delta.x)
            camera.panY += Double(delta.y)
            parent.camera = camera
        }

        @objc func pinch(_ recognizer: UIPinchGestureRecognizer) {
            if recognizer.state == .began { baseZoom = parent.camera.zoom }
            let zoom = baseZoom * Double(recognizer.scale)
            guard zoom.isFinite else { return }
            parent.camera.zoom = min(max(zoom, NativeGraphCamera.zoomRange.lowerBound), NativeGraphCamera.zoomRange.upperBound)
        }

        @objc func tap(_ recognizer: UITapGestureRecognizer) {
            guard recognizer.state == .ended, let view = recognizer.view else { return }
            parent.tap(recognizer.location(in: view), view.bounds.size)
        }

        // Two-finger pan and pinch move the camera together, as the Flutter scale gesture does.
        func gestureRecognizer(_ gestureRecognizer: UIGestureRecognizer,
                               shouldRecognizeSimultaneouslyWith other: UIGestureRecognizer) -> Bool {
            !(gestureRecognizer is UITapGestureRecognizer) && !(other is UITapGestureRecognizer)
        }
    }
}

/// Renders one graph row for an explicit share, at the size it was last drawn and with its current
/// camera. Nothing is cached; the PNG goes straight back to the existing Dart share owner.
@available(iOS 16.0, *)
enum NativeGraphCapture {
    static let maximumPixels = 16_000_000.0
    static let maximumBytes = 16 * 1024 * 1024

    @MainActor
    static func png(_ graph: NativeSurfaceRow.Graph, camera: NativeGraphCamera, size: CGSize,
                    colorScheme: ColorScheme) -> Data? {
        let width = Double(size.width), height = Double(size.height)
        guard !graph.placeholder, width.isFinite, height.isFinite, width > 0, height > 0,
              (width * height).isFinite else { return nil }
        var scale = min(3, (maximumPixels / (width * height)).squareRoot())
        // Rounding up to whole pixels must not cross the 16 MP bound either.
        while (width * scale).rounded(.up) * (height * scale).rounded(.up) > maximumPixels { scale *= 0.999 }
        let renderer = ImageRenderer(content: NativeGraphCanvas(graph: graph, camera: camera)
            .frame(width: size.width, height: size.height)
            .environment(\.colorScheme, colorScheme))
        renderer.scale = CGFloat(scale)
        renderer.isOpaque = false
        guard let image = renderer.cgImage, Double(image.width) * Double(image.height) <= maximumPixels,
              let data = UIImage(cgImage: image).pngData(), data.count <= maximumBytes else { return nil }
        return data
    }
}
