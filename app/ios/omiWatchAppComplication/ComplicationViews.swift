// Created by Barrett Jacobsen

import SwiftUI
import WidgetKit

// MARK: - Device Monitor Views

struct DeviceMonitorCircularView: View {
    let batteryLevel: Float
    let isRecording: Bool
    let isConnected: Bool

    var body: some View {
        ZStack {
            AccessoryWidgetBackground()
            Gauge(value: Double(max(0, batteryLevel)), in: 0...100) {
                Image(systemName: isRecording ? "waveform" : "bolt.fill")
                    .font(.system(size: 10))
            }
            .gaugeStyle(.accessoryCircular)
            .tint(isRecording ? .green : (isConnected ? .white : .gray))
        }
    }
}

struct DeviceMonitorRectangularView: View {
    let batteryLevel: Float
    let isRecording: Bool
    let isConnected: Bool

    var body: some View {
        HStack {
            VStack(alignment: .leading, spacing: 2) {
                Text("Omi")
                    .font(.headline)
                    .widgetAccentable()
                if isConnected {
                    Text(isRecording ? "Recording" : "Connected")
                        .font(.caption)
                } else {
                    Text("Disconnected")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
            }
            Spacer()
            if isConnected && batteryLevel >= 0 {
                Label("\(Int(batteryLevel))%", systemImage: batteryIconName(level: batteryLevel))
                    .font(.caption)
            }
        }
    }

    private func batteryIconName(level: Float) -> String {
        switch level {
        case 0..<25: return "battery.25percent"
        case 25..<50: return "battery.50percent"
        case 50..<75: return "battery.75percent"
        default: return "battery.100percent"
        }
    }
}

struct DeviceMonitorInlineView: View {
    let batteryLevel: Float
    let isRecording: Bool
    let isConnected: Bool

    var body: some View {
        if isConnected {
            if isRecording {
                Label("Omi \(Int(batteryLevel))% · Recording", systemImage: "waveform")
            } else {
                Label("Omi \(Int(batteryLevel))%", systemImage: "bolt.fill")
            }
        } else {
            Label("Omi · Disconnected", systemImage: "bolt.slash")
        }
    }
}

struct DeviceMonitorCornerView: View {
    let batteryLevel: Float
    let isRecording: Bool

    var body: some View {
        Image(systemName: isRecording ? "waveform" : "bolt.fill")
            .font(.title3)
            .widgetLabel {
                Gauge(value: Double(max(0, batteryLevel)), in: 0...100) {
                    Text("Omi")
                }
                .gaugeStyle(.accessoryLinear)
            }
    }
}

// MARK: - Quick Record Views

struct QuickRecordCircularView: View {
    let isRecording: Bool

    var body: some View {
        ZStack {
            AccessoryWidgetBackground()
            Image(systemName: isRecording ? "mic.fill" : "mic")
                .font(.title2)
                .foregroundStyle(isRecording ? .green : .white)
        }
    }
}

struct QuickRecordRectangularView: View {
    let isRecording: Bool

    var body: some View {
        HStack {
            Image(systemName: isRecording ? "mic.fill" : "mic")
                .font(.title3)
                .foregroundStyle(isRecording ? .green : .white)
                .widgetAccentable()
            VStack(alignment: .leading, spacing: 2) {
                Text("Omi Recorder")
                    .font(.headline)
                Text(isRecording ? "Listening..." : "Tap to Record")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
        }
    }
}

struct QuickRecordInlineView: View {
    let isRecording: Bool

    var body: some View {
        Label(isRecording ? "Omi: Listening" : "Omi: Tap to Record", systemImage: isRecording ? "mic.fill" : "mic")
    }
}

struct QuickRecordCornerView: View {
    let isRecording: Bool

    var body: some View {
        Image(systemName: isRecording ? "mic.fill" : "mic")
            .font(.title3)
            .widgetLabel(isRecording ? "Listening" : "Record")
    }
}

// MARK: - Ask Omi Views

struct AskOmiCircularView: View {
    var body: some View {
        ZStack {
            AccessoryWidgetBackground()
            Image(systemName: "bubble.left.fill")
                .font(.title2)
        }
    }
}

struct AskOmiRectangularView: View {
    var body: some View {
        HStack {
            Image(systemName: "bubble.left.fill")
                .font(.title3)
                .widgetAccentable()
            VStack(alignment: .leading, spacing: 2) {
                Text("Ask Omi")
                    .font(.headline)
                Text("Tap to ask a question")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
        }
    }
}

struct AskOmiInlineView: View {
    var body: some View {
        Label("Ask Omi a Question", systemImage: "bubble.left.fill")
    }
}

struct AskOmiCornerView: View {
    var body: some View {
        Image(systemName: "bubble.left.fill")
            .font(.title3)
            .widgetLabel("Ask Omi")
    }
}
