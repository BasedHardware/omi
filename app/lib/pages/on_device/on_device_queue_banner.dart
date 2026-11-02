import 'dart:async';

import 'package:flutter/material.dart';

import 'package:provider/provider.dart';

import 'package:omi/backend/http/api_result.dart';
import 'package:omi/backend/http/plan_storefront_api.dart';
import 'package:omi/models/local_recording.dart';
import 'package:omi/models/plan_storefront.dart';
import 'package:omi/pages/on_device/on_device_components.dart';
import 'package:omi/pages/on_device/on_device_setup_page.dart';
import 'package:omi/pages/settings/widgets/plans/contextual_plans.dart';
import 'package:omi/providers/local_recordings_provider.dart';
import 'package:omi/providers/usage_provider.dart';
import 'package:omi/services/experiments/plan_storefront_gate.dart';
import 'package:omi/services/on_device/on_device_model.dart';
import 'package:omi/services/on_device/on_device_schedule_policy.dart';
import 'package:omi/services/on_device/on_device_settings.dart';
import 'package:omi/services/on_device/on_device_transcription_controller.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';

/// Opens the plans sheet for the shared usage budget. There is no legacy usage-page fallback.
void openOnDeviceUpgrade(BuildContext context) => unawaited(openOnDeviceUsagePlans(context));

/// Opens that sheet from the settings "Get more usage" row.
///
/// Returns false when the sheet is unavailable. This row does not open the legacy usage page.
Future<bool> openOnDeviceUsagePlans(BuildContext context) {
  return openContextualPlans(context, source: 'on_device_overflow', trigger: 'usage_budget');
}

/// The storefront `usage` object. Null when the sheet is off or the payload is not the shared
/// budget. The client never invents hours from a local counter.
Future<StorefrontUsage?> loadOnDeviceUsage(String locale) async {
  final result = await PlanStorefrontApi().load(source: 'on_device_overflow', trigger: 'usage_budget', locale: locale);
  if (result is! ApiSuccess<PlanStorefront>) return null;
  final usage = result.data.usage;
  if (usage == null || usage.kind != 'usage_budget') return null;
  return usage;
}

Future<bool> onDevicePlansSheetAvailable(BuildContext context) async {
  final provider = context.read<UsageProvider>();
  return provider.showSubscriptionUI && await PlanStorefrontGate.sheetEnabled();
}

/// The conversations list's banner for recordings waiting on this phone. Renders nothing unless the
/// on-device flag is on and something is waiting.
class OnDeviceQueueBanner extends StatefulWidget {
  const OnDeviceQueueBanner({super.key, this.controller, this.loadUsage, this.plansSheetAvailable});

  final OnDeviceTranscriptionController? controller;
  final Future<StorefrontUsage?> Function(String locale)? loadUsage;
  final Future<bool> Function(BuildContext context)? plansSheetAvailable;

  @override
  State<OnDeviceQueueBanner> createState() => _OnDeviceQueueBannerState();
}

class _OnDeviceQueueBannerState extends State<OnDeviceQueueBanner> {
  OnDeviceTranscriptionController get _controller => widget.controller ?? OnDeviceTranscriptionController.instance;
  int _evaluatedSeconds = -1;
  String? _moreLabel;
  bool _plansSheet = false;
  Future<void>? _usageLoad;

