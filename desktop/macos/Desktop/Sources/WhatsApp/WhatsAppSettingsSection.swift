import SwiftUI
import OmiTheme

struct WhatsAppSettingsSection: View {
  @ObservedObject private var state = WhatsAppState.shared
  @ObservedObject private var replySettings = WhatsAppReplySettings.shared
  @ObservedObject private var replyCoordinator = WhatsAppReplyCoordinator.shared
  @ObservedObject private var toneProfile = WhatsAppToneProfile.shared
  @ObservedObject private var contactResolver = WhatsAppContactResolver.shared
  @ObservedObject private var memoryImport = WhatsAppMemoryImportService.shared
  @Binding var highlightedSettingId: String?
  let includePendingDrafts: Bool

  init(highlightedSettingId: Binding<String?>, includePendingDrafts: Bool = true) {
    self._highlightedSettingId = highlightedSettingId
    self.includePendingDrafts = includePendingDrafts
  }

  @State private var showConnectSheet = false
  @State private var isDisconnecting = false
  @State private var isCheckingHealth = false
  @State private var isRebuildingToneProfile = false
  @State private var healthSummary: String?
  @State private var allowlistInput = ""
  @State private var allowlistError: String?
  @State private var draftEdits: [String: String] = [:]

  private var showsDeveloperDiagnostics: Bool {
    AppBuild.isNonProduction
  }

  private var showsConnectedSettings: Bool {
    state.connectionState.isConnected
  }

  var body: some View {
    VStack(spacing: 20) {
      connectionCard
      if showsConnectedSettings {
        replyModeCard
        if includePendingDrafts {
          pendingDraftsCard
        }
        allowlistCard
        guardrailsCard
        brainSyncCard
        if showsDeveloperDiagnostics {
          auditCard
          detailsCard
        }
      }
    }
    .sheet(isPresented: $showConnectSheet) {
      WhatsAppConnectView(onDismiss: { showConnectSheet = false })
    }
    .task {
      await WhatsAppService.shared.resumeIfAuthenticated()
      WhatsAppContactResolver.shared.scheduleRefresh()
    }
    .onChange(of: replyCoordinator.pendingDrafts) { _, drafts in
      let activeDraftIds = Set(drafts.map(\.id))
      draftEdits = draftEdits.filter { activeDraftIds.contains($0.key) }
    }
  }

  private var connectionCard: some View {
    card(settingId: "whatsapp.connection") {
      VStack(alignment: .leading, spacing: 16) {
        HStack(spacing: 16) {
          Circle()
            .fill(statusColor)
            .frame(width: 12, height: 12)
            .shadow(color: statusColor.opacity(0.45), radius: 6)

          ConnectorBrandIcon(brand: .whatsapp, size: 32, cornerRadius: 8)

          VStack(alignment: .leading, spacing: 4) {
            Text("WhatsApp")
              .scaledFont(size: 16, weight: .semibold)
              .foregroundColor(OmiColors.textPrimary)

            Text(state.connectionState.statusText)
              .scaledFont(size: 13)
              .foregroundColor(statusTextColor)
          }

          Spacer()

          if state.connectionState.isConnected {
            Button(isDisconnecting ? "Disconnecting..." : "Disconnect") {
              Task { await disconnect() }
            }
            .buttonStyle(OnboardingCardButtonStyle(isPrimary: false))
            .disabled(isDisconnecting)
          } else {
            Button("Connect") {
              showConnectSheet = true
            }
            .buttonStyle(OnboardingCardButtonStyle(isPrimary: true))
          }
        }

        Text("Scan a QR code to link your WhatsApp account as a linked device. Omi can draft replies by default, and only auto-sends for contacts you explicitly allow.")
          .scaledFont(size: 13)
          .foregroundColor(OmiColors.textTertiary)
          .fixedSize(horizontal: false, vertical: true)
      }
    }
  }

