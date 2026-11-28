import Charts
import OmiComponents
import OmiDesign
import OmiService
import SwiftUI
import UniformTypeIdentifiers

/// My Devices › Help with your Omi › Connection health (Flutter `device_diagnostics.dart`): right
/// now, the last 7 days with a verdict, signal and battery over time, and the link's history. Share
/// and Send to support sit in the one "…" menu. Signal is read every 2 s while the page is open.
struct DeviceDiagnosticsScreen: View {
    @Environment(DeviceStore.self) private var devices
    @Environment(DiagnosticsReportStore.self) private var report
    @State private var confirmSend = false

    private var log: DeviceDiagnosticsLog {
        devices.diagnostics
    }

    var body: some View {
        OmiGroupedList {
            rightNow
            lastWeek
            history
            disconnects
        }
        .omiPage(L("nativeConnectionHealth"))
        .toolbar {
            ToolbarItem(placement: .topBarTrailing) {
                Menu {
                    ShareLink(
                        item: DiagnosticsJSON(data: report.bundle()),
                        preview: SharePreview(L("diagnosticsExportTitle"))
                    ) { Label(L("share"), systemImage: "square.and.arrow.up") }
                    Button { confirmSend = true } label: { Label(L("sendToSupport"), systemImage: "lifepreserver") }
                        .disabled(report.phase == .sending)
                } label: {
                    if report.phase == .sending { ProgressView() } else { Image(systemName: "ellipsis") }
                }
                .accessibilityIdentifier("diagnostics.menu")
            }
        }
        .task {
            while !Task.isCancelled {
                devices.readSignal()
                try? await Task.sleep(for: .seconds(2))
            }
        }
        .alert(L("sendToSupport"), isPresented: $confirmSend) {
            Button(L("cancel"), role: .cancel) {}
            Button(L("send")) { Task { await report.send() } }
        } message: {
            Text(L("nativeDiagnosticsSendBody"))
        }
        .alert(L("deviceDiagnosticsTicket"), isPresented: Binding(get: { ticket != nil }, set: { if !$0 { report.dismiss() } })) {
            Button(L("copy")) { UIPasteboard.general.string = ticket }
            Button(L("ok"), role: .cancel) {}
        } message: {
            Text(ticket ?? "")
        }
        .alert(
            L("deviceDiagnosticsUploadFailed"),
            isPresented: Binding(get: { report.phase == .failed }, set: { if !$0 { report.dismiss() } })
        ) {
            Button(L("ok"), role: .cancel) {}
        }
    }

    private var ticket: String? {
        if case let .sent(ticket) = report.phase { return ticket }
        return nil
    }

    // MARK: Sections

    private var rightNow: some View {
        Section {
            LabeledContent(L("diagnosticsConnectedFor")) {
                if let since = log.connectedAt, devices.connection == .connected {
                    Text(since, style: .relative).monospacedDigit()
                } else {
                    Text(L("nativeNotConnected"))
                }
            }
            LabeledContent(L("battery"), value: devices.connection == .connected ? devices.battery.map { "\($0)%" } ?? "–" : "–")
            LabeledContent(L("signal")) {
                if let rssi = log.latestSignal, devices.connection == .connected {
                    HStack(spacing: DS.Spacing.sm) {
                        Circle().fill(Self.color(SignalQuality(rssi: rssi))).frame(width: 8, height: 8)
                        Text(Self.label(SignalQuality(rssi: rssi)))
                    }
                } else {
                    Text("–")
                }
            }
        } header: {
            OmiSectionLabel(L("nativeDiagnosticsNow"))
        }
    }

    private var lastWeek: some View {
        let summary = log.summary
        return Section {
            verdict(summary)
            LabeledContent(L("diagnosticsDrops")) {
                HStack(spacing: DS.Spacing.xs) {
                    Text("\(summary.drops)").monospacedDigit()
                    if let perHour = summary.dropsPerHour {
                        Text(L("diagnosticsDropsPerHour", String(perHour))).foregroundStyle(DS.Palette.inkTertiary)
                    }
                }
            }
            LabeledContent(L("failedConnections"), value: "\(summary.failed)")
            if let gap = summary.longestGap {
                LabeledContent(L("diagnosticsLongestGap"), value: Self.compact(gap))
            }
        } header: {
            OmiSectionLabel(L("nativeDiagnosticsWeek"))
        }
    }

    private func verdict(_ summary: DiagnosticsSummary) -> some View {
        let verdict = if summary.hasTrouble {
            Verdict(
                title: L("diagnosticsVerdictTrouble"), detail: L("diagnosticsVerdictTroubleDetail", String(summary.failedLast24h)),
                symbol: "exclamationmark.triangle.fill", tint: DS.Palette.warning
            )
        } else if let median = summary.medianReconnect {
            Verdict(
                title: L("diagnosticsVerdictReconnects"), detail: L("diagnosticsVerdictReconnectsDetail", Self.compact(median)),
                symbol: "arrow.triangle.2.circlepath", tint: DS.Palette.success
            )
        } else {
            Verdict(title: L("diagnosticsVerdictNoDrops"), detail: nil, symbol: "checkmark.circle.fill", tint: DS.Palette.success)
        }
        return HStack(alignment: .top, spacing: DS.Spacing.md) {
            Image(systemName: verdict.symbol).font(.title3).foregroundStyle(verdict.tint)
            VStack(alignment: .leading, spacing: DS.Spacing.xxs) {
                Text(verdict.title).font(DS.Typography.cardTitle)
                if let detail = verdict.detail {
                    Text(detail).font(DS.Typography.callout).foregroundStyle(DS.Palette.inkSecondary)
                }
            }
        }
        .padding(.vertical, DS.Spacing.xs)
        .accessibilityElement(children: .combine)
    }

