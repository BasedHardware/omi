part of 'page.dart';

extension _NativeHomePresentation on _HomePageState {
  Widget _buildNativeHome(BuildContext context) {
    final l10n = context.l10n;
    final device = context.watch<DeviceProvider>();
    final capture = context.watch<CaptureProvider>();
    final home = context.watch<HomeProvider>();
    final prompts = context.watch<SpeakerTagPromptsProvider>();
    final sync = context.watch<SyncProvider>();
    final wedge = CaptureWedgeMonitor.instance;
    final pending = sync.missingWalsOnDevice.length + sync.pendingLocalTranscriptionWals.length;
    final phoneRecording = capture.recordingState == RecordingState.record || capture.isPhoneMicPaused;
    final deviceLabel = device.isConnected
        ? device.batteryLevel > 0
            ? '${device.batteryLevel}%'
            : device.connectedDevice!.name
        : device.isConnecting
            ? l10n.deviceConnecting
            : device.pairedDevice == null
                ? l10n.connect
                : l10n.disconnected;
    return ListenableBuilder(
        listenable: wedge,
        builder: (context, _) => IosNativeHome(
              key: _nativeHomeKey,
              // A refused Home restores the complete classic shell, which keeps every Home control.
              fallback: const Center(child: OmiSpinner()),
              onRejected: _restoreClassicShell,
              header: [
                NativeHomeAction(
                    'device', deviceLabel, device.isCharging ? 'battery.100percent.bolt' : 'battery.75percent',
                    () async {
                  await routeToPage(
                      context, device.pairedDevice == null ? const ConnectDevicePage() : const ConnectedDevice());
                }),
                NativeHomeAction('calls', l10n.phoneCallsWithOmi, 'phone', () async {
                  await routeToPage(context, const PhoneCallsPage());
                }),
                if (device.pairedDevice != null || pending > 0)
                  NativeHomeAction('sync', pending > 0 ? '${l10n.sync} ($pending)' : l10n.sync, 'icloud', () async {
                    await routeToPage(context, device.supportsMultiFileSync ? const AutoSyncPage() : const SyncPage());
                  }),
                NativeHomeAction('search', l10n.search, 'magnifyingglass', _openSearch),
                NativeHomeAction('settings', l10n.settings, 'gearshape', _openSettings),
              ],
              footer: [
                NativeHomeAction('chat', l10n.askOmi, 'bubble.left', () => _openChat()),
                NativeHomeAction('voice', l10n.voiceMode, 'mic', () => _openChat(voice: true)),
                NativeHomeAction('record', phoneRecording ? l10n.stopRecording : l10n.startRecording,
                    phoneRecording ? 'stop.fill' : 'record.circle', () async {
                  await _nativeRecordKey.currentState?.performPrimaryAction();
                }, enabled: capture.recordingState != RecordingState.initialising),
              ],
              alerts: [
                if (wedge.visiblePrompt != null)
                  NativeHomeAction('recovery', l10n.captureRecoveryBanner, 'exclamationmark.triangle', () async {
                    wedge.markPromptShown();
                    wedge.onRecoveryActioned(surface: 'banner');
                    if (wedge.visiblePrompt?.trigger == CaptureWedgeMonitor.triggerStorageAtRisk) {
                      wedge.retryVisibleEpisode();
                    } else {
                      await HomeNavigation.openRoute('/settings/device');
                    }
                  }),
                if (!home.isLoading &&
                    !home.hasSpeakerProfile &&
                    device.isConnected &&
                    device.pairedDevice?.firmwareRevision != '1.0.2')
                  NativeHomeAction('voiceProfile', l10n.teachOmiYourVoice, 'waveform', () async {
                    final before = SharedPreferencesUtil().hasSpeakerProfile;
                    await openVoiceProfile(context);
                    if (!mounted || before == SharedPreferencesUtil().hasSpeakerProfile) return;
                    await capture.onRecordProfileSettingChanged();
                    if (mounted) home.setSpeakerProfile(SharedPreferencesUtil().hasSpeakerProfile);
                  }),
                if (device.havingNewFirmware)
                  NativeHomeAction('firmware', l10n.updateOmiFirmware, 'arrow.up.circle', () async {
                    final isGlass = device.pairedDevice?.type == DeviceType.openglass ||
                        (device.pairedDevice?.name.toLowerCase().contains('glass') ?? false);
                    PlatformManager.instance.analytics.pageOpened('Update Firmware Memories');
                    await routeToPage(
                        context,
                        isGlass
                            ? OmiGlassOtaUpdate(
                                device: device.pairedDevice,
                                latestFirmwareDetails: device.latestOmiGlassFirmwareDetails)
                            : FirmwareUpdate(device: device.pairedDevice));
                  }),
                if (prompts.visible && (prompts.finished || prompts.current != null))
                  NativeHomeAction('speakers', l10n.speakerTagPromptTitle, 'person.wave.2', () async {
                    await showOmiSheet<void>(
                        context: context,
                        title: l10n.speakerTagPromptTitle,
                        builder: (_) => const SpeakerTagPromptCard());
                  }),
              ],
            ));
  }
}
