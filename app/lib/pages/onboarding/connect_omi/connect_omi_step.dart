import 'dart:async';

import 'package:flutter/material.dart';

import 'package:provider/provider.dart';

import 'package:omi/gen/assets.gen.dart';
import 'package:omi/pages/onboarding/find_device/found_devices.dart';
import 'package:omi/pages/shop/omi_shop.dart';
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
  const ConnectOmiStep({super.key, required this.onDone, this.openShop = openOmiShop});

  /// Called once with how the reader left the step.
  final void Function(OnboardingDeviceChoice choice) onDone;

  /// Opens the Omi store for "Not ordered yet"; replaceable in tests (no web view there).
  final Future<void> Function(BuildContext context, {required String source}) openShop;

  @override
  State<ConnectOmiStep> createState() => _ConnectOmiStepState();
}

class _ConnectOmiStepState extends State<ConnectOmiStep> with SingleTickerProviderStateMixin {
  OnboardingProvider? _provider;
  bool _done = false;

  /// The arrival: the device rises and grows in, then the title, the line under it and the links
  /// fade up one after another. A light tap marks the moment the device lands.
  late final AnimationController _entrance = AnimationController(
    vsync: this,
    duration: const Duration(milliseconds: 1400),
  );
  late final Animation<double> _device = CurvedAnimation(
    parent: _entrance,
    curve: const Interval(0.0, 0.55, curve: Curves.easeOutBack),
  );
  late final Animation<double> _title = CurvedAnimation(
    parent: _entrance,
    curve: const Interval(0.35, 0.7, curve: Curves.easeOutCubic),
  );
  late final Animation<double> _line = CurvedAnimation(
    parent: _entrance,
    curve: const Interval(0.45, 0.8, curve: Curves.easeOutCubic),
  );
  late final Animation<double> _links = CurvedAnimation(
    parent: _entrance,
    curve: const Interval(0.7, 1.0, curve: Curves.easeOut),
  );
  Timer? _landingTap;

  @override
  void initState() {
    super.initState();
    _provider = context.read<OnboardingProvider>();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) return;
      if (OmiMotion.of(context).emphasized == Duration.zero) {
        _entrance.value = 1;
        _scan();
      } else {
        // Let the arrival play before any Bluetooth guidance can cover it. A search started after
        // sign-in keeps finding devices in the meantime.
        _entrance.forward().whenComplete(() {
          if (mounted) _scan();
        });
        _landingTap = Timer(const Duration(milliseconds: 620), () {
          if (mounted) OmiHaptics.selection();
        });
      }
    });
  }

  /// Fades [child] up from slightly below as [animation] runs.
  Widget _rise(Animation<double> animation, Widget child, {double distance = 12}) {
    return AnimatedBuilder(
      animation: animation,
      child: child,
      builder: (context, child) {
        final t = animation.value.clamp(0.0, 1.0);
        return Opacity(
          opacity: t,
          child: Transform.translate(offset: Offset(0, (1 - t) * distance), child: child),
        );
      },
    );
  }

  @override
  void dispose() {
    _landingTap?.cancel();
    _entrance.dispose();
    _provider?.endSearch();
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

  /// "Not ordered yet": the Omi store opens inside the app; closing it carries on with onboarding.
  bool _shopOpen = false;
  Future<void> _notOrdered() async {
    if (_done || _shopOpen) return;
    _shopOpen = true;
    OmiHaptics.selection();
    await widget.openShop(context, source: 'onboarding_not_ordered');
    _shopOpen = false;
    if (mounted) _finish(OnboardingDeviceChoice.notOrdered);
  }

  void _finish(OnboardingDeviceChoice choice) {
    if (_done) return;
    _done = true;
    PlatformManager.instance.analytics.onboardingDeviceChoice(choice.wireValue);
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
    final stage = compact ? 220.0 : 260.0;
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
                  sizeMultiplier: compact ? 0.65 : 0.75,
                  isConnected: provider.isConnected,
                  deviceName: provider.isConnected ? provider.deviceName : shown?.name,
                  deviceType: provider.isConnected ? provider.deviceType : shown?.type,
                  modelNumber: shown?.modelNumber,
                ),
              )
            : Stack(
                alignment: Alignment.center,
                children: [
                  if (!cantFind) ScanningRippleWidget(isScanning: true, size: stage, color: OmiColors.textTertiary),
                  Assets.images.omiWithoutRopeTurnedOff.image(width: stage * 0.42, height: stage * 0.42),
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
            padding: const EdgeInsets.fromLTRB(OmiSpacing.xl, 0, OmiSpacing.xl, OmiSpacing.sm),
            child: Column(
              children: [
                Expanded(
                  child: Center(
                    child: SingleChildScrollView(
                      child: Column(
                        mainAxisSize: MainAxisSize.min,
                        children: [
                          AnimatedBuilder(
                            animation: _device,
                            child: SizedBox(height: stage, child: Center(child: visual)),
                            builder: (context, child) {
                              final t = _device.value;
                              return Opacity(
                                opacity: t.clamp(0.0, 1.0),
                                child: Transform.translate(
                                  offset: Offset(0, (1 - t) * 24),
                                  child: Transform.scale(scale: 0.7 + 0.3 * t, child: child),
                                ),
                              );
                            },
                          ),
                          const SizedBox(height: OmiSpacing.xxl),
                          _rise(
                            _title,
                            Semantics(
                              header: true,
                              child:
                                  Text(l10n.onboardingConnectOmi, style: OmiType.title1, textAlign: TextAlign.center),
                            ),
                          ),
                          const SizedBox(height: OmiSpacing.xs),
                          // A narrow measure so the instruction wraps evenly instead of leaving one word behind.
                          _rise(
                            _line,
                            ConstrainedBox(
                              constraints: const BoxConstraints(maxWidth: 280),
                              child: Text(
                                subtitle,
                                key: const Key('connect_omi_status'),
                                style: OmiType.subhead.copyWith(color: OmiColors.textSecondary, height: 1.35),
                                textAlign: TextAlign.center,
                              ),
                            ),
                          ),
                          const SizedBox(height: OmiSpacing.lg),
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
                              onPressed: _scanAgain,
                            ),
                            OmiButton.tertiary(
                              key: const Key('connect_omi_how_to_pair'),
                              label: l10n.howToPair,
                              onPressed: _showConnectionGuide,
                            ),
                          ],
                        ],
                      ),
                    ),
                  ),
                ),
                if (!provider.isConnected)
                  _rise(
                      _links,
                      Column(mainAxisSize: MainAxisSize.min, children: [
                        Text(
                          l10n.onboardingNoOmiYet,
                          style: OmiType.footnote.copyWith(color: OmiColors.textTertiary),
                          textAlign: TextAlign.center,
                        ),
                        // Quiet links, not buttons: they must not compete with the device above.
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
                            Container(width: 1, height: 14, color: OmiColors.border),
                            Flexible(
                              child: OmiButton.tertiary(
                                key: const Key('connect_omi_not_ordered'),
                                label: l10n.onboardingOmiNotOrdered,
                                size: OmiButtonSize.compact,
                                onPressed: _notOrdered,
                              ),
                            ),
                          ],
                        ),
                      ]),
                      distance: 8),
              ],
            ),
          ),
        );
      },
    );
  }
}
