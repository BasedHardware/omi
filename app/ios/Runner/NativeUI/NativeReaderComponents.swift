import SwiftUI
import Charts
import ImageIO

@available(iOS 16.0, *)
struct NativeRichTextView: View {
    let row: NativeSurfaceRow
    @ObservedObject var state: NativeSurfaceState
    let query: String
    private func rich(_ source: String) -> AttributedString {
        nativeHighlighted((try? AttributedString(markdown: source, options: .init(interpretedSyntax: .inlineOnlyPreservingWhitespace))) ?? AttributedString(source), query: query)
    }
    var body: some View {
        let blocks = row.blocks ?? []
        VStack(alignment: .leading, spacing: 0) {
            ForEach(Array(blocks.enumerated()), id: \.offset) { index, block in
                HStack(alignment: .firstTextBaseline, spacing: 8) {
                    if !block.prefix.isEmpty {
                        Text(block.prefix).foregroundStyle(.secondary).monospacedDigit()
                            .frame(minWidth: 18, alignment: .trailing)
                    }
                    content(block).frame(maxWidth: .infinity, alignment: .leading)
                }
                .padding(.leading, CGFloat(block.indent) * 20)
                .padding(.top, index == 0 ? 0 : Self.spacing(before: block, after: blocks[index - 1]))
            }
        }.frame(maxWidth: .infinity, alignment: .leading).textSelection(.enabled)
            .environment(\.openURL, OpenURLAction { url in
                // Native code never opens a URL itself: only a link from this row's whitelist reaches
                // its Dart owner, and without options every link is discarded.
                guard row.enabled, row.options.contains(where: { $0.id == url.absoluteString }) else { return .discarded }
                Task { await state.send(row.id, value: url.absoluteString) }
                return .handled
            })
    }
    /// Space above a block: headings get more above than below, list items stay close, paragraphs breathe.
    private static func spacing(before block: NativeSurfaceRow.RichBlock, after previous: NativeSurfaceRow.RichBlock) -> CGFloat {
        if block.kind == "heading" { return (block.level ?? 1) <= 2 ? 22 : 18 }
        if previous.kind == "heading" { return 8 }
        if !block.prefix.isEmpty && !previous.prefix.isEmpty { return 6 }
        return 12
    }

    private static func headingFont(_ level: Int?) -> Font {
        switch level ?? 1 {
        case 1: return .title2.bold()
        case 2: return .title3.weight(.semibold)
        case 3: return .headline
        default: return .subheadline.weight(.semibold)
        }
    }

    /// Code and tables sit on a translucent fill, so they read on the chat, reader and list-cell backgrounds alike.
    private static var blockBackground: some View {
        RoundedRectangle(cornerRadius: NativeMetrics.blockRadius, style: .continuous)
            .fill(Color(uiColor: .tertiarySystemFill))
    }

    @ViewBuilder private func content(_ block: NativeSurfaceRow.RichBlock) -> some View {
        switch block.kind {
        case "heading":
            Text(rich(block.text)).font(Self.headingFont(block.level))
                .accessibilityAddTraits(.isHeader)
        case "quote":
            HStack(spacing: 10) {
                RoundedRectangle(cornerRadius: 1.5).fill(.tertiary).frame(width: 3)
                Text(rich(block.text)).foregroundStyle(.secondary).lineSpacing(3).padding(.vertical, 2)
            }.fixedSize(horizontal: false, vertical: true)
        case "code":
            ScrollView(.horizontal, showsIndicators: false) {
                Text(nativeHighlighted(AttributedString(block.text), query: query)).font(.callout.monospaced())
                    .lineSpacing(2).padding(.horizontal, 14).padding(.vertical, 12)
            }
            .background(Self.blockBackground)
        case "rule": Divider().padding(.vertical, 4)
        case "image":
            if let url = URL(string: block.uri ?? "") {
                AsyncImage(url: url) { image in image.resizable().scaledToFit() } placeholder: { ProgressView() }
                    .frame(maxWidth: .infinity, maxHeight: 300).accessibilityLabel(block.text)
                if !block.text.isEmpty { Text(nativeHighlighted(AttributedString(block.text), query: query)).font(.caption).foregroundStyle(.secondary) }
            }
        case "table":
            ScrollView(.horizontal, showsIndicators: false) {
                Grid(alignment: .leading, horizontalSpacing: 20, verticalSpacing: 10) {
                    ForEach(Array((block.cells ?? []).enumerated()), id: \.offset) { index, cells in
                        GridRow { ForEach(Array(cells.enumerated()), id: \.offset) { _, cell in
                            Text(rich(cell)).fontWeight(index == 0 ? .semibold : .regular)
                                .fixedSize(horizontal: true, vertical: false)
                        } }
                        if index == 0 { Divider().gridCellUnsizedAxes(.horizontal) }
                    }
                }.padding(.horizontal, 14).padding(.vertical, 12)
            }.background(Self.blockBackground)
        default: Text(rich(block.text)).lineSpacing(3)
        }
    }
}

