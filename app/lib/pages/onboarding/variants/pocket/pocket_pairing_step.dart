import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import 'package:omi/pages/capture/connect.dart';

import 'package:omi/providers/device_provider.dart';
import 'package:omi/providers/onboarding_provider.dart';
import 'package:omi/utils/platform/platform_manager.dart';

/// Pairing with no "do you have an Omi" question. The body is Home's Connect page itself
/// ([ConnectDevicePage]): the same scan, nearby device list, tap-to-connect path and help, plus
/// "Not now". Back or Not now leaves the step.
class PocketPairingStep extends StatefulWidget {
  const PocketPairingStep({super.key, required this.onDone});

  /// `true` when an Omi was connected, `false` when the reader left without one.
  final void Function(bool connected) onDone;

  @override
  State<PocketPairingStep> createState() => _PocketPairingStepState();
}

class _PocketPairingStepState extends State<PocketPairingStep> {
  bool _done = false;

  bool _advanceScheduled = false;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (mounted) _maybeAdvanceOnReconnect();
    });
  }

  /// The pendant already connected, or a saved one reconnecting on its own while the step is open,
  /// completes pairing once. A tap-to-connect still connecting or settling is left to
  /// [OnboardingProvider.handleTap], which calls goNext itself after its settle and persistence. A
  /// tap that finished after the reader left (Not now) advances here when they come back.
  void _maybeAdvanceOnReconnect() {
    if (_done || _advanceScheduled) return;
    final devices = context.read<DeviceProvider>();
    final onboarding = context.read<OnboardingProvider>();
    if (!devices.isConnected || devices.connectedDevice == null) return;
    if (onboarding.isClicked || onboarding.connectingToDeviceId != null || onboarding.isSettlingConnection) return;
    _advanceScheduled = true;
    WidgetsBinding.instance.addPostFrameCallback((_) {
      _advanceScheduled = false;
      if (!mounted || _done) return;
      // Re-check after the frame: the pendant may have dropped, or a tap may have started.
      final d = context.read<DeviceProvider>();
      final o = context.read<OnboardingProvider>();
      if (d.isConnected &&
          d.connectedDevice != null &&
          !o.isClicked &&
          o.connectingToDeviceId == null &&
          !o.isSettlingConnection) {
        _finish(true);
      }
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
    _finish(devices.isConnected &&
        devices.connectedDevice != null &&
        !onboarding.isClicked &&
        onboarding.connectingToDeviceId == null &&
        !onboarding.isSettlingConnection);
  }

  @override
  Widget build(BuildContext context) {
    return PopScope(
      canPop: false,
      onPopInvokedWithResult: (didPop, _) {
        if (!didPop) _back();
      },
      // Rebuilds on connection and tap-settle changes, so a delayed reconnect, or a tap that settled
      // after the reader left and came back, still advances.
      child: Consumer2<DeviceProvider, OnboardingProvider>(
        builder: (context, devices, onboarding, _) {
          WidgetsBinding.instance.addPostFrameCallback((_) {
            if (mounted) _maybeAdvanceOnReconnect();
          });
          return _scaffold(context);
        },
      ),
    );
  }

  Widget _scaffold(BuildContext context) {
    // The Home Connect page itself: same scan, device list and tap-to-connect as in the app.
    return ConnectDevicePage(onConnected: () => _finish(true), onSkip: () => _finish(false));
  }
}
