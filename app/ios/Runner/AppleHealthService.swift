import Foundation
import HealthKit
import Flutter

class AppleHealthService {
    private let healthStore = HKHealthStore()

    // Health data types we want to read
    private var readTypes: Set<HKObjectType> {
        var types = Set<HKObjectType>()

        // Activity
        if let stepCount = HKQuantityType.quantityType(forIdentifier: .stepCount) {
            types.insert(stepCount)
        }
        if let activeEnergy = HKQuantityType.quantityType(forIdentifier: .activeEnergyBurned) {
            types.insert(activeEnergy)
        }
        if let distance = HKQuantityType.quantityType(forIdentifier: .distanceWalkingRunning) {
            types.insert(distance)
        }

        // Heart
        if let heartRate = HKQuantityType.quantityType(forIdentifier: .heartRate) {
            types.insert(heartRate)
        }
        if let restingHeartRate = HKQuantityType.quantityType(forIdentifier: .restingHeartRate) {
            types.insert(restingHeartRate)
        }

        // Sleep
        if let sleep = HKCategoryType.categoryType(forIdentifier: .sleepAnalysis) {
            types.insert(sleep)
        }

        // Workouts
        types.insert(HKWorkoutType.workoutType())

        return types
    }

    func handleMethodCall(_ call: FlutterMethodCall, result: @escaping FlutterResult) {
        guard HKHealthStore.isHealthDataAvailable() else {
            result(FlutterError(code: "UNAVAILABLE", message: "HealthKit is not available on this device", details: nil))
            return
        }

        switch call.method {
        case "hasPermission":
            hasPermission(result: result)
        case "requestPermission":
            requestPermission(result: result)
        case "getHealthSummary":
            getHealthSummary(call: call, result: result)
        case "getStepCount":
            getStepCount(call: call, result: result)
        case "getSleepData":
            getSleepData(call: call, result: result)
        case "getHeartRateData":
            getHeartRateData(call: call, result: result)
        case "getActiveEnergy":
            getActiveEnergy(call: call, result: result)
        case "getWorkouts":
            getWorkouts(call: call, result: result)
        default:
            result(FlutterMethodNotImplemented)
        }
    }

    private func hasPermission(result: @escaping FlutterResult) {
        // Check if we have authorization for at least step count
        guard let stepType = HKQuantityType.quantityType(forIdentifier: .stepCount) else {
            result(false)
            return
        }

        let status = healthStore.authorizationStatus(for: stepType)
        // HealthKit only reveals authorization status for write access
        // For read access, we check if user has at least been asked (not .notDetermined)
        result(status != .notDetermined)
    }

    private func requestPermission(result: @escaping FlutterResult) {
        healthStore.requestAuthorization(toShare: nil, read: readTypes) { success, error in
            DispatchQueue.main.async {
                if let error = error {
                    print("Error requesting HealthKit authorization: \(error.localizedDescription)")
                    result(false)
                    return
                }
                result(success)
            }
        }
    }

    private func getHealthSummary(call: FlutterMethodCall, result: @escaping FlutterResult) {
        let args = call.arguments as? [String: Any]
        let days = args?["days"] as? Int ?? 7

        let endDate = Date()
        let startDate = Calendar.current.date(byAdding: .day, value: -days, to: endDate)!

        var summary: [String: Any] = [:]
        let group = DispatchGroup()

        // Get steps with daily breakdown
        group.enter()
        fetchDailySteps(startDate: startDate, endDate: endDate) { dailySteps, total in
            summary["totalSteps"] = total
            summary["averageStepsPerDay"] = total / days
            summary["dailySteps"] = dailySteps  // Array of {date, steps}
            group.leave()
        }

        // Get active energy with daily breakdown
        group.enter()
        fetchDailyActiveEnergy(startDate: startDate, endDate: endDate) { dailyEnergy, total in
            summary["totalActiveEnergy"] = total
            summary["averageActiveEnergyPerDay"] = total / Double(days)
            summary["dailyActiveEnergy"] = dailyEnergy  // Array of {date, calories}
            group.leave()
        }

        // Get heart rate
        group.enter()
        fetchHeartRateStats(startDate: startDate, endDate: endDate) { stats in
            summary["heartRate"] = stats
            group.leave()
        }

        // Get sleep with daily breakdown
        group.enter()
        fetchDailySleep(startDate: startDate, endDate: endDate) { dailySleep, totalHours, sessions in
            summary["sleep"] = [
                "totalSleepHours": totalHours,
                "sessionsCount": sessions.count,
                "sessions": sessions,
                "daily": dailySleep  // Array of {date, sleepHours}
            ]
            group.leave()
        }

        // Get workouts count
        group.enter()
        fetchWorkouts(startDate: startDate, endDate: endDate) { workouts in
            summary["workoutsCount"] = workouts?.count ?? 0
            summary["workouts"] = workouts ?? []
            group.leave()
        }

        group.notify(queue: .main) {
            summary["periodDays"] = days
            summary["startDate"] = startDate.timeIntervalSince1970 * 1000
            summary["endDate"] = endDate.timeIntervalSince1970 * 1000
            result(summary)
        }
    }

