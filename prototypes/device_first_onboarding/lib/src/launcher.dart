import 'package:flutter/material.dart';

import 'content.dart';
import 'flow.dart';
import 'theme.dart';
import 'widgets.dart';

/// Pick a direction and a trial arm, then play the flow or jump to a screen.
class PrototypeLauncher extends StatefulWidget {
  const PrototypeLauncher({super.key});

  @override
  State<PrototypeLauncher> createState() => _PrototypeLauncherState();
}

class _PrototypeLauncherState extends State<PrototypeLauncher> {
  DfDirection _direction = DfDirection.graphite;
  TrialLength _trial = TrialLength.oneMonth;

  void _open(DfStep step) {
    final navigator = Navigator.of(context);
    navigator.push(
      MaterialPageRoute<void>(
        builder: (_) =>
            DeviceFirstFlow(direction: _direction, trial: _trial, initialStep: step, onExit: () => navigator.pop()),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final theme = DfTheme.of(_direction);
    return DfThemeScope(
      theme: theme,
      child: Scaffold(
        backgroundColor: theme.background,
        body: DfPage(
          children: <Widget>[
            const DfEyebrow('Omi · design prototype'),
            const DfHeadline('Device-first onboarding'),
            const DfBody('Pick a direction and a trial length, then play the flow or jump to any screen.'),
            const DfEyebrow('Direction'),
            _Choices<DfDirection>(
              values: DfDirection.values,
              selected: _direction,
              label: (d) => d.label,
              onSelected: (d) => setState(() => _direction = d),
            ),
            const DfEyebrow('Trial length'),
            _Choices<TrialLength>(
              values: TrialLength.values,
              selected: _trial,
              label: (t) => t.label,
              onSelected: (t) => setState(() => _trial = t),
            ),
            DfButton('Play the flow', onPressed: () => _open(DfStep.welcome)),
            const DfEyebrow('Jump to a screen'),
            DfCard(
              child: Column(
                children: <Widget>[
                  for (final step in DfStep.values.where((s) => s != DfStep.end))
                    DfListRow(
                      label: step.title,
                      trailing: Icon(Icons.chevron_right, color: theme.textTertiary),
                      onTap: () => _open(step),
                    ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _Choices<T> extends StatelessWidget {
  const _Choices({required this.values, required this.selected, required this.label, required this.onSelected});

  final List<T> values;
  final T selected;
  final String Function(T) label;
  final ValueChanged<T> onSelected;

  @override
  Widget build(BuildContext context) {
    final t = DfThemeScope.of(context);
    return Wrap(
      spacing: 8,
      runSpacing: 8,
      children: <Widget>[
        for (final value in values)
          Semantics(
            button: true,
            selected: value == selected,
            child: GestureDetector(
              onTap: () => onSelected(value),
              child: Container(
                padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 10),
                decoration: BoxDecoration(
                  color: value == selected ? t.accent : t.surface,
                  borderRadius: BorderRadius.circular(20),
                ),
                child: Text(
                  label(value),
                  style: t.label(color: value == selected ? t.onAccent : t.text, weight: FontWeight.w600),
                ),
              ),
            ),
          ),
      ],
    );
  }
}
