import Foundation
import WidgetKit
import RelevanceKit
import os.log

/// Persists context needed to make the Smart Stack surface the Omi widget at the right time.
/// Data is shared between the watch app and the widget extension via UserDefaults/App Groups.
actor SmartStackRelevanceStore {
    struct Snapshot: Codable, Sendable, Equatable {
        var isRecording: Bool = false
        var recordingStartDate: Date?
        var lastRecordingEndDate: Date?
        var lastRecordingDuration: TimeInterval = 0
        var batteryLevel: Int = 100
        var batteryUpdatedAt: Date?
        var lastUpdated: Date = Date()
    }

    nonisolated static let shared = SmartStackRelevanceStore()
    nonisolated static let widgetKind = "OmiWidget"
    private static let storageKey = "com.omi.watch.relevance.snapshot"

    private let defaults: UserDefaults
    private let encoder = JSONEncoder()
    private let decoder = JSONDecoder()
    private let logger = Logger(subsystem: "com.omi.watchapp", category: "SmartStackRelevance")

    init(userDefaults: UserDefaults? = nil) {
        if let userDefaults {
            self.defaults = userDefaults
        } else if let groupIdentifier = Bundle.main.object(forInfoDictionaryKey: "OmiAppGroupIdentifier") as? String,
                  let groupDefaults = UserDefaults(suiteName: groupIdentifier) {
            self.defaults = groupDefaults
        } else {
            self.defaults = .standard
        }
    }

    func snapshot() -> Snapshot {
        loadSnapshot()
    }

    /// Called whenever recording starts so the widget can mark itself as urgent.
    func recordingDidStart(at startDate: Date = Date()) async {
        var snapshot = loadSnapshot()
        snapshot.isRecording = true
        snapshot.recordingStartDate = startDate
        snapshot.lastUpdated = Date()
        persist(snapshot)
        await notifyWidgetCenter()
    }

    /// Called when recording stops so the widget de-prioritises itself but remains relevant for follow-up.
    func recordingDidStop(at endDate: Date = Date(), duration: TimeInterval) async {
        var snapshot = loadSnapshot()
        snapshot.isRecording = false
        snapshot.lastRecordingEndDate = endDate
        snapshot.lastRecordingDuration = max(duration, 0)
        snapshot.recordingStartDate = nil
        snapshot.lastUpdated = endDate
        persist(snapshot)
        await notifyWidgetCenter()
    }

    /// Called on notable battery changes so the widget can surface low-battery warnings.
    func updateBattery(level: Int, at timestamp: Date = Date()) async {
        var snapshot = loadSnapshot()
        snapshot.batteryLevel = max(0, min(100, level))
        snapshot.batteryUpdatedAt = timestamp
        snapshot.lastUpdated = timestamp
        persist(snapshot)
        await notifyWidgetCenter()
    }

    /// Builds WidgetKit relevance attributes that describe why the widget should be surfaced.
    func widgetRelevance(currentDate: Date = Date()) -> WidgetRelevance<Void> {
        let snapshot = loadSnapshot()
        return WidgetRelevance(snapshot.widgetRelevanceAttributes(currentDate: currentDate))
    }

    /// Provides TimelineEntry relevance so the timeline entry itself can participate in ranking.
    func timelineRelevance(currentDate: Date = Date()) -> TimelineEntryRelevance {
        let snapshot = loadSnapshot()
        return snapshot.timelineRelevance(currentDate: currentDate)
    }

    // MARK: - Private helpers

    private func loadSnapshot() -> Snapshot {
        guard let data = defaults.data(forKey: Self.storageKey) else {
            return Snapshot()
        }

        do {
            return try decoder.decode(Snapshot.self, from: data)
        } catch {
            logger.error("Failed to decode relevance snapshot: \(error.localizedDescription, privacy: .public)")
            return Snapshot()
        }
    }

    private func persist(_ snapshot: Snapshot) {
        do {
            let data = try encoder.encode(snapshot)
            defaults.set(data, forKey: Self.storageKey)
        } catch {
            logger.error("Failed to persist relevance snapshot: \(error.localizedDescription, privacy: .public)")
        }
    }

    private func notifyWidgetCenter() async {
        await MainActor.run {
            WidgetCenter.shared.invalidateRelevance(ofKind: Self.widgetKind)
            WidgetCenter.shared.reloadTimelines(ofKind: Self.widgetKind)
        }
    }
}

// MARK: - Snapshot helpers

extension SmartStackRelevanceStore.Snapshot {
    func recordingDuration(at referenceDate: Date = Date()) -> TimeInterval {
        if isRecording, let startDate = recordingStartDate {
            return max(0, referenceDate.timeIntervalSince(startDate))
        }
        return max(0, lastRecordingDuration)
    }

    func widgetRelevanceAttributes(currentDate: Date = Date()) -> [WidgetRelevanceAttribute<Void>] {
        var attributes: [WidgetRelevanceAttribute<Void>] = []

        if isRecording, let start = recordingStartDate {
            let end = start.addingTimeInterval(15 * 60)
            let context = RelevantContext.date(interval: DateInterval(start: start, end: end), kind: .default)
            attributes.append(WidgetRelevanceAttribute<Void>(context: context))
        }

        if batteryLevel <= 20 {
            let end = currentDate.addingTimeInterval(10 * 60)
            let context = RelevantContext.date(interval: DateInterval(start: currentDate, end: end), kind: .informational)
            attributes.append(WidgetRelevanceAttribute<Void>(context: context))
        }

        if let lastEnd = lastRecordingEndDate,
           !isRecording,
           currentDate.timeIntervalSince(lastEnd) <= 60 * 60 {
            let end = lastEnd.addingTimeInterval(30 * 60)
            let context = RelevantContext.date(interval: DateInterval(start: lastEnd, end: end), kind: .informational)
            attributes.append(WidgetRelevanceAttribute<Void>(context: context))
        }

        if attributes.isEmpty {
            let fallBackEnd = currentDate.addingTimeInterval(30 * 60)
            let fallback = RelevantContext.date(interval: DateInterval(start: currentDate, end: fallBackEnd), kind: .informational)
            attributes.append(WidgetRelevanceAttribute<Void>(context: fallback))
        }

        return attributes
    }

    func timelineRelevance(currentDate: Date = Date()) -> TimelineEntryRelevance {
        if isRecording {
            if let start = recordingStartDate {
                let elapsed = currentDate.timeIntervalSince(start)
                return TimelineEntryRelevance(score: 1.0, duration: max(60, min(900, elapsed)))
            }
            return TimelineEntryRelevance(score: 1.0, duration: 300)
        }

        if batteryLevel <= 20 {
            return TimelineEntryRelevance(score: 0.8, duration: 600)
        }

        if let lastEnd = lastRecordingEndDate,
           currentDate.timeIntervalSince(lastEnd) <= 60 * 60 {
            return TimelineEntryRelevance(score: 0.6, duration: 600)
        }

        return TimelineEntryRelevance(score: 0.2, duration: 900)
    }
}
