import OmiExtras
import SwiftUI

/// A task Omi works on, in the recording card's language: the pendant (lit while Omi works) with a
/// sparkle badge, a status title over the task, the clock, the breathing wave, the current step.
struct AgentSnapshot {
    typealias State = OmiActivityAttributes.ContentState

    let state: State

    var working: Bool {
        state.phase == .working || state.phase == .recording
    }

    var tint: Color {
        switch state.phase {
        case .finished: CapturePalette.success
        case .failed: CapturePalette.warning
        case .recording, .working: CapturePalette.led
        }
    }

    var symbol: String {
        switch state.phase {
        case .finished: "checkmark"
        case .failed: "exclamationmark"
        case .recording, .working: "sparkles"
        }
    }

    var heading: LocalizedStringKey {
        switch state.phase {
        case .finished: "Omi finished"
        case .failed: "Omi couldn't finish"
        case .recording, .working: "Omi is working"
        }
    }

    /// The island's title beside the camera, where "Omi is working" does not fit.
    var shortHeading: LocalizedStringKey {
        switch state.phase {
        case .finished: "Done"
        case .failed: "Stuck"
        case .recording, .working: "Working"
        }
    }

    var clock: ActivityClockValue {
        ActivityClockValue(kind: .run, startedAt: state.startedAt, clockEnd: state.clockEnd, frozen: working ? nil : state.elapsed)
    }

    /// The step (or what to do now), with how many other runs are going.
    var detail: Text {
        let base = switch state.phase {
        case .finished: Text("Tap to see what Omi did", bundle: .activity)
        case .failed: Text("Tap to open the task", bundle: .activity)
        case .recording, .working:
            if state.step.isEmpty { Text("Getting started…", bundle: .activity) } else { Text(verbatim: state.step) }
        }
        guard state.otherRuns > 0, working else { return base }
        return base + Text(verbatim: " · ") + Text("+\(state.otherRuns) more", bundle: .activity)
    }
}

/// The pendant with a badge for the run's state. Below 28 pt (compact and minimal island) the badge
/// alone, as a glowing glyph.
struct AgentArt: View {
    let snapshot: AgentSnapshot
    let size: CGFloat

    var body: some View {
        if size < 28 {
            Image(systemName: snapshot.symbol)
                .font(.system(size: size * 0.8, weight: .semibold))
                .foregroundStyle(snapshot.tint)
                .shadow(color: snapshot.tint.opacity(0.45), radius: size * 0.18)
                .frame(width: size, height: size)
                .accessibilityHidden(true)
        } else {
            CapturePendant(active: snapshot.working, size: size)
                .overlay(alignment: .bottomTrailing) {
                    Image(systemName: snapshot.symbol)
                        .font(.system(size: size * 0.2, weight: .bold))
                        .foregroundStyle(CapturePalette.ink)
                        .frame(width: size * 0.42, height: size * 0.42)
                        .background(snapshot.tint, in: Circle())
                        .overlay(Circle().stroke(CapturePalette.ink, lineWidth: 1.5))
                        .offset(x: size * 0.06, y: size * 0.06)
                        .accessibilityHidden(true)
                }
        }
    }
}

/// The Lock Screen card: the recording card's top row and wave, the step where its buttons are.
struct AgentLockScreenView: View {
    let snapshot: AgentSnapshot

    var body: some View {
        VStack(spacing: 10) {
            HStack(spacing: 12) {
                AgentArt(snapshot: snapshot, size: 36 * CaptureLayout.heroScale)
                VStack(alignment: .leading, spacing: 0) {
                    Text(snapshot.heading, bundle: .activity)
                        .font(.subheadline.weight(.semibold))
                        .foregroundStyle(CapturePalette.label)
                        .lineLimit(1)
                    Text(verbatim: snapshot.state.title)
                        .font(.footnote)
                        .foregroundStyle(CapturePalette.secondary)
                        .lineLimit(2)
                }
                .fixedSize(horizontal: false, vertical: true)
                .frame(maxWidth: .infinity, alignment: .leading)
                CaptureClock(value: snapshot.clock, size: 30)
            }
            .frame(height: 58)
            CaptureWaveform(running: snapshot.working, startedAt: snapshot.state.startedAt, height: 22)
            AgentStepLine(snapshot: snapshot, height: 40)
        }
        .modifier(ActivityCard())
    }
}

/// The step in the place of the recording's buttons: one line in a quiet capsule.
struct AgentStepLine: View {
    let snapshot: AgentSnapshot
    let height: CGFloat
    var fill = 0.12

    var body: some View {
        snapshot.detail
            .font(.subheadline.weight(.semibold))
            .foregroundStyle(snapshot.working ? CapturePalette.label : snapshot.tint)
            .lineLimit(1)
            .padding(.horizontal, 16)
            .frame(maxWidth: .infinity, minHeight: height)
            .background(Color.white.opacity(fill), in: Capsule())
            .dynamicTypeSize(...DynamicTypeSize.xLarge)
    }
}

struct AgentIslandLeading: View {
    let snapshot: AgentSnapshot

    var body: some View {
        IslandLeading(title: snapshot.shortHeading) {
            AgentArt(snapshot: snapshot, size: 32)
        }
    }
}

/// The expanded island's bottom region, in the recording's 22 + 10 + 38: the wave, the task's
/// title over its step.
struct AgentIslandBottom: View {
    let snapshot: AgentSnapshot

    var body: some View {
        VStack(spacing: 10) {
            CaptureWaveform(running: snapshot.working, startedAt: snapshot.state.startedAt, height: 22)
            VStack(alignment: .leading, spacing: 0) {
                Text(verbatim: snapshot.state.title)
                    .font(.subheadline.weight(.semibold))
                    .foregroundStyle(CapturePalette.label)
                    .lineLimit(1)
                snapshot.detail
                    .font(.footnote)
                    .foregroundStyle(CapturePalette.secondary)
                    .lineLimit(1)
            }
            .frame(maxWidth: .infinity, minHeight: 38, alignment: .leading)
            .padding(.horizontal, 4)
            .dynamicTypeSize(...DynamicTypeSize.large)
        }
    }
}
