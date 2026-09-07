import OmiTheme
import SwiftUI

/// Source-specific transport embedded in the canonical transcript. Transcript
/// bubbles own precise moment seeking, so playback no longer creates a second
/// transcript-like list ahead of the conversation summary.
struct ConversationCapturePlaybackSection: View {
  let capture: ServerConversation
  @ObservedObject var playback: CapturePlaybackController
  @ObservedObject var resync: CaptureTranscriptResyncer
  let onPrepare: () -> Void
  let onRefresh: () -> Void

  var body: some View {
    VStack(alignment: .leading, spacing: OmiSpacing.md) {
      HStack(spacing: OmiSpacing.sm) {
        Image(systemName: "waveform")
          .scaledFont(size: OmiType.body)
          .foregroundStyle(Ink.secondary)
        Text("Audio")
          .scaledFont(size: OmiType.subheading, weight: .semibold)
          .foregroundStyle(Ink.secondary)
        Spacer()
      }

      playbackControls
    }
    .padding(OmiSpacing.lg)
    .frame(maxWidth: .infinity, alignment: .leading)
    .background(
      RoundedRectangle(cornerRadius: OmiChrome.smallControlRadius, style: .continuous)
        .fill(Ink.rowFillHover.opacity(0.45))
    )
    .accessibilityIdentifier("conversation-detail-capture-playback")
  }

  @ViewBuilder
  private var playbackControls: some View {
    if playback.isResolving {
      HStack(spacing: OmiSpacing.sm) {
        ProgressView()
        Text("Preparing audio")
          .scaledFont(size: OmiType.body)
          .foregroundStyle(Ink.secondary)
      }
      .accessibilityLabel("Preparing capture audio")
    } else if let resolution = playback.resolution {
      VStack(alignment: .leading, spacing: OmiSpacing.sm) {
        HStack(spacing: OmiSpacing.md) {
          switch resolution {
          case .readyAggregate, .fileFallback:
            Button {
              playback.playOrPause()
            } label: {
              Label(
                playback.isPlaybackRequested ? "Pause" : "Play audio",
                systemImage: playback.isPlaybackRequested ? "pause.fill" : "play.fill"
              )
            }
            .buttonStyle(.bordered)
            .accessibilityLabel(playback.isPlaybackRequested ? "Pause capture audio" : "Play capture audio")
            .accessibilityIdentifier("chat-first-capture-play")
          case .pending, .locked, .unavailable, .noAudio:
            Button("Check audio", action: onRefresh)
              .buttonStyle(.bordered)
              .disabled(capture.isLocked)
              .accessibilityLabel("Check capture audio")
              .accessibilityIdentifier("chat-first-capture-check-audio-\(capture.id)")
          }

          Text(resolution.userFacingMessage)
            .scaledFont(size: OmiType.caption)
            .foregroundStyle(Ink.secondary)
        }

        if playback.duration > 0 {
          HStack(spacing: OmiSpacing.sm) {
            CapturePlaybackScrubber(playback: playback)
            // Counted on the capture's clock, the same one the transcript
            // timestamps use, so the transport and the bubbles agree.
            Text(
              "\(Self.playbackTimestamp(Self.wallPosition(playback, resolution))) / \(Self.playbackTimestamp(Self.wallEnd(playback, resolution)))"
            )
            .scaledFont(size: OmiType.caption, weight: .medium)
            .foregroundStyle(Ink.secondary)
            .monospacedDigit()
            .accessibilityLabel("Capture position \(Self.playbackTimestamp(Self.wallPosition(playback, resolution)))")
          }
        }

        if playback.isBuffering {
          Label("Buffering audio…", systemImage: "circle.dotted")
            .scaledFont(size: OmiType.caption)
            .foregroundStyle(Ink.secondary)
        } else if playback.isPlaying {
          Label("Playing", systemImage: "speaker.wave.2.fill")
            .scaledFont(size: OmiType.caption)
            .foregroundStyle(Ink.secondary)
        }

        resyncStatus

        if let playbackError = playback.playbackError {
          HStack(spacing: OmiSpacing.sm) {
            Label(playbackError, systemImage: "exclamationmark.triangle")
              .scaledFont(size: OmiType.caption)
              .foregroundStyle(Ink.errorRed)
            Button("Refresh", action: onRefresh)
              .buttonStyle(.link)
          }
        }
      }
    } else {
      Button("Prepare audio", action: onPrepare)
        .buttonStyle(.bordered)
        .accessibilityLabel("Prepare capture audio")
        .accessibilityIdentifier("chat-first-capture-prepare-audio")
    }
  }

  /// Progress and outcome of the on-device transcript sync started from the
  /// transcript header's refresh button.
  @ViewBuilder
  private var resyncStatus: some View {
    switch resync.phase {
    case .idle:
      EmptyView()
    case .downloading:
      resyncLine("Downloading audio to sync the transcript…", systemImage: "arrow.down.circle")
    case .preparingModel:
      resyncLine("Preparing the on-device speech model (first time only)…", systemImage: "cpu")
    case .listening:
      resyncLine("Listening to the audio on this Mac to sync the transcript…", systemImage: "ear")
    case .aligning:
      resyncLine("Aligning sentences to the audio…", systemImage: "text.line.first.and.arrowtriangle.forward")
    case .synced(let report):
      resyncLine(Self.syncedSummary(report), systemImage: "checkmark.circle")
        .accessibilityIdentifier("chat-first-capture-resync-done")
    case .failed(let message):
      Label(message, systemImage: "exclamationmark.triangle")
        .scaledFont(size: OmiType.caption)
        .foregroundStyle(Ink.errorRed)
        .accessibilityIdentifier("chat-first-capture-resync-failed")
    }
  }