    private func getStepCount(call: FlutterMethodCall, result: @escaping FlutterResult) {
        let (startDate, endDate) = parseDateRange(call: call)

        fetchStepCount(startDate: startDate, endDate: endDate) { steps in
            DispatchQueue.main.async {
                result(steps)
            }
        }
    }

    private func getSleepData(call: FlutterMethodCall, result: @escaping FlutterResult) {
        let (startDate, endDate) = parseDateRange(call: call)

        fetchSleepData(startDate: startDate, endDate: endDate) { sleepData in
            DispatchQueue.main.async {
                result(sleepData)
            }
        }
    }

    private func getHeartRateData(call: FlutterMethodCall, result: @escaping FlutterResult) {
        let (startDate, endDate) = parseDateRange(call: call)

        fetchHeartRateStats(startDate: startDate, endDate: endDate) { stats in
            DispatchQueue.main.async {
                result(stats)
            }
        }
    }

    private func getActiveEnergy(call: FlutterMethodCall, result: @escaping FlutterResult) {
        let (startDate, endDate) = parseDateRange(call: call)

        fetchActiveEnergy(startDate: startDate, endDate: endDate) { energy in
            DispatchQueue.main.async {
                result(energy)
            }
        }
    }

    private func getWorkouts(call: FlutterMethodCall, result: @escaping FlutterResult) {
        let (startDate, endDate) = parseDateRange(call: call)

        fetchWorkouts(startDate: startDate, endDate: endDate) { workouts in
            DispatchQueue.main.async {
                result(workouts)
            }
        }
    }

    // MARK: - Helper Methods

    private func parseDateRange(call: FlutterMethodCall) -> (Date, Date) {
        let args = call.arguments as? [String: Any]
        let endDate: Date
        let startDate: Date

        if let endMs = args?["endDate"] as? Int64 {
            endDate = Date(timeIntervalSince1970: TimeInterval(endMs) / 1000.0)
        } else {
            endDate = Date()
        }

        if let startMs = args?["startDate"] as? Int64 {
            startDate = Date(timeIntervalSince1970: TimeInterval(startMs) / 1000.0)
        } else {
            startDate = Calendar.current.date(byAdding: .day, value: -7, to: endDate)!
        }

        return (startDate, endDate)
    }

    private func fetchStepCount(startDate: Date, endDate: Date, completion: @escaping (Int?) -> Void) {
        guard let stepType = HKQuantityType.quantityType(forIdentifier: .stepCount) else {
            completion(nil)
            return
        }

        let predicate = HKQuery.predicateForSamples(withStart: startDate, end: endDate, options: .strictStartDate)

        let query = HKStatisticsQuery(
            quantityType: stepType,
            quantitySamplePredicate: predicate,
            options: .cumulativeSum
        ) { _, statistics, error in
            guard let statistics = statistics, let sum = statistics.sumQuantity() else {
                completion(nil)
                return
            }
            let steps = Int(sum.doubleValue(for: HKUnit.count()))
            completion(steps)
        }

        healthStore.execute(query)
    }

