import SwiftUI

/// AI Clone page — an AI-powered messaging assistant that learns to reply to your
/// contacts in your voice. Contacts are the user's real top iMessage correspondents
/// (ranked by message count), read locally via `IMessageReaderService`.
struct AIClonePage: View {
  private enum LoadState: Equatable {
    case loading
    case loaded
    case needsFullDiskAccess
    case empty
    case failed(String)
  }

  @State private var state: LoadState = .loading
  @State private var contacts: [IMessageContact] = []
  @State private var selectedHandles: Set<String> = []
  /// How many top contacts to auto-select. Defaults to 5; re-applied whenever changed.
  @State private var autoSelectCount = 5
  /// Bumped to force `.task` to re-run (e.g. after the user grants Full Disk Access).
  @State private var reloadToken = UUID()

  /// Generated personas keyed by contact handle (hydrated from disk on load).
  @State private var personas: [String: ContactPersona] = [:]
  /// Handles currently generating a persona (drives the per-row spinner).
  @State private var trainingHandles: Set<String> = []
  /// Last training error per handle, shown inline on that row.
  @State private var trainingErrors: [String: String] = [:]
  /// Non-nil while the "Preview Chat" sheet is open for a trained contact.
  @State private var chatTarget: AICloneChatTarget?
  /// Per-handle backtest UI state (progress while running, result when done).
  @State private var backtestStates: [String: AICloneBacktestUIState] = [:]
  /// Non-nil while the backtest-results detail sheet is open.
  @State private var backtestDetail: AICloneBacktestDetail?

  private var maxSelectable: Int { contacts.count }

  var body: some View {
    VStack(alignment: .leading, spacing: 24) {
      header

      content
    }
    .padding(28)
    .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
    .background(OmiColors.backgroundPrimary)
    .task(id: reloadToken) { await load() }
    .sheet(item: $chatTarget) { target in
      AIClonePreviewChatSheet(contact: target.contact, persona: target.persona)
    }
    .sheet(item: $backtestDetail) { detail in
      AICloneBacktestSheet(contact: detail.contact, result: detail.result)
    }
  }

  // MARK: - Header

  private var header: some View {
    VStack(alignment: .leading, spacing: 6) {
      Text("AI Clone")
        .scaledFont(size: 28, weight: .bold)
        .foregroundColor(OmiColors.textPrimary)

      Text("Your AI-powered messaging assistant")
        .scaledFont(size: 15, weight: .regular)
        .foregroundColor(OmiColors.textSecondary)
    }
  }

  // MARK: - Content (state machine)

  @ViewBuilder
  private var content: some View {
    switch state {
    case .loading:
      centered {
        ProgressView()
          .scaleEffect(1.2)
          .tint(.white)
        Text("Reading your Messages history…")
          .scaledFont(size: 14, weight: .regular)
          .foregroundColor(OmiColors.textTertiary)
      }

    case .needsFullDiskAccess:
      fullDiskAccessPrompt

    case .empty:
      centered {
        Image(systemName: "message")
          .font(.system(size: 34, weight: .regular))
          .foregroundColor(OmiColors.textQuaternary)
        Text("No conversations found")
          .scaledFont(size: 16, weight: .semibold)
          .foregroundColor(OmiColors.textPrimary)
        Text("Once you have direct message threads in Messages, your top contacts will appear here.")
          .scaledFont(size: 13, weight: .regular)
          .foregroundColor(OmiColors.textTertiary)
          .multilineTextAlignment(.center)
          .frame(maxWidth: 360)
      }

    case .failed(let message):
      centered {
        Image(systemName: "exclamationmark.triangle")
          .font(.system(size: 32, weight: .regular))
          .foregroundColor(OmiColors.warning)
        Text("Couldn't load contacts")
          .scaledFont(size: 16, weight: .semibold)
          .foregroundColor(OmiColors.textPrimary)
        Text(message)
          .scaledFont(size: 13, weight: .regular)
          .foregroundColor(OmiColors.textTertiary)
          .multilineTextAlignment(.center)
          .frame(maxWidth: 360)
        reloadButton(title: "Try Again")
      }

    case .loaded:
      loadedContent
    }
  }

