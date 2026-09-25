import AppKit
import ContextCore
import SwiftUI

/// Capture: whether the screen is being recorded, and whether idling pauses it.
///
/// **The Capture Quality tiles are gone**, on the report *"don't give capture quality option"*.
/// They were a real setting by the end — `FrameImage` genuinely resized and re-compressed to the
/// selected tile — but the choice they offered was between one good answer and three worse ones:
/// three of the four tiles bought disk back by making the user's own screenshots harder to read,
/// and since the `look` tool started handing frames to Claude as images, harder for a model to read
/// too. What every install shipped on is now what every install gets; the numbers live in
/// `FrameImage.Quality`.
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
        }
    }

    /// `CaptureActivity.idleThreshold` in whole minutes, for the row above. Whole minutes because the
    /// constant is 300s exactly and a fractional figure in a settings row would be noise.
    private static var idleMinutes: Int { Int(CaptureActivity.idleThreshold / 60) }
}
