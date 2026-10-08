import OmiTheme
import SwiftUI

/// Copy and control set for one approval card, kept out of the view so the
/// words a reader sees can be asserted without a window server.
struct DesktopToolApprovalCardPresentation: Equatable {
  struct Action: Equatable, Identifiable {
    let answer: DesktopToolApprovalAnswer
    let title: String
    var id: String { answer.rawValue }
  }

  let headline: String
  let question: String
  /// "To" for a send, "Script" for AppleScript, nil for the list tools.
  let targetLabel: String?
  let target: String?
  let preview: [DesktopToolApprovalRequest.PreviewField]
  /// What "Allow for This Chat" would also allow, in the runtime's words.
  let sessionGrantNote: String?
  let actions: [Action]
  /// One line under the controls: the open deadline, or the final outcome.
  let status: String
  let isFinal: Bool
  let isAnswering: Bool
  let error: String?

  static let allowOnceTitle = "Allow Once"
  static let allowForChatTitle = "Allow for This Chat (1 h)"
  static let denyTitle = "Deny"

  init(approval: DesktopToolApproval, now: Date = Date()) {
    let request = approval.request
    headline = request.title
    question = request.decisionPrompt
    switch request.toolName {
    case "send_message":
      targetLabel = "To"
    case "run_applescript":
      targetLabel = "Script"
    case "read_message_history":
      targetLabel = "Conversation"
    default:
      targetLabel = nil
    }
    let targetValue = targetLabel == nil ? nil : request.displayResourceRef
    target = targetValue
    // The target line already shows the resource; do not print the field that
    // carries it twice. A field with a different value stays: a thread read by
    // chat id still shows the handle it was given.
    preview = request.preview.filter { targetValue == nil || $0.value != targetValue }
    sessionGrantNote = request.sessionGrantOption?.covers.map { "Also allows \($0) for the next hour" }
    isAnswering = approval.state.isAnswering
    let overdue = approval.state == .pending && request.expiresAt <= now
    isFinal = !approval.state.isPending || overdue
    error = approval.lastError
    if approval.state.isPending, !overdue {
      var pendingActions = [Action(answer: .allowOnce, title: Self.allowOnceTitle)]
      if request.offersSessionGrant {
        pendingActions.append(Action(answer: .allowForSession, title: Self.allowForChatTitle))
      }
      pendingActions.append(Action(answer: .deny, title: Self.denyTitle))
      actions = pendingActions
    } else {
      actions = []
    }
    status = Self.statusLine(approval: approval, now: now)
  }

  static func statusLine(approval: DesktopToolApproval, now: Date) -> String {
    let request = approval.request
    switch approval.state {
    case .pending:
      return request.expiresAt <= now
        ? "Expired, not run"
        : "Waits until \(OmiDateFormat.time(request.expiresAt)), then stops without running"
    case .answering(let answer):
      switch answer {
      case .allowOnce, .allowForSession: return "Allowing…"
      case .deny: return "Denying…"
      }
    case .allowed(let selectedOptionId, _):
      if selectedOptionId == DesktopToolApprovalAnswer.allowForSession.rawValue {
        let until = (approval.resolvedAt ?? now).addingTimeInterval(DesktopToolApprovalAnswer.sessionGrantDuration)
        return "Allowed for this chat until \(OmiDateFormat.time(until))"
      }
      return "Allowed once"
    case .denied:
      return "Denied, not run"
    case .expired:
      return "Expired, not run"
    case .cancelled:
      return "Cancelled, not run"
    }
  }
}

/// The card a sensitive device tool call shows while it waits for the user:
/// what will run, the exact target, the content, and the three answers. It is
/// a projection of a kernel dispatch; pressing a button sends one
/// `resolve_desktop_dispatch` through signed direct control, and the kernel's
/// `approval_resolved` is what makes the card final.
struct DesktopToolApprovalCard: View {
  let approval: DesktopToolApproval
  let onAnswer: (DesktopToolApprovalAnswer) -> Void

  private var presentation: DesktopToolApprovalCardPresentation {
    DesktopToolApprovalCardPresentation(approval: approval)
  }