/// A stable tint per speaker label: the same label always gets the same hue, across launches and devices.
/// Each hue reads at least 4.5:1 on the light and dark reading and card backgrounds; Increase Contrast uses
/// the label colour instead. No hue is purple or violet (INV-UI-1).
enum NativeSpeakerTint {
    private static let hues: [(light: UInt32, dark: UInt32)] = [
        (0x0A64C8, 0x5AA6FF), (0x1B7A33, 0x5AD27A), (0xB04E00, 0xFFA94D), (0x876400, 0xE8C04A),
        (0xBE1A5A, 0xFF7EAB), (0x0D7280, 0x4FD0DB), (0x3F6178, 0x9DBBD0), (0x8A5A2C, 0xD6AC80),
    ]

    static func color(for speaker: String) -> Color {
        // FNV-1a, because Swift's own hash is seeded per process and would change between launches.
        var hash: UInt32 = 2_166_136_261
        for byte in speaker.utf8 { hash = (hash ^ UInt32(byte)) &* 16_777_619 }
        let hue = hues[Int(hash % UInt32(hues.count))]
        return Color(uiColor: UIColor { traits in
            if traits.accessibilityContrast == .high { return .label }
            let rgb = traits.userInterfaceStyle == .dark ? hue.dark : hue.light
            return UIColor(red: CGFloat((rgb >> 16) & 0xFF) / 255, green: CGFloat((rgb >> 8) & 0xFF) / 255,
                           blue: CGFloat(rgb & 0xFF) / 255, alpha: 1)
        })
    }

    /// A transcript row's subtitle, which its owner joins as "speaker · details": the speaker in its tint and
    /// semibold, the details secondary. The text, and so the row's accessibility label, is unchanged.
    static func subtitle(_ subtitle: String, font: Font = .subheadline) -> Text {
        let range = subtitle.range(of: " · ")
        let speaker = String(subtitle[..<(range?.lowerBound ?? subtitle.endIndex)])
        var styled = AttributedString(speaker)
        styled.font = font.weight(.semibold)
        styled.foregroundColor = color(for: speaker)
        if let range {
            var details = AttributedString(String(subtitle[range.lowerBound...]))
            details.font = font
            details.foregroundColor = .secondary
            styled += details
        }
        return Text(styled)
    }
}

func nativeHighlighted(_ source: AttributedString, query: String) -> AttributedString {
    guard !query.isEmpty else { return source }
    var result = source
    let text = String(source.characters)
    var start = text.startIndex
    while start < text.endIndex,
          let range = text.range(of: query, options: .caseInsensitive, range: start..<text.endIndex) {
        if let lower = AttributedString.Index(range.lowerBound, within: result),
           let upper = AttributedString.Index(range.upperBound, within: result) {
            result[lower..<upper].backgroundColor = Color.yellow.opacity(0.4)
        }
        start = range.upperBound
    }
    return result
}

@available(iOS 16.0, *)
struct NativeZoomImage: View {
    let row: NativeSurfaceRow
    @State private var image: UIImage?
    @State private var failed = false