  private var loadedContent: some View {
    VStack(alignment: .leading, spacing: 16) {
      autoSelectControl

      ScrollView {
        LazyVStack(spacing: 10) {
          ForEach(Array(contacts.enumerated()), id: \.element.id) { index, contact in
            AICloneContactRow(
              rank: index + 1,
              contact: contact,
              isSelected: selectedHandles.contains(contact.id),
              isTraining: trainingHandles.contains(contact.id),
              persona: personas[contact.id],
              errorMessage: trainingErrors[contact.id],
              backtest: backtestStates[contact.id],
              onToggle: { toggleSelection(contact) },
              onTrain: { train(contact) },
              onPreviewChat: {
                if let persona = personas[contact.id] {
                  chatTarget = AICloneChatTarget(contact: contact, persona: persona)
                }
              },
              onRunBacktest: { runBacktest(contact) },
              onShowBacktestDetail: {
                if case .done(let result) = backtestStates[contact.id] {
                  backtestDetail = AICloneBacktestDetail(contact: contact, result: result)
                }
              }
            )
          }
        }
        .padding(.bottom, 8)
      }
    }
    .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
  }

  // MARK: - Auto-select control

  private var autoSelectControl: some View {
    HStack(spacing: 12) {
      Text("Auto-select top")
        .scaledFont(size: 14, weight: .medium)
        .foregroundColor(OmiColors.textSecondary)

      Text("\(autoSelectCount)")
        .scaledFont(size: 14, weight: .semibold)
        .foregroundColor(OmiColors.textPrimary)
        .frame(minWidth: 22)

      Stepper("", value: $autoSelectCount, in: 0...max(0, maxSelectable))
        .labelsHidden()
        .onChange(of: autoSelectCount) { applyTopXSelection() }

      Text("contact\(autoSelectCount == 1 ? "" : "s") by message count")
        .scaledFont(size: 14, weight: .regular)
        .foregroundColor(OmiColors.textTertiary)

      Spacer()

      Text("\(selectedHandles.count) selected")
        .scaledFont(size: 13, weight: .medium)
        .foregroundColor(OmiColors.textTertiary)
    }
    .padding(.horizontal, 16)
    .padding(.vertical, 12)
    .background(
      RoundedRectangle(cornerRadius: 12, style: .continuous)
        .fill(OmiColors.backgroundSecondary)
    )
  }

  // MARK: - Full Disk Access prompt

  private var fullDiskAccessPrompt: some View {
    centered {
      Image(systemName: "lock.shield")
        .font(.system(size: 34, weight: .regular))
        .foregroundColor(OmiColors.textSecondary)

      Text("Full Disk Access required")
        .scaledFont(size: 16, weight: .semibold)
        .foregroundColor(OmiColors.textPrimary)

      Text(
        "Omi reads your Messages history locally on this Mac to learn how you write. "
          + "Grant Full Disk Access in System Settings, then reload."
      )
      .scaledFont(size: 13, weight: .regular)
      .foregroundColor(OmiColors.textTertiary)
      .multilineTextAlignment(.center)
      .frame(maxWidth: 380)

      HStack(spacing: 10) {
        Button(action: { IMessageReaderService.shared.openFullDiskAccessSettings() }) {
          Text("Open System Settings")
            .scaledFont(size: 13, weight: .semibold)
            .foregroundColor(OmiColors.backgroundPrimary)
            .padding(.horizontal, 18)
            .padding(.vertical, 8)
            .background(RoundedRectangle(cornerRadius: 8).fill(OmiColors.textPrimary))
        }
        .buttonStyle(.plain)

        reloadButton(title: "Reload")
      }
      .padding(.top, 4)
    }
  }

  // MARK: - Reusable pieces

  private func reloadButton(title: String) -> some View {
    Button(action: { reloadToken = UUID() }) {
      Text(title)
        .scaledFont(size: 13, weight: .semibold)
        .foregroundColor(OmiColors.textPrimary)
        .padding(.horizontal, 18)
        .padding(.vertical, 8)
        .background(
          RoundedRectangle(cornerRadius: 8)
            .stroke(OmiColors.border, lineWidth: 1)
        )
    }
    .buttonStyle(.plain)
  }

