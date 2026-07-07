import AppKit
import SwiftUI

/// AI Clone page — an AI-powered messaging assistant that learns to reply to your
/// contacts in your voice. Contacts are the user's real top correspondents (ranked by
/// message count) from iMessage (read locally via `IMessageReaderService`) plus any
/// Telegram/WhatsApp exports the user has imported this session.
struct AIClonePage: View {
  private enum LoadState: Equatable {
    case loading
    case loaded
    case needsFullDiskAccess
    case empty
    case failed(String)
  }

  /// Send-mode coordinator (per-contact mode, autonomous kill switch, drafts, sent log).
  @ObservedObject private var sendMode = AICloneSendModeService.shared
  /// Non-nil while the "Recent Sent Messages" sheet is open.
  @State private var showSentLog = false

  @State private var state: LoadState = .loading
  @State private var contacts: [ImportedContact] = []
  @State private var selectedHandles: Set<String> = []
  /// How many top contacts to auto-select. Defaults to 5; re-applied whenever changed.
  @State private var autoSelectCount = 5
  /// Bumped to force `.task` to re-run (e.g. after the user grants Full Disk Access).
  @State private var reloadToken = UUID()

  /// Generated personas keyed by contact id (hydrated from disk on load).
  @State private var personas: [String: ContactPersona] = [:]
  /// Contact ids currently generating a persona (drives the per-row spinner).
  @State private var trainingHandles: Set<String> = []
  /// Last training error per contact id, shown inline on that row.
  @State private var trainingErrors: [String: String] = [:]
  /// Non-nil while the chat sheet is open for a trained contact.
  @State private var chatTarget: AICloneChatTarget?
  /// Automation-requested chat open that arrived before contacts finished loading.
  @State private var pendingAutomationChatId: String?
  /// Per-contact backtest UI state (progress while running, result when done).
  @State private var backtestStates: [String: AICloneBacktestUIState] = [:]
  /// Non-nil while the backtest-results detail sheet is open.
  @State private var backtestDetail: AICloneBacktestDetail?

  /// Non-nil while the Telegram "which one is you" sheet is open.
  @State private var telegramSenderPicker: TelegramSenderPickerState?
  /// Non-nil while the WhatsApp "which one is you" sheet is open.
  @State private var whatsAppSenderPicker: WhatsAppSenderPickerState?
  @State private var telegramImportError: String?
  @State private var whatsAppImportError: String?

  /// WhatsApp live-link state (QR scanning / linked), mirrored from the sidecar.
  @ObservedObject private var whatsAppLink = WhatsAppLinkModel.shared
  /// True while the WhatsApp QR-linking sheet is open.
  @State private var showWhatsAppLinkSheet = false
  /// Non-nil while the one-time "WhatsApp Autonomous is risky" confirmation is up: the
  /// contact whose switch to Autonomous awaits explicit acknowledgment.
  @State private var whatsAppAutonomousCandidate: ImportedContact?

  private var maxSelectable: Int { contacts.count }
  private var hasTelegramContacts: Bool { contacts.contains { $0.platform == "telegram" } }
  private var hasWhatsAppContacts: Bool { contacts.contains { $0.platform == "whatsapp" } }

  var body: some View {
    VStack(alignment: .leading, spacing: 20) {
      header

      autonomousBanner

      importControls

      if !sendMode.pendingDrafts.isEmpty {
        pendingDraftsSection
      }

      content
    }
    .padding(28)
    .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
    .background(OmiColors.backgroundPrimary)
    .task(id: reloadToken) { await load() }
    // Deliberately NO stopListening on disappear: Draft-Review/Autonomous must keep
    // working after the user navigates away — the listeners are app-level, owned by
    // AICloneSendModeService (bootstrapped at launch), not by this page's lifecycle.
    .onReceive(NotificationCenter.default.publisher(for: .aiCloneOpenChatRequested)) { note in
      guard let id = note.userInfo?["contactId"] as? String else { return }
      openChatViaAutomation(id)
    }
    .onReceive(NotificationCenter.default.publisher(for: .aiCloneCloseChatRequested)) { _ in
      chatTarget = nil
    }
    .onChange(of: chatTarget?.id) {
      // Authoritative presentation signal: the sheet's own onDisappear is unreliable on
      // macOS (sheet hosts get cached), so lifecycle state is owned here.
      AICloneChatAutomation.shared.activeContactId = chatTarget?.contact.id
      if chatTarget == nil {
        AICloneChatAutomation.shared.liveSnapshot = nil
      }
    }
    .sheet(isPresented: $showSentLog) {
      AICloneSentLogSheet()
    }
    .sheet(item: $chatTarget) { target in
      AICloneChatSheet(contact: target.contact, persona: target.persona)
    }
    .sheet(item: $backtestDetail) { detail in
      AICloneBacktestSheet(contact: detail.contact, result: detail.result)
    }
    .sheet(item: $telegramSenderPicker) { picker in
      TelegramSenderSheet(senders: picker.senders) { chosen in
        telegramSenderPicker = nil
        Task {
          await TelegramImportService.shared.setSelfID(chosen.senderID ?? chosen.id)
          await refreshTelegramContacts()
        }
      }
    }
    .sheet(item: $whatsAppSenderPicker) { picker in
      WhatsAppSenderSheet(options: picker.options, preselected: picker.preselected) { chosen in
        whatsAppSenderPicker = nil
        Task {
          await WhatsAppImportService.shared.setSelfName(chosen)
          await refreshWhatsAppContacts()
        }
      }
    }
    .sheet(isPresented: $showWhatsAppLinkSheet) {
      WhatsAppLinkSheet()
    }
    .alert(
      "Enable Autonomous for WhatsApp?",
      isPresented: Binding(
        get: { whatsAppAutonomousCandidate != nil },
        set: { if !$0 { whatsAppAutonomousCandidate = nil } }
      ),
      presenting: whatsAppAutonomousCandidate
    ) { contact in
      Button("I Understand the Risk — Enable", role: .destructive) {
        sendMode.acknowledgeWhatsAppAutonomousRisk()
        sendMode.setMode(.autonomous, for: contact.id)
        whatsAppAutonomousCandidate = nil
      }
      Button("Cancel", role: .cancel) {
        whatsAppAutonomousCandidate = nil
      }
    } message: { _ in
      Text(
        "Omi connects to WhatsApp through Linked Devices using an unofficial method — "
          + "WhatsApp has no official API for personal accounts. Automated sending is "
          + "against WhatsApp's terms and carries some risk of your account being "
          + "flagged or banned. This one-time confirmation is required before any "
          + "WhatsApp contact can be set to Autonomous. Nothing sends while the global "
          + "Autonomous switch stays paused."
      )
    }
  }