    private func fetchDailySteps(startDate: Date, endDate: Date, completion: @escaping ([[String: Any]], Int) -> Void) {
        guard let stepType = HKQuantityType.quantityType(forIdentifier: .stepCount) else {
            completion([], 0)
            return
        }

        let calendar = Calendar.current
        var interval = DateComponents()
        interval.day = 1

        // Anchor to start of day
        let anchorDate = calendar.startOfDay(for: startDate)

        // Add date predicate for the query
        let predicate = HKQuery.predicateForSamples(withStart: startDate, end: endDate, options: .strictStartDate)

        let query = HKStatisticsCollectionQuery(
            quantityType: stepType,
            quantitySamplePredicate: predicate,
            options: .cumulativeSum,
            anchorDate: anchorDate,
            intervalComponents: interval
        )

        query.initialResultsHandler = { _, results, error in
            guard let statsCollection = results else {
                completion([], 0)
                return
            }

            var dailySteps: [[String: Any]] = []
            var totalSteps = 0

            statsCollection.enumerateStatistics(from: startDate, to: endDate) { statistics, _ in
                let steps = statistics.sumQuantity()?.doubleValue(for: HKUnit.count()) ?? 0
                let stepsInt = Int(steps)
                totalSteps += stepsInt

                let dateFormatter = DateFormatter()
                dateFormatter.dateFormat = "yyyy-MM-dd"
                let dateString = dateFormatter.string(from: statistics.startDate)

                dailySteps.append([
                    "date": dateString,
                    "dateMs": statistics.startDate.timeIntervalSince1970 * 1000,
                    "steps": stepsInt
                ])
            }

            completion(dailySteps, totalSteps)
        }

        healthStore.execute(query)
    }

    private func fetchDailyActiveEnergy(startDate: Date, endDate: Date, completion: @escaping ([[String: Any]], Double) -> Void) {
        guard let energyType = HKQuantityType.quantityType(forIdentifier: .activeEnergyBurned) else {
            completion([], 0)
            return
        }

        let calendar = Calendar.current
        var interval = DateComponents()
        interval.day = 1

        let anchorDate = calendar.startOfDay(for: startDate)
        let predicate = HKQuery.predicateForSamples(withStart: startDate, end: endDate, options: .strictStartDate)

        let query = HKStatisticsCollectionQuery(
            quantityType: energyType,
            quantitySamplePredicate: predicate,
            options: .cumulativeSum,
            anchorDate: anchorDate,
            intervalComponents: interval
        )

        query.initialResultsHandler = { _, results, error in
            guard let statsCollection = results else {
                completion([], 0)
                return
            }

            var dailyEnergy: [[String: Any]] = []
            var totalEnergy: Double = 0

            statsCollection.enumerateStatistics(from: startDate, to: endDate) { statistics, _ in
                let energy = statistics.sumQuantity()?.doubleValue(for: HKUnit.kilocalorie()) ?? 0
                totalEnergy += energy

                let dateFormatter = DateFormatter()
                dateFormatter.dateFormat = "yyyy-MM-dd"
                let dateString = dateFormatter.string(from: statistics.startDate)

                dailyEnergy.append([
                    "date": dateString,
                    "dateMs": statistics.startDate.timeIntervalSince1970 * 1000,
                    "calories": energy
                ])
            }

            completion(dailyEnergy, totalEnergy)
        }

        healthStore.execute(query)
    }

    private func fetchDailySleep(startDate: Date, endDate: Date, completion: @escaping ([[String: Any]], Double, [[String: Any]]) -> Void) {
        guard let sleepType = HKCategoryType.categoryType(forIdentifier: .sleepAnalysis) else {
            completion([], 0, [])
            return
        }

        let predicate = HKQuery.predicateForSamples(withStart: startDate, end: endDate, options: .strictStartDate)
        let sortDescriptor = NSSortDescriptor(key: HKSampleSortIdentifierEndDate, ascending: false)

        let query = HKSampleQuery(
            sampleType: sleepType,
            predicate: predicate,
            limit: HKObjectQueryNoLimit,
            sortDescriptors: [sortDescriptor]
        ) { _, samples, error in
            guard let samples = samples as? [HKCategorySample] else {
                completion([], 0, [])
                return
            }

            let calendar = Calendar.current
            var dailySleepMap: [String: Double] = [:]
            var totalSleepSeconds: Double = 0
            var sleepSessions: [[String: Any]] = []
            let dateFormatter = DateFormatter()
            dateFormatter.dateFormat = "yyyy-MM-dd"

            for sample in samples {
                let duration = sample.endDate.timeIntervalSince(sample.startDate)
                var isSleep = false

                if #available(iOS 16.0, *) {
                    switch sample.value {
                    case HKCategoryValueSleepAnalysis.asleepCore.rawValue,
                         HKCategoryValueSleepAnalysis.asleepDeep.rawValue,
                         HKCategoryValueSleepAnalysis.asleepREM.rawValue,
                         HKCategoryValueSleepAnalysis.asleepUnspecified.rawValue:
                        isSleep = true
                    default:
                        break
                    }
                } else {
                    if sample.value == HKCategoryValueSleepAnalysis.asleep.rawValue {
                        isSleep = true
                    }
                }

                if isSleep {
                    totalSleepSeconds += duration
                    // Aggregate by the date the sleep ended (woke up)
                    let dateString = dateFormatter.string(from: sample.endDate)
                    dailySleepMap[dateString, default: 0] += duration
                }

                sleepSessions.append([
                    "startDate": sample.startDate.timeIntervalSince1970 * 1000,
                    "endDate": sample.endDate.timeIntervalSince1970 * 1000,
                    "durationMinutes": duration / 60.0,
                    "type": self.sleepTypeString(sample.value)
                ])
            }

            // Convert daily map to array
            var dailySleep: [[String: Any]] = []
            for (date, seconds) in dailySleepMap {
                dailySleep.append([
                    "date": date,
                    "sleepHours": seconds / 3600.0
                ])
            }
            // Sort by date descending
            dailySleep.sort { ($0["date"] as? String ?? "") > ($1["date"] as? String ?? "") }

            completion(dailySleep, totalSleepSeconds / 3600.0, sleepSessions)
        }

