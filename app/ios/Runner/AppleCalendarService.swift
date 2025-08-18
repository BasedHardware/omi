import Foundation
import EventKit
import UIKit
import Flutter

/// Native service for handling Apple Calendar interactions via Flutter.
///
/// Exposes two methods to Flutter: `createEvent` to add a new event to the
/// user's default calendar and `checkAvailability` to verify that Calendar
/// services are available. All calls are dispatched on the main thread to
/// ensure proper UI interactions and permission prompts.
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
        
        // Request calendar permissions and then create the event
        if #available(iOS 17.0, *) {
            eventStore.requestFullAccessToEvents { granted, _ in
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
            eventStore.requestAccess(to: .event) { granted, _ in
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
            // Default event duration: now + 1 hour
            event.startDate = Date()
            event.endDate = Date().addingTimeInterval(3600)
            event.calendar = self.eventStore.defaultCalendarForNewEvents
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
        // Calendar services are always available on iOS
        result(true)
    }
}
