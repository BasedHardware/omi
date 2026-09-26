import 'package:flutter/material.dart';

import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';

/// The label of a mic-gain level (0 = mute … 8 = +40 dB). Decibel values are not translated.
String micGainLevelLabel(BuildContext context, int level) {
  const decibels = ['-20dB', '-10dB', '+0dB', '+6dB', '+10dB', '+20dB', '+30dB', '+40dB'];
  if (level == 0) return context.l10n.mute;
  return level >= 1 && level <= decibels.length ? decibels[level - 1] : '';
}

/// What a mic-gain level is for ("Neutral - balanced recording").
String micGainDescription(BuildContext context, int level) {
  final l10n = context.l10n;
  final descriptions = [
    l10n.micGainDescMuted,
    l10n.micGainDescLow,
    l10n.micGainDescModerate,
    l10n.micGainDescNeutral,
    l10n.micGainDescSlightlyBoosted,
    l10n.micGainDescBoosted,
    l10n.micGainDescHigh,
    l10n.micGainDescVeryHigh,
    l10n.micGainDescMax,
  ];
  return level >= 0 && level < descriptions.length ? descriptions[level] : '';
}

/// Lets the reader pick what a double tap on the device does. Resolves to the chosen action
/// (0 end and process, 1 mute/unmute, 2 star), or null when dismissed.
Future<int?> showDoubleTapActionSheet(BuildContext context, {required int current}) {
  final l10n = context.l10n;
  final options = [l10n.endAndProcess, l10n.deviceOnboardingMuteUnmute, l10n.starOngoing];
  return showOmiSheet<int>(
    context: context,
    title: l10n.doubleTapAction,
    padding: const EdgeInsets.only(bottom: OmiSpacing.md),
    builder: (sheetContext) => Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        for (var i = 0; i < options.length; i++)
          Semantics(
            selected: i == current,
            child: OmiSettingsRow(
              title: options[i],
              showChevron: false,
              trailing: i == current ? Icon(Icons.check, color: OmiColors.textPrimary, size: 20) : null,
              onTap: () => Navigator.of(sheetContext).pop(i),
            ),
          ),
      ],
    ),
  );
}

/// A setting set by dragging, inline in a group (v2 `Device.dc` Light brightness and Microphone
/// gain): the title with the current value on the right, the slider under them, and an optional
/// note under the slider.
class DeviceLevelRow extends StatelessWidget {
  const DeviceLevelRow({
    super.key,
    required this.title,
    required this.value,
    required this.max,
    required this.divisions,
    required this.valueLabel,
    required this.onChanged,
    required this.onChangeEnd,
    this.note,
  });

  final String title;
  final double value;
  final double max;
  final int divisions;
  final String Function(double value) valueLabel;
  final ValueChanged<double> onChanged;
  final ValueChanged<double> onChangeEnd;
  final String? note;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(OmiSpacing.md, 12, OmiSpacing.md, 14),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        mainAxisSize: MainAxisSize.min,
        children: [
          // The slider announces the title and value; the line above is for the eye.
          ExcludeSemantics(
            child: Row(
              children: [
                Expanded(child: Text(title, style: OmiType.body)),
                const SizedBox(width: OmiSpacing.xs),
                Text(valueLabel(value), style: OmiType.body.copyWith(color: OmiColors.textSecondary)),
              ],
            ),
          ),
          const SizedBox(height: 6),
          MergeSemantics(
            child: Semantics(
              label: title,
              child: OmiSlider(
                value: value,
                max: max,
                divisions: divisions,
                onChanged: onChanged,
                onChangeEnd: onChangeEnd,
                semanticFormatterCallback: valueLabel,
              ),
            ),
          ),
          if (note != null) ...[
            const SizedBox(height: OmiSpacing.xxs),
            Text(note!, style: OmiType.footnote.copyWith(color: OmiColors.textTertiary)),
          ],
        ],
      ),
    );
  }
}