  private func resyncLine(_ text: String, systemImage: String) -> some View {
    Label(text, systemImage: systemImage)
      .scaledFont(size: OmiType.caption)
      .foregroundStyle(Ink.secondary)
      .accessibilityLabel(text)
  }

  static func syncedSummary(_ report: CaptureTranscriptSyncReport) -> String {
    func signed(_ seconds: TimeInterval) -> String {
      let rounded = Int(seconds.rounded())
      return rounded >= 0 ? "+\(rounded) s" : "\(rounded) s"
    }
    let shift =
      abs(report.shiftAtStart - report.shiftAtEnd) < 1
      ? "shifted \(signed(report.shiftAtStart))"
      : "shifted \(signed(report.shiftAtStart)) to \(signed(report.shiftAtEnd))"
    return
      "Transcript synced to the audio (\(shift), \(report.matchedSegments) of \(report.alignableSegments) sentences matched)"
  }

  private static func wallPosition(
    _ playback: CapturePlaybackController, _ resolution: CapturePlaybackResolution
  ) -> TimeInterval {
    if let wall = CaptureTranscriptFollowPolicy.wallOffset(
      forPlaybackOffset: playback.currentTime, resolution: resolution)
    {
      return wall
    }
    // Spans are half-open, so the exact end of the media maps to nothing; the
    // counter should rest on the capture's end rather than jump clocks.
    return playback.currentTime >= playback.duration - 0.01 ? wallEnd(playback, resolution) : playback.currentTime
  }

  private static func wallEnd(
    _ playback: CapturePlaybackController, _ resolution: CapturePlaybackResolution
  ) -> TimeInterval {
    CaptureTranscriptFollowPolicy.wallDuration(resolution: resolution) ?? playback.duration
  }

  private static func playbackTimestamp(_ offset: TimeInterval) -> String {
    let totalSeconds = max(0, Int(offset))
    return String(format: "%02d:%02d", totalSeconds / 60, totalSeconds % 60)
  }
}

/// Draggable transport position. Drawn with named tokens rather than a system
/// `Slider` so the fill never picks up the machine's accent hue (INV-UI-1) and
/// it sits on the glass like the rest of the page chrome.
private struct CapturePlaybackScrubber: View {
  @ObservedObject var playback: CapturePlaybackController

  private static let trackHeight: CGFloat = 4
  private static let thumbDiameter: CGFloat = 12
  private static let hitHeight: CGFloat = 20
  private static let keyboardStep: TimeInterval = 5

  var body: some View {
    GeometryReader { geometry in
      let width = geometry.size.width
      let progress = CapturePlaybackScrubPolicy.progress(
        currentTime: playback.currentTime, duration: playback.duration)
      let thumbCenter = width * progress

      ZStack(alignment: .leading) {
        Capsule()
          .fill(Ink.rowFillHover)
          .frame(height: Self.trackHeight)
        Capsule()
          .fill(Ink.accent)
          .frame(width: max(0, thumbCenter), height: Self.trackHeight)
        Circle()
          .fill(Ink.accent)
          .frame(width: Self.thumbDiameter, height: Self.thumbDiameter)
          .scaleEffect(playback.isScrubbing ? 1.25 : 1)
          .offset(x: thumbCenter - Self.thumbDiameter / 2)
      }
      .frame(width: width, height: Self.hitHeight)
      .contentShape(Rectangle())
      .gesture(
        DragGesture(minimumDistance: 0)
          .onChanged { value in
            playback.scrub(toPlaybackOffset: offset(forLocationX: value.location.x, width: width))
          }
          .onEnded { value in
            let target = offset(forLocationX: value.location.x, width: width)
            Task { await playback.endScrubbing(atPlaybackOffset: target) }
          }
      )
    }
    .frame(height: Self.hitHeight)
    .accessibilityElement(children: .ignore)
    .accessibilityLabel("Capture playback position")
    .accessibilityValue(Self.accessibilityTimestamp(playback.currentTime))
    .accessibilityAdjustableAction { direction in
      let delta = direction == .increment ? Self.keyboardStep : -Self.keyboardStep
      let target = playback.currentTime + delta
      Task { await playback.seek(toPlaybackOffset: target) }
    }
    .accessibilityIdentifier("chat-first-capture-scrubber")
  }

  private func offset(forLocationX x: CGFloat, width: CGFloat) -> TimeInterval {
    CapturePlaybackScrubPolicy.playbackOffset(forLocationX: x, width: width, duration: playback.duration)
  }

  private static func accessibilityTimestamp(_ offset: TimeInterval) -> String {
    let totalSeconds = max(0, Int(offset))
    return "\(totalSeconds / 60) minutes \(totalSeconds % 60) seconds"
  }
}
