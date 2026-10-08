part of 'developer.dart';

extension _NativeDeveloperPresentation on _DeveloperSettingsPageState {
  Widget _nativeDeveloperSurface(DeveloperModeProvider provider, Widget classic) {
    if (!iosSwiftUiEnabled) return classic;
    final pageContext = context;
    final l10n = pageContext.l10n;
    final logs = SharedPreferencesUtil().devLogsToFileEnabled;
    final device = pageContext.watch<DeviceProvider>();
    Future<void> docs(String url, String analytics) async {
      await launchUrl(Uri.parse(url));
      PlatformManager.instance.analytics.pageOpened(analytics);
    }

    NativeSection webhook(String id, String title, String description, bool enabled, ValueChanged<bool> toggle,
            TextEditingController controller) =>
        NativeSection(id, [
          NativeRow('$id:enabled', title,
              subtitle: description,
              kind: 'toggle',
              value: enabled,
              enabled: !provider.savingSettingsLoading,
              action: (value) => toggle(value as bool)),
          if (enabled)
            NativeRow('$id:url', l10n.endpointUrl,
                kind: 'text',
                keyboard: 'url',
                value: controller.text,
                enabled: !provider.savingSettingsLoading,
                action: (value) => controller.text = value as String),
          if (id == 'developer_audio' && enabled)
            NativeRow('developer_audio_interval', l10n.intervalSeconds,
                kind: 'text',
                keyboard: 'decimal',
                value: provider.webhookAudioBytesDelay.text,
                enabled: !provider.savingSettingsLoading,
                action: (value) => provider.webhookAudioBytesDelay.text = value as String)
        ]);
    return PopScope(
        canPop: !provider.hasUnsavedWebhookChanges,
        onPopInvokedWithResult: (didPop, _) async {
          if (!didPop && await _confirmDiscard(provider) && pageContext.mounted) Navigator.of(pageContext).pop();
        },
        child: Scaffold(
            body: IosNativeSurface(title: l10n.developerSettings, fallback: classic, toolbar: [
          NativeRow('developer_back', l10n.back,
              symbol: 'chevron.left', action: (_) => Navigator.of(pageContext).maybePop()),
          if (provider.hasUnsavedWebhookChanges || provider.savingSettingsLoading)
            NativeRow('developer_save', l10n.save,
                symbol: 'checkmark', enabled: !provider.savingSettingsLoading, action: (_) => provider.saveSettings())
        ], sections: [
          NativeSection(
              'developer_creators',
              [
                NativeRow('developer_payouts', l10n.creatorPayouts,
                    kind: 'navigation',
                    action: (_) => openSettingsDestination(pageContext, SettingsDestination.creatorPayouts))
              ],
              title: l10n.appCreators),
          NativeSection(
              'developer_logs',
              [
                NativeRow('developer_logs_enabled', l10n.debugLogs,
                    kind: 'toggle',
                    value: logs,
                    subtitle: logs ? l10n.autoDeletesAfterThreeDays : l10n.helpsDiagnoseIssues, action: (value) async {
                  await DebugLogManager.setEnabled(value as bool);
                  _nativeRebuild(() {});
                }),
                if (logs) ...[
                  NativeRow('developer_share_logs', l10n.shareLogs,
                      symbol: 'square.and.arrow.up', action: (_) => _shareLogs()),
                  NativeRow('developer_clear_logs', l10n.clear, destructive: true, action: (_) async {
                    final message = l10n.debugLogCleared;
                    await DebugLogManager.clear();
                    if (pageContext.mounted) OmiFeedback.confirm(pageContext, message);
                  })
                ]
              ],
              title: l10n.debugAndDiagnostics),
          NativeSection(
              'developer_credentials',
              [
                NativeRow('developer_api_keys', l10n.developerApi,
                    kind: 'navigation', action: (_) => routeToPage(pageContext, const DeveloperApiKeysPage())),
                NativeRow('developer_mcp_keys', l10n.mcp,
                    kind: 'navigation', action: (_) => routeToPage(pageContext, const DeveloperMcpPage())),
                NativeRow('developer_webhook_docs', l10n.docs,
                    action: (_) => docs('https://docs.omi.me/doc/developer/apps/Introduction', 'Webhooks'))
              ],
              title: l10n.webhooks),
          webhook(
              'developer_conversation',
              l10n.conversationEvents,
              l10n.newConversationCreated,
              provider.conversationEventsToggled,
              provider.onConversationEventsToggled,
              provider.webhookOnConversationCreated),
          webhook('developer_transcript', l10n.realTimeTranscript, l10n.transcriptReceived, provider.transcriptsToggled,
              provider.onTranscriptsToggled, provider.webhookOnTranscriptReceived),
          webhook('developer_audio', l10n.audioBytes, l10n.audioDataReceived, provider.audioBytesToggled,
              provider.onAudioBytesToggled, provider.webhookAudioBytes),
          webhook('developer_day', l10n.daySummary, l10n.summaryGenerated, provider.daySummaryToggled,
              provider.onDaySummaryToggled, provider.webhookDaySummary),
          NativeSection(
              'developer_experiments',
              [
                NativeRow('developer_conversation_tools', l10n.conversationDeveloperTools,
                    kind: 'toggle',
                    subtitle: l10n.conversationDeveloperToolsDescription,
                    value: SharedPreferencesUtil().devModeEnabled,
                    action: (value) => _nativeRebuild(() => SharedPreferencesUtil().devModeEnabled = value as bool)),
                NativeRow('developer_transcription_diagnostics', l10n.transcriptionDiagnostics,
                    kind: 'toggle',
                    subtitle: l10n.detailedDiagnosticMessages,
                    value: provider.transcriptionDiagnosticEnabled,
                    action: (value) => provider.onTranscriptionDiagnosticChanged(value as bool)),
                NativeRow('developer_vad', l10n.vadGate,
                    kind: 'toggle',
                    subtitle: l10n.vadGateDescription,
                    value: provider.vadGateEnabled,
                    action: (value) => provider.onVadGateChanged(value as bool))
              ],
              title: l10n.experimental),
          if (FirmwareUpdateBuildPolicy.current.allowsOmiFirmwareUpdate &&
              device.isConnected &&
              device.pairedDevice != null)
            NativeSection(
                'developer_firmware',
                [
                  NativeRow('developer_flash', l10n.flashCustomFirmware,
                      subtitle: l10n.flashCustomFirmwareDescription, action: (_) => _pickFirmware(device))
                ],
                title: l10n.firmware)
        ])));
  }
}
