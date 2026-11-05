import Foundation

/// What Apple Health reports for the last days, in the shape Flutter's `AppleHealthService.swift`
/// (`getHealthSummary`) builds and `PUT v1/integrations/apple-health/sync` stores for the chat.
/// Nested keys stay camelCase (`dateMs`, `sleepHours` …) as Flutter sends them.
public struct HealthSummary: Hashable, Sendable {
    public struct DailySteps: Codable, Hashable, Sendable {
        public let date: String
        public let dateMs: Double
        public let steps: Int

        public init(date: String, dateMs: Double, steps: Int) {
            self.date = date
            self.dateMs = dateMs
            self.steps = steps
        }
    }

    public struct DailyEnergy: Codable, Hashable, Sendable {
        public let date: String
        public let dateMs: Double
        public let calories: Double

        public init(date: String, dateMs: Double, calories: Double) {
            self.date = date
            self.dateMs = dateMs
            self.calories = calories
        }
    }

    public struct DailySleep: Codable, Hashable, Sendable {
        public let date: String
        public let sleepHours: Double

        public init(date: String, sleepHours: Double) {
            self.date = date
            self.sleepHours = sleepHours
        }
    }

    public struct SleepSession: Codable, Hashable, Sendable {
        public let startDate: Double
        public let endDate: Double
        public let durationMinutes: Double
        /// core, deep, rem, asleep, inBed, awake, unknown.
        public let type: String

        public init(startDate: Double, endDate: Double, durationMinutes: Double, type: String) {
            self.startDate = startDate
            self.endDate = endDate
            self.durationMinutes = durationMinutes
            self.type = type
        }
    }

    public struct Workout: Codable, Hashable, Sendable {
        public let type: String
        public let startDate: Double
        public let endDate: Double
        public let durationMinutes: Double
        public let caloriesBurned: Double?
        public let distanceKm: Double?

        public init(
            type: String, startDate: Double, endDate: Double, durationMinutes: Double, caloriesBurned: Double?, distanceKm: Double?
        ) {
            self.type = type
            self.startDate = startDate
            self.endDate = endDate
            self.durationMinutes = durationMinutes
            self.caloriesBurned = caloriesBurned
            self.distanceKm = distanceKm
        }
    }

    public struct HeartRate: Hashable, Sendable {
        public let average: Double?
        public let minimum: Double?
        public let maximum: Double?

        public init(average: Double?, minimum: Double?, maximum: Double?) {
            self.average = average
            self.minimum = minimum
            self.maximum = maximum
        }
    }

    public var periodDays: Int
    public var dailySteps: [DailySteps] = []
    public var dailyEnergy: [DailyEnergy] = []
    public var dailySleep: [DailySleep] = []
    public var sleepSessions: [SleepSession] = []
    public var totalSleepHours: Double = 0
    public var totalInBedHours: Double = 0
    public var heartRate: HeartRate?
    public var workouts: [Workout] = []

    public init(periodDays: Int) {
        self.periodDays = periodDays
    }

    public var totalSteps: Int {
        dailySteps.reduce(0) { $0 + $1.steps }
    }

    public var totalActiveEnergy: Double {
        dailyEnergy.reduce(0) { $0 + $1.calories }
    }

    /// Something to send: HealthKit hides denied read access, so an all-empty summary means no access.
    public var hasData: Bool {
        totalSteps > 0 || totalActiveEnergy > 0 || !sleepSessions.isEmpty || heartRate?.average != nil || !workouts.isEmpty
    }

    /// The request body Flutter's `syncHealthDataToBackend` builds (backend `AppleHealthSyncData`).
    /// Averages divide by the period as Flutter does (steps with integer division).
    public var syncBody: [String: Any] {
        let days = max(periodDays, 1)
        var body: [String: Any] = [
            "period_days": periodDays,
            "total_steps": totalSteps,
            "average_steps_per_day": totalSteps / days,
            "daily_steps": dailySteps.map { ["date": $0.date, "dateMs": $0.dateMs, "steps": $0.steps] },
            "total_sleep_hours": totalSleepHours,
            "total_in_bed_hours": totalInBedHours,
            "sleep_sessions_count": sleepSessions.count,
            "sleep_sessions": sleepSessions.map {
                ["startDate": $0.startDate, "endDate": $0.endDate, "durationMinutes": $0.durationMinutes, "type": $0.type]
            },
            "daily_sleep": dailySleep.map { ["date": $0.date, "sleepHours": $0.sleepHours] },
            "total_active_energy": totalActiveEnergy,
            "average_active_energy_per_day": totalActiveEnergy / Double(days),
            "daily_active_energy": dailyEnergy.map { ["date": $0.date, "dateMs": $0.dateMs, "calories": $0.calories] },
            "workouts": workouts.map(\.jsonObject),
        ]
        if let heartRate, let average = heartRate.average {
            body["heart_rate_average"] = average
            body["heart_rate_min"] = heartRate.minimum
            body["heart_rate_max"] = heartRate.maximum
        }
        return body
    }
}

extension HealthSummary.Workout {
    var jsonObject: [String: Any] {
        var object: [String: Any] = ["type": type, "startDate": startDate, "endDate": endDate, "durationMinutes": durationMinutes]
        if let caloriesBurned { object["caloriesBurned"] = caloriesBurned }
        if let distanceKm { object["distanceKm"] = distanceKm }
        return object
    }
}
