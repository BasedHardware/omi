import 'package:flutter/material.dart';

import '../content.dart';
import '../theme.dart';
import '../v2/paywall_first_screens.dart';
import '../widgets.dart';
import 'app_state.dart';

/// Opens the in-app paywall (same design as onboarding). Returns true if the
/// user started a trial.
Future<bool> showUpgrade(BuildContext context, {bool capHit = false}) async {
  final state = OmiAppScope.of(context);
  final started = await pushDf<bool>(context, (_) => UpgradePage(state: state, capHit: capHit));
  return started ?? false;
}

enum _UpgradeStep { paywall, web, appStore }

class UpgradePage extends StatefulWidget {
  const UpgradePage({super.key, required this.state, this.capHit = false});

  final OmiAppState state;
  final bool capHit;

  @override
  State<UpgradePage> createState() => _UpgradePageState();
}

class _UpgradePageState extends State<UpgradePage> {
  _UpgradeStep _step = _UpgradeStep.paywall;

  // Users who already declined in onboarding get the winback length here.
  static const int _days = DfOffer.winbackDays;

  void _confirm() {
    widget.state.upgrade(_days);
    Navigator.of(context).pop(true);
  }

  @override
  Widget build(BuildContext context) {
    final t = DfThemeScope.of(context);
    final paywall = PaywallV2Screen(
      trialDays: _days,
      today: widget.state.today,
      mode: widget.capHit ? PaywallMode.capHit : PaywallMode.onboarding,
      onTryWeb: () => setState(() => _step = _UpgradeStep.web),
      onTryAppStore: () => setState(() => _step = _UpgradeStep.appStore),
      onClose: () => Navigator.of(context).pop(false),
    );
    void back() => setState(() => _step = _UpgradeStep.paywall);
    return Scaffold(
      backgroundColor: t.background,
      body: switch (_step) {
        _UpgradeStep.paywall => paywall,
        _UpgradeStep.web => DfSheetOver(
            behind: paywall,
            sheet: WebCheckoutSheet(trialDays: _days, today: widget.state.today, onConfirm: _confirm, onClose: back),
          ),
        _UpgradeStep.appStore => DfSheetOver(
            behind: paywall,
            sheet: AppStoreSheet(trialDays: _days, today: widget.state.today, onConfirm: _confirm, onClose: back),
          ),
      },
    );
  }
}