  @override
  void initState() {
    super.initState();
    unawaited(_controller.ensureLoaded());
  }

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    _usageLoad ??= _loadUsage();
  }

  Future<void> _loadUsage() async {
    await _controller.ensureLoaded();
    // The conversations page mounts this banner while the flag is off. Do not
    // construct the storefront client until the gate is on; that reads Env.
    if (!mounted || !_controller.isActive) return;
    final sheet = await (widget.plansSheetAvailable ?? onDevicePlansSheetAvailable)(context);
    if (!mounted) return;
    final usage = await (widget.loadUsage ?? loadOnDeviceUsage)(context.l10n.localeName);
    if (mounted) {
      setState(() {
        _plansSheet = sheet;
        _moreLabel = usage?.moreLabel;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    return ListenableBuilder(
      listenable: _controller,
      builder: (context, _) {
        if (!_controller.isActive) return const SizedBox.shrink();
        final recordingSeconds = context.select<LocalRecordingsProvider, int>((p) => p.recordings
            .where((r) => r.state == LocalRecordingState.pending)
            .fold<int>(0, (sum, r) => sum + r.seconds));
        final pendingSeconds = recordingSeconds + _controller.pendingSeconds;
        final atCap = context.select<UsageProvider, bool>((p) => p.isOutOfCredits);
        if (pendingSeconds != _evaluatedSeconds) {
          _evaluatedSeconds = pendingSeconds;
          unawaited(_controller.evaluate(pendingAudio: Duration(seconds: pendingSeconds)));
        }
        if (_controller.lastRunFailed) {
          return OmiErrorState(
              message: context.l10n.failedToTranscribeAudio, onRetry: () => unawaited(_controller.transcribeNow()));
        }
        final moreLabel = onDeviceMoreUsageTitle(
          plansSheetAvailable: _plansSheet,
          moreLabel: _moreLabel,
        );
        return OnDeviceQueueBannerView(
          controller: _controller,
          pendingSeconds: pendingSeconds,
          atCap: atCap,
          onSetUp: () => unawaited(openOnDeviceSetup(context, controller: widget.controller)),
          moreLabel: moreLabel,
          onGetMoreUsage: () => openOnDeviceUpgrade(context),
        );
      },
    );
  }
}

/// The banner's content for a given state; [OnDeviceQueueBanner] supplies the inputs.
///
/// - Model ready and on-device on: "3h 20m waiting to transcribe", why it is waiting, Transcribe Now.
/// - No model yet (on, or the usage limit is reached): finish setup, with the download size.
/// - OS-managed speech assets still installing: progress only.
/// - This phone cannot run the model and the limit is reached: audio stays saved; open plans.
class OnDeviceQueueBannerView extends StatelessWidget {
  const OnDeviceQueueBannerView({
    super.key,
    required this.controller,
    required this.pendingSeconds,
    required this.atCap,
    required this.onSetUp,
    required this.onGetMoreUsage,
    this.moreLabel,
  });

  final OnDeviceTranscriptionController controller;
  final int pendingSeconds;
  final bool atCap;
  final VoidCallback onSetUp;
  final VoidCallback onGetMoreUsage;

  /// Backend-owned label for the plans row. Hidden when the storefront did not send one.
  final String? moreLabel;

  @override
  Widget build(BuildContext context) {
    if (!controller.isActive || pendingSeconds <= 0) return const SizedBox.shrink();
    final settings = controller.settings;
    final status = controller.model.status;
    if (controller.model.detectionFailed) {
      return settings.enabled || atCap ? _engineUnavailable(context) : const SizedBox.shrink();
    }
    if (!status.isSupported) {
      return atCap ? _unsupported(context) : const SizedBox.shrink();
    }
    if (!status.isInstalled) {
      if (controller.model.isOsManaged) {
        return settings.enabled || atCap ? _OsAssetProgress(controller: controller) : const SizedBox.shrink();
      }
      return settings.enabled || atCap ? _finishSetup(context, status) : const SizedBox.shrink();
    }
    return settings.enabled ? _waiting(context, settings) : const SizedBox.shrink();
  }

  String _duration(BuildContext context) => OmiDuration.compact(pendingSeconds, context.l10n);

  Widget _card({required Key key, required List<Widget> children}) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(OmiSpacing.md, OmiSpacing.sm, OmiSpacing.md, 0),
      child: Container(
        key: key,
        padding: const EdgeInsets.all(OmiSpacing.md),
        decoration: BoxDecoration(
          color: OmiColors.surface1,
          borderRadius: OmiRadius.lgAll,
          border: Border.all(color: OmiColors.border, width: 0.5),
        ),
        child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: children),
      ),
    );
  }

  Widget _title(IconData icon, String text, {Color? color}) {
    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Padding(
          padding: const EdgeInsets.only(top: 1),
          child: ExcludeSemantics(child: Icon(icon, size: 18, color: color ?? OmiColors.textSecondary)),
        ),
        const SizedBox(width: OmiSpacing.xs),
        Expanded(child: Text(text, style: OmiType.headline)),
      ],
    );
  }

  Widget _body(String text) => Padding(
        padding: const EdgeInsets.only(top: OmiSpacing.xxs),
        child: Text(text, style: OmiType.subhead.copyWith(color: OmiColors.textSecondary, height: 1.35)),
      );

  Widget _waiting(BuildContext context, OnDeviceSettings settings) {
    final l10n = context.l10n;
    final reason = controller.decision?.reason;
    final String body;
    if (reason == OnDeviceRunReason.batteryTooLow) {
      body = l10n.onDeviceQueueLowBatteryBody;
    } else if (settings.schedule == OnDeviceSchedule.everyFewHours) {
      body = l10n.onDeviceQueueHoursBody;
    } else {
      body = l10n.onDeviceQueueChargingBody;
    }
    return _card(
      key: const Key('on_device_queue_banner'),
      children: [
        _title(Icons.schedule, l10n.onDeviceQueueWaiting(_duration(context))),
        if (!controller.isTranscribing) _body(body),
        const SizedBox(height: OmiSpacing.sm),
        if (controller.isTranscribing && controller.progress > 0) ...[
          OnDeviceProgressBar(value: controller.progress),
          const SizedBox(height: OmiSpacing.sm),
        ],
        if (controller.isTranscribing)
          Row(
            children: [
              const OmiSpinner(size: OmiSpinnerSize.small),
              const SizedBox(width: OmiSpacing.xs),
              Text(l10n.onDeviceTranscribing, style: OmiType.subhead.copyWith(color: OmiColors.textSecondary)),
            ],
          )
        else
          Row(
            children: [
              OmiButton.secondary(
                key: const Key('on_device_transcribe_now'),
                label: l10n.onDeviceTranscribeNow,
                icon: Icons.bolt,
                size: OmiButtonSize.compact,
                onPressed: () => controller.transcribeNow(seconds: pendingSeconds),
              ),
              const SizedBox(width: OmiSpacing.sm),
              Flexible(
                child: Text(l10n.onDeviceUsesBattery, style: OmiType.footnote.copyWith(color: OmiColors.textTertiary)),
              ),
            ],
          ),
      ],
    );
  }

  Widget _finishSetup(BuildContext context, OnDeviceModelStatus status) {
    final l10n = context.l10n;
    final downloading = status.phase == OnDeviceModelPhase.downloading;
    return _card(
      key: const Key('on_device_finish_setup_banner'),
      children: [
        _title(Icons.file_download_outlined, l10n.onDeviceFinishSetupTitle),
        _body(l10n.onDeviceFinishSetupBody),
        const SizedBox(height: OmiSpacing.sm),
        Text(
          '${l10n.onDeviceQueueWaiting(_duration(context))} · ${l10n.onDeviceDownloadSize(onDeviceSizeLabel(l10n, status.sizeBytes))}',
          style: OmiType.footnote.copyWith(color: OmiColors.textTertiary),
        ),
        const SizedBox(height: OmiSpacing.sm),
        if (downloading) ...[
          OnDeviceProgressBar(value: status.progress),
          const SizedBox(height: OmiSpacing.xs),
          Text(
            onDeviceModelStatusLabel(l10n, status, wifiOnly: controller.settings.wifiOnlyDownload),
            style: OmiType.footnote.copyWith(color: OmiColors.textSecondary),
          ),
        ] else
          OmiButton(
            key: const Key('on_device_finish_setup_download'),
            label: l10n.onDeviceDownloadModel,
            size: OmiButtonSize.compact,
            expand: true,
            onPressed: onSetUp,
          ),
        if (moreLabel != null && moreLabel!.isNotEmpty)
          OmiButton.tertiary(
            key: const Key('on_device_finish_setup_upgrade'),
            label: moreLabel!,
            size: OmiButtonSize.compact,
            expand: true,
            onPressed: onGetMoreUsage,
          ),
      ],
    );
  }

  Widget _engineUnavailable(BuildContext context) {
    final l10n = context.l10n;
    return _card(
      key: const Key('on_device_engine_unavailable'),
      children: [
        _title(Icons.graphic_eq, l10n.onDeviceModelUnsupported),
        const SizedBox(height: OmiSpacing.sm),
        OmiButton(
          key: const Key('on_device_engine_retry'),
          label: l10n.tryAgain,
          size: OmiButtonSize.compact,
          expand: true,
          onPressed: () => unawaited(controller.model.refresh()),
        ),
      ],
    );
  }

  Widget _unsupported(BuildContext context) {
    final l10n = context.l10n;
    return _card(
      key: const Key('on_device_unsupported_banner'),
      children: [
        _title(Icons.graphic_eq, l10n.onDeviceQueueWaiting(_duration(context))),
        _body(l10n.onDeviceUnsupportedBody),
        const SizedBox(height: OmiSpacing.sm),
        if (moreLabel != null && moreLabel!.isNotEmpty)
          OmiButton.secondary(
            key: const Key('on_device_unsupported_upgrade'),
            label: moreLabel!,
            size: OmiButtonSize.compact,
            expand: true,
            onPressed: onGetMoreUsage,
          ),
      ],
    );
  }
}