  private var replyModeCard: some View {
    card(settingId: "whatsapp.mode") {
      VStack(alignment: .leading, spacing: 16) {
        HStack(alignment: .center) {
          VStack(alignment: .leading, spacing: 4) {
            Text("Reply Mode")
              .scaledFont(size: 15, weight: .semibold)
              .foregroundColor(OmiColors.textPrimary)
            Text("Draft is the default. Allowlisted direct chats can auto-send.")
              .scaledFont(size: 12)
              .foregroundColor(OmiColors.textTertiary)
          }
          Spacer()
          Picker("", selection: $replySettings.mode) {
            ForEach(WhatsAppReplyMode.allCases) { mode in
              Text(mode.title).tag(mode)
            }
          }
          .pickerStyle(.segmented)
          .frame(width: 220)
        }

        Toggle("Kill switch: pause all WhatsApp sends", isOn: $replySettings.killSwitchEnabled)
          .toggleStyle(.switch)
          .scaledFont(size: 13, weight: .medium)
          .foregroundColor(OmiColors.textSecondary)
          .modifier(SettingHighlightModifier(settingId: "whatsapp.killswitch", highlightedSettingId: $highlightedSettingId))
      }
    }
  }

  @ViewBuilder
  private var pendingDraftsCard: some View {
    card(settingId: "whatsapp.drafts") {
      VStack(alignment: .leading, spacing: 14) {
        HStack {
          VStack(alignment: .leading, spacing: 4) {
            Text("Pending Drafts")
              .scaledFont(size: 15, weight: .semibold)
              .foregroundColor(OmiColors.textPrimary)
            Text("Review drafted replies before they are sent.")
              .scaledFont(size: 12)
              .foregroundColor(OmiColors.textTertiary)
          }
          Spacer()
          Text("\(replyCoordinator.pendingDrafts.count)")
            .scaledFont(size: 13, weight: .semibold)
            .foregroundColor(OmiColors.textSecondary)
        }

        if replyCoordinator.pendingDrafts.isEmpty {
          Text("No pending WhatsApp drafts")
            .scaledFont(size: 12)
            .foregroundColor(OmiColors.textTertiary)
        } else {
          ForEach(replyCoordinator.pendingDrafts) { draft in
            draftRow(draft)
          }
        }

        if let lastDraftFailure = replyCoordinator.lastDraftFailure {
          Text(lastDraftFailure)
            .scaledFont(size: 12)
            .foregroundColor(OmiColors.warning)
            .fixedSize(horizontal: false, vertical: true)
        }
      }
    }
  }

  private var allowlistCard: some View {
    card(settingId: "whatsapp.allowlist") {
      VStack(alignment: .leading, spacing: 14) {
        VStack(alignment: .leading, spacing: 4) {
          Text("Auto-Send Allowlist")
            .scaledFont(size: 15, weight: .semibold)
            .foregroundColor(OmiColors.textPrimary)
          Text("Auto replies are restricted to contacts you add by name, phone number, or JID.")
            .scaledFont(size: 12)
            .foregroundColor(OmiColors.textTertiary)
        }

        HStack(spacing: 10) {
          TextField("Contact name, phone, or JID", text: $allowlistInput)
            .textFieldStyle(.roundedBorder)
          Button("Add") {
            Task { await addAllowlistEntry() }
          }
          .buttonStyle(OnboardingCardButtonStyle(isPrimary: false))
        }

        if let allowlistError {
          Text(allowlistError)
            .scaledFont(size: 12)
            .foregroundColor(OmiColors.warning)
            .fixedSize(horizontal: false, vertical: true)
        }

        if replySettings.allowlistedJids.isEmpty {
          Text("No contacts allowlisted yet")
            .scaledFont(size: 12)
            .foregroundColor(OmiColors.textTertiary)
        } else {
          ForEach(Array(replySettings.allowlistedJids).sorted(), id: \.self) { jid in
            HStack {
              VStack(alignment: .leading, spacing: 2) {
                Text(contactResolver.displayName(for: jid))
                  .scaledFont(size: 12, weight: .medium)
                  .foregroundColor(OmiColors.textSecondary)
                  .lineLimit(1)
                Text(contactResolver.detailLabel(for: jid))
                  .scaledFont(size: 11)
                  .foregroundColor(OmiColors.textTertiary)
                  .lineLimit(1)
                  .truncationMode(.middle)
              }
              Spacer()
              Button("Remove") {
                replySettings.removeAllowlistedJid(jid)
              }
              .buttonStyle(.plain)
              .foregroundColor(OmiColors.warning)
            }
          }
        }
      }
    }
  }

