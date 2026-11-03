import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/gen/assets.gen.dart';
import 'package:omi/pages/capture/connect.dart';
import 'package:omi/pages/shop/omi_shop.dart';
import 'package:omi/providers/onboarding_provider.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/analytics/registry/events.g.dart';
import 'package:omi/utils/analytics/registry/typed_events.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/platform/platform_manager.dart';
import 'first_capture_layout.dart';

/// The last onboarding step puts the device first: pair an Omi (the one main action), get one if
/// the reader has none (the store, in-app), or skip and go straight to Home without waiting.
/// Keeps completion at persisted index 9; pairing never marks onboarding complete until it
/// succeeds or the reader explicitly skips.
class OnboardingCompleteScreen extends StatefulWidget {
  const OnboardingCompleteScreen({
    super.key,
    required this.onComplete,
    this.emit,
    this.setProperty,
    this.pairDevice,
    this.openShop,
    this.onSkipped,
  });
  final VoidCallback onComplete;
  final VoidCallback? onSkipped;
  final void Function(RegisteredEvent)? emit;
  final void Function(String, Object)? setProperty;
  final Future<bool> Function(BuildContext)? pairDevice;

  /// Test seam: replaces [openOmiShop].
  final Future<void> Function(BuildContext)? openShop;

  @override
  State<OnboardingCompleteScreen> createState() => _OnboardingCompleteScreenState();
}

class _OnboardingCompleteScreenState extends State<OnboardingCompleteScreen> {
  bool _routing = false;
  bool _pairedOmi = false;
  void _emit(RegisteredEvent event) => (widget.emit ?? const TypedEvents().emit)(event);
  void _property(String key, Object value) =>
      (widget.setProperty ?? PlatformManager.instance.analytics.setUserProperty)(key, value);

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (mounted) _emit(const OnboardingFirstCaptureShown());
    });
  }

  void _choose(OnboardingFirstCaptureChoiceSelectedChoice choice) {
    _property('capture_choice', choice.wireName);
    // Pairing evidence owns the device property; a selected route is only intent.
    final hasOmi = _pairedOmi ||
        SharedPreferencesUtil().btDevices.any((device) => device.id.isNotEmpty && device.type == DeviceType.omi);
    _property('has_omi_device', hasOmi);
    _emit(OnboardingFirstCaptureChoiceSelected(choice: choice));
  }

  void _complete() {
    // Completion belongs to the persisted wrapper route, even when invoked
    // from a pairing child. Replace that owner with Home, not the child.
    final owner = ModalRoute.of(context);
    if (owner != null) Navigator.of(context).popUntil((route) => route == owner);
    widget.onComplete();
  }

  void _skip() {
    _choose(OnboardingFirstCaptureChoiceSelectedChoice.skipped);
    _emit(const OnboardingFirstCaptureSkipped());
    widget.onSkipped?.call();
    _complete();
  }

  Future<void> _omi() async {
    if (_routing) return;
    _choose(OnboardingFirstCaptureChoiceSelectedChoice.omi);
    setState(() => _routing = true);
    bool paired;
    if (widget.pairDevice != null) {
      paired = await widget.pairDevice!(context);
    } else {
      final connected = await Navigator.of(context).push<bool>(omiPageRoute(
        builder: (routeContext) => ConnectDevicePage(
          onConnected: () => Navigator.of(routeContext).pop(true),
        ),
      ));
      if (!mounted) return;
      paired = connected == true &&
          context.read<OnboardingProvider>().isConnected &&
          context.read<OnboardingProvider>().deviceType == DeviceType.omi;
    }
    if (!mounted) return;
    setState(() => _routing = false);
    if (paired) {
      _pairedOmi = true;
      _property('has_omi_device', true);
      _complete();
    } // Home owns the existing CV1 tutorial gate.
  }

  /// No device yet: the store opens in-app and the reader lands back here, where Skip is one tap.
  Future<void> _shop() async {
    if (_routing) return;
    setState(() => _routing = true);
    await (widget.openShop ??
        (BuildContext context) => openOmiShop(context, source: 'onboarding_first_capture'))(context);
    if (mounted) setState(() => _routing = false);
  }

  @override
  Widget build(BuildContext context) {
    final labelStyle = OmiType.callout
        .copyWith(fontWeight: FontWeight.w600, fontFamily: Theme.of(context).textTheme.labelLarge?.fontFamily);
    return ColoredBox(
        color: OmiColors.surface0,
        child: FirstCaptureLayout(content: [
          Assets.images.omiWithRopeNoPadding.image(
            height: 180,
            fit: BoxFit.contain,
            errorBuilder: (_, __, ___) => Icon(Icons.bluetooth, size: 64, color: OmiColors.textPrimary),
          ),
          const SizedBox(height: OmiSpacing.lg),
          Text(context.l10n.firstCaptureConnectTitle, style: OmiType.title1, textAlign: TextAlign.center),
          const SizedBox(height: OmiSpacing.md),
          Text(context.l10n.firstCaptureConnectDescription,
              style: OmiType.body.copyWith(color: OmiColors.textSecondary), textAlign: TextAlign.center),
          const SizedBox(height: OmiSpacing.xxl),
        ], actions: [
          OmiButton(
              labelStyle: labelStyle,
              key: const Key('first_capture_omi'),
              label: context.l10n.firstCaptureConnect,
              icon: Icons.bluetooth,
              expand: true,
              onPressed: _routing ? null : _omi),
          const SizedBox(height: OmiSpacing.md),
          OmiButton(
              variant: OmiButtonVariant.secondary,
              labelStyle: labelStyle,
              key: const Key('first_capture_shop'),
              label: context.l10n.firstCaptureNoDevice,
              expand: true,
              onPressed: _routing ? null : _shop),
          const SizedBox(height: OmiSpacing.lg),
          OmiButton(
              variant: OmiButtonVariant.tertiary,
              labelStyle: labelStyle,
              key: const Key('onboarding_complete_start'),
              label: context.l10n.firstCaptureSkip,
              onPressed: _routing ? null : _skip),
        ]));
  }
}
