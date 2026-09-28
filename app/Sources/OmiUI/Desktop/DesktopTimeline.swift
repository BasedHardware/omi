import OmiKit
import SwiftUI

// Port of `DesktopActivity.tsx` + `timeline/UnifiedTimeline.tsx` + the Home
// pieces of `DesktopHome.tsx` (glance card, read banner, explore checklist).
// The feed comes from `AppStore.mergedTimeline(filter:)` (OmiKit's
// `mergeTimeline`), extended with the local capture groups the store already
// exposes so Recall frames interleave like the TS feed.

// MARK: - Activity page

struct DesktopActivityPage: View {
    @EnvironmentObject var store: AppStore
    let filter: TimelineFilter
    let groupBy: TimelineGrouping
    /// Effective recall query — empty in Ask mode (upstream
    /// `query={mode === 'Search' ? draft : ''}`), so the ask draft never
    /// filters the Activity timeline.
    let query: String
    let exploreDone: Set<ExploreCheck>
    let onExploreItem: (ExploreCheck) -> Void
    let onOpenCapture: (CaptureGroupSummary) -> Void

    var body: some View {
        VStack(spacing: 0) {
            DesktopReadBanner()
            DesktopUnifiedTimeline(
                filter: filter,
                groupBy: groupBy,
                query: query,
                header: {
                    VStack(alignment: .leading, spacing: 0) {
                        GlanceCard()
                        if exploreDone.count < ExploreCheck.allCases.count {
                            exploreSection
                        }
                    }
                },
                onOpenEntry: { entry in
                    if entry.kind == TimelineEntryKind.capture {
                        let id = String(entry.id.dropFirst("capture-".count))
                        if let capture = store.rewindGroups.first(where: { $0.id == id }) {
                            onOpenCapture(
                                CaptureGroupSummary(
                                    id: capture.id,
                                    title: capture.windowTitle.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
                                        ? capture.appName : capture.windowTitle,
                                    appName: capture.appName,
                                    capturedAtMs: capture.capturedAtMs,
                                    count: capture.count
                                )
                            )
                        }
                    }
                }
            )
        }
        .accessibilityLabel("Activity page")
    }

    private var exploreSection: some View {
        VStack(alignment: .leading, spacing: 4) {
            SectionTitle("Getting started")
                .padding(.bottom, 4)
            ForEach(ExploreCheck.allCases, id: \.self) { check in
                let done = exploreDone.contains(check)
                Button {
                    onExploreItem(check)
                } label: {
                    HStack(spacing: 10) {
                        ZStack {
                            RoundedRectangle(cornerRadius: 7)
                                .fill(done ? tokens.glassSelected : Color.clear)
                                .overlay(
                                    RoundedRectangle(cornerRadius: 7)
                                        .strokeBorder(done ? tokens.glassSelected : tokens.inkFaint, lineWidth: 1)
                                )
                            if done {
                                DesktopIcon.check
                                    .frame(width: 13, height: 13)
                                    .foregroundStyle(tokens.inkMuted)
                            }
                        }
                        .frame(width: 18, height: 18)
                        Text(check.label)
                            .font(.system(size: 14))
                            .foregroundStyle(done ? tokens.inkMuted : tokens.ink)
                        Spacer(minLength: 0)
                    }
                    .padding(.horizontal, 6)
                    .padding(.vertical, 7)
                }
                .buttonStyle(GlassPressableStyle())
                .accessibilityLabel("Guide: \(check.label)")
            }
        }
        .padding(.top, 14)
        .accessibilityLabel("Home explore")
    }

    @Environment(\.desktopTokens) private var tokens
}

// MARK: - Read banner (DesktopHome.tsx DesktopReadBanner)

struct DesktopReadBanner: View {
    @EnvironmentObject var store: AppStore
    @Environment(\.desktopTokens) private var tokens