/// Progress only, while iOS installs speech assets. No explanation.
class _OsAssetProgress extends StatefulWidget {
  const _OsAssetProgress({required this.controller});

  final OnDeviceTranscriptionController controller;

  @override
  State<_OsAssetProgress> createState() => _OsAssetProgressState();
}

class _OsAssetProgressState extends State<_OsAssetProgress> {
  @override
  void initState() {
    super.initState();
    final model = widget.controller.model;
    if (!model.status.isInstalled && model.status.phase != OnDeviceModelPhase.downloading) {
      unawaited(model.download(wifiOnly: false));
    }
  }

  @override
  Widget build(BuildContext context) {
    return ListenableBuilder(
      listenable: widget.controller.model,
      builder: (context, _) {
        final status = widget.controller.model.status;
        final l10n = context.l10n;
        return Padding(
          padding: const EdgeInsets.fromLTRB(OmiSpacing.md, OmiSpacing.sm, OmiSpacing.md, 0),
          child: Container(
            key: const Key('on_device_asset_progress'),
            padding: const EdgeInsets.all(OmiSpacing.md),
            decoration: BoxDecoration(
              color: OmiColors.surface1,
              borderRadius: OmiRadius.lgAll,
              border: Border.all(color: OmiColors.border, width: 0.5),
            ),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                if (status.phase == OnDeviceModelPhase.downloading) ...[
                  OnDeviceProgressBar(value: status.progress),
                  const SizedBox(height: OmiSpacing.xs),
                ],
                Text(
                  onDeviceModelStatusLabel(l10n, status, wifiOnly: false),
                  style: OmiType.footnote.copyWith(color: OmiColors.textSecondary),
                ),
              ],
            ),
          ),
        );
      },
    );
  }
}

/// The status line of a recording waiting on this phone, or null when the on-device flag is off
/// or on-device transcription does not apply (not chosen and usage remains).
Widget? onDeviceRecordingChip(BuildContext context, OnDeviceTranscriptionController controller, {required bool atCap}) {
  if (!controller.isActive) return null;
  final l10n = context.l10n;
  final settings = controller.settings;
  final status = controller.model.status;
  if (!status.isSupported || !(settings.enabled || atCap)) return null;
  if (!status.isInstalled) {
    return OnDeviceStatusChip(icon: Icons.file_download_outlined, label: l10n.onDeviceWaitingForSetup);
  }
  if (!settings.enabled) return null;
  if (controller.isTranscribing) {
    return OnDeviceStatusChip(icon: Icons.graphic_eq, label: l10n.onDeviceTranscribing);
  }
  if (settings.schedule == OnDeviceSchedule.whileCharging) {
    return OnDeviceStatusChip(icon: Icons.bolt, label: l10n.onDeviceWaitingForCharger, color: OmiColors.warning);
  }
  return OnDeviceStatusChip(icon: Icons.schedule, label: l10n.onDeviceWaitingToTranscribe, color: OmiColors.warning);
}
