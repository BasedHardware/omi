import Foundation
import OmiCore
#if canImport(HealthKit) && os(iOS)
    import HealthKit
#endif

/// `HealthDataReading` on HealthKit: the types and queries of Flutter's `ios/Runner/AppleHealthService.swift`
/// (steps, active energy, walking + running distance, heart rate, resting heart rate, sleep, workouts).
public final class HealthKitReader: HealthDataReading, @unchecked Sendable {
    public init() {}

    #if canImport(HealthKit) && os(iOS)
        private let store = HKHealthStore()

        public var isAvailable: Bool {
            HKHealthStore.isHealthDataAvailable()
        }

        private var readTypes: Set<HKObjectType> {
            [
                HKQuantityType(.stepCount), HKQuantityType(.activeEnergyBurned), HKQuantityType(.distanceWalkingRunning),
                HKQuantityType(.heartRate), HKQuantityType(.restingHeartRate), HKCategoryType(.sleepAnalysis), HKWorkoutType.workoutType(),
            ]
        }

        public func requestAuthorization() async -> Bool {
            guard isAvailable else { return false }
            do {
                try await store.requestAuthorization(toShare: [], read: readTypes)
                return true
            } catch {
                return false
            }
        }

        public func probeAccess() async -> Bool {
            guard isAvailable, let start = Calendar.current.date(byAdding: .day, value: -90, to: .now) else { return false }
            let range = HKQuery.predicateForSamples(withStart: start, end: .now, options: .strictStartDate)
            let types: [HKSampleType] = [
                HKQuantityType(.stepCount), HKQuantityType(.heartRate), HKQuantityType(.activeEnergyBurned),
                HKQuantityType(.distanceWalkingRunning), HKCategoryType(.sleepAnalysis), HKWorkoutType.workoutType(),
            ]
            for probe in types.map({ HKSamplePredicate<HKSample>.sample(type: $0, predicate: range) }) {
                let samples = try? await HKSampleQueryDescriptor(predicates: [probe], sortDescriptors: [], limit: 1).result(for: store)
                if samples?.isEmpty == false { return true }
            }
            return false
        }

        public func summary(days: Int) async -> HealthSummary? {
            let end = Date.now
            guard isAvailable, (1 ... 365).contains(days), let start = Calendar.current.date(byAdding: .day, value: -days, to: end) else {
                return nil
            }
            let range = HKQuery.predicateForSamples(withStart: start, end: end, options: .strictStartDate)
            var summary = HealthSummary(periodDays: days)
            summary.dailySteps = await daily(.stepCount, unit: .count(), range: range, from: start, to: end).map {
                .init(date: $0.date, dateMs: $0.dateMs, steps: Int($0.value))
            }
            summary.dailyEnergy = await daily(.activeEnergyBurned, unit: .kilocalorie(), range: range, from: start, to: end).map {
                .init(date: $0.date, dateMs: $0.dateMs, calories: $0.value)
            }
            summary.heartRate = await heartRate(range)
            await addSleep(range, to: &summary)
            summary.workouts = await workouts(range)
            return summary
        }

        // MARK: Queries

        private func daily(
            _ identifier: HKQuantityTypeIdentifier, unit: HKUnit, range: NSPredicate, from start: Date, to end: Date
        ) async -> [DayTotal] {
            let query = HKStatisticsCollectionQueryDescriptor(
                predicate: .quantitySample(type: HKQuantityType(identifier), predicate: range), options: .cumulativeSum,
                anchorDate: Calendar.current.startOfDay(for: start), intervalComponents: DateComponents(day: 1)
            )
            guard let collection = try? await query.result(for: store) else { return [] }
            var days: [DayTotal] = []
            collection.enumerateStatistics(from: start, to: end) { statistics, _ in
                let value = statistics.sumQuantity()?.doubleValue(for: unit) ?? 0
                let day = statistics.startDate
                days.append(DayTotal(date: Self.day(day), dateMs: day.timeIntervalSince1970 * 1000, value: value))
            }
            return days
        }

        /// One day's sum of a quantity.
        private struct DayTotal {
            let date: String
            let dateMs: Double
            let value: Double
        }

        private func heartRate(_ range: NSPredicate) async -> HealthSummary.HeartRate? {
            let query = HKStatisticsQueryDescriptor(
                predicate: .quantitySample(type: HKQuantityType(.heartRate), predicate: range),
                options: [.discreteAverage, .discreteMin, .discreteMax]
            )
            guard let statistics = try? await query.result(for: store) else { return nil }
            let unit = HKUnit.count().unitDivided(by: .minute())
            let rate = HealthSummary.HeartRate(
                average: statistics.averageQuantity()?.doubleValue(for: unit),
                minimum: statistics.minimumQuantity()?.doubleValue(for: unit),
                maximum: statistics.maximumQuantity()?.doubleValue(for: unit)
            )
            return rate.average == nil && rate.minimum == nil && rate.maximum == nil ? nil : rate
        }

