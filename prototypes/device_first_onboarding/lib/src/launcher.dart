import 'package:flutter/material.dart';

import 'app/app_gallery.dart';
import 'app/app_shell.dart';
import 'content.dart';
import 'flow.dart';
import 'theme.dart';
import 'v2/paywall_first_flow.dart';
import 'widgets.dart';

enum PrototypeFlow {
  paywallFirst('Paywall first'),
  deviceFirst('Device first (v1)');

  const PrototypeFlow(this.label);

  final String label;
}

/// Pick a flow, a direction and a trial arm, then play it or jump to any
/// onboarding or app screen.
class PrototypeLauncher extends StatefulWidget {
  const PrototypeLauncher({super.key, this.today});

  /// Fixed "today" for tests; defaults to the real date.
  final DateTime? today;

  @override
  State<PrototypeLauncher> createState() => _PrototypeLauncherState();
}

class _PrototypeLauncherState extends State<PrototypeLauncher> {
  PrototypeFlow _flow = PrototypeFlow.paywallFirst;
  DfDirection _direction = DfDirection.auroraLight;
  TrialLength _trial = TrialLength.oneWeek;
  bool _unlimited = false;

  DateTime get _today => dfDay(widget.today ?? DateTime.now());

  List<TrialLength> get _arms => _flow == PrototypeFlow.paywallFirst ? DfOffer.paywallFirstArms : TrialLength.values;

  void _push(Widget Function(VoidCallback exit) page) {
    final navigator = Navigator.of(context);
    navigator.push(MaterialPageRoute<void>(builder: (_) => page(() => navigator.pop())));
  }

  void _openV2(V2Step step) => _push(
        (exit) => PaywallFirstFlow(
          direction: _direction,
          trial: _trial,
          today: _today,
          initialStep: step,
          onExit: exit,
        ),
      );

  void _openV1(DfStep step) => _push(
        (exit) => DeviceFirstFlow(direction: _direction, trial: _trial, initialStep: step, onExit: exit),
      );

  void _openApp(WidgetBuilder? home) {
    final theme = DfTheme.of(_direction);
    _push(
      (exit) => DfThemeScope(
        theme: theme,
        child: Scaffold(
          backgroundColor: theme.background,
          body: OmiApp(
            plan: _unlimited ? const DfPlanState.trial(DfOffer.winbackDays) : const DfPlanState.free(),
            today: _today,
            home: home,
            onExit: exit,
          ),
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final theme = DfTheme.of(_direction);
    final chevron = Icon(Icons.chevron_right, color: theme.textTertiary);
    return DfThemeScope(
      theme: theme,
      child: DfStatusBar(
        child: Scaffold(
          backgroundColor: theme.background,
          body: DfPage(
            wash: true,
            children: <Widget>[
              const DfEyebrow('Omi · design prototype'),
              const DfHeadline('Onboarding, paywall & app'),
              const DfBody('Pick a flow, a look and a trial arm, then play it or jump to any screen.'),
              const DfEyebrow('Flow'),
              _Choices<PrototypeFlow>(
                values: PrototypeFlow.values,
                selected: _flow,
                label: (f) => f.label,
                onSelected: (f) => setState(() {
                  _flow = f;
                  if (!_arms.contains(_trial)) _trial = TrialLength.oneWeek;
                }),
              ),
              const DfEyebrow('Look'),
              _Choices<DfDirection>(
                values: DfDirection.values,
                selected: _direction,
                label: (d) => d.label,
                onSelected: (d) => setState(() => _direction = d),
              ),
              const DfEyebrow('Trial length'),
              _Choices<TrialLength>(
                values: _arms,
                selected: _trial,
                label: (t) => t.label,
                onSelected: (t) => setState(() => _trial = t),
              ),
              DfButton(
                'Play the flow',
                onPressed: () =>
                    _flow == PrototypeFlow.paywallFirst ? _openV2(V2Step.welcome) : _openV1(DfStep.welcome),
              ),
              const DfEyebrow('Jump to an onboarding screen'),
              DfCard(
                child: Column(
                  children: <Widget>[
                    if (_flow == PrototypeFlow.paywallFirst)
                      for (final step in V2Step.values.where((s) => s != V2Step.app))
                        DfListRow(label: step.title, trailing: chevron, onTap: () => _openV2(step))
                    else
                      for (final step in DfStep.values.where((s) => s != DfStep.end))
                        DfListRow(label: step.title, trailing: chevron, onTap: () => _openV1(step)),
                  ],
                ),
              ),
              const DfEyebrow('App screens'),
              _Choices<bool>(
                values: const <bool>[false, true],
                selected: _unlimited,
                label: (u) => u ? 'Unlimited (trial)' : 'Free',
                onSelected: (u) => setState(() => _unlimited = u),
              ),
              DfButton('Open the app', kind: DfButtonKind.secondary, onPressed: () => _openApp(null)),
              DfCard(
                child: Column(
                  children: <Widget>[
                    for (final (title, builder) in appScreens)
                      DfListRow(label: title, trailing: chevron, onTap: () => _openApp(builder)),
                  ],
                ),
              ),
            ],
          ),
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
                  border: t.isLight && value != selected ? Border.all(color: t.border) : null,
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