    var body: some View {
        ZStack {
            if let image { NativeZoomScroll(image: image, maximumScale: row.maximumValue ?? 4) }
            else if failed { Image(systemName: "photo.badge.exclamationmark").foregroundStyle(.secondary) }
            else { ProgressView() }
        }.frame(height: 400)
            .clipShape(RoundedRectangle(cornerRadius: NativeMetrics.blockRadius, style: .continuous))
            .accessibilityLabel(row.title)
            .task(id: row.imageUri) {
                image = nil
                failed = false
                guard let url = URL(string: row.imageUri ?? ""), url.isFileURL else { failed = true; return }
                let path = url.resolvingSymlinksInPath().standardizedFileURL.path
                let root = URL(fileURLWithPath: NSHomeDirectory()).resolvingSymlinksInPath().standardizedFileURL.path
                guard path.hasPrefix(root + "/") else { failed = true; return }
                let decoded = await Task.detached(priority: .userInitiated) {
                    guard let source = CGImageSourceCreateWithURL(url as CFURL, [kCGImageSourceShouldCache: false] as CFDictionary) else { return nil as CGImage? }
                    return CGImageSourceCreateThumbnailAtIndex(source, 0, [
                        kCGImageSourceCreateThumbnailFromImageAlways: true,
                        kCGImageSourceCreateThumbnailWithTransform: true,
                        kCGImageSourceThumbnailMaxPixelSize: 4096,
                        kCGImageSourceShouldCacheImmediately: true,
                    ] as CFDictionary)
                }.value
                guard !Task.isCancelled else { return }
                if let decoded { image = UIImage(cgImage: decoded) } else { failed = true }
            }
    }
}

private struct NativeZoomScroll: UIViewRepresentable {
    let image: UIImage
    let maximumScale: Double
    final class Coordinator: NSObject, UIScrollViewDelegate {
        let imageView = UIImageView()
        var locale = Locale.current
        func viewForZooming(in scrollView: UIScrollView) -> UIView? { imageView }
        func scrollViewDidZoom(_ scrollView: UIScrollView) {
            scrollView.accessibilityValue = Double(scrollView.zoomScale).formatted(.percent.precision(.fractionLength(0)).locale(locale))
        }
        @objc func doubleTap(_ gesture: UITapGestureRecognizer) {
            guard let scroll = imageView.superview as? UIScrollView else { return }
            if scroll.zoomScale > 1 { scroll.setZoomScale(1, animated: true) }
            else {
                let scale = min(2, scroll.maximumZoomScale)
                let center = gesture.location(in: imageView)
                let width = scroll.bounds.width / scale
                let height = scroll.bounds.height / scale
                scroll.zoom(to: CGRect(x: center.x - width / 2, y: center.y - height / 2,
                                      width: width, height: height), animated: true)
            }
        }
    }
    func makeCoordinator() -> Coordinator { Coordinator() }
    func makeUIView(context: Context) -> UIScrollView {
        let scroll = UIScrollView()
        scroll.delegate = context.coordinator
        context.coordinator.locale = context.environment.locale
        context.coordinator.scrollViewDidZoom(scroll)
        scroll.minimumZoomScale = 1
        scroll.maximumZoomScale = maximumScale
        scroll.bouncesZoom = true
        scroll.showsHorizontalScrollIndicator = false
        scroll.showsVerticalScrollIndicator = false
        let view = context.coordinator.imageView
        view.contentMode = .scaleAspectFit
        view.autoresizingMask = [.flexibleWidth, .flexibleHeight]
        view.frame = scroll.bounds
        view.image = image
        scroll.addSubview(view)
        let doubleTap = UITapGestureRecognizer(target: context.coordinator, action: #selector(Coordinator.doubleTap))
        doubleTap.numberOfTapsRequired = 2
        scroll.addGestureRecognizer(doubleTap)
        return scroll
    }
    func updateUIView(_ scroll: UIScrollView, context: Context) {
        context.coordinator.locale = context.environment.locale
        context.coordinator.scrollViewDidZoom(scroll)
        scroll.maximumZoomScale = maximumScale
        guard context.coordinator.imageView.image !== image else { return }
        scroll.setZoomScale(1, animated: false)
        context.coordinator.imageView.image = image
        context.coordinator.imageView.frame = CGRect(origin: .zero, size: scroll.bounds.size)
    }
}

@available(iOS 16.0, *)
struct NativePlaybackSlider: View {
    let row: NativeSurfaceRow
    @ObservedObject var state: NativeSurfaceState
    @State private var position = 0.0
    @State private var dragging = false