    var body: some View {
        if store.readsPhase == ReadsPhase.initialLoading || store.readsPhase == ReadsPhase.refreshing {
            HStack(spacing: 8) {
                ProgressView()
                    .foregroundStyle(tokens.inkMuted)
                Text("Reading your day…")
                    .font(.system(size: 12))
                    .foregroundStyle(tokens.inkMuted)
            }
            .padding(.vertical, 4)
            .accessibilityLabel("Reading your day")
        } else if store.readsPhase == ReadsPhase.unavailable || store.readsPhase == ReadsPhase.savedButRefreshFailed {
            Button {
                Task { await store.refreshReads() }
            } label: {
                HStack(spacing: 8) {
                    Text("Some of your history isn't loaded yet.")
                        .font(.system(size: 12))
                        .foregroundStyle(tokens.inkMuted)
                    Text("Try again")
                        .font(.system(size: 12, weight: .semibold))
                        .foregroundStyle(tokens.blue)
                }
            }
            .buttonStyle(GlassPressableStyle())
            .accessibilityLabel("Try again")
        }
    }
}

// MARK: - Glance card (DesktopHome.tsx GlanceCard)

struct GlanceCard: View {
    @EnvironmentObject var store: AppStore

    var body: some View {
        PageHeading(title: line.title, subtitle: line.copy)
            .accessibilityLabel("At a glance")
    }

    /// The newest fresh capture frame becomes "Now on your Mac"; otherwise
    /// the deterministic fun-fact rotation fills the glance (the remote
    /// glance worker line has no store surface yet — see report).
    private var line: (title: String, copy: String) {
        if let newest = newestCapture,
            nowMilliseconds() - newest.capturedAtMs < glanceFrameFreshMs
        {
            let window = newest.windowTitle.trimmingCharacters(in: .whitespacesAndNewlines)
            let copy = window.isEmpty ? newest.appName : "\(newest.appName) — \(window)"
            return ("Now on your Mac", copy)
        }
        let calendar = Calendar(identifier: Calendar.Identifier.gregorian)
        let components = calendar.dateComponents([.hour, .minute], from: Date())
        let minuteOfDay = (components.hour ?? 0) * 60 + (components.minute ?? 0)
        let index = (minuteOfDay / 30) % glanceFunLines.count
        return glanceFunLines[index]
    }

    private var newestCapture: RewindCaptureGroup? {
        store.rewindGroups.first
    }

    private let glanceFrameFreshMs: Int64 = 5 * 60 * 1000
}

private let glanceFunLines: [(title: String, copy: String)] = [
    ("Three hearts", "An octopus has three hearts, and two of them stop beating whenever it swims."),
    ("Eternal honey", "Honey found in ancient Egyptian tombs is still considered safe to eat."),
    ("Older than trees", "Sharks were already swimming the oceans before trees existed."),
    ("Venus days", "A single day on Venus stretches on longer than its whole year around the Sun."),
    ("Scotland's unicorn", "The unicorn is the official national animal of Scotland."),
    ("Shortest war", "The Anglo-Zanzibar War of 1896 lasted around 38 minutes."),
    ("Otter handholding", "Sea otters hold hands while they sleep so they do not drift apart."),
    ("Berry confusion", "Bananas count as berries, while strawberries famously do not."),
]

// MARK: - Unified timeline (timeline/UnifiedTimeline.tsx)

struct DesktopUnifiedTimeline<Header: View>: View {
    @EnvironmentObject var store: AppStore
    let filter: TimelineFilter
    let groupBy: TimelineGrouping
    let query: String
    @ViewBuilder let header: () -> Header
    var onOpenEntry: ((TimelineEntry) -> Void)?

    @Environment(\.desktopTokens) private var tokens
    @State private var collapsed: Set<String> = []

