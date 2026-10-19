import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';

import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/models/plan_storefront.dart';
import 'package:omi/services/on_device/on_device_model.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';

/// The copy names the iPhone on iOS ("Transcribed on this iPhone") and the phone elsewhere.
bool get onDeviceIsIphone => defaultTargetPlatform == TargetPlatform.iOS;

/// The plans sheet and this meter share the storefront catalog. The backend string is the
/// only copy; the device locale is sent on the request that produced [usage].
String? onDeviceMeterLine(StorefrontUsage usage) {
  final sent = usage.meterLine;
  if (sent == null || sent.isEmpty) return null;
  return sent;
}

/// Shown only when the plans sheet can open. [moreLabel] is the catalog string for the
/// locale the client already sent.
String? onDeviceMoreUsageTitle({
  required bool plansSheetAvailable,
  required String? moreLabel,
}) {
  if (!plansSheetAvailable || moreLabel == null || moreLabel.trim().isEmpty) return null;
  return moreLabel;
}

/// The glyph for "this phone", matching the platform.
IconData get onDevicePhoneIcon => onDeviceIsIphone ? Icons.phone_iphone : Icons.phone_android;

/// "600 MB", rounded to whole megabytes.
String onDeviceSizeLabel(AppLocalizations l10n, int bytes) =>
    l10n.onDeviceMegabytes((bytes / (1024 * 1024)).round().toString());

/// One-line status of the speech model, for a settings value or a card.
String onDeviceModelStatusLabel(AppLocalizations l10n, OnDeviceModelStatus status, {required bool wifiOnly}) {
  final percent = (status.progress * 100).floor();
  switch (status.phase) {
    case OnDeviceModelPhase.unsupported:
      return l10n.onDeviceModelUnsupported;
    case OnDeviceModelPhase.notDownloaded:
      return l10n.onDeviceModelNotDownloaded;
    case OnDeviceModelPhase.waitingForWifi:
      return l10n.onDeviceWaitingForWifi;
    case OnDeviceModelPhase.downloading:
      return wifiOnly ? l10n.onDeviceDownloadingWifi(percent) : l10n.onDeviceDownloadingPercent(percent);
    case OnDeviceModelPhase.installed:
      return l10n.onDeviceModelInstalled(onDeviceSizeLabel(l10n, status.sizeBytes));
    case OnDeviceModelPhase.failed:
      return l10n.onDeviceDownloadFailed;
  }
}

/// A selectable option card: a title with an optional badge or trailing note, a description, an
/// optional meta line, and a selection mark. The whole card is one radio-style target.
class OnDeviceChoiceCard extends StatelessWidget {
  const OnDeviceChoiceCard({
    super.key,
    required this.title,
    required this.body,
    required this.selected,
    required this.onSelected,
    this.badge,
    this.meta,
  });

  final String title;
  final String body;
  final bool selected;
  final VoidCallback onSelected;

  /// A short pill beside the title ("Included", "Recommended").
  final String? badge;

  /// A muted line under the body ("Battery: almost none").
  final String? meta;

