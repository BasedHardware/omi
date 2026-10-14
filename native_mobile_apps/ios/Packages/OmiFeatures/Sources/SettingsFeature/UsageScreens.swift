import Charts
import OmiComponents
import OmiDesign
import OmiNetwork
import OmiService
import SwiftUI

/// What Omi heard in a period: minutes, words, insights, memories, and words per day.
struct ActivitySection: View {
    @Bindable var store: UsageStore

    var body: some View {
        Section {
            Picker(L("nativeUsagePeriod"), selection: $store.period) {
                Text(L("today")).tag(UsageStats.Period.today)
                Text(L("usageMonth")).tag(UsageStats.Period.monthly)
                Text(L("usageYear")).tag(UsageStats.Period.yearly)
                Text(L("usageAll")).tag(UsageStats.Period.allTime)
            }
            .pickerStyle(.segmented)
            .labelsHidden()
            if let stats = store.current {
                if stats.totals.isEmpty {
                    Text(L("nativeUsageEmpty")).font(DS.Typography.callout).foregroundStyle(DS.Palette.inkSecondary)
                } else {
                    totals(stats.totals)
                    if stats.history.count > 3 { chart(stats) }
                }
            } else if store.failedPeriods.contains(store.period) {
                retry(L("nativeCouldNotLoad")) { await store.load() }
            } else {
                ProgressView().frame(maxWidth: .infinity)
            }
        } header: {
            SettingsHeader(L("nativeSettingsActivity"))
        }
        .task(id: store.period) { await store.load() }
    }

    private func totals(_ totals: UsageStats.Totals) -> some View {
        Grid(alignment: .leading, horizontalSpacing: DS.Spacing.lg, verticalSpacing: DS.Spacing.md) {
            GridRow {
                number(L("nativeMinutesValue", String(totals.transcriptionSeconds / 60)), L("nativeUsageListened"))
                number(totals.words.formatted(), L("nativeUsageWords"))
            }
            GridRow {
                number(totals.insights.formatted(), L("nativeUsageInsights"))
                number(totals.memories.formatted(), L("memories"))
            }
        }
        .padding(.vertical, DS.Spacing.xs)
    }

    private func number(_ value: String, _ label: String) -> some View {
        VStack(alignment: .leading, spacing: DS.Spacing.xxs) {
            Text(value).font(DS.Typography.sectionTitle).monospacedDigit()
            Text(label).font(DS.Typography.caption).foregroundStyle(DS.Palette.inkSecondary)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .accessibilityElement(children: .combine)
    }

    private func chart(_ stats: UsageStats) -> some View {
        Chart(stats.history, id: \.date) { bucket in
            BarMark(x: .value("Date", String(bucket.date.prefix(10))), y: .value("Words", bucket.totals.words))
                .foregroundStyle(DS.Palette.ink)
                .cornerRadius(3)
        }
        .chartXAxis(.hidden)
        .chartYAxis(.hidden)
        .frame(height: 110)
        .padding(.vertical, DS.Spacing.xs)
        .accessibilityLabel(L("nativeUsageWords"))
    }

    static func shareText(_ totals: UsageStats.Totals, period: UsageStats.Period) -> String {
        let title = switch period {
        case .today: L("today")
        case .monthly: L("usageMonth")
        case .yearly: L("usageYear")
        case .allTime: L("usageAll")
        }
        var lines = [L("nativeUsageShareTitle", title)]
        if totals.transcriptionSeconds >= 60 { lines.append("🎧 " + L("nativeUsageShareMinutes", String(totals.transcriptionSeconds / 60))) }
        if totals.words > 0 { lines.append("💬 " + L("nativeUsageShareWords", totals.words.formatted())) }
        if totals.insights > 0 { lines.append("💡 " + L("nativeUsageShareInsights", totals.insights.formatted())) }
        if totals.memories > 0 { lines.append("🧠 " + L("nativeUsageShareMemories", totals.memories.formatted())) }
        return (lines + ["omi.me"]).joined(separator: "\n")
    }
}

/// Speech hours against today's, three days' and the week's fair-use limits, and the server's note.
struct FairUseSection: View {
    let store: UsageStore

    var body: some View {
        Section {
            if let status = store.fairUse {
                if status.stage != "none" {
                    Label(stageTitle(status.stage), systemImage: "exclamationmark.triangle.fill")
                        .foregroundStyle(DS.Palette.warning)
                    if let reference = status.caseReference {
                        Button {
                            UIPasteboard.general.string = reference
                            DSHaptics.success()
                        } label: {
                            LabeledContent(L("nativeCaseReference"), value: reference)
                        }
                        .tint(DS.Palette.ink)
                    }
                }
                meter(L("fairUseToday"), status.today)
                meter(L("nativeFairUseThreeDays"), status.threeDays)
                meter(L("nativeFairUseWeek"), status.week)
                if !status.message.isEmpty {
                    Text(status.message).font(DS.Typography.callout)
                }
            } else if store.fairUseFailed {
                retry(L("nativeFairUseLoadError")) { await store.loadFairUse() }
            } else {
                ProgressView().frame(maxWidth: .infinity)
            }
        } header: {
            SettingsHeader(L("nativeFairUseTitle"))
        } footer: {
            Text(L("fairUseAboutBody"))
        }
    }

    private func stageTitle(_ stage: String) -> String {
        switch stage {
        case "throttle": L("fairUseStageThrottle")
        case "restrict": L("fairUseStageRestrict")
        default: L("fairUseStageWarning")
        }
    }

    private func meter(_ title: String, _ window: FairUseStatus.Window) -> some View {
        VStack(alignment: .leading, spacing: DS.Spacing.xs) {
            LabeledContent(title, value: L("nativeHoursOfHours", Self.hours(window.usedHours), Self.hours(window.limitHours)))
            OmiMeterBar(
                fraction: min(window.percent, 100) / 100,
                tint: window.percent >= 100 ? DS.Palette.live : window.percent >= 80 ? DS.Palette.warning : DS.Palette.ink
            )
        }
        .padding(.vertical, DS.Spacing.xxs)
    }

    static func hours(_ value: Double) -> String {
        value.formatted(.number.precision(.fractionLength(0 ... 1)))
    }
}

/// A row saying what failed, with Try again (never an endless spinner).
@MainActor
func retry(_ message: String, action: @escaping @MainActor () async -> Void) -> some View {
    HStack {
        Label(message, systemImage: "wifi.exclamationmark").foregroundStyle(DS.Palette.inkSecondary)
        Spacer()
        Button(L("tryAgain")) { Task { await action() } }
            .buttonStyle(.bordered)
            .buttonBorderShape(.capsule)
            .tint(DS.Palette.ink)
    }
}