    var body: some View {
        let timeline = mergedFeed
        FadedScrollView {
            VStack(alignment: .leading, spacing: 0) {
                header()
                if store.readsLoading && timeline.entries.isEmpty {
                    VStack(spacing: 10) {
                        OmiLoadingMark(size: 56, ink: tokens.ink)
                        Text("Gathering your timeline…")
                            .font(.system(size: 14))
                            .foregroundStyle(tokens.inkMuted)
                    }
                    .frame(maxWidth: .infinity)
                    .padding(.top, 24)
                } else if timeline.entries.isEmpty && timeline.failures.isEmpty {
                    Text(
                        !query.trimmingCharacters(in: .whitespaces).isEmpty
                            ? "Nothing in your timeline matches yet."
                            : "Your timeline fills in as Omi captures your day."
                    )
                    .font(.system(size: 14))
                    .foregroundStyle(tokens.inkMuted)
                    .multilineTextAlignment(.center)
                    .frame(maxWidth: .infinity)
                    .padding(.vertical, 32)
                }
                ForEach(timeline.failures, id: \.self) { failure in
                    Text(failure)
                        .font(.system(size: 12))
                        .foregroundStyle(tokens.red)
                        .frame(maxWidth: .infinity)
                        .padding(.bottom, 8)
                }
                ForEach(sections(timeline.entries), id: \.key) { section in
                    timelineSection(section)
                }
            }
            .padding(.horizontal, 8)
            .padding(.bottom, 24)
            .frame(maxWidth: DesktopLayout.contentMaxWidth)
            .frame(maxWidth: .infinity)
        }
        .accessibilityLabel("Unified timeline")
    }

    /// Conversations / memories / tasks from the store's merged timeline plus
    /// the local capture groups (600 s same-window dedupe lives in OmiKit).
    private var mergedFeed: MergedTimeline {
        var captures: [CaptureGroupSummary] = []
        for group in store.rewindGroups {
            let title = group.windowTitle.trimmingCharacters(in: .whitespacesAndNewlines)
            captures.append(
                CaptureGroupSummary(
                    id: group.id, title: title.isEmpty ? group.appName : title,
                    appName: group.appName, capturedAtMs: group.capturedAtMs,
                    count: group.count
                )
            )
        }
        return mergeTimeline(
            store.outcomes, query: query,
            captures: captures, filter: filter
        )
    }

    private func sections(_ entries: [TimelineEntry]) -> [TimelineSection] {
        groupTimelineSections(entries, groupBy, nowMs: nowMilliseconds())
    }

    @ViewBuilder
    private func timelineSection(_ section: TimelineSection) -> some View {
        let isCollapsed = collapsed.contains(section.key)
        VStack(spacing: 0) {
            Button {
                if isCollapsed {
                    collapsed.remove(section.key)
                } else {
                    collapsed.insert(section.key)
                }
            } label: {
                HStack(spacing: 8) {
                    ChevronShape()
                        .stroke(style: StrokeStyle(lineWidth: 1.8, lineCap: .round, lineJoin: .round))
                        .frame(width: 16, height: 16)
                        .rotationEffect(.degrees(isCollapsed ? -90 : 0))
                        .foregroundStyle(tokens.inkMuted)
                    Text(section.label.uppercased())
                        .font(.system(size: 12, weight: .semibold))
                        .foregroundStyle(tokens.ink)
                    Spacer(minLength: 0)
                    Text("\(section.entries.count)")
                        .font(.system(size: 11))
                        .foregroundStyle(tokens.inkMuted)
                }
                .padding(.horizontal, 12)
                .padding(.vertical, 8)
                .background(
                    RoundedRectangle(cornerRadius: 10)
                        .fill(tokens.glassQuiet)
                        .overlay(
                            RoundedRectangle(cornerRadius: 10)
                                .strokeBorder(tokens.line, lineWidth: 1)
                        )
                )
            }
            .buttonStyle(GlassPressableStyle())
            .padding(.top, 18)
            .accessibilityLabel(
                "\(isCollapsed ? "Expand" : "Collapse") \(section.label) section"
            )

            if !isCollapsed {
                ForEach(section.entries, id: \.id) { entry in
                    entryRow(entry)
                }
            }
        }
    }

