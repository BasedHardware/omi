import AppKit
import SwiftUI

// MARK: - Shared page-header controls
//
// The Capture/Listening status pills and the settings menu were born on the
// Home header; they're shared components now so every main page can carry
// the same control cluster (see PageHeaderView). Moved verbatim from
// DashboardPage — visuals unchanged.

enum HomeStatusState {
    case active
    case inactive
    case blocked

    var indicator: Color {
        switch self {
        case .active:
            return HomePalette.green
        case .inactive:
            return HomePalette.faint
        case .blocked:
            return Color(red: 1.0, green: 0.24, blue: 0.30)
        }
    }

    var text: String {
        switch self {
        case .active:
            return "On"
        case .inactive:
            return "Off"
        case .blocked:
            return "Blocked"
        }
    }

    var isActive: Bool {
        if case .active = self { return true }
        return false
    }

    var isBlocked: Bool {
        if case .blocked = self { return true }
        return false
    }
}

struct HomeStatusButton: View {
    let title: String
    let systemImage: String
    let status: HomeStatusState
    let isToggling: Bool
    let action: () -> Void

    @State private var isHovering = false

    var body: some View {
        Button(action: action) {
            HStack(spacing: 8) {
                ZStack {
                    if isToggling {
                        ProgressView()
                            .controlSize(.small)
                            .scaleEffect(0.55)
                    } else {
                        Image(systemName: systemImage)
                            .scaledFont(size: 13, weight: .semibold)
                    }
                }
                .frame(width: 18, height: 18)

                Text(title)
                    .scaledFont(size: 12, weight: .semibold)
                    .lineLimit(1)
            }
            .foregroundStyle(status.isActive ? HomePalette.ink : (status.isBlocked ? status.indicator : HomePalette.muted))
            .padding(.horizontal, 12)
            .padding(.vertical, 8)
            .frame(height: 34)
            .background(
                Capsule(style: .continuous)
                    .fill(statusFill)
            )
            .overlay(
                Capsule(style: .continuous)
                    .stroke(statusStroke, lineWidth: 1)
            )
            .contentShape(Capsule())
        }
        .buttonStyle(.plain)
        .disabled(isToggling)
        .onHover { isHovering = $0 }
        .help("\(title): \(status.text)")
        .accessibilityLabel("\(title) \(status.text)")
    }

    private var statusFill: Color {
        if status.isActive {
            return HomePalette.green.opacity(isHovering ? 0.20 : 0.12)
        }
        if status.isBlocked {
            return status.indicator.opacity(isHovering ? 0.16 : 0.10)
        }
        return isHovering ? HomePalette.tileHover : HomePalette.panel
    }

    private var statusStroke: Color {
        if status.isActive {
            return HomePalette.green.opacity(0.38)
        }
        if status.isBlocked {
            return status.indicator.opacity(isHovering ? 0.54 : 0.38)
        }
        return HomePalette.hairline.opacity(isHovering ? 0.8 : 0.58)
    }
}

struct HomeListeningStatusButton: View {
    let title: String
    let systemImage: String
    let status: HomeStatusState
    let modeTitle: String
    let isMeetingsOnly: Bool
    let isToggling: Bool
    let action: () -> Void
    let modeAction: () -> Void

    // Single pill-level hover flag so moving between the title and the mode
    // toggle never flickers the revealed controls.
    @State private var isHovering = false

