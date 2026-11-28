import Charts
import OmiCore
import OmiDesign
import SwiftUI
import UIKit

/// A chart an answer draws (Flutter `ChartMessageWidget`): line or bar, a legend once there are
/// several series, the backend's colors when it picks them.
struct ChartCard: View {
    let chart: ChatChart

    var body: some View {
        VStack(alignment: .leading, spacing: DS.Spacing.sm) {
            if !chart.title.isEmpty {
                Text(chart.title).font(DS.Typography.callout.weight(.semibold)).foregroundStyle(DS.Palette.ink)
            }
            Chart {
                ForEach(chart.series, id: \.label) { series in
                    ForEach(Array(series.points.enumerated()), id: \.offset) { _, point in
                        switch chart.kind {
                        case .line:
                            LineMark(x: .value(chart.xLabel ?? "x", point.label), y: .value(chart.yLabel ?? "y", point.value))
                                .foregroundStyle(by: .value("series", series.label))
                                .symbol(by: .value("series", series.label))
                        case .bar:
                            BarMark(x: .value(chart.xLabel ?? "x", point.label), y: .value(chart.yLabel ?? "y", point.value))
                                .foregroundStyle(by: .value("series", series.label))
                                .position(by: .value("series", series.label))
                        }
                    }
                }
            }
            .chartForegroundStyleScale(domain: chart.series.map(\.label), range: colors)
            .chartLegend(chart.series.count > 1 ? .visible : .hidden)
            .chartXAxisLabel(chart.xLabel ?? "")
            .chartYAxisLabel(chart.yLabel ?? "")
            .frame(height: 180)
        }
        .padding(DS.Spacing.md)
        .background(DS.Palette.card, in: RoundedRectangle(cornerRadius: DS.Radius.md, style: .continuous))
        .accessibilityElement(children: .combine)
        .accessibilityLabel(chart.title)
    }

    private var colors: [Color] {
        let fallback: [Color] = [DS.Palette.agent, DS.Palette.success, DS.Palette.warning, DS.Palette.live, DS.Palette.inkSecondary]
        return chart.series.enumerated().map { index, series in
            series.color.flatMap(Self.color(hex:)) ?? fallback[index % fallback.count]
        }
    }

    static func color(hex: String) -> Color? {
        let digits = hex.trimmingCharacters(in: CharacterSet(charactersIn: "#"))
        guard digits.count == 6, let value = Int(digits, radix: 16) else { return nil }
        return Color(red: Double((value >> 16) & 0xFF) / 255, green: Double((value >> 8) & 0xFF) / 255, blue: Double(value & 0xFF) / 255)
    }
}

/// Photos and files sent with a question: photo thumbnails, documents as a named chip. A tap
/// opens the photo large, or the file's page (ask Omi about it again).
struct MessageFiles: View {
    let files: [ChatFile]
    /// "Ask about it" on a file's page: a question about the file into the composer.
    var onAsk: ((ChatFile) -> Void)?
    @State private var previewed: ChatFile?

    var body: some View {
        HStack(spacing: DS.Spacing.xs) {
            Spacer(minLength: 48)
            ForEach(files) { file in
                Button { previewed = file } label: {
                    if file.isImage {
                        AttachmentThumbnail(preview: file.localPreview, url: file.thumbnailURL)
                            .frame(width: 72, height: 72)
                            .clipShape(RoundedRectangle(cornerRadius: DS.Radius.sm, style: .continuous))
                    } else {
                        DocumentChip(name: file.name)
                    }
                }
                .buttonStyle(.plain)
                .accessibilityLabel(file.name)
                .accessibilityIdentifier("chat.file")
            }
        }
        .sheet(item: $previewed) { file in
            FilePreviewSheet(file: file) { onAsk?(file) }
        }
    }
}

/// A sent photo, large; or a sent file's name and type, with "Ask about it".
struct FilePreviewSheet: View {
    @Environment(\.dismiss) private var dismiss
    let file: ChatFile
    let onAsk: () -> Void

    var body: some View {
        NavigationStack {
            Group {
                if file.isImage {
                    AttachmentThumbnail(preview: file.localPreview, url: file.thumbnailURL)
                        .scaledToFit()
                        .frame(maxWidth: .infinity, maxHeight: .infinity)
                        .clipShape(RoundedRectangle(cornerRadius: DS.Radius.md, style: .continuous))
                        .padding(DS.Spacing.gutter)
                } else {
                    VStack(spacing: DS.Spacing.md) {
                        Image(systemName: "doc.text").font(.system(size: 44, weight: .light)).foregroundStyle(DS.Palette.inkSecondary)
                        Text(file.name).font(DS.Typography.body.weight(.medium)).multilineTextAlignment(.center)
                        Text(L("nativeChatFileSent")).font(DS.Typography.caption).foregroundStyle(DS.Palette.inkSecondary)
                    }
                    .padding(DS.Spacing.gutter)
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
                }
            }
            .background(DS.Palette.background)
            .navigationTitle(file.isImage ? "" : file.name)
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button(L("close")) { dismiss() }
                }
                ToolbarItem(placement: .confirmationAction) {
                    Button(L("nativeChatAskAboutFile")) {
                        dismiss()
                        onAsk()
                    }
                }
            }
        }
        .presentationDetents([.medium, .large])
    }
}

/// A photo from the phone's preview, else the backend thumbnail.
struct AttachmentThumbnail: View {
    let preview: Data?
    var url: URL?

    var body: some View {
        if let preview, let image = UIImage(data: preview) {
            Image(uiImage: image).resizable().scaledToFill()
        } else if let url {
            AsyncImage(url: url) { image in
                image.resizable().scaledToFill()
            } placeholder: {
                DS.Palette.fill
            }
        } else {
            ZStack {
                DS.Palette.fill
                Image(systemName: "photo").foregroundStyle(DS.Palette.inkTertiary)
            }
        }
    }
}

struct DocumentChip: View {
    let name: String

    var body: some View {
        Label(name, systemImage: "doc.text")
            .font(DS.Typography.caption)
            .lineLimit(1)
            .truncationMode(.middle)
            .foregroundStyle(DS.Palette.ink)
            .padding(.horizontal, DS.Spacing.md)
            .frame(maxWidth: 180, minHeight: 36)
            .background(DS.Palette.fill, in: RoundedRectangle(cornerRadius: DS.Radius.sm, style: .continuous))
    }
}