  private func centered<Inner: View>(@ViewBuilder _ inner: () -> Inner) -> some View {
    VStack(spacing: 12) {
      inner()
    }
    .frame(maxWidth: .infinity, maxHeight: .infinity)
  }

  // MARK: - Data + selection

  private func load() async {
    state = .loading
    do {
      let result = try await IMessageReaderService.shared.topContacts(limit: 20)
      // Restore any personas generated in a previous session so "Trained" badges persist.
      personas = await AIClonePersonaService.shared.allPersonas()
      contacts = result
      if result.isEmpty {
        selectedHandles = []
        state = .empty
        return
      }
      // Default: auto-select the top 5 (clamped to however many contacts exist).
      autoSelectCount = min(5, result.count)
      applyTopXSelection()
      state = .loaded
    } catch IMessageReaderError.fullDiskAccessDenied {
      state = .needsFullDiskAccess
    } catch IMessageReaderError.chatDatabaseNotFound {
      state = .empty
    } catch {
      state = .failed(error.localizedDescription)
    }
  }

  /// Select exactly the top-N contacts by rank. Called on load and whenever the user
  /// changes N via the stepper; per-row toggles override this afterward.
  private func applyTopXSelection() {
    let clamped = max(0, min(autoSelectCount, contacts.count))
    selectedHandles = Set(contacts.prefix(clamped).map { $0.id })
  }

  private func toggleSelection(_ contact: IMessageContact) {
    if selectedHandles.contains(contact.id) {
      selectedHandles.remove(contact.id)
    } else {
      selectedHandles.insert(contact.id)
    }
  }

  /// Generate a persona for one contact. Runs on the MainActor-isolated view, so state
  /// mutations after the `await` are safe. Errors surface inline on the row.
  private func train(_ contact: IMessageContact) {
    guard !trainingHandles.contains(contact.id) else { return }
    trainingHandles.insert(contact.id)
    trainingErrors[contact.id] = nil
    Task {
      do {
        let (generic, messages) = try await Self.loadImported(contact)
        let persona = try await AIClonePersonaService.shared.generatePersona(
          for: generic, messages: messages)
        personas[contact.id] = persona
      } catch {
        trainingErrors[contact.id] = error.localizedDescription
      }
      trainingHandles.remove(contact.id)
    }
  }

  /// Fetch this iMessage contact's history and convert to the platform-agnostic shapes the
  /// AI Clone services now consume.
  private static func loadImported(
    _ contact: IMessageContact
  ) async throws -> (ImportedContact, [ImportedMessage]) {
    let messages = try await IMessageReaderService.shared.messages(for: contact, limit: 500)
      .map { $0.asImportedMessage() }
    return (contact.asImportedContact(), messages)
  }

  /// Run the full backtest + refine loop for one contact, streaming progress into the row.
  private func runBacktest(_ contact: IMessageContact) {
    if case .running = backtestStates[contact.id] { return }
    backtestStates[contact.id] = .running(
      AICloneBacktestProgressUI(iteration: 1, maxIterations: 5, phase: "Starting", latestAverage: nil))

    Task {
      do {
        let (generic, messages) = try await Self.loadImported(contact)
        let (persona, result) = try await AICloneBacktestService.shared.trainToTarget(
          for: generic,
          messages: messages,
          onProgress: { progress in
            Task { @MainActor in
              // Only overwrite while still running (don't clobber a finished result).
              if case .running = backtestStates[contact.id] {
                backtestStates[contact.id] = .running(
                  AICloneBacktestProgressUI(
                    iteration: progress.iteration,
                    maxIterations: progress.maxIterations,
                    phase: progress.phase,
                    latestAverage: progress.latestAverage))
              }
            }
          }
        )
        // trainToTarget persisted the winning persona; refresh the row's cached copy.
        personas[contact.id] = persona
        backtestStates[contact.id] = .done(result)
      } catch {
        backtestStates[contact.id] = .failed(error.localizedDescription)
      }
    }
  }
}

// MARK: - Contact Row