  /// Route a mode-picker selection through the WhatsApp-autonomous safety gate: the first
  /// time any WhatsApp contact is switched to Autonomous, the explicit unofficial-connection
  /// risk confirmation must be accepted before the mode applies.
  private func requestModeChange(_ newMode: SendMode, for contact: ImportedContact) {
    if AICloneSendModeService.requiresWhatsAppAutonomousAcknowledgment(
      mode: newMode, contactId: contact.id,
      acknowledged: sendMode.whatsAppAutonomousAcknowledged)
    {
      whatsAppAutonomousCandidate = contact
      return
    }
    sendMode.setMode(newMode, for: contact.id)
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

  // MARK: - Autonomous kill switch banner

  /// Always-visible global control for autonomous sending. Warning-colored (the one place
  /// the AI Clone UI uses `OmiColors.warning` as an accent) because flipping it ACTIVE lets
  /// the clone message real people on its own.
  private var autonomousBanner: some View {
    let active = !sendMode.isPaused
    return HStack(spacing: 14) {
      Image(systemName: active ? "bolt.fill" : "pause.circle.fill")
        .font(.system(size: 18, weight: .semibold))
        .foregroundColor(active ? OmiColors.warning : OmiColors.textSecondary)

      VStack(alignment: .leading, spacing: 2) {
        Text("Autonomous Sending: \(active ? "ACTIVE" : "PAUSED")")
          .scaledFont(size: 14, weight: .bold)
          .foregroundColor(active ? OmiColors.warning : OmiColors.textPrimary)
        Text(
          active
            ? "The clone can send replies to real people on its own. Turn this off to stop."
            : "Autonomous replies are paused. Draft-Review and manual sending still work."
        )
        .scaledFont(size: 12, weight: .regular)
        .foregroundColor(OmiColors.textTertiary)
        .fixedSize(horizontal: false, vertical: true)
      }

      Spacer()

      Button(action: { showSentLog = true }) {
        HStack(spacing: 5) {
          Image(systemName: "paperplane")
            .font(.system(size: 11, weight: .semibold))
          Text("Sent\(sendMode.sentLog.isEmpty ? "" : " (\(sendMode.sentLog.count))")")
            .scaledFont(size: 12, weight: .semibold)
        }
        .foregroundColor(OmiColors.textSecondary)
        .padding(.horizontal, 12)
        .padding(.vertical, 7)
        .background(RoundedRectangle(cornerRadius: 8).stroke(OmiColors.border, lineWidth: 1))
      }
      .buttonStyle(.plain)

      Toggle(
        "",
        isOn: Binding(
          get: { !sendMode.isPaused },
          set: { sendMode.setPaused(!$0) }
        )
      )
      .labelsHidden()
      .toggleStyle(.switch)
      .tint(OmiColors.warning)
    }
    .padding(.horizontal, 16)
    .padding(.vertical, 12)
    .background(
      RoundedRectangle(cornerRadius: 12, style: .continuous)
        .fill(active ? OmiColors.warning.opacity(0.12) : OmiColors.backgroundSecondary)
    )
    .overlay(
      RoundedRectangle(cornerRadius: 12, style: .continuous)
        .stroke(active ? OmiColors.warning.opacity(0.5) : OmiColors.border, lineWidth: 1)
    )
  }

  // MARK: - Pending drafts (Draft-Review approval queue)

  private var pendingDraftsSection: some View {
    VStack(alignment: .leading, spacing: 10) {
      HStack(spacing: 6) {
        Image(systemName: "tray.full")
          .font(.system(size: 12, weight: .semibold))
          .foregroundColor(OmiColors.textSecondary)
        Text("Pending replies (\(sendMode.pendingDrafts.count))")
          .scaledFont(size: 14, weight: .semibold)
          .foregroundColor(OmiColors.textPrimary)
      }

      VStack(spacing: 8) {
        ForEach(sendMode.pendingDrafts) { draft in
          AIClonePendingDraftRow(draft: draft)
        }
      }
    }
    .padding(16)
    .frame(maxWidth: .infinity, alignment: .leading)
    .background(
      RoundedRectangle(cornerRadius: 12, style: .continuous)
        .fill(OmiColors.backgroundSecondary)
    )
  }

  // MARK: - Import controls (Telegram / WhatsApp)

  private var importControls: some View {
    VStack(alignment: .leading, spacing: 6) {
      HStack(spacing: 10) {
        importButton(title: "Import Telegram", systemImage: "paperplane.fill", action: importTelegram)
        if hasTelegramContacts {
          changeButton(action: changeTelegramSelf)
        }

        importButton(
          title: "Import WhatsApp", systemImage: "phone.bubble.left.fill", action: importWhatsApp)
        if hasWhatsAppContacts {
          changeButton(action: changeWhatsAppSelf)
        }

        whatsAppLinkButton

        Spacer()
      }

      if let telegramImportError {
        Text(telegramImportError)
          .scaledFont(size: 12, weight: .regular)
          .foregroundColor(OmiColors.warning)
      }
      if let whatsAppImportError {
        Text(whatsAppImportError)
          .scaledFont(size: 12, weight: .regular)
          .foregroundColor(OmiColors.warning)
      }
    }
  }

  private func importButton(title: String, systemImage: String, action: @escaping () -> Void)
    -> some View
  {
    Button(action: action) {
      HStack(spacing: 6) {
        Image(systemName: systemImage)
          .font(.system(size: 12, weight: .semibold))
        Text(title)
          .scaledFont(size: 13, weight: .semibold)
      }
      .foregroundColor(OmiColors.textPrimary)
      .padding(.horizontal, 14)
      .padding(.vertical, 8)
      .background(RoundedRectangle(cornerRadius: 8).stroke(OmiColors.border, lineWidth: 1))
    }
    .buttonStyle(.plain)
  }

  /// Opens the QR linking sheet. Label reflects the live link state so "Linked" is visible
  /// at a glance without opening the sheet.
  private var whatsAppLinkButton: some View {
    Button(action: { showWhatsAppLinkSheet = true }) {
      HStack(spacing: 6) {
        Image(
          systemName: whatsAppLink.state.isLinked ? "checkmark.circle.fill" : "qrcode")
          .font(.system(size: 12, weight: .semibold))
        Text(whatsAppLink.state.isLinked ? "WhatsApp Linked" : "Link WhatsApp")
          .scaledFont(size: 13, weight: .semibold)
      }
      .foregroundColor(
        whatsAppLink.state.isLinked ? OmiColors.success : OmiColors.textPrimary)
      .padding(.horizontal, 14)
      .padding(.vertical, 8)
      .background(RoundedRectangle(cornerRadius: 8).stroke(OmiColors.border, lineWidth: 1))
    }
    .buttonStyle(.plain)
    .help("Connect your WhatsApp account (Linked Devices) so the clone can send and receive")
  }

  private func changeButton(action: @escaping () -> Void) -> some View {
    Button(action: action) {
      Text("Change")
        .scaledFont(size: 12, weight: .medium)
        .foregroundColor(OmiColors.textTertiary)
    }
    .buttonStyle(.plain)
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
        Text(
          "Once you have direct message threads in Messages, or import a Telegram/WhatsApp "
            + "export, your top contacts will appear here."
        )
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
              sendMode: sendMode.mode(for: contact.id),
              onSetMode: { newMode in requestModeChange(newMode, for: contact) },
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
          + "Grant Full Disk Access in System Settings, then reload — or import a "
          + "Telegram/WhatsApp export above instead."
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
    personas = await AIClonePersonaService.shared.allPersonas()
    do {
      let result = try await IMessageReaderService.shared.topContacts(limit: 20)
      // Re-fetch after the await so imports finished during load aren't clobbered.
      let otherContacts = await importedPlatformContacts()
      finishLoad(result.map { $0.asImportedContact() } + otherContacts)
    } catch IMessageReaderError.fullDiskAccessDenied {
      let otherContacts = await importedPlatformContacts()
      if otherContacts.isEmpty {
        state = .needsFullDiskAccess
      } else {
        finishLoad(otherContacts)
      }
    } catch IMessageReaderError.chatDatabaseNotFound {
      let otherContacts = await importedPlatformContacts()
      finishLoad(otherContacts)
    } catch {
      state = .failed(error.localizedDescription)
    }
  }

  /// Session-imported Telegram/WhatsApp contacts (empty until the user imports one).
  private func importedPlatformContacts() async -> [ImportedContact] {
    async let telegram = TelegramImportService.shared.topContacts(limit: 20)
    async let whatsApp = WhatsAppImportService.shared.topContacts(limit: 20)
    return await telegram + whatsApp
  }

  private func finishLoad(_ imported: [ImportedContact]) {
    contacts = imported.sorted { $0.messageCount > $1.messageCount }
    if contacts.isEmpty {
      selectedHandles = []
      state = .empty
      return
    }
    autoSelectCount = min(5, contacts.count)
    applyTopXSelection()
    state = .loaded
    refreshActiveContacts()
    sendMode.startListening()
    if let pending = pendingAutomationChatId {
      pendingAutomationChatId = nil
      openChatViaAutomation(pending)
    }
  }

  /// Open the chat sheet for a bridge-requested contact; parked until contacts load when
  /// the request lands mid-load (e.g. right after a navigate to this page).
  private func openChatViaAutomation(_ contactId: String) {
    if let contact = contacts.first(where: { $0.id == contactId }),
      let persona = personas[contact.id]
    {
      chatTarget = AICloneChatTarget(contact: contact, persona: persona)
    } else if state == .loading {
      pendingAutomationChatId = contactId
    }
  }

  /// Push the current trained contacts (contact + persona) into the send-mode coordinator so
  /// its live listeners can route incoming messages. Called on load and after each train.
  private func refreshActiveContacts() {
    let entries = contacts.compactMap { contact -> (contact: ImportedContact, persona: ContactPersona)? in
      guard let persona = personas[contact.id] else { return nil }
      return (contact, persona)
    }
    sendMode.updateActiveContacts(entries)
  }

  /// Select exactly the top-N contacts by rank. Called on load and whenever the user
  /// changes N via the stepper; per-row toggles override this afterward.
  private func applyTopXSelection() {
    let clamped = max(0, min(autoSelectCount, contacts.count))
    selectedHandles = Set(contacts.prefix(clamped).map { $0.id })
  }

  private func toggleSelection(_ contact: ImportedContact) {
    if selectedHandles.contains(contact.id) {
      selectedHandles.remove(contact.id)
    } else {
      selectedHandles.insert(contact.id)
    }
  }

  /// Generate a persona for one contact. Runs on the MainActor-isolated view, so state
  /// mutations after the `await` are safe. Errors surface inline on the row.
  private func train(_ contact: ImportedContact) {
    guard !trainingHandles.contains(contact.id) else { return }
    trainingHandles.insert(contact.id)
    trainingErrors[contact.id] = nil
    Task {
      if contact.platform == "telegram",
        await TelegramImportService.shared.hasSelfIdentity() == false
      {
        telegramSenderPicker = TelegramSenderPickerState(
          senders: await TelegramImportService.shared.currentSenders())
        trainingHandles.remove(contact.id)
        return
      }
      if contact.platform == "whatsapp",
        await WhatsAppImportService.shared.hasSelfIdentity() == false
      {
        let options = await WhatsAppImportService.shared.currentSenderOptions()
        let preselected = options.first(where: \.appearsInEveryChat)?.name
        whatsAppSenderPicker = WhatsAppSenderPickerState(options: options, preselected: preselected)
        trainingHandles.remove(contact.id)
        return
      }
      do {
        let messages = try await Self.loadMessages(for: contact, limit: 500)
        let persona = try await AIClonePersonaService.shared.generatePersona(
          for: contact, messages: messages)
        personas[contact.id] = persona
        refreshActiveContacts()
      } catch {
        trainingErrors[contact.id] = error.localizedDescription
      }
      trainingHandles.remove(contact.id)
    }
  }

  /// Fetch this contact's history, branching by platform. `fileprivate` so
  /// `AICloneChatSheet` in this file can reuse the same loading logic.
  fileprivate static func loadMessages(
    for contact: ImportedContact, limit: Int = 500
  ) async throws -> [ImportedMessage] {
    try await AICloneMessageLoader.loadMessages(for: contact, limit: limit)
  }

  /// Run the full backtest + refine loop for one contact, streaming progress into the row.
  private func runBacktest(_ contact: ImportedContact) {
    if case .running = backtestStates[contact.id] { return }
    backtestStates[contact.id] = .running(
      AICloneBacktestProgressUI(iteration: 1, maxIterations: 5, phase: "Starting", latestAverage: nil))

    Task {
      if contact.platform == "telegram",
        await TelegramImportService.shared.hasSelfIdentity() == false
      {
        telegramSenderPicker = TelegramSenderPickerState(
          senders: await TelegramImportService.shared.currentSenders())
        backtestStates[contact.id] = nil
        return
      }
      if contact.platform == "whatsapp",
        await WhatsAppImportService.shared.hasSelfIdentity() == false
      {
        let options = await WhatsAppImportService.shared.currentSenderOptions()
        let preselected = options.first(where: \.appearsInEveryChat)?.name
        whatsAppSenderPicker = WhatsAppSenderPickerState(options: options, preselected: preselected)
        backtestStates[contact.id] = nil
        return
      }
      do {
        let messages = try await Self.loadMessages(for: contact, limit: 500)
        let (persona, result) = try await AICloneBacktestService.shared.trainToTarget(
          for: contact,
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
        refreshActiveContacts()
        backtestStates[contact.id] = .done(result)
      } catch {
        backtestStates[contact.id] = .failed(error.localizedDescription)
      }
    }
  }

  // MARK: - Import actions

  private func importTelegram() {
    let panel = NSOpenPanel()
    panel.message = "Select your Telegram export (result.json, or the export folder)"
    panel.prompt = "Import"
    panel.allowedContentTypes = [.json]
    panel.canChooseFiles = true
    panel.canChooseDirectories = true
    panel.allowsMultipleSelection = false
    guard panel.runModal() == .OK, let url = panel.url else { return }

    telegramImportError = nil
    Task {
      do {
        let senders = try await TelegramImportService.shared.importExport(at: url)
        await refreshTelegramContacts()
        if !senders.isEmpty {
          telegramSenderPicker = TelegramSenderPickerState(senders: senders)
        }
      } catch {
        telegramImportError = error.localizedDescription
      }
    }
  }

  private func changeTelegramSelf() {
    Task {
      let senders = await TelegramImportService.shared.currentSenders()
      guard !senders.isEmpty else { return }
      telegramSenderPicker = TelegramSenderPickerState(senders: senders)
    }
  }

  private func importWhatsApp() {
    let panel = NSOpenPanel()
    panel.message = "Select one or more WhatsApp \"Export Chat\" .txt files"
    panel.prompt = "Import"
    panel.allowedContentTypes = [.plainText]
    panel.canChooseFiles = true
    panel.canChooseDirectories = false
    panel.allowsMultipleSelection = true
    guard panel.runModal() == .OK, !panel.urls.isEmpty else { return }
    let urls = panel.urls

    whatsAppImportError = nil
    Task {
      do {
        let options = try await WhatsAppImportService.shared.importFiles(at: urls)
        if !options.isEmpty {
          let preselected = options.first(where: \.appearsInEveryChat)?.name
          whatsAppSenderPicker = WhatsAppSenderPickerState(options: options, preselected: preselected)
        }
      } catch {
        whatsAppImportError = error.localizedDescription
      }
      // Show any chats that imported successfully even if a later file failed mid-batch.
      await refreshWhatsAppContacts()
    }
  }

  private func changeWhatsAppSelf() {
    Task {
      let options = await WhatsAppImportService.shared.currentSenderOptions()
      guard !options.isEmpty else { return }
      let preselected = options.first(where: \.appearsInEveryChat)?.name
      whatsAppSenderPicker = WhatsAppSenderPickerState(options: options, preselected: preselected)
    }
  }

  private func refreshTelegramContacts() async {
    let imported = await TelegramImportService.shared.topContacts(limit: 20)
    mergeContacts(imported)
  }

  private func refreshWhatsAppContacts() async {
    let imported = await WhatsAppImportService.shared.topContacts(limit: 20)
    mergeContacts(imported)
  }

  /// Merge freshly-imported contacts into the existing list (by id) without disturbing
  /// contacts from other platforms already showing.
  private func mergeContacts(_ imported: [ImportedContact]) {
    guard !imported.isEmpty else { return }
    var byID = Dictionary(uniqueKeysWithValues: contacts.map { ($0.id, $0) })
    for contact in imported { byID[contact.id] = contact }
    contacts = byID.values.sorted { $0.messageCount > $1.messageCount }
    if state != .loaded { state = .loaded }
  }
}

// MARK: - Sender picker sheets

/// Identifies an in-progress Telegram "which one is you" prompt.
private struct TelegramSenderPickerState: Identifiable {
  let id = UUID()
  let senders: [TelegramSender]
}

/// Identifies an in-progress WhatsApp "which one is you" prompt.
private struct WhatsAppSenderPickerState: Identifiable {
  let id = UUID()
  let options: [WhatsAppSenderOption]
  let preselected: String?
}

private struct TelegramSenderSheet: View {
  let senders: [TelegramSender]
  let onSelect: (TelegramSender) -> Void

  var body: some View {
    SenderPickerSheet(
      subtitle: "Pick your name so Omi knows which Telegram messages are yours."
    ) {
      ForEach(senders) { sender in
        SenderPickerRow(
          name: sender.name ?? "Unknown", messageCount: sender.messageCount, badge: nil,
          onSelect: { onSelect(sender) })
      }
    }
  }
}

private struct WhatsAppSenderSheet: View {
  let options: [WhatsAppSenderOption]
  let preselected: String?
  let onSelect: (String) -> Void

  var body: some View {
    SenderPickerSheet(
      subtitle: "Pick your name so Omi knows which WhatsApp messages are yours."
    ) {
      ForEach(options) { option in
        SenderPickerRow(
          name: option.name, messageCount: option.messageCount,
          badge: option.name == preselected ? "likely you" : nil,
          onSelect: { onSelect(option.name) })
      }
    }
  }
}

/// Shared chrome for the Telegram/WhatsApp "which one is you" sheets.
private struct SenderPickerSheet<Rows: View>: View {
  let subtitle: String
  let rows: Rows

  init(subtitle: String, @ViewBuilder rows: () -> Rows) {
    self.subtitle = subtitle
    self.rows = rows()
  }

  var body: some View {
    VStack(alignment: .leading, spacing: 0) {
      VStack(alignment: .leading, spacing: 4) {
        Text("Which one is you?")
          .scaledFont(size: 16, weight: .semibold)
          .foregroundColor(OmiColors.textPrimary)
        Text(subtitle)
          .scaledFont(size: 12, weight: .regular)
          .foregroundColor(OmiColors.textTertiary)
      }
      .padding(16)
      Divider().overlay(OmiColors.border)
      ScrollView {
        LazyVStack(spacing: 6) {
          rows
        }
        .padding(16)
      }
    }
    .frame(width: 380, height: 420)
    .background(OmiColors.backgroundPrimary)
  }
}

private struct SenderPickerRow: View {
  let name: String
  let messageCount: Int
  let badge: String?
  let onSelect: () -> Void
  @Environment(\.dismiss) private var dismiss

  var body: some View {
    Button(action: {
      onSelect()
      dismiss()
    }) {
      HStack(spacing: 8) {
        Text(name)
          .scaledFont(size: 14, weight: .medium)
          .foregroundColor(OmiColors.textPrimary)
          .lineLimit(1)

        if let badge {
          Text(badge)
            .scaledFont(size: 10, weight: .semibold)
            .foregroundColor(OmiColors.textTertiary)
            .padding(.horizontal, 6)
            .padding(.vertical, 2)
            .background(Capsule().fill(OmiColors.backgroundTertiary))
        }

        Spacer()

        Text("\(messageCount) messages")
          .scaledFont(size: 12, weight: .regular)
          .foregroundColor(OmiColors.textTertiary)
      }
      .padding(.horizontal, 14)
      .padding(.vertical, 10)
      .background(RoundedRectangle(cornerRadius: 10).fill(OmiColors.backgroundSecondary))
    }
    .buttonStyle(.plain)
  }
}

// MARK: - Contact Row

private struct AICloneContactRow: View {
  let rank: Int
  let contact: ImportedContact
  let isSelected: Bool
  let isTraining: Bool
  let persona: ContactPersona?
  let errorMessage: String?
  let backtest: AICloneBacktestUIState?
  let sendMode: SendMode
  let onSetMode: (SendMode) -> Void
  let onToggle: () -> Void
  let onTrain: () -> Void
  let onPreviewChat: () -> Void
  let onRunBacktest: () -> Void
  let onShowBacktestDetail: () -> Void

  @State private var isHovered = false

  private var isTrained: Bool { persona != nil }

  /// Small platform badge shown next to the name for non-iMessage sources. No purple
  /// (per AGENTS.md) — neutral white/gray SF Symbols.
  private var platformIcon: String? {
    switch contact.platform {
    case "telegram": return "paperplane.fill"
    case "whatsapp": return "phone.bubble.left.fill"
    default: return nil
    }
  }

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
        HStack(spacing: 6) {
          if let platformIcon {
            Image(systemName: platformIcon)
              .font(.system(size: 10, weight: .semibold))
              .foregroundColor(OmiColors.textQuaternary)
          }
          Text(contact.displayName)
            .scaledFont(size: 15, weight: .medium)
            .foregroundColor(OmiColors.textPrimary)
            .lineLimit(1)
            .truncationMode(.middle)
        }

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

        modePicker

        backtestControl

        // Live conversation + practice chat against the persona.
        Button(action: onPreviewChat) {
          Text("Chat")
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

  // MARK: - Send-mode picker (Manual / Draft / Auto)

  private var modePicker: some View {
    Menu {
      ForEach(SendMode.allCases, id: \.self) { mode in
        Button(action: { onSetMode(mode) }) {
          if mode == sendMode {
            Label(mode.fullLabel, systemImage: "checkmark")
          } else {
            Text(mode.fullLabel)
          }
        }
      }
    } label: {
      HStack(spacing: 4) {
        Image(systemName: modeIcon)
          .font(.system(size: 10, weight: .semibold))
        Text(sendMode.label)
          .scaledFont(size: 12, weight: .semibold)
        Image(systemName: "chevron.down")
          .font(.system(size: 8, weight: .semibold))
      }
      // Force an explicit neutral/warning fill so the Menu never picks up the system
      // accent color (which can be purple) — see AGENTS.md "Never use purple".
      .foregroundStyle(modeTint)
      .padding(.horizontal, 10)
      .padding(.vertical, 7)
      .background(
        RoundedRectangle(cornerRadius: 8).stroke(
          sendMode == .autonomous ? OmiColors.warning.opacity(0.6) : OmiColors.border,
          lineWidth: 1))
    }
    .menuStyle(.borderlessButton)
    .menuIndicator(.hidden)
    .tint(modeTint)
    .fixedSize()
    .help("How the clone handles new messages from \(contact.displayName)")
  }

  private var modeIcon: String {
    switch sendMode {
    case .manual: return "hand.point.up.left"
    case .draftReview: return "tray.full"
    case .autonomous: return "bolt.fill"
    }
  }

  /// Neutral by default, warning-amber only for Autonomous. Never accent/purple.
  private var modeTint: Color {
    sendMode == .autonomous ? OmiColors.warning : OmiColors.textSecondary
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
      .help("\(result.iterationsRun) iteration\(result.iterationsRun == 1 ? "" : "s") • click for held-out pairs")

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

// MARK: - Chat sheet (Live conversation + Practice)

/// Identifies which trained contact the chat sheet is for.
private struct AICloneChatTarget: Identifiable {
  let contact: ImportedContact
  let persona: ContactPersona
  var id: String { contact.id }
}

/// Chat sheet with two tabs: **Live** — the real conversation with this contact (recent
/// history, new messages as they arrive, clone-suggested replies you can edit and send,
/// and a composer for your own messages) — and **Practice**, the original simulator where
/// you type as the contact and see how the clone would reply as you.
private struct AICloneChatSheet: View {
  let contact: ImportedContact
  let persona: ContactPersona

  @Environment(\.dismiss) private var dismiss
  @State private var mode: Mode = .live

  enum Mode: String, CaseIterable {
    case live = "Live"
    case practice = "Practice"
  }

  var body: some View {
    VStack(spacing: 0) {
      header
      Divider().overlay(OmiColors.border)
      // Both tabs stay mounted so switching never drops transcript state or pauses the
      // live poll; only the visible one receives interaction.
      ZStack {
        AICloneLiveChatView(contact: contact, persona: persona)
          .opacity(mode == .live ? 1 : 0)
          .allowsHitTesting(mode == .live)
        AIClonePracticeChatView(contact: contact, persona: persona)
          .opacity(mode == .practice ? 1 : 0)
          .allowsHitTesting(mode == .practice)
      }
    }
    .frame(width: 520, height: 660)
    .background(OmiColors.backgroundPrimary)
    .task {
      // Build the retrieval index so replies get dynamic few-shot examples from the
      // real history (no-op if already built for this contact).
      if let messages = try? await AIClonePage.loadMessages(for: contact, limit: 1500) {
        await AICloneRetrievalService.shared.ensureIndex(
          contactId: contact.id, messages: messages)
      }
    }
  }

  private var header: some View {
    HStack(alignment: .center, spacing: 12) {
      VStack(alignment: .leading, spacing: 3) {
        Text(contact.displayName)
          .scaledFont(size: 16, weight: .semibold)
          .foregroundColor(OmiColors.textPrimary)
        Text(
          mode == .live
            ? "Your real conversation — the clone drafts replies you approve and send"
            : "Type as \(contact.displayName) to see how the clone would reply as you"
        )
        .scaledFont(size: 12, weight: .regular)
        .foregroundColor(OmiColors.textTertiary)
        .fixedSize(horizontal: false, vertical: true)
      }

      Spacer()

      Picker("", selection: $mode) {
        ForEach(Mode.allCases, id: \.self) { Text($0.rawValue).tag($0) }
      }
      .pickerStyle(.segmented)
      .labelsHidden()
      .frame(width: 170)

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
}

// MARK: - Live conversation tab

/// One rendered message in the live transcript. `pending` marks an optimistic local echo
/// (dispatched but not yet observed back in the platform's message store).
private struct AICloneLiveMessage: Identifiable, Equatable {
  let id: String
  let isFromMe: Bool
  let text: String
  let date: Date
  var pending = false
}

/// The real conversation with this contact: recent history, live-updating while the sheet
/// is open (3s poll of the platform store), clone-suggested replies for the latest incoming
/// message, and a composer to send your own messages for real.
private struct AICloneLiveChatView: View {
  let contact: ImportedContact
  let persona: ContactPersona

  private enum SuggestionState: Equatable {
    case idle
    case generating
    case ready
    case failed(String)
  }

  @State private var messages: [AICloneLiveMessage] = []
  /// Keys of every message ever fetched (wider than what's displayed) so poll ticks
  /// re-observing old history never duplicate bubbles.
  @State private var seenKeys: Set<String> = []
  @State private var isLoading = true
  @State private var loadError: String?

  @State private var suggestionState: SuggestionState = .idle
  @State private var suggestionText = ""
  @State private var isSendingSuggestion = false

  @State private var draft = ""
  @State private var isSendingOwn = false
  @State private var sendError: String?
  @FocusState private var inputFocused: Bool

  var body: some View {
    VStack(spacing: 0) {
      transcript
      Divider().overlay(OmiColors.border)
      suggestionSection
      inputBar
    }
    .onAppear {
      inputFocused = true
      // The page's onChange may not have run yet when the sheet content first appears.
      AICloneChatAutomation.shared.activeContactId = contact.id
      publishAutomationSnapshot()
    }
    .onChange(of: messages.count) { publishAutomationSnapshot() }
    .onChange(of: suggestionState) { publishAutomationSnapshot() }
    .onChange(of: isLoading) { publishAutomationSnapshot() }
    .onReceive(NotificationCenter.default.publisher(for: .aiCloneChatSuggestRequested)) { _ in
      guard isPresented else { return }
      suggest()
    }
    .task { await runLiveLoop() }
  }

  /// Whether this view is the currently-presented chat sheet. False once dismissed, even
  /// if macOS keeps the sheet host (and this view's subscriptions) cached for reuse.
  private var isPresented: Bool {
    AICloneChatAutomation.shared.activeContactId == contact.id
  }

  /// Mirror the live tab's state into the automation mailbox so bridge harness actions can
  /// verify the real UI headlessly (local bridge is non-prod only).
  private func publishAutomationSnapshot() {
    guard isPresented else { return }
    let suggestionLabel: String
    switch suggestionState {
    case .idle: suggestionLabel = "idle"
    case .generating: suggestionLabel = "generating"
    case .ready: suggestionLabel = "ready"
    case .failed(let message): suggestionLabel = "failed: \(message)"
    }
    AICloneChatAutomation.shared.liveSnapshot = [
      "open": "true",
      "contactId": contact.id,
      "isLoading": isLoading ? "true" : "false",
      "loadError": loadError ?? "",
      "messageCount": String(messages.count),
      "lastMessages": messages.suffix(5)
        .map { "\($0.isFromMe ? "me" : "them"): \($0.text)" }.joined(separator: "\n"),
      "suggestionState": suggestionLabel,
      "suggestionText": suggestionText,
    ]
  }

  // MARK: Transcript

  private var transcript: some View {
    ScrollViewReader { proxy in
      ScrollView {
        LazyVStack(spacing: 8) {
          if isLoading {
            HStack(spacing: 8) {
              ProgressView().scaleEffect(0.6).tint(.white)
              Text("Loading conversation…")
                .scaledFont(size: 13, weight: .regular)
                .foregroundColor(OmiColors.textTertiary)
            }
            .padding(.top, 40)
          } else if let loadError {
            Text(loadError)
              .scaledFont(size: 12, weight: .regular)
              .foregroundColor(OmiColors.warning)
              .padding(.top, 40)
          } else if messages.isEmpty {
            Text("No messages with \(contact.displayName) yet.")
              .scaledFont(size: 13, weight: .regular)
              .foregroundColor(OmiColors.textTertiary)
              .padding(.top, 40)
          }

          ForEach(Array(messages.enumerated()), id: \.element.id) { index, message in
            VStack(spacing: 8) {
              if showsTimestamp(at: index) {
                Text(message.date.formatted(date: .abbreviated, time: .shortened))
                  .scaledFont(size: 10, weight: .medium)
                  .foregroundColor(OmiColors.textQuaternary)
                  .padding(.top, 6)
              }
              liveBubble(message)
            }
            .id(message.id)
          }

          if let sendError {
            Text(sendError)
              .scaledFont(size: 12, weight: .regular)
              .foregroundColor(OmiColors.warning)
              .frame(maxWidth: .infinity, alignment: .leading)
          }
        }
        .padding(16)
      }
      .onChange(of: messages.count) { scrollToBottom(proxy) }
      .onAppear { scrollToBottom(proxy, animated: false) }
    }
  }

  /// Show a timestamp above the first message and whenever >1h passed since the previous.
  private func showsTimestamp(at index: Int) -> Bool {
    guard index > 0 else { return true }
    return messages[index].date.timeIntervalSince(messages[index - 1].date) > 3600
  }

  private func liveBubble(_ message: AICloneLiveMessage) -> some View {
    HStack(alignment: .bottom, spacing: 6) {
      if message.isFromMe { Spacer(minLength: 60) }

      Text(message.text)
        .scaledFont(size: 14, weight: .regular)
        .foregroundColor(message.isFromMe ? OmiColors.backgroundPrimary : OmiColors.textPrimary)
        .padding(.horizontal, 14)
        .padding(.vertical, 10)
        .background(
          RoundedRectangle(cornerRadius: 16, style: .continuous)
            .fill(message.isFromMe ? OmiColors.textPrimary : OmiColors.backgroundSecondary)
        )
        .opacity(message.pending ? 0.6 : 1)
        .textSelection(.enabled)

      if message.pending {
        Text("Sending…")
          .scaledFont(size: 10, weight: .regular)
          .foregroundColor(OmiColors.textQuaternary)
      }

      if !message.isFromMe { Spacer(minLength: 60) }
    }
    .frame(maxWidth: .infinity, alignment: message.isFromMe ? .trailing : .leading)
  }

  private func scrollToBottom(_ proxy: ScrollViewProxy, animated: Bool = true) {
    guard let last = messages.last else { return }
    if animated {
      withAnimation(.easeOut(duration: 0.2)) { proxy.scrollTo(last.id, anchor: .bottom) }
    } else {
      proxy.scrollTo(last.id, anchor: .bottom)
    }
  }

  // MARK: Suggestion section (the clone's draft for the latest incoming message)

  @ViewBuilder
  private var suggestionSection: some View {
    switch suggestionState {
    case .idle:
      HStack {
        Button(action: suggest) {
          HStack(spacing: 6) {
            Image(systemName: "sparkles")
              .font(.system(size: 11, weight: .semibold))
            Text("Suggest Reply")
              .scaledFont(size: 12, weight: .semibold)
          }
          .foregroundColor(hasIncoming ? OmiColors.textPrimary : OmiColors.textQuaternary)
          .padding(.horizontal, 12)
          .padding(.vertical, 7)
          .background(RoundedRectangle(cornerRadius: 8).stroke(OmiColors.border, lineWidth: 1))
        }
        .buttonStyle(.plain)
        .disabled(!hasIncoming)
        .help("Have the clone draft a reply to \(contact.displayName)'s latest message")

        Spacer()
      }
      .padding(.horizontal, 16)
      .padding(.top, 10)

    case .generating:
      HStack(spacing: 8) {
        ProgressView().scaleEffect(0.55).tint(.white)
        Text("Clone is drafting a reply…")
          .scaledFont(size: 12, weight: .regular)
          .foregroundColor(OmiColors.textTertiary)
        Spacer()
      }
      .padding(.horizontal, 16)
      .padding(.top, 10)

    case .ready:
      VStack(alignment: .leading, spacing: 8) {
        HStack(spacing: 6) {
          Image(systemName: "sparkles")
            .font(.system(size: 10, weight: .semibold))
            .foregroundColor(OmiColors.textTertiary)
          Text("CLONE SUGGESTS — EDIT BEFORE SENDING")
            .scaledFont(size: 9, weight: .semibold)
            .foregroundColor(OmiColors.textQuaternary)
          Spacer()
        }

        TextField("Reply", text: $suggestionText, axis: .vertical)
          .textFieldStyle(.plain)
          .scaledFont(size: 13, weight: .regular)
          .foregroundColor(OmiColors.textPrimary)
          .lineLimit(1...5)
          .padding(.horizontal, 10)
          .padding(.vertical, 8)
          .background(RoundedRectangle(cornerRadius: 8).fill(OmiColors.backgroundTertiary))

        HStack(spacing: 8) {
          Spacer()
          Button(action: { suggestionState = .idle }) {
            Text("Dismiss")
              .scaledFont(size: 12, weight: .semibold)
              .foregroundColor(OmiColors.textSecondary)
              .padding(.horizontal, 12)
              .padding(.vertical, 6)
              .background(RoundedRectangle(cornerRadius: 7).stroke(OmiColors.border, lineWidth: 1))
          }
          .buttonStyle(.plain)

          Button(action: suggest) {
            HStack(spacing: 4) {
              Image(systemName: "arrow.clockwise")
                .font(.system(size: 10, weight: .semibold))
              Text("Redo")
                .scaledFont(size: 12, weight: .semibold)
            }
            .foregroundColor(OmiColors.textSecondary)
            .padding(.horizontal, 12)
            .padding(.vertical, 6)
            .background(RoundedRectangle(cornerRadius: 7).stroke(OmiColors.border, lineWidth: 1))
          }
          .buttonStyle(.plain)

          Button(action: sendSuggestion) {
            HStack(spacing: 4) {
              if isSendingSuggestion {
                ProgressView().scaleEffect(0.45).tint(OmiColors.backgroundPrimary)
              } else {
                Image(systemName: "paperplane.fill")
                  .font(.system(size: 10, weight: .semibold))
              }
              Text("Send")
                .scaledFont(size: 12, weight: .semibold)
            }
            .foregroundColor(OmiColors.backgroundPrimary)
            .padding(.horizontal, 14)
            .padding(.vertical, 6)
            .background(RoundedRectangle(cornerRadius: 7).fill(OmiColors.textPrimary))
          }
          .buttonStyle(.plain)
          .disabled(
            isSendingSuggestion
              || suggestionText.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
        }
      }
      .padding(12)
      .background(
        RoundedRectangle(cornerRadius: 10, style: .continuous).fill(OmiColors.backgroundSecondary)
      )
      .padding(.horizontal, 16)
      .padding(.top, 10)

    case .failed(let message):
      HStack(spacing: 8) {
        Text(message)
          .scaledFont(size: 12, weight: .regular)
          .foregroundColor(OmiColors.warning)
          .lineLimit(2)
        Spacer()
        Button(action: suggest) {
          Text("Retry")
            .scaledFont(size: 12, weight: .semibold)
            .foregroundColor(OmiColors.textPrimary)
            .padding(.horizontal, 12)
            .padding(.vertical, 6)
            .background(RoundedRectangle(cornerRadius: 7).stroke(OmiColors.border, lineWidth: 1))
        }
        .buttonStyle(.plain)
      }
      .padding(.horizontal, 16)
      .padding(.top, 10)
    }
  }

  private var hasIncoming: Bool { messages.contains { !$0.isFromMe } }

  // MARK: Composer (your own real message)

  private var inputBar: some View {
    HStack(spacing: 10) {
      TextField("Message \(contact.displayName)…", text: $draft, axis: .vertical)
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
        .onSubmit { sendOwn() }

      Button(action: sendOwn) {
        Image(systemName: "arrow.up")
          .font(.system(size: 15, weight: .bold))
          .foregroundColor(OmiColors.backgroundPrimary)
          .frame(width: 36, height: 36)
          .background(Circle().fill(canSendOwn ? OmiColors.textPrimary : OmiColors.textQuaternary))
      }
      .buttonStyle(.plain)
      .disabled(!canSendOwn)
      .help("Sends for real to \(contact.displayName)")
    }
    .padding(16)
  }

  private var canSendOwn: Bool {
    !isSendingOwn && !draft.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
  }

  // MARK: Live loop (initial load + poll)

  private func runLiveLoop() async {
    await loadInitial()
    // Also stop when this sheet is no longer the presented one — .task cancellation is
    // not guaranteed on macOS when the dismissed sheet host is cached for reuse.
    while !Task.isCancelled, isPresented {
      try? await Task.sleep(nanoseconds: 3_000_000_000)
      await refresh()
    }
  }

  private func loadInitial() async {
    do {
      let history = try await AIClonePage.loadMessages(for: contact, limit: 200)
      let ordered = history.sorted { $0.date < $1.date }
      var loaded: [AICloneLiveMessage] = []
      for message in ordered {
        guard let entry = register(message) else { continue }
        loaded.append(entry)
      }
      // Track keys for the full fetch window but only render the recent tail.
      messages = Array(loaded.suffix(60))
      isLoading = false
    } catch {
      loadError = error.localizedDescription
      isLoading = false
    }
  }

  /// Poll tick: append any messages not seen yet. A from-me arrival that matches an
  /// optimistic pending bubble replaces it (the real store echo has the authoritative date).
  private func refresh() async {
    guard let history = try? await AIClonePage.loadMessages(for: contact, limit: 50) else {
      return
    }
    var appendedIncoming = false
    for message in history.sorted(by: { $0.date < $1.date }) {
      guard let entry = register(message) else { continue }
      if entry.isFromMe,
        let pendingIdx = messages.firstIndex(where: { $0.pending && $0.text == entry.text })
      {
        messages.remove(at: pendingIdx)
      }
      messages.append(entry)
      if !entry.isFromMe { appendedIncoming = true }
    }
    // A new incoming message while the sheet is open → auto-draft a suggestion, but never
    // stomp a draft the user may already be editing.
    if appendedIncoming, suggestionState == .idle {
      suggest()
    }
  }

  /// Dedupe gate: returns a renderable entry only the first time a message is observed.
  private func register(_ message: ImportedMessage) -> AICloneLiveMessage? {
    let key =
      "\(Int(message.date.timeIntervalSince1970))|\(message.isFromMe ? 1 : 0)|\(message.text)"
    guard !seenKeys.contains(key) else { return nil }
    seenKeys.insert(key)
    return AICloneLiveMessage(
      id: key, isFromMe: message.isFromMe, text: message.text, date: message.date)
  }

  // MARK: Actions

  /// Ask the clone for a reply to the latest incoming burst, with the real conversation
  /// tail as context.
  private func suggest() {
    guard suggestionState != .generating else { return }
    let turns = messages.filter { !$0.pending }.map { (isFromMe: $0.isFromMe, text: $0.text) }
    guard let burst = AICloneLiveChat.latestIncomingBurst(in: turns) else { return }
    suggestionState = .generating
    sendError = nil
    Task {
      do {
        let reply = try await AIClonePersonaService.shared.respond(
          as: persona, to: burst.incoming, context: burst.context)
        suggestionText = reply
        suggestionState = .ready
      } catch {
        suggestionState = .failed(error.localizedDescription)
      }
    }
  }

  private func sendSuggestion() {
    let text = suggestionText.trimmingCharacters(in: .whitespacesAndNewlines)
    guard !text.isEmpty, !isSendingSuggestion else { return }
    isSendingSuggestion = true
    sendError = nil
    Task {
      do {
        // Multi-bubble suggestions go out as separate messages, like a real burst.
        try await AICloneSendModeService.shared.sendBubbles(
          contactId: contact.id, displayName: contact.displayName, text: text, mode: .manual)
        for bubble in AICloneReplyPresentation.bubbles(from: text) {
          appendOptimistic(text: bubble)
        }
        suggestionText = ""
        suggestionState = .idle
      } catch {
        sendError = error.localizedDescription
      }
      isSendingSuggestion = false
    }
  }

  private func sendOwn() {
    let text = draft.trimmingCharacters(in: .whitespacesAndNewlines)
    guard !text.isEmpty, !isSendingOwn else { return }
    isSendingOwn = true
    sendError = nil
    Task {
      do {
        try await AICloneSendModeService.shared.send(
          contactId: contact.id, displayName: contact.displayName, text: text, mode: .manual)
        appendOptimistic(text: text)
        draft = ""
      } catch {
        sendError = error.localizedDescription
      }
      isSendingOwn = false
    }
  }

  /// Local echo shown immediately after a successful dispatch; the next poll tick swaps it
  /// for the real store entry.
  private func appendOptimistic(text: String) {
    messages.append(
      AICloneLiveMessage(
        id: "local-\(UUID().uuidString)", isFromMe: true, text: text, date: Date(),
        pending: true))
  }
}

/// Pure helpers for the live chat, kept off the view for unit testing.
enum AICloneLiveChat {
  /// The most recent run of consecutive incoming bubbles — joined newline-style like the
  /// multi-bubble bursts `respond()` is trained on — plus up to 8 turns of preceding
  /// context, shaped for `respond(as:to:context:)`. Nil when the thread has no incoming
  /// messages at all.
  static func latestIncomingBurst(
    in turns: [(isFromMe: Bool, text: String)]
  ) -> (incoming: String, context: [ConversationTurn])? {
    guard let last = turns.lastIndex(where: { !$0.isFromMe }) else { return nil }
    var start = last
    while start > 0, !turns[start - 1].isFromMe { start -= 1 }
    let incoming = turns[start...last].map(\.text).joined(separator: "\n")
    let context = turns[..<start].suffix(8).map {
      ConversationTurn(isFromMe: $0.isFromMe, text: $0.text)
    }
    return (incoming, Array(context))
  }
}

// MARK: - Practice tab (simulator)

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
private struct AIClonePracticeChatView: View {
  let contact: ImportedContact
  let persona: ContactPersona

  @State private var draft = ""
  @State private var messages: [AIClonePreviewMessage] = []
  @State private var isResponding = false
  @State private var errorMessage: String?
  /// Reply bubbles already dispatched to the real contact (manual send).
  @State private var sentMessageIds: Set<UUID> = []
  /// Reply bubbles with a send in flight.
  @State private var sendingMessageIds: Set<UUID> = []
  @State private var sendError: String?
  @FocusState private var inputFocused: Bool

  /// Whether the clone can actually send on this contact's platform (WhatsApp can't).
  private var platformCanSend: Bool { AIClonePlatform.of(contactId: contact.id).canSend }

  var body: some View {
    VStack(spacing: 0) {
      transcript
      Divider().overlay(OmiColors.border)
      inputBar
    }
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

          if let sendError {
            Text(sendError)
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
    VStack(alignment: isReply ? .trailing : .leading, spacing: 4) {
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

      // Manual send: each predicted reply can be dispatched to the real contact.
      if isReply && platformCanSend {
        replySendControl(for: message)
      }
    }
  }

  @ViewBuilder
  private func replySendControl(for message: AIClonePreviewMessage) -> some View {
    if sentMessageIds.contains(message.id) {
      HStack(spacing: 4) {
        Image(systemName: "checkmark.circle.fill")
          .font(.system(size: 10, weight: .semibold))
        Text("Sent to \(contact.displayName)")
          .scaledFont(size: 11, weight: .medium)
      }
      .foregroundColor(OmiColors.success)
      .padding(.trailing, 4)
    } else if sendingMessageIds.contains(message.id) {
      HStack(spacing: 5) {
        ProgressView().scaleEffect(0.5).tint(.white)
        Text("Sending…")
          .scaledFont(size: 11, weight: .medium)
          .foregroundColor(OmiColors.textTertiary)
      }
      .padding(.trailing, 4)
    } else {
      Button(action: { sendForReal(message) }) {
        HStack(spacing: 4) {
          Image(systemName: "paperplane.fill")
            .font(.system(size: 9, weight: .semibold))
          Text("Send for Real")
            .scaledFont(size: 11, weight: .semibold)
        }
        .foregroundColor(OmiColors.textSecondary)
        .padding(.horizontal, 9)
        .padding(.vertical, 4)
        .background(RoundedRectangle(cornerRadius: 6).stroke(OmiColors.border, lineWidth: 1))
      }
      .buttonStyle(.plain)
      .padding(.trailing, 4)
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
        for bubble in AICloneReplyPresentation.bubbles(from: reply) {
          messages.append(AIClonePreviewMessage(kind: .reply, text: bubble))
        }
      } catch {
        errorMessage = error.localizedDescription
      }
      isResponding = false
    }
  }

  /// Manually dispatch one predicted reply bubble to the real contact via the platform send
  /// service. This is the only send path in Manual mode — the user explicitly taps it.
  private func sendForReal(_ message: AIClonePreviewMessage) {
    guard message.kind == .reply, !sendingMessageIds.contains(message.id),
      !sentMessageIds.contains(message.id)
    else { return }
    sendingMessageIds.insert(message.id)
    sendError = nil
    Task {
      do {
        try await AICloneSendModeService.shared.send(
          contactId: contact.id, displayName: contact.displayName, text: message.text,
          mode: .manual)
        sentMessageIds.insert(message.id)
      } catch {
        sendError = error.localizedDescription
      }
      sendingMessageIds.remove(message.id)
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

/// Splits a clone reply (newline-joined bubbles) into the separate message bubbles the
/// preview transcript renders — one bubble per line, blanks dropped.
enum AICloneReplyPresentation {
  static func bubbles(from reply: String) -> [String] {
    reply.components(separatedBy: "\n")
      .map { $0.trimmingCharacters(in: .whitespaces) }
      .filter { !$0.isEmpty }
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
  let contact: ImportedContact
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
  let contact: ImportedContact
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

// MARK: - Pending draft row (Approve / Edit / Reject)

/// One Draft-Review suggestion: the incoming message, the clone's proposed reply (editable
/// in place), and Approve / Reject actions. Approving sends for real via the send service.
private struct AIClonePendingDraftRow: View {
  let draft: AIClonePendingDraft
  @ObservedObject private var sendMode = AICloneSendModeService.shared
  @State private var editedText: String
  @State private var isEditing = false

  init(draft: AIClonePendingDraft) {
    self.draft = draft
    _editedText = State(initialValue: draft.draftText)
  }

  var body: some View {
    VStack(alignment: .leading, spacing: 8) {
      HStack(spacing: 6) {
        Text(draft.contactDisplayName)
          .scaledFont(size: 13, weight: .semibold)
          .foregroundColor(OmiColors.textPrimary)
          .lineLimit(1)
        Spacer()
        Text(draft.createdAt, style: .relative)
          .scaledFont(size: 10, weight: .regular)
          .foregroundColor(OmiColors.textQuaternary)
      }

      Text("They said: \(draft.incomingText)")
        .scaledFont(size: 12, weight: .regular)
        .foregroundColor(OmiColors.textTertiary)
        .lineLimit(2)
        .fixedSize(horizontal: false, vertical: true)

      if isEditing {
        TextField("Reply", text: $editedText, axis: .vertical)
          .textFieldStyle(.plain)
          .scaledFont(size: 13, weight: .regular)
          .foregroundColor(OmiColors.textPrimary)
          .lineLimit(1...5)
          .padding(.horizontal, 10)
          .padding(.vertical, 8)
          .background(RoundedRectangle(cornerRadius: 8).fill(OmiColors.backgroundTertiary))
      } else {
        Text(editedText)
          .scaledFont(size: 13, weight: .regular)
          .foregroundColor(OmiColors.textPrimary)
          .fixedSize(horizontal: false, vertical: true)
          .frame(maxWidth: .infinity, alignment: .leading)
          .padding(.horizontal, 10)
          .padding(.vertical, 8)
          .background(RoundedRectangle(cornerRadius: 8).fill(OmiColors.backgroundTertiary))
      }

      HStack(spacing: 8) {
        Spacer()
        Button(action: { isEditing.toggle() }) {
          Text(isEditing ? "Done" : "Edit")
            .scaledFont(size: 12, weight: .semibold)
            .foregroundColor(OmiColors.textSecondary)
            .padding(.horizontal, 12)
            .padding(.vertical, 6)
            .background(RoundedRectangle(cornerRadius: 7).stroke(OmiColors.border, lineWidth: 1))
        }
        .buttonStyle(.plain)

        Button(action: { sendMode.rejectDraft(draft) }) {
          Text("Reject")
            .scaledFont(size: 12, weight: .semibold)
            .foregroundColor(OmiColors.warning)
            .padding(.horizontal, 12)
            .padding(.vertical, 6)
            .background(RoundedRectangle(cornerRadius: 7).stroke(OmiColors.warning.opacity(0.5), lineWidth: 1))
        }
        .buttonStyle(.plain)

        Button(action: { sendMode.approveDraft(draft, editedText: editedText) }) {
          Text("Approve & Send")
            .scaledFont(size: 12, weight: .semibold)
            .foregroundColor(OmiColors.backgroundPrimary)
            .padding(.horizontal, 12)
            .padding(.vertical, 6)
            .background(RoundedRectangle(cornerRadius: 7).fill(OmiColors.textPrimary))
        }
        .buttonStyle(.plain)
        .disabled(editedText.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
      }
    }
    .padding(12)
    .frame(maxWidth: .infinity, alignment: .leading)
    .background(
      RoundedRectangle(cornerRadius: 10, style: .continuous).fill(OmiColors.backgroundPrimary))
    .overlay(
      RoundedRectangle(cornerRadius: 10, style: .continuous).stroke(OmiColors.border, lineWidth: 1))
  }
}

// MARK: - Recent Sent Messages log

private struct AICloneSentLogSheet: View {
  @ObservedObject private var sendMode = AICloneSendModeService.shared
  @Environment(\.dismiss) private var dismiss

  var body: some View {
    VStack(spacing: 0) {
      HStack {
        VStack(alignment: .leading, spacing: 3) {
          Text("Recent Sent Messages")
            .scaledFont(size: 16, weight: .semibold)
            .foregroundColor(OmiColors.textPrimary)
          Text("Everything the clone sent — manual, approved, or autonomous")
            .scaledFont(size: 12, weight: .regular)
            .foregroundColor(OmiColors.textTertiary)
        }
        Spacer()
        if !sendMode.sentLog.isEmpty {
          Button(action: { sendMode.clearSentLog() }) {
            Text("Clear")
              .scaledFont(size: 12, weight: .semibold)
              .foregroundColor(OmiColors.textSecondary)
          }
          .buttonStyle(.plain)
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
      .padding(16)
      Divider().overlay(OmiColors.border)

      if sendMode.sentLog.isEmpty {
        VStack(spacing: 10) {
          Image(systemName: "paperplane")
            .font(.system(size: 30, weight: .regular))
            .foregroundColor(OmiColors.textQuaternary)
          Text("Nothing sent yet")
            .scaledFont(size: 14, weight: .semibold)
            .foregroundColor(OmiColors.textSecondary)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
      } else {
        ScrollView {
          LazyVStack(spacing: 8) {
            ForEach(sendMode.sentLog) { entry in
              sentRow(entry)
            }
          }
          .padding(16)
        }
      }
    }
    .frame(width: 480, height: 560)
    .background(OmiColors.backgroundPrimary)
  }

  private func sentRow(_ entry: AICloneSentLogEntry) -> some View {
    VStack(alignment: .leading, spacing: 6) {
      HStack(spacing: 6) {
        Text(entry.contactDisplayName)
          .scaledFont(size: 13, weight: .semibold)
          .foregroundColor(OmiColors.textPrimary)
          .lineLimit(1)
        modeTag(entry.mode)
        Spacer()
        Text(entry.timestamp, style: .relative)
          .scaledFont(size: 10, weight: .regular)
          .foregroundColor(OmiColors.textQuaternary)
      }
      Text(entry.text)
        .scaledFont(size: 13, weight: .regular)
        .foregroundColor(OmiColors.textSecondary)
        .fixedSize(horizontal: false, vertical: true)
        .frame(maxWidth: .infinity, alignment: .leading)
        .textSelection(.enabled)
    }
    .padding(12)
    .frame(maxWidth: .infinity, alignment: .leading)
    .background(
      RoundedRectangle(cornerRadius: 10, style: .continuous).fill(OmiColors.backgroundSecondary))
  }

  private func modeTag(_ mode: SendMode) -> some View {
    Text(mode.fullLabel)
      .scaledFont(size: 9, weight: .semibold)
      .foregroundColor(mode == .autonomous ? OmiColors.warning : OmiColors.textTertiary)
      .padding(.horizontal, 6)
      .padding(.vertical, 2)
      .background(
        Capsule().fill(
          (mode == .autonomous ? OmiColors.warning : OmiColors.textTertiary).opacity(0.14)))
  }
}

// MARK: - WhatsApp linking sheet (QR scan via Linked Devices)

/// Drives the WhatsApp linking flow against the local Baileys sidecar: starts the sidecar,
/// shows the QR to scan from the phone (WhatsApp → Settings → Linked Devices → Link a
/// Device), polls until linked, then shows the linked number. Session persists on disk, so
/// this is one-time unless the user unlinks.
private struct WhatsAppLinkSheet: View {
  @ObservedObject private var link = WhatsAppLinkModel.shared
  @Environment(\.dismiss) private var dismiss

  var body: some View {
    VStack(spacing: 0) {
      header
      Divider().overlay(OmiColors.border)
      content
        .frame(maxWidth: .infinity, maxHeight: .infinity)
      Divider().overlay(OmiColors.border)
      footer
    }
    .frame(width: 420, height: 560)
    .background(OmiColors.backgroundPrimary)
    .task {
      // Kick off (or resume) linking, then poll while the sheet is open. The poll drives
      // QR refreshes (WhatsApp rotates codes every ~20s) and the linked transition.
      _ = await WhatsAppSendService.shared.startLinking()
      while !Task.isCancelled {
        let state = await WhatsAppSendService.shared.refreshStatus()
        if state.isLinked {
          // Live listener can attach now that a linked session exists.
          AICloneSendModeService.shared.startWhatsAppListenerIfLinked()
        }
        try? await Task.sleep(nanoseconds: 2_000_000_000)
      }
    }
  }

  private var header: some View {
    HStack(alignment: .top, spacing: 12) {
      VStack(alignment: .leading, spacing: 3) {
        Text("Link WhatsApp")
          .scaledFont(size: 16, weight: .semibold)
          .foregroundColor(OmiColors.textPrimary)
        Text("Connects this Mac as a linked device, like WhatsApp Web")
          .scaledFont(size: 12, weight: .regular)
          .foregroundColor(OmiColors.textTertiary)
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

  @ViewBuilder
  private var content: some View {
    switch link.state {
    case .stopped, .starting:
      statusStack(spinner: true, title: "Starting the WhatsApp connector…", detail: nil)

    case .connecting:
      statusStack(
        spinner: true, title: "Contacting WhatsApp…",
        detail: "Generating a QR code (or resuming your saved session).")

    case .unlinked, .loggedOut:
      VStack(spacing: 14) {
        Image(systemName: "qrcode")
          .font(.system(size: 34, weight: .regular))
          .foregroundColor(OmiColors.textQuaternary)
        Text(
          link.state == .loggedOut
            ? "This device was unlinked from your phone."
            : "Not linked yet.")
          .scaledFont(size: 13, weight: .regular)
          .foregroundColor(OmiColors.textTertiary)
        Button(action: { Task { await WhatsAppSendService.shared.startLinking() } }) {
          Text("Generate QR Code")
            .scaledFont(size: 13, weight: .semibold)
            .foregroundColor(OmiColors.backgroundPrimary)
            .padding(.horizontal, 18)
            .padding(.vertical, 8)
            .background(RoundedRectangle(cornerRadius: 8).fill(OmiColors.textPrimary))
        }
        .buttonStyle(.plain)
      }

    case .waitingScan(let qrDataUrl):
      VStack(spacing: 14) {
        if let image = Self.image(fromDataUrl: qrDataUrl) {
          Image(nsImage: image)
            .interpolation(.none)
            .resizable()
            .scaledToFit()
            .frame(width: 240, height: 240)
            .padding(10)
            .background(RoundedRectangle(cornerRadius: 12).fill(Color.white))
        } else {
          statusStack(spinner: true, title: "Preparing QR code…", detail: nil)
        }
        VStack(spacing: 4) {
          Text("Scan with your phone")
            .scaledFont(size: 14, weight: .semibold)
            .foregroundColor(OmiColors.textPrimary)
          Text("WhatsApp → Settings → Linked Devices → Link a Device")
            .scaledFont(size: 12, weight: .regular)
            .foregroundColor(OmiColors.textTertiary)
        }
      }

    case .linked(let phone):
      VStack(spacing: 12) {
        Image(systemName: "checkmark.circle.fill")
          .font(.system(size: 36, weight: .regular))
          .foregroundColor(OmiColors.success)
        Text("Linked as \(phone.isEmpty ? "your account" : "+\(phone)")")
          .scaledFont(size: 15, weight: .semibold)
          .foregroundColor(OmiColors.textPrimary)
        Text("The clone can now send and receive WhatsApp messages on this Mac.")
          .scaledFont(size: 12, weight: .regular)
          .foregroundColor(OmiColors.textTertiary)
          .multilineTextAlignment(.center)
          .frame(maxWidth: 300)
        Button(action: { Task { await WhatsAppSendService.shared.logout() } }) {
          Text("Unlink")
            .scaledFont(size: 12, weight: .semibold)
            .foregroundColor(OmiColors.warning)
            .padding(.horizontal, 14)
            .padding(.vertical, 7)
            .background(
              RoundedRectangle(cornerRadius: 8).stroke(
                OmiColors.warning.opacity(0.5), lineWidth: 1))
        }
        .buttonStyle(.plain)
        .padding(.top, 6)
      }

    case .error(let message):
      VStack(spacing: 12) {
        Image(systemName: "exclamationmark.triangle")
          .font(.system(size: 30, weight: .regular))
          .foregroundColor(OmiColors.warning)
        Text(message)
          .scaledFont(size: 13, weight: .regular)
          .foregroundColor(OmiColors.textSecondary)
          .multilineTextAlignment(.center)
          .frame(maxWidth: 320)
        Button(action: { Task { await WhatsAppSendService.shared.startLinking() } }) {
          Text("Try Again")
            .scaledFont(size: 13, weight: .semibold)
            .foregroundColor(OmiColors.textPrimary)
            .padding(.horizontal, 18)
            .padding(.vertical, 8)
            .background(RoundedRectangle(cornerRadius: 8).stroke(OmiColors.border, lineWidth: 1))
        }
        .buttonStyle(.plain)
      }
    }
  }

  private var footer: some View {
    HStack(alignment: .top, spacing: 8) {
      Image(systemName: "exclamationmark.shield")
        .font(.system(size: 11, weight: .semibold))
        .foregroundColor(OmiColors.textQuaternary)
        .padding(.top, 1)
      Text(
        "WhatsApp has no official API for personal accounts — this uses an unofficial "
          + "connection through Linked Devices. Automated messaging can put an account "
          + "at risk of being flagged; keep automated replies conservative."
      )
      .scaledFont(size: 11, weight: .regular)
      .foregroundColor(OmiColors.textQuaternary)
      .fixedSize(horizontal: false, vertical: true)
    }
    .padding(14)
  }

  private func statusStack(spinner: Bool, title: String, detail: String?) -> some View {
    VStack(spacing: 12) {
      if spinner {
        ProgressView().scaleEffect(1.1).tint(.white)
      }
      Text(title)
        .scaledFont(size: 14, weight: .medium)
        .foregroundColor(OmiColors.textSecondary)
      if let detail {
        Text(detail)
          .scaledFont(size: 12, weight: .regular)
          .foregroundColor(OmiColors.textTertiary)
          .multilineTextAlignment(.center)
          .frame(maxWidth: 300)
      }
    }
  }

  /// Decode a `data:image/png;base64,…` URL (the sidecar's QR payload) into an NSImage.
  static func image(fromDataUrl dataUrl: String) -> NSImage? {
    guard let comma = dataUrl.firstIndex(of: ","),
      let data = Data(base64Encoded: String(dataUrl[dataUrl.index(after: comma)...]))
    else { return nil }
    return NSImage(data: data)
  }
}

#Preview {
  AIClonePage()
}
