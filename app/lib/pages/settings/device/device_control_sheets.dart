import 'package:flutter/material.dart';

import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';

/// The label of a mic-gain level (0 = mute … 8 = +40 dB). Decibel values are not translated.
String micGainLevelLabel(BuildContext context, int level) {
  const decibels = ['-20dB', '-10dB', '+0dB', '+6dB', '+10dB', '+20dB', '+30dB', '+40dB'];
  if (level == 0) return context.l10n.mute;
  return level >= 1 && level <= decibels.length ? decibels[level - 1] : '';
}

String _micGainDescription(BuildContext context, int level) {
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
              trailing: i == current ? const Icon(Icons.check, color: OmiColors.textPrimary, size: 20) : null,
              onTap: () => Navigator.of(sheetContext).pop(i),
            ),
          ),
      ],
    ),
  );
}

/// LED brightness (0–100 %). [onChanged] fires while dragging, [onChangeEnd] when released.
Future<void> showLedBrightnessSheet(
  BuildContext context, {
  required double initial,
  required ValueChanged<double> onChanged,
  required ValueChanged<double> onChangeEnd,
}) {
  return showOmiSheet<void>(
    context: context,
    title: context.l10n.ledBrightness,
    padding: const EdgeInsets.fromLTRB(OmiSpacing.lg, 0, OmiSpacing.lg, OmiSpacing.md),
    builder: (_) => _LevelSheetBody(
      initial: initial,
      max: 100,
      divisions: 100,
      valueLabel: (_, value) => '${value.round()}%',
      minLabel: (context) => context.l10n.off,
      onChanged: onChanged,
      onChangeEnd: onChangeEnd,
    ),
  );
}

/// Mic gain (level 0–8) with Quiet / Normal / High presets.
Future<void> showMicGainSheet(
  BuildContext context, {
  required double initial,
  required ValueChanged<double> onChanged,
  required ValueChanged<double> onChangeEnd,
}) {
  return showOmiSheet<void>(
    context: context,
    title: context.l10n.micGain,
    padding: const EdgeInsets.fromLTRB(OmiSpacing.lg, 0, OmiSpacing.lg, OmiSpacing.md),
    builder: (_) => _LevelSheetBody(
      initial: initial,
      max: 8,
      divisions: 8,
      valueLabel: (context, value) => micGainLevelLabel(context, value.round()),
      description: (context, value) => _micGainDescription(context, value.round()),
      minLabel: (context) => context.l10n.mute,
      presets: (context) => [(context.l10n.quiet, 2.0), (context.l10n.normal, 4.0), (context.l10n.high, 6.0)],
      onChanged: onChanged,
      onChangeEnd: onChangeEnd,
    ),
  );
}

class _LevelSheetBody extends StatefulWidget {
  const _LevelSheetBody({
    required this.initial,
    required this.max,
    required this.divisions,
    required this.valueLabel,
    required this.minLabel,
    required this.onChanged,
    required this.onChangeEnd,
    this.description,
    this.presets,
  });

  final double initial;
  final double max;
  final int divisions;
  final String Function(BuildContext context, double value) valueLabel;
  final String Function(BuildContext context, double value)? description;
  final String Function(BuildContext context) minLabel;
  final List<(String, double)> Function(BuildContext context)? presets;
  final ValueChanged<double> onChanged;
  final ValueChanged<double> onChangeEnd;

  @override
  State<_LevelSheetBody> createState() => _LevelSheetBodyState();
}

class _LevelSheetBodyState extends State<_LevelSheetBody> {
  late double _value = widget.initial;

  @override
  Widget build(BuildContext context) {
    final captionStyle = OmiType.caption.copyWith(color: OmiColors.textTertiary);
    final presets = widget.presets?.call(context);
    return Column(
      mainAxisSize: MainAxisSize.min,
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Text(widget.valueLabel(context, _value), style: OmiType.title3, textAlign: TextAlign.center),
        if (widget.description != null) ...[
          const SizedBox(height: OmiSpacing.xs),
          Text(
            widget.description!(context, _value),
            textAlign: TextAlign.center,
            style: OmiType.footnote.copyWith(color: OmiColors.textSecondary),
          ),
        ],
        const SizedBox(height: OmiSpacing.md),
        SliderTheme(
          data: SliderThemeData(
            activeTrackColor: OmiColors.accent,
            inactiveTrackColor: OmiColors.surface3,
            thumbColor: OmiColors.accent,
            overlayColor: OmiColors.accent.withValues(alpha: 0.1),
            thumbShape: const RoundSliderThumbShape(enabledThumbRadius: 12, elevation: 2),
            overlayShape: const RoundSliderOverlayShape(overlayRadius: 24),
            trackHeight: 6,
          ),
          child: Slider(
            value: _value,
            min: 0,
            max: widget.max,
            divisions: widget.divisions,
            label: widget.valueLabel(context, _value),
            onChanged: (value) {
              setState(() => _value = value);
              widget.onChanged(value);
            },
            onChangeEnd: widget.onChangeEnd,
          ),
        ),
        Row(
          mainAxisAlignment: MainAxisAlignment.spaceBetween,
          children: [
            Text(widget.minLabel(context), style: captionStyle),
            Text(context.l10n.max, style: captionStyle),
          ],
        ),
        if (presets != null) ...[
          const SizedBox(height: OmiSpacing.lg),
          Row(
            children: [
              for (var i = 0; i < presets.length; i++) ...[
                if (i > 0) const SizedBox(width: OmiSpacing.xs),
                Expanded(child: _presetButton(presets[i].$1, presets[i].$2)),
              ],
            ],
          ),
        ],
      ],
    );
  }

  Widget _presetButton(String label, double level) {
    void select() {
      setState(() => _value = level);
      widget.onChangeEnd(level);
    }

    final selected = _value.round() == level.round();
    return Semantics(
      selected: selected,
      child: selected
          ? OmiButton(label: label, onPressed: select, size: OmiButtonSize.compact, expand: true)
          : OmiButton.secondary(label: label, onPressed: select, size: OmiButtonSize.compact, expand: true),
    );
  }
}