private struct AICloneContactRow: View {
  let rank: Int
  let contact: IMessageContact
  let isSelected: Bool
  let isTraining: Bool
  let persona: ContactPersona?
  let errorMessage: String?
  let backtest: AICloneBacktestUIState?
  let onToggle: () -> Void
  let onTrain: () -> Void
  let onPreviewChat: () -> Void
  let onRunBacktest: () -> Void
  let onShowBacktestDetail: () -> Void

  @State private var isHovered = false

  private var isTrained: Bool { persona != nil }

  var body: some View {
    HStack(spacing: 14) {
      // Selection toggle — neutral white/gray, no accent color (per AGENTS.md: no purple).
      Button(action: onToggle) {
        Image(systemName: isSelected ? "checkmark.circle.fill" : "circle")
          .font(.system(size: 20, weight: .regular))
          .foregroundColor(isSelected ? OmiColors.textPrimary : OmiColors.textQuaternary)
      }
      .buttonStyle(.plain)

      // Rank badge (position by message count).
      ZStack {
        Circle()
          .fill(OmiColors.backgroundTertiary)
          .frame(width: 40, height: 40)

        Text("\(rank)")
          .scaledFont(size: 15, weight: .semibold)
          .foregroundColor(OmiColors.textSecondary)
      }

      VStack(alignment: .leading, spacing: 2) {
        Text(contact.displayName)
          .scaledFont(size: 15, weight: .medium)
          .foregroundColor(OmiColors.textPrimary)
          .lineLimit(1)
          .truncationMode(.middle)

        Text("\(contact.messageCount.formatted()) messages")
          .scaledFont(size: 12, weight: .regular)
          .foregroundColor(OmiColors.textTertiary)
      }

      Spacer()

      if let errorMessage, !isTraining {
        Text(errorMessage)
          .scaledFont(size: 11, weight: .regular)
          .foregroundColor(OmiColors.warning)
          .lineLimit(2)
          .multilineTextAlignment(.trailing)
          .frame(maxWidth: 180, alignment: .trailing)
      }

      trailingControl
    }
    .padding(.horizontal, 16)
    .padding(.vertical, 12)
    .background(
      RoundedRectangle(cornerRadius: 12, style: .continuous)
        .fill(
          isHovered
            ? OmiColors.backgroundTertiary.opacity(0.6)
            : OmiColors.backgroundSecondary
        )
    )
    .overlay(
      RoundedRectangle(cornerRadius: 12, style: .continuous)
        .stroke(isSelected ? OmiColors.border : Color.clear, lineWidth: 1)
    )
    .contentShape(Rectangle())
    .onTapGesture { onToggle() }
    .onHover { isHovered = $0 }
  }

  // MARK: - Trailing control (Train / Training… / Trained / Retry)

  @ViewBuilder
  private var trailingControl: some View {
    if isTraining {
      HStack(spacing: 8) {
        ProgressView()
          .scaleEffect(0.6)
          .tint(.white)
        Text("Training…")
          .scaledFont(size: 13, weight: .semibold)
          .foregroundColor(OmiColors.textSecondary)
      }
      .frame(minWidth: 96)
    } else if isTrained {
      HStack(spacing: 8) {
        if case .done = backtest {
          // Once a backtest exists, the score badge replaces the "Trained" pill.
        } else {
          HStack(spacing: 5) {
            Image(systemName: "checkmark.circle.fill")
              .font(.system(size: 13, weight: .semibold))
              .foregroundColor(OmiColors.textPrimary)
            Text("Trained")
              .scaledFont(size: 13, weight: .semibold)
              .foregroundColor(OmiColors.textPrimary)
          }
        }

        backtestControl

        // Manual sanity-check tool: chat against the persona.
        Button(action: onPreviewChat) {
          Text("Preview Chat")
            .scaledFont(size: 13, weight: .semibold)
            .foregroundColor(OmiColors.backgroundPrimary)
            .padding(.horizontal, 18)
            .padding(.vertical, 8)
            .background(RoundedRectangle(cornerRadius: 8).fill(OmiColors.textPrimary))
        }
        .buttonStyle(.plain)
        // Allow regenerating the persona from the latest history.
        trainButton(title: "Retrain", filled: false)
      }
    } else {
      trainButton(title: errorMessage == nil ? "Train" : "Retry", filled: true)
    }
  }