  private var guardrailsCard: some View {
    card(settingId: "whatsapp.guardrails") {
      VStack(alignment: .leading, spacing: 16) {
        Text("Guardrails")
          .scaledFont(size: 15, weight: .semibold)
          .foregroundColor(OmiColors.textPrimary)

        Stepper("Auto-send cap: \(replySettings.rateLimitPerHour) per contact/hour", value: $replySettings.rateLimitPerHour, in: 1...20)
          .scaledFont(size: 13)
          .foregroundColor(OmiColors.textSecondary)

        Toggle("Quiet hours force Draft mode", isOn: $replySettings.quietHoursEnabled)
          .toggleStyle(.switch)
          .scaledFont(size: 13)
          .foregroundColor(OmiColors.textSecondary)

        if replySettings.quietHoursEnabled {
          HStack {
            Stepper("Start: \(replySettings.quietHoursStart):00", value: $replySettings.quietHoursStart, in: 0...23)
            Stepper("End: \(replySettings.quietHoursEnd):00", value: $replySettings.quietHoursEnd, in: 0...23)
          }
          .scaledFont(size: 12)
          .foregroundColor(OmiColors.textTertiary)
        }

        Toggle("Match my WhatsApp writing style", isOn: $replySettings.toneMatchEnabled)
          .toggleStyle(.switch)
          .scaledFont(size: 13)
          .foregroundColor(OmiColors.textSecondary)

        HStack {
          Text(toneProfile.snapshot?.styleGuide ?? "Tone profile has not been built yet")
            .scaledFont(size: 12)
            .foregroundColor(OmiColors.textTertiary)
            .lineLimit(3)
          Spacer()
          Button(isRebuildingToneProfile || toneProfile.isRebuilding ? "Rebuilding..." : "Rebuild Tone") {
            Task { await rebuildToneProfile() }
          }
          .buttonStyle(OnboardingCardButtonStyle(isPrimary: false))
          .disabled(isRebuildingToneProfile || toneProfile.isRebuilding)
        }

        if let snapshot = toneProfile.snapshot {
          Text("Tone rebuilt \(formatDate(snapshot.generatedAt)) from \(snapshot.sampleCount) sent messages")
            .scaledFont(size: 11)
            .foregroundColor(OmiColors.textTertiary)
        }
        if let error = toneProfile.lastError, !error.isEmpty {
          Text(error)
            .scaledFont(size: 11)
            .foregroundColor(OmiColors.warning)
            .lineLimit(2)
        }
      }
    }
  }

  private var brainSyncCard: some View {
    card(settingId: "whatsapp.brain-sync") {
      VStack(alignment: .leading, spacing: 14) {
        VStack(alignment: .leading, spacing: 4) {
          Text("Omi Brain Sync")
            .scaledFont(size: 15, weight: .semibold)
            .foregroundColor(OmiColors.textPrimary)
          Text("When enabled, synced WhatsApp history is uploaded to Omi memory so chat and replies can use it for personal context.")
            .scaledFont(size: 12)
            .foregroundColor(OmiColors.textTertiary)
            .fixedSize(horizontal: false, vertical: true)
        }

        Toggle("Sync WhatsApp with Omi brain", isOn: $memoryImport.syncWithBrainEnabled)
          .toggleStyle(.switch)
          .scaledFont(size: 13, weight: .medium)
          .foregroundColor(OmiColors.textSecondary)

        HStack {
          if memoryImport.lastSourceCount > 0 || memoryImport.lastMemoryCount > 0 {
            Text("\(memoryImport.lastSourceCount.formatted()) messages scanned - \(memoryImport.lastMemoryCount.formatted()) memories saved")
              .scaledFont(size: 12)
              .foregroundColor(OmiColors.textTertiary)
          } else {
            Text("No WhatsApp brain sync has run yet")
              .scaledFont(size: 12)
              .foregroundColor(OmiColors.textTertiary)
          }

          Spacer()

          Button(memoryImport.isSyncing ? "Syncing..." : "Sync Now") {
            Task { _ = await memoryImport.enableAndSyncNow() }
          }
          .buttonStyle(OnboardingCardButtonStyle(isPrimary: false))
          .disabled(memoryImport.isSyncing)

          Button("Retry All") {
            Task { _ = await memoryImport.retryAllMessages() }
          }
          .buttonStyle(.plain)
          .foregroundColor(OmiColors.warning)
          .disabled(memoryImport.isSyncing || !memoryImport.syncWithBrainEnabled)
        }

        if let status = memoryImport.lastStatus, !status.isEmpty {
          Text(status)
            .scaledFont(size: 11)
            .foregroundColor(OmiColors.textTertiary)
            .fixedSize(horizontal: false, vertical: true)
        }
        if let error = memoryImport.lastError, !error.isEmpty {
          Text(error)
            .scaledFont(size: 11)
            .foregroundColor(OmiColors.warning)
            .lineLimit(2)
        }
      }
    }
  }

