import 'package:flutter/material.dart';

import 'package:omi/pages/on_device/on_device_components.dart';
import 'package:omi/services/on_device/on_device_provenance.dart';
import 'package:omi/services/on_device/on_device_transcription_controller.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';

/// "Transcribed on this iPhone" or "Transcribed and summarized on this iPhone".
String onDeviceTranscriptOriginLabel(BuildContext context, OnDeviceProvenance provenance) {
  final l10n = context.l10n;
  if (provenance.summary == OnDeviceSummaryOrigin.phone && onDeviceIsIphone) {
    return l10n.onDeviceTranscribedSummarizedOnIphone;
  }
  return onDeviceIsIphone ? l10n.onDeviceTranscribedOnIphone : l10n.onDeviceTranscribedOnPhone;
}

/// The conversation row's provenance line, or nothing for a conversation Omi Cloud transcribed.
class OnDeviceProvenanceChip extends StatelessWidget {
  const OnDeviceProvenanceChip({super.key, required this.conversationId, this.controller});

  final String conversationId;
  final OnDeviceTranscriptionController? controller;

  @override
  Widget build(BuildContext context) {
    final controller = this.controller ?? OnDeviceTranscriptionController.instance;
    return ListenableBuilder(
      listenable: controller,
      builder: (context, _) {
        final provenance = controller.provenanceFor(conversationId);
        if (provenance == null) return const SizedBox.shrink();
        return Padding(
          padding: const EdgeInsets.only(top: OmiSpacing.xs),
          child: Align(
            alignment: AlignmentDirectional.centerStart,
            child:
                OnDeviceStatusChip(icon: onDevicePhoneIcon, label: onDeviceTranscriptOriginLabel(context, provenance)),
          ),
        );
      },
    );
  }
}

/// Top of a conversation's summary when its transcript was made on the phone: where the transcript
/// and summary were made on one line, and — behind a tap on that line — why, the keep-everything
/// switch where a summary left the phone, and Redo with Omi Cloud. Nothing for a conversation Omi
/// Cloud transcribed.
class OnDeviceProvenanceSection extends StatelessWidget {
  const OnDeviceProvenanceSection({super.key, required this.conversationId, this.controller, this.onRedo});

  final String conversationId;
  final OnDeviceTranscriptionController? controller;

  /// Re-runs the conversation through Omi Cloud. The Redo button is hidden when null.
  final VoidCallback? onRedo;

  @override
  Widget build(BuildContext context) {
    final controller = this.controller ?? OnDeviceTranscriptionController.instance;
    return ListenableBuilder(
      listenable: controller,
      builder: (context, _) {
        final provenance = controller.provenanceFor(conversationId);
        if (provenance == null) return const SizedBox.shrink();
        return _content(context, controller, provenance);
      },
    );
  }

  Widget _content(BuildContext context, OnDeviceTranscriptionController controller, OnDeviceProvenance provenance) {
    final l10n = context.l10n;
    final cloudSummary = provenance.summary == OnDeviceSummaryOrigin.cloud;
    final reason = provenance.reason == OnDeviceReason.liveHoursUsed
        ? l10n.onDeviceWhyLiveHoursUsed
        : l10n.onDeviceWhySavingLiveHours;
    final String why;
    switch (provenance.summary) {
      case OnDeviceSummaryOrigin.phone:
        why = '$reason ${l10n.onDeviceWhySummaryOnPhone}';
      case OnDeviceSummaryOrigin.none:
        why = '$reason ${l10n.onDeviceWhyNoSummary}';
      case OnDeviceSummaryOrigin.cloud:
        why = onDeviceIsIphone ? l10n.onDeviceWhyCloudIphone : l10n.onDeviceWhyCloudPhone;
    }
    final settings = controller.settings;
    return Padding(
      padding: const EdgeInsets.only(bottom: OmiSpacing.md),
      child: Column(
        key: const Key('on_device_provenance_section'),
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          _CollapsibleWhy(
            summary: Wrap(
              spacing: OmiSpacing.xs,
              runSpacing: OmiSpacing.xs,
              children: [
                OnDeviceStatusChip(icon: onDevicePhoneIcon, label: onDeviceTranscriptOriginLabel(context, provenance)),
                if (cloudSummary) OnDeviceStatusChip(icon: Icons.cloud, label: l10n.onDeviceSummarizedByCloud),
              ],
            ),
            details: Container(
              padding: const EdgeInsets.all(OmiSpacing.md),
              decoration: BoxDecoration(color: OmiColors.surface1, borderRadius: OmiRadius.lgAll),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      ExcludeSemantics(child: Icon(Icons.info_outline, size: 18, color: OmiColors.textSecondary)),
                      const SizedBox(width: OmiSpacing.xs),
                      Expanded(
                        child: Semantics(
                          header: true,
                          child: Text(
                            cloudSummary ? l10n.onDeviceWhyCloudTitle : l10n.onDeviceWhyPhoneTitle,
                            style: OmiType.headline,
                          ),
                        ),
                      ),
                    ],
                  ),
                  const SizedBox(height: OmiSpacing.xs),
                  Text(why, style: OmiType.subhead.copyWith(color: OmiColors.textSecondary, height: 1.4)),
                  if (onRedo != null) ...[
                    const SizedBox(height: OmiSpacing.sm),
                    OmiButton.secondary(
                      key: const Key('on_device_redo_with_cloud'),
                      label: l10n.onDeviceRedoWithCloud,
                      icon: Icons.refresh,
                      size: OmiButtonSize.compact,
                      onPressed: onRedo,
                    ),
                    const SizedBox(height: OmiSpacing.xxs),
                    Text(l10n.onDeviceRedoHint, style: OmiType.footnote.copyWith(color: OmiColors.textTertiary)),
                  ],
                ],
              ),
            ),
          ),
          if (cloudSummary) ...[
            const SizedBox(height: OmiSpacing.sm),
            OmiSettingsGroup(
              children: [
                OmiSettingsRow.toggle(
                  leading: const Icon(Icons.lock_outline),
                  title: l10n.onDeviceKeepEverything,
                  subtitle: l10n.onDeviceKeepEverythingSubtitle,
                  value: settings.keepEverythingOnDevice,
                  onChanged: (value) => controller.updateSettings(settings.copyWith(keepEverythingOnDevice: value)),
                ),
              ],
            ),
          ],
        ],
      ),
    );
  }
}

/// The one-line provenance, collapsed by default: a tap on the line opens the details beneath it.
class _CollapsibleWhy extends StatefulWidget {
  const _CollapsibleWhy({required this.summary, required this.details});

  final Widget summary;
  final Widget details;

  @override
  State<_CollapsibleWhy> createState() => _CollapsibleWhyState();
}

class _CollapsibleWhyState extends State<_CollapsibleWhy> {
  bool _expanded = false;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Semantics(
          button: true,
          expanded: _expanded,
          child: InkWell(
            key: const Key('on_device_why_toggle'),
            borderRadius: OmiRadius.lgAll,
            onTap: () => setState(() => _expanded = !_expanded),
            child: Row(
              children: [
                Expanded(child: widget.summary),
                Icon(_expanded ? Icons.expand_less : Icons.expand_more, color: OmiColors.textSecondary),
              ],
            ),
          ),
        ),
        if (_expanded) ...[
          const SizedBox(height: OmiSpacing.sm),
          widget.details,
        ],
      ],
    );
  }
}