    var body: some View {
        HStack(spacing: 0) {
            Button(action: action) {
                HStack(spacing: 8) {
                    ZStack {
                        if isToggling {
                            ProgressView()
                                .controlSize(.small)
                                .scaleEffect(0.55)
                        } else {
                            Image(systemName: systemImage)
                                .scaledFont(size: 13, weight: .semibold)
                        }
                    }
                    .frame(width: 18, height: 18)

                    VStack(alignment: .leading, spacing: 1) {
                        Text(title)
                            .scaledFont(size: 12, weight: .semibold)
                            .lineLimit(1)

                        // Mode ("Always" / "In meeting" / …) is revealed only on
                        // hover to keep the resting pill clean.
                        if isHovering {
                            Text(modeTitle)
                                .scaledFont(size: 8, weight: .medium)
                                .foregroundStyle(status.isActive ? HomePalette.secondary : HomePalette.muted)
                                .lineLimit(1)
                                .transition(.opacity)
                        }
                    }
                }
                .padding(.leading, 12)
                .padding(.trailing, 8)
                .frame(height: 34)
                .contentShape(Rectangle())
            }
            .buttonStyle(.plain)
            .disabled(isToggling)
            .help("Listening: \(status.text), \(modeTitle)")
            .accessibilityLabel("Listening \(status.text), \(modeTitle)")

            // Divider + mode toggle are revealed only on hover to keep the
            // resting pill compact.
            if isHovering {
                Rectangle()
                    .fill(HomePalette.hairline.opacity(0.65))
                    .frame(width: 1, height: 18)
                    .transition(.opacity)

                Button(action: modeAction) {
                    Image(systemName: isMeetingsOnly ? "person.2.fill" : "person.fill")
                        .scaledFont(size: 11, weight: .semibold)
                        .foregroundStyle(modeIconColor)
                        .frame(width: 30, height: 34)
                        .contentShape(Rectangle())
                }
                .buttonStyle(.plain)
                .help(isMeetingsOnly ? "Switch to always listening" : "Switch to meetings only")
                .accessibilityLabel(isMeetingsOnly ? "Switch Listening to Always" : "Switch Listening to Meetings Only")
                .transition(.opacity)
            }
        }
        .foregroundStyle(status.isActive ? HomePalette.ink : (status.isBlocked ? status.indicator : HomePalette.muted))
        .background(
            Capsule(style: .continuous)
                .fill(statusFill)
        )
        .overlay(
            Capsule(style: .continuous)
                .stroke(statusStroke, lineWidth: 1)
        )
        .contentShape(Capsule())
        .frame(height: 34)
        .onHover { isHovering = $0 }
        .animation(.easeInOut(duration: 0.14), value: isHovering)
    }

    private var modeIconColor: Color {
        status.isActive ? HomePalette.green : HomePalette.muted
    }

    private var statusFill: Color {
        if status.isActive {
            return HomePalette.green.opacity(isHovering ? 0.20 : 0.12)
        }
        if status.isBlocked {
            return status.indicator.opacity(isHovering ? 0.16 : 0.10)
        }
        return isHovering ? HomePalette.tileHover : HomePalette.panel
    }

    private var statusStroke: Color {
        if status.isActive {
            return HomePalette.green.opacity(0.38)
        }
        if status.isBlocked {
            return status.indicator.opacity(isHovering ? 0.54 : 0.38)
        }
        return HomePalette.hairline.opacity(isHovering ? 0.8 : 0.58)
    }
}

struct HomeSettingsMenuButton: View {
    let onRefer: () -> Void
    let onDiscord: () -> Void
    let onSettings: () -> Void

    @State private var isHovering = false
    @State private var isPresented = false

    var body: some View {
        Button {
            isPresented.toggle()
        } label: {
            ZStack {
                Circle()
                    .fill(isHovering ? HomePalette.tileHover : HomePalette.tile.opacity(0.86))
                    .overlay(
                        Circle()
                            .stroke(HomePalette.hairline.opacity(isHovering ? 0.9 : 0.68), lineWidth: 1)
                    )

                Image(systemName: "gearshape.fill")
                    .scaledFont(size: 14, weight: .semibold)
                    .foregroundStyle(isHovering ? HomePalette.ink : HomePalette.secondary)
            }
            .frame(width: 34, height: 34)
            .contentShape(Circle())
        }
        .buttonStyle(.plain)
        .onHover { isHovering = $0 }
        .popover(isPresented: $isPresented, arrowEdge: .top) {
            VStack(alignment: .leading, spacing: 4) {
                popoverButton(title: "Refer a Friend", systemImage: "gift.fill") {
                    isPresented = false
                    onRefer()
                }

                popoverButton(title: "Discord", systemImage: "message.fill") {
                    isPresented = false
                    onDiscord()
                }

                Divider()
                    .padding(.vertical, 3)

                popoverButton(title: "Settings", systemImage: "gearshape.fill") {
                    isPresented = false
                    onSettings()
                }
            }
            .padding(8)
            .frame(width: 190)
            .background(HomePalette.panel)
        }
        .help("Settings")
        .accessibilityLabel("Settings menu")
    }

    private func popoverButton(title: String, systemImage: String, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            HStack(spacing: 10) {
                Image(systemName: systemImage)
                    .scaledFont(size: 13, weight: .semibold)
                    .foregroundStyle(HomePalette.secondary)
                    .frame(width: 18)

                Text(title)
                    .scaledFont(size: 13, weight: .medium)
                    .foregroundStyle(HomePalette.ink)

                Spacer(minLength: 0)
            }
            .padding(.horizontal, 9)
            .padding(.vertical, 7)
            .contentShape(.rect(cornerRadius: 8))
        }
        .buttonStyle(.plain)
    }
}