  // MARK: - Backtest control (Run Backtest / progress / score badge)

  @ViewBuilder
  private var backtestControl: some View {
    switch backtest {
    case .running(let progress):
      HStack(spacing: 8) {
        ProgressView().scaleEffect(0.55).tint(.white)
        VStack(alignment: .leading, spacing: 1) {
          Text("Iteration \(progress.iteration)/\(progress.maxIterations)")
            .scaledFont(size: 12, weight: .semibold)
            .foregroundColor(OmiColors.textPrimary)
          Text(progress.subtitle)
            .scaledFont(size: 10, weight: .regular)
            .foregroundColor(OmiColors.textTertiary)
        }
      }
      .frame(minWidth: 128, alignment: .leading)

    case .done(let result):
      Button(action: onShowBacktestDetail) {
        HStack(spacing: 6) {
          Image(systemName: "chart.bar.fill")
            .font(.system(size: 11, weight: .semibold))
          Text("Avg \(AICloneScoreFormat.pct(result.averageScore))")
            .scaledFont(size: 13, weight: .semibold)
        }
        .foregroundColor(OmiColors.textPrimary)
        .padding(.horizontal, 12)
        .padding(.vertical, 8)
        .background(
          RoundedRectangle(cornerRadius: 8).stroke(OmiColors.border, lineWidth: 1))
      }
      .buttonStyle(.plain)
      .help("\(result.iterationsRun) iteration(s) • tap for held-out pairs")

    case .failed(let message):
      HStack(spacing: 6) {
        Text(message)
          .scaledFont(size: 11, weight: .regular)
          .foregroundColor(OmiColors.warning)
          .lineLimit(1)
          .frame(maxWidth: 120)
        backtestRunButton(title: "Retry")
      }

    case nil:
      backtestRunButton(title: "Run Backtest")
    }
  }

  private func backtestRunButton(title: String) -> some View {
    Button(action: onRunBacktest) {
      Text(title)
        .scaledFont(size: 13, weight: .semibold)
        .foregroundColor(OmiColors.textPrimary)
        .padding(.horizontal, 14)
        .padding(.vertical, 8)
        .background(RoundedRectangle(cornerRadius: 8).stroke(OmiColors.border, lineWidth: 1))
    }
    .buttonStyle(.plain)
  }

  private func trainButton(title: String, filled: Bool) -> some View {
    Button(action: onTrain) {
      Text(title)
        .scaledFont(size: 13, weight: .semibold)
        .foregroundColor(filled ? OmiColors.backgroundPrimary : OmiColors.textPrimary)
        .padding(.horizontal, 18)
        .padding(.vertical, 8)
        .background(
          Group {
            if filled {
              RoundedRectangle(cornerRadius: 8).fill(OmiColors.textPrimary)
            } else {
              RoundedRectangle(cornerRadius: 8).stroke(OmiColors.border, lineWidth: 1)
            }
          }
        )
    }
    .buttonStyle(.plain)
  }
}

// MARK: - Preview Chat

/// Identifies which trained contact the preview-chat sheet is for.
private struct AICloneChatTarget: Identifiable {
  let contact: IMessageContact
  let persona: ContactPersona
  var id: String { contact.id }
}

/// A single turn in the preview transcript. `incoming` = a message you type *as the
/// contact*; `reply` = the persona's predicted response *as you*.
private struct AIClonePreviewMessage: Identifiable {
  enum Kind { case incoming, reply }
  let id = UUID()
  let kind: Kind
  let text: String
}

/// Minimal manual chat tool: type a message as the contact, see how the persona (you)
/// would reply. In-memory only — nothing is persisted.
private struct AIClonePreviewChatSheet: View {
  let contact: IMessageContact
  let persona: ContactPersona

  @Environment(\.dismiss) private var dismiss
  @State private var draft = ""
  @State private var messages: [AIClonePreviewMessage] = []
  @State private var isResponding = false
  @State private var errorMessage: String?
  @FocusState private var inputFocused: Bool