  @override
  Widget build(BuildContext context) {
    return Semantics(
      selected: selected,
      inMutuallyExclusiveGroup: true,
      button: true,
      child: Material(
        color: OmiColors.surface1,
        shape: RoundedRectangleBorder(
          borderRadius: OmiRadius.lgAll,
          side: BorderSide(color: selected ? OmiColors.accent : OmiColors.border, width: selected ? 2 : 1),
        ),
        clipBehavior: Clip.antiAlias,
        child: InkWell(
          onTap: () {
            OmiHaptics.selection();
            onSelected();
          },
          child: Padding(
            padding: const EdgeInsets.all(OmiSpacing.md),
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Padding(
                  padding: const EdgeInsets.only(top: 1),
                  child: ExcludeSemantics(
                    child: Icon(
                      selected ? Icons.check_circle : Icons.radio_button_unchecked,
                      size: 22,
                      color: selected ? OmiColors.accent : OmiColors.textTertiary,
                    ),
                  ),
                ),
                const SizedBox(width: OmiSpacing.sm),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Wrap(
                        spacing: OmiSpacing.xs,
                        runSpacing: OmiSpacing.xxs,
                        crossAxisAlignment: WrapCrossAlignment.center,
                        children: [
                          Text(title, style: OmiType.headline),
                          if (badge != null) OnDeviceBadge(label: badge!),
                        ],
                      ),
                      const SizedBox(height: OmiSpacing.xxs),
                      Text(body, style: OmiType.subhead.copyWith(color: OmiColors.textSecondary, height: 1.35)),
                      if (meta != null) ...[
                        const SizedBox(height: OmiSpacing.xs),
                        Text(meta!, style: OmiType.footnote.copyWith(color: OmiColors.textTertiary)),
                      ],
                    ],
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

/// A small filled pill on the accent: "Included", "Recommended".
class OnDeviceBadge extends StatelessWidget {
  const OnDeviceBadge({super.key, required this.label});

  final String label;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: OmiSpacing.xs, vertical: 2),
      decoration: BoxDecoration(color: OmiColors.accent, borderRadius: OmiRadius.pillAll),
      child: Text(label, style: OmiType.footnote.copyWith(color: OmiColors.onAccent, fontWeight: FontWeight.w600)),
    );
  }
}

/// A non-interactive status pill with a glyph: "Waiting for charger", "Transcribed on this iPhone".
class OnDeviceStatusChip extends StatelessWidget {
  const OnDeviceStatusChip({super.key, required this.icon, required this.label, this.color});

  final IconData icon;
  final String label;

  /// Text and glyph colour; [OmiColors.textSecondary] when null. Use a status colour only for state.
  final Color? color;

  @override
  Widget build(BuildContext context) {
    final ink = color ?? OmiColors.textSecondary;
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: OmiSpacing.xs, vertical: 3),
      decoration: BoxDecoration(
        borderRadius: OmiRadius.pillAll,
        border: Border.all(color: ink.withValues(alpha: 0.4)),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          ExcludeSemantics(child: Icon(icon, size: 13, color: ink)),
          const SizedBox(width: OmiSpacing.xxs),
          Flexible(
            child: Text(
              label,
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              style: OmiType.footnote.copyWith(color: ink, fontWeight: FontWeight.w500),
            ),
          ),
        ],
      ),
    );
  }
}

/// A line with a leading glyph, for short reassurances under a setup step.
class OnDeviceFactRow extends StatelessWidget {
  const OnDeviceFactRow({super.key, required this.icon, required this.text});

  final IconData icon;
  final String text;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: OmiSpacing.xxs),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          ExcludeSemantics(child: Icon(icon, size: 18, color: OmiColors.textTertiary)),
          const SizedBox(width: OmiSpacing.sm),
          Expanded(
            child: Text(text, style: OmiType.subhead.copyWith(color: OmiColors.textSecondary, height: 1.35)),
          ),
        ],
      ),
    );
  }
}

/// The step label above a setup heading ("Step 1 of 2").
class OnDeviceStepLabel extends StatelessWidget {
  const OnDeviceStepLabel({super.key, required this.step, required this.total});

  final int step;
  final int total;

  @override
  Widget build(BuildContext context) {
    return Text(
      context.l10n.onDeviceStepOf(step, total),
      style: OmiType.footnote.copyWith(color: OmiColors.textTertiary, fontWeight: FontWeight.w600),
    );
  }
}

/// A thin determinate bar, the same as the usage meters.
class OnDeviceProgressBar extends StatelessWidget {
  const OnDeviceProgressBar({super.key, required this.value, this.semanticsLabel});

  final double value;
  final String? semanticsLabel;

  @override
  Widget build(BuildContext context) {
    return LinearProgressIndicator(
      value: value.clamp(0.0, 1.0),
      backgroundColor: OmiColors.surface3,
      valueColor: AlwaysStoppedAnimation<Color>(OmiColors.accent),
      minHeight: 4,
      borderRadius: OmiRadius.pillAll,
      semanticsLabel: semanticsLabel,
    );
  }
}