    @ViewBuilder
    private func entryRow(_ entry: TimelineEntry) -> some View {
        let body = entryBody(entry)
        if onOpenEntry != nil {
            Button {
                onOpenEntry?(entry)
            } label: {
                body
                    .padding(.horizontal, 6)
            }
            .buttonStyle(GlassPressableStyle())
            .accessibilityLabel("\(kindLabel(entry.kind)) \(entry.title)")
        } else {
            body
        }
    }

    /// Memories render single-voice (the sentence is the row); every other
    /// kind gets the boxed icon row.
    @ViewBuilder
    private func entryBody(_ entry: TimelineEntry) -> some View {
        if entry.kind == .memory {
            HStack(alignment: .top, spacing: 8) {
                DesktopIcon.sparkles
                    .frame(width: 13, height: 13)
                    .foregroundStyle(tokens.inkMuted)
                    .padding(.top, 3)
                VStack(alignment: .leading, spacing: 4) {
                    Text(entry.title.isEmpty ? "Memory" : entry.title)
                        .font(.system(size: 14))
                        .foregroundStyle(tokens.ink)
                        .lineLimit(3)
                    Text(metaLine(entry))
                        .font(.system(size: 11))
                        .foregroundStyle(tokens.inkFaint)
                }
            }
            .padding(.vertical, 10)
        } else {
            HStack(alignment: .top, spacing: 12) {
                RowGlyph(kind: entry.kind)
                VStack(alignment: .leading, spacing: 2) {
                    Text(entry.title)
                        .font(.system(size: 14, weight: .semibold))
                        .foregroundStyle(tokens.ink)
                        .lineLimit(1)
                    if !entry.detail.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
                        Text(entry.detail)
                            .font(.system(size: 13))
                            .foregroundStyle(tokens.inkMuted)
                            .lineLimit(2)
                            .padding(.top, 2)
                    }
                    Text(metaLine(entry))
                        .font(.system(size: 11))
                        .foregroundStyle(tokens.inkFaint)
                        .padding(.top, 4)
                }
            }
            .padding(.vertical, 10)
        }
    }

    private func metaLine(_ entry: TimelineEntry) -> String {
        let time = entry.atMs == 0 ? "" : timelineTimeLabel(atMs: entry.atMs)
        let label = kindLabel(entry.kind)
        return time.isEmpty ? label : "\(label) · \(time)"
    }

    private func kindLabel(_ kind: TimelineEntryKind) -> String {
        switch kind {
        case .conversation: return "Conversation"
        case .memory: return "Memory"
        case .task: return "Task"
        case .capture: return "Recall"
        }
    }
}

func nowMilliseconds() -> Int64 {
    Int64(Date().timeIntervalSince1970 * 1000)
}

// MARK: - Loading mark (OmiLoadingMark port: the animated Omi dot)

/// The Omi mark: a single ink dot breathing while work is in flight.
/// Reduce Motion holds it still.
struct OmiLoadingMark: View {
    var size: CGFloat
    var ink: Color

    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @State private var pulsing = false

    var body: some View {
        Circle()
            .fill(ink)
            .frame(width: size * 0.22, height: size * 0.22)
            .scaleEffect(pulsing ? 1.25 : 0.9)
            .opacity(pulsing ? 1 : 0.55)
            .onAppear {
                guard !reduceMotion else { return }
                withAnimation(
                    .easeInOut(
                        duration: DesktopMotion.motionDuration(900, reduceMotion: reduceMotion)
                    )
                    .repeatForever(autoreverses: true)
                ) {
                    pulsing = true
                }
            }
            .frame(width: size, height: size)
            .accessibilityLabel("Loading")
    }
}