  private var auditCard: some View {
    card(settingId: "whatsapp.audit") {
      VStack(alignment: .leading, spacing: 14) {
        Text("Audit Log")
          .scaledFont(size: 15, weight: .semibold)
          .foregroundColor(OmiColors.textPrimary)

        let entries = replySettings.recentAuditEntries(limit: 8)
        if entries.isEmpty {
          Text("No reply activity yet")
            .scaledFont(size: 12)
            .foregroundColor(OmiColors.textTertiary)
        } else {
          ForEach(entries) { entry in
            VStack(alignment: .leading, spacing: 3) {
              Text("\(entry.outcome) - \(contactResolver.displayName(for: entry.senderJid))")
                .scaledFont(size: 12, weight: .medium)
                .foregroundColor(OmiColors.textSecondary)
                .lineLimit(1)
                .truncationMode(.middle)
              Text(contactResolver.detailLabel(for: entry.chatJid))
                .scaledFont(size: 10)
                .foregroundColor(OmiColors.textTertiary)
                .lineLimit(1)
                .truncationMode(.middle)
              Text("\(formatDate(entry.createdAt)) - \(entry.text)")
                .scaledFont(size: 11)
                .foregroundColor(OmiColors.textTertiary)
                .lineLimit(2)
              if let reason = entry.reason, !reason.isEmpty {
                Text(reason)
                  .scaledFont(size: 11)
                  .foregroundColor(OmiColors.warning)
                  .lineLimit(2)
              }
            }
          }
        }
      }
    }
  }

  private var detailsCard: some View {
    card(settingId: "whatsapp.status") {
      VStack(alignment: .leading, spacing: 14) {
        HStack {
          VStack(alignment: .leading, spacing: 4) {
            Text("Connection Details")
              .scaledFont(size: 15, weight: .semibold)
              .foregroundColor(OmiColors.textPrimary)

            Text("Store: \(state.storePath)")
              .scaledFont(size: 12)
              .foregroundColor(OmiColors.textTertiary)
              .lineLimit(2)
              .truncationMode(.middle)
          }

          Spacer()

          Button(isCheckingHealth ? "Checking..." : "Check Health") {
            Task { await checkHealth() }
          }
          .buttonStyle(OnboardingCardButtonStyle(isPrimary: false))
          .disabled(isCheckingHealth)
        }

        if let lastEventSummary = state.lastEventSummary {
          divider
          detailRow(title: "Last event", value: lastEventSummary)
        }

        if let healthSummary {
          divider
          detailRow(title: "Health", value: healthSummary)
        }
      }
    }
  }

  private var statusColor: Color {
    switch state.connectionState {
    case .connected:
      return OmiColors.success
    case .degraded, .needsReauth:
      return OmiColors.warning
    case .pairing, .pairingTerminal, .connecting, .downloading:
      return OmiColors.purplePrimary
    case .disconnected:
      return OmiColors.textTertiary.opacity(0.35)
    }
  }