    /// Signal while the page is open, battery over the week.
    private var history: some View {
        Section {
            VStack(alignment: .leading, spacing: DS.Spacing.sm) {
                Text(L("nativeSignalStrength")).font(DS.Typography.callout.weight(.semibold))
                if log.signal.count < 2 {
                    Text(L("collectingData")).font(DS.Typography.callout).foregroundStyle(DS.Palette.inkTertiary)
                        .frame(maxWidth: .infinity, minHeight: 80)
                } else {
                    Chart(Array(log.signal.enumerated()), id: \.offset) { _, reading in
                        LineMark(x: .value("Time", reading.at), y: .value("dBm", reading.rssi))
                            .foregroundStyle(DS.Palette.agent)
                            .interpolationMethod(.monotone)
                    }
                    .chartXAxis(.hidden)
                    .chartYScale(domain: -100 ... -30)
                    .frame(height: 110)
                }
            }
            .padding(.vertical, DS.Spacing.xs)
            VStack(alignment: .leading, spacing: DS.Spacing.sm) {
                Text(L("batteryHistory")).font(DS.Typography.callout.weight(.semibold))
                if log.battery.count < 2 {
                    Text(L("noBatteryDataYet")).font(DS.Typography.callout).foregroundStyle(DS.Palette.inkTertiary)
                        .frame(maxWidth: .infinity, minHeight: 80)
                } else {
                    Chart(Array(log.battery.enumerated()), id: \.offset) { _, reading in
                        AreaMark(x: .value("Time", reading.at), y: .value("%", reading.level))
                            .foregroundStyle(DS.Palette.success.opacity(0.18))
                        LineMark(x: .value("Time", reading.at), y: .value("%", reading.level))
                            .foregroundStyle(DS.Palette.success)
                    }
                    .chartYScale(domain: 0 ... 100)
                    .frame(height: 110)
                }
            }
            .padding(.vertical, DS.Spacing.xs)
        }
    }

    private var disconnects: some View {
        Section {
            if log.recent.isEmpty {
                Text(L("noDisconnectsRecorded")).foregroundStyle(DS.Palette.inkSecondary)
            }
            ForEach(Array(log.recent.enumerated()), id: \.offset) { _, event in
                HStack(alignment: .firstTextBaseline) {
                    VStack(alignment: .leading, spacing: DS.Spacing.xxs) {
                        Text(Self.title(event)).font(DS.Typography.body)
                        Text(Self.detail(event)).font(DS.Typography.caption).foregroundStyle(DS.Palette.inkSecondary)
                    }
                    Spacer()
                    if event.kind == .failedConnect {
                        Text(L("diagnosticsFailBadge"))
                            .font(DS.Typography.micro)
                            .foregroundStyle(DS.Palette.warning)
                            .padding(.horizontal, DS.Spacing.sm)
                            .padding(.vertical, DS.Spacing.xxs)
                            .background(DS.Palette.warning.opacity(0.14), in: Capsule())
                    }
                }
                .accessibilityElement(children: .combine)
            }
        } header: {
            OmiSectionLabel(L("nativeDisconnectHistory"))
        } footer: {
            if !log.recent.isEmpty { Text(L("lastNEvents", String(log.recent.count))) }
        }
    }

    // MARK: Wording

    private static func title(_ event: DiagnosticsEvent) -> String {
        if event.kind == .failedConnect { return L("connectionFailed") }
        if event.manual { return L("manualDisconnect") }
        return event.reason ?? L("nativeConnectionDropped")
    }

    private static func detail(_ event: DiagnosticsEvent) -> String {
        let ago = L("durationAgo", compact(Date.now.timeIntervalSince(event.at)))
        guard let back = event.reconnectedAfter else { return ago }
        return ago + " · " + L("diagnosticsReconnectedIn", compact(back))
    }

    /// "45s", "3m 10s", "2h 5m", "3d" (Flutter `OmiDuration.compact`).
    static func compact(_ interval: TimeInterval) -> String {
        let seconds = max(0, Int(interval.rounded()))
        switch seconds {
        case ..<60: return L("timeCompactSecs", String(seconds))
        case ..<3600:
            let (mins, secs) = (seconds / 60, seconds % 60)
            return secs == 0 ? L("timeCompactMins", String(mins)) : L("timeCompactMinsAndSecs", String(mins), String(secs))
        case ..<86400:
            let (hours, mins) = (seconds / 3600, seconds % 3600 / 60)
            return mins == 0 ? L("timeCompactHours", String(hours)) : L("timeCompactHoursAndMins", String(hours), String(mins))
        default: return L("timeCompactDays", String(seconds / 86400))
        }
    }

    private static func label(_ quality: SignalQuality) -> String {
        switch quality {
        case .excellent: L("excellent")
        case .good: L("good")
        case .fair: L("fair")
        case .weak: L("weak")
        }
    }

    /// Excellent and good read as fine, fair as a warning, weak as trouble.
    private static func color(_ quality: SignalQuality) -> Color {
        switch quality {
        case .excellent, .good: DS.Palette.success
        case .fair: DS.Palette.warning
        case .weak: DS.Palette.live
        }
    }
}

/// The week's verdict line.
private struct Verdict {
    let title: String
    let detail: String?
    let symbol: String
    let tint: Color
}

/// The bundle as an `omi_diagnostics.json` attachment for the share sheet.
private struct DiagnosticsJSON: Transferable {
    let data: Data

    static var transferRepresentation: some TransferRepresentation {
        DataRepresentation(exportedContentType: .json) { $0.data }
            .suggestedFileName("omi_diagnostics.json")
    }
}
