// Created by Barrett Jacobsen

import AppIntents
import WidgetKit

enum ComplicationTapAction: String, AppEnum {
    case startDeviceRecording = "startDeviceRecording"
    case startWatchRecording = "startWatchRecording"
    case askQuestion = "askQuestion"
    case openApp = "openApp"

    static var typeDisplayRepresentation: TypeDisplayRepresentation {
        "Tap Action"
    }

    static var caseDisplayRepresentations: [ComplicationTapAction: DisplayRepresentation] {
        [
            .startDeviceRecording: "Start Device Recording",
            .startWatchRecording: "Start Watch Recording",
            .askQuestion: "Ask a Question",
            .openApp: "Open App",
        ]
    }
}

struct DeviceMonitorConfigIntent: WidgetConfigurationIntent {
    static var title: LocalizedStringResource = "Omi Device Monitor"
    static var description: IntentDescription = "Monitor your Omi device and choose what happens on tap."

    @Parameter(title: "Tap Action", default: .startDeviceRecording)
    var tapAction: ComplicationTapAction
}
