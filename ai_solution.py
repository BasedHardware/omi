```swift
// HealthKit extension
@objc(OMH_Health)
class OMH_Health: NSObject {
    @objc class func handleWorkout(_ callback: @escaping ([String: Any]) -> Void) {
        let healthStore = HKHealthStore()
        let workoutType = HKWorkoutType()
        let query = HKSampleQuery(
            quantityType: HKWorkoutType.workout,
            startDate: Date(),
            endDate: nil
        ) { (query, result) in
            guard let result = result as? HKSampleCollection else { return }
            guard let sample = result.firstSample() else { return }
            let value = sample.value
            // Process the value and return
            callback(["workout": value])
        }
        healthStore.execute(query)
    }
}

// Usage
extension Health {
    func getWorkout() {
        OMH_Health.handleWorkout { result in
            // Use the result
        }
    }
}
```