  private var statusTextColor: Color {
    switch state.connectionState {
    case .degraded, .needsReauth:
      return OmiColors.warning
    default:
      return OmiColors.textTertiary
    }
  }

  private var divider: some View {
    Rectangle()
      .fill(OmiColors.backgroundQuaternary)
      .frame(height: 1)
  }

  private func detailRow(title: String, value: String) -> some View {
    HStack(alignment: .top, spacing: 12) {
      Text(title)
        .scaledFont(size: 12, weight: .medium)
        .foregroundColor(OmiColors.textSecondary)
        .frame(width: 84, alignment: .leading)

      Text(value)
        .scaledFont(size: 12)
        .foregroundColor(OmiColors.textTertiary)
        .fixedSize(horizontal: false, vertical: true)

      Spacer(minLength: 0)
    }
  }

  private func draftRow(_ draft: WhatsAppDraft) -> some View {
    VStack(alignment: .leading, spacing: 10) {
      Text("To \(contactResolver.displayName(for: draft.senderJid, fallback: draft.senderName))")
        .scaledFont(size: 12, weight: .semibold)
        .foregroundColor(OmiColors.textSecondary)
      Text(contactResolver.detailLabel(for: draft.senderJid))
        .scaledFont(size: 11)
        .foregroundColor(OmiColors.textTertiary)
        .lineLimit(1)
        .truncationMode(.middle)
      TextField("Draft reply", text: Binding(
        get: { draftEdits[draft.id] ?? draft.text },
        set: { draftEdits[draft.id] = $0 }
      ), axis: .vertical)
      .textFieldStyle(.roundedBorder)
      HStack {
        Button("Send") {
          Task {
            _ = await replyCoordinator.approveDraft(id: draft.id, editedText: draftEdits[draft.id])
            draftEdits[draft.id] = nil
          }
        }
        .buttonStyle(OnboardingCardButtonStyle(isPrimary: true))

        Button("Always Auto + Send") {
          Task {
            _ = await replyCoordinator.alwaysAutoReplyAndApproveDraft(id: draft.id)
            draftEdits[draft.id] = nil
          }
        }
        .buttonStyle(OnboardingCardButtonStyle(isPrimary: false))

        Button("Dismiss") {
          replyCoordinator.dismissDraft(id: draft.id)
          draftEdits[draft.id] = nil
        }
        .buttonStyle(.plain)
        .foregroundColor(OmiColors.warning)
      }
    }
    .padding(12)
    .background(RoundedRectangle(cornerRadius: 12).fill(OmiColors.backgroundQuaternary.opacity(0.5)))
  }

  private func card<Content: View>(
    settingId: String,
    @ViewBuilder content: () -> Content
  ) -> some View {
    content()
      .padding(20)
      .background(
        RoundedRectangle(cornerRadius: 16)
          .fill(OmiColors.backgroundTertiary)
          .overlay(
            RoundedRectangle(cornerRadius: 16)
              .stroke(OmiColors.border.opacity(0.5), lineWidth: 1)
          )
      )
      .modifier(SettingHighlightModifier(settingId: settingId, highlightedSettingId: $highlightedSettingId))
  }

  private func disconnect() async {
    isDisconnecting = true
    await WhatsAppService.shared.disconnect()
    isDisconnecting = false
  }

  private func checkHealth() async {
    isCheckingHealth = true
    let health = await WhatsAppService.shared.health()
    healthSummary = health.summary
    isCheckingHealth = false
  }

  private func addAllowlistEntry() async {
    do {
      let jid = try await contactResolver.resolveRecipient(allowlistInput)
      replySettings.addAllowlistedJid(jid)
      allowlistInput = ""
      allowlistError = nil
    } catch {
      allowlistError = error.localizedDescription
    }
  }

  private func rebuildToneProfile() async {
    isRebuildingToneProfile = true
    await WhatsAppToneProfile.shared.rebuild()
    isRebuildingToneProfile = false
  }

  private func formatDate(_ date: Date) -> String {
    let formatter = DateFormatter()
    formatter.dateStyle = .short
    formatter.timeStyle = .short
    return formatter.string(from: date)
  }
}
