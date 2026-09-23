import OmiTheme
import SwiftUI

// MARK: - Source vocabulary

extension ConversationSource {
  /// The device name a person recognises, shared by the list badge and the detail header.
  var captureLabel: String {
    switch self {
    case .desktop: return "Desktop"
    case .omi: return "omi"
    case .phone: return "Phone"
    case .appleWatch: return "Apple Watch"
    case .workflow: return "Workflow"
    case .screenpipe: return "Screenpipe"
    case .friend, .friendCom: return "Friend"
    case .openglass: return "OpenGlass"
    case .frame: return "Frame"
    case .bee: return "Bee"
    case .limitless: return "Limitless"
    case .plaud: return "Plaud"
    default: return "Unknown"
    }
  }

  var captureSymbol: String {
    switch self {
    case .desktop: return "desktopcomputer"
    case .omi, .friend, .friendCom, .limitless, .plaud, .bee: return "dot.radiowaves.left.and.right"
    case .phone: return "iphone"
    case .appleWatch: return "applewatch"
    default: return "mic"
    }
  }
}

// MARK: - Recordings of one event

/// One device's recording of the event the open conversation belongs to.
struct CaptureGroupRecording: Identifiable, Equatable {
  let id: String
  let source: ConversationSource
  let startedAt: Date?
  let finishedAt: Date?
  /// The recording whose detail is on screen.
  let isCurrent: Bool
}

extension CaptureGroupPresentation {
  /// The recordings to list on `conversation`'s detail, in the order they started.
  ///
  /// Empty unless the event has another recording: a group of one is just a conversation, and
  /// its device is already in the header. Built from the server's membership rather than from
  /// the loaded list, so a member the list has not paged in is still listed.
  static func recordings(of conversation: ServerConversation) -> [CaptureGroupRecording] {
    guard let group = conversation.captureGroup else { return [] }
    var seen: Set<String> = []
    var recordings: [CaptureGroupRecording] = []
    for member in group.members where seen.insert(member.id).inserted {
      recordings.append(
        CaptureGroupRecording(
          id: member.id, source: member.source, startedAt: member.startedAt, finishedAt: member.finishedAt,
          isCurrent: member.id == conversation.id))
    }
    // A membership that has not caught up with this conversation still lists it.
    if !seen.contains(conversation.id) {
      recordings.append(
        CaptureGroupRecording(
          id: conversation.id, source: conversation.source ?? .unknown, startedAt: conversation.startedAt,
          finishedAt: conversation.finishedAt, isCurrent: true))
    }
    guard recordings.count > 1 else { return [] }
    return recordings.sorted { lhs, rhs in
      switch (lhs.startedAt, rhs.startedAt) {
      case (let l?, let r?) where l != r: return l < r
      case (nil, _?): return false
      case (_?, nil): return true
      default: return lhs.id < rhs.id
      }
    }
  }

  /// "12:58 – 2:00 PM", or the start alone when the recording has no end.
  static func timeWindow(
    of recording: CaptureGroupRecording,
    locale: Locale = .current,
    timeZone: TimeZone = .current
  ) -> String? {
    guard let start = recording.startedAt else { return nil }
    guard let end = recording.finishedAt, end > start else {
      let formatter = DateFormatter()
      formatter.locale = locale
      formatter.timeZone = timeZone
      formatter.dateStyle = .none
      formatter.timeStyle = .short
      return formatter.string(from: start)
    }
    let formatter = DateIntervalFormatter()
    formatter.locale = locale
    formatter.timeZone = timeZone
    formatter.dateStyle = .none
    formatter.timeStyle = .short
    return formatter.string(from: start, to: end)
  }

  static func label(of recording: CaptureGroupRecording, locale: Locale = .current, timeZone: TimeZone = .current)
    -> String
  {
    let source = recording.source.captureLabel
    guard let window = timeWindow(of: recording, locale: locale, timeZone: timeZone) else { return source }
    return "\(source) · \(window)"
  }

  /// Opens a member by id: the loaded row when the list has it, otherwise a fetch.
  @MainActor
  static func resolveMember(
    id: String,
    loaded: [ServerConversation],
    fetch: (String) async -> ServerConversation?
  ) async -> ServerConversation? {
    if let row = loaded.first(where: { $0.id == id }) { return row }
    return await fetch(id)
  }
}

extension Notification.Name {
  /// Automation: open or separate a recording through the open detail's own handlers
  /// (`conversation_detail_recording`), the same calls its chips and confirmation make.
  static let desktopAutomationConversationRecordingRequested = Notification.Name(
    "desktopAutomationConversationRecordingRequested")
}

// MARK: - Separation

/// One separation at a time, with the outcome the header shows. Separation is sticky on the
/// server, so the page confirms first and reloads only after the server accepted it.
@MainActor
final class CaptureGroupSeparationController: ObservableObject {
  enum Phase: Equatable {
    case idle
    case separating(recordingID: String)
    case failed(recordingID: String)
  }

  @Published private(set) var phase: Phase = .idle
  private let separateOnServer: (String) async -> Bool

  init(separate: @escaping (String) async -> Bool) {
    separateOnServer = separate
  }

  var isBusy: Bool {
    if case .separating = phase { return true }
    return false
  }