  var body: some View {
    VStack(spacing: 0) {
      sheetHeader
      Divider().overlay(OmiColors.border)
      transcript
      Divider().overlay(OmiColors.border)
      inputBar
    }
    .frame(width: 460, height: 560)
    .background(OmiColors.backgroundPrimary)
    .onAppear { inputFocused = true }
    .task {
      // Build the retrieval index so replies get dynamic few-shot examples from the
      // real history (no-op if already built for this contact).
      if let messages = try? await IMessageReaderService.shared.messages(
        for: contact, limit: 1500)
      {
        await AICloneRetrievalService.shared.ensureIndex(
          contactId: contact.id, messages: messages.map { $0.asImportedMessage() })
      }
    }
  }

  // MARK: Header

  private var sheetHeader: some View {
    HStack(alignment: .top, spacing: 12) {
      VStack(alignment: .leading, spacing: 3) {
        Text("Preview Chat")
          .scaledFont(size: 16, weight: .semibold)
          .foregroundColor(OmiColors.textPrimary)
        Text("Type as if you were \(contact.displayName) — Omi predicts how you'd reply")
          .scaledFont(size: 12, weight: .regular)
          .foregroundColor(OmiColors.textTertiary)
          .fixedSize(horizontal: false, vertical: true)
      }

      Spacer()

      Button(action: { dismiss() }) {
        Image(systemName: "xmark")
          .font(.system(size: 13, weight: .semibold))
          .foregroundColor(OmiColors.textSecondary)
          .padding(8)
          .background(Circle().fill(OmiColors.backgroundSecondary))
      }
      .buttonStyle(.plain)
    }
    .padding(16)
  }

  // MARK: Transcript

  private var transcript: some View {
    ScrollViewReader { proxy in
      ScrollView {
        LazyVStack(spacing: 10) {
          if messages.isEmpty && !isResponding {
            Text("Send a message to see the predicted reply.")
              .scaledFont(size: 13, weight: .regular)
              .foregroundColor(OmiColors.textTertiary)
              .frame(maxWidth: .infinity)
              .padding(.top, 40)
          }

          ForEach(messages) { message in
            bubble(for: message)
              .id(message.id)
          }

          if isResponding {
            HStack {
              typingBubble
              Spacer(minLength: 60)
            }
            .id("typing")
          }

          if let errorMessage {
            Text(errorMessage)
              .scaledFont(size: 12, weight: .regular)
              .foregroundColor(OmiColors.warning)
              .frame(maxWidth: .infinity, alignment: .leading)
          }
        }
        .padding(16)
      }
      .onChange(of: messages.count) { scrollToBottom(proxy) }
      .onChange(of: isResponding) { scrollToBottom(proxy) }
    }
  }

  @ViewBuilder
  private func bubble(for message: AIClonePreviewMessage) -> some View {
    let isReply = message.kind == .reply
    HStack {
      if isReply { Spacer(minLength: 60) }

      Text(message.text)
        .scaledFont(size: 14, weight: .regular)
        .foregroundColor(isReply ? OmiColors.backgroundPrimary : OmiColors.textPrimary)
        .padding(.horizontal, 14)
        .padding(.vertical, 10)
        .background(
          RoundedRectangle(cornerRadius: 16, style: .continuous)
            .fill(isReply ? OmiColors.textPrimary : OmiColors.backgroundSecondary)
        )
        .textSelection(.enabled)

      if !isReply { Spacer(minLength: 60) }
    }
  }

  private var typingBubble: some View {
    HStack(spacing: 8) {
      ProgressView().scaleEffect(0.6).tint(.white)
      Text("Predicting reply…")
        .scaledFont(size: 13, weight: .regular)
        .foregroundColor(OmiColors.textSecondary)
    }
    .padding(.horizontal, 14)
    .padding(.vertical, 10)
    .background(
      RoundedRectangle(cornerRadius: 16, style: .continuous)
        .fill(OmiColors.backgroundSecondary)
    )
  }

  // MARK: Input

