import 'dart:async';
import 'dart:math' as math;

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
import 'package:omi/pages/onboarding/variants/yinka/widgets/onboarding_card.dart';

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

class _ConnectOmiStepState extends State<ConnectOmiStep> with TickerProviderStateMixin {
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

  /// The moment the Omi connects: a ring draws around it, a ✓ lands on the ring and one soft pulse
  /// goes out, the title says Connected, then the step moves on by itself.
  late final AnimationController _celebration = AnimationController(
    vsync: this,
    duration: const Duration(milliseconds: 1100),
  );
  bool _celebrating = false;

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
    _celebration.dispose();
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

  /// How the reader left the step: `connected`, `ordered` or `not_ordered`. Also kept on the person,
  /// so buyers who say they ordered can be matched to Shopify orders later.
  static void _trackDeviceChoice(String choice) {
    PlatformManager.instance.analytics.track('Onboarding Device Choice', properties: {'choice': choice});
    PlatformManager.instance.analytics.setUserProperty('Onboarding Device Choice', choice);
  }

  void _finish(OnboardingDeviceChoice choice) {
    if (_done) return;
    _done = true;
    _trackDeviceChoice(choice.wireValue);
    widget.onDone(choice);
  }

  /// Connected: hold the step for the celebration (long enough to read "Connected"), then move on.
  Future<void> _connected() async {
    if (_done) return;
    _done = true;
    _trackDeviceChoice(OnboardingDeviceChoice.connected.wireValue);
    final still = OmiMotion.of(context).emphasized == Duration.zero;
    setState(() => _celebrating = true);
    if (still) {
      _celebration.value = 1;
    } else {
      await _celebration.forward();
    }
    await Future<void>.delayed(Duration(milliseconds: still ? 1200 : 700));
    if (mounted) widget.onDone(OnboardingDeviceChoice.connected);
  }

  void _showConnectionGuide() {
    PlatformManager.instance.analytics.connectionGuideOpened();
    ConnectionGuideSheet.show(context);
  }

  bool _feltFound = false;
  bool _feltConnected = false;

  /// A light tap when the Omi appears, a firmer one when it is connected: felt, not only seen.
  void _feelProgress({required bool found, required bool connected}) {
    if (found && !_feltFound) {
      _feltFound = true;
      WidgetsBinding.instance.addPostFrameCallback((_) => OmiHaptics.light());
    }
    if (connected && !_feltConnected) {
      _feltConnected = true;
      WidgetsBinding.instance.addPostFrameCallback((_) => OmiHaptics.success());
    }
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
        _feelProgress(found: found, connected: provider.isConnected);

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
            ? (provider.deviceName.isNotEmpty ? provider.deviceName : l10n.connected)
            : found
                ? l10n.onboardingConnectTapToConnect
                : cantFind
                    ? l10n.cantFindDeviceHint
                    : l10n.pairingDescOmi;

        return SafeArea(
          child: Padding(
            padding: const EdgeInsets.fromLTRB(OmiSpacing.xl, 0, OmiSpacing.xl, kOnboardingButtonBottomGap),
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
                            child: SizedBox(
                              height: stage,
                              child: _ConnectedHalo(
                                progress: _celebration,
                                active: _celebrating,
                                diameter: stage * 0.86,
                                child: Center(child: visual),
                              ),
                            ),
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
                              liveRegion: true,
                              // The title becomes the news once the Omi is connected.
                              child: AnimatedSwitcher(
                                duration: OmiMotion.of(context).standard,
                                transitionBuilder: (child, animation) => FadeTransition(
                                  opacity: animation,
                                  child: SlideTransition(
                                    position: Tween(begin: const Offset(0, 0.25), end: Offset.zero).animate(animation),
                                    child: child,
                                  ),
                                ),
                                child: Text(
                                  _celebrating ? l10n.connected : l10n.onboardingConnectOmi,
                                  key: ValueKey(_celebrating),
                                  style: OmiType.title1,
                                  textAlign: TextAlign.center,
                                ),
                              ),
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
                            goNext: _connected,
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
                // Once the reader is connecting their own Omi, "Don't have your Omi yet?" no longer applies.
                // It fades out but keeps its space, so the device and title above don't jump.
                AnimatedOpacity(
                  opacity: provider.isConnected || provider.isClicked ? 0 : 1,
                  duration: const Duration(milliseconds: 200),
                  child: IgnorePointer(
                    ignoring: provider.isConnected || provider.isClicked,
                    child: _rise(
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
                  ),
                ),
              ],
            ),
          ),
        );
      },
    );
  }
}

/// Around the connected Omi: a ring that draws itself, a ✓ that lands where the ring closes, and
/// one pulse outward. Nothing shows until [active].
class _ConnectedHalo extends StatelessWidget {
  const _ConnectedHalo({required this.progress, required this.active, required this.diameter, required this.child});

  final Animation<double> progress;
  final bool active;
  final double diameter;
  final Widget child;

  static const _badge = 40.0;

  @override
  Widget build(BuildContext context) {
    if (!active) return child;
    return AnimatedBuilder(
      animation: progress,
      child: child,
      builder: (context, child) {
        final t = progress.value;
        final ring = Curves.easeInOutCubic.transform((t / 0.55).clamp(0.0, 1.0));
        final badge = Curves.easeOutBack.transform(((t - 0.45) / 0.35).clamp(0.0, 1.0));
        final pulse = Curves.easeOut.transform(((t - 0.5) / 0.5).clamp(0.0, 1.0));
        // The ✓ sits on the ring at its lower right, where the drawing ends.
        const angle = math.pi / 4;
        final r = diameter / 2;
        return Stack(
          alignment: Alignment.center,
          clipBehavior: Clip.none,
          children: [
            // One pulse outward as the ✓ lands.
            if (pulse > 0 && pulse < 1)
              Container(
                width: diameter * (1 + 0.22 * pulse),
                height: diameter * (1 + 0.22 * pulse),
                decoration: BoxDecoration(
                  shape: BoxShape.circle,
                  border: Border.all(color: OmiColors.textPrimary.withValues(alpha: 0.3 * (1 - pulse)), width: 2),
                ),
              ),
            SizedBox.square(
              dimension: diameter,
              child: CustomPaint(painter: _RingPainter(progress: ring, color: OmiColors.textPrimary)),
            ),
            child!,
            Transform.translate(
              offset: Offset(r * math.cos(angle), r * math.sin(angle)),
              child: Transform.scale(
                scale: badge,
                child: Container(
                  key: const Key('connect_omi_connected_badge'),
                  width: _badge,
                  height: _badge,
                  decoration: BoxDecoration(
                    color: OmiColors.accent,
                    shape: BoxShape.circle,
                    border: Border.all(color: OmiColors.surface0, width: 3),
                  ),
                  child: Icon(Icons.check_rounded, size: 22, color: OmiColors.onAccent),
                ),
              ),
            ),
          ],
        );
      },
    );
  }
}

class _RingPainter extends CustomPainter {
  _RingPainter({required this.progress, required this.color});

  final double progress;
  final Color color;

  @override
  void paint(Canvas canvas, Size size) {
    if (progress <= 0) return;
    final rect = Offset.zero & size;
    final paint = Paint()
      ..color = color
      ..style = PaintingStyle.stroke
      ..strokeWidth = 2.5
      ..strokeCap = StrokeCap.round;
    // Starts and closes under the ✓ (lower right), clockwise.
    canvas.drawArc(rect.deflate(1.25), math.pi / 4, 2 * math.pi * progress, false, paint);
  }

  @override
  bool shouldRepaint(covariant _RingPainter old) => old.progress != progress || old.color != color;
}
