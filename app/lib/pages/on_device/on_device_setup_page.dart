import 'dart:async';

import 'package:flutter/material.dart';

import 'package:omi/pages/on_device/on_device_components.dart';
import 'package:omi/pages/on_device/on_device_schedule_page.dart';
import 'package:omi/services/on_device/on_device_model.dart';
import 'package:omi/services/on_device/on_device_transcription_controller.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/other/temp.dart';

/// Parakeet setup opens only after a positive non-OS-managed engine. A null or failed
/// detection stays unavailable; Android Whisper is that positive download engine.
bool onDeviceOpensDownloadSetup(OnDeviceModel model) {
  if (!model.engineResolved || model.detectionFailed || !model.status.isSupported || model.isOsManaged) {
    return false;
  }
  if (model is AppleOnDeviceModel) {
    final engine = model.engine;
    return engine != null && engine.isNotEmpty;
  }
  return true;
}

/// Opens model setup only when this phone needs a download the user starts.
///
/// An unknown engine is still loading: wait for it, and do not guess Parakeet. A failed or
/// timed-out lookup stays unavailable. SpeechAnalyzer and the system speech fallback are
/// OS-managed. They turn on here, and a speech-asset install is a progress row on the settings
/// page, not its own screen. Parakeet and Android keep the download setup page.
Future<void> openOnDeviceSetup(BuildContext context, {OnDeviceTranscriptionController? controller}) async {
  final resolved = controller ?? OnDeviceTranscriptionController.instance;
  final model = resolved.model;
  if (!model.engineResolved) await model.refresh();
  if (!context.mounted || !onDeviceOpensDownloadSetup(model)) {
    if (context.mounted && model.isOsManaged && model.engineResolved && !model.detectionFailed) {
      if (!model.status.isInstalled && model.status.phase != OnDeviceModelPhase.downloading) {
        unawaited(model.download(wifiOnly: false));
      }
    }
    return;
  }
  await routeToPage(context, OnDeviceSetupPage(controller: controller));
}

/// Step 1 of 2: get the speech model. Recording never waits on this, so Next is always available
/// and the download carries on in the background. Not used for an OS-managed speech engine.
class OnDeviceSetupPage extends StatefulWidget {
  const OnDeviceSetupPage({super.key, this.controller});

  final OnDeviceTranscriptionController? controller;

  @override
  State<OnDeviceSetupPage> createState() => _OnDeviceSetupPageState();
}

class _OnDeviceSetupPageState extends State<OnDeviceSetupPage> {
  OnDeviceTranscriptionController get _controller => widget.controller ?? OnDeviceTranscriptionController.instance;

  Future<void> _next() async {
    final done = await routeToPage(context, OnDeviceSchedulePage(controller: widget.controller, step: 2));
    if (done == true && mounted) Navigator.of(context).pop(true);
  }

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    return Scaffold(
      appBar: AppBar(leading: const OmiBackButton(), title: Text(l10n.onDeviceTranscription)),
      body: SafeArea(
        top: false,
        child: ListenableBuilder(
          listenable: _controller,
          builder: (context, _) {
            final settings = _controller.settings;
            return Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                Expanded(
                  child: ListView(
                    padding: const EdgeInsets.fromLTRB(OmiSpacing.lg, OmiSpacing.xs, OmiSpacing.lg, OmiSpacing.lg),
                    children: [
                      const OnDeviceStepLabel(step: 1, total: 2),
                      const SizedBox(height: OmiSpacing.xs),
                      Semantics(header: true, child: Text(l10n.onDeviceTranscribeOnPhone, style: OmiType.title1)),
                      const SizedBox(height: OmiSpacing.xs),
                      Text(l10n.onDeviceSetupBody,
                          style: OmiType.callout.copyWith(color: OmiColors.textSecondary, height: 1.4)),
                      const SizedBox(height: OmiSpacing.xl),
                      OnDeviceModelCard(model: _controller.model, wifiOnly: settings.wifiOnlyDownload),
                      const SizedBox(height: OmiSpacing.md),
                      if (!_controller.model.isOsManaged || !_controller.model.status.isInstalled)
                        OnDeviceFactRow(icon: Icons.mic_none, text: l10n.onDeviceSetupKeepRecording),
                      OnDeviceFactRow(icon: Icons.lock_outline, text: l10n.onDeviceSetupAudioStays),
                      const SizedBox(height: OmiSpacing.lg),
                      if (!_controller.model.isOsManaged)
                        OmiSettingsGroup(
                          children: [
                            OmiSettingsRow.toggle(
                              leading: const Icon(Icons.wifi),
                              title: l10n.onDeviceWifiOnly,
                              value: settings.wifiOnlyDownload,
                              onChanged: (value) =>
                                  _controller.updateSettings(settings.copyWith(wifiOnlyDownload: value)),
                            ),
                          ],
                        ),
                    ],
                  ),
                ),
                Padding(
                  padding: const EdgeInsets.fromLTRB(OmiSpacing.lg, OmiSpacing.xs, OmiSpacing.lg, OmiSpacing.md),
                  child: OmiButton(
                    key: const Key('on_device_setup_next'),
                    label: l10n.nextButton,
                    expand: true,
                    onPressed: _next,
                  ),
                ),
              ],
            );
          },
        ),
      ),
    );
  }
}

