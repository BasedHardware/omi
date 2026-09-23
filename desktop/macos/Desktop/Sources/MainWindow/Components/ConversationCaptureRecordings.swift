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

  /// The devices drawn in the header's stack: one per recording, in start order, at most three.
  static func stackSources(of recordings: [CaptureGroupRecording], limit: Int = 3) -> [ConversationSource] {
    Array(recordings.prefix(limit).map(\.source))
  }

  static func countLabel(_ count: Int) -> String {
    count == 1 ? "1 recording" : "\(count) recordings"
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

// MARK: - Header device stack

/// Where the device stack sits, so the recordings panel can hang from it without the header
/// having to make room for it.
struct CaptureRecordingsAnchorKey: PreferenceKey {
  static var defaultValue: Anchor<CGRect>? { nil }
  static func reduce(value: inout Anchor<CGRect>?, nextValue: () -> Anchor<CGRect>?) {
    value = value ?? nextValue()
  }
}

/// The end of the header's metadata line for an event more than one device recorded: the
/// devices as a small overlapping stack plus a count. It opens `CaptureRecordingsPanel`.
struct CaptureRecordingsStackButton: View {
  let recordings: [CaptureGroupRecording]
  let isOpen: Bool
  let onToggle: () -> Void

  var body: some View {
    Button(action: onToggle) {
      HStack(spacing: OmiSpacing.xs) {
        HStack(spacing: -5) {
          ForEach(Array(CaptureGroupPresentation.stackSources(of: recordings).enumerated()), id: \.offset) {
            index, source in
            Image(systemName: source.captureSymbol)
              .scaledFont(size: OmiType.caption, weight: .medium)
              .foregroundColor(Ink.primary)
              .frame(width: 20, height: 20)
              .background(Circle().fill(Ink.surface))
              .overlay(Circle().strokeBorder(Ink.separator, lineWidth: 1))
              .zIndex(Double(-index))
          }
        }
        Text(CaptureGroupPresentation.countLabel(recordings.count))
          .scaledFont(size: OmiType.caption, weight: .medium)
          .fixedSize()
        Image(systemName: "chevron.down")
          .scaledFont(size: OmiType.micro, weight: .semibold)
          .rotationEffect(.degrees(isOpen ? 180 : 0))
      }
      .foregroundColor(isOpen ? Ink.primary : Ink.secondary)
      .padding(.leading, OmiSpacing.hairline)
      .padding(.trailing, OmiSpacing.sm)
      .frame(height: 24)
      .glassChip(isActive: isOpen)
    }
    .buttonStyle(.plain)
    .anchorPreference(key: CaptureRecordingsAnchorKey.self, value: .bounds) { $0 }
    .help("Recorded by " + recordings.map(\.source.captureLabel).joined(separator: ", "))
    .accessibilityLabel("\(CaptureGroupPresentation.countLabel(recordings.count)) of this conversation")
    .accessibilityIdentifier("conversation-detail-recordings")
  }
}

/// Each recording of the event: device, time range, the one on screen checked. A row opens its
/// recording; Separate… splits it out behind the host's confirmation.
struct CaptureRecordingsPanel: View {
  static let width: CGFloat = 340

  let recordings: [CaptureGroupRecording]
  let phase: CaptureGroupSeparationController.Phase
  let onOpen: (CaptureGroupRecording) -> Void
  let onSeparate: (CaptureGroupRecording) -> Void

  var body: some View {
    VStack(alignment: .leading, spacing: 0) {
      Text("Recordings of this conversation")
        .scaledFont(size: OmiType.caption, weight: .semibold)
        .foregroundColor(Ink.secondary)
        .padding(.horizontal, OmiSpacing.md)
        .padding(.top, OmiSpacing.md)
        .padding(.bottom, OmiSpacing.xs)

      ForEach(Array(recordings.enumerated()), id: \.element.id) { index, recording in
        if index > 0 {
          GlassSeparator().padding(.leading, 40)
        }
        row(recording)
      }

      if case .failed = phase {
        Label("Couldn’t separate. Try again.", systemImage: "exclamationmark.circle")
          .scaledFont(size: OmiType.caption)
          .foregroundColor(PageGlass.warning)
          .padding(.horizontal, OmiSpacing.md)
          .padding(.top, OmiSpacing.xs)
      }
    }
    .padding(.bottom, OmiSpacing.xs)
    .frame(width: Self.width, alignment: .leading)
    .background(RoundedRectangle(cornerRadius: PageGlass.rowRadius, style: .continuous).fill(Ink.surface))
    .overlay(RoundedRectangle(cornerRadius: PageGlass.rowRadius, style: .continuous).strokeBorder(Ink.separator))
    .shadow(
      color: .black.opacity(Double(InkGlassShadow.ambient.opacity)), radius: InkGlassShadow.ambient.radius, y: 4
    )
    .accessibilityElement(children: .contain)
    .accessibilityIdentifier("conversation-detail-recordings-panel")
  }

  private func row(_ recording: CaptureGroupRecording) -> some View {
    let isSeparating = phase == .separating(recordingID: recording.id)
    return HStack(spacing: OmiSpacing.sm) {
      Button {
        onOpen(recording)
      } label: {
        HStack(spacing: OmiSpacing.sm) {
          Group {
            if isSeparating {
              ProgressView().controlSize(.small)
            } else {
              Image(systemName: recording.source.captureSymbol)
                .scaledFont(size: OmiType.body)
            }
          }
          .foregroundColor(Ink.secondary)
          .frame(width: 20)
          VStack(alignment: .leading, spacing: 0) {
            Text(recording.source.captureLabel)
              .scaledFont(size: OmiType.body, weight: recording.isCurrent ? .semibold : .medium)
              .foregroundColor(Ink.primary)
            if let window = CaptureGroupPresentation.timeWindow(of: recording) {
              Text(window)
                .scaledFont(size: OmiType.caption)
                .monospacedDigit()
                .foregroundColor(Ink.secondary)
            }
          }
          Spacer(minLength: OmiSpacing.sm)
          if recording.isCurrent {
            Image(systemName: "checkmark")
              .scaledFont(size: OmiType.caption, weight: .semibold)
              .foregroundColor(Ink.primary)
              .help("You’re viewing this recording")
          }
        }
        .contentShape(Rectangle())
      }
      .buttonStyle(.plain)
      // The open recording stays at full ink with its check; it is simply not a link.
      .allowsHitTesting(!recording.isCurrent && !isSeparating)
      .accessibilityLabel(
        recording.isCurrent
          ? "\(CaptureGroupPresentation.label(of: recording)), current recording"
          : "Open \(CaptureGroupPresentation.label(of: recording)) recording"
      )
      .accessibilityIdentifier("conversation-detail-recording-\(recording.id)")

      Button {
        onSeparate(recording)
      } label: {
        Text("Separate…")
          .scaledFont(size: OmiType.caption, weight: .medium)
          .foregroundColor(Ink.secondary)
          .padding(.horizontal, OmiSpacing.xs)
          .frame(height: 22)
          .contentShape(Rectangle())
      }
      .buttonStyle(.plain)
      .disabled(phase.isSeparating)
      .help("Show this recording as its own conversation")
      .accessibilityIdentifier("conversation-detail-recording-separate-\(recording.id)")
    }
    .padding(.horizontal, OmiSpacing.md)
    .padding(.vertical, OmiSpacing.sm)
  }
}

/// Hangs `CaptureRecordingsPanel` from the header's device stack and owns the separation
/// confirmation, so the page composes one modifier instead of three pieces of state.
struct CaptureRecordingsPanelHost: ViewModifier {
  @Binding var isOpen: Bool
  let recordings: [CaptureGroupRecording]
  let phase: CaptureGroupSeparationController.Phase
  let onOpen: (CaptureGroupRecording) -> Void
  let onSeparate: (CaptureGroupRecording) -> Void

  @State private var pendingSeparation: CaptureGroupRecording?

  func body(content: Content) -> some View {
    content
      .overlayPreferenceValue(CaptureRecordingsAnchorKey.self) { anchor in
        GeometryReader { proxy in
          if isOpen, let anchor, !recordings.isEmpty {
            let origin = proxy[anchor]
            ZStack(alignment: .topLeading) {
              // A click anywhere else closes the panel, like a menu.
              Color.clear
                .contentShape(Rectangle())
                .onTapGesture { isOpen = false }
              CaptureRecordingsPanel(
                recordings: recordings,
                phase: phase,
                onOpen: { recording in
                  isOpen = false
                  onOpen(recording)
                },
                onSeparate: { recording in
                  isOpen = false
                  pendingSeparation = recording
                }
              )
              .offset(
                x: max(0, min(origin.minX, proxy.size.width - CaptureRecordingsPanel.width - OmiSpacing.xxl)),
                y: origin.maxY + OmiSpacing.xs
              )
              .transition(.opacity)
            }
          }
        }
      }
      .onExitCommand { isOpen = false }
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
}

extension CaptureGroupSeparationController.Phase {
  fileprivate var isSeparating: Bool {
    if case .separating = self { return true }
    return false
  }
}
