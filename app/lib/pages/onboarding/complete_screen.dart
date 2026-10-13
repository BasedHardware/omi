import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/gen/pigeon_communicator.g.dart';
import 'package:omi/pages/capture/connect.dart';
import 'package:omi/providers/capture_provider.dart';
import 'package:omi/providers/onboarding_provider.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/analytics/registry/events.g.dart';
import 'package:omi/utils/analytics/registry/typed_events.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/platform/platform_manager.dart';
import 'first_capture_controller.dart';
import 'first_capture_io.dart';
import 'first_capture_page.dart';
import 'first_capture_layout.dart';

/// Keeps completion at persisted index 9. Child capture routes never mark
/// onboarding complete until the user sees a result, pairs, or explicitly skips.
class OnboardingCompleteScreen extends StatefulWidget {
  const OnboardingCompleteScreen(
      {super.key,
      required this.onComplete,
      this.emit,
      this.setProperty,
      this.phoneControllerFactory,
      this.pairDevice,
      this.watchStateProbe,
      this.showWatch,
      this.onSkipped});
  final VoidCallback onComplete;
  final VoidCallback? onSkipped;
  final void Function(RegisteredEvent)? emit;
  final void Function(String, Object)? setProperty;
  final FirstCaptureController Function()? phoneControllerFactory;
  final Future<bool> Function(BuildContext)? pairDevice;
  final Future<({bool paired, bool installed})> Function()? watchStateProbe;
  final bool? showWatch;

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
    // from a phone/Watch child. Replace that owner with Home, not the child.
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

  Future<void> _phone() async {
    if (_routing) return;
    _choose(OnboardingFirstCaptureChoiceSelectedChoice.phone);
    setState(() => _routing = true);
    final controller = widget.phoneControllerFactory?.call() ??
        FirstCaptureController(PhoneFirstCaptureIO(context.read<CaptureProvider>()), emit: _emit);
    await Navigator.of(context).push(
        omiPageRoute(builder: (_) => FirstCapturePage(controller: controller, onComplete: _complete, onSkip: _skip)));
    await controller.leave();
    controller.dispose();
    if (mounted) setState(() => _routing = false);
  }

  Future<void> _watch() async {
    if (_routing) return;
    _choose(OnboardingFirstCaptureChoiceSelectedChoice.appleWatch);
    setState(() => _routing = true);
    ({bool paired, bool installed})? state;
    try {
      state = await (widget.watchStateProbe ??
              () async {
                final host = WatchRecorderHostAPI();
                return (paired: await host.isWatchPaired(), installed: await host.isWatchAppInstalled());
              })()
          .timeout(const Duration(seconds: 2));
    } catch (_) {/* Instructions are useful even when WatchConnectivity is unavailable. */}
    if (!mounted) return;
    await Navigator.of(context).push(omiPageRoute(
        builder: (_) =>
            FirstCaptureWatchInstructions(paired: state?.paired, installed: state?.installed, onComplete: _complete)));
    if (mounted) setState(() => _routing = false);
  }

  @override
  Widget build(BuildContext context) {
    final watch = widget.showWatch ?? Theme.of(context).platform == TargetPlatform.iOS;
    return ColoredBox(
        color: OmiColors.surface0,
        child: FirstCaptureLayout(content: [
          Icon(Icons.mic_none, size: 64, color: OmiColors.textPrimary),
          const SizedBox(height: OmiSpacing.lg),
          Text(context.l10n.firstCaptureTitle, style: OmiType.title1, textAlign: TextAlign.center),
          const SizedBox(height: OmiSpacing.md),
          Text(context.l10n.firstCaptureDescription,
              style: OmiType.body.copyWith(color: OmiColors.textSecondary), textAlign: TextAlign.center),
          const SizedBox(height: OmiSpacing.xxl),
        ], actions: [
          OmiButton(
              variant: OmiButtonVariant.secondary,
              labelStyle: OmiType.callout.copyWith(
                  fontWeight: FontWeight.w600, fontFamily: Theme.of(context).textTheme.labelLarge?.fontFamily),
              key: const Key('first_capture_omi'),
              label: context.l10n.firstCaptureOmi,
              icon: Icons.bluetooth,
              expand: true,
              onPressed: _routing ? null : _omi),
          const SizedBox(height: OmiSpacing.md),
          if (watch) ...[
            OmiButton(
                variant: OmiButtonVariant.secondary,
                labelStyle: OmiType.callout.copyWith(
                    fontWeight: FontWeight.w600, fontFamily: Theme.of(context).textTheme.labelLarge?.fontFamily),
                key: const Key('first_capture_watch'),
                label: context.l10n.firstCaptureWatch,
                icon: Icons.watch_outlined,
                expand: true,
                onPressed: _routing ? null : _watch),
            const SizedBox(height: OmiSpacing.md),
          ],
          OmiButton(
              labelStyle: OmiType.callout.copyWith(
                  fontWeight: FontWeight.w600, fontFamily: Theme.of(context).textTheme.labelLarge?.fontFamily),
              key: const Key('first_capture_phone'),
              label: context.l10n.firstCapturePhone,
              icon: Icons.phone_iphone,
              expand: true,
              onPressed: _routing ? null : _phone),
          const SizedBox(height: OmiSpacing.lg),
          OmiButton(
              variant: OmiButtonVariant.tertiary,
              labelStyle: OmiType.callout.copyWith(
                  fontWeight: FontWeight.w600, fontFamily: Theme.of(context).textTheme.labelLarge?.fontFamily),
              key: const Key('onboarding_complete_start'),
              label: context.l10n.firstCaptureSkip,
              onPressed: _routing ? null : _skip),
        ]));
  }
}

class FirstCaptureWatchInstructions extends StatelessWidget {
  const FirstCaptureWatchInstructions({super.key, this.paired, this.installed, required this.onComplete});
  final bool? paired;
  final bool? installed;
  final VoidCallback onComplete;
  @override
  Widget build(BuildContext context) => Scaffold(
        appBar: AppBar(leading: const OmiBackButton(), title: Text(context.l10n.firstCaptureWatch)),
        body: FirstCaptureLayout(content: [
          Icon(Icons.watch_outlined, size: 64, color: OmiColors.textPrimary),
          const SizedBox(height: OmiSpacing.lg),
          Text(context.l10n.watchCaptureTitle, style: OmiType.title2, textAlign: TextAlign.center),
          const SizedBox(height: OmiSpacing.xl),
          if (paired == false || installed == false)
            Text(paired == false ? context.l10n.firstCaptureWatchPair : context.l10n.firstCaptureWatchInstall,
                style: OmiType.body.copyWith(color: OmiColors.textSecondary), textAlign: TextAlign.center)
          else
            for (final step in [
              context.l10n.watchCaptureOpen,
              context.l10n.watchCaptureRecord,
              context.l10n.watchCaptureSync
            ].indexed)
              Padding(
                padding: const EdgeInsets.only(bottom: OmiSpacing.md),
                child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
                  Text('${step.$1 + 1}.', style: OmiType.body),
                  const SizedBox(width: OmiSpacing.sm),
                  Expanded(child: Text(step.$2, style: OmiType.body.copyWith(color: OmiColors.textSecondary))),
                ]),
              ),
        ], actions: [
          OmiButton(
              key: const Key('watch_capture_continue'),
              labelStyle: OmiType.callout.copyWith(
                  fontWeight: FontWeight.w600, fontFamily: Theme.of(context).textTheme.labelLarge?.fontFamily),
              label: context.l10n.startUsingOmi,
              expand: true,
              onPressed: onComplete),
        ]),
      );
}