  private var inputBar: some View {
    HStack(spacing: 10) {
      TextField("Message as \(contact.displayName)…", text: $draft, axis: .vertical)
        .textFieldStyle(.plain)
        .scaledFont(size: 14, weight: .regular)
        .foregroundColor(OmiColors.textPrimary)
        .lineLimit(1...4)
        .focused($inputFocused)
        .padding(.horizontal, 14)
        .padding(.vertical, 10)
        .background(
          RoundedRectangle(cornerRadius: 12, style: .continuous)
            .fill(OmiColors.backgroundSecondary)
        )
        .onSubmit { send() }

      Button(action: send) {
        Image(systemName: "arrow.up")
          .font(.system(size: 15, weight: .bold))
          .foregroundColor(OmiColors.backgroundPrimary)
          .frame(width: 36, height: 36)
          .background(Circle().fill(canSend ? OmiColors.textPrimary : OmiColors.textQuaternary))
      }
      .buttonStyle(.plain)
      .disabled(!canSend)
    }
    .padding(16)
  }

  private var canSend: Bool {
    !isResponding && !draft.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
  }

  // MARK: Actions

  private func send() {
    let text = draft.trimmingCharacters(in: .whitespacesAndNewlines)
    guard !text.isEmpty, !isResponding else { return }

    // Carry the last few turns of this preview as context so the clone replies in flow.
    let context = messages.suffix(4).map {
      ConversationTurn(isFromMe: $0.kind == .reply, text: $0.text)
    }

    messages.append(AIClonePreviewMessage(kind: .incoming, text: text))
    draft = ""
    errorMessage = nil
    isResponding = true

    Task {
      do {
        let reply = try await AIClonePersonaService.shared.respond(
          as: persona, to: text, context: context)
        // A burst reply comes back as newline-joined bubbles — render each as its own
        // message bubble, exactly like the real person's multi-text bursts.
        for bubble in reply.components(separatedBy: "\n")
        where !bubble.trimmingCharacters(in: .whitespaces).isEmpty {
          messages.append(AIClonePreviewMessage(kind: .reply, text: bubble))
        }
      } catch {
        errorMessage = error.localizedDescription
      }
      isResponding = false
    }
  }

  private func scrollToBottom(_ proxy: ScrollViewProxy) {
    withAnimation(.easeOut(duration: 0.2)) {
      if isResponding {
        proxy.scrollTo("typing", anchor: .bottom)
      } else if let last = messages.last {
        proxy.scrollTo(last.id, anchor: .bottom)
      }
    }
  }
}

// MARK: - Backtest UI models

/// Per-row backtest state.
enum AICloneBacktestUIState {
  case running(AICloneBacktestProgressUI)
  case done(BacktestResult)
  case failed(String)
}

struct AICloneBacktestProgressUI {
  let iteration: Int
  let maxIterations: Int
  let phase: String
  let latestAverage: Double?

  /// e.g. "Backtesting" or "Refining · best 78%".
  var subtitle: String {
    if let latestAverage {
      return "\(phase) · best \(AICloneScoreFormat.pct(latestAverage))"
    }
    return phase
  }
}

/// Identifies which contact's backtest results the detail sheet shows.
private struct AICloneBacktestDetail: Identifiable {
  let contact: IMessageContact
  let result: BacktestResult
  var id: String { contact.id }
}

enum AICloneScoreFormat {
  /// A cosine score in [-1, 1] rendered as a 0–100% match.
  static func pct(_ score: Double) -> String {
    "\(Int((max(0, min(1, score)) * 100).rounded()))%"
  }

  static func color(_ score: Double) -> Color {
    switch score {
    case 0.85...: return OmiColors.success
    case 0.65..<0.85: return OmiColors.textPrimary
    default: return OmiColors.warning
    }
  }
}

// MARK: - Backtest results sheet

/// Shows the average score prominently and the held-out pairs so the user can eyeball
/// quality: their message / what the clone predicted / what the user actually said / score.
private struct AICloneBacktestSheet: View {
  let contact: IMessageContact
  let result: BacktestResult

  @Environment(\.dismiss) private var dismiss

  private var scoredPairs: [BacktestPair] {
    result.pairs
      .filter { $0.similarityScore != nil }
      .sorted { ($0.similarityScore ?? 0) > ($1.similarityScore ?? 0) }
  }