        /// Every sample becomes a session with its stage; asleep stages count toward the total and
        /// the day the sleep ended (Flutter `fetchDailySleep`).
        private func addSleep(_ range: NSPredicate, to summary: inout HealthSummary) async {
            let query = HKSampleQueryDescriptor(
                predicates: [.categorySample(type: HKCategoryType(.sleepAnalysis), predicate: range)],
                sortDescriptors: [SortDescriptor(\.endDate, order: .reverse)]
            )
            guard let samples = try? await query.result(for: store) else { return }
            let asleep: Set<Int> = [
                HKCategoryValueSleepAnalysis.asleepCore.rawValue, HKCategoryValueSleepAnalysis.asleepDeep.rawValue,
                HKCategoryValueSleepAnalysis.asleepREM.rawValue, HKCategoryValueSleepAnalysis.asleepUnspecified.rawValue,
            ]
            var byDay: [String: Double] = [:]
            var asleepSeconds = 0.0, inBedSeconds = 0.0
            for sample in samples {
                let seconds = sample.endDate.timeIntervalSince(sample.startDate)
                if asleep.contains(sample.value) {
                    asleepSeconds += seconds
                    byDay[Self.day(sample.endDate), default: 0] += seconds
                } else if sample.value == HKCategoryValueSleepAnalysis.inBed.rawValue {
                    inBedSeconds += seconds
                }
                summary.sleepSessions.append(.init(
                    startDate: sample.startDate.timeIntervalSince1970 * 1000, endDate: sample.endDate.timeIntervalSince1970 * 1000,
                    durationMinutes: seconds / 60, type: Self.sleepStage(sample.value)
                ))
            }
            summary.totalSleepHours = asleepSeconds / 3600
            summary.totalInBedHours = inBedSeconds / 3600
            summary.dailySleep = byDay.map { .init(date: $0.key, sleepHours: $0.value / 3600) }.sorted { $0.date > $1.date }
        }

        private func workouts(_ range: NSPredicate) async -> [HealthSummary.Workout] {
            let newestFirst = [SortDescriptor(\HKWorkout.endDate, order: .reverse)]
            let query = HKSampleQueryDescriptor(predicates: [.workout(range)], sortDescriptors: newestFirst)
            guard let workouts = try? await query.result(for: store) else { return [] }
            let distances: [HKQuantityTypeIdentifier] = [.distanceWalkingRunning, .distanceCycling, .distanceSwimming]
            return workouts.map { workout in
                let energy = workout.statistics(for: HKQuantityType(.activeEnergyBurned))?.sumQuantity()
                let distance = distances.lazy.compactMap { workout.statistics(for: HKQuantityType($0))?.sumQuantity() }.first
                return HealthSummary.Workout(
                    type: Self.workoutName(workout.workoutActivityType),
                    startDate: workout.startDate.timeIntervalSince1970 * 1000, endDate: workout.endDate.timeIntervalSince1970 * 1000,
                    durationMinutes: workout.duration / 60,
                    caloriesBurned: energy?.doubleValue(for: .kilocalorie()),
                    distanceKm: distance?.doubleValue(for: .meterUnit(with: .kilo))
                )
            }
        }

        // MARK: Names (Flutter's strings, kept for the backend and the chat)

        private static func day(_ date: Date) -> String {
            let formatter = DateFormatter()
            formatter.locale = Locale(identifier: "en_US_POSIX")
            formatter.dateFormat = "yyyy-MM-dd"
            return formatter.string(from: date)
        }

        private static func sleepStage(_ value: Int) -> String {
            switch HKCategoryValueSleepAnalysis(rawValue: value) {
            case .asleepCore: "core"
            case .asleepDeep: "deep"
            case .asleepREM: "rem"
            case .asleepUnspecified: "asleep"
            case .inBed: "inBed"
            case .awake: "awake"
            default: "unknown"
            }
        }

        private static func workoutName(_ type: HKWorkoutActivityType) -> String {
            switch type {
            case .running: "Running"
            case .walking: "Walking"
            case .cycling: "Cycling"
            case .swimming: "Swimming"
            case .hiking: "Hiking"
            case .yoga: "Yoga"
            case .functionalStrengthTraining, .traditionalStrengthTraining: "Strength Training"
            case .crossTraining: "Cross Training"
            case .elliptical: "Elliptical"
            case .rowing: "Rowing"
            case .stairClimbing: "Stair Climbing"
            case .highIntensityIntervalTraining: "HIIT"
            case .dance: "Dance"
            case .pilates: "Pilates"
            case .tennis: "Tennis"
            case .basketball: "Basketball"
            case .soccer: "Soccer"
            case .golf: "Golf"
            default: "Other"
            }
        }
    #else
        public var isAvailable: Bool {
            false
        }

        public func requestAuthorization() async -> Bool {
            false
        }

        public func probeAccess() async -> Bool {
            false
        }

        public func summary(days _: Int) async -> HealthSummary? {
            nil
        }
    #endif
}
