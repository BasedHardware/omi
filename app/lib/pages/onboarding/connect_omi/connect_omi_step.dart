import 'dart:async';

import 'package:flutter/material.dart';

import 'package:provider/provider.dart';

import 'package:omi/gen/assets.gen.dart';
import 'package:omi/pages/onboarding/find_device/found_devices.dart';
import 'package:omi/providers/onboarding_provider.dart';
import 'package:omi/services/devices/bluetooth_readiness.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/platform/platform_manager.dart';
import 'package:omi/widgets/connection_guide_sheet.dart';
import 'package:omi/widgets/device_widget.dart';
import 'package:omi/widgets/scanning_ripple.dart';

/// What the reader told the connect step about their Omi. Sent as `choice` on
/// `Onboarding Device Choice`.
enum OnboardingDeviceChoice {
  connected('connected'),
  ordered('ordered'),
  notOrdered('not_ordered');

  const OnboardingDeviceChoice(this.wireValue);
  final String wireValue;
}

/// First-run "Connect your Omi" step.
///
/// The search started in the background right after sign-in, so a reader whose Omi is on and nearby
/// sees it revealed as the step opens. Otherwise the step searches with instructions, and readers
/// without their Omi say whether it is on its way or not ordered yet.
class ConnectOmiStep extends StatefulWidget {
  const ConnectOmiStep({super.key, required this.onDone});

  /// Called once with how the reader left the step.
  final void Function(OnboardingDeviceChoice choice) onDone;

  @override
  State<ConnectOmiStep> createState() => _ConnectOmiStepState();
}

class _ConnectOmiStepState extends State<ConnectOmiStep> {
  OnboardingProvider? _provider;
  bool _done = false;

  @override
  void initState() {
    super.initState();
    _provider = context.read<OnboardingProvider>();
    WidgetsBinding.instance.addPostFrameCallback((_) => _scan());
  }

  @override
  void dispose() {
    _provider?.cancelActiveScan();
    _provider = null;
    super.dispose();
  }

  /// A missing permission goes through the shared Bluetooth guidance prompt, like the pairing page.
  Future<void> _scan() async {
    void publishGuidance() {
      if (mounted) unawaited(BluetoothReadiness.instance.ensureReady(BluetoothUse.discovery));
    }

    await _provider?.scanDevices(onShowDialog: publishGuidance, onShowLocationDialog: publishGuidance);
  }

  Future<void> _scanAgain() async {
    OmiHaptics.selection();
    _provider?.cancelActiveScan();
    _provider?.enableInstructions = false;
    setState(() {});
    await _scan();
  }

  void _finish(OnboardingDeviceChoice choice) {
    if (_done) return;
    _done = true;
    PlatformManager.instance.analytics.track('Onboarding Device Choice', properties: {'choice': choice.wireValue});
    widget.onDone(choice);
  }

  void _showConnectionGuide() {
    PlatformManager.instance.analytics.connectionGuideOpened();
    ConnectionGuideSheet.show(context);
  }

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    final compact = MediaQuery.sizeOf(context).height <= 700;
    return Consumer<OnboardingProvider>(
      builder: (context, provider, child) {
        final devices = provider.visibleDeviceList;
        final found = provider.isConnected || devices.isNotEmpty;
        final cantFind = !found && provider.enableInstructions;
        final shown = devices.isNotEmpty ? devices.first : null;

        final Widget visual = found
            ? TweenAnimationBuilder<double>(
                // The reveal: the found device grows in from the search.
                key: ValueKey('connect_omi_reveal_${shown?.id ?? provider.deviceId}'),
                tween: Tween(begin: 0, end: 1),
                duration: OmiMotion.of(context).emphasized == Duration.zero
                    ? Duration.zero
                    : const Duration(milliseconds: 700),
                curve: Curves.easeOutBack,
                builder: (context, t, child) => Opacity(
                  opacity: t.clamp(0.0, 1.0),
                  child: Transform.scale(scale: 0.6 + 0.4 * t, child: child),
                ),
                child: DeviceAnimationWidget(
                  sizeMultiplier: compact ? 0.8 : 1.0,
                  isConnected: provider.isConnected,
                  deviceName: provider.isConnected ? provider.deviceName : shown?.name,
                  deviceType: provider.isConnected ? provider.deviceType : shown?.type,
                  modelNumber: shown?.modelNumber,
                ),
              )
            : Stack(
                alignment: Alignment.center,
                children: [
                  if (!cantFind) ScanningRippleWidget(isScanning: true, size: compact ? 240 : 300),
                  Assets.images.omiWithoutRopeTurnedOff.image(width: compact ? 110 : 140, height: compact ? 110 : 140),
                ],
              );

        final String subtitle = provider.isConnected
            ? l10n.pairingSuccessful
            : found
                ? l10n.devicesFoundNearby(provider.nearbyDeviceCount == 0 ? devices.length : provider.nearbyDeviceCount)
                : cantFind
                    ? l10n.cantFindDeviceHint
                    : l10n.pairingDescOmi;

        return SafeArea(
          child: Padding(
            padding: const EdgeInsets.symmetric(horizontal: OmiSpacing.xl),
            child: Column(
              children: [
                Expanded(child: Center(child: visual)),
                Semantics(
                  header: true,
                  child: Text(l10n.connectOmiDevice, style: OmiType.title1, textAlign: TextAlign.center),
                ),
                const SizedBox(height: OmiSpacing.xs),
                Text(
                  subtitle,
                  key: const Key('connect_omi_status'),
                  style: OmiType.subhead.copyWith(color: OmiColors.textSecondary),
                  textAlign: TextAlign.center,
                ),
                const SizedBox(height: OmiSpacing.md),
                // The tappable device rows; stays mounted because it owns the connection handling.
                FoundDevices(
                  goNext: () => _finish(OnboardingDeviceChoice.connected),
                  isFromOnboarding: true,
                  onRescan: _scanAgain,
                  showStatus: false,
                ),
                if (cantFind) ...[
                  OmiButton(
                    key: const Key('connect_omi_scan_again'),
                    label: l10n.scanAgain,
                    icon: Icons.refresh,
                    expand: true,
                    onPressed: _scanAgain,
                  ),
                  const SizedBox(height: OmiSpacing.xs),
                  OmiButton.secondary(
                    key: const Key('connect_omi_how_to_pair'),
                    label: l10n.howToPair,
                    expand: true,
                    onPressed: _showConnectionGuide,
                  ),
                ],
                const SizedBox(height: OmiSpacing.lg),
                if (!provider.isConnected) ...[
                  Text(
                    l10n.onboardingNoOmiYet,
                    style: OmiType.footnote.copyWith(color: OmiColors.textTertiary),
                    textAlign: TextAlign.center,
                  ),
                  Row(
                    mainAxisAlignment: MainAxisAlignment.center,
                    children: [
                      Flexible(
                        child: OmiButton.tertiary(
                          key: const Key('connect_omi_ordered'),
                          label: l10n.onboardingOmiOrdered,
                          size: OmiButtonSize.compact,
                          onPressed: () => _finish(OnboardingDeviceChoice.ordered),
                        ),
                      ),
                      Flexible(
                        child: OmiButton.tertiary(
                          key: const Key('connect_omi_not_ordered'),
                          label: l10n.onboardingOmiNotOrdered,
                          size: OmiButtonSize.compact,
                          onPressed: () => _finish(OnboardingDeviceChoice.notOrdered),
                        ),
                      ),
                    ],
                  ),
                ],
                const SizedBox(height: OmiSpacing.sm),
              ],
            ),
          ),
        );
      },
    );
  }
}