  /// Separates `recordingID`, then runs `reload` so the detail and list show the new membership.
  @discardableResult
  func separate(recordingID: String, reload: () async -> Void) async -> Bool {
    guard !isBusy else { return false }
    phase = .separating(recordingID: recordingID)
    guard await separateOnServer(recordingID) else {
      phase = .failed(recordingID: recordingID)
      return false
    }
    await reload()
    phase = .idle
    return true
  }

  func reset() {
    guard !isBusy else { return }
    phase = .idle
  }
}

// MARK: - Header strip

/// "Recorded on" row in the conversation header: one chip per device that recorded the event.
/// Clicking another device's chip opens its recording; separating lives one level down, in a
/// quiet menu at the end of the row and in each chip's context menu, behind a confirmation.
struct ConversationCaptureRecordingsStrip: View {
  let recordings: [CaptureGroupRecording]
  let phase: CaptureGroupSeparationController.Phase
  let onOpen: (CaptureGroupRecording) -> Void
  let onSeparate: (CaptureGroupRecording) -> Void

  @State private var pendingSeparation: CaptureGroupRecording?

  var body: some View {
    HStack(spacing: OmiSpacing.xs) {
      Text("Recorded on")
        .scaledFont(size: OmiType.caption)
        .foregroundColor(Ink.secondary)
        .fixedSize()

      ForEach(recordings) { recording in
        chip(recording)
      }

      separateMenu

      if case .failed = phase {
        Label("Couldn’t separate. Try again.", systemImage: "exclamationmark.circle")
          .scaledFont(size: OmiType.caption)
          .foregroundColor(PageGlass.warning)
          .lineLimit(1)
      }
    }
    .accessibilityElement(children: .contain)
    .accessibilityIdentifier("conversation-detail-recordings")
    .alert(
      "Separate this recording?",
      isPresented: Binding(get: { pendingSeparation != nil }, set: { if !$0 { pendingSeparation = nil } }),
      presenting: pendingSeparation
    ) { recording in
      Button("Cancel", role: .cancel) {}
      Button("Separate") { onSeparate(recording) }
    } message: { recording in
      Text(
        "\(CaptureGroupPresentation.label(of: recording)) will show as its own conversation and won’t be grouped with this event again."
      )
    }
  }

  @ViewBuilder
  private func chip(_ recording: CaptureGroupRecording) -> some View {
    let isSeparating = phase == .separating(recordingID: recording.id)
    let label = HStack(spacing: OmiSpacing.xxs) {
      if isSeparating {
        ProgressView().controlSize(.mini)
      } else {
        Image(systemName: recording.source.captureSymbol)
          .scaledFont(size: OmiType.micro, weight: .medium)
      }
      Text(recording.source.captureLabel)
        .scaledFont(size: OmiType.caption, weight: recording.isCurrent ? .semibold : .medium)
      if let window = CaptureGroupPresentation.timeWindow(of: recording) {
        Text(window)
          .scaledFont(size: OmiType.caption)
          .monospacedDigit()
      }
    }
    .foregroundColor(recording.isCurrent ? Ink.primary : Ink.secondary)
    .lineLimit(1)
    .fixedSize()
    .padding(.horizontal, OmiSpacing.sm)
    .frame(height: 22)
    .glassChip(isActive: recording.isCurrent)

    if recording.isCurrent {
      label
        .help("You’re viewing this recording")
        .accessibilityLabel("\(CaptureGroupPresentation.label(of: recording)), current recording")
        .contextMenu { separateButton(recording) }
    } else {
      Button {
        onOpen(recording)
      } label: {
        label
      }
      .buttonStyle(.plain)
      .help("Open the \(recording.source.captureLabel) recording")
      .accessibilityLabel("Open \(CaptureGroupPresentation.label(of: recording)) recording")
      .accessibilityIdentifier("conversation-detail-recording-\(recording.id)")
      .contextMenu {
        Button("Open Recording") { onOpen(recording) }
        separateButton(recording)
      }
      .disabled(isSeparating)
    }
  }

  private func separateButton(_ recording: CaptureGroupRecording) -> some View {
    Button(recording.isCurrent ? "Separate This Recording…" : "Separate Recording…") {
      pendingSeparation = recording
    }
    .disabled(phase.isSeparating)
  }

  private var separateMenu: some View {
    Menu {
      ForEach(recordings) { recording in
        Button(
          recording.isCurrent
            ? "This recording (\(CaptureGroupPresentation.label(of: recording)))"
            : CaptureGroupPresentation.label(of: recording)
        ) {
          pendingSeparation = recording
        }
      }
    } label: {
      Text("Separate…")
        .scaledFont(size: OmiType.caption)
        .foregroundColor(Ink.secondary)
    }
    .menuStyle(.button)
    .buttonStyle(.plain)
    .menuIndicator(.hidden)
    .fixedSize()
    .disabled(phase.isSeparating)
    .help("Split a recording out of this event")
    .accessibilityIdentifier("conversation-detail-recordings-separate")
  }
}

extension CaptureGroupSeparationController.Phase {
  fileprivate var isSeparating: Bool {
    if case .separating = self { return true }
    return false
  }
}
