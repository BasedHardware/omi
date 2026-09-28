import OmiKit
import SwiftUI

// Port of `DesktopRewind.tsx`: the capture-detail page. The store owns the
// rewind timeline reader (`App/RewindTimelineStore.swift`) and exposes the
// grouped capture feed (`AppStore.rewindGroups`, collapsed by OmiKit's
// `groupRewindFrames` with the 12-minute gap bound); this renders the moment
// list with day separators, the Load-more pagination, and the preview pane
// showing the selected moment's captured frame (host bitmap bridge).

#if os(macOS)
import AppKit

/// Decodes frame JPEG/PNG data for the preview pane (macOS host path; the
/// Skip/Android build never renders the desktop Recall surface).
private func platformFrameImage(_ data: Data) -> Image? {
    guard let nsImage = NSImage(data: data) else { return nil }
    var rect = CGRect(origin: .zero, size: nsImage.size)
    guard let cgImage = nsImage.cgImage(forProposedRect: &rect, context: nil, hints: nil) else {
        return nil
    }
    return Image(decorative: cgImage, scale: 1.0)
}
#else
/// Skip/Android: hosts carry no frame bitmaps; the glyph fallback renders.
private func platformFrameImage(_ data: Data) -> Image? {
    nil
}
#endif

struct DesktopRewindPage: View {
    @EnvironmentObject var store: AppStore
    let query: String
    /// Group id to open directly, e.g. from an Activity timeline entry.
    var focusGroupId: String? = nil

    @Environment(\.desktopTokens) private var tokens
    @State private var selectedGroupId: String?

    var body: some View {
        gatedView
            .task(id: query) {
                // DesktopRewind.tsx: every query change rebuilds the reader.
                await store.refreshRewindTimeline(query: query)
            }
            .task {
                // The upstream 15 s refresh keeps Recall live while visible.
                while !Task.isCancelled {
                    try? await Task.sleep(nanoseconds: 15_000_000_000)
                    guard !Task.isCancelled else { break }
                    await store.refreshRewindTimeline(query: query)
                }
            }
    }

    @ViewBuilder
    private var gatedView: some View {
        if groups.isEmpty {
            emptyState
        } else {
            content
        }
    }

    private var groups: [RewindCaptureGroup] {
        let needle = query.trimmingCharacters(in: .whitespaces).lowercased()
        guard !needle.isEmpty else { return store.rewindGroups }
        return store.rewindGroups.filter {
            "\($0.windowTitle)\n\($0.appName)".lowercased().contains(needle)
        }
    }

    private var emptyState: some View {
        DesktopEmptyStateView(
            title: query.trimmingCharacters(in: .whitespaces).isEmpty
                ? "A place for what you saw."
                : "Nothing matches yet",
            detail: query.trimmingCharacters(in: .whitespaces).isEmpty
                ? "No captures saved yet."
                : "No captures match this search.",
            icon: DesktopIcon.monitor
        )
        .padding(16)
        .accessibilityLabel("Recall screen history")
    }

    private var content: some View {
        HStack(alignment: .top, spacing: 14) {
            momentList
                .frame(width: 320)
            previewPane
                .frame(maxWidth: .infinity, maxHeight: .infinity)
        }
        .padding(8)
        .overlay(alignment: .top) {
            if let notice = store.rewindTimelineWarning {
                Text(notice)
                    .font(.system(size: 12))
                    .foregroundStyle(tokens.inkMuted)
                    .padding(.horizontal, 12)
                    .padding(.vertical, 6)
                    .background(Capsule().fill(tokens.glassQuiet))
                    .padding(.top, 2)
            }
        }
        .accessibilityLabel("Recall screen history")
        .onAppear {
            if selectedGroupId == nil, let focusGroupId {
                selectedGroupId = focusGroupId
            } else if selectedGroupId == nil, let first = groups.first {
                selectedGroupId = first.id
            }
        }
    }

    private var momentList: some View {
        FadedScrollView {
            LazyVStack(alignment: .leading, spacing: 0) {
                let sections = rewindDaySections(groups)
                ForEach(sections, id: \.label) { section in
                    Text(section.label)
                        .font(.system(size: 12, weight: .semibold))
                        .foregroundStyle(tokens.inkMuted)
                        .padding(.top, 16)
                        .padding(.bottom, 6)
                    ForEach(section.groups, id: \.id) { group in
                        momentRow(group)
                    }
                }
                if store.rewindTimelineHasMore {
                    Button {
                        Task { await store.loadOlderRewindTimeline() }
                    } label: {
                        HStack(spacing: 8) {
                            if store.rewindTimelineBusy {
                                ProgressView()
                            }
                            Text("Load more")
                                .font(.system(size: 12, weight: .semibold))
                        }
                        .foregroundStyle(tokens.ink)
                        .padding(.horizontal, 14)
                        .padding(.vertical, 7)
                        .background(
                            Capsule().fill(tokens.glassQuiet)
                                .overlay(Capsule().strokeBorder(tokens.line, lineWidth: 1))
                        )
                    }
                    .buttonStyle(GlassPressableStyle())
                    .disabled(store.rewindTimelineBusy)
                    .accessibilityLabel("Load more history")
                    .padding(.top, 14)
                }
            }
            .padding(.horizontal, 4)
        }
    }