    var body: some View {
        VStack(spacing: 4) {
            if let points = row.points, !points.isEmpty {
                // Rounded bars like the system's audio scrubbers; played audio is full ink.
                Chart(points) { point in
                    BarMark(x: .value(row.title, point.x),
                            yStart: .value(row.title, -max(0.06, point.y)),
                            yEnd: .value(row.title, max(0.06, point.y)))
                        .cornerRadius(3)
                        .foregroundStyle(Color.primary.opacity(point.label == "missing" ? 0.08 : point.x <= position ? 0.9 : 0.25))
                }.frame(height: 32).chartYScale(domain: -1...1)
                    .chartXScale(domain: 0...(row.maximumValue ?? 1))
                    .chartXAxis(.hidden).chartYAxis(.hidden).accessibilityHidden(true)
                    .padding(.horizontal, 4)
            }
            Slider(value: Binding(get: { position }, set: { value in
                position = value
                Task { await state.send(row.id, value: value) }
            }), in: 0...(row.maximumValue ?? 1), onEditingChanged: { dragging = $0 }) {
                Text(row.title)
            }.accessibilityIdentifier("\(row.id)_slider")
                .accessibilityValue(row.subtitle)
            Text(row.subtitle).font(.footnote).monospacedDigit().foregroundStyle(.secondary)
                .multilineTextAlignment(.center)
        }.onAppear { position = row.value?.number ?? 0 }
            .onChange(of: row.value) { value in if !dragging && !state.pending.contains(row.id) { position = value?.number ?? 0 } }
    }
}

/// A categorical bar or line chart. Point x is the category's index; the axis names the first, the
/// last and every ceil(n/6)th category by its label, so long or many labels stay legible.
@available(iOS 16.0, *)
struct NativeCategoricalChart: View {
    let row: NativeSurfaceRow
    let points: [NativeSurfaceRow.Point]

    private var axisValues: [Double] {
        let step = max(1, (points.count + 5) / 6)
        return points.indices.filter { $0 == 0 || $0 == points.count - 1 || $0 % step == 0 }.map { Double($0) }
    }

    private func label(_ value: AxisValue) -> String {
        guard let x = value.as(Double.self), let index = Int(exactly: x), points.indices.contains(index) else { return "" }
        return points[index].label
    }

    var body: some View {
        Chart(points) { point in
            if row.chartStyle == "bar" {
                BarMark(x: .value(row.subtitle, point.x), y: .value(row.title, point.y))
                    .accessibilityLabel(point.label)
            } else {
                LineMark(x: .value(row.subtitle, point.x), y: .value(row.title, point.y))
                    .interpolationMethod(.catmullRom)
                PointMark(x: .value(row.subtitle, point.x), y: .value(row.title, point.y))
                    .accessibilityLabel(point.label)
            }
        }
        // Half a category of margin keeps a single point, and the first and last bars, inside the plot.
        .chartXScale(domain: -0.5...(Double(points.count) - 0.5))
        .chartXAxis {
            AxisMarks(values: axisValues) { value in
                AxisGridLine()
                AxisTick()
                AxisValueLabel {
                    Text(label(value)).lineLimit(1).truncationMode(.tail).frame(maxWidth: 96)
                }
            }
        }
        .frame(height: 200)
        .accessibilityElement(children: .contain)
        .accessibilityLabel(row.title)
    }
}
