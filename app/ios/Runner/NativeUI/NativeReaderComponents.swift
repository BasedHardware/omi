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
        VStack(alignment: .leading, spacing: 16) {
            ForEach(Array((row.blocks ?? []).enumerated()), id: \.offset) { _, block in
                HStack(alignment: .top, spacing: 10) {
                    if !block.prefix.isEmpty { Text(block.prefix).frame(minWidth: 16, alignment: .trailing) }
                    content(block).frame(maxWidth: .infinity, alignment: .leading)
                }.padding(.leading, CGFloat(block.indent) * 16)
            }
        }.frame(maxWidth: .infinity, alignment: .leading).textSelection(.enabled)
            .environment(\.openURL, OpenURLAction { url in
                guard !row.options.isEmpty else { return .systemAction }
                guard row.options.contains(where: { $0.id == url.absoluteString }) else { return .discarded }
                Task { await state.send(row.id, value: url.absoluteString) }
                return .handled
            })
    }
    @ViewBuilder private func content(_ block: NativeSurfaceRow.RichBlock) -> some View {
        switch block.kind {
        case "heading":
            Text(rich(block.text)).font(block.level == 1 ? .title2.bold() : .headline)
                .accessibilityAddTraits(.isHeader)
        case "quote":
            HStack { RoundedRectangle(cornerRadius: 2).fill(.secondary).frame(width: 3)
                Text(rich(block.text)).foregroundStyle(.secondary) }.fixedSize(horizontal: false, vertical: true)
        case "code":
            ScrollView(.horizontal) { Text(nativeHighlighted(AttributedString(block.text), query: query)).font(.body.monospaced()).padding(12) }
                .background(Color(uiColor: .secondarySystemGroupedBackground), in: RoundedRectangle(cornerRadius: 12))
        case "rule": Divider()
        case "image":
            if let url = URL(string: block.uri ?? "") {
                AsyncImage(url: url) { image in image.resizable().scaledToFit() } placeholder: { ProgressView() }
                    .frame(maxWidth: .infinity, maxHeight: 300).accessibilityLabel(block.text)
                if !block.text.isEmpty { Text(nativeHighlighted(AttributedString(block.text), query: query)).font(.caption).foregroundStyle(.secondary) }
            }
        case "table":
            ScrollView(.horizontal) {
                Grid(alignment: .leading, horizontalSpacing: 16, verticalSpacing: 10) {
                    ForEach(Array((block.cells ?? []).enumerated()), id: \.offset) { index, cells in
                        GridRow { ForEach(Array(cells.enumerated()), id: \.offset) { _, cell in
                            Text(rich(cell)).fontWeight(index == 0 ? .semibold : .regular)
                                .fixedSize(horizontal: true, vertical: false)
                        } }
                        if index == 0 { Divider().gridCellUnsizedAxes(.horizontal) }
                    }
                }.padding(12)
            }.background(Color(uiColor: .secondarySystemGroupedBackground), in: RoundedRectangle(cornerRadius: 12))
        default: Text(rich(block.text)).lineSpacing(4)
        }
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
        }.frame(height: 400).accessibilityLabel(row.title)
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
                Chart(points) { point in
                    BarMark(x: .value(row.title, point.x),
                            yStart: .value(row.title, -max(0.04, point.y)),
                            yEnd: .value(row.title, max(0.04, point.y)))
                        .foregroundStyle(Color.primary.opacity(point.label == "missing" ? 0.1 : point.x <= position ? 1 : 0.3))
                }.frame(height: 28).chartYScale(domain: -1...1)
                    .chartXScale(domain: 0...(row.maximumValue ?? 1))
                    .chartXAxis(.hidden).chartYAxis(.hidden).accessibilityHidden(true)
            }
            Slider(value: Binding(get: { position }, set: { value in
                position = value
                Task { await state.send(row.id, value: value) }
            }), in: 0...(row.maximumValue ?? 1), onEditingChanged: { dragging = $0 }) {
                Text(row.title)
            }.accessibilityIdentifier("\(row.id)_slider")
                .accessibilityValue(row.subtitle)
            Text(row.subtitle).font(.caption).monospacedDigit().foregroundStyle(.secondary)
        }.onAppear { position = row.value?.number ?? 0 }
            .onChange(of: row.value) { value in if !dragging && !state.pending.contains(row.id) { position = value?.number ?? 0 } }
    }
}
