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
                    Toggle(
                        "",
                        isOn: Binding(
                            get: { store.screenCaptureEnabled },
                            set: { value in
                                Sound.effect(.click)
                                store.screenCaptureEnabled = value
                            })
                    )
                    .labelsHidden()
                    .toggleStyle(.switch)
                    .controlSize(.small)
                }

                SettingsRowDivider()

                SettingsRow(
                    icon: "moon.zzz",
                    title: "Pause on Inactivity",
                    subtitle: "Automatically suspends recording when no keyboard or mouse activity is detected."
                ) {
                    Toggle(
                        "",
                        isOn: Binding(
                            get: { store.pausesOnInactivity },
                            set: { value in
                                Sound.effect(.click)
                                store.pausesOnInactivity = value
                            })
                    )
                    .labelsHidden()
                    .toggleStyle(.switch)
                    .controlSize(.small)
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
