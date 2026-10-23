import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import 'package:omi/pages/onboarding/find_device/page.dart';
import 'package:omi/providers/device_provider.dart';
import 'package:omi/providers/onboarding_provider.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/platform/platform_manager.dart';
import 'package:omi/widgets/device_widget.dart';
import 'package:omi/widgets/scanning_ripple.dart';

/// Pairing with no "do you have an Omi" question. The body is the Connect page's own: the same
/// ripple and device animation over [FindDevicesPage], which owns the scan, the nearby device
/// list, the tap-to-connect path and the "No Omi Found" help. Back or Not now leaves the step.
class PocketPairingStep extends StatefulWidget {
  const PocketPairingStep({super.key, required this.onDone});

  /// `true` when an Omi was connected, `false` when the reader left without one.
  final void Function(bool connected) onDone;

  @override
  State<PocketPairingStep> createState() => _PocketPairingStepState();
}

class _PocketPairingStepState extends State<PocketPairingStep> {
  bool _done = false;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) return;
      // The pendant was already connected when the step opened: pairing is done.
      final devices = context.read<DeviceProvider>();
      if (devices.isConnected && devices.connectedDevice != null) _finish(true);
    });
  }

  @override
  void dispose() {
    _done = true;
    super.dispose();
  }

  void _finish(bool connected) {
    // A connect that settles after the reader left (Back, Not now) must not advance twice.
    if (_done || !mounted) return;
    _done = true;
    PlatformManager.instance.analytics
        .track('Onboarding Device Choice', properties: {'choice': connected ? 'connected' : 'skipped'});
    widget.onDone(connected);
  }

  /// Back (button, system back or the iOS swipe) leaves as skipped; mid-connect it never claims a
  /// connection or opens the walkthrough.
  void _back() {
    final devices = context.read<DeviceProvider>();
    final onboarding = context.read<OnboardingProvider>();
    _finish(devices.isConnected && devices.connectedDevice != null && !onboarding.isClicked);
  }

  @override
  Widget build(BuildContext context) {
    return PopScope(
      canPop: false,
      onPopInvokedWithResult: (didPop, _) {
        if (!didPop) _back();
      },
      child: _scaffold(context),
    );
  }

  Widget _scaffold(BuildContext context) {
    final l10n = context.l10n;
    return Scaffold(
      backgroundColor: OmiColors.surface0,
      appBar: AppBar(
        leading: OmiBackButton(onPressed: _back),
      ),
      body: Consumer<OnboardingProvider>(
        builder: (context, onboardingProvider, child) {
          return ListView(
            children: [
              Padding(
                padding: const EdgeInsets.symmetric(horizontal: OmiSpacing.xl),
                child: Column(
                  children: [
                    Text(l10n.pairingPowerOnTitle, style: OmiType.title1, textAlign: TextAlign.center),
                    const SizedBox(height: OmiSpacing.xs),
                    Text(
                      l10n.pairingPowerOnSubtitle,
                      style: OmiType.body.copyWith(color: OmiColors.textSecondary),
                      textAlign: TextAlign.center,
                    ),
                  ],
                ),
              ),
              Stack(
                alignment: Alignment.center,
                children: [
                  if (!onboardingProvider.isConnected)
                    ScanningRippleWidget(
                      isScanning: !onboardingProvider.isConnected,
                      size: (MediaQuery.sizeOf(context).height <= 700 ? 280.0 : 360.0) *
                          (onboardingProvider.pairingFailureReason == null ? 1 : 0.5),
                    ),
                  DeviceAnimationWidget(
                    sizeMultiplier: onboardingProvider.pairingFailureReason == null ? 1 : 0.5,
                    isConnected: onboardingProvider.isConnected,
                    deviceName: onboardingProvider.deviceName,
                    deviceType: onboardingProvider.deviceType,
                    animatedBackground: onboardingProvider.isConnected,
                  ),
                ],
              ),
              FindDevicesPage(
                isFromOnboarding: true,
                goNext: () => _finish(true),
                onSkip: () => _finish(false),
              ),
            ],
          );
        },
      ),
    );
  }
}