/// The speech model's size, state and the one action that state offers (Download, Cancel or Try
/// Again).
class OnDeviceModelCard extends StatelessWidget {
  const OnDeviceModelCard({super.key, required this.model, required this.wifiOnly});

  final OnDeviceModel model;
  final bool wifiOnly;

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    return ListenableBuilder(
      listenable: model,
      builder: (context, _) {
        final status = model.status;
        final phase = status.phase;
        final timeLeft = status.timeLeft;
        return Container(
          padding: const EdgeInsets.all(OmiSpacing.md),
          decoration: BoxDecoration(color: OmiColors.surface1, borderRadius: OmiRadius.lgAll),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Row(
                children: [
                  Container(
                    width: 40,
                    height: 40,
                    decoration: BoxDecoration(color: OmiColors.surface2, borderRadius: OmiRadius.mdAll),
                    child: Icon(Icons.graphic_eq, color: OmiColors.textSecondary, size: 20),
                  ),
                  const SizedBox(width: OmiSpacing.sm),
                  Expanded(child: Text(l10n.onDeviceSpeechModel, style: OmiType.headline)),
                  if (status.isSupported && !status.isInstalled && status.sizeBytes > 0)
                    Text(onDeviceSizeLabel(l10n, status.sizeBytes),
                        style: OmiType.subhead.copyWith(color: OmiColors.textSecondary)),
                ],
              ),
              const SizedBox(height: OmiSpacing.sm),
              if (phase == OnDeviceModelPhase.downloading) ...[
                OnDeviceProgressBar(value: status.progress),
                const SizedBox(height: OmiSpacing.xs),
              ],
              Row(
                children: [
                  if (phase == OnDeviceModelPhase.installed) ...[
                    Icon(Icons.check_circle, size: 16, color: OmiColors.success),
                    const SizedBox(width: OmiSpacing.xxs),
                  ],
                  Expanded(
                    child: Text(
                      onDeviceModelStatusLabel(l10n, status, wifiOnly: wifiOnly && !model.isOsManaged),
                      style: OmiType.footnote.copyWith(
                        color: phase == OnDeviceModelPhase.failed ? OmiColors.danger : OmiColors.textSecondary,
                      ),
                    ),
                  ),
                  if (phase == OnDeviceModelPhase.downloading && timeLeft != null)
                    Text(
                      l10n.onDeviceTimeLeft(OmiDuration.compact(timeLeft.inSeconds, l10n)),
                      style: OmiType.footnote.copyWith(color: OmiColors.textTertiary),
                    ),
                ],
              ),
              if (_action(context, status) case final action?) ...[
                const SizedBox(height: OmiSpacing.sm),
                action,
              ],
            ],
          ),
        );
      },
    );
  }

  Widget? _action(BuildContext context, OnDeviceModelStatus status) {
    final l10n = context.l10n;
    switch (status.phase) {
      case OnDeviceModelPhase.unsupported:
      case OnDeviceModelPhase.installed:
        return null;
      case OnDeviceModelPhase.downloading:
        return OmiButton.secondary(
          key: const Key('on_device_model_cancel'),
          label: l10n.cancel,
          size: OmiButtonSize.compact,
          onPressed: model.cancel,
        );
      case OnDeviceModelPhase.failed:
        return OmiButton.secondary(
          key: const Key('on_device_model_retry'),
          label: l10n.tryAgain,
          size: OmiButtonSize.compact,
          onPressed: () => unawaited(model.download(wifiOnly: wifiOnly)),
        );
      case OnDeviceModelPhase.notDownloaded:
      case OnDeviceModelPhase.waitingForWifi:
        return OmiButton.secondary(
          key: const Key('on_device_model_download'),
          label: l10n.onDeviceDownloadModel,
          icon: Icons.file_download_outlined,
          size: OmiButtonSize.compact,
          onPressed: () => unawaited(model.download(wifiOnly: wifiOnly)),
        );
    }
  }
}