  var body: some View {
    VStack(spacing: 0) {
      header
      Divider().overlay(OmiColors.border)
      ScrollView {
        LazyVStack(spacing: 12) {
          ForEach(scoredPairs) { pair in
            pairCard(pair)
          }
          if scoredPairs.isEmpty {
            Text("No scored pairs — predictions or embeddings may have failed.")
              .scaledFont(size: 13, weight: .regular)
              .foregroundColor(OmiColors.textTertiary)
              .padding(.top, 40)
          }
        }
        .padding(18)
      }
    }
    .frame(width: 560, height: 640)
    .background(OmiColors.backgroundPrimary)
  }

  private var header: some View {
    HStack(alignment: .center, spacing: 16) {
      VStack(alignment: .leading, spacing: 4) {
        Text("Backtest — \(contact.displayName)")
          .scaledFont(size: 16, weight: .semibold)
          .foregroundColor(OmiColors.textPrimary)
        Text(
          "\(result.iterationsRun) iteration\(result.iterationsRun == 1 ? "" : "s") · "
            + "\(scoredPairs.count) held-out pairs · \(result.messageCountUsed) messages")
          .scaledFont(size: 12, weight: .regular)
          .foregroundColor(OmiColors.textTertiary)
      }

      Spacer()

      VStack(alignment: .trailing, spacing: 2) {
        Text(AICloneScoreFormat.pct(result.averageScore))
          .scaledFont(size: 30, weight: .bold)
          .foregroundColor(AICloneScoreFormat.color(result.averageScore))
        Text("avg match")
          .scaledFont(size: 11, weight: .medium)
          .foregroundColor(OmiColors.textTertiary)
      }

      Button(action: { dismiss() }) {
        Image(systemName: "xmark")
          .font(.system(size: 13, weight: .semibold))
          .foregroundColor(OmiColors.textSecondary)
          .padding(8)
          .background(Circle().fill(OmiColors.backgroundSecondary))
      }
      .buttonStyle(.plain)
    }
    .padding(18)
  }

  private func pairCard(_ pair: BacktestPair) -> some View {
    VStack(alignment: .leading, spacing: 10) {
      HStack {
        Text(contact.displayName)
          .scaledFont(size: 11, weight: .semibold)
          .foregroundColor(OmiColors.textTertiary)
        Spacer()
        if let score = pair.similarityScore {
          Text(AICloneScoreFormat.pct(score))
            .scaledFont(size: 12, weight: .bold)
            .foregroundColor(AICloneScoreFormat.color(score))
            .padding(.horizontal, 8)
            .padding(.vertical, 3)
            .background(
              Capsule().fill(AICloneScoreFormat.color(score).opacity(0.14)))
        }
      }

      labeledLine(label: "They said", text: pair.contactMessage, tint: OmiColors.textSecondary)
      labeledLine(
        label: "Clone predicted", text: pair.predictedReply ?? "—", tint: OmiColors.textPrimary)
      labeledLine(label: "You actually said", text: pair.actualReply, tint: OmiColors.success)

      if let reasoning = pair.judgeReasoning, !reasoning.isEmpty {
        HStack(alignment: .top, spacing: 6) {
          Image(systemName: "gavel")
            .font(.system(size: 10, weight: .semibold))
            .foregroundColor(OmiColors.textQuaternary)
          Text(reasoning)
            .scaledFont(size: 11, weight: .regular)
            .foregroundColor(OmiColors.textTertiary)
            .italic()
            .fixedSize(horizontal: false, vertical: true)
        }
        .padding(.top, 2)
      }
    }
    .padding(14)
    .frame(maxWidth: .infinity, alignment: .leading)
    .background(
      RoundedRectangle(cornerRadius: 12, style: .continuous).fill(OmiColors.backgroundSecondary))
  }

  private func labeledLine(label: String, text: String, tint: Color) -> some View {
    VStack(alignment: .leading, spacing: 2) {
      Text(label.uppercased())
        .scaledFont(size: 9, weight: .semibold)
        .foregroundColor(OmiColors.textQuaternary)
      Text(text)
        .scaledFont(size: 13, weight: .regular)
        .foregroundColor(tint)
        .fixedSize(horizontal: false, vertical: true)
        .textSelection(.enabled)
    }
    .frame(maxWidth: .infinity, alignment: .leading)
  }
}

#Preview {
  AIClonePage()
}