        healthStore.execute(query)
    }

    private func fetchActiveEnergy(startDate: Date, endDate: Date, completion: @escaping (Double?) -> Void) {
        guard let energyType = HKQuantityType.quantityType(forIdentifier: .activeEnergyBurned) else {
            completion(nil)
            return
        }

        let predicate = HKQuery.predicateForSamples(withStart: startDate, end: endDate, options: .strictStartDate)

        let query = HKStatisticsQuery(
            quantityType: energyType,
            quantitySamplePredicate: predicate,
            options: .cumulativeSum
        ) { _, statistics, error in
            guard let statistics = statistics, let sum = statistics.sumQuantity() else {
                completion(nil)
                return
            }
            let energy = sum.doubleValue(for: HKUnit.kilocalorie())
            completion(energy)
        }

        healthStore.execute(query)
    }

    private func fetchHeartRateStats(startDate: Date, endDate: Date, completion: @escaping ([String: Any]?) -> Void) {
        guard let heartRateType = HKQuantityType.quantityType(forIdentifier: .heartRate) else {
            completion(nil)
            return
        }

        let predicate = HKQuery.predicateForSamples(withStart: startDate, end: endDate, options: .strictStartDate)

        let query = HKStatisticsQuery(
            quantityType: heartRateType,
            quantitySamplePredicate: predicate,
            options: [.discreteAverage, .discreteMin, .discreteMax]
        ) { _, statistics, error in
            guard let statistics = statistics else {
                completion(nil)
                return
            }

            let unit = HKUnit.count().unitDivided(by: HKUnit.minute())
            var result: [String: Any] = [:]

            if let avg = statistics.averageQuantity() {
                result["average"] = avg.doubleValue(for: unit)
            }
            if let min = statistics.minimumQuantity() {
                result["minimum"] = min.doubleValue(for: unit)
            }
            if let max = statistics.maximumQuantity() {
                result["maximum"] = max.doubleValue(for: unit)
            }

            completion(result.isEmpty ? nil : result)
        }

        healthStore.execute(query)
    }

    private func fetchSleepData(startDate: Date, endDate: Date, completion: @escaping ([String: Any]?) -> Void) {
        guard let sleepType = HKCategoryType.categoryType(forIdentifier: .sleepAnalysis) else {
            completion(nil)
            return
        }

        let predicate = HKQuery.predicateForSamples(withStart: startDate, end: endDate, options: .strictStartDate)
        let sortDescriptor = NSSortDescriptor(key: HKSampleSortIdentifierEndDate, ascending: false)

        let query = HKSampleQuery(
            sampleType: sleepType,
            predicate: predicate,
            limit: HKObjectQueryNoLimit,
            sortDescriptors: [sortDescriptor]
        ) { _, samples, error in
            guard let samples = samples as? [HKCategorySample] else {
                completion(nil)
                return
            }

            var totalSleepSeconds: Double = 0
            var inBedSeconds: Double = 0
            var sleepSessions: [[String: Any]] = []

            for sample in samples {
                let duration = sample.endDate.timeIntervalSince(sample.startDate)

                if #available(iOS 16.0, *) {
                    switch sample.value {
                    case HKCategoryValueSleepAnalysis.asleepCore.rawValue,
                         HKCategoryValueSleepAnalysis.asleepDeep.rawValue,
                         HKCategoryValueSleepAnalysis.asleepREM.rawValue,
                         HKCategoryValueSleepAnalysis.asleepUnspecified.rawValue:
                        totalSleepSeconds += duration
                    case HKCategoryValueSleepAnalysis.inBed.rawValue:
                        inBedSeconds += duration
                    default:
                        break
                    }
                } else {
                    if sample.value == HKCategoryValueSleepAnalysis.asleep.rawValue {
                        totalSleepSeconds += duration
                    } else if sample.value == HKCategoryValueSleepAnalysis.inBed.rawValue {
                        inBedSeconds += duration
                    }
                }

                sleepSessions.append([
                    "startDate": sample.startDate.timeIntervalSince1970 * 1000,
                    "endDate": sample.endDate.timeIntervalSince1970 * 1000,
                    "durationMinutes": duration / 60.0,
                    "type": self.sleepTypeString(sample.value)
                ])
            }

            let result: [String: Any] = [
                "totalSleepHours": totalSleepSeconds / 3600.0,
                "totalInBedHours": inBedSeconds / 3600.0,
                "sessionsCount": sleepSessions.count,
                "sessions": sleepSessions
            ]

            completion(result)
        }

        healthStore.execute(query)
    }

    private func sleepTypeString(_ value: Int) -> String {
        if #available(iOS 16.0, *) {
            switch value {
            case HKCategoryValueSleepAnalysis.asleepCore.rawValue:
                return "core"
            case HKCategoryValueSleepAnalysis.asleepDeep.rawValue:
                return "deep"
            case HKCategoryValueSleepAnalysis.asleepREM.rawValue:
                return "rem"
            case HKCategoryValueSleepAnalysis.asleepUnspecified.rawValue:
                return "asleep"
            case HKCategoryValueSleepAnalysis.inBed.rawValue:
                return "inBed"
            case HKCategoryValueSleepAnalysis.awake.rawValue:
                return "awake"
            default:
                return "unknown"
            }
        } else {
            switch value {
            case HKCategoryValueSleepAnalysis.asleep.rawValue:
                return "asleep"
            case HKCategoryValueSleepAnalysis.inBed.rawValue:
                return "inBed"
            case HKCategoryValueSleepAnalysis.awake.rawValue:
                return "awake"
            default:
                return "unknown"
            }
        }
    }

    private func fetchWorkouts(startDate: Date, endDate: Date, completion: @escaping ([[String: Any]]?) -> Void) {
        let predicate = HKQuery.predicateForSamples(withStart: startDate, end: endDate, options: .strictStartDate)
        let sortDescriptor = NSSortDescriptor(key: HKSampleSortIdentifierEndDate, ascending: false)

        let query = HKSampleQuery(
            sampleType: HKWorkoutType.workoutType(),
            predicate: predicate,
            limit: HKObjectQueryNoLimit,
            sortDescriptors: [sortDescriptor]
        ) { _, samples, error in
            guard let workouts = samples as? [HKWorkout] else {
                completion(nil)
                return
            }

            let result: [[String: Any]] = workouts.map { workout in
                var workoutData: [String: Any] = [
                    "type": self.workoutTypeString(workout.workoutActivityType),
                    "startDate": workout.startDate.timeIntervalSince1970 * 1000,
                    "endDate": workout.endDate.timeIntervalSince1970 * 1000,
                    "durationMinutes": workout.duration / 60.0
                ]

                if let totalEnergy = workout.totalEnergyBurned {
                    workoutData["caloriesBurned"] = totalEnergy.doubleValue(for: HKUnit.kilocalorie())
                }

                if let totalDistance = workout.totalDistance {
                    workoutData["distanceKm"] = totalDistance.doubleValue(for: HKUnit.meterUnit(with: .kilo))
                }

                return workoutData
            }

            completion(result)
        }

        healthStore.execute(query)
    }

    private func workoutTypeString(_ type: HKWorkoutActivityType) -> String {
        switch type {
        case .running: return "Running"
        case .walking: return "Walking"
        case .cycling: return "Cycling"
        case .swimming: return "Swimming"
        case .hiking: return "Hiking"
        case .yoga: return "Yoga"
        case .functionalStrengthTraining: return "Strength Training"
        case .traditionalStrengthTraining: return "Strength Training"
        case .crossTraining: return "Cross Training"
        case .elliptical: return "Elliptical"
        case .rowing: return "Rowing"
        case .stairClimbing: return "Stair Climbing"
        case .highIntensityIntervalTraining: return "HIIT"
        case .dance: return "Dance"
        case .pilates: return "Pilates"
        case .tennis: return "Tennis"
        case .basketball: return "Basketball"
        case .soccer: return "Soccer"
        case .golf: return "Golf"
        default: return "Other"
        }
    }
}
