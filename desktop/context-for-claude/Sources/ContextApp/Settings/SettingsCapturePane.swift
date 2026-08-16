import AppKit
import ContextCore
import SwiftUI

/// Capture: whether the screen is being recorded, whether idling pauses it, and the quality of the
/// stored picture.
struct SettingsCapturePane: View {
    @ObservedObject var store: SettingsStore

    var body: some View {
        SettingsPaneScroll {
            SettingsSection(title: "Recording") {
                SettingsRow(
                    icon: "record.circle",
                    title: "Screen Capture",
                    subtitle: "Controls whether your screen is actively being recorded."
                ) {
                    SettingsToggle(
                        title: "Screen Capture", isOn: $store.screenCaptureEnabled,
                        onChange: { _ in Sound.effect(.click) })
                }

                SettingsRowDivider()

                SettingsRow(
                    icon: "moon.zzz",
                    title: "Pause on Inactivity",
                    // "Suspends recording" was too broad: the idle check lives in `ScreenWatcher`, so
                    // it stops screenshots and nothing else — microphone and system-audio
                    // transcription keep running while the machine is idle, which is a room the user
                    // has walked away from still being recorded. Say which half stops.
                    //
                    // The threshold is named because "inactivity" alone is not a decision anyone can
                    // make: five minutes is short enough that a video watched hands-off stops being
                    // captured, and a user cannot weigh that against an unquantified word. Read from
                    // `CaptureActivity.idleThreshold` rather than typed as "five" so the sentence
                    // cannot outlive the constant it describes.
                    subtitle: "Stops taking screenshots after \(Self.idleMinutes) minutes with no "
                        + "keyboard or mouse activity, until you touch the machine again. "
                        + "Audio transcription is not affected."
                ) {
                    SettingsToggle(
                        title: "Pause on Inactivity", isOn: $store.pausesOnInactivity,
                        onChange: { _ in Sound.effect(.click) })
                }
            }

            SettingsSection(
                title: "Capture Quality",
                footnote: "Higher quality preserves more detail but uses more disk space. "
                    + "Text search is unaffected — it reads a separate, larger image before this one is stored."
            ) {
                VStack(alignment: .leading, spacing: 9) {
                    HStack(spacing: 8) {
                        ForEach(CaptureQuality.allCases) { quality in
                            SettingsTile(isSelected: store.captureQuality == quality) {
                                Sound.effect(.click)
                                store.captureQuality = quality
                            } content: {
                                VStack(spacing: 4) {
                                    Image(systemName: symbol(for: quality))
                                        .font(.system(size: 13, weight: .medium))
                                        .foregroundStyle(Ink.primary)
                                    Text(quality.title)
                                        .font(.system(size: 10, weight: .medium))
                                        .foregroundStyle(Ink.primary)
                                        .lineLimit(1)
                                        .minimumScaleFactor(0.8)
                                }
                            }
                        }
                    }
                    // The subtitle describes the *selected* tile, which is what the reference does.
                    Text(store.captureQuality.subtitle)
                        .font(.system(size: 11))
                        .foregroundStyle(Ink.secondary)
                        .fixedSize(horizontal: false, vertical: true)
                }
                .padding(12)
            }
        }
    }

    /// `CaptureActivity.idleThreshold` in whole minutes, for the row above. Whole minutes because the
    /// constant is 300s exactly and a fractional figure in a settings row would be noise.
    private static var idleMinutes: Int { Int(CaptureActivity.idleThreshold / 60) }

    /// A four-step ladder rather than four unrelated glyphs, so the tiles read as one scale.
    private func symbol(for quality: CaptureQuality) -> String {
        switch quality {
        case .best: "square.grid.3x3.fill"
        case .standard: "square.grid.2x2.fill"
        case .compact: "square.split.2x2"
        case .smallest: "square"
        }
    }
}