    private func momentRow(_ group: RewindCaptureGroup) -> some View {
        let isSelected = selectedGroupId == group.id
        let title = group.windowTitle.isEmpty
            ? (group.appName.isEmpty ? "Captured screen" : group.appName)
            : group.windowTitle
        let countLabel = group.count == 1 ? "capture" : "captures"
        let meta = group.windowTitle != group.appName && !group.windowTitle.isEmpty
            ? "\(group.appName) · \(group.count) \(countLabel)"
            : "\(group.count) \(countLabel)"
        return Button {
            selectedGroupId = group.id
        } label: {
            HStack(alignment: .top, spacing: 10) {
                Text(timelineTimeLabel(atMs: group.capturedAtMs))
                    .font(.system(size: 11))
                    .foregroundStyle(tokens.inkFaint)
                    .frame(width: 44, alignment: .leading)
                VStack(spacing: 0) {
                    Circle()
                        .fill(isSelected ? tokens.ink : tokens.inkFaint)
                        .frame(width: 8, height: 8)
                    if group.count > 1 {
                        Rectangle()
                            .fill(tokens.line)
                            .frame(width: 1.5)
                            .frame(maxHeight: .infinity)
                    }
                }
                .frame(maxHeight: .infinity)
                VStack(alignment: .leading, spacing: 2) {
                    Text(title)
                        .font(.system(size: 13, weight: .medium))
                        .foregroundStyle(tokens.ink)
                        .lineLimit(1)
                    Text(meta)
                        .font(.system(size: 11))
                        .foregroundStyle(tokens.inkMuted)
                        .lineLimit(2)
                }
                Spacer(minLength: 0)
            }
            .padding(8)
            .background(
                RoundedRectangle(cornerRadius: 10)
                    .fill(isSelected ? tokens.glassSelected : Color.clear)
            )
        }
        .buttonStyle(GlassPressableStyle())
        .accessibilityLabel("View capture \(group.id)")
        .accessibilityAddTraits(isSelected ? .isSelected : [])
    }

    @ViewBuilder
    private var previewPane: some View {
        let selected = groups.first { $0.id == selectedGroupId }
        ZStack {
            RoundedRectangle(cornerRadius: 18)
                .fill(tokens.glassQuiet)
                .overlay(
                    RoundedRectangle(cornerRadius: 18)
                        .strokeBorder(tokens.line, lineWidth: 1)
                )
            if let selected {
                VStack(spacing: 10) {
                    framePreview(selected)
                        .frame(maxWidth: .infinity, maxHeight: .infinity)
                        .clipShape(RoundedRectangle(cornerRadius: 12))
                        .overlay(
                            RoundedRectangle(cornerRadius: 12)
                                .strokeBorder(tokens.line, lineWidth: 1)
                        )
                    Text(momentTitle(selected))
                        .font(.system(size: 14, weight: .medium))
                        .foregroundStyle(tokens.ink)
                        .multilineTextAlignment(.center)
                    Text(previewMeta(selected))
                        .font(.system(size: 12))
                        .foregroundStyle(tokens.inkMuted)
                        .multilineTextAlignment(.center)
                }
                .padding(16)
            } else {
                VStack(spacing: 8) {
                    DesktopIcon.monitor
                        .frame(width: 32, height: 32)
                        .foregroundStyle(tokens.inkFaint)
                    Text("Select a capture to view it.")
                        .font(.system(size: 12))
                        .foregroundStyle(tokens.inkMuted)
                }
            }
        }
        .aspectRatio(16.0 / 10.0, contentMode: .fit)
    }

    /// The captured frame bitmap (`OmiRewind.readFrame` upstream). Hosts
    /// without bitmaps fall back to the capture glyph — the summary stays
    /// honest either way.
    @ViewBuilder
    private func framePreview(_ group: RewindCaptureGroup) -> some View {
        if let data = store.services.rewindFrameImage?(group.frame.id),
            let image = platformFrameImage(data)
        {
            image
                .resizable()
                .aspectRatio(contentMode: .fill)
        } else {
            ZStack {
                RoundedRectangle(cornerRadius: 12).fill(tokens.glassQuiet)
                DesktopIcon.monitor
                    .frame(width: 32, height: 32)
                    .foregroundStyle(tokens.inkFaint)
            }
        }
    }

    private func momentTitle(_ group: RewindCaptureGroup) -> String {
        let title = group.windowTitle.isEmpty ? group.appName : group.windowTitle
        return title.isEmpty ? "Captured screen" : title
    }

    private func previewMeta(_ group: RewindCaptureGroup) -> String {
        let countLabel = group.count == 1 ? "capture" : "captures"
        return "\(timelineDayLabelCompat(group.capturedAtMs)) · \(timelineTimeLabel(atMs: group.capturedAtMs)) · \(group.count) \(countLabel)"
    }

    /// Day label for preview meta; reuse the OmiKit bucketing labels.
    private func timelineDayLabelCompat(_ atMs: Int64) -> String {
        timelineDayLabel(atMs: atMs, nowMs: nowMilliseconds())
    }
}

struct RewindDaySection {
    var label: String
    var groups: [RewindCaptureGroup]
}

/// Day separators for the moment list (`dayLabel` in DesktopRewind.tsx).
func rewindDaySections(_ groups: [RewindCaptureGroup]) -> [RewindDaySection] {
    var sections: [RewindDaySection] = []
    for group in groups {
        let label = timelineDayLabel(atMs: group.capturedAtMs, nowMs: nowMilliseconds())
        if var last = sections.last, last.label == label {
            last.groups.append(group)
            sections[sections.count - 1] = last
        } else {
            sections.append(RewindDaySection(label: label, groups: [group]))
        }
    }
    return sections
}
