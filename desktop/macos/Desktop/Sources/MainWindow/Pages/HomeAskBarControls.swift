import OmiTheme
import SwiftUI

/// What the Home ask bar puts in its trailing slot, as a decision rather than a
/// chain of `if`s inside the view.
///
/// Home's ask bar is the app's primary composer, and it shipped without two of
/// the three controls the other composers carry: there was no microphone at all,
/// and Send existed only once you had already typed. Everything before the first
/// keystroke — the state a composer spends most of its life in — rendered as a
/// paperclip and a Connect chip, which is a chat box with no visible way to chat.
///
/// Stating it as a value is what makes "Send is always on screen" testable
/// without a screenshot: the old rule had a fourth branch that resolved to
/// `EmptyView()`, and an empty branch is invisible to every check except the eye.
enum HomeAskBarPrimaryAction: Equatable {
  /// Send. `isArmed` is only whether there is anything to send yet — the disc
  /// stays mounted either way, because a send button that appears on the first
  /// keystroke is one nobody can find before it.
  case send(isArmed: Bool)
  /// Stop, while a turn is in flight. Same slot and same weight as Send: a
  /// primary that thins out the moment it becomes the only control is a button
  /// that disappears exactly when it starts to matter.
  case stop(isStopping: Bool)
}

/// The Home ask bar's trailing cluster, resolved from composer state.
struct HomeAskBarControls: Equatable {
  let primary: HomeAskBarPrimaryAction
  /// Home's own Connect entry point, which no other composer has. It yields the
  /// slot as soon as the bar is engaged — a draft in flight, text typed, or the
  /// field focused — so Send is never competing with a second filled capsule for
  /// the same corner.
  let showsConnect: Bool

  static func resolve(
    isSending: Bool,
    isStopping: Bool,
    hasText: Bool,
    isFocused: Bool
  ) -> HomeAskBarControls {
    if isSending {
      return HomeAskBarControls(primary: .stop(isStopping: isStopping), showsConnect: false)
    }
    return HomeAskBarControls(primary: .send(isArmed: hasText), showsConnect: !hasText && !isFocused)
  }
}

/// The Home ask bar's trailing controls: Connect while the bar is at rest, then
/// the primary Send / Stop disc.
///
/// The microphone is deliberately *not* here — it joins the leading cluster next
/// to the paperclip, which is where `ChatInputView` already puts it. Both live in
/// the main window and should read as one control vocabulary; the floating bar's
/// composer has no leading cluster to join, so its mic sits beside Send instead.
struct HomeAskBarTrailingControls: View {
  let controls: HomeAskBarControls
  let isConnectActive: Bool
  let onSend: () -> Void
  let onStop: () -> Void
  let onConnect: () -> Void

  var body: some View {
    HStack(spacing: OmiSpacing.xs) {
      if controls.showsConnect {
        HomeAskBarConnectButton(isActive: isConnectActive, action: onConnect)
      }

      switch controls.primary {
      case .send(let isArmed):
        sendButton(isArmed: isArmed)
      case .stop(let isStopping):
        stopButton(isStopping: isStopping)
      }
    }
  }

  private func sendButton(isArmed: Bool) -> some View {
    Button(action: onSend) {
      ZStack {
        // Unarmed is the same wash Connect-at-rest uses rather than a dimmed
        // copy of the filled disc: on light glass a low-alpha ink circle is the
        // panel's own colour, i.e. the invisible-control bug in a new place.
        Circle()
          .fill(isArmed ? HomeAskBarPalette.primaryFill : HomeAskBarPalette.secondaryFill(isHovering: false))

        Image(systemName: "arrow.up")
          .scaledFont(size: OmiType.body, weight: .bold)
          .foregroundStyle(isArmed ? HomeAskBarPalette.primaryLabel : HomeAskBarPalette.secondaryLabel)
      }
      .frame(width: 34, height: 34)
      .contentShape(Circle())
    }
    .buttonStyle(.plain)
    .disabled(!isArmed)
    .help("Send")
    .accessibilityLabel("Send message")
  }

  private func stopButton(isStopping: Bool) -> some View {
    Button(action: onStop) {
      ZStack {
        Circle()
          .fill(HomeAskBarPalette.primaryFill)

        if isStopping {
          ProgressView()
            .controlSize(.small)
            .scaleEffect(0.6)
        } else {
          Image(systemName: "square.fill")
            .scaledFont(size: OmiType.micro, weight: .bold)
            .foregroundStyle(HomeAskBarPalette.primaryLabel)
        }
      }
      .frame(width: 34, height: 34)
      .contentShape(Circle())
    }
    .buttonStyle(.plain)
    .disabled(isStopping)
    .help("Stop")
    .accessibilityLabel("Stop response")
  }
}

struct HomeAskBarConnectButton: View {
  let isActive: Bool
  let action: () -> Void

  @State private var isHovering = false

  var body: some View {
    Button(action: action) {
      HStack(spacing: OmiSpacing.xs) {
        Image(systemName: "link")
          .scaledFont(size: OmiType.caption, weight: .semibold)

        Text("Connect")
          .scaledFont(size: OmiType.caption, weight: .semibold)
      }
      .foregroundStyle(isActive ? HomeAskBarPalette.primaryLabel : HomeAskBarPalette.secondaryLabel)
      .padding(.horizontal, OmiSpacing.md)
      .frame(height: 34)
      .background(
        Capsule(style: .continuous)
          .fill(
            isActive
              ? HomeAskBarPalette.primaryFill
              : HomeAskBarPalette.secondaryFill(isHovering: isHovering))
      )
      .overlay(
        Capsule(style: .continuous)
          .stroke(isActive ? Color.clear : HomePalette.hairline, lineWidth: 1)
      )
      .contentShape(Capsule())
    }
    .buttonStyle(.plain)
    .onHover { isHovering = $0 }
    .help("Connect data & use omi anywhere")
    .accessibilityLabel(isActive ? "Close connect" : "Connect")
  }
}
