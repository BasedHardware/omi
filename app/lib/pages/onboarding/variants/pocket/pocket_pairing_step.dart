import 'dart:async';

import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/gen/assets.gen.dart';
import 'package:omi/providers/onboarding_provider.dart';
import 'package:omi/services/devices/bluetooth_readiness.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/platform/platform_manager.dart';
import 'package:omi/widgets/connection_guide_sheet.dart';
import 'package:omi/widgets/scanning_ripple.dart';

/// Pairing that starts by itself: no "do you have an Omi" question. The scan runs as the step
/// opens; the first Omi found is connected through the same path as a tap on the pairing page
/// ([OnboardingProvider.handleTap]), once per device, and the step moves on when it settles. A
/// failed attempt offers Scan again. Back (or Skip) leaves it for readers without an Omi at hand.
class PocketPairingStep extends StatefulWidget {
  const PocketPairingStep({super.key, required this.onDone});

  /// `true` when an Omi was connected, `false` when the reader left without one.
  final void Function(bool connected) onDone;

  @override
  State<PocketPairingStep> createState() => _PocketPairingStepState();
}

class _PocketPairingStepState extends State<PocketPairingStep> {
  OnboardingProvider? _provider;
  bool _done = false;
  bool _showHelp = false;
  Timer? _helpTimer;

  /// The device an attempt was started for; never retried on its own (Scan again clears it).
  String? _attemptedId;
  bool _failed = false;

  @override
  void initState() {
    super.initState();
    _helpTimer = Timer(const Duration(seconds: 12), () {
      if (mounted) setState(() => _showHelp = true);
    });
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) return;
      _provider = context.read<OnboardingProvider>();
      unawaited(_scan());
    });
  }

  @override
  void dispose() {
    _helpTimer?.cancel();
    if (!_done) _provider?.cancelActiveScan();
    // Invalidates the pending handleTap success callback and post-frame connect.
    _done = true;
    super.dispose();
  }

  /// Connects the first Omi the scan found, exactly once per device, through the pairing page's
  /// own path. Runs after the frame so the provider is never mutated during build.
  void _maybeConnect(OnboardingProvider provider) {
    if (_done || _failed || provider.isConnected || provider.isClicked) return;
    BtDevice? candidate;
    for (final device in provider.deviceList) {
      if (device.type == DeviceType.omi) {
        candidate = device;
        break;
      }
    }
    if (candidate == null || candidate.id == _attemptedId) return;
    _attemptedId = candidate.id;
    final device = candidate;
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted || _done) return;
      unawaited(provider.handleTap(device: device, isFromOnboarding: true, goNext: () => _finish(true)).then((_) {
        if (!mounted || _done || provider.isConnected) return;
        // handleTap swallowed a failure: offer a fresh scan instead of searching forever.
        setState(() {
          _failed = true;
          _showHelp = true;
        });
      }));
    });
  }

  Future<void> _scanAgain() async {
    OmiHaptics.selection();
    _provider?.cancelActiveScan();
    setState(() {
      _failed = false;
      _attemptedId = null;
    });
    await _scan();
  }

  Future<void> _scan() async {
    void publishGuidance() {
      if (mounted) unawaited(BluetoothReadiness.instance.ensureReady(BluetoothUse.discovery));
    }

    await _provider?.scanDevices(onShowDialog: publishGuidance, onShowLocationDialog: publishGuidance);
  }

  void _finish(bool connected) {
    // A connect that settles after the reader left the step (Back, Skip, or the step was
    // disposed) must not advance onboarding a second time or touch a dead context.
    if (_done || !mounted) return;
    _done = true;
    PlatformManager.instance.analytics
        .track('Onboarding Device Choice', properties: {'choice': connected ? 'connected' : 'skipped'});
    if (!connected) _provider?.cancelActiveScan();
    widget.onDone(connected);
  }

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    final pixelRatio = MediaQuery.of(context).devicePixelRatio;
    const imageSize = 150.0;
    return Consumer<OnboardingProvider>(
      builder: (context, provider, _) {
        _maybeConnect(provider);
        final connected = provider.isConnected;
        final connecting = provider.isClicked && !connected;
        return Scaffold(
          backgroundColor: OmiColors.surface0,
          body: SafeArea(
            child: Column(
              children: [
                Align(
                  alignment: Alignment.centerLeft,
                  child: OmiBackButton(onPressed: () => _finish(false)),
                ),
                const SizedBox(height: OmiSpacing.lg),
                Padding(
                  padding: const EdgeInsets.symmetric(horizontal: OmiSpacing.xl),
                  child: Column(
                    children: [
                      Text(
                        connected ? l10n.connected : l10n.pairingPowerOnTitle,
                        style: OmiType.title1,
                        textAlign: TextAlign.center,
                      ),
                      const SizedBox(height: OmiSpacing.xs),
                      Text(
                        connected
                            ? provider.deviceName
                            : _failed
                                ? l10n.connectionFailed
                                : l10n.pairingPowerOnSubtitle,
                        style: OmiType.body.copyWith(color: OmiColors.textSecondary),
                        textAlign: TextAlign.center,
                      ),
                    ],
                  ),
                ),
                const Spacer(),
                Stack(
                  alignment: Alignment.center,
                  children: [
                    if (!connected)
                      ScanningRippleWidget(
                          isScanning: true,
                          size: imageSize + 140,
                          color: OmiColors.textPrimary.withValues(alpha: 0.25)),
                    Image.asset(
                      Assets.images.omiWithoutRope.path,
                      height: imageSize,
                      width: imageSize,
                      cacheHeight: (imageSize * pixelRatio).round(),
                      cacheWidth: (imageSize * pixelRatio).round(),
                    ),
                  ],
                ),
                const SizedBox(height: OmiSpacing.lg),
                if (!connected && !_failed)
                  Row(
                    mainAxisAlignment: MainAxisAlignment.center,
                    children: [
                      const OmiSpinner(size: OmiSpinnerSize.small),
                      const SizedBox(width: OmiSpacing.sm),
                      Text(
                        connecting ? l10n.deviceConnecting : l10n.pairingLookingForOmi,
                        style: OmiType.callout.copyWith(color: OmiColors.textSecondary),
                      ),
                    ],
                  ),
                const Spacer(),
                AnimatedOpacity(
                  opacity: _showHelp && !connected ? 1 : 0,
                  duration: const Duration(milliseconds: 300),
                  child: Padding(
                    padding: const EdgeInsets.symmetric(horizontal: OmiSpacing.xl),
                    child: Column(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        if (_failed)
                          OmiButton(
                            key: const Key('pocket_pairing_scan_again'),
                            label: l10n.scanAgain,
                            icon: Icons.refresh,
                            onPressed: _scanAgain,
                          ),
                        OmiButton.tertiary(
                          key: const Key('pocket_pairing_how_to_pair'),
                          label: l10n.howToPair,
                          onPressed: () {
                            PlatformManager.instance.analytics.connectionGuideOpened();
                            ConnectionGuideSheet.show(context);
                          },
                        ),
                        OmiButton.tertiary(
                          key: const Key('pocket_pairing_skip'),
                          label: l10n.skipForNow,
                          onPressed: () => _finish(false),
                        ),
                      ],
                    ),
                  ),
                ),
                const SizedBox(height: OmiSpacing.lg),
              ],
            ),
          ),
        );
      },
    );
  }
}
