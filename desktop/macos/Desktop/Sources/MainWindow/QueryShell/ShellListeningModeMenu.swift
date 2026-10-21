//
//  ShellListeningModeMenu.swift — what the top bar's microphone opens.
//
//  The mic used to cycle Off → Always On → Only Meetings on each click, with no menu and no
//  confirmation, so one stray click could turn on always-on room recording. A control that changes
//  what Omi records names the choices instead (ux-contract §2): this popover lists the three modes,
//  marks the current one, says under each what it records, and links to Settings → Transcription.
//
//  Keyboard: the popover takes focus when it opens; ↑/↓ move the highlight, Return or Space choose,
//  Esc closes. Every row is a real `Button`, so VoiceOver reaches and activates each one directly.
//
//  Brand: `Ink` semantics only (INV-UI-1).
//

import OmiTheme
import SwiftUI

/// One row of the listening menu, in display order.
enum ShellListeningMenuItem: Hashable {
  case mode(AssistantSettings.AudioRecordingMode)
  case audioSettings

  /// Off, Always On, Only Meetings, then the settings link below a divider. Declared here, not in
  /// the view, so the keyboard model and the view walk the same list.
  static let all: [ShellListeningMenuItem] =
    [.mode(.off), .mode(.always), .mode(.onlyMeetings), .audioSettings]

  var title: String {
    switch self {
    case .mode(let mode): return CaptureListeningLogic.audioRecordingModeTitle(mode)
    case .audioSettings: return "Audio Settings…"
    }
  }

  /// The line under a mode saying what it records. Sentence case, no trailing period (§8).
  var detail: String? {
    switch self {
    case .mode(.off): return "Nothing is recorded"
    case .mode(.always): return "Records everything your microphone hears"
    case .mode(.onlyMeetings): return "Records only while you are on a call"
    case .audioSettings: return nil
    }
  }

  /// The row the highlight starts on: the current mode, so Return on open changes nothing.
  static func initialHighlight(current: AssistantSettings.AudioRecordingMode) -> Int {
    all.firstIndex(of: .mode(current)) ?? 0
  }

  /// Arrow-key movement, wrapping at both ends as a system menu does.
  static func highlight(movingFrom index: Int, by delta: Int) -> Int {
    let count = all.count
    return ((index + delta) % count + count) % count
  }
}

struct ShellListeningModeMenu: View {
  let current: AssistantSettings.AudioRecordingMode
  let onSelect: (AssistantSettings.AudioRecordingMode) -> Void
  let onOpenSettings: () -> Void
  let onDismiss: () -> Void

  @State private var highlighted: Int
  @FocusState private var isFocused: Bool

  init(
    current: AssistantSettings.AudioRecordingMode,
    onSelect: @escaping (AssistantSettings.AudioRecordingMode) -> Void,
    onOpenSettings: @escaping () -> Void,
    onDismiss: @escaping () -> Void
  ) {
    self.current = current
    self.onSelect = onSelect
    self.onOpenSettings = onOpenSettings
    self.onDismiss = onDismiss
    _highlighted = State(initialValue: ShellListeningMenuItem.initialHighlight(current: current))
  }

  var body: some View {
    VStack(alignment: .leading, spacing: OmiSpacing.hairline) {
      ForEach(Array(ShellListeningMenuItem.all.enumerated()), id: \.element) { index, item in
        if item == .audioSettings {
          Divider().padding(.vertical, OmiSpacing.xxs)
        }
        row(item, at: index)
      }
    }
    .padding(OmiSpacing.xs)
    .frame(width: 280)
    .focusable()
    .focusEffectDisabled()
    .focused($isFocused)
    .onKeyPress(.upArrow) { move(by: -1) }
    .onKeyPress(.downArrow) { move(by: 1) }
    .onKeyPress(.return) { activateHighlighted() }
    .onKeyPress(.space) { activateHighlighted() }
    .onKeyPress(.escape) {
      onDismiss()
      return .handled
    }
    .onAppear { isFocused = true }
    .accessibilityElement(children: .contain)
    .accessibilityLabel("Audio recording")
  }

  private func row(_ item: ShellListeningMenuItem, at index: Int) -> some View {
    let isCurrent = item == .mode(current)
    return Button {
      activate(item)
    } label: {
      HStack(alignment: .firstTextBaseline, spacing: OmiSpacing.sm) {
        Image(systemName: "checkmark")
          .scaledFont(size: OmiType.caption, weight: .semibold)
          .opacity(isCurrent ? 1 : 0)
          .accessibilityHidden(true)
        VStack(alignment: .leading, spacing: OmiSpacing.hairline) {
          Text(item.title)
            .scaledFont(size: OmiType.body, weight: .medium)
            .foregroundStyle(Ink.primary)
          if let detail = item.detail {
            Text(detail)
              .scaledFont(size: OmiType.caption)
              .foregroundStyle(Ink.secondary)
          }
        }
        Spacer(minLength: 0)
      }
      .padding(.horizontal, OmiSpacing.sm)
      .padding(.vertical, OmiSpacing.xs)
      .background(
        RoundedRectangle(cornerRadius: OmiChrome.elementRadius, style: .continuous)
          .fill(highlighted == index ? Ink.rowFillHover : Color.clear)
      )
      .contentShape(Rectangle())
    }
    .buttonStyle(.plain)
    .onHover { hovering in
      if hovering { highlighted = index }
    }
    .accessibilityLabel(Text(item.title))
    .accessibilityHint(item.detail.map { Text($0) } ?? Text(""))
    .accessibilityAddTraits(isCurrent ? .isSelected : [])
    .accessibilityIdentifier(accessibilityIdentifier(for: item))
  }

  private func accessibilityIdentifier(for item: ShellListeningMenuItem) -> String {
    switch item {
    case .mode(let mode): return "shell-listening-mode-\(mode.rawValue)"
    case .audioSettings: return "shell-listening-audio-settings"
    }
  }

  private func move(by delta: Int) -> KeyPress.Result {
    highlighted = ShellListeningMenuItem.highlight(movingFrom: highlighted, by: delta)
    return .handled
  }

  private func activateHighlighted() -> KeyPress.Result {
    guard ShellListeningMenuItem.all.indices.contains(highlighted) else { return .ignored }
    activate(ShellListeningMenuItem.all[highlighted])
    return .handled
  }

  private func activate(_ item: ShellListeningMenuItem) {
    switch item {
    case .mode(let mode): onSelect(mode)
    case .audioSettings: onOpenSettings()
    }
  }
}