  var body: some View {
    let presentation = presentation
    VStack(alignment: .leading, spacing: OmiSpacing.sm) {
      Label(presentation.headline, systemImage: "hand.raised")
        .scaledFont(size: OmiType.caption, weight: .semibold)
        .foregroundStyle(Ink.secondary)

      Text(presentation.question)
        .scaledFont(size: OmiType.body, weight: .medium)
        .foregroundStyle(Ink.primary)
        .fixedSize(horizontal: false, vertical: true)

      if let targetLabel = presentation.targetLabel, let target = presentation.target {
        detailRow(label: targetLabel, value: target, monospaced: true)
      }
      ForEach(presentation.preview, id: \.key) { field in
        detailRow(label: fieldLabel(field.key), value: field.value)
      }

      if !presentation.actions.isEmpty {
        HStack(spacing: OmiSpacing.sm) {
          ForEach(presentation.actions) { action in
            Button(action.title) { onAnswer(action.answer) }
              .buttonStyle(OmiButtonStyle(action.answer == .allowOnce ? .primary : .secondary, size: .compact))
              .disabled(presentation.isAnswering)
              .accessibilityIdentifier("tool-approval-\(approval.id)-\(action.answer.rawValue)")
          }
          if presentation.isAnswering {
            ProgressView().controlSize(.small)
          }
        }
        .padding(.top, OmiSpacing.xxs)
        if let note = presentation.sessionGrantNote {
          Text(note)
            .scaledFont(size: OmiType.caption)
            .foregroundStyle(Ink.secondary)
            .fixedSize(horizontal: false, vertical: true)
        }
      }

      HStack(spacing: OmiSpacing.sm) {
        Text(presentation.status)
          .scaledFont(size: OmiType.caption)
          .foregroundStyle(Ink.secondary)
          .accessibilityIdentifier("tool-approval-\(approval.id)-status")
        if let error = presentation.error {
          Text(error)
            .scaledFont(size: OmiType.caption)
            .foregroundStyle(Ink.errorRed)
            .fixedSize(horizontal: false, vertical: true)
        }
      }
    }
    .padding(.horizontal, OmiSpacing.md)
    .padding(.vertical, OmiSpacing.sm)
    .frame(maxWidth: .infinity, alignment: .leading)
    .background(Ink.rowFill)
    .clipShape(RoundedRectangle(cornerRadius: PageGlass.rowRadius, style: .continuous))
    .overlay(
      RoundedRectangle(cornerRadius: PageGlass.rowRadius, style: .continuous)
        .stroke(Ink.glassEdge, lineWidth: 1)
    )
    .accessibilityElement(children: .contain)
    .accessibilityIdentifier("tool-approval-\(approval.id)")
  }

  @ViewBuilder
  /// A field of the request. The target (a recipient, a script) is drawn in a
  /// monospaced run so look-alike characters stand out; a value with line
  /// breaks is drawn as one ruled block so its lines cannot pose as other rows.
  private func detailRow(label: String, value: String, monospaced: Bool = false) -> some View {
    VStack(alignment: .leading, spacing: OmiSpacing.hairline) {
      Text(label)
        .scaledFont(size: OmiType.micro, weight: .semibold)
        .foregroundStyle(Ink.secondary)
        .textCase(.uppercase)
      Group {
        if monospaced {
          Text(value).scaledFont(size: OmiType.body, design: .monospaced)
        } else {
          Text(value).scaledFont(size: OmiType.body)
        }
      }
      .foregroundStyle(Ink.primary)
      .textSelection(.enabled)
      .fixedSize(horizontal: false, vertical: true)
      .padding(.leading, value.contains("\n") ? OmiSpacing.sm : 0)
      .overlay(alignment: .leading) {
        if value.contains("\n") {
          Rectangle().fill(Ink.glassEdge).frame(width: 1)
        }
      }
    }
  }

  private func fieldLabel(_ key: String) -> String {
    switch key {
    case "text": return "Message"
    case "service": return "Service"
    case "file_path": return "Attachment"
    case "timeout_seconds": return "Timeout (seconds)"
    case "limit": return "Limit"
    default: return key.replacingOccurrences(of: "_", with: " ").capitalized
    }
  }
}

/// The approval cards that belong in one chat thread: every card whose
/// kernel session is the one this surface is bound to. The store is the
/// source; this view only chooses which cards a surface shows.
struct DesktopToolApprovalCardList: View {
  let surface: AgentSurfaceReference?
  @ObservedObject private var approvals: DesktopToolApprovalStore = .shared
  @ObservedObject private var runtimeStatus: AgentRuntimeStatusStore = .shared

  var body: some View {
    let cards = visibleApprovals
    if !cards.isEmpty {
      VStack(alignment: .leading, spacing: OmiSpacing.sm) {
        ForEach(cards) { approval in
          DesktopToolApprovalCard(approval: approval) { answer in
            Task { @MainActor in
              await approvals.answer(approvalId: approval.id, with: answer)
            }
          }
        }
      }
    }
  }

  private var visibleApprovals: [DesktopToolApproval] {
    guard let surface else { return [] }
    return approvals.approvals(forSessionId: runtimeStatus.sessionIdBySurface[surface.key])
  }
}
