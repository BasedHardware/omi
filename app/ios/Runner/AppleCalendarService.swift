import Foundation
import EventKit
import UIKit

class AppleCalendarService: NSObject {
    private let eventStore = EKEventStore()
    
    func handleMethodCall(_ call: FlutterMethodCall, result: @escaping FlutterResult) {
        switch call.method {
        case "createEvent":
            createEvent(call: call, result: result)
        case "checkAvailability":
            checkAvailability(result: result)
        default:
            result(FlutterMethodNotImplemented)
        }
    }
    
    private func createEvent(call: FlutterMethodCall, result: @escaping FlutterResult) {
        guard let args = call.arguments as? [String: Any],
              let title = args["title"] as? String,
              let notes = args["notes"] as? String else {
            result(FlutterError(code: "INVALID_ARGUMENTS",
                                message: "Invalid arguments for createEvent",
                                details: nil))
            return
        }
        
        if #available(iOS 17.0, *) {
            eventStore.requestFullAccessToEvents { granted, error in
                DispatchQueue.main.async {
                    if granted {
                        self.createAndSaveEvent(title: title, notes: notes, result: result)
                    } else {
                        result([
                            "success": false,
                            "message": "Calendar access denied. Please enable in Settings."
                        ])
                    }
                }
            }
        } else {
            // Fallback for iOS 16 and earlier
            eventStore.requestAccess(to: .event) { granted, error in
                DispatchQueue.main.async {
                    if granted {
                        self.createAndSaveEvent(title: title, notes: notes, result: result)
                    } else {
                        result([
                            "success": false,
                            "message": "Calendar access denied. Please enable in Settings."
                        ])
                    }
                }
            }
        }
    }
    
    private func createAndSaveEvent(title: String, notes: String, result: @escaping FlutterResult) {
        do {
            let event = EKEvent(eventStore: self.eventStore)
            event.title = title
            event.notes = notes
            
            // Set the event to today with a default duration of 1 hour
            event.startDate = Date()
            event.endDate = Date().addingTimeInterval(3600) // 1 hour later
            
            // Use the default calendar
            event.calendar = self.eventStore.defaultCalendarForNewEvents
            
            // Save the event
            try self.eventStore.save(event, span: .thisEvent)
            
            result([
                "success": true,
                "message": "Event created in Calendar"
            ])
        } catch {
            result([
                "success": false,
                "message": "Failed to create event: \(error.localizedDescription)"
            ])
        }
    }
    
    private func checkAvailability(result: @escaping FlutterResult) {
        // Check if Calendar app is available (it always is on iOS)
        result(true)
    }
